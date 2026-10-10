"""Arm B final: detection params picked on qa1+qa3 ONLY, applied to qa1/qa3/qa7,
eval with the shared harness, save data/accuracy_armB_chm.json, render preview PNG."""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

ROOT = os.path.expanduser("~/workspace/toronto-tree-canopy")
sys.path.insert(0, os.path.join(ROOT, "data", "lidar"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from detect_armB import tile_chm, detect, boxes_with_scores
from eval_harness import load_gt, evaluate

# Params from the qa1+qa3 grid search (grid_qa13.json), qa7 untouched in tuning.
PARAMS = dict(sigma=0.5, min_dist=2, floor=1.5, peak_h=2.5,
              rough_thresh=0.5, max_area=120.0, big_area=400.0, big_rough=0.5)

tiles = ["qa1", "qa3", "qa7"]
preds, cand = {}, {}
for t in tiles:
    chm = tile_chm(t)
    dets = detect(chm, **PARAMS)
    preds[t] = boxes_with_scores(dets)
    cand[t] = len(dets)
print("per-tile candidate counts:", cand)

gt = load_gt(tiles)
res = evaluate(preds, gt, arm_name="chm-watershed",
               params={**PARAMS, "score": "segment max CHM, min-max normalized to [0,1] per tile"},
               vintage="2023")
print("best overall:", res["best"])
print("qa7 only best:", res["qa7_only"]["best"])

res["method"] = {
    "data_source": "NRCan HRDEM Mosaic WCS (https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic), "
                   "DSM + DTM coverages, Open Government Licence - Canada",
    "vintage": "2023 (TRCA GTA_2023 airborne LiDAR ingested into federal mosaic)",
    "nominal_resolution": "1 m (WCS serves EPSG:4326 at 1.3216e-05 deg; reprojected to EPSG:3857 at 1.0 m square pixels)",
    "fetch_window": "lon -79.455..-79.405, lat 43.665..43.69; 16 WCS chunks (4x2 per layer, ~0.0125 deg each); "
                    "scripts data/lidar/fetch_qa_cover.py, build_qa_chm.py; CHM = DSM - DTM, clipped [-2, 60] m",
    "smoothing_sigma_m": PARAMS["sigma"],
    "min_separation_m": PARAMS["min_dist"],
    "min_peak_height_m": PARAMS["peak_h"],
    "watershed_height_floor_m": PARAMS["floor"],
    "roughness_rule": ("drop segments with mean local CHM std (5x5 m window) < %.2f m; "
                       "additionally drop segments > %.0f m^2 with roughness < %.2f; "
                       "also drop any segment > %.0f m^2 (merged house/tree blobs). "
                       "Thresholds picked by grid search on qa1+qa3 F1; qa7 untouched." %
                       (PARAMS["rough_thresh"], PARAMS["big_area"], PARAMS["big_rough"], PARAMS["max_area"])),
    "box_construction": "axis-aligned bbox of the surviving watershed segment, meters from tile top-left (row 0 = tile top)",
    "score_definition": "segment max CHM, min-max normalized to [0,1] per tile",
}
res["baselines_for_comparison"] = {
    "rgb_pretrained_at_production_gsd": 0.023,
    "rgb_finetuned_at_production_gsd": 0.000,
    "note": "Identical harness (IoU 0.5, greedy matching, threshold sweep); production GSD for RGB arms.",
}
res["caveats"] = ("CHM is 2023 leaf-on airborne LiDAR at 1 m; labels are hand-labeled "
    "center+diameter eyeball estimates on leaf-off 2022 8 cm ortho. qa1/qa3 are dense "
    "residential (median labeled-crown max CHM 9 m); qa7 is mature canopy (median 22.4 m).")

out = os.path.join(ROOT, "data", "accuracy_armB_chm.json")
with open(out, "w") as f:
    json.dump(res, f, indent=1)
print("wrote", out)

# Side-by-side preview PNG for qa7 (held-out tile): CHM + detected boxes.
t = "qa7"
chm = tile_chm(t)
cmap = LinearSegmentedColormap.from_list("chm", ["#f5f5f5", "#a6d96a", "#1a9850", "#006837"])
c = np.clip(chm, 0, 25)
fig, ax = plt.subplots(figsize=(9, 9))
ax.imshow(c, cmap=cmap, vmin=0, vmax=25, interpolation="nearest")
for b in preds[t]:
    ax.add_patch(Rectangle((b[0], b[1]), b[2]-b[0], b[3]-b[1],
                           fill=False, edgecolor="red", lw=1.2))
ax.set_title(f"qa7 (held-out): 1 m CHM + {len(preds[t])} detected crown boxes (red)")
ax.axis("off")
png = os.path.join(ROOT, "data", "lidar", "qa_cover", "qa_preview.png")
plt.savefig(png, dpi=110, bbox_inches="tight")
print("wrote", png)
