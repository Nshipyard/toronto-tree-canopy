"""Diagnostic: CHM crop + detected boxes + GT boxes for qa1/qa3."""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

sys.path.insert(0, os.path.expanduser("~/workspace/toronto-tree-canopy/data/lidar"))
from detect_armB import tile_chm, detect, boxes_with_scores
sys.path.insert(0, os.path.expanduser("~/workspace/toronto-tree-canopy/pipeline"))
from eval_harness import load_gt

W = os.path.expanduser("~/workspace/toronto-tree-canopy/data/lidar/qa_cover")
gt = load_gt(["qa1", "qa3"])

for tile in ["qa1", "qa3"]:
    chm = tile_chm(tile)
    print(tile, "CHM shape", chm.shape, "nan%", np.isnan(chm).mean()*100,
          "median", np.nanmedian(chm), "p90", np.nanpercentile(chm, 90),
          "max", np.nanmax(chm))
    dets = detect(chm, floor=1.5, peak_h=2.5, rough_thresh=0.5, big_area=400.0, big_rough=0.5)
    print(tile, "detections:", len(dets))
    for d in dets[:10]:
        print(f"  box=({d[0]:.0f},{d[1]:.0f},{d[2]:.0f},{d[3]:.0f}) hmax={d[4]:.1f} area={d[5]:.0f} rough={d[6]:.2f}")
    preds = boxes_with_scores(dets)
    cmap = LinearSegmentedColormap.from_list("chm", ["#f5f5f5", "#a6d96a", "#1a9850", "#006837"])
    c = np.clip(chm, 0, 25)
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.imshow(c, cmap=cmap, vmin=0, vmax=25, interpolation="nearest")
    for b in preds:
        ax.add_patch(Rectangle((b[0], b[1]), b[2]-b[0], b[3]-b[1],
                               fill=False, edgecolor="red", lw=1.2))
    for b in gt[tile]:
        ax.add_patch(Rectangle((b[0], b[1]), b[2]-b[0], b[3]-b[1],
                               fill=False, edgecolor="cyan", lw=1.2))
    ax.set_title(f"{tile}: CHM 1m + preds (red) + GT (cyan)")
    ax.axis("off")
    plt.savefig(os.path.join(W, f"diag_{tile}.png"), dpi=110, bbox_inches="tight")
    print("wrote", os.path.join(W, f"diag_{tile}.png"))
