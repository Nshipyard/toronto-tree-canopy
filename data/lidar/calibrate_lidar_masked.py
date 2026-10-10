"""Calibrate P(DBH >= 30 cm | LiDAR height, tall-canopy area) on street trees,
MASKED variant.

Identical to data/lidar/calibrate_lidar.py EXCEPT:
  - samples the building-masked CHM (ward12_chm_full_masked.tif): City
    building footprints (2 m buffer) are NaN, so roofs no longer contribute
    height or tall-canopy area to the fit features
  - NaN is treated as nodata everywhere in the window sampling (a NaN-only
    window counts as no-CHM and the tree is dropped from the fit set)

Output overwrites data/calibration_lidar.json (same schema) with the masked fit.

Run: .venv/bin/python3 data/lidar/calibrate_lidar_masked.py

For each Ward 12 street tree with a known DBH (City of Toronto street-tree
inventory, 18,052 trees), sample the 2023 LiDAR CHM at its location:
  - h: max CHM in a ~3 m window (3x3 px)
  - area: tall-canopy area (CHM >= 6 m) inside a 5 m radius, in m^2
Fit logistic regression P(DBH>=30 | h, area): one generic model (shipped in
the app) plus per-genus models where n >= 500 (reported, not shipped: genus is
unknown at inference time). Also fit generic P(DBH>61) for the Distinctive tier.

Outputs data/calibration_lidar.json: coefficients, scaler, AUCs, binned
observed-vs-predicted calibration, and a plain-language limitations note.

LIMITATION (stated in the JSON and METHOD_NOTES): street trees are managed
road-allowance trees, pruned and spaced by the City; transfer of the fitted
relationship to private backyard trees is approximate. The model also
conditions on tree presence: applied to a LiDAR peak, it answers "IF this peak
is a tree, how likely is it mature", so peaks over buildings inflate parcel
rollups. Screening signal only.

Run: .venv/bin/python3 data/lidar/calibrate_lidar.py
"""
import csv
import json
import math
import os

import numpy as np
import rasterio
from shapely.geometry import Point, shape
from shapely.prepared import prep
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_score

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHM = os.path.join(HERE, "wcs", "ward12_chm_full_masked.tif")
TREES = os.path.join(ROOT, "street_trees.csv")
WARD_GEO = os.path.join(ROOT, "ward12.geojson")
OUT = os.path.join(ROOT, "calibration_lidar.json")

H_THRESH = 6.0   # tall-canopy threshold (m)
R_M = 5.0        # area radius (m)


def norm_genus(botanical):
    g = (botanical or "").split()
    return g[0][:1].upper() + g[0][1:].lower() if g else "Unknown"


