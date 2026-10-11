#!/usr/bin/env python3
"""finetune.py — light fine-tune of DeepForest on hand-labeled Toronto tiles.

Why: the pre-trained (leaf-on NEON) model scores F1 ~0.05 on Toronto's
leaf-off spring 2022 ortho (measured in 03_evaluate.py). This fine-tunes the
full RetinaNet on 118 hand-labeled crowns (qa1+qa3, 8cm, 400px chips),
holding out qa7 (64 crowns) for evaluation.

Outputs: data/weights/model_finetuned.pt (state dict)
         data/ft_train/, data/ft_val/ (chips + CSVs)
"""
import csv, json, os, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
from df_model import load_model

CHIP = 400
STRIDE = 300
TRAIN_TILES = ["qa1", "qa3"]
VAL_TILES = ["qa7"]

def build_chips(tiles, out_img_dir, csv_path):
    os.makedirs(out_img_dir, exist_ok=True)
    rows = []
    n_chips = 0
    for t in tiles:
        meta = json.load(open(os.path.join(DATA, "qa-tiles", f"{t}.json")))
        gsd = meta["gsd_m"]
        im = Image.open(os.path.join(DATA, "qa-tiles", f"{t}.png")).convert("RGB")
        W, H = im.size
        labels = json.load(open(os.path.join(DATA, "labels", f"{t}.json")))["labels"]
        # label boxes in tile pixels
        boxes = []
        for L in labels:
            cx, cy, d = L["x_m"]/gsd, L["y_m"]/gsd, L["d_m"]/gsd
            boxes.append([cx-d/2, cy-d/2, cx+d/2, cy+d/2])
        for yy in range(0, H-CHIP+1, STRIDE):
            for xx in range(0, W-CHIP+1, STRIDE):
                chip = im.crop((xx, yy, xx+CHIP, yy+CHIP))
                name = f"{t}_{xx}_{yy}.png"
                chip.save(os.path.join(out_img_dir, name))
                n_chips += 1
                for b in boxes:
                    x0 = max(b[0]-xx, 0); y0 = max(b[1]-yy, 0)
                    x1 = min(b[2]-xx, CHIP); y1 = min(b[3]-yy, CHIP)
                    if x1-x0 < 15 or y1-y0 < 15:
                        continue
                    orig_area = (b[2]-b[0])*(b[3]-b[1])
                    if (x1-x0)*(y1-y0) < 0.3*orig_area:
                        continue
                    rows.append([name, round(x0,1), round(y0,1), round(x1,1), round(y1,1), "Tree"])
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image_path","xmin","ymin","xmax","ymax","label"])
        w.writerows(rows)
    print(f"{csv_path}: {n_chips} chips, {len(rows)} boxes")

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--lr", type=float, default=0.0005)
    args = ap.parse_args()

    build_chips(TRAIN_TILES, os.path.join(DATA, "ft_train"), os.path.join(DATA, "ft_train.csv"))
    build_chips(VAL_TILES, os.path.join(DATA, "ft_val"), os.path.join(DATA, "ft_val.csv"))

    print("loading base model...", flush=True)
    m = load_model(score_thresh=0.15)
    m.config.train.csv_file = os.path.join(DATA, "ft_train.csv")
    m.config.train.root_dir = os.path.join(DATA, "ft_train")
    m.config.validation.csv_file = os.path.join(DATA, "ft_val.csv")
    m.config.validation.root_dir = os.path.join(DATA, "ft_val")
    m.config.train.epochs = args.epochs
    m.config.train.lr = args.lr
    m.config.devices = 1
    m.config.accelerator = "cpu"
    m.config.workers = 0
    m.config.train.fast_dev_run = False
    m.create_trainer()
    print(f"training {args.epochs} epochs, lr={args.lr} ...", flush=True)
    m.trainer.fit(m)
    out = os.path.join(DATA, "weights", "model_finetuned.pt")
    import torch
    torch.save(m.model.state_dict(), out)
    print(f"saved -> {out}")

if __name__ == "__main__":
    main()
