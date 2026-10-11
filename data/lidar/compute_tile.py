#!/usr/bin/env python3
"""compute_tile.py -- one tile of the city-wide masked canopy run.

For tile T (a 4x4 block of 0.015 deg WCS chunks, see data/tile_plan.json):
  1. fetch the tile's DSM+DTM chunks (skipped when cached)
  2. mosaic -> CHM = DSM-DTM (float32, nodata -9999, clipped [-2, 60])
  3. apply the City building-footprint mask (2 m buffer -> NaN), same method
     as data/lidar/mask_chm.py, via the prebuilt footprint bbox index
  4. per-parcel masked metrics for every parcel whose centroid falls in the
     tile core, with pilot-identical logic (data/lidar/parcel_canopy_masked.py):
     lot + 6 m buffer zones, tall-canopy area >= 6 m / >= 8 m, max CHM,
     connected-component peaks, roughness gate, calibrated P(DBH>=30) and
     P(DBH>61) rolled up as 1 - prod(1 - p_i)
  5. write data/tiles_out/tile_<T>.json (records, pilot schema + "ward") and
     a uint16-decimetre masked CHM COG data/cogs_tile/tile_<T>.tif (for the
     later per-ward COG merge; the parcel-map endpoint reads ward COGs)

Memory-slim ordering: lot/buf zones are rasterized and reduced one at a time
where possible, and the connected-component labels are dropped before the
fftconvolve passes. Peak is ~30 bytes/px (~600-750 MB for a full 4x4 tile).

Usage: .venv/bin/python3 data/lidar/compute_tile.py --tile 12
"""
import argparse
import gc
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.merge import merge
from rasterio.windows import from_bounds, transform as window_transform
from scipy.ndimage import label as nd_label, maximum_filter
from scipy.signal import fftconvolve
from shapely.geometry import Polygon, shape
from shapely.ops import transform as shp_transform
from pyproj import Transformer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(ROOT, "data")
TILES_OUT = os.path.join(DATA, "tiles_out")
COGS_TILE = os.path.join(DATA, "cogs_tile")
CHUNK_DIR = os.path.join(HERE, "wcs", "city_chunks")
FP_GEOJSON = os.path.join(HERE, "raw", "building_outlines_4326.geojson")
FP_INDEX = os.path.join(HERE, "raw", "footprint_index.npz")
CAL = os.path.join(DATA, "calibration_lidar.json")
CENTROIDS = os.path.join(DATA, "parcel_centroids.npz")

BASE = "https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic"
STEP = 0.015
MARGIN_M = 50.0   # raster margin around the tile core (covers 6 m buffer + 5 m peak windows)
R = 20037508.34


def merc_inv(x, y):
    lon = x / R * 180.0
    lat = (2.0 * math.atan(math.exp(y / R * math.pi)) - math.pi / 2.0) * 180.0 / math.pi
    return (lon, lat)


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def fetch_chunk(layer, i, j):
    fn = os.path.join(CHUNK_DIR, f"{layer}_{i}_{j}.tif")
    if os.path.exists(fn) and os.path.getsize(fn) > 10000:
        return True
    lon_a, lon_b = i * STEP, (i + 1) * STEP
    lat_a, lat_b = j * STEP, (j + 1) * STEP
    url = (f"{BASE}?service=WCS&request=GetCoverage&version=1.1.1&Identifier={layer}"
           f"&boundingbox={lat_a},{lon_a},{lat_b},{lon_b},urn:ogc:def:crs:EPSG::4326"
           f"&format=image/geotiff")
    for _ in range(3):
        r = subprocess.run(
            ["curl", "-s", "--max-time", "300", "-o", fn, "-w", "%{http_code}", url],
            capture_output=True, text=True)
        if r.stdout.strip() == "200" and os.path.getsize(fn) > 10000:
            return True
        time.sleep(5)
    return False


