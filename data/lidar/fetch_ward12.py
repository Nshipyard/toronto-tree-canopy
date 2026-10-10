"""Fetch Ward 12 DSM+DTM from NRCan HRDEM mosaic WCS in small chunks, then mosaic."""
import subprocess, os, sys, time

BASE = "https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic"
OUT = os.path.expanduser("~/workspace/toronto-tree-canopy/data/lidar/wcs/chunks")
# Ward 12 bbox (lon/lat)
LON0, LON1 = -79.47, -79.41
LAT0, LAT1 = 43.64, 43.70
N = 4  # 4x4 chunks

def fetch(layer, i, j):
    lon_a = LON0 + (LON1 - LON0) * i / N
    lon_b = LON0 + (LON1 - LON0) * (i + 1) / N
    lat_a = LAT0 + (LAT1 - LAT0) * j / N
    lat_b = LAT0 + (LAT1 - LAT0) * (j + 1) / N
    fn = f"{OUT}/{layer}_{i}_{j}.tif"
    if os.path.exists(fn) and os.path.getsize(fn) > 10000:
        return True
    url = (f"{BASE}?service=WCS&request=GetCoverage&version=1.1.1&Identifier={layer}"
           f"&boundingbox={lat_a},{lon_a},{lat_b},{lon_b},urn:ogc:def:crs:EPSG::4326&format=image/geotiff")
    for attempt in range(3):
        r = subprocess.run(["curl", "-s", "--max-time", "300", "-o", fn, "-w", "%{http_code}", url],
                           capture_output=True, text=True)
        code = r.stdout.strip()
        if code == "200" and os.path.getsize(fn) > 10000:
            return True
        time.sleep(5)
    print(f"FAILED {layer} {i},{j} code={code}", flush=True)
    return False

ok = True
for layer in ["dsm", "dtm"]:
    for i in range(N):
        for j in range(N):
            r = fetch(layer, i, j)
            ok = ok and r
            print(f"{layer} chunk {i},{j}: {'ok' if r else 'FAIL'}", flush=True)
print("ALL DONE" if ok else "SOME FAILED")
