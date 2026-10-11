#!/usr/bin/env python3
"""01_export.py — Export 2022 8cm ortho for a ward from the City MapServer.

Exports tiles at a target GSD (default 0.40 m) covering the ward polygon,
in EPSG:3857, as PNG files. Skips tiles that do not intersect the ward.
Writes data/tiles.json with per-tile metadata (bbox, size, GSD).

Usage: python3 01_export.py [WARD_GEOJSON] [--gsd 0.40] [--px 2048] [--out data/tiles]
"""
import json, os, sys, time, urllib.request, urllib.parse
import argparse

BASE = "https://gis.toronto.ca/arcgis/rest/services/basemap/cot_ortho_2022_color_8cm/MapServer/export"

def parse_4326_polygon(geojson_path):
    d = json.load(open(geojson_path))
    if d["type"] == "FeatureCollection":
        g = d["features"][0]["geometry"]
    else:
        g = d["geometry"]
    rings = g["coordinates"] if g["type"] == "Polygon" else [r for p in g["coordinates"] for r in p]
    return rings

def to3857(lon, lat):
    import math
    x = lon * 20037508.34 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) * 20037508.34 / math.pi
    return (x, y)

def point_in_poly(px, py, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]; xj, yj = ring[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside

def ring_intersects_bbox(ring, bbox):
    x0, y0, x1, y1 = bbox
    # any ring vertex inside bbox?
    for px, py in ring:
        if x0 <= px <= x1 and y0 <= py <= y1:
            return True
    # any bbox corner inside ring?
    for px, py in [(x0,y0),(x0,y1),(x1,y0),(x1,y1),((x0+x1)/2,(y0+y1)/2)]:
        if point_in_poly(px, py, ring):
            return True
    return False

def export_tile(bbox, size, path, tries=4):
    params = {
        "bbox": ",".join(f"{v:.3f}" for v in bbox),
        "size": f"{size},{size}",
        "imageSR": "3857",
        "bboxSR": "3857",
        "format": "png32",
        "f": "image",
    }
    url = BASE + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "nshipyard-tree-canopy/1.0"})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            if data[:4] != b"\x89PNG":
                raise RuntimeError(f"non-PNG response: {data[:120]!r}")
            open(path, "wb").write(data)
            return len(data)
        except Exception as e:
            last = e
            print(f"    attempt {attempt+1} failed: {type(e).__name__}; retrying", flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"export failed after {tries} tries: {last}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ward_geojson", default="data/ward12.geojson", nargs="?")
    ap.add_argument("--gsd", type=float, default=0.40)
    ap.add_argument("--px", type=int, default=2048)
    ap.add_argument("--out", default="data/tiles")
    ap.add_argument("--vintage", default="2022")
    args = ap.parse_args()

    rings4326 = parse_4326_polygon(args.ward_geojson)
    rings = [[to3857(lon, lat) for lon, lat in ring] for ring in rings4326]
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    tile_m = args.px * args.gsd
    os.makedirs(args.out, exist_ok=True)

    tiles = []
    nx = int((x1 - x0) // tile_m) + 1
    ny = int((y1 - y0) // tile_m) + 1
    print(f"ward bbox 3857: {x0:.0f},{y0:.0f} -> {x1:.0f},{y1:.0f} ; grid {nx}x{ny}")
    kept = 0
    for i in range(nx):
        for j in range(ny):
            tx0 = x0 + i * tile_m; ty0 = y0 + j * tile_m
            bbox = (tx0, ty0, tx0 + tile_m, ty0 + tile_m)
            if not any(ring_intersects_bbox(r, bbox) for r in rings):
                continue
            name = f"tile_{i:02d}_{j:02d}"
            path = os.path.join(args.out, name + ".png")
            if os.path.exists(path) and os.path.getsize(path) > 10000:
                print(f"  skip {name} (exists)")
            else:
                t0 = time.time()
                nbytes = export_tile(bbox, args.px, path)
                dt = time.time() - t0
                print(f"  {name}: {nbytes/1e6:.1f} MB in {dt:.1f}s", flush=True)
                time.sleep(0.5)
            tiles.append({"name": name, "path": path, "bbox_3857": bbox,
                          "size_px": args.px, "gsd_m": args.gsd,
                          "vintage": args.vintage})
            kept += 1
    meta_path = os.path.join(os.path.dirname(args.out), "tiles.json")
    json.dump({"tiles": tiles, "ward_bbox_3857": [x0, y0, x1, y1],
               "gsd_m": args.gsd, "px": args.px, "vintage": args.vintage}, open(meta_path, "w"), indent=1)
    print(f"kept {kept} tiles -> {meta_path}")

if __name__ == "__main__":
    main()
