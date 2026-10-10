"""Per-parcel tall-canopy metrics for every Ward 12 parcel (Track B), MASKED variant.

Identical to data/lidar/parcel_canopy.py EXCEPT:
  - reads the building-masked CHM (data/lidar/wcs/ward12_chm_full_masked.tif),
    where City building footprints (2 m buffer) are NaN (see data/lidar/mask_chm.py)
  - the `valid` pixel selector additionally excludes NaN (required: NaN would
    otherwise poison the max-CHM reduce and the roughness convolution)
  - writes data/parcel_canopy_ward12_masked.json (intermediate; copied over
    data/parcel_canopy_ward12.json only after comparison against the old file)

Same thresholds, same roughness gate, same peak logic: the mask effect is isolated.

Reads the full-ward masked 1 m CHM and
data/parcels_ward12.json, then for EACH parcel computes, for the LOT and for
the 6 m NEIGHBOUR BUFFER (buffer minus lot, matching the by-law site-plan rule):
  - tall-canopy area with CHM >= 6 m and >= 8 m (m^2)
  - max CHM (m)
  - canopy percentage = tall-canopy area / parcel area_m2 (both thresholds)
  - calibrated P(any tree DBH >= 30 cm) and P(any tree DBH > 61 cm):
    one apex peak per contiguous tall (>= 6 m) structure (connected components
    of the tall mask; a flat roof is one peak, a tree crown is one peak),
    then a roughness gate: peaks smoother than p1 of street-tree crown roughness
    are treated as structures (flat roofs) and excluded. Surviving peaks are
    scored with the generic logistic model from calibrate_lidar.py (features:
    max CHM in ~3 m window, tall-canopy area in 5 m radius), then rolled up as
    1 - prod(1 - p_i).

Writes data/parcel_canopy_ward12.json keyed by parcel id, with centroid, bbox
and ring in WGS84 so the API can do point-in-polygon without the 14 MB parcels
file. Deterministic; no ML training here.

Run: .venv/bin/python3 data/lidar/parcel_canopy.py
"""
import json
import math
import os

import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import maximum_filter
from scipy.signal import fftconvolve
from shapely.geometry import Polygon
from shapely.ops import transform as shp_transform

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHM = os.path.join(HERE, "wcs", "ward12_chm_full_masked.tif")
PARCELS = os.path.join(ROOT, "parcels_ward12.json")
CAL = os.path.join(ROOT, "calibration_lidar.json")
OUT = os.path.join(ROOT, "parcel_canopy_ward12_masked.json")

R = 20037508.34