def main():
    src = rasterio.open(CHM)
    chm = src.read(1)
    valid = (chm != -9999.0) & np.isfinite(chm)
    res_y = abs(src.transform[4]) * 111320.0          # m per px N-S
    res_x = abs(src.transform[0]) * 111320.0 * math.cos(math.radians(43.67))
    px_area = res_x * res_y
    print(f"CHM {chm.shape}, px {res_x:.2f}x{res_y:.2f} m, area {px_area:.3f} m2", flush=True)

    # 5 m elliptical footprint offsets (in px)
    rx = int(math.ceil(R_M / res_x)) + 1
    ry = int(math.ceil(R_M / res_y)) + 1
    offs = [(dx, dy) for dy in range(-ry, ry + 1) for dx in range(-rx, rx + 1)
            if (dx * res_x) ** 2 + (dy * res_y) ** 2 <= R_M ** 2]
    print(f"footprint: {len(offs)} px in 5 m radius", flush=True)

    # Ward 12 tree selection is GEOMETRIC (point in the ward polygon), not by the
    # CSV's WARD column: that column uses a different ward numbering (trees inside
    # the Davenport polygon carry WARD='09'), so WARD=='12' selects trees that are
    # not in Ward 12 at all.
    wgeo = json.load(open(WARD_GEO))["features"][0]["geometry"]
    ward_shape = shape(wgeo)
    ward_poly = prep(ward_shape)
    wxs = [c[0] for c in ward_shape.exterior.coords]
    wys = [c[1] for c in ward_shape.exterior.coords]
    wbbox = (min(wxs), min(wys), max(wxs), max(wys))

    H, A, Y30, Y61, G = [], [], [], [], []
    n_no_chm = 0
    n_outside = 0
    rough = []
    with open(TREES, newline="") as fh:
        for r in csv.DictReader(fh):
            if not (r["DBH_TRUNK"] or "").strip():
                continue
            try:
                g = json.loads(r["geometry"])
                lon, lat = g["coordinates"]
                dbh = float(r["DBH_TRUNK"])
            except Exception:
                continue
            if not (wbbox[0] <= lon <= wbbox[2] and wbbox[1] <= lat <= wbbox[3]):
                n_outside += 1
                continue
            if not ward_poly.contains(Point(lon, lat)):
                n_outside += 1
                continue
            try:
                row, col = src.index(lon, lat)
            except Exception:
                n_no_chm += 1
                continue
            hgt, wdt = chm.shape
            if not (1 <= row < hgt - 1 and 1 <= col < wdt - 1):
                n_no_chm += 1
                continue
            win = chm[row - 1:row + 2, col - 1:col + 2]
            wv = win[np.isfinite(win)]
            if wv.size == 0:
                n_no_chm += 1
                continue
            h = float(wv.max())
            cnt = 0
            rvals = []
            for dx, dy in offs:
                rr, cc = row + dy, col + dx
                if 0 <= rr < hgt and 0 <= cc < wdt and np.isfinite(chm[rr, cc]):
                    rvals.append(chm[rr, cc])
                    if chm[rr, cc] >= H_THRESH:
                        cnt += 1
            rough.append(float(np.std(rvals)) if len(rvals) > 3 else 0.0)
            H.append(h)
            A.append(cnt * px_area)
            Y30.append(1 if dbh >= 30 else 0)
            Y61.append(1 if dbh > 61 else 0)
            G.append(norm_genus(r["BOTANICAL_NAME"]))
    src.close()

    H = np.array(H); A = np.array(A)
    Y30 = np.array(Y30); Y61 = np.array(Y61); G = np.array(G)
    X = np.column_stack([H, A])
    mu, sd = X.mean(axis=0), X.std(axis=0)
    Xs = (X - mu) / sd
    print(f"trees sampled: {len(H)} (outside ward: {n_outside}, no CHM: {n_no_chm}), "
          f"frac>=30cm: {Y30.mean():.3f}, frac>61cm: {Y61.mean():.3f}", flush=True)

    def fit(Xs_, y):
        m = LogisticRegression(max_iter=2000, C=1.0)
        m.fit(Xs_, y)
        auc = roc_auc_score(y, m.predict_proba(Xs_)[:, 1])
        cv = cross_val_score(m, Xs_, y, cv=5, scoring="roc_auc")
        return m, auc, cv

    def bins(m, Xs_, y, k=10):
        p = m.predict_proba(Xs_)[:, 1]
        qs = np.quantile(p, np.linspace(0, 1, k + 1))
        out = []
        for i in range(k):
            lo, hi = qs[i], qs[i + 1]
            sel = (p >= lo) & (p <= hi if i == k - 1 else p < hi)
            if sel.sum() == 0:
                continue
            out.append({"n": int(sel.sum()),
                        "pred_mean": round(float(p[sel].mean()), 4),
                        "obs_frac": round(float(y[sel].mean()), 4)})
        return out

    m30, auc30, cv30 = fit(Xs, Y30)
    m61, auc61, cv61 = fit(Xs, Y61)
    print(f"generic P(DBH>=30): train AUC {auc30:.3f}, CV AUC {cv30.mean():.3f}±{cv30.std():.3f}",
          flush=True)
    print(f"generic P(DBH>61):  train AUC {auc61:.3f}, CV AUC {cv61.mean():.3f}±{cv61.std():.3f}",
          flush=True)
    print(f"generic>=30 coef (std): intercept {m30.intercept_[0]:.3f}, "
          f"h {m30.coef_[0][0]:.3f}, area {m30.coef_[0][1]:.3f}", flush=True)

    genus_models = {}
    for genus in sorted(set(G)):
        sel = G == genus
        n = int(sel.sum())
        if n < 500:
            continue
        mg, ag, cvg = fit(Xs[sel], Y30[sel])
        genus_models[genus] = {
            "n": n, "frac_ge_30": round(float(Y30[sel].mean()), 4),
            "train_auc": round(float(ag), 4),
            "cv_auc_mean": round(float(cvg.mean()), 4),
            "cv_auc_sd": round(float(cvg.std()), 4),
            "intercept": round(float(mg.intercept_[0]), 4),
            "coef_h": round(float(mg.coef_[0][0]), 4),
            "coef_area": round(float(mg.coef_[0][1]), 4),
        }
        print(f"  {genus:12s} n={n:5d} AUC {ag:.3f} (CV {cvg.mean():.3f}±{cvg.std():.3f})",
              flush=True)

    rough = np.array(rough)
    r_p1, r_p5, r_med = (round(float(np.percentile(rough, q)), 3) for q in (1, 5, 50))
    print(f"roughness (CHM std in 5 m) at trees: p1={r_p1} p5={r_p5} median={r_med} m",
          flush=True)
    # Gate at p5: peaks smoother than 95% of street-tree crowns are treated as
    # structures (flat roofs), not trees. The sub-p5 trees are mostly small
    # ornamentals, so excluding them barely moves P(mature).

    doc = {
        "vintage": "2023 LiDAR (NRCan HRDEM mosaic, TRCA GTA_2023)",
        "features": {
            "h": "max CHM (m) in ~3 m window at the tree location",
            "area": "tall-canopy area (m^2), CHM >= 6 m inside 5 m radius",
        },
        "scaler": {"mean": [round(float(mu[0]), 4), round(float(mu[1]), 4)],
                   "sd": [round(float(sd[0]), 4), round(float(sd[1]), 4)]},
        "n_trees": int(len(H)),
        "n_no_chm": int(n_no_chm),
        "roughness_gate_m": r_p5,
        "roughness_note": (
            "Peaks smoother than p5 of street-tree crown roughness are treated as "
            "structures (flat roofs), not trees, and excluded from parcel scoring. "
            f"At fit trees: p1={r_p1} m, p5={r_p5} m, median={r_med} m."
        ),
        "generic_ge_30": {
            "intercept": round(float(m30.intercept_[0]), 4),
            "coef_h": round(float(m30.coef_[0][0]), 4),
            "coef_area": round(float(m30.coef_[0][1]), 4),
            "train_auc": round(float(auc30), 4),
            "cv_auc_mean": round(float(cv30.mean()), 4),
            "cv_auc_sd": round(float(cv30.std()), 4),
            "calibration_bins": bins(m30, Xs, Y30),
        },
        "generic_gt_61": {
            "intercept": round(float(m61.intercept_[0]), 4),
            "coef_h": round(float(m61.coef_[0][0]), 4),
            "coef_area": round(float(m61.coef_[0][1]), 4),
            "train_auc": round(float(auc61), 4),
            "cv_auc_mean": round(float(cv61.mean()), 4),
            "cv_auc_sd": round(float(cv61.std()), 4),
            "calibration_bins": bins(m61, Xs, Y61),
        },
        "per_genus_ge_30": genus_models,
        "shipped": "generic_ge_30 and generic_gt_61 (genus is unknown at inference time)",
        "limitations": (
            "Fit on City of Toronto street trees: managed road-allowance trees, "
            "pruned and spaced by the City. Transfer to private backyard trees is "
            "approximate. The model conditions on tree presence: P(DBH>=30 | h, area) "
            "was fit at known tree locations, so applied to a LiDAR peak it answers "
            "'if this peak is a tree, how likely is it mature'. Peaks smoother than "
            "p5 of street-tree crown roughness are excluded as structures (flat roofs). "
            "City building footprints (2 m buffer) are masked to NaN in the CHM, so "
            "mapped buildings no longer contribute peaks; structures missing from the "
            "footprint dataset (unmapped outbuildings) can still pass the gate and "
            "inflate parcel rollups. Screening signal only; not a permit determination."
        ),
    }
    json.dump(doc, open(OUT, "w"), indent=1)
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
