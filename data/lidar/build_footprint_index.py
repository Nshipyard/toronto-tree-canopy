"""One-time: build a bbox+offset index over the City building footprints GeoJSON.

The 414 MB building_outlines_4326.geojson holds 557,694 feature lines. Scanning
+ json-parsing all of them per ward (25x) is wasteful; this builds a compact
index once: per-feature bbox (float32) and byte offset (int64) into the file,
so a ward run can vector-select candidate footprints and seek+parse only those.

Output (gitignored): data/lidar/raw/footprint_index.npz
Run: .venv/bin/python3 data/lidar/build_footprint_index.py
"""
import json
import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
GEOJSON = os.path.join(HERE, "raw", "building_outlines_4326.geojson")
OUT = os.path.join(HERE, "raw", "footprint_index.npz")

# fast bbox pre-scan: pull the coordinate runs out of the raw line text.
# Feature lines look like: { "type": "Feature", "properties": {...},
#   "geometry": { "type": "Polygon", "coordinates": [ [ [lon,lat], ... ] ] } }
# The coordinates array is the tail of the line; scan float pairs there.
COORD_RE = re.compile(r"\[\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*\]")


def main():
    bboxes = []
    offsets = []
    n_feat = 0
    with open(GEOJSON, "rb") as fh:
        while True:
            off = fh.tell()
            line = fh.readline()
            if not line:
                break
            if not line.startswith(b'{ "type": "Feature"'):
                continue
            n_feat += 1
            # bbox from the coordinate pairs in the raw text (no json parse)
            txt = line.decode("utf-8", "ignore")
            gi = txt.find('"geometry"')
            seg = txt[gi:] if gi >= 0 else txt
            xs, ys = [], []
            for m in COORD_RE.finditer(seg):
                xs.append(float(m.group(1)))
                ys.append(float(m.group(2)))
            if not xs:
                continue
            bboxes.append((min(xs), min(ys), max(xs), max(ys)))
            offsets.append(off)
            if n_feat % 100000 == 0:
                print(f"  {n_feat} features indexed", flush=True)
    bboxes = np.array(bboxes, dtype="float32")
    offsets = np.array(offsets, dtype="int64")
    np.savez_compressed(OUT, bboxes=bboxes, offsets=offsets)
    print(f"indexed {len(bboxes)} footprints -> {OUT}", flush=True)
    print(f"bbox range lon {bboxes[:,0].min():.4f}..{bboxes[:,2].max():.4f} "
          f"lat {bboxes[:,1].min():.4f}..{bboxes[:,3].max():.4f}", flush=True)


if __name__ == "__main__":
    main()
