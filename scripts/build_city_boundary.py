"""Build data/city_boundary.json: simplified Toronto boundary for honest 404s.

Unions the 25 ward polygons (data/wards_dump.geojson), simplifies at 50 m,
then buffers OUTWARD by 100 m so the simplified ring can never cut inside the
true city edge (a false outside-Toronto 404 would be worse than a ~100 m
tolerance band where an outside point tests inside and then 404s as
"no canopy data"). Stores every exterior ring (the Islands can split the
union into a MultiPolygon).

Output: data/city_boundary.json { rings_4326: [ [[lon,lat],...], ... ], ... }
~10 KB. Bundled with the serverless function.

Run: .venv/bin/python3 scripts/build_city_boundary.py
"""
import csv
import json
import os

from shapely.geometry import shape
from shapely.ops import transform as shp_transform, unary_union
from pyproj import Transformer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "city_boundary.json")

csv.field_size_limit(10 ** 9)


def main():
    polys = []
    with open(os.path.join(DATA, "wards_dump.geojson"), newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            polys.append(shape(json.loads(row["geometry"])))
    print(f"{len(polys)} ward polygons", flush=True)
    union = unary_union(polys)
    print(f"union type: {union.geom_type}, area {union.area:.4f} deg^2", flush=True)

    fwd = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    back = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    u3857 = shp_transform(lambda x, y: fwd.transform(x, y), union)
    simp = u3857.simplify(50.0, preserve_topology=True)
    buf = simp.buffer(100.0)  # outward tolerance band; never cuts inside
    u4326 = shp_transform(lambda x, y: back.transform(x, y), buf)

    geoms = u4326.geoms if u4326.geom_type == "MultiPolygon" else [u4326]
    rings = []
    for g in geoms:
        ring = [[round(x, 5), round(y, 5)] for x, y in g.exterior.coords]
        rings.append(ring)
    doc = {
        "rings_4326": rings,
        "simplify_m": 50,
        "outward_buffer_m": 100,
        "source": "union of 25 ward polygons (data/wards_dump.geojson)",
        "note": "Coverage gate for honest 404s. 2023 LiDAR mosaic covers 100% of Toronto (316/316 WCS probes); inside this ring a miss means no parcel, not no coverage.",
    }
    json.dump(doc, open(OUT, "w"))
    size = os.path.getsize(OUT)
    total_pts = sum(len(r) for r in rings)
    print(f"wrote {OUT} ({size / 1024:.1f} KB, {len(rings)} rings, {total_pts} pts)",
          flush=True)


if __name__ == "__main__":
    main()
