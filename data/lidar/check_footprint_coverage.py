"""Step 1: verify City building-footprint coverage of Ward 12.

Streams data/lidar/raw/building_outlines_4326.geojson (557,694 outlines, one
feature per line), counts how many intersect the Ward 12 polygon, and compares
bounds. Fast bbox pre-filter before the shapely intersection test.
"""
import json
import os

from shapely.geometry import shape
from shapely.prepared import prep

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GEOJSON = os.path.join(HERE, "raw", "building_outlines_4326.geojson")
WARD_GEO = os.path.join(ROOT, "ward12.geojson")

wgeo = json.load(open(WARD_GEO))["features"][0]["geometry"]
ward = shape(wgeo)
wprep = prep(ward)
wxs = [c[0] for c in ward.exterior.coords]
wys = [c[1] for c in ward.exterior.coords]
wbbox = (min(wxs), min(wys), max(wxs), max(wys))

total = 0
bbox_hits = 0
inter = 0
obx = [1e9, 1e9, -1e9, -1e9]  # overall bounds of intersecting outlines
allbx = [1e9, 1e9, -1e9, -1e9]  # overall bounds of ALL outlines (dataset extent)


def walk_coords(c):
    if isinstance(c[0], (int, float)):
        yield c[0], c[1]
    else:
        for part in c:
            yield from walk_coords(part)


def bbox_of(geom):
    xs = []
    ys = []
    for x, y in walk_coords(geom["coordinates"]):
        xs.append(x)
        ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys))


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
        if feat.get("type") != "Feature":
            continue
        geom = feat["geometry"]
        bb = bbox_of(geom)
        for i in range(4):
            allbx[i] = (min(allbx[i], bb[i]) if i < 2 else max(allbx[i], bb[i]))
        if bb[2] < wbbox[0] or bb[0] > wbbox[2] or bb[3] < wbbox[1] or bb[1] > wbbox[3]:
            continue
        bbox_hits += 1
        g = shape(geom)
        if wprep.intersects(g):
            inter += 1
            gb = g.bounds
            for i in range(4):
                obx[i] = (min(obx[i], gb[i]) if i < 2 else max(obx[i], gb[i]))

print(f"total outlines parsed: {total}")
print(f"bbox-overlap ward bbox: {bbox_hits}")
print(f"intersect Ward 12 polygon: {inter}")
print(f"ward bbox 4326: {wbbox}")
print(f"intersecting-outlines bounds: {tuple(obx)}")
print(f"whole-dataset bounds: {tuple(allbx)}")
print(f"share of dataset inside ward: {inter/total*100:.2f}%")
