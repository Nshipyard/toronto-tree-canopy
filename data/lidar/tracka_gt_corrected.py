#!/usr/bin/env python3
"""Load CORRECTED labels (data/labels_corrected/qa{1,3,7}.json) in harness format.

The original data/labels/qa{1,3,7}.json are 8x8 grid cells, not crowns
(proven in data/TRACKA_REPORT.md). These corrected labels are real trees,
verified one-by-one against the 8 cm ortho.
"""
import json, os
import numpy as np

ROOT = os.path.expanduser("~/workspace/toronto-tree-canopy")
CORR = os.path.join(ROOT, "data", "labels_corrected")


def load_gt_corrected(tiles=("qa1", "qa3", "qa7")):
    gt = {}
    for t in tiles:
        d = json.load(open(os.path.join(CORR, f"{t}.json")))
        boxes = []
        for L in d["labels"]:
            r = L["d_m"] / 2.0
            boxes.append([L["x_m"] - r, L["y_m"] - r, L["x_m"] + r, L["y_m"] + r])
        gt[t] = np.array(boxes, dtype=float)
    return gt
