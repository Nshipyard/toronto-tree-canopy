"""Arm B: detect trees in HEIGHT space (CHM), standard forestry recipe.

1. CHM reprojected to EPSG:3857 at 1 m square pixels (working in meters).
2. Gaussian smooth sigma~1m, local maxima (min separation ~3m, min height ~2.5m).
3. Marker-controlled watershed on inverted CHM, masked at a height floor.
4. Building suppression: drop segments with low CHM roughness (std in 5m
   window), or very large AND flat segments.
5. One box per surviving segment (segment bbox), score = segment max CHM
   normalized to [0,1] per tile.

Params picked on qa1+qa3 ONLY. qa7 untouched until final eval.
Usage: python detect_armB.py          -> reproject CHM + run param grid on qa1+qa3
       python detect_armB.py final    -> final params on qa1,qa3,qa7 + eval + outputs
"""
import json, os, sys
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling, calculate_default_transform
from scipy.ndimage import gaussian_filter, uniform_filter
from skimage.feature import peak_local_max
from skimage.segmentation import watershed
from skimage.measure import regionprops

W = os.path.expanduser("~/workspace/toronto-tree-canopy/data/lidar/qa_cover")
ROOT = os.path.expanduser("~/workspace/toronto-tree-canopy")
CHM3857 = os.path.join(W, "qa_cover_chm_3857.tif")


def reproject_chm():
    src_f = os.path.join(W, "qa_cover_chm.tif")
    with rasterio.open(src_f) as src:
        dst_transform, dst_w, dst_h = calculate_default_transform(
            src.crs, "EPSG:3857", src.width, src.height, *src.bounds, resolution=1.0)
        profile = src.profile.copy()
        profile.update(crs="EPSG:3857", transform=dst_transform, width=dst_w,
                       height=dst_h, compress="deflate", predictor=2, tiled=True)
        with rasterio.open(CHM3857, "w", **profile) as dst:
            reproject(rasterio.band(src, 1), rasterio.band(dst, 1),
                      resampling=Resampling.bilinear, src_nodata=-9999.0, dst_nodata=-9999.0)
    print("wrote", CHM3857)


def tile_chm(tile):
    """Return 80x80 m CHM array for a QA tile footprint (row 0 = tile top)."""
    t = json.load(open(os.path.join(ROOT, "data", "qa-tiles", f"{tile}.json")))
    xmin, ymin, xmax, ymax = t["bbox_3857"]
    with rasterio.open(CHM3857) as src:
        win = rasterio.windows.from_bounds(xmin, ymin, xmax, ymax, src.transform)
        win = win.round_offsets().round_lengths()
        a = src.read(1, window=win)
    a = np.where(a == -9999.0, np.nan, a)
    return a  # shape ~80x80, y=0 is top


def roughness_map(chm, win=5):
    """Local std of CHM in a win x win px window (nan-aware)."""
    c = np.where(np.isnan(chm), 0.0, chm)
    m = ~np.isnan(chm)
    s1 = uniform_filter(c, size=win, mode="reflect")
    s2 = uniform_filter(c * c, size=win, mode="reflect")
    n = uniform_filter(m.astype(float), size=win, mode="reflect")
    var = np.maximum(s2 - s1 * s1, 0.0)
    return np.sqrt(var)


