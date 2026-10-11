"""Do segment stats separate GT-matching segments from junk? (qa1+qa3 only)."""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.expanduser("~/workspace/toronto-tree-canopy/data/lidar"))
sys.path.insert(0, os.path.expanduser("~/workspace/toronto-tree-canopy/pipeline"))
from detect_armB import tile_chm, detect
from eval_harness import load_gt, _iou_matrix

gt = load_gt(["qa1", "qa3"])
all_segs = []
for tile in ["qa1", "qa3"]:
    chm = tile_chm(tile)
    dets = detect(chm, sigma=0.5, min_dist=2, peak_h=2.0, floor=1.0,
                  rough_thresh=0.0, big_area=0.0, big_rough=0.0)  # no suppression
    gb = gt[tile]
    pb = np.array([[d[0], d[1], d[2], d[3]] for d in dets]) if dets else np.zeros((0, 4))
    iou = _iou_matrix(pb, gb) if len(pb) else np.zeros((0, len(gb)))
    best_iou = iou.max(axis=1) if len(pb) else []
    for d, bi in zip(dets, best_iou):
        all_segs.append((bi, d[4], d[5], d[6]))  # iou, hmax, area, rough

good = [s for s in all_segs if s[0] >= 0.5]
bad = [s for s in all_segs if s[0] < 0.2]
print(f"n segments={len(all_segs)}, good(IoU>=0.5)={len(good)}, bad(IoU<0.2)={len(bad)}")
for name, arr, idx in [("hmax", None, 1), ("area", None, 2), ("rough", None, 3)]:
    g = np.array([s[idx] for s in good]); b = np.array([s[idx] for s in bad])
    if len(g):
        print(f"{name}: good median={np.median(g):.2f} p25/75={np.percentile(g,25):.2f}/{np.percentile(g,75):.2f} | "
              f"bad median={np.median(b):.2f} p25/75={np.percentile(b,25):.2f}/{np.percentile(b,75):.2f}")
    else:
        print(f"{name}: NO good segments at all")
# GT crown diameter distribution
ds = []
for t in ["qa1", "qa3"]:
    for L in json.load(open(os.path.expanduser(f"~/workspace/toronto-tree-canopy/data/labels/{t}.json")))["labels"]:
        ds.append(L["d_m"])
ds = np.array(ds)
print(f"GT diameter: n={len(ds)} median={np.median(ds):.1f}m p25/75={np.percentile(ds,25):.1f}/{np.percentile(ds,75):.1f}")
