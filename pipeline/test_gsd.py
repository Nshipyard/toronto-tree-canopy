#!/usr/bin/env python3
"""Quick test: run DeepForest on qa3 downsampled to 20cm and 40cm; save box overlays."""
import json, os, sys, time
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from df_model import load_model
import importlib.util
spec = importlib.util.spec_from_file_location("inf", os.path.join(HERE, "02_inference.py"))
inf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inf)

print("loading model...", flush=True)
model = load_model(score_thresh=0.15)

QA = os.path.join(ROOT, "data", "qa-tiles", "qa3.png")
im = Image.open(QA).convert("RGB")
meta = json.load(open(os.path.join(ROOT, "data", "qa-tiles", "qa3.json")))
gsd8 = meta["gsd_m"]

for target_gsd, tag in [(0.20, "20cm"), (0.40, "40cm")]:
    scale = gsd8 / target_gsd
    w, h = int(im.size[0]*scale), int(im.size[1]*scale)
    small = im.resize((w, h), Image.BILINEAR)
    arr = np.array(small)[:, :, ::-1]  # BGR
    t0 = time.time()
    boxes = model.predict_tile(image=arr, patch_size=400, patch_overlap=0.25,
                               iou_threshold=0.5)
    dt = time.time() - t0
    n_raw = 0 if boxes is None else len(boxes)
    keep = []
    b = None
    if n_raw:
        b = boxes[["xmin","ymin","xmax","ymax"]].to_numpy(float)
        s = boxes["score"].to_numpy(float)
        keep = inf.nms(b, s, 0.5)
    vis = im.copy()
    dr = ImageDraw.Draw(vis)
    if b is not None:
        for k in keep:
            xmin, ymin, xmax, ymax = b[k] / scale
            dr.rectangle([xmin, ymin, xmax, ymax], outline=(255,0,0), width=3)
    vis.save(os.path.join(ROOT, "data", "qa-tiles", f"qa3_pred_{tag}.png"))
    scores = sorted([float(x) for x in boxes["score"]], reverse=True)[:8] if n_raw else []
    print(f"{tag}: raw={n_raw} kept={len(keep)} time={dt:.1f}s top_scores={scores}", flush=True)
