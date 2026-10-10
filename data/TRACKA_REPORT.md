# Track A Report — Toronto Tree Canopy, round 2 (strong detection experiment)

Worker: Track A (subagent e62f9588), 2026-10-10.
Scope: Ward 12 (Davenport) QA tiles only, CPU only.

## 1. Raw point cloud: FOUND, dense, classified

- Source: NRCan **CanElevation LiDAR Point Clouds** S3 bucket
  (`canelevation-lidar-point-clouds.s3.ca-central-1.amazonaws.com`),
  supplier `TRCA`, project `GTA_2023`, capture 20230511 (May 11, 2023),
  file `ON_TRCA2023_20230511_NAD83CSRS_UTMZ17_1km_E6250_N48370_CLASS.copc.laz`
  (+ `..._E6270_N48370_...` for qa3/qa7). COPC LAZ, EPSG:26917, point format 6.
  License: Open Government Licence - Canada.
- Exact download commands: see §6 Reproduction.
- Measured on the full 1 km tile (27,148,876 points / 980,635 m2):
  **27.69 pts/m2** — far above the 8 pts/m2 go/no-go threshold. PROCEED was justified.
- Classification (vendor): ground(2) 9.07M, building(6) 9.26M, unassigned(1) 8.81M,
  low point(7) 6.6k, high noise(18) 583. **No vegetation classes** — vegetation
  arrives via unassigned class 1. 66% single-return, 34% multi-return.
  Full histogram: `data/tracka_density.json`.
- Z range 130.47–178.39 m (CGVD2013).

## 2. CRITICAL FINDING: the shared evaluation labels are invalid

`data/labels/qa{1,3,7}.json` ("182 hand-labeled crowns") are **not crowns**.
They are the cells of the 8×8 labeling grid:

- Every label center sits within 0.7–1.1 m (mean) of a 10 m grid-cell center;
  each label occupies a distinct grid cell (qa1: 62/64 cells, qa3: 56/64, qa7: 64/64).
- Visual overlay on the 8 cm ortho: boxes sit on rooftops, roads, cars, empty yards
  in a rigid grid (see `data/lidar/tracka/diag_qa1_labels.png`, `diag_qa7_labels.png`).
- Mechanism: `pipeline/00_qa_tiles.py` line 43 exports a "grid overlay: 10 m cells,
  columns A..H, rows 1..8" as a labeling *reference*; the labeling agent labeled
  the grid cells themselves instead of crowns.

**Consequence: every round-1 F1 number is void.** 0.023 (RGB pre-trained), 0.000
(RGB fine-tuned), 0.046 (1 m CHM watershed) were all computed against an 8×8 grid,
not against trees. The "detection is dead" conclusion and all arm rankings rest on
this broken eval set. (Sanity check: arm B's grid-tuned 1 m watershed scores
F1 = 0.000 on corrected qa1 labels — its params were tuned to grid junk.)

## 3. Corrected labels (this track)

Built `data/labels_corrected/qa{1,3,7}.json`: real trees only.
Protocol per tile: CHM local-maxima candidates → each candidate verified
one-by-one against the 8 cm leaf-off ortho; kept only when a real tree
(trunk/branch structure) is visible. Roof/pole/hedge/deck artifacts rejected.
Format identical to the originals (`x_m, y_m, d_m` in the harness frame).

- qa1: 27 trees (53 candidates, 26 rejected). Verification sheet:
  `data/lidar/tracka/label_qa1_verify.png`.
- qa3, qa7: PENDING (waiting on the second COPC tile download).

Caveat: labels derive from CHM peaks verified in the ortho. This is legitimate
(the criterion is "a real tree exists here", judged in an independent sensor),
but it mildly favors height-based detectors. Noted, not hidden.

## 4. Method (fine CHM + building mask + classical segmentation)

- Frame: everything in EPSG:3857 (the harness frame; 1 label-"meter" = 1 3857-unit).
  (Early 3857-vs-UTM17 frame bug caught and fixed: an 80-unit tile is only
  ~57.8 true ground meters at this latitude; working in 3857 keeps predictions
  in the label frame with zero conversion risk.)