def merc_inv(x, y):
    lon = x / R * 180.0
    lat = (2.0 * math.atan(math.exp(y / R * math.pi)) - math.pi / 2.0) * 180.0 / math.pi
    return (lon, lat)


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def main():
    src = rasterio.open(CHM)
    chm = src.read(1)
    transform, shape = src.transform, chm.shape
    res_y = abs(transform[4]) * 111320.0
    res_x = abs(transform[0]) * 111320.0 * math.cos(math.radians(43.67))
    px_area = res_x * res_y
    print(f"CHM {shape}, px {res_x:.3f}x{res_y:.3f} m", flush=True)

    parcels = json.load(open(PARCELS))["parcels"]
    n = len(parcels)
    print(f"parcels: {n}", flush=True)

    # polygons in 3857 (for the 6 m buffer) and 4326 (for rasterize + API rings)
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

    print("rasterizing lots...", flush=True)
    lot_idx = rasterize([(g, i + 1) for i, g in enumerate(lot_4326)],
                        out_shape=shape, transform=transform, dtype="int32")
    print("rasterizing buffers...", flush=True)
    buf_idx = rasterize([(g, i + 1) for i, g in enumerate(buf_4326) if not g.is_empty],
                        out_shape=shape, transform=transform, dtype="int32")

    valid = (chm != -9999.0) & np.isfinite(chm)
    tall6 = valid & (chm >= 6.0)
    tall8 = valid & (chm >= 8.0)

    cnt_valid = np.bincount(lot_idx.ravel(), minlength=n + 1)[1:]
    cnt6 = np.bincount(lot_idx.ravel()[tall6.ravel()], minlength=n + 1)[1:]
    cnt8 = np.bincount(lot_idx.ravel()[tall8.ravel()], minlength=n + 1)[1:]
    bcnt_valid = np.bincount(buf_idx.ravel(), minlength=n + 1)[1:]
    bcnt6 = np.bincount(buf_idx.ravel()[tall6.ravel()], minlength=n + 1)[1:]
    bcnt8 = np.bincount(buf_idx.ravel()[tall8.ravel()], minlength=n + 1)[1:]

    print("per-parcel max CHM...", flush=True)
    maxv = np.full(n, np.nan)
    bmaxv = np.full(n, np.nan)
    # vectorized per-label max via sorting trick
    for idx_arr, out in ((lot_idx, maxv), (buf_idx, bmaxv)):
        lab = idx_arr.ravel()
        order = np.argsort(lab, kind="stable")
        lab_s = lab[order]
        chm_s = np.where(valid.ravel()[order], chm.ravel()[order], -np.inf)
        # segment maxima
        bounds = np.flatnonzero(np.r_[True, lab_s[1:] != lab_s[:-1]])
        seg_max = np.maximum.reduceat(chm_s, bounds)
        seg_lab = lab_s[bounds]
        has = (seg_lab > 0) & np.isfinite(seg_max)
        out[seg_lab[has] - 1] = seg_max[has]

    # ---- calibrated mature-tree probabilities from LiDAR peaks ----
    # One peak per (contiguous tall structure x parcel): label connected
    # components of the >= 6 m mask (a flat roof is one component, a tree crown
    # is one component), then for each parcel take the highest pixel of each
    # component touching it. This avoids counting every pixel of a roof plateau
    # as a separate "tree", while a component shared across a boundary still
    # gives each parcel its own peak (no cross-parcel zeroing).
    # Each peak is scored with the generic logistic model from calibrate_lidar.py
    # (features: max CHM in ~3 m window, tall-canopy area in 5 m radius) and
    # rolled up per zone as 1 - prod(1 - p_i).
    cal = json.load(open(CAL))
    mu = np.array(cal["scaler"]["mean"])
    sd = np.array(cal["scaler"]["sd"])
    g30 = cal["generic_ge_30"]
    g61 = cal["generic_gt_61"]

    print("labeling tall components...", flush=True)
    from scipy.ndimage import label as nd_label
    labels, ncomp = nd_label(tall6, structure=np.ones((3, 3), dtype=bool))
    print(f"tall components: {ncomp}", flush=True)

    W = chm.shape[1]

    def zone_peaks(idx_arr):
        """Return {parcel_i: ([rows], [cols])} of component apexes in the zone."""
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
            j = b0 + int(np.argmax(h[b0:b1]))
            r_, c_ = divmod(int(pix[j]), W)
            out.setdefault(int(p[b0]), []).append((r_, c_))
        return out

    print("lot zone peaks...", flush=True)
    lot_peaks = zone_peaks(lot_idx)
    print("buffer zone peaks...", flush=True)
    buf_peaks = zone_peaks(buf_idx)
    print(f"parcels with lot peaks: {len(lot_peaks)}, with buffer peaks: {len(buf_peaks)}",
          flush=True)

    # tall-canopy area in a 5 m elliptical footprint, for every pixel (exact kernel)
    rx = int(math.ceil(5.0 / res_x)) + 1
    ry = int(math.ceil(5.0 / res_y)) + 1
    ky, kx = np.mgrid[-ry:ry + 1, -rx:rx + 1]
    kernel = (((kx * res_x) ** 2 + (ky * res_y) ** 2) <= 25.0).astype("float32")
    area_cnt = fftconvolve(tall6.astype("float32"), kernel, mode="same")
    h3 = maximum_filter(np.where(valid, chm, -np.inf), size=3)

    # per-pixel roughness: std of valid CHM inside the same 5 m elliptical window.
    # Peaks smoother than p1 of street-tree roughness are structures (flat roofs),
    # not trees: exclude them from scoring.
    gate = float(cal["roughness_gate_m"])
    print(f"roughness gate: {gate} m", flush=True)
    vf = valid.astype("float32")
    cf = np.where(valid, chm, 0.0).astype("float32")
    kc = fftconvolve(vf, kernel, mode="same")
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = fftconvolve(cf, kernel, mode="same") / kc
        e2 = fftconvolve(cf * cf, kernel, mode="same") / kc
    rough = np.sqrt(np.maximum(e2 - mean * mean, 0.0)).astype("float32")
    rough[kc < 3] = 0.0

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

    print("scoring lot peaks...", flush=True)
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
    print("scoring buffer peaks...", flush=True)
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

    print("writing", OUT, flush=True)
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
    json.dump(out, open(OUT, "w"))
    print(f"wrote {OUT}: {len(out)} parcels", flush=True)
    # quick sanity stats
    a8s = np.array([v["lot"]["tall_canopy_m2_ge8"] for v in out.values()])
    p30s = np.array([v["lot"]["p_any_ge_30cm"] for v in out.values()])
    print(f"lot ge8 area: median {np.median(a8s):.1f} m2, p90 {np.percentile(a8s,90):.1f}, "
          f"frac>0 {(a8s>0).mean()*100:.1f}%", flush=True)
    print(f"lot P(any>=30): median {np.median(p30s):.3f}, "
          f"frac>0.5 {(p30s>0.5).mean()*100:.1f}%", flush=True)


if __name__ == "__main__":
    main()
