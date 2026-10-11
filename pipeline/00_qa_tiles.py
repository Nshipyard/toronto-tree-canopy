#!/usr/bin/env python3
"""Export small 8cm QA tiles (same 2022 source) and grid-overlay versions for hand labeling."""
import json, math, os, sys, urllib.request, urllib.parse
from PIL import Image, ImageDraw

BASE = "https://gis.toronto.ca/arcgis/rest/services/basemap/cot_ortho_2022_color_8cm/MapServer/export"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "qa-tiles")
os.makedirs(OUT, exist_ok=True)

SPOTS = [
    ("qa1", -79.4400, 43.6780),
    ("qa2", -79.4300, 43.6720),
    ("qa3", -79.4200, 43.6820),
    ("qa4", -79.4350, 43.6900),
]
GSD = 0.08
PX = 1000  # 80 m x 80 m

def to3857(lon, lat):
    x = lon * 20037508.34 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) * 20037508.34 / math.pi
    return x, y

for name, lon, lat in SPOTS:
    cx, cy = to3857(lon, lat)
    half = PX * GSD / 2.0
    bbox = (cx - half, cy - half, cx + half, cy + half)
    path = os.path.join(OUT, f"{name}.png")
    if not os.path.exists(path):
        params = {"bbox": ",".join(f"{v:.3f}" for v in bbox),
                  "size": f"{PX},{PX}", "imageSR": "3857", "bboxSR": "3857",
                  "format": "png32", "f": "image"}
        req = urllib.request.Request(BASE + "?" + urllib.parse.urlencode(params),
                                     headers={"User-Agent": "nshipyard-tree-canopy/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r:
            data = r.read()
        assert data[:4] == b"\x89PNG", data[:120]
        open(path, "wb").write(data)
        print(f"exported {name} ({len(data)/1e6:.1f} MB)")
    else:
        print(f"exists {name}")

    # grid overlay: 10 m cells -> 125 px; label columns A..H, rows 1..8
    im = Image.open(path).convert("RGB")
    W, H = im.size
    cell = int(round(10.0 / GSD))
    dr = ImageDraw.Draw(im)
    cols = "ABCDEFGH"
    for i in range(9):
        x = i * cell
        dr.line([(x, 0), (x, H)], fill=(255, 255, 0), width=2)
        y = i * cell
        dr.line([(0, y), (W, y)], fill=(255, 255, 0), width=2)
    for i in range(8):
        dr.text((i * cell + 6, 4), cols[i], fill=(255, 255, 0))
        dr.text((4, i * cell + 4), str(i + 1), fill=(255, 255, 0))
    # scale bar: 5 m = 62.5 px
    sb = int(round(5.0 / GSD))
    dr.rectangle([10, H - 24, 10 + sb, H - 14], fill=(255, 255, 255))
    dr.text((14 + sb, H - 26), "5 m", fill=(255, 255, 255))
    im.save(os.path.join(OUT, f"{name}_grid.png"))
    meta = {"name": name, "center_lon": lon, "center_lat": lat,
            "bbox_3857": list(bbox), "gsd_m": GSD, "px": PX, "tile_m": PX * GSD,
            "grid_cell_m": 10.0, "grid_cell_px": cell}
    json.dump(meta, open(os.path.join(OUT, f"{name}.json"), "w"), indent=1)
    print(f"  grid overlay -> {name}_grid.png")
