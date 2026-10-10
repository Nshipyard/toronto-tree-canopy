#!/usr/bin/env python3
"""render_parcel_maps.py — Render presentation-grade per-parcel crown maps.

For each parcel: compute parcel bbox + 6 m buffer in EPSG:3857, mosaic/crop
the 2022 ortho tiles (0.40 m GSD, 2048 px, tile_m = 819.2 m, grid origin from
data/ward12.geojson) to that bbox, then draw:

  - detected crown polygons: RED outline when p_ge_30cm >= 0.5,
    GREEN outline otherwise (outlines only, no fill)
  - parcel boundary: solid dark line
  - 6 m neighbour buffer: dashed gray line
  - a 10 m scale bar and the caption "Imagery: City of Toronto 2022 orthophoto"

Parcels flagged synthetic ("_sample") render as the bare ortho crop with the
overlaid text "Crown detection pending. Ward 12 pilot in progress." — no
crowns are ever drawn for them. Genuine parcels with an empty crown list
render the bare crop with boundary overlays only.

Output: public/parcels/<parcel-id>.png, long edge ~1080 px.

Usage:
  python3 render_parcel_maps.py                      # all parcels in the active dataset
  python3 render_parcel_maps.py --geojson data/sample-parcels.geojson --only TOP-W12-0101
  python3 render_parcel_maps.py --out public/parcels
"""
import argparse
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

GSD = 0.40            # metres per pixel of the exported ortho tiles
TILE_PX = 2048
TILE_M = TILE_PX * GSD          # 819.2 m
BUFFER_M = 6.0                  # neighbour buffer required by the by-law site plan
LONG_EDGE = 1080                # target web size (long edge, px)
NATIVE_MIN_PX = 96              # never render a crop below this native size before upscaling

RED = (214, 6, 33)
GREEN = (46, 125, 50)
DARK = (10, 15, 30)
GRAY = (138, 143, 160)
WHITE = (255, 255, 255)

PENDING_LINE1 = "Crown detection pending."
PENDING_LINE2 = "Ward 12 pilot in progress."
CAPTION = "Imagery: City of Toronto 2022 orthophoto"
SCALE_BAR_M = 10


def to3857(lon, lat):
    x = lon * 20037508.34 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) * 20037508.34 / math.pi
    return (x, y)


def grid_origin():
    """Minimum of data/ward12.geojson in EPSG:3857 (the tile grid origin)."""
    d = json.load(open(os.path.join(ROOT, "data", "ward12.geojson")))
    g = d["features"][0]["geometry"] if d["type"] == "FeatureCollection" else d["geometry"]
    rings = g["coordinates"] if g["type"] == "Polygon" else [r for p in g["coordinates"] for r in p]
    xs = [to3857(lon, lat)[0] for r in rings for lon, lat in r]
    ys = [to3857(lon, lat)[1] for r in rings for lon, lat in r]
    return (min(xs), min(ys))


def tile_path(i, j):
    return os.path.join(ROOT, "data", "tiles", f"tile_{i:02d}_{j:02d}.png")


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


_measure_draw = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def fit_font(text, max_w, start, bold=False):
    """Largest font size (<= start) whose rendered width fits max_w."""
    size = start
    while size > 9:
        f = font(size, bold)
        if _measure_draw.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return font(9, bold)


def mosaic(bbox):
    """Paste the tiles covering bbox (3857) into one image; return (img, origin)."""
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
                raise FileNotFoundError(
                    f"missing tile tile_{i:02d}_{j:02d}.png; run the tile export for this bbox first")
            t = Image.open(p).convert("RGB")
            base.paste(t, ((i - i0) * TILE_PX, (j - j0) * TILE_PX))
    # Crop: tile rows grow northward (+y), image rows grow downward.
    ox = gx0 + i0 * TILE_M
    oy1 = gy0 + (j1 + 1) * TILE_M  # top edge in 3857
    px0 = int(round((x0 - ox) / GSD)); px1 = int(round((x1 - ox) / GSD))
    py0 = int(round((oy1 - y1) / GSD)); py1 = int(round((oy1 - y0) / GSD))
    return base.crop((px0, py0, px1, py1))


