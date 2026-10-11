#!/usr/bin/env python3
"""probe_wcs_coverage.py - verify NRCan HRDEM mosaic WCS (GTA_2023 LiDAR) covers all of Toronto.

Samples points on a grid inside the city union polygon, fetches a small DSM+DTM
GetCoverage window around each, and measures the valid-pixel fraction. Reports
the covered fraction of the city and lists gap areas honestly.

Usage: .venv/bin/python scripts/probe_wcs_coverage.py
Output: data/coverage_probe.json (gitignored working file)
"""
import csv, json, math, os, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = "https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic"
OUT = os.path.join(ROOT, "data", "coverage_probe.json")
CITY = "/tmp/city_union.geojson"
STEP = 0.015          # grid spacing in degrees (~1.6 km)
WIN = 0.0015          # half-width of each probe window (~160 m)
WORKERS = 4

csv.field_size_limit(10**9)


def load_city():
    from shapely.geometry import shape
    g = json.load(open(CITY))
    return shape(g["geometry"] if g["type"] == "Feature" else g)


def fetch(layer, lon, lat):
    lat_a, lat_b = lat - WIN, lat + WIN
    lon_a, lon_b = lon - WIN, lon + WIN
    url = (f"{BASE}?service=WCS&request=GetCoverage&version=1.1.1&Identifier={layer}"
           f"&boundingbox={lat_a},{lon_a},{lat_b},{lon_b},urn:ogc:def:crs:EPSG::4326"
           f"&format=image/geotiff")
    fn = tempfile.mktemp(suffix=".tif")
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "120", "-o", fn,
                            "-w", "%{http_code}", url],
                           capture_output=True, text=True)
        code = r.stdout.strip()
        if code != "200" or not os.path.exists(fn) or os.path.getsize(fn) < 500:
            return None, f"http={code}"
        return fn, None
    except Exception as e:
        return None, str(e)


def valid_fraction(fn):
    import numpy as np
    import rasterio
    with rasterio.open(fn) as ds:
        a = ds.read(1)
        nd = ds.nodata
        if nd is None:
            nd = -9999.0
        mask = np.isfinite(a) & (a != nd)
        return float(mask.sum()) / mask.size, a.shape


def probe(pt):
    lon, lat = pt
    res = {"lon": round(lon, 5), "lat": round(lat, 5)}
    for layer in ("dsm", "dtm"):
        fn, err = fetch(layer, lon, lat)
        if err:
            res[layer] = {"error": err}
        else:
            try:
                vf, shp = valid_fraction(fn)
                res[layer] = {"valid_frac": round(vf, 4), "shape": shp}
            except Exception as e:
                res[layer] = {"error": f"read: {e}"}
            finally:
                try:
                    os.unlink(fn)
                except OSError:
                    pass
    return res


def main():
    city = load_city()
    x0, y0, x1, y1 = city.bounds
    print(f"city bbox: {x0:.4f},{y0:.4f} -> {x1:.4f},{y1:.4f}", flush=True)
    from shapely.prepared import prep
    pc = prep(city)
    pts = []
    lon = x0 + STEP / 2
    while lon < x1:
        lat = y0 + STEP / 2
        while lat < y1:
            if pc.contains(__import__("shapely.geometry", fromlist=["Point"]).Point(lon, lat)):
                pts.append((lon, lat))
            lat += STEP
        lon += STEP
    print(f"probe points inside city: {len(pts)}", flush=True)

    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, r in enumerate(ex.map(probe, pts)):
            results.append(r)
            if (i + 1) % 20 == 0:
                print(f"  probed {i+1}/{len(pts)}", flush=True)

    def covered(r):
        d = r.get("dsm", {})
        t = r.get("dtm", {})
        return (d.get("valid_frac", 0) or 0) > 0.5 and (t.get("valid_frac", 0) or 0) > 0.5

    def gap(r):
        d = r.get("dsm", {}).get("valid_frac")
        t = r.get("dtm", {}).get("valid_frac")
        return d is not None and t is not None and d < 0.05 and t < 0.05

    n = len(results)
    n_cov = sum(1 for r in results if covered(r))
    n_gap = sum(1 for r in results if gap(r))
    gaps = [{"lon": r["lon"], "lat": r["lat"],
             "dsm": r.get("dsm", {}).get("valid_frac"),
             "dtm": r.get("dtm", {}).get("valid_frac")}
            for r in results if gap(r)]
    errors = [r for r in results
              if "error" in r.get("dsm", {}) or "error" in r.get("dtm", {})]
    report = {
        "source": "NRCan HRDEM mosaic WCS (GTA_2023 TRCA LiDAR), layers dsm+dtm",
        "method": f"{n} grid points at {STEP} deg spacing inside city union; "
                  f"{2*WIN} deg probe windows; covered = >50% valid pixels in BOTH layers",
        "n_points": n,
        "n_covered": n_cov,
        "n_gap": n_gap,
        "n_error": len(errors),
        "covered_frac": round(n_cov / n, 4) if n else None,
        "gap_points": gaps,
        "error_points": [{"lon": r["lon"], "lat": r["lat"]} for r in errors],
        "all": results,
    }
    json.dump(report, open(OUT, "w"))
    print(f"covered {n_cov}/{n} = {n_cov/n:.1%}  gaps={n_gap} errors={len(errors)}", flush=True)
    for g in gaps:
        print(f"  GAP lon={g['lon']} lat={g['lat']} dsm={g['dsm']} dtm={g['dtm']}", flush=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
