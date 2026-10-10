#!/usr/bin/env python3
"""Prepare corrected-label verification sheets for a QA tile.

Builds the unmasked fine CHM (if missing), extracts CHM treetop candidates,
renders a contact sheet of ortho crops for one-by-one verification.
Usage: python label_prep.py qa3
"""
import sys, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
from scipy.ndimage import gaussian_filter
from skimage.feature import peak_local_max

ROOT = os.path.expanduser("~/workspace/toronto-tree-canopy")
sys.path.insert(0, os.path.join(ROOT, "data", "lidar"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from tracka_detect import tile_chm_window, build_chm, OUT, CHM_RES


def main(tile):
    path = os.path.join(OUT, f"chm_{tile}_{int(CHM_RES*100)}cm_3857.tif")
    if not os.path.exists(path):
        print("building unmasked CHM for", tile)
        build_chm(tile, mask_buildings=False)
    chm = tile_chm_window(tile)
    s = gaussian_filter(np.nan_to_num(chm, nan=0.0), 1.0)
    peaks = peak_local_max(s, min_distance=4, threshold_abs=2.0, exclude_border=False)
    print(tile, "candidates:", len(peaks))
    np.savetxt(os.path.join(OUT, f"label_{tile}_candidates.csv"),
               np.column_stack([np.arange(len(peaks)),
                                peaks[:, 1] / chm.shape[1] * 80,
                                peaks[:, 0] / chm.shape[0] * 80]),
               fmt=['%d', '%.1f', '%.1f'], header='id,x_m,y_m', delimiter=',',
               comments='')
    ortho = np.asarray(Image.open(
        os.path.join(ROOT, "data", "qa-tiles", f"{tile}.png")).convert("RGB"))
    Hh, Ww = chm.shape
    sy, sx = ortho.shape[0] / Hh, ortho.shape[1] / Ww
    n = len(peaks); cols = 6; rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(3 * cols, 3.2 * rows))
    crop = 150
    for k, (r, c) in enumerate(peaks):
        ax = axes[k // cols, k % cols] if rows > 1 else axes[k % cols]
        x, y = int(c * sx), int(r * sy)
        x0, x1 = max(0, x - crop // 2), min(ortho.shape[1], x + crop // 2)
        y0, y1 = max(0, y - crop // 2), min(ortho.shape[0], y + crop // 2)
        ax.imshow(ortho[y0:y1, x0:x1])
        ax.plot(x - x0, y - y0, 'r+', ms=14, mew=2)
        ax.set_title(f"#{k} h={float(chm[r, c]):.1f}m", fontsize=10,
                     color='yellow', backgroundcolor='black')
        ax.axis("off")
    for k in range(n, rows * cols):
        a = axes[k // cols, k % cols] if rows > 1 else axes[k % cols]
        a.axis("off")
    plt.suptitle(f"{tile} candidates: ortho 12m crops, red + = CHM peak", fontsize=14)
    plt.tight_layout()
    out = os.path.join(OUT, f"label_{tile}_verify.png")
    plt.savefig(out, dpi=90, bbox_inches="tight")
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1])