def poly_px(poly_4326, bbox):
    """Convert a [[lon,lat],...] ring to pixel coords of the cropped image."""
    x0, y0, x1, y1 = bbox
    w_m, h_m = x1 - x0, y1 - y0
    pts = [to3857(lon, lat) for lon, lat in poly_4326]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return [((x - x0) / w_m, (y1 - y) / h_m) for x, y in zip(xs, ys)]  # (0..1, 0..1)


def dashed_line(draw, pts, fill, width, dash_m, m_per_px):
    """Draw a polyline as dashes, dash length in metres."""
    dash_px = max(6, int(round(dash_m / m_per_px)))
    gap_px = max(4, int(round(dash_m * 0.75 / m_per_px)))
    segs = []
    for a, b in zip(pts, pts[1:] + pts[:1]):
        ax, ay = a; bx, by = b
        length = math.hypot(bx - ax, by - ay)
        if length < 1:
            continue
        ux, uy = (bx - ax) / length, (by - ay) / length
        d = 0.0
        while d < length:
            e = min(d + dash_px, length)
            segs.append(((ax + ux * d, ay + uy * d), (ax + ux * e, ay + uy * e)))
            d += dash_px + gap_px
    for (p, q) in segs:
        draw.line([p, q], fill=fill, width=width)


def text_with_halo(draw, xy, text, fnt, fill, anchor="la"):
    x, y = xy
    for dx in (-2, 0, 2):
        for dy in (-2, 0, 2):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=fnt, fill=(0, 0, 0, 255), anchor=anchor)
    draw.text((x, y), text, font=fnt, fill=fill, anchor=anchor)


def render(parcel, pending, out_path):
    geom = parcel["geometry"]
    pts3857 = [to3857(lon, lat) for lon, lat in geom]
    xs = [p[0] for p in pts3857]; ys = [p[1] for p in pts3857]
    bbox = (min(xs) - BUFFER_M, min(ys) - BUFFER_M, max(xs) + BUFFER_M, max(ys) + BUFFER_M)

    crop = mosaic(bbox)
    cw, ch = crop.size
    upscale = max(LONG_EDGE / max(cw, ch), NATIVE_MIN_PX / max(cw, ch))
    w, h = int(round(cw * upscale)), int(round(ch * upscale))
    if (w, h) != crop.size:
        crop = crop.resize((w, h), Image.LANCZOS)
    img = crop.convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    m_per_px = (bbox[2] - bbox[0]) / w

    def to_final(frac_pts):
        return [(fx * w, fy * h) for fx, fy in frac_pts]

    # 6 m buffer = the bbox itself, drawn as a dashed rectangle.
    buf_pts = [(4, 4), (w - 4, 4), (w - 4, h - 4), (4, h - 4)]
    dashed_line(draw, buf_pts, WHITE + (255,), 7, 4.0, m_per_px)
    dashed_line(draw, buf_pts, GRAY + (255,), 3, 4.0, m_per_px)

    # Parcel boundary: solid dark line with a white underlay for legibility.
    parcel_pts = to_final(poly_px(geom, bbox))
    draw.line(parcel_pts + parcel_pts[:1], fill=WHITE + (255,), width=9, joint="curve")
    draw.line(parcel_pts + parcel_pts[:1], fill=DARK + (255,), width=4, joint="curve")

    # Crown outlines (never for pending parcels).
    crowns = [] if pending else parcel.get("crowns", [])
    for c in crowns:
        mature = c["p_ge_30cm"] >= 0.5
        col = RED if mature else GREEN
        cpts = to_final(poly_px(c["polygon"], bbox))
        draw.line(cpts + cpts[:1], fill=WHITE + (255,), width=8, joint="curve")
        draw.line(cpts + cpts[:1], fill=col + (255,), width=4, joint="curve")

    # Scale bar (10 m), bottom-left above the caption band.
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

    # Caption, bottom-right in the band (shrunk to fit narrow parcels).
    fnt_cap = fit_font(CAPTION, w - 40, 24)
    tw = draw.textlength(CAPTION, font=fnt_cap)
    text_with_halo(draw, (w - 20 - tw, h - band_h + 8), CAPTION, fnt_cap, WHITE)

    if pending:
        # Centered pending panel: no crowns drawn, no fake data.
        fnt1 = fit_font(PENDING_LINE1, w - 64, 44, bold=True)
        fnt2 = fit_font(PENDING_LINE2, w - 64, 32)
        w1 = draw.textlength(PENDING_LINE1, font=fnt1)
        w2 = draw.textlength(PENDING_LINE2, font=fnt2)
        pw, ph = max(w1, w2) + 72, fnt1.size + fnt2.size + 64
        px0, py0 = (w - pw) / 2, (h - ph) / 2 - 20
        draw.rectangle([px0, py0, px0 + pw, py0 + ph], fill=(0, 0, 0, 170))
        draw.rectangle([px0, py0, px0 + pw, py0 + ph], outline=WHITE, width=3)
        draw.text((w / 2, py0 + 12 + fnt1.size / 2), PENDING_LINE1, font=fnt1, fill=WHITE, anchor="mm")
        draw.text((w / 2, py0 + 24 + fnt1.size + fnt2.size / 2), PENDING_LINE2, font=fnt2, fill=WHITE, anchor="mm")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path, "PNG", optimize=True)
    return (w, h)


