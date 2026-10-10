#!/usr/bin/env python3
"""render_parcel_maps.py — Render per-parcel tall-canopy maps (Track B).

For each Ward 12 parcel: crop a base image to the parcel bbox + 6 m buffer
(EPSG:3857), tint the tall-canopy pixels (2023 LiDAR CHM >= 8 m) green, then draw:

  - tall canopy (>= 8 m): GREEN translucent tint, from the 1 m CHM
  - parcel boundary: solid dark line (white underlay)
  - 6 m neighbour buffer: dashed gray rectangle (the image edge)
  - a 10 m scale bar and a caption band naming the sources

Base image: the 2022 ortho tile composite when the parcel's bbox is fully
covered by data/tiles (round-1 export); otherwise a grayscale rendering of the
2023 LiDAR surface itself (always available ward-wide). The caption names which.

Input: data/parcel_canopy_ward12.json (rings + metrics).
Output: public/parcels/<parcel-id>.png, long edge ~1080 px.

Usage:
  python3 render_parcel_maps.py --only TOP-5293472
  python3 render_parcel_maps.py --limit 20            # first 20 parcels
  python3 render_parcel_maps.py --base chm            # force LiDAR base
  python3 render_parcel_maps.py                       # all 27,104 parcels (slow)
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CANOPY = os.path.join(ROOT, "data", "parcel_canopy_ward12.json")
CHM_PATH = os.path.join(ROOT, "data", "lidar", "wcs", "ward12_chm_full.tif")

GSD = 0.40            # metres per pixel of the exported ortho tiles
TILE_PX = 2048
TILE_M = TILE_PX * GSD          # 819.2 m
BUFFER_M = 6.0                  # neighbour buffer required by the by-law site plan
LONG_EDGE = 1080                # target web size (long edge, px)
NATIVE_MIN_PX = 96
TALL_M = 8.0                    # tall-canopy tint threshold (m)

GREEN = (46, 125, 50)
DARK = (10, 15, 30)
GRAY = (138, 143, 160)
WHITE = (255, 255, 255)
SCALE_BAR_M = 10


def to3857(lon, lat):
    x = lon * 20037508.34 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) * 20037508.34 / math.pi
    return (x, y)


def grid_origin():
    d = json.load(open(os.path.join(ROOT, "data", "ward12.geojson")))
    g = d["features"][0]["geometry"] if d["type"] == "FeatureCollection" else d["geometry"]
    rings = g["coordinates"] if g["type"] == "Polygon" else [r for p in g["coordinates"] for r in p]
    xs = [to3857(lon, lat)[0] for r in rings for lon, lat in r]
    ys = [to3857(lon, lat)[1] for r in rings for lon, lat in r]
    return (min(xs), min(ys))


def tile_path(i, j):
    return os.path.join(ROOT, "data", "tiles", f"tile_{i:02d}_{j:02d}.png")


def ortho_mosaic(bbox):
    """Paste the 2022 ortho tiles covering bbox (3857); raise FileNotFoundError
    when any needed tile is missing (caller falls back to the LiDAR base)."""
    x0, y0, x1, y1 = bbox
    gx0, gy0 = grid_origin()
    i0 = int(math.floor((x0 - gx0) / TILE_M)); i1 = int(math.floor((x1 - gx0) / TILE_M))
    j0 = int(math.floor((y0 - gy0) / TILE_M)); j1 = int(math.floor((y1 - gy0) / TILE_M))
    w = (i1 - i0 + 1) * TILE_PX; h = (j1 - j0 + 1) * TILE_PX
    base = Image.new("RGB", (w, h), (0, 0, 0))
    for i in range(i0, i1 + 1):
        for j in range(j0, j1 + 1):
            p = tile_path(i, j)
            if not os.path.exists(p):
                raise FileNotFoundError(f"tile_{i:02d}_{j:02d}.png")
            t = Image.open(p).convert("RGB")
            base.paste(t, ((i - i0) * TILE_PX, (j - j0) * TILE_PX))
    ox = gx0 + i0 * TILE_M
    oy1 = gy0 + (j1 + 1) * TILE_M
    px0 = int(round((x0 - ox) / GSD)); px1 = int(round((x1 - ox) / GSD))
    py0 = int(round((oy1 - y1) / GSD)); py1 = int(round((oy1 - y0) / GSD))
    return base.crop((px0, py0, px1, py1)), "Imagery: City of Toronto 2022 orthophoto · Canopy: 2023 LiDAR"


def bbox_to4326(bbox):
    """(minx, miny, maxx, maxy) in EPSG:3857 -> EPSG:4326."""
    lon0, lat0 = merc_inv(bbox[0], bbox[1])
    lon1, lat1 = merc_inv(bbox[2], bbox[3])
    return (lon0, lat0, lon1, lat1)


def merc_inv(x, y):
    lon = x / 20037508.34 * 180.0
    lat = (2.0 * math.atan(math.exp(y / 20037508.34 * math.pi)) - math.pi / 2.0) * 180.0 / math.pi
    return (lon, lat)


def chm_base(bbox, chm_src):
    """Grayscale rendering of the 2023 LiDAR surface for bbox (3857)."""
    from rasterio.windows import from_bounds
    b = bbox_to4326(bbox)
    win = from_bounds(b[0], b[1], b[2], b[3], chm_src.transform)
    arr = chm_src.read(1, window=win)
    v = np.where(arr == -9999.0, 0.0, arr).astype("float32")
    gray = (235.0 - np.clip(v, 0, 30) / 30.0 * 165.0).astype("uint8")
    img = Image.fromarray(np.stack([gray, gray, gray], axis=-1), "RGB")
    return img, "Base: 2023 LiDAR surface (no orthophoto tile here) · Canopy: 2023 LiDAR"


def canopy_overlay(bbox, chm_src, size):
    """RGBA green tint where CHM >= 8 m, resized to `size` with NEAREST."""
    from rasterio.windows import from_bounds
    b = bbox_to4326(bbox)
    win = from_bounds(b[0], b[1], b[2], b[3], chm_src.transform)
    arr = chm_src.read(1, window=win)
    mask = (arr >= TALL_M)
    tint = np.zeros((arr.shape[0], arr.shape[1], 4), dtype="uint8")
    tint[mask] = (46, 125, 50, 115)
    img = Image.fromarray(tint, "RGBA").resize(size, Image.NEAREST)
    return img


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


_measure_draw = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def fit_font(text, max_w, start, bold=False):
    size = start
    while size > 9:
        f = font(size, bold)
        if _measure_draw.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return font(9, bold)


def poly_frac(ring_4326, bbox):
    x0, y0, x1, y1 = bbox
    w_m, h_m = x1 - x0, y1 - y0
    pts = [to3857(lon, lat) for lon, lat in ring_4326]
    return [((x - x0) / w_m, (y1 - y) / h_m) for x, y in pts]


def dashed_line(draw, pts, fill, width, dash_m, m_per_px):
    dash_px = max(6, int(round(dash_m / m_per_px)))
    gap_px = max(4, int(round(dash_m * 0.75 / m_per_px)))
    for a, b in zip(pts, pts[1:] + pts[:1]):
        ax, ay = a; bx, by = b
        length = math.hypot(bx - ax, by - ay)
        if length < 1:
            continue
        ux, uy = (bx - ax) / length, (by - ay) / length
        d = 0.0
        while d < length:
            e = min(d + dash_px, length)
            draw.line([(ax + ux * d, ay + uy * d), (ax + ux * e, ay + uy * e)],
                      fill=fill, width=width)
            d += dash_px + gap_px


def text_with_halo(draw, xy, text, fnt, fill, anchor="la"):
    x, y = xy
    for dx in (-2, 0, 2):
        for dy in (-2, 0, 2):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=fnt, fill=(0, 0, 0, 255), anchor=anchor)
    draw.text((x, y), text, font=fnt, fill=fill, anchor=anchor)


def render(parcel_id, ring_4326, base_mode, out_path, chm_src):
    pts3857 = [to3857(lon, lat) for lon, lat in ring_4326]
    xs = [p[0] for p in pts3857]; ys = [p[1] for p in pts3857]
    bbox = (min(xs) - BUFFER_M, min(ys) - BUFFER_M, max(xs) + BUFFER_M, max(ys) + BUFFER_M)

    base = None
    caption = ""
    if base_mode in ("auto", "ortho"):
        try:
            base, caption = ortho_mosaic(bbox)
        except FileNotFoundError:
            if base_mode == "ortho":
                raise
    if base is None:
        base, caption = chm_base(bbox, chm_src)

    cw, ch = base.size
    upscale = max(LONG_EDGE / max(cw, ch), NATIVE_MIN_PX / max(cw, ch))
    w, h = int(round(cw * upscale)), int(round(ch * upscale))
    if (w, h) != base.size:
        base = base.resize((w, h), Image.LANCZOS)
    img = base.convert("RGBA")

    # Tall-canopy tint from the CHM.
    tint = canopy_overlay(bbox, chm_src, (w, h))
    img = Image.alpha_composite(img, tint)
    draw = ImageDraw.Draw(img, "RGBA")
    m_per_px = (bbox[2] - bbox[0]) / w

    def to_final(frac_pts):
        return [(fx * w, fy * h) for fx, fy in frac_pts]

    # 6 m buffer = the image edge, dashed.
    buf_pts = [(4, 4), (w - 4, 4), (w - 4, h - 4), (4, h - 4)]
    dashed_line(draw, buf_pts, WHITE + (255,), 7, 4.0, m_per_px)
    dashed_line(draw, buf_pts, GRAY + (255,), 3, 4.0, m_per_px)

    # Parcel boundary: solid dark line with white underlay.
    parcel_pts = to_final(poly_frac(ring_4326, bbox))
    draw.line(parcel_pts + parcel_pts[:1], fill=WHITE + (255,), width=9, joint="curve")
    draw.line(parcel_pts + parcel_pts[:1], fill=DARK + (255,), width=4, joint="curve")

    # Scale bar (10 m) + caption band.
    bar_px = SCALE_BAR_M / m_per_px
    band_h = 44
    draw.rectangle([0, h - band_h, w, h], fill=(0, 0, 0, 160))
    sb_y = h - band_h - 26
    sb_x = 24
    fnt = font(26, bold=True)
    draw.line([(sb_x, sb_y), (sb_x + bar_px, sb_y)], fill=WHITE, width=7)
    draw.line([(sb_x, sb_y - 7), (sb_x, sb_y + 7)], fill=WHITE, width=7)
    draw.line([(sb_x + bar_px, sb_y - 7), (sb_x + bar_px, sb_y + 7)], fill=WHITE, width=7)
    text_with_halo(draw, (sb_x + bar_px / 2, sb_y - 34), f"{SCALE_BAR_M} m", fnt, WHITE, anchor="ma")

    fnt_cap = fit_font(caption, w - 40, 24)
    tw = draw.textlength(caption, font=fnt_cap)
    text_with_halo(draw, (w - 20 - tw, h - band_h + 8), caption, fnt_cap, WHITE)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path, "PNG", optimize=True)
    return (w, h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="comma-separated parcel ids")
    ap.add_argument("--limit", type=int, default=None, help="render first N parcels")
    ap.add_argument("--base", default="auto", choices=["auto", "ortho", "chm"])
    ap.add_argument("--out", default=os.path.join(ROOT, "public", "parcels"))
    args = ap.parse_args()

    canopy = json.load(open(CANOPY))
    ids = list(canopy.keys())
    if args.only:
        ids = [i for i in args.only.split(",") if i in canopy]
    if args.limit:
        ids = ids[:args.limit]
    print(f"{len(ids)} parcels; base={args.base}", flush=True)

    chm_src = rasterio.open(CHM_PATH)
    for pid in ids:
        ring = canopy[pid]["ring_4326"]
        out = os.path.join(args.out, f"{pid}.png")
        w, h = render(pid, ring, args.base, out, chm_src)
        print(f"  {pid}: {w}x{h} -> {out}", flush=True)
    chm_src.close()


if __name__ == "__main__":
    main()
