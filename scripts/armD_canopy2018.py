#!/usr/bin/env python3
"""Arm D final computation: tree polygon intersection per QA tile + label fractions."""
import json, math, time
import pyogrio
from shapely.geometry import box
from pyproj import Transformer

DATA = "/home/hatch/workspace/toronto-tree-canopy/data"
TILES = ["qa1", "qa3", "qa7"]
AREA = 80.0 * 80.0

t0 = time.time()
tree = pyogrio.read_dataframe(f"{DATA}/canopy2018/LandCover2018.gdb",
                              layer="LandCover2018", where="gridcode = 1")
print(f"read {len(tree)} tree polygons in {time.time()-t0:.1f}s", flush=True)
tree = tree.set_crs("EPSG:2952")

xfer = Transformer.from_crs("EPSG:3857", "EPSG:2952", always_xy=True)
per_tile, rf_list, lf_list = {}, [], []
for t in TILES:
    qt = json.load(open(f"{DATA}/qa-tiles/{t}.json"))
    lab = json.load(open(f"{DATA}/labels/{t}.json"))
    xmin, ymin, xmax, ymax = qt["bbox_3857"]
    x0, y0 = xfer.transform(xmin, ymin)
    x1, y1 = xfer.transform(xmax, ymax)
    tp = box(x0, y0, x1, y1)
    sel = tree[tree.intersects(tp)]
    valid = sel.geometry.apply(lambda g: g if g.is_valid else __import__("shapely").make_valid(g))
    ta = valid.intersection(tp).area.sum()
    rf = ta / AREA
    lf = sum(math.pi * (l["d_m"] / 2.0) ** 2 for l in lab["labels"]) / AREA
    per_tile[t] = {"raster_frac": round(rf, 4), "label_frac": round(lf, 4),
                   "tree_area_m2": round(ta, 1), "n_labels": len(lab["labels"]),
                   "n_tree_polys_touching": int(len(sel))}
    rf_list.append(rf); lf_list.append(lf)
    print(t, per_tile[t], flush=True)

mae = sum(abs(r - l) for r, l in zip(rf_list, lf_list)) / 3
mr = sum(rf_list) / 3; ml = sum(lf_list) / 3
cov = sum((r - mr) * (l - ml) for r, l in zip(rf_list, lf_list))
vr = sum((r - mr) ** 2 for r in rf_list); vl = sum((l - ml) ** 2 for l in lf_list)
corr = cov / math.sqrt(vr * vl)

out = {
    "arm": "D-canopy2018",
    "per_tile": {t: {"raster_frac": per_tile[t]["raster_frac"],
                     "label_frac": per_tile[t]["label_frac"]} for t in TILES},
    "mae": round(mae, 4),
    "correlation": round(corr, 4),
    "n_tiles": 3,
    "raster_resolution_m": None,
    "vintage_observed": ("2018 (vector LandCover2018 polygons from automated "
                         "classification of multispectral satellite imagery + LiDAR; "
                         "exact capture month/day and satellite unnamed in "
                         "2018-land-cover-documentation.docx)"),
    "limitations": [
        "The 2018 geodatabase contains no raster; Arm D ran on vector land-cover polygons (1812 multipolygons, EPSG:2952) produced by NDVI segmentation of satellite imagery, so 'raster_frac' is a polygon-intersection fraction, not a pixel fraction.",
        "Classes: 1=tree, 2=grass, 3=bare, 4=water, 5=building, 6=road, 7=other, 8=shrub, 0=(empty, 55 features); agriculture removed per methodology.",
        "Label fraction sums circular crown areas (pi*(d/2)^2); overlapping crowns double-count, inflating label_frac.",
        "Labels were made on 2022 leaf-off orthophotos; the 2018 data predates them by ~4 years, so growth/removal/disease between 2018 and 2022 contributes mismatch.",
        "n=3 tiles: Pearson correlation is indicative only.",
        "Class polygons are large image segments (organizePolygons had to be skipped); sub-canopy texture (gaps between crowns) inside a 'tree' polygon is not resolved, biasing the 2018 fraction upward where crowns are sparse.",
    ],
}
json.dump(out, open(f"{DATA}/accuracy_armD_canopy2018.json", "w"), indent=2)
print(json.dumps(out, indent=2))