def load_parcels(path):
    doc = json.load(open(path))
    top_sample = bool(doc.get("_sample"))
    feats = doc.get("features", [])
    parcels = []
    for f in feats:
        props = f.get("properties", {}) or {}
        geom = f.get("geometry", {}) or {}
        coords = geom.get("coordinates") or []
        ring = coords[0] if geom.get("type") == "Polygon" else (coords[0][0] if coords else [])
        crowns = []
        for c in props.get("crowns", []) or []:
            crowns.append({
                "polygon": c["polygon"],
                "p_ge_30cm": c.get("p_ge_30cm", 0.0),
                "p_gt_61cm": c.get("p_gt_61cm", 0.0),
            })
        parcels.append({
            "parcel_id": props.get("parcel_id"),
            "geometry": ring,
            "crowns": crowns,
            "pending": top_sample or bool(props.get("_sample")),
        })
    return parcels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", default=None,
                    help="parcel GeoJSON (default: parcels-ward12 if present, else sample)")
    ap.add_argument("--only", default=None, help="comma-separated parcel ids to render")
    ap.add_argument("--out", default=os.path.join(ROOT, "public", "parcels"))
    args = ap.parse_args()

    if args.geojson:
        gpath = args.geojson if os.path.isabs(args.geojson) else os.path.join(ROOT, args.geojson)
    else:
        pilot = os.path.join(ROOT, "data", "parcels-ward12.geojson")
        gpath = pilot if os.path.exists(pilot) else os.path.join(ROOT, "data", "sample-parcels.geojson")
    only = set(args.only.split(",")) if args.only else None

    parcels = load_parcels(gpath)
    print(f"grid origin from data/ward12.geojson; GSD {GSD} m; {len(parcels)} parcels in {gpath}")
    for p in parcels:
        if only and p["parcel_id"] not in only:
            continue
        out = os.path.join(args.out, f'{p["parcel_id"]}.png')
        w, h = render(p, p["pending"], out)
        mode = "pending" if p["pending"] else f"{len(p['crowns'])} crowns"
        print(f"  {p['parcel_id']}: {w}x{h} ({mode}) -> {out}")


if __name__ == "__main__":
    main()
