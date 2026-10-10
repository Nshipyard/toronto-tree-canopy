#!/usr/bin/env python3
"""Track A final: param grid on qa1+qa3 ONLY, then final eval incl. held-out qa7.

Usage: python tracka_final.py grid    -> params picked on qa1+qa3, saved tracka/grid_qa13.json
       python tracka_final.py final   -> apply best, eval, write data/accuracy_tracka.json + preview PNG
"""
import itertools, json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

ROOT = os.path.expanduser("~/workspace/toronto-tree-canopy")
sys.path.insert(0, os.path.join(ROOT, "data", "lidar"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from tracka_detect import tile_chm_window, region_grow, boxes_with_scores, OUT, CHM_RES
from eval_harness import load_gt, evaluate


def detect_tile(tile, res, **kw):
    chm = tile_chm_window(tile, res)
    dets = region_grow(chm, res=res, **kw)
    return boxes_with_scores(dets)


def f1_on(preds, tiles):
    gt = load_gt(list(tiles))
    return evaluate(preds, gt, arm_name="tracka-fine-chm")["best"]["f1"]


def grid():
    from tracka_gt_corrected import load_gt_corrected
    res = CHM_RES
    chms = {t: tile_chm_window(t, res) for t in ["qa1", "qa3"]}
    keys = ["sigma", "min_dist", "peak_h", "floor", "max_radius", "min_area"]
    space = {
        "sigma": [0.3, 0.5, 0.75],
        "min_dist": [2.0, 2.5, 3.0],
        "peak_h": [2.0, 2.5, 3.0],
        "floor": [1.0, 1.5, 2.0],
        "max_radius": [2.0, 2.5, 3.0, 3.5, 4.0],
        "min_area": [2.0, 3.0, 5.0],
    }
    gt = load_gt_corrected(["qa1", "qa3"])
    rows = []
    for vals in itertools.product(*[space[k] for k in keys]):
        kw = dict(zip(keys, vals))
        preds = {t: boxes_with_scores(region_grow(chms[t], res=res, **kw))
                 for t in ["qa1", "qa3"]}
        r = evaluate(preds, gt, arm_name="tracka-grid")
        f1 = r["best"]["f1"]
        n = sum(len(v) for v in preds.values())
        rows.append({"f1": round(f1, 4), "n_pred": n, **{k: v for k, v in kw.items()}})
    rows.sort(key=lambda r: -r["f1"])
    print("CORRECTED labels grid (qa1+qa3), region growing")
    print("f1     n   " + " ".join(f"{k:>10}" for k in keys))
    for r in rows[:12]:
        print(f"{r['f1']:.4f} {r['n_pred']:>3} " +
              " ".join(f"{r[k]:>10}" for k in keys))
    json.dump({"res_m": res, "grid": rows,
               "note": "tuned on CORRECTED labels (real trees); qa7 held out"},
              open(os.path.join(OUT, "grid_qa13.json"), "w"), indent=1)
    best = rows[0]
    print("BEST:", {k: best[k] for k in keys})
    return {k: best[k] for k in keys}


def final(params, res):
    from tracka_gt_corrected import load_gt_corrected
    tiles = ["qa1", "qa3", "qa7"]
    preds = {}
    for t in tiles:
        preds[t] = detect_tile(t, res, **params)
        print(t, "detections:", len(preds[t]))
    gt = load_gt_corrected(tiles)
    r = evaluate(preds, gt, arm_name="tracka-fine-chm-regiongrow",
                 params={**params, "res_m": res,
                         "score": "segment max CHM, min-max normalized to [0,1] per tile",
                         "labels": "CORRECTED (real trees, not grid cells)"},
                 vintage="2023")
    print("best overall:", r["best"])
    print("qa7 only best:", r["qa7_only"]["best"])
    r["method"] = {
        "data_source": ("NRCan CanElevation LiDAR Point Clouds S3 "
            "(https://canelevation-lidar-point-clouds.s3.ca-central-1.amazonaws.com), "
            "supplier TRCA, project GTA_2023, 20230511 capture, Open Government Licence - Canada"),
        "point_density": "measured 27.69 pts/m2 on E6250_N48370 tile (27,148,876 pts / 980,635 m2)",
        "classification": ("vendor-classified: ground(2), building(6), unassigned(1), "
            "low point(7), high noise(18); NO vegetation classes -> buildings dropped from DSM, "
            "vegetation arrives via unassigned class 1"),
        "building_mask": ("City of Toronto 'Topographic Mapping - Building Outlines' "
            "(CKAN 09a930cc..., 557,694 outlines, DERIVED_HEIGHT from LiDAR), rasterized "
            "at 0.5 m with 2 m buffer; masked to nan in CHM BEFORE segmentation. "
            "Double defense: class-6 points also excluded from DSM."),
        "dtm": "NRCan HRDEM 1 m DTM (WCS, validated flat-ground median 0.06 m), bilinear resample to 0.5 m",
        "dsm": "fine max-Z scatter of class-1/vegetation points at 0.5 m (~6.9 pts/cell)",
        "chm": "DSM - DTM, clipped [-2, 60] m, EPSG:26917",
        "segmentation": ("classical Dalponte-style seeded region growing: Gaussian smooth -> "
            "local-maxima treetops (tallest first) -> grow to 8-neighbors only downhill, "
            "above floor, within max_radius, unclaimed. Stops at valleys between crowns; "
            "this fixes the marker-watershed failure mode (segments leaking across "
            "shallow valleys into grove-sized blobs)."),
        "labels": ("CORRECTED labels (data/labels_corrected/): the shared data/labels "
            "are 8x8 grid cells, not crowns (proven in TRACKA_REPORT.md); corrected "
            "labels are real trees verified against the 8 cm ortho. qa7 HELD OUT of tuning."),
        "box_construction": "axis-aligned bbox of surviving watershed segment, meters from tile top-left",
    }
    r["baselines_for_comparison"] = {
        "rgb_pretrained_at_production_gsd": 0.023,
        "chm_watershed_1m": 0.046,
        "note": "Identical harness (IoU 0.5, greedy matching, threshold sweep). qa7 HELD OUT of tuning.",
    }
    out = os.path.join(ROOT, "data", "accuracy_tracka.json")
    json.dump(r, open(out, "w"), indent=1)
    print("wrote", out)

    # preview PNG on held-out qa7
    chm = tile_chm_window("qa7", res)
    cmap = LinearSegmentedColormap.from_list("chm", ["#f5f5f5", "#a6d96a", "#1a9850", "#006837"])
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.imshow(np.clip(chm, 0, 25), cmap=cmap, vmin=0, vmax=25, interpolation="nearest")
    for b in preds["qa7"]:
        ax.add_patch(Rectangle((b[0] / res, b[1] / res),
                               (b[2] - b[0]) / res, (b[3] - b[1]) / res,
                               fill=False, edgecolor="red", lw=1.2))
    ax.set_title(f"qa7 (held-out): fine 0.5 m CHM + {len(preds['qa7'])} detected crown boxes")
    ax.axis("off")
    png = os.path.join(OUT, "qa7_preview.png")
    plt.savefig(png, dpi=110, bbox_inches="tight")
    print("wrote", png)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "grid"
    if mode == "grid":
        grid()
    else:
        g = json.load(open(os.path.join(OUT, "grid_qa13.json")))
        keys = ["sigma", "min_dist", "peak_h", "floor", "max_radius", "min_area"]
        params = {k: g["grid"][0][k] for k in keys}
        print("using params:", params, "res:", g["res_m"])
        final(params, g["res_m"])