def detect(chm, sigma=1.0, min_dist=3, peak_h=2.5, floor=1.5,
           rough_thresh=1.0, big_area=400.0, big_rough=0.5, max_area=0.0):
    """chm: (H,W) meters, y=0 top. Returns list of [x0,y0,x1,y1,score]."""
    chm_s = gaussian_filter(np.nan_to_num(chm, nan=0.0), sigma=sigma)
    peaks = peak_local_max(chm_s, min_distance=min_dist, threshold_abs=peak_h,
                           exclude_border=False)
    markers = np.zeros(chm.shape, dtype=np.int32)
    for k, (r, c) in enumerate(peaks):
        markers[r, c] = k + 1
    mask = chm_s > floor
    if markers.sum() == 0 or mask.sum() == 0:
        return []
    seg = watershed(-chm_s, markers, mask=mask)
    rough = roughness_map(chm)
    out = []
    for r in regionprops(seg, intensity_image=rough):
        seg_mask = seg == r.label
        area = float(r.area)  # px = m^2 at 1 m
        mean_rough = float(r.intensity_mean)
        if max_area > 0 and area > max_area:
            continue
        if mean_rough < rough_thresh:
            continue
        if area > big_area and mean_rough < big_rough:
            continue
        y0, x0, y1, x1 = r.bbox
        hmax = float(np.nanmax(np.where(seg_mask, chm, np.nan)))
        out.append([float(x0), float(y0), float(x1), float(y1), hmax, area, mean_rough])
    return out


def boxes_with_scores(dets):
    """Normalize segment max CHM to [0,1] per tile -> [x0,y0,x1,y1,score]."""
    if not dets:
        return []
    hs = np.array([d[4] for d in dets])
    lo, hi = hs.min(), hs.max()
    rng = hi - lo if hi > lo else 1.0
    return [[d[0], d[1], d[2], d[3], float((d[4] - lo) / rng)] for d in dets]


def quick_f1(preds13, tiles=("qa1", "qa3")):
    """F1 at IoU 0.5 best threshold, using the shared harness."""
    sys.path.insert(0, os.path.join(ROOT, "pipeline"))
    from eval_harness import load_gt, evaluate
    gt = load_gt(list(tiles))
    res = evaluate(preds13, gt, arm_name="chm-watershed")
    return res


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "grid"
    if not os.path.exists(CHM3857):
        reproject_chm()

    if mode == "grid":
        import itertools
        sigmas = [0.5, 1.0]
        dists = [2, 3]
        floors = [1.0, 1.5]
        peaks = [2.0, 2.5]
        roughs = [0.0, 0.5, 0.75, 1.0]
        max_areas = [0.0, 120.0, 200.0]
        bigs = [(400.0, 0.5), (0.0, 0.0)]  # (big_area, big_rough); area 0 disables
        tiles = ["qa1", "qa3"]
        chms = {t: tile_chm(t) for t in tiles}
        rows = []
        for sig, md, floor, peak_h, rt, ma, (ba, br) in itertools.product(
                sigmas, dists, floors, peaks, roughs, max_areas, bigs):
            preds = {}
            for t in tiles:
                dets = detect(chms[t], sigma=sig, min_dist=md, floor=floor,
                              peak_h=peak_h, rough_thresh=rt, big_area=ba,
                              big_rough=br, max_area=ma)
                preds[t] = boxes_with_scores(dets)
            res = quick_f1(preds)
            n = sum(len(v) for v in preds.values())
            rows.append((res["best"]["f1"], res["best"]["threshold"],
                         res["best"]["precision"], res["best"]["recall"],
                         sig, md, floor, peak_h, rt, ma, ba, br, n))
        rows.sort(reverse=True)
        print("f1  thr   prec  rec   sig md floor peak rough maxA bigA bigR n_pred")
        for r in rows[:15]:
            print(f"{r[0]:.3f} {r[1]:.2f} {r[2]:.3f} {r[3]:.3f} "
                  f"{r[4]:.1f} {r[5]} {r[6]:.1f} {r[7]:.1f} {r[8]:.2f} {r[9]:.0f} {r[10]:.0f} {r[11]:.1f} {r[12]}")
        best = rows[0]
        keys = ["f1","thr","prec","rec","sig","md","floor","peak_h","rough","maxA","bigA","bigR","n_pred"]
        print("BEST: " + " ".join(f"{k}={v}" for k, v in zip(keys, best)))
        with open(os.path.join(W, "grid_qa13.json"), "w") as f:
            json.dump({"grid": [dict(zip(keys, r)) for r in rows]}, f, indent=1)
