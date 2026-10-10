"""Step 2: mask the Ward 12 CHM under City building footprints.

Rasterizes data/lidar/raw/building_outlines_4326.geojson (City of Toronto
"Topographic Mapping - Building Outlines", 557,694 outlines) at the CHM's
native grid, with a 2 m buffer (Track A method, data/TRACKA_REPORT.md section 4:
footprints in 4326 -> 3857 for the 2 m buffer -> back to 4326 for rasterize),
and sets the ward CHM to NaN under the mask BEFORE any metric computation.

Input:  data/lidar/wcs/ward12_chm_full.tif (EPSG:4326 1 m, nodata -9999)
Output: data/lidar/wcs/ward12_chm_full_masked.tif (gitignored, nodata -9999;
        NaN under buffered footprints, identical elsewhere)

Run: .venv/bin/python3 data/lidar/mask_chm.py
"""
import json
import os

import numpy as np
import rasterio
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.ops import transform as shp_transform
from shapely.prepared import prep
from pyproj import Transformer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHM_IN = os.path.join(HERE, "wcs", "ward12_chm_full.tif")
CHM_OUT = os.path.join(HERE, "wcs", "ward12_chm_full_masked.tif")
GEOJSON = os.path.join(HERE, "raw", "building_outlines_4326.geojson")
WARD_GEO = os.path.join(ROOT, "ward12.geojson")

BUF_M = 2.0  # Track A buffer (m)


def main():
    src = rasterio.open(CHM_IN)
    chm = src.read(1).astype("float32")
    transform, shape_px = src.transform, chm.shape
    profile = src.profile.copy()
    extent = (src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top)
    src.close()
    print(f"CHM {shape_px}, extent {extent}", flush=True)

    wgeo = json.load(open(WARD_GEO))["features"][0]["geometry"]
    ward = shape(wgeo)
    wprep = prep(ward)
    wxs = [c[0] for c in ward.exterior.coords]
    wys = [c[1] for c in ward.exterior.coords]
    wbbox = (min(wxs), min(wys), max(wxs), max(wys))

    fwd = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    back = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    def to3857(x, y):
        return fwd.transform(x, y)

    def to4326(x, y):
        return back.transform(x, y)

    # collect buffered footprint polygons intersecting the ward, in 4326
    polys = []
    total = 0
    with open(GEOJSON) as fh:
        for line in fh:
            s = line.strip()
            if not s.startswith('{ "type": "Feature"'):
                continue
            try:
                # feature lines carry the GeoJSON array's trailing comma
                feat = json.loads(s[:-1] if s.endswith(",") else s)
            except json.JSONDecodeError:
                continue
            total += 1
            geom = feat.get("geometry")
            if not geom:
                continue
            try:
                g = shape(geom)
            except Exception:
                continue
            gb = g.bounds
            if gb[2] < wbbox[0] or gb[0] > wbbox[2] or gb[3] < wbbox[1] or gb[1] > wbbox[3]:
                continue
            if not wprep.intersects(g):
                continue
            gb3857 = shp_transform(to3857, g)
            if gb3857.is_empty:
                continue
            polys.append(shp_transform(to4326, gb3857.buffer(BUF_M)))
            if total % 100000 == 0:
                print(f"  scanned {total}, kept {len(polys)}", flush=True)
    print(f"scanned {total} outlines, {len(polys)} intersect Ward 12", flush=True)

    print("rasterizing footprint mask...", flush=True)
    mask = rasterize([(g, 1) for g in polys], out_shape=shape_px,
                     transform=transform, dtype="uint8")
    n_mask = int(mask.sum())
    print(f"mask pixels: {n_mask} / {mask.size} "
          f"({n_mask / mask.size * 100:.1f}% of raster)", flush=True)

    # NaN under the mask; keep nodata -9999 elsewhere; copy everywhere else
    valid = chm != -9999.0
    ward_valid = int(valid.sum())
    out = chm.copy()
    out[mask == 1] = np.nan
    n_nan = int(np.isnan(out).sum())
    print(f"valid ward px: {ward_valid}, NaN under mask: {n_nan} "
          f"({n_nan / ward_valid * 100:.1f}% of valid)", flush=True)

    profile.update(dtype="float32", nodata=-9999.0, compress="deflate")
    with rasterio.open(CHM_OUT, "w", **profile) as dst:
        dst.write(out, 1)
    print("wrote", CHM_OUT, flush=True)


if __name__ == "__main__":
    main()
