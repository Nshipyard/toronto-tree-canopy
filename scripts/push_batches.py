#!/usr/bin/env python3
"""Push the city-wide product to GitHub in sequential batches.

Uses ~/workspace/skills/github/bin/gh_push.py (git database API, one commit
per invocation). Batches run SEQUENTIALLY: each gh_push reads the current head
ref, so parallel pushes would clobber each other.

Order (matters for the live site):
  1. data batches (shards, index, COGs, downloads, boundary) - no code change,
     the old app keeps serving from data/parcel_canopy_ward12.json
  2. verify jsDelivr serves a shard (the driver only reports; verify manually)
  3. code batch - triggers the Vercel deploy of the sharded API

Usage:
  python3 scripts/push_batches.py --step data    # shards+index+cogs+downloads+boundary
  python3 scripts/push_batches.py --step code    # src, scripts, configs, docs
  python3 scripts/push_batches.py --step shards  # just the shard batches
Run from the repo root. Logs commit SHAs to /tmp/push_batches.log.
"""
import argparse
import os
import subprocess
import sys

REPO = "Nshipyard/toronto-tree-canopy"
BRANCH = "main"
GH_PUSH = os.path.expanduser("~/workspace/skills/github/bin/gh_push.py")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = "/tmp/push_batches.log"
BATCH = 250


def log(msg):
    line = f"{msg}"
    print(line, flush=True)
    with open(LOG, "a") as fh:
        fh.write(line + "\n")


def push(message, specs):
    """specs: list of (repo_path, local_path). One commit."""
    cmd = [sys.executable, GH_PUSH, "--repo", REPO, "--branch", BRANCH,
           "--message", message]
    for repo_path, local_path in specs:
        cmd.append(f"{repo_path}={local_path}")
    log(f"PUSH: {message} ({len(specs)} files)")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        log(f"FAILED: {r.stderr[-2000:]}")
        raise SystemExit(f"push failed: {message}")
    log(f"OK: {r.stdout.strip()}")
    return r.stdout.strip()


def shards(start_batch=0):
    d = os.path.join(ROOT, "data", "shards")
    files = sorted(f for f in os.listdir(d) if f.endswith(".json")
                   and f not in ("parcel_index.json", "manifest.json"))
    log(f"{len(files)} shard files")
    nbatches = (len(files) + BATCH - 1) // BATCH
    for bi in range(start_batch, nbatches):
        i = bi * BATCH
        chunk = files[i:i + BATCH]
        specs = [(f"data/shards/{f}", os.path.join(d, f)) for f in chunk]
        # retry each batch up to 3 times on transient network errors
        for attempt in range(3):
            try:
                push(f"city canopy shards {bi + 1}/{nbatches} ({len(chunk)} cells)",
                     specs)
                break
            except SystemExit as e:
                if attempt == 2:
                    raise
                log(f"retry {attempt + 1}/3 after failure: {e}")


def data_rest():
    d = os.path.join(ROOT, "data")
    specs = [
        ("data/shards/parcel_index.json", os.path.join(d, "shards", "parcel_index.json")),
        ("data/city_boundary.json", os.path.join(d, "city_boundary.json")),
    ]
    cogs = sorted(f for f in os.listdir(os.path.join(d, "cogs")) if f.endswith(".tif"))
    specs += [(f"data/cogs/{f}", os.path.join(d, "cogs", f)) for f in cogs]
    dls = sorted(os.listdir(os.path.join(d, "downloads")))
    specs += [(f"data/downloads/{f}", os.path.join(d, "downloads", f)) for f in dls]
    log(f"index + boundary + {len(cogs)} COGs + {len(dls)} downloads")
    # split to keep each push modest
    for i in range(0, len(specs), BATCH):
        push(f"city canopy static data {i // BATCH + 1}", specs[i:i + BATCH])


def code():
    specs = []
    for base, _, files in os.walk(os.path.join(ROOT, "src")):
        for f in files:
            full = os.path.join(base, f)
            specs.append((os.path.relpath(full, ROOT), full))
    for base, _, files in os.walk(os.path.join(ROOT, "scripts")):
        if "proto_api" in base:
            continue  # Worker 2 scratch prototypes; superseded, not shipped
        for f in files:
            if f == "push_batches.py":
                continue
            full = os.path.join(base, f)
            specs.append((os.path.relpath(full, ROOT), full))
    for f in ["README.md", "next.config.ts", "package.json", "package-lock.json",
              ".gitignore", "DESIGN_BRIEF.md"]:
        full = os.path.join(ROOT, f)
        if os.path.exists(full):
            specs.append((f, full))
    # data pipeline scripts (new, untracked)
    for f in ["data/lidar/build_footprint_index.py", "data/lidar/ward_plan.py",
              "data/lidar/build_parcel_index.py", "data/lidar/prefetch_chunks.py",
              "data/lidar/compute_tile.py", "data/lidar/run_all_tiles.sh"]:
        full = os.path.join(ROOT, f)
        if os.path.exists(full):
            specs.append((f, full))
    log(f"{len(specs)} code/config/doc files")
    for i in range(0, len(specs), BATCH):
        push(f"city-wide canopy API {i // BATCH + 1}", specs[i:i + BATCH])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["data", "shards", "data_rest", "code"],
                    required=True)
    ap.add_argument("--start-batch", type=int, default=0,
                    help="resume shards from this 0-based batch index")
    args = ap.parse_args()
    os.chdir(ROOT)
    if args.step == "data":
        shards()
        data_rest()
    elif args.step == "shards":
        shards(args.start_batch)
    elif args.step == "data_rest":
        data_rest()
    elif args.step == "code":
        code()
    log("STEP DONE")


if __name__ == "__main__":
    main()