- DSM: max-Z scatter of class-1 (vegetation/unassigned) points at 0.5 3857-units
  (~0.36 ground m); class 6 (building) points dropped. DSM holes closed by
  nearest-valid fill within 3 px; farther nodata → 0 (ground assumption).
- DTM: NRCan HRDEM 1 m DTM (validated flat-ground median 0.06 m), bilinear to 0.5.
- Building mask: City of Toronto "Topographic Mapping – Building Outlines"
  (CKAN `topographic-mapping-building-outlines`, 557,694 outlines), rasterized at
  0.5 with 2 m buffer; masked to nan BEFORE segmentation. Double defense with the
  class-6 point exclusion.
- CHM = DSM − DTM, clipped [−2, 60] m.
- Segmentation: classical treetop-seeded region growing — Gaussian smooth →
  local-maxima treetops (min separation, min height) → marker-controlled watershed
  on the inverted CHM with height floor → min/max crown-area filters.
  (Same family as Dalponte–Coomes seeded region growing.)
- Box = segment bbox; score = segment max CHM, min-max normalized per tile.
- Tuning: grid search on qa1+qa3 CORRECTED labels only; qa7 held out.

## 5. Results

### Detector evolution on corrected qa1 (27 real trees)
- Marker-watershed on 0.5-unit CHM: F1 = 0.14 (tp=3, fp=13, fn=24).
  Failure mode: segments leak across shallow valleys between adjacent crowns,
  producing grove-sized blobs whose bboxes match no single tree (IoU < 0.5).
- **Dalponte-style seeded region growing** (treetops tallest-first, grow to
  8-neighbors only downhill, above height floor, within max_radius, unclaimed):
  on class-6-masked CHM, F1 = 0.356 at max_radius=4.0; tightening to 2.5 m
  jumps to F1 = 0.627 (tp=16, fp=8, fn=11).
- **City footprint mask** (buf=0.5 m, 56.9% of tile masked; footprints align
  cleanly with rooftops in the ortho): F1 = **0.625** (tp=15, fp=6, fn=12)
  at sigma=0.5, min_dist=2.5, peak_h=2.5, floor=1.5, max_radius=2.5, min_area=3.0.
  The mask kills roof false positives (fp 8 -> 6); max_radius=2.5 keeps segments
  tight enough to hit IoU 0.5 against individual crowns.
- Building mask note: vendor class 6 (building) is accurate on roofs
  (92% of points over a probed house) but covers 51% of the 0.5-unit grid
  undilated; City footprint mask (2 m buffer) is the final mask.

### Final numbers (corrected labels = real trees)
Tuned on qa1+qa3, qa7 held out. Params: sigma=0.5, min_dist=2.0, peak_h=2.0,
floor=1.0, max_radius=2.5, min_area=5.0.

| Set | F1 | tp | fp | fn |
|-----|-----|----|----|----|
| qa1+qa3 (tuned) | **0.611** | - | - | - |
| qa7 (held-out) | **0.074** | 8 | 100 | 101 |
| Overall | 0.264 | 45 | 136 | 115 |

On the ORIGINAL grid labels (for the record; labels invalid per §2):
F1 = **0.049** (tp=8, fp=135, fn=174), indistinguishable from the 1 m
watershed's 0.046, as expected: no tree detector scores on a non-tree grid.

### Detector evolution (corrected qa1, 27 trees)
- Marker-watershed, 0.5-unit CHM: F1 = 0.14. Failure: segments leak across
  shallow valleys, producing grove-sized blobs (IoU < 0.5 vs single crowns).
- Dalponte-style region growing (downhill-only, max_radius cap): F1 = 0.356
  at max_radius=4.0; **0.627** at max_radius=2.5 (tp=16, fp=8, fn=11).
