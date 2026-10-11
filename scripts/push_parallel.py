#!/usr/bin/env python3
"""Parallel blob uploader with read-remote-then-push semantics.

Uploads missing shard files using parallel blob POSTs (10 workers), then
creates a single tree/commit/ref-update. Same safety as gh_push.py (reads
head ref first, fails if head moved), but 10x faster for many files.

Usage: python3 scripts/push_parallel.py
"""
import os
import sys
import json
import base64
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

REPO = "Nshipyard/toronto-tree-canopy"
BRANCH = "main"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKERS = 5
CREDENTIAL = "custom.github"
API_BASE = "https://api.github.com"
ALLOWED = ["api.github.com"]


def api(path, method="GET", body=None):
    """Authenticated GitHub API request (same auth as gh_push.py) with retry."""
    data = None
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    for attempt in range(5):
        req = urllib.request.Request(API_BASE + path, data=data,
                                     headers=headers, method=method)
        add_surrogate_to_request(req, CREDENTIAL, allowed_hosts=ALLOWED)
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            return read_json_response(resp)
        except urllib.error.HTTPError as exc:
            if exc.code in (500, 502, 503, 429) and attempt < 4:
                time.sleep(2 ** attempt * 2)
                continue
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise SystemExit(f"HTTP {exc.code} {method} {path}: {detail}")
        except Exception:
            if attempt < 4:
                time.sleep(2 ** attempt * 2)
                continue
            raise
    raise RuntimeError("API failed after retries")


def upload_blob(args):
    """Upload one file as a blob, return (repo_path, sha) or (repo_path, None)."""
    repo_path, local_path = args
    with open(local_path, "rb") as fh:
        raw = fh.read()
    content = base64.b64encode(raw).decode()
    body = {"content": content, "encoding": "base64"}
    for attempt in range(5):
        try:
            resp = api(f"/repos/{REPO}/git/blobs", method="POST", body=body)
            return (repo_path, resp["sha"], None)
        except SystemExit as e:
            msg = str(e)
            # HTTP 400 malformed: don't retry, it's a bad file
            if "HTTP 400" in msg:
                return (repo_path, None, f"400: {local_path} ({len(raw)} bytes)")
            if attempt < 4:
                time.sleep(2 ** attempt * 3)
                continue
            return (repo_path, None, f"failed: {msg[:200]}")
        except Exception as e:
            if attempt < 4:
                time.sleep(2 ** attempt * 3)
                continue
            return (repo_path, None, f"failed: {str(e)[:200]}")
    return (repo_path, None, "retries exhausted")


def main():
    os.chdir(ROOT)
    # 1. Read remote tree to find missing files
    print("reading remote tree...", flush=True)
    # Use gh_read.py tree (it handles auth)
    import subprocess
    r = subprocess.run(
        [sys.executable,
         os.path.expanduser("~/workspace/skills/github/bin/gh_read.py"),
         "tree", REPO],
        capture_output=True, text=True, timeout=120)
    remote = set()
    for line in r.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1].startswith("data/shards/"):
            remote.add(parts[1])
    print(f"remote has {len(remote)} shard files", flush=True)

    d = os.path.join(ROOT, "data", "shards")
    local = sorted(f for f in os.listdir(d) if f.endswith(".json")
                   and f not in ("parcel_index.json", "manifest.json"))
    missing = [(f"data/shards/{f}", os.path.join(d, f))
               for f in local if f"data/shards/{f}" not in remote]
    print(f"uploading {len(missing)} blobs with {WORKERS} workers...", flush=True)

    # 2. Upload blobs in parallel
    blob_shas = {}
    failed = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(upload_blob, (rp, lp)) for rp, lp in missing]
        done = 0
        for fut in as_completed(futures):
            rp, sha, err = fut.result()
            done += 1
            if sha:
                blob_shas[rp] = sha
            else:
                failed.append((rp, err))
            if done % 500 == 0:
                print(f"  {done}/{len(missing)} blobs", flush=True)
    print(f"uploaded {len(blob_shas)}/{len(missing)} blobs", flush=True)
    if failed:
        print(f"FAILED {len(failed)} blobs:", flush=True)
        for rp, err in failed[:10]:
            print(f"  {err}", flush=True)
        # Save failed list for retry
        with open("/tmp/push_failed.json", "w") as fh:
            json.dump([rp for rp, _ in failed], fh)
        sys.exit(1)

    # 3. Read head ref (read-remote-then-push)
    ref = api(f"/repos/{REPO}/git/ref/heads/{BRANCH}")
    head_sha = ref["object"]["sha"]
    print(f"head: {head_sha[:8]}", flush=True)

    # 4. Get base tree and create new tree with blobs
    commit = api(f"/repos/{REPO}/git/commits/{head_sha}")
    base_tree = commit["tree"]["sha"]
    tree_items = [{"path": rp, "mode": "100644", "type": "blob", "sha": sha}
                  for rp, sha in blob_shas.items()]
    # GitHub tree API limits to 1000 items per request; chunk if needed
    # For simplicity, assume < 100k items is OK (it is, but chunk to be safe)
    tree_sha = None
    # Actually, we need to build incrementally. Simpler: create tree with
    # base_tree and all items (GitHub allows up to 100,000).
    tree_resp = api(f"/repos/{REPO}/git/trees",
                    method="POST",
                    body={"base_tree": base_tree, "tree": tree_items})
    tree_sha = tree_resp["sha"]
    print(f"tree: {tree_sha[:8]}", flush=True)

    # 5. Create commit
    commit_resp = api(f"/repos/{REPO}/git/commits",
                      method="POST",
                      body={"message": f"city canopy shards bulk ({len(blob_shas)} files)",
                            "tree": tree_sha, "parents": [head_sha]})
    new_sha = commit_resp["sha"]
    print(f"commit: {new_sha[:8]}", flush=True)

    # 6. Update ref (fails if head moved)
    api(f"/repos/{REPO}/git/ref/heads/{BRANCH}",
        method="PATCH",
        body={"sha": new_sha})
    print(f"PUSHED {len(blob_shas)} files in one commit: {new_sha}", flush=True)


if __name__ == "__main__":
    main()
