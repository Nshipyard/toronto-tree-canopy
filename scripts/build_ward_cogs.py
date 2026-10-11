"""Merge per-tile uint16 masked-CHM COGs into per-ward COGs for the map endpoint.

Reads data/cogs_tile/tile_*.tif (written by data/lidar/compute_tile.py) and,
per ward, merges the tiles whose core bbox intersects the ward bbox (+50 m),
crops to the ward bbox + 50 m, and writes data/cogs/ward_<NN>_chm.tif
(tiled, deflate, uint16 decimetres, 65535 = nodata).

Every output must stay under jsDelivr's 20 MB per-file limit; the script
asserts that and reports sizes.

Run: .venv/bin/python3 scripts/build_ward_cogs.py
"""
import json
import math
import os

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.windows import from_bounds, transform as window_transform
from affine import Affine

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
TILE_COGS = os.path.join(DATA, "cogs_tile")
OUT = os.path.join(DATA, "cogs")
MARGIN_M = 50.0
LIMIT_MB = 20.0


def main():
    os.makedirs(OUT, exist_ok=True)
    plan = json.load(open(os.path.join(DATA, "ward_plan.json")))["wards"]
    tplan = json.load(open(os.path.join(DATA, "tile_plan.json")))["tiles"]
    # tile core bboxes for intersection tests
    tcores = [(t["tile"], t["core_bbox_4326"]) for t in tplan]
    for code in sorted(plan):
        lon0, lat0, lon1, lat1 = plan[code]["bbox_4326"]
        lat_c = (lat0 + lat1) / 2
        dlat = MARGIN_M / 111320.0
        dlon = MARGIN_M / (111320.0 * math.cos(math.radians(lat_c)))
        eb = (lon0 - dlon, lat0 - dlat, lon1 + dlon, lat1 + dlat)
        tiles = [t for t, b in tcores
                 if not (b[2] < eb[0] or b[0] > eb[2] or b[3] < eb[1] or b[1] > eb[3])]
        files = [os.path.join(TILE_COGS, f"tile_{t}.tif") for t in tiles]
        missing = [f for f in files if not os.path.exists(f)]
        assert not missing, f"ward {code}: missing tile COGs {missing}"
        srcs = [rasterio.open(f) for f in files]
        arr, tr = merge(srcs, nodata=65535)
        for s in srcs:
            s.close()
        win = from_bounds(*eb, tr).round_offsets().round_lengths()
        assert win.col_off >= 0 and win.row_off >= 0, f"ward {code}: {win}"
        sub = arr[0][int(win.row_off):int(win.row_off + win.height),
                     int(win.col_off):int(win.col_off + win.width)]
        # Downsample 2x to ~2 m for the visual parcel-map COGs (keeps every
        # ward under jsDelivr's 20 MB/file limit; 2 m is plenty for a PNG).
        sub = sub[::2, ::2]
        out_tr = Affine(window_transform(win, tr).a * 2, 0.0,
                        window_transform(win, tr).c, 0.0,
                        window_transform(win, tr).e * 2,
                        window_transform(win, tr).f)
        fn = os.path.join(OUT, f"ward_{code}_chm.tif")
        profile = {
            "driver": "GTiff", "dtype": "uint16", "nodata": 65535,
            "width": sub.shape[1], "height": sub.shape[0], "count": 1,
            "crs": "EPSG:4326", "transform": out_tr,
            "tiled": True, "blockxsize": 256, "blockysize": 256,
            "compress": "zstd", "predictor": 2,
        }
        with rasterio.open(fn, "w", **profile) as dst:
            dst.write(sub, 1)
        mb = os.path.getsize(fn) / 1e6
        status = "OK" if mb < LIMIT_MB else "OVER LIMIT"
        print(f"ward {code}: {len(tiles)} tiles -> {fn} ({mb:.1f} MB) {status}",
              flush=True)
        assert mb < LIMIT_MB, f"ward {code} COG {mb:.1f} MB exceeds jsDelivr limit"
    print("all ward COGs under 20 MB", flush=True)


if __name__ == "__main__":
    main()
