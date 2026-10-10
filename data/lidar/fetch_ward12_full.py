"""Fetch the FULL Ward 12 DSM+DTM from the NRCan HRDEM mosaic WCS.

Covers the Track B pilot ward (lon -79.4706..-79.4208, lat 43.6406..43.6957)
plus margin for the 6 m neighbour-buffer stats. Reuses the round-1 0.015 deg
chunk grid (files dsm_I_J.tif / dtm_I_J.tif, skipped when already present) and
adds a west extension column (dsm_W_J / dtm_W_J) because the ward's western
edge sits 0.0006 deg west of the original grid.

Full-ward single requests 500 (GeoTrellis backend); keep requests <= 0.015 deg.
Run: .venv/bin/python3 data/lidar/fetch_ward12_full.py
"""
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

BASE = "https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wcs", "chunks")
os.makedirs(OUT, exist_ok=True)

# (name, layer, lon0, lon1, lat0, lat1)
JOBS = []
LON0, LON1, LAT0, LAT1, STEP = -79.47, -79.41, 43.64, 43.70, 0.015
for layer in ("dsm", "dtm"):
    for i in range(4):
        for j in range(4):
            JOBS.append((
                f"{layer}_{i}_{j}", layer,
                LON0 + STEP * i, LON0 + STEP * (i + 1),
                LAT0 + STEP * j, LAT0 + STEP * (j + 1),
            ))
    # west extension column: overlaps column 0, extends past the ward's west edge
    for j in range(4):
        JOBS.append((
            f"{layer}_W_{j}", layer,
            -79.476, -79.466,
            LAT0 + STEP * j, LAT0 + STEP * (j + 1),
        ))


def fetch(job):
    name, layer, lon_a, lon_b, lat_a, lat_b = job
    fn = os.path.join(OUT, f"{name}.tif")
    if os.path.exists(fn) and os.path.getsize(fn) > 10000:
        return (name, True, "cached")
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
            return (name, True, "fetched")
        time.sleep(5)
    return (name, False, f"code={code}")


def main():
    ok = True
    with ThreadPoolExecutor(max_workers=4) as ex:
        for name, good, note in ex.map(fetch, JOBS):
            print(f"{name}: {'ok' if good else 'FAIL'} ({note})", flush=True)
            ok = ok and good
    print("ALL DONE" if ok else "SOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