def build_chm(tile):
    """Mosaic the tile's chunks -> masked-convention CHM float32 + transform."""
    lon0, lat0, lon1, lat1 = tile["core_bbox_4326"]
    lat_c = (lat0 + lat1) / 2
    dlat = MARGIN_M / 111320.0
    dlon = MARGIN_M / (111320.0 * math.cos(math.radians(lat_c)))
    eb = (lon0 - dlon, lat0 - dlat, lon1 + dlon, lat1 + dlat)
    # chunk range from the EXPANDED bbox so the merged raster fully covers it
    # (the crop window below is then strictly interior; no wraparound slice)
    i0, i1 = math.floor(eb[0] / STEP), math.floor(eb[2] / STEP)
    j0, j1 = math.floor(eb[1] / STEP), math.floor(eb[3] / STEP)

    jobs = [("dsm", i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]
    jobs += [("dtm", i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda jb: fetch_chunk(*jb), jobs))
    if not all(results):
        bad = [jobs[k] for k, ok in enumerate(results) if not ok]
        raise RuntimeError(f"chunk fetch failed: {bad}")

    arrays = {}
    for layer in ("dsm", "dtm"):
        files = [os.path.join(CHUNK_DIR, f"{layer}_{i}_{j}.tif")
                 for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]
        srcs = [rasterio.open(f) for f in files]
        arr, tr = merge(srcs, nodata=-32767.0)
        for s in srcs:
            s.close()
        win = from_bounds(*eb, tr)
        win = win.round_offsets().round_lengths()
        assert win.col_off >= 0 and win.row_off >= 0, f"window outside mosaic: {win}"
        assert win.col_off + win.width <= arr.shape[2], f"window overflows mosaic: {win}"
        assert win.row_off + win.height <= arr.shape[1], f"window overflows mosaic: {win}"
        arrays[layer] = (arr[0][int(win.row_off):int(win.row_off + win.height),
                               int(win.col_off):int(win.col_off + win.width)],
                         window_transform(win, tr))
        del arr
    dsm, tr = arrays["dsm"]
    dtm, dtr = arrays["dtm"]
    assert dtr == tr and dtm.shape == dsm.shape, "DSM/DTM grid mismatch"
    dsm = dsm.astype("float64")
    dtm = dtm.astype("float64")
    valid = (dsm != -32767.0) & (dtm != -32767.0)
    chm = np.full(dsm.shape, -9999.0, dtype="float32")
    chm[valid] = (dsm[valid] - dtm[valid]).astype("float32")
    chm[(chm < -2) | (chm > 60)] = -9999.0
    del dsm, dtm, valid, arrays
    gc.collect()
    print(f"  CHM {chm.shape}, valid {(chm != -9999).mean() * 100:.1f}%", flush=True)
    return chm, tr, eb


def apply_footprint_mask(chm, transform, eb):
    """NaN the CHM under City building footprints (+2 m buffer)."""
    idx = np.load(FP_INDEX)
    bb = idx["bboxes"]
    sel = ((bb[:, 2] >= eb[0]) & (bb[:, 0] <= eb[2]) &
           (bb[:, 3] >= eb[1]) & (bb[:, 1] <= eb[3]))
    cand = np.flatnonzero(sel)
    print(f"  footprint candidates in tile: {len(cand)}", flush=True)
    if len(cand) == 0:
        return 0
    offsets = idx["offsets"][cand]
    fwd = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    back = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    polys = []
    with open(FP_GEOJSON, "rb") as fh:
        for off in offsets:
            fh.seek(int(off))
            line = fh.readline().decode("utf-8", "ignore").strip()
            try:
                feat = json.loads(line[:-1] if line.endswith(",") else line)
            except json.JSONDecodeError:
                continue
            geom = feat.get("geometry")
            if not geom:
                continue
            try:
                g = shape(geom)
            except Exception:
                continue
            if g.is_empty:
                continue
            gb = shp_transform(lambda x, y: fwd.transform(x, y), g)
            polys.append(shp_transform(lambda x, y: back.transform(x, y),
                                       gb.buffer(2.0)))
    print(f"  parsed {len(polys)} footprints, rasterizing...", flush=True)
    mask = rasterize([(g, 1) for g in polys], out_shape=chm.shape,
                     transform=transform, dtype="uint8")
    n = int(mask.sum())
    chm[mask == 1] = np.nan
    del mask, polys
    gc.collect()
    print(f"  masked {n} px ({n / chm.size * 100:.1f}% of tile)", flush=True)
    return n


def load_tile_parcels(tile):
    """Full parcel records whose centroid falls in the tile core."""
    idx = np.load(CENTROIDS, allow_pickle=True)
    b = tile["core_bbox_4326"]  # [lon0, lat0, lon1, lat1]
    sel = ((idx["lon"] >= b[0]) & (idx["lon"] <= b[2]) &
           (idx["lat"] >= b[1]) & (idx["lat"] <= b[3]))
    want = set(idx["parcel_id"][sel].tolist())
    ward_of = dict(zip(idx["parcel_id"][sel].tolist(), idx["ward"][sel].tolist()))
    print(f"  parcels in tile core: {len(want)}", flush=True)
    # load the ward shards this tile touches (plus unplaced.json when needed)
    recs = {}
    shard_cache = {}
    unplaced = None
    for pid in want:
        w = str(ward_of[pid])
        if w not in shard_cache:
            shard_cache[w] = {p["parcel_id"]: p for p in
                              json.load(open(os.path.join(
                                  DATA, "parcels_toronto", f"ward_{w}.json")))["parcels"]}
        shard_cache[w].get(pid)
        r = shard_cache[w].get(pid)
        if r is None:
            if unplaced is None:
                unplaced = {p["parcel_id"]: p for p in
                            json.load(open(os.path.join(
                                DATA, "parcels_toronto", "unplaced.json")))["parcels"]}
            r = unplaced.get(pid)
        if r is not None:
            rec = dict(r)
            rec["_ward"] = w
            recs[pid] = rec
    print(f"  parcel records resolved: {len(recs)}", flush=True)
    return list(recs.values())


def compute_metrics(chm, transform, parcels, cal):
    """Pilot-identical masked metric computation (parcel_canopy_masked.py)."""
    n = len(parcels)
    res_y = abs(transform[4]) * 111320.0
    res_x = abs(transform[0]) * 111320.0 * math.cos(math.radians(43.67))
    px_area = res_x * res_y
    print(f"  px {res_x:.3f}x{res_y:.3f} m, {n} parcels", flush=True)

    lot_3857, lot_4326, buf_4326 = [], [], []
    for p in parcels:
        rings = [Polygon(r) for r in p["rings_3857"]]
        u3857 = rings[0]
        for r in rings[1:]:
            u3857 = u3857.union(r)
        lot_3857.append(u3857)
        u4326 = shp_transform(lambda x, y: merc_inv(x, y), u3857)
        lot_4326.append(u4326)
        buf = u3857.buffer(6.0).difference(u3857)
        buf_4326.append(shp_transform(lambda x, y: merc_inv(x, y), buf))
    print("  rasterizing lots...", flush=True)
    lot_idx = rasterize([(g, i + 1) for i, g in enumerate(lot_4326)],
                        out_shape=chm.shape, transform=transform, dtype="int32")
    print("  rasterizing buffers...", flush=True)
    buf_idx = rasterize([(g, i + 1) for i, g in enumerate(buf_4326) if not g.is_empty],
                        out_shape=chm.shape, transform=transform, dtype="int32")

    valid = (chm != -9999.0) & np.isfinite(chm)
    tall6 = valid & (chm >= 6.0)
    tall8 = valid & (chm >= 8.0)

    cnt6 = np.bincount(lot_idx.ravel()[tall6.ravel()], minlength=n + 1)[1:]
    cnt8 = np.bincount(lot_idx.ravel()[tall8.ravel()], minlength=n + 1)[1:]
    bcnt6 = np.bincount(buf_idx.ravel()[tall6.ravel()], minlength=n + 1)[1:]
    bcnt8 = np.bincount(buf_idx.ravel()[tall8.ravel()], minlength=n + 1)[1:]

    print("  per-parcel max CHM...", flush=True)
    maxv = np.full(n, np.nan)
    bmaxv = np.full(n, np.nan)
    for idx_arr, out in ((lot_idx, maxv), (buf_idx, bmaxv)):
        lab = idx_arr.ravel()
        order = np.argsort(lab, kind="stable")
        lab_s = lab[order]
        chm_s = np.where(valid.ravel()[order], chm.ravel()[order], -np.inf)
        bounds = np.flatnonzero(np.r_[True, lab_s[1:] != lab_s[:-1]])
        seg_max = np.maximum.reduceat(chm_s, bounds)
        seg_lab = lab_s[bounds]
        has = (seg_lab > 0) & np.isfinite(seg_max)
        out[seg_lab[has] - 1] = seg_max[has]

    mu = np.array(cal["scaler"]["mean"])
    sd = np.array(cal["scaler"]["sd"])
    g30 = cal["generic_ge_30"]
    g61 = cal["generic_gt_61"]

    print("  labeling tall components...", flush=True)
    labels, ncomp = nd_label(tall6, structure=np.ones((3, 3), dtype=bool))
    print(f"  tall components: {ncomp}", flush=True)
    W = chm.shape[1]

    def zone_peaks(idx_arr):
        fidx = idx_arr.ravel()
        flab = labels.ravel()
        m = (fidx > 0) & (flab > 0)
        p = fidx[m] - 1
        l = flab[m]
        h = chm.ravel()[m]
        pix = np.flatnonzero(m)
        order = np.lexsort((l, p))
        p, l, h, pix = p[order], l[order], h[order], pix[order]
        chg = np.flatnonzero((p[1:] != p[:-1]) | (l[1:] != l[:-1]))
        bounds = np.r_[0, chg + 1, len(p)]
        out = {}
        for b0, b1 in zip(bounds[:-1], bounds[1:]):
            if b1 <= b0:  # no pixel in this segment (e.g. zone with no tall pixels)
                continue
            j = b0 + int(np.argmax(h[b0:b1]))
            r_, c_ = divmod(int(pix[j]), W)
            out.setdefault(int(p[b0]), []).append((r_, c_))
        return out

    print("  zone peaks...", flush=True)
    lot_peaks = zone_peaks(lot_idx)
    buf_peaks = zone_peaks(buf_idx)
    del labels, lot_idx, buf_idx
    gc.collect()
    print(f"  parcels with lot peaks: {len(lot_peaks)}, buffer peaks: {len(buf_peaks)}",
          flush=True)

    rx = int(math.ceil(5.0 / res_x)) + 1
    ry = int(math.ceil(5.0 / res_y)) + 1
    ky, kx = np.mgrid[-ry:ry + 1, -rx:rx + 1]
    kernel = (((kx * res_x) ** 2 + (ky * res_y) ** 2) <= 25.0).astype("float32")
    print("  convolutions...", flush=True)
    area_cnt = fftconvolve(tall6.astype("float32"), kernel, mode="same")
    del tall6
    gc.collect()
    vf = valid.astype("float32")
    cf = np.where(valid, chm, 0.0).astype("float32")
    del valid
    gc.collect()
    kc = fftconvolve(vf, kernel, mode="same")
    del vf
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = fftconvolve(cf, kernel, mode="same") / kc
        e2 = fftconvolve(cf * cf, kernel, mode="same") / kc
    del cf
    rough = np.sqrt(np.maximum(e2 - mean * mean, 0.0)).astype("float32")
    del mean, e2
    rough[kc < 3] = 0.0
    del kc
    gc.collect()
    h3 = maximum_filter(np.where(np.isfinite(chm), chm, -np.inf), size=3)
    gate = float(cal["roughness_gate_m"])
    print(f"  roughness gate: {gate} m", flush=True)

    def probs(rows, cols):
        h = h3[rows, cols]
        a = area_cnt[rows, cols] * px_area
        z = (np.column_stack([h, a]) - mu) / sd
        p30 = sigmoid(g30["intercept"] + z[:, 0] * g30["coef_h"] + z[:, 1] * g30["coef_area"])
        p61 = sigmoid(g61["intercept"] + z[:, 0] * g61["coef_h"] + z[:, 1] * g61["coef_area"])
        return p30, p61

    p_lot30 = np.zeros(n)
    p_lot61 = np.zeros(n)
    p_buf30 = np.zeros(n)
    p_buf61 = np.zeros(n)
    npeak_lot = np.zeros(n, dtype="int32")
    npeak_buf = np.zeros(n, dtype="int32")

    print("  scoring peaks...", flush=True)
    for li, pts in lot_peaks.items():
        pts = [(r, c) for r, c in pts if rough[r, c] >= gate]
        if not pts:
            continue
        rr = np.array([p[0] for p in pts])
        cc = np.array([p[1] for p in pts])
        p30, p61 = probs(rr, cc)
        p_lot30[li] = 1.0 - float(np.prod(1.0 - p30))
        p_lot61[li] = 1.0 - float(np.prod(1.0 - p61))
        npeak_lot[li] = len(rr)
    for li, pts in buf_peaks.items():
        pts = [(r, c) for r, c in pts if rough[r, c] >= gate]
        if not pts:
            continue
        rr = np.array([p[0] for p in pts])
        cc = np.array([p[1] for p in pts])
        p30, p61 = probs(rr, cc)
        p_buf30[li] = 1.0 - float(np.prod(1.0 - p30))
        p_buf61[li] = 1.0 - float(np.prod(1.0 - p61))
        npeak_buf[li] = len(rr)
    del rough, h3, area_cnt, tall8
    gc.collect()

    out = {}
    for i, p in enumerate(parcels):
        area = p["area_m2"] or 0.0
        ring = [merc_inv(x, y) for x, y in p["rings_3857"][0]]
        xs = [c[0] for c in ring]
        ys = [c[1] for c in ring]
        a6 = cnt6[i] * px_area
        a8 = cnt8[i] * px_area
        b6 = bcnt6[i] * px_area
        b8 = bcnt8[i] * px_area
        out[p["parcel_id"]] = {
            "parcel_id": p["parcel_id"],
            "address": p["address"],
            "area_m2": round(area, 1),
            "centroid_4326": p["centroid_4326"],
            "bbox_4326": [round(min(xs), 6), round(min(ys), 6),
                          round(max(xs), 6), round(max(ys), 6)],
            "ring_4326": [[round(x, 6), round(y, 6)] for x, y in ring],
            "ward": p["_ward"],
            "lot": {
                "tall_canopy_m2_ge6": round(float(a6), 1),
                "tall_canopy_m2_ge8": round(float(a8), 1),
                "max_chm_m": round(float(maxv[i]), 2) if np.isfinite(maxv[i]) else None,
                "canopy_pct_6": round(float(a6 / area * 100), 1) if area else 0.0,
                "canopy_pct_8": round(float(a8 / area * 100), 1) if area else 0.0,
                "p_any_ge_30cm": round(float(p_lot30[i]), 4),
                "p_any_distinctive": round(float(p_lot61[i]), 4),
                "peak_count": int(npeak_lot[i]),
            },
            "buffer_6m": {
                "tall_canopy_m2_ge6": round(float(b6), 1),
                "tall_canopy_m2_ge8": round(float(b8), 1),
                "max_chm_m": round(float(bmaxv[i]), 2) if np.isfinite(bmaxv[i]) else None,
                "canopy_pct_6": None,
                "canopy_pct_8": None,
                "p_any_ge_30cm": round(float(p_buf30[i]), 4),
                "p_any_distinctive": round(float(p_buf61[i]), 4),
                "peak_count": int(npeak_buf[i]),
            },
            "imagery_vintage": "2023 LiDAR",
        }
    return out


def write_tile_cog(chm, transform, tile):
    """uint16-decimetre masked CHM COG for the tile (later merged per ward)."""
    os.makedirs(COGS_TILE, exist_ok=True)
    q = np.full(chm.shape, 65535, dtype="uint16")
    m = np.isfinite(chm) & (chm != -9999.0)
    q[m] = np.clip(np.round(chm[m] * 10.0), 0, 600).astype("uint16")
    profile = {
        "driver": "GTiff", "dtype": "uint16", "nodata": 65535,
        "width": chm.shape[1], "height": chm.shape[0], "count": 1,
        "crs": "EPSG:4326", "transform": transform,
        "tiled": True, "blockxsize": 256, "blockysize": 256,
        "compress": "deflate", "predictor": 2,
    }
    fn = os.path.join(COGS_TILE, f"tile_{tile['tile']}.tif")
    with rasterio.open(fn, "w", **profile) as dst:
        dst.write(q, 1)
    size = os.path.getsize(fn)
    print(f"  wrote {fn} ({size / 1e6:.1f} MB)", flush=True)
    return fn, size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tile", type=int, required=True)
    args = ap.parse_args()
    plan = json.load(open(os.path.join(DATA, "tile_plan.json")))
    tile = plan["tiles"][args.tile]
    t0 = time.time()
    print(f"TILE {args.tile}: chunks i{tile['chunk_i']} j{tile['chunk_j']}, "
          f"wards {tile['wards']}", flush=True)

    chm, transform, eb = build_chm(tile)
    n_mask = apply_footprint_mask(chm, transform, eb)
    v = chm[np.isfinite(chm) & (chm != -9999.0)]
    tall_frac = float((v >= 8.0).mean()) if v.size else 0.0
    print(f"  masked tall-band (>=8 m) fraction of valid px: {tall_frac * 100:.2f}%",
          flush=True)

    parcels = load_tile_parcels(tile)
    cal = json.load(open(CAL))
    records = compute_metrics(chm, transform, parcels, cal)

    os.makedirs(TILES_OUT, exist_ok=True)
    out_fn = os.path.join(TILES_OUT, f"tile_{args.tile}.json")
    json.dump(records, open(out_fn, "w"))
    print(f"  wrote {out_fn}: {len(records)} records", flush=True)

    cog_fn, cog_size = write_tile_cog(chm, transform, tile)

    a8s = np.array([r["lot"]["tall_canopy_m2_ge8"] for r in records.values()])
    p30s = np.array([r["lot"]["p_any_ge_30cm"] for r in records.values()])
    stats = {
        "tile": args.tile,
        "parcels": len(records),
        "masked_px": int(n_mask),
        "tall_frac_ge8": round(tall_frac, 4),
        "lot_ge8_median": round(float(np.median(a8s)), 1),
        "lot_ge8_frac_pos": round(float((a8s > 0).mean()), 4),
        "p30_median": round(float(np.median(p30s)), 4),
        "cog_mb": round(cog_size / 1e6, 1),
        "wall_s": round(time.time() - t0, 1),
    }
    with open(os.path.join(TILES_OUT, "stats.jsonl"), "a") as fh:
        fh.write(json.dumps(stats) + "\n")
    print(f"TILE {args.tile} DONE in {stats['wall_s']}s: {json.dumps(stats)}", flush=True)


if __name__ == "__main__":
    main()
