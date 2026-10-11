"""Prefetch all unique WCS DSM/DTM chunks for the city-wide run.

Reads data/tile_plan.json, fetches every (layer, i, j) chunk once into
data/lidar/wcs/city_chunks/ (skips files already present and >10 KB).
Run in the background while the tile compute pipeline is built:
  .venv/bin/python3 data/lidar/prefetch_chunks.py

Same WCS endpoint and request shape as the Ward 12 pilot
(data/lidar/fetch_ward12_full.py): NRCan HRDEM mosaic, WCS 1.1.1,
layers dsm/dtm, <=0.015 deg requests.
"""
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(HERE, "wcs", "city_chunks")
os.makedirs(OUT, exist_ok=True)

BASE = "https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic"
STEP = 0.015


def fetch(job):
    layer, i, j = job
    fn = os.path.join(OUT, f"{layer}_{i}_{j}.tif")
    if os.path.exists(fn) and os.path.getsize(fn) > 10000:
        return (layer, i, j, True, "cached")
    lon_a, lon_b = i * STEP, (i + 1) * STEP
    lat_a, lat_b = j * STEP, (j + 1) * STEP
    url = (f"{BASE}?service=WCS&request=GetCoverage&version=1.1.1&Identifier={layer}"
           f"&boundingbox={lat_a},{lon_a},{lat_b},{lon_b},urn:ogc:def:crs:EPSG::4326"
           f"&format=image/geotiff")
    code = "?"
    for _ in range(3):
        r = subprocess.run(
            ["curl", "-s", "--max-time", "300", "-o", fn, "-w", "%{http_code}", url],
            capture_output=True, text=True)
        code = r.stdout.strip()
        if code == "200" and os.path.exists(fn) and os.path.getsize(fn) > 10000:
            return (layer, i, j, True, "fetched")
        time.sleep(5)
    return (layer, i, j, False, f"code={code}")


def main():
    plan = json.load(open(os.path.join(DATA, "tile_plan.json")))
    jobs = set()
    for tl in plan["tiles"]:
        (i0, i1), (j0, j1) = tl["chunk_i"], tl["chunk_j"]
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                jobs.add(("dsm", i, j))
                jobs.add(("dtm", i, j))
    jobs = sorted(jobs)
    print(f"{len(jobs)} chunk requests", flush=True)
    ok, fail = 0, []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for layer, i, j, good, note in ex.map(fetch, jobs):
            if good:
                ok += 1
            else:
                fail.append((layer, i, j, note))
            if (ok + len(fail)) % 50 == 0:
                print(f"  {ok + len(fail)}/{len(jobs)} done, {len(fail)} failed",
                      flush=True)
    print(f"PREFETCH DONE: {ok} ok, {len(fail)} failed", flush=True)
    for f in fail:
        print("  FAIL", f, flush=True)
    sys.exit(0 if not fail else 1)


if __name__ == "__main__":
    main()
