#!/usr/bin/env python3
"""03_evaluate.py — detection F1 of DeepForest vs hand labels on QA tiles.

Runs inference on each QA tile downsampled to the production GSD (0.40 m),
converts hand labels (center+diameter, meters from tile top-left) to boxes,
and computes precision/recall/F1 at IoU 0.5 across score thresholds.

Outputs: data/accuracy_detection.json
"""
import json, os, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
from df_model import load_model
import importlib.util
spec = importlib.util.spec_from_file_location("inf", os.path.join(HERE, "02_inference.py"))
inf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inf)

IOU = 0.5

def iou_matrix(pb, gb):
    """pb: (N,4), gb: (M,4) in same units -> (N,M) IoU."""
    N, M = len(pb), len(gb)
    out = np.zeros((N, M))
    for j in range(M):
        xx1 = np.maximum(pb[:,0], gb[j,0]); yy1 = np.maximum(pb[:,1], gb[j,1])
        xx2 = np.minimum(pb[:,2], gb[j,2]); yy2 = np.minimum(pb[:,3], gb[j,3])
        w = np.maximum(0, xx2-xx1); h = np.maximum(0, yy2-yy1)
        inter = w*h
        ua = (pb[:,2]-pb[:,0])*(pb[:,3]-pb[:,1]) + (gb[j,2]-gb[j,0])*(gb[j,3]-gb[j,1]) - inter
        out[:,j] = inter/np.maximum(ua, 1e-9)
    return out

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=None)
    ap.add_argument("--gsd", type=float, default=0.40)
    ap.add_argument("--tiles", default="qa1,qa3,qa7")
    ap.add_argument("--out", default=os.path.join(DATA, "accuracy_detection.json"))
    a = ap.parse_args()
    GSD = a.gsd
    model = load_model(score_thresh=0.05,
                       **({"weights_path": a.weights} if a.weights else {}))  # keep everything; threshold in eval
    tiles = a.tiles.split(",")
    all_pred, all_gt = [], []
    per_tile = {}
    for t in tiles:
        meta = json.load(open(os.path.join(DATA, "qa-tiles", f"{t}.json")))
        im = Image.open(os.path.join(DATA, "qa-tiles", f"{t}.png")).convert("RGB")
        scale = meta["gsd_m"] / GSD
        small = im.resize((int(im.size[0]*scale), int(im.size[1]*scale)), Image.BILINEAR)
        arr = np.array(small)  # RGB: empirically better than BGR here
        boxes = model.predict_tile(image=arr, patch_size=400, patch_overlap=0.25,
                                   iou_threshold=0.5)
        preds = []
        if boxes is not None and len(boxes):
            b = boxes[["xmin","ymin","xmax","ymax"]].to_numpy(float) / scale  # back to 8cm px
            s = boxes["score"].to_numpy(float)
            keep = inf.nms(b, s, 0.5)
            for k in keep:
                # convert to meters from tile top-left
                x0m = b[k][0]*meta["gsd_m"]; y0m = b[k][1]*meta["gsd_m"]
                x1m = b[k][2]*meta["gsd_m"]; y1m = b[k][3]*meta["gsd_m"]
                preds.append([x0m, y0m, x1m, y1m, float(s[k])])
        labels = json.load(open(os.path.join(DATA, "labels", f"{t}.json")))["labels"]
        gt = []
        for L in labels:
            r = L["d_m"]/2
            gt.append([L["x_m"]-r, L["y_m"]-r, L["x_m"]+r, L["y_m"]+r])
        all_pred.append(np.array(preds)); all_gt.append(np.array(gt))
        per_tile[t] = {"n_gt": len(gt), "n_pred": len(preds)}
        print(f"{t}: gt={len(gt)} pred={len(preds)}", flush=True)

    # F1 across score thresholds (greedy matching, each gt matched once)
    P = np.vstack(all_pred) if any(len(p) for p in all_pred) else np.zeros((0,5))
    G = np.vstack(all_gt)
    thresholds = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
    rows = []
    for th in thresholds:
        sel = P[P[:,4] >= th] if len(P) else P
        pb = sel[:,:4]
        matched_gt = set(); tp = 0
        if len(pb) and len(G):
            iou = iou_matrix(pb, G)
            order = np.argsort(-sel[:,4])
            for i in order:
                j = int(np.argmax(iou[i]))
                if iou[i,j] >= IOU and j not in matched_gt:
                    matched_gt.add(j); tp += 1
        fp = len(pb) - tp; fn = len(G) - tp
        prec = tp/max(tp+fp,1); rec = tp/max(tp+fn,1)
        f1 = 2*prec*rec/max(prec+rec,1e-9)
        rows.append({"threshold": th, "tp": tp, "fp": fp, "fn": fn,
                     "precision": round(prec,3), "recall": round(rec,3),
                     "f1": round(f1,3)})
        print(f"thr={th}: P={prec:.3f} R={rec:.3f} F1={f1:.3f} (tp={tp} fp={fp} fn={fn})")
    best = max(rows, key=lambda r: r["f1"])
    out = {"imagery_vintage": "2022", "gsd_m": GSD, "iou": IOU,
           "model": ("deepforest 2.1.0 fine-tuned on 118 hand-labeled Toronto crowns "
                     "(qa1+qa3, leaf-off 2022 ortho)" if a.weights else
                     "deepforest 2.1.0 pre-trained NEON release weights (weecology/deepforest-tree); NO Toronto fine-tuning"),
           "n_labeled_crowns": int(sum(len(g) for g in all_gt)),
           "n_qa_tiles": len(tiles),
           "label_method": "hand-labeled center+diameter eyeball estimates on 8cm ortho by visual inspection",
           "threshold_sweep": rows,
           "best": best,
           "note": ("Imagery is leaf-off (early spring 2022); model trained on leaf-on "
                    "NEON data. Labels are eyeball estimates, not survey-grade.")}
    json.dump(out, open(a.out, "w"), indent=1)
    print("best:", best)

if __name__ == "__main__":
    main()
