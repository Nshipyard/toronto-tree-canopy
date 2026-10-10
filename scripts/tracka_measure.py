#!/usr/bin/env python3
"""Track A step 2: measure raw point density + classification of GTA_2023 COPC tiles.

Usage: tracka_measure.py raw/qa1_tile.copc.laz raw/qa37_tile.copc.laz
Writes: data/tracka_density.json
"""
import json, os, sys
import numpy as np

import laspy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "data", "tracka_density.json")

CLASS_NAMES = {0: "never classified", 1: "unassigned", 2: "ground", 3: "low veg",
               4: "medium veg", 5: "high veg", 6: "building", 7: "low point",
               8: "model key", 9: "water", 17: "bridge deck", 18: "high noise"}


def measure(path):
    print(f"--- {path} ---", flush=True)
    las = laspy.read(path)
    n = len(las.points)
    x = np.asarray(las.x); y = np.asarray(las.y)
    # 1 km tiles; use 5-95 percentile span to estimate effective covered area
    x0, x1 = np.percentile(x, 0.5), np.percentile(x, 99.5)
    y0, y1 = np.percentile(y, 0.5), np.percentile(y, 99.5)
    area = max((x1 - x0) * (y1 - y0), 1.0)
    density = n / area
    classes = np.asarray(las.classification)
    uniq, counts = np.unique(classes, return_counts=True)
    class_hist = {f"{int(u)} ({CLASS_NAMES.get(int(u), '?')})": int(c)
                  for u, c in zip(uniq, counts)}
    # return stats: single-photon lidars usually have 1 return only
    ret = np.asarray(las.return_num)
    nret = np.asarray(las.num_returns)
    res = {
        "file": os.path.basename(path),
        "n_points": int(n),
        "area_m2_percentile": round(area, 1),
        "density_pts_per_m2": round(density, 2),
        "bbox_utm17": [float(x.min()), float(y.min()), float(x.max()), float(y.max())],
        "class_histogram": class_hist,
        "fraction_single_return": round(float(np.mean(nret == 1)), 4),
        "z_range": [round(float(np.asarray(las.z).min()), 2),
                    round(float(np.asarray(las.z).max()), 2)],
        "point_format": int(las.header.point_format.id),
    }
    print(json.dumps(res, indent=1), flush=True)
    return res


if __name__ == "__main__":
    out = {"files": [measure(p) for p in sys.argv[1:]]}
    json.dump(out, open(OUT, "w"), indent=1)
    print("wrote", OUT)
