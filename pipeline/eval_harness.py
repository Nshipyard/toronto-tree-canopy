#!/usr/bin/env python3
"""eval_harness.py — SHARED evaluation for all Toronto Tree Canopy experiment arms.

Every arm (RGB baseline, CHM-based, leaf-off RGB v2, canopy-raster proxy) is
scored with the IDENTICAL metric so numbers are comparable:

  - Labels: data/labels/qa{1,3,7}.json, center+diameter in meters from the
    QA tile top-left, converted to [x0,y0,x1,y1] boxes in meters.
  - Predictions: dict tile -> list of [x0m, y0m, x1m, y1m, score],
    same meter-from-top-left frame.
  - Matching: greedy, each gt matched at most once, highest score first.
  - Metric: F1 at IoU 0.5, threshold sweep
    [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]; best-F1 reported.
  - Also reports qa7 alone (the tile held out by the RGB fine-tune).

Usage:
    from eval_harness import load_gt, evaluate
    gt = load_gt(["qa1", "qa3", "qa7"])          # tile -> (N,4) boxes
    result = evaluate(preds, gt, arm_name="chm-watershed", params={...})
    # result["best"]["f1"], result["rows"], result["qa7_only"]["best"]["f1"]

evaluate() writes nothing; callers save result to data/accuracy_<arm>.json.
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

IOU = 0.5
THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
TILES = ["qa1", "qa3", "qa7"]


def load_gt(tiles=TILES):
    """tile -> (N,4) float array of [x0,y0,x1,y1] in meters from tile top-left."""
    gt = {}
    for t in tiles:
        labels = json.load(open(os.path.join(DATA, "labels", f"{t}.json")))["labels"]
        boxes = []
        for L in labels:
            r = L["d_m"] / 2.0
            boxes.append([L["x_m"] - r, L["y_m"] - r, L["x_m"] + r, L["y_m"] + r])
        gt[t] = np.array(boxes, dtype=float)
    return gt


def _iou_matrix(pb, gb):
    N, M = len(pb), len(gb)
    out = np.zeros((N, M))
    for j in range(M):
        xx1 = np.maximum(pb[:, 0], gb[j, 0])
        yy1 = np.maximum(pb[:, 1], gb[j, 1])
        xx2 = np.minimum(pb[:, 2], gb[j, 2])
        yy2 = np.minimum(pb[:, 3], gb[j, 3])
        w = np.maximum(0, xx2 - xx1)
        h = np.maximum(0, yy2 - yy1)
        inter = w * h
        ua = (pb[:, 2] - pb[:, 0]) * (pb[:, 3] - pb[:, 1]) + \
             (gb[j, 2] - gb[j, 0]) * (gb[j, 3] - gb[j, 1]) - inter
        out[:, j] = inter / np.maximum(ua, 1e-9)
    return out


def _sweep(preds, gt):
    """preds: (P,5) [x0,y0,x1,y1,score]; gt: (G,4). Returns rows + best."""
    rows = []
    for th in THRESHOLDS:
        sel = preds[preds[:, 4] >= th] if len(preds) else preds
        pb = sel[:, :4]
        matched = set()
        tp = 0
        if len(pb) and len(gt):
            iou = _iou_matrix(pb, gt)
            for i in np.argsort(-sel[:, 4]):
                j = int(np.argmax(iou[i]))
                if iou[i, j] >= IOU and j not in matched:
                    matched.add(j)
                    tp += 1
        fp = len(pb) - tp
        fn = len(gt) - tp
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        rows.append({"threshold": th, "tp": tp, "fp": fp, "fn": fn,
                     "precision": round(prec, 3), "recall": round(rec, 3),
                     "f1": round(f1, 3)})
    return rows, max(rows, key=lambda r: r["f1"])


def evaluate(preds, gt, arm_name, params=None, vintage="2022"):
    """preds: dict tile -> list of [x0m,y0m,x1m,y1m,score].
    gt: dict tile -> (N,4). Returns the standard result dict."""
    per_tile = {}
    for t, g in gt.items():
        p = np.array(preds.get(t, []), dtype=float).reshape(-1, 5)
        per_tile[t] = {"n_gt": int(len(g)), "n_pred": int(len(p))}
    P = np.vstack([np.array(preds.get(t, []), dtype=float).reshape(-1, 5)
                   for t in gt]) if any(preds.get(t) for t in gt) else np.zeros((0, 5))
    G = np.vstack(list(gt.values()))
    rows, best = _sweep(P, G)

    # qa7 alone: the tile the RGB fine-tune held out; reported for comparability.
    qa7_only = None
    if "qa7" in gt:
        p7 = np.array(preds.get("qa7", []), dtype=float).reshape(-1, 5)
        rows7, best7 = _sweep(p7, gt["qa7"])
        qa7_only = {"rows": rows7, "best": best7,
                    "n_gt": int(len(gt["qa7"])), "n_pred": int(len(p7))}

    return {
        "arm": arm_name,
        "params": params or {},
        "imagery_vintage": vintage,
        "iou": IOU,
        "thresholds": THRESHOLDS,
        "tiles": list(gt.keys()),
        "n_labeled_crowns": int(sum(len(g) for g in gt.values())),
        "per_tile": per_tile,
        "threshold_sweep": rows,
        "best": best,
        "qa7_only": qa7_only,
        "note": ("Greedy matching F1 at IoU 0.5, identical harness for all arms. "
                 "Labels are hand-labeled center+diameter eyeball estimates on "
                 "leaf-off 2022 8cm ortho; not survey-grade."),
    }


if __name__ == "__main__":
    # smoke test: perfect predictions on qa1 should give F1 = 1.0
    gt = load_gt(["qa1"])
    preds = {"qa1": [[b[0], b[1], b[2], b[3], 0.99] for b in gt["qa1"]]}
    r = evaluate(preds, gt, "smoke")
    assert r["best"]["f1"] == 1.0, r["best"]
    # empty predictions -> F1 0
    r2 = evaluate({}, gt, "smoke-empty")
    assert r2["best"]["f1"] == 0.0, r2["best"]
    print("harness smoke test OK; qa1 n_gt =", len(gt["qa1"]))
