#!/usr/bin/env python3
"""02_inference.py — DeepForest crown detection on exported ortho tiles.

Loads the pre-trained DeepForest RetinaNet (NEON release weights, NOT fine-tuned
on Toronto; see METHOD_NOTES.md), runs predict_tile on each exported tile,
applies a global per-tile NMS, and writes detected crowns with 3857 coords.

Usage: python3 02_inference.py [--score 0.15] [--patch 400] [--overlap 0.25]
Outputs: data/crowns_ward12.json
"""
import argparse, json, os, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from df_model import load_model

def nms(boxes, scores, iou_thresh=0.5):
    """Greedy NMS. boxes: (N,4) xmin,ymin,xmax,ymax."""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:,0], boxes[:,1], boxes[:,2], boxes[:,3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= iou_thresh]
    return keep

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", type=float, default=0.15, help="score threshold (deepforest default 0.15)")
    ap.add_argument("--patch", type=int, default=400)
    ap.add_argument("--overlap", type=float, default=0.25)
    ap.add_argument("--nms-iou", type=float, default=0.5)
    ap.add_argument("--tiles-json", default=os.path.join(ROOT, "data", "tiles.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "crowns_ward12.json"))
    ap.add_argument("--weights", default=None,
                    help="weights file; default = pre-trained release safetensors")
    args = ap.parse_args()

    print("loading DeepForest model (pre-trained release weights, local file)...", flush=True)
    model = load_model(score_thresh=args.score, nms_thresh=args.nms_iou,
                       **({"weights_path": args.weights} if args.weights else {}))
    print("model ready", flush=True)

    tiles = json.load(open(args.tiles_json))["tiles"]
    crowns = []
    cid = 0
    for t in tiles:
        img = Image.open(t["path"])
        if img.mode != "RGB":
            img = img.convert("RGB")
        W, H = img.size
        arr = np.array(img)[:, :, ::-1]  # deepforest predict_tile expects BGR
        boxes = model.predict_tile(image=arr, patch_size=args.patch,
                                   patch_overlap=args.overlap,
                                   iou_threshold=args.nms_iou)
        if boxes is None or len(boxes) == 0:
            print(f"  {t['name']}: 0 boxes", flush=True)
            continue
        b = boxes[["xmin","ymin","xmax","ymax"]].to_numpy(dtype=float)
        s = boxes["score"].to_numpy(dtype=float)
        keep = nms(b, s, args.nms_iou)
        x0, y0, x1, y1 = t["bbox_3857"]
        gsd = t["gsd_m"]
        for k in keep:
            xmin, ymin, xmax, ymax = b[k]
            wx0 = x0 + xmin * gsd; wy1 = y1 - ymin * gsd
            wx1 = x0 + xmax * gsd; wy0 = y1 - ymin * gsd
            w_m, h_m = (xmax - xmin) * gsd, (ymax - ymin) * gsd
            crowns.append({
                "id": f"c{cid}", "tile": t["name"], "score": float(s[k]),
                "bbox_3857": [wx0, wy0, wx1, wy1],
                "cx_3857": (wx0+wx1)/2, "cy_3857": (wy0+wy1)/2,
                "crown_diameter_m": float((w_m*h_m) ** 0.5),
                "width_m": float(w_m), "height_m": float(h_m),
            })
            cid += 1
        print(f"  {t['name']}: {len(keep)} crowns (raw {len(b)})", flush=True)

    json.dump({"crowns": crowns, "score_threshold": args.score,
               "patch_size": args.patch, "patch_overlap": args.overlap,
               "nms_iou": args.nms_iou,
               "model": "deepforest 2.1.0 pre-trained NEON release weights (no Toronto fine-tuning)"},
              open(args.out, "w"))
    print(f"wrote {len(crowns)} crowns -> {args.out}")

if __name__ == "__main__":
    main()