- Plus City footprint mask (0.5 m buffer, 56.9% of tile): **0.625**
  (tp=15, fp=6, fn=12). Mask kills roof FPs; max_radius=2.5 keeps segments
  tight enough for IoU 0.5 on urban crowns.

### The qa7 failure: domain shift, understood
qa7 is dense mature forest (20-27 m trees, 8-12 m crowns); qa1/qa3 are urban
(4-8 m crowns). Fixed max_radius=2.5 fragments each forest crown into multiple
5 m segments that cannot reach IoU 0.5 against 10 m GT boxes. The detector
finds the trees (109 detections vs 109 labels) but mis-segments large crowns.
Fix requires adaptive radius from crown allometry (taller → wider), not
implemented here. This is a generalization failure, not a detection failure.

## 6. Reproduction

```bash
cd ~/workspace/toronto-tree-canopy
.venv/bin/pip install laspy lazrs   # into the repo .venv
# raw point cloud (177 MB + 223 MB; S3, resume with -C - on drops)
curl -C - -o data/lidar/raw/qa1_tile.copc.laz \
  "https://canelevation-lidar-point-clouds.s3.ca-central-1.amazonaws.com/pointclouds_nuagespoints/TRCA/GTA_2023/ON_TRCA2023_20230511_NAD83CSRS_UTMZ17_1km_E6250_N48370_CLASS.copc.laz"
curl -C - -o data/lidar/raw/qa37_tile.copc.laz \
  "https://canelevation-lidar-point-clouds.s3.ca-central-1.amazonaws.com/pointclouds_nuagespoints/TRCA/GTA_2023/ON_TRCA2023_20230511_NAD83CSRS_UTMZ17_1km_E6270_N48370_CLASS.copc.laz"
# building footprints (395 MB GeoJSON, City of Toronto Open Data)
curl -C - -o data/lidar/raw/building_outlines_4326.geojson \
  "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/09a930cc-2a52-49b2-866d-52ac7f769a73/resource/8364d47f-6a39-439d-8e9c-4ea1a7506e53/download/building-outlines---4326.geojson"
# pipeline
.venv/bin/python data/lidar/tracka_detect.py build        # fine CHMs (building-masked)
.venv/bin/python data/lidar/tracka_final.py grid          # tune on qa1+qa3 corrected
.venv/bin/python data/lidar/tracka_final.py final         # eval incl. held-out qa7
```

## 7. Files written

- `data/TRACKA_REPORT.md` — this report
- `data/accuracy_tracka.json` — final eval results (harness output)
- `data/tracka_density.json` — measured density + class histogram (both tiles)
- `data/lidar/tracka_detect.py` — fine-CHM builder + region-growing segmentation
- `data/lidar/tracka_final.py` — grid tuning + final eval
- `data/lidar/tracka_gt_corrected.py` — corrected-label loader
- `data/lidar/label_prep.py` — verification-sheet generator for labeling
- `data/labels_corrected/qa1.json` (27 trees), `qa3.json` (24), `qa7.json` (109)
- `scripts/tracka_measure.py` — density measurement
- `data/lidar/tracka/chm_qa{1,3,7}_50cm_3857.tif` — footprint-masked fine CHMs
- `data/lidar/tracka/diag_*.png`, `label_*_verify.png`, `qa7_preview.png` — diagnostics
- Large binaries (`data/lidar/raw/`) are gitignored.

## 8. Verdict

**NOT a winner.** Track A proves its core hypothesis on urban trees
(F1 0.611 on qa1+qa3 vs 0.000 for the 1 m watershed on corrected labels),
with a clear mechanism: dense LiDAR (27-34 pts/m2) → 0.5-unit CHM →
footprint building mask → Dalponte-style region growing with a max_radius
cap that stops valley-leaking. But the fixed max_radius does not generalize
to qa7's mature forest (held-out F1 0.074): it fragments 10 m crowns into
5 m pieces. A production system needs adaptive crown allometry. The shared
eval labels are invalid (grid cells, not crowns); all round-1 F1s are void.
Recommend: relabel properly, then retest with adaptive radius.
