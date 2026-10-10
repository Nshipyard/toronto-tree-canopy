"""Fetch DSM+DTM for the QA tile area from NRCan HRDEM mosaic WCS in small chunks.

Window: lon -79.455..-79.405, lat 43.665..43.69 (covers qa1, qa3, qa7 footprints
with margin). Chunk size ~0.0125 deg (single big requests return HTTP 500).
Saves into data/lidar/qa_cover/chunks/.
"""
import subprocess, os, sys, time

BASE = "https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic"
OUT = os.path.expanduser("~/workspace/toronto-tree-canopy/data/lidar/qa_cover/chunks")
os.makedirs(OUT, exist_ok=True)

# QA cover window (lon/lat)
LON0, LON1 = -79.455, -79.405
LAT0, LAT1 = 43.665, 43.69
NX, NY = 4, 2  # chunks: ~0.0125 deg each

def fetch(layer, i, j):
    lon_a = LON0 + (LON1 - LON0) * i / NX
    lon_b = LON0 + (LON1 - LON0) * (i + 1) / NX
    lat_a = LAT0 + (LAT1 - LAT0) * j / NY
    lat_b = LAT0 + (LAT1 - LAT0) * (j + 1) / NY
    fn = f"{OUT}/{layer}_{i}_{j}.tif"
    if os.path.exists(fn) and os.path.getsize(fn) > 10000:
        return True
    url = (f"{BASE}?service=WCS&request=GetCoverage&version=1.1.1&Identifier={layer}"
           f"&boundingbox={lat_a},{lon_a},{lat_b},{lon_b},urn:ogc:def:crs:EPSG::4326&format=image/geotiff")
    for attempt in range(3):
        r = subprocess.run(["curl", "-s", "--max-time", "300", "-o", fn, "-w", "%{http_code}", url],
                           capture_output=True, text=True)
        code = r.stdout.strip()
        if code == "200" and os.path.exists(fn) and os.path.getsize(fn) > 10000:
            return True
        time.sleep(5)
    print(f"FAILED {layer} {i},{j} code={code}", flush=True)
    return False

ok = True
for layer in ["dsm", "dtm"]:
    for j in range(NY):
        for i in range(NX):
            r = fetch(layer, i, j)
            ok = ok and r
            print(f"{layer} chunk {i},{j}: {'ok' if r else 'FAIL'}", flush=True)
print("ALL DONE" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
