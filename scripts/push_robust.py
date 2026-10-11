#!/usr/bin/env python3
"""Robustly push missing shard files with small batches, delays, and retries.

Usage: python3 scripts/push_robust.py
Resumes automatically by comparing local files to the remote tree.
"""
import os
import subprocess
import sys
import time
import json

REPO = "Nshipyard/toronto-tree-canopy"
BRANCH = "main"
GH_PUSH = os.path.expanduser("~/workspace/skills/github/bin/gh_push.py")
GH_READ = os.path.expanduser("~/workspace/skills/github/bin/gh_read.py")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCH = 50
DELAY = 5  # seconds between batches


def get_remote_files():
    """Get set of data/shards/*.json paths on remote."""
    r = subprocess.run(
        [sys.executable, GH_READ, "tree", REPO],
        capture_output=True, text=True, cwd=ROOT, timeout=120,
    )
    # gh_read tree outputs lines like "  1234  path/to/file"
    files = set()
    for line in r.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1].startswith("data/shards/"):
            files.add(parts[1])
    return files


def push_batch(specs, batch_no, total_batches):
    """Push one batch with retries."""
    cmd = [sys.executable, GH_PUSH, "--repo", REPO, "--branch", BRANCH,
           "--message", f"city canopy shards robust {batch_no}/{total_batches}"]
    for repo_path, local_path in specs:
        cmd.append(f"{repo_path}={local_path}")
    for attempt in range(5):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT,
                           timeout=300)
        if r.returncode == 0:
            print(f"  batch {batch_no}: OK ({len(specs)} files)", flush=True)
            return True
        print(f"  batch {batch_no}: attempt {attempt + 1} failed, "
              f"retrying in {2 ** attempt * 10}s...", flush=True)
        time.sleep(2 ** attempt * 10)
    print(f"  batch {batch_no}: FAILED after 5 attempts", flush=True)
    return False


def main():
    os.chdir(ROOT)
    print("fetching remote tree...", flush=True)
    remote = get_remote_files()
    print(f"remote has {len(remote)} shard files", flush=True)

    d = os.path.join(ROOT, "data", "shards")
    local = sorted(f for f in os.listdir(d) if f.endswith(".json")
                   and f not in ("parcel_index.json", "manifest.json"))
    missing = [f for f in local if f"data/shards/{f}" not in remote]
    print(f"missing: {len(missing)} files", flush=True)

    if not missing:
        print("all shards already pushed!", flush=True)
        return

    nbatches = (len(missing) + BATCH - 1) // BATCH
    for bi in range(nbatches):
        chunk = missing[bi * BATCH:(bi + 1) * BATCH]
        specs = [(f"data/shards/{f}", os.path.join(d, f)) for f in chunk]
        ok = push_batch(specs, bi + 1, nbatches)
        if not ok:
            print(f"STOPPING at batch {bi + 1}", flush=True)
            sys.exit(1)
        if bi < nbatches - 1:
            time.sleep(DELAY)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
