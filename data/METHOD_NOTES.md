# Toronto Tree Canopy — Pilot (Ward 12 Davenport): Method Notes

Pilot run 2026-10-10. This file records what was actually done, the parameter
choices, and every measured number. Nothing here is cited from a paper.

## Imagery

- Source: City of Toronto ArcGIS MapServer
  `basemap/cot_ortho_2022_color_8cm/MapServer`, `export` operation (the service
  is a MapServer, so `exportImage` returns HTTP 400 "Invalid URL"; `export`
  works), EPSG:3857, `format=png32`.
- Ward 12 polygon: Toronto Open Data "City Wards" datastore dump
  (resource 7672dac5-b383-4d7c-90ec-291dc69d37bf), AREA_NAME "Davenport".
  Bbox (3857): x -8846622..-8841081, y 5409993..5418470 (~5.5 x 8.5 km).
- Inference GSD: 0.40 m (within the brief's 25-50 cm band). Exported as
  2048x2048 px tiles (819.2 m), 52 tiles kept after ward-intersection filter.
- QA: a few 8 cm tiles (80x80 m) kept under data/qa-tiles/ for labeling and QA.
- IMPORTANT: the 2022 capture is leaf-off (early spring). Deciduous crowns
  appear as bare branch structure. The 2020 and 2021 vintages were checked at
  a QA spot and are also leaf-off; the 2018 and 2015 vintages were visually
  confirmed leaf-off as well. All five city vintages checked (2015, 2018,
  2020, 2021, 2022) are leaf-off. There is no leaf-on vintage in the city
  archive.

## Detection

- Model: DeepForest 2.1.0 RetinaNet, release weights `weecology/deepforest-tree`
  (MIT), downloaded from HuggingFace with curl to data/weights/model.safetensors
  (the sandbox proxy breaks huggingface_hub/httpx proxy parsing, so weights
  are loaded from the local file; see pipeline/df_model.py).
- Pre-trained (leaf-on NEON) model on the leaf-off Toronto tiles: measured
  F1 = 0.046 at IoU 0.5 (182 hand-labeled crowns, 3 tiles; best threshold 0.05;
  F1 0.007-0.023 at higher thresholds). Far below the brief's 0.64-0.93 band.
  The domain shift (leaf-on training -> leaf-off inference) breaks the
  pre-trained model on this imagery.
- Fine-tuning (what was actually done, no claim beyond this): the full
  RetinaNet was fine-tuned on CPU for 15 epochs (lr 5e-4, batch 1) on
  118 hand-labeled crowns from qa1+qa3 (8 cm, 400 px chips, stride 300),
  with qa7 (64 crowns) held out. No frozen layers, no hyperparameter search.
  Train chips: data/ft_train/, val chips: data/ft_val/.
- Fine-tuned model evaluation (measured 2026-10-10, pipeline/03_evaluate.py,
  greedy matching, IoU 0.5; weights data/weights/model_finetuned.pt loaded
  cleanly: 301 tensors, missing=0, unexpected=0):
  - Held-out qa7 (64 crowns, production GSD 0.40 m): F1 = 0.000 at every
    threshold 0.05-0.50 (tp=0; 27 predictions at thr 0.05, none matching).
  - qa1+qa3+qa7 at 0.40 m (qa1+qa3 are the training tiles, so in-sample):
    best F1 = 0.037 at threshold 0.05 (tp=5, fp=86, fn=177).
  - Held-out qa7 at native 8 cm (training resolution, diagnostic only):
    best F1 = 0.233 at threshold 0.25 (P=0.231, R=0.234, tp=15, fp=50,
    fn=49). The model learned a weak signal at its training resolution but
    it does not transfer to the 0.40 m production GSD at all.
  - Conclusion: fine-tuning on 118 hand-labeled crowns did not produce a
    usable detector. At production GSD it scores WORSE than the pre-trained
    model (0.000 vs 0.046). Branch 2b taken: detection track STOPPED.
  - Detail tables: data/accuracy_finetuned_qa7_40cm.json,
    data/accuracy_finetuned_all_40cm.json,
    data/accuracy_finetuned_qa7_8cm.json.

## Hand-labeled evaluation set

- 3 tiles x 80x80 m (qa1, qa3, qa7), 8 cm imagery, labeled by visual
  inspection: 62 + 56 + 64 = 182 crowns. Labels are center+diameter eyeball
  estimates (nearest ~1 m), not survey-grade; ambiguous/merged crowns were
  labeled as best seen. Files: data/labels/qa{1,3,7}.json.
- Metric: greedy matching, F1 at IoU 0.5, reported across score thresholds.

## Calibration (crown diameter -> DBH)

- Street trees: Toronto Open Data "Street Tree Data" datastore dump
  (resource 3dafa392-c6ab-4f37-9bf9-21ddf7308eaf), Ward 12 subset
  (18,077 trees with WARD=12).
- Pairing: nearest detected crown within 5 m of the inventory position;
  pairs skipped when a second crown is within 5 m and within 2 m of the
  nearest (ambiguous). Crown diameter = sqrt(box width x height) in meters.
- Model per genus group (genus from BOTANICAL_NAME first token):
  log10(DBH_cm) = a + b * log10(crown_diameter_m), OLS, 80/20 split,
  R^2 reported on the 20% holdout per group (groups with n>=100).
- Distributional assumption: residuals normal in log10 space, homoscedastic
  (i.e. DBH lognormal conditional on crown diameter). 95% prediction
  interval = mu +/- 1.96*sigma, back-transformed. p_ge_30cm and p_gt_61cm
  from the normal CDF in log10 space.
- Parcel-level DBH uses the GENERIC group (all paired urban trees): species
  is NOT guessed from RGB imagery, so intervals are wider than any
  species-specific fit. Fitted on URBAN street trees only; no forest-derived
  allometry anywhere.
- Per-group R^2: NOT COMPLETABLE. The pairing step assumes detected crowns
  correspond to real trees; with detection F1 = 0.000 on the held-out tile,
  pairing detections to street-tree positions would fit noise, not
  allometry. No calibration R^2 is reported. (If a future detector reaches
  usable F1, re-run pipeline/04_calibrate.py against trustworthy detections.)

## Parcel join

- Parcels: City Property Boundaries + TOAR Address Points, same sources as
  Nshipyard/toronto-parcel-spine (used read-only; spine repo cloned to
  vendor/ for reference, not modified). Parcel IDs are TOP-<PARCELID>.
- Kept parcels whose centroid falls in the Ward 12 polygon; addresses joined
  by point-in-polygon (first address kept; address may be null).
- Crown -> parcel: crown center inside parcel polygon. canopy_pct = clipped
  crown-box area / parcel area. Neighbour 6 m: crown centers within 6 m of
  the parcel boundary but outside it (by-law site-plan rule).
- Crown "polygon" in the output is the detection bounding box as a closed
  ring, NOT a true crown outline. Stated in the GeoJSON disclaimer.

## Outputs

- data/parcels-ward12.geojson (EPSG:4326) - NOT PRODUCED (detection track stopped)
- data/accuracy.json - app-side file, not regenerated from this pilot
- data/crowns_ward12.json (all detections, 3857) - NOT PRODUCED
- data/allometry.json, data/accuracy_calibration.json - NOT PRODUCED (no calibration)
- data/parcels_ward12.json (existing, kept) - STALE/BROKEN: built on the
  failed pre-trained detector (F1 0.046). Left in place untouched; do not
  ship parcel outputs derived from it.

## Leaf-off verdict (branch 2b, 2026-10-10)

All five vintages in the city ortho archive that were checked (2015, 2018,
2020, 2021, 2022) are leaf-off spring captures. There is no leaf-on vintage
available. Measured detection quality on leaf-off Toronto imagery:

- Pre-trained DeepForest 2.1.0 (leaf-on NEON weights): F1 = 0.046 at IoU 0.5
  (182 hand-labeled crowns, 3 tiles, best threshold 0.05; 0.007-0.023 at
  higher thresholds).
- Fine-tuned on 118 Toronto crowns (15 epochs, CPU, qa1+qa3; qa7 held out):
  F1 = 0.000 on held-out qa7 at the 0.40 m production GSD; 0.037 in-sample
  (qa1+qa3) at 0.40 m; 0.233 on held-out qa7 at native 8 cm.

Why RGB crown detection cannot ship on this imagery: deciduous crowns are
bare branch structure with almost no crown-width visual cue in leaf-off RGB;
the fine-tuned model's weak 8 cm signal (F1 0.233) collapses to zero at the
production 0.40 m GSD, so there is no usable detector at any operating point.
118 hand-labeled crowns were not enough to overcome the domain shift, and the
brief's 0.64-0.93 F1 band is unreachable here. No parcel outputs, calibration
fits, or accuracy claims were built on these detections. The only remaining
viable path for per-parcel canopy signal is the 2018 leaf-on canopy raster
(per-parcel canopy percent), not RGB crown detection.

## Honesty ledger

- Detection F1 and calibration R^2 below are MEASURED on this pilot, not
  cited. Where they fall short of the brief's published ranges, that is
  reported, not hidden.
- Screening signal only. Nothing in the output says "permit required".
- Every record carries imagery_vintage "2022": trees removed after the
  capture are invisible to this product.

## Aurora Solar research (2026-10-10, web research by subagent)

Question: how does Aurora Solar (user's former employer) do tree detection for
shade analysis, and what transfers to leaf-off Toronto open data?

Findings (sourced from Aurora help docs, blog, patents US11830137B2 /
US11983813B2, NREL blind study fy16osti/65558, TechCrunch/Engineering.com):
- Input for trees is aerial LiDAR point clouds / height fields, NOT RGB
  appearance. Aurora pre-stages a stitched LiDAR database (~2/3 of US
  population coverage as of 2019). RGB (Google/satellite, Nearmap, EagleView,
  drone) is the visual backdrop and an ML input for ROOF geometry only.
- No 2D RGB crown detection exists anywhere in their pipeline. Trees enter
  the shade model two ways: (a) LIDAR Shading mode, the default automated
  path: the raw LiDAR height field is ray-traced DIRECTLY in the irradiance
  engine, no tree objects drawn at all; (b) parametric 3D tree solids
  (cone/sphere with Tree Height + Crown Height), placed manually or by AI
  Tree Detection (~Sept 2025), auto-sized to LiDAR points ("Fit Trees to
  LIDAR"). AI Tree Detection outputs location + canopy spread + height: 3D
  parameters, never a 2D polygon mask.
- Leaf-on vs leaf-off: NOT modeled. Static 3D scene; no species/dormancy
  parameter. The shade model inherits whatever season the LiDAR snapshot was
  captured in. Competitor Scanifly markets seasonal dormancy simulation as a
  differentiator against Aurora, consistent with Aurora not doing it.
- Hypothesis verdict: CONFIRMED, stronger than expected. Aurora works in 3D
  height space rather than 2D RGB appearance, and for its primary path it
  does not detect tree objects at all.

Transferable techniques (ranked), now under test as experiment arms:
1. Arm B: abandon 2D crown polygons; detect in a canopy height model
   (CHM = DSM - DTM). A tree is a localized height bump; the bump persists
   leaf-off because trunks/branches occupy 3D space.
2. Arm B method: local-maxima treetop detection + marker-controlled
   watershed crown segmentation on the CHM (standard forestry recipe).
3. Fit each crown as a parametric 3D solid (ellipsoid/cone: treetop height,
   crown-base height, footprint ellipse) rather than a flat polygon.
4. Arm C (no-LiDAR fallback): shadow-length height proxies from the leaf-off
   orthophoto, h = L / tan(solar elevation) from acquisition timestamp +
   solar ephemeris, the only height signal in pure RGB.

## Arm B: CHM watershed detection (2026-10-10) — measured F1 0.046, NOT a win

Data: NRCan HRDEM Mosaic WCS (TRCA GTA_2023 airborne LiDAR, ~1 m DSM+DTM,
Open Government Licence - Canada). CHM = DSM - DTM, reprojected EPSG:3857
at 1.0 m. Extra WCS chunks fetched to cover QA tiles (lon -79.455..-79.405,
lat 43.665..43.69); files under data/lidar/qa_cover/.

Method (Aurora transferable technique #2): Gaussian sigma 0.5 m,
local-maxima treetops (min separation 2 m, min height 2.5 m),
marker-controlled watershed with 1.5 m floor; drop segments with 5 m-window
CHM std < 0.5 m (building suppression), >120 m^2, or >400 m^2 and flat.
Params picked from qa1+qa3 grid only; qa7 untouched. Box = segment bbox,
score = segment max CHM normalized per tile.

Result (identical harness, IoU 0.5): best F1 0.046 overall
(tp 5, fp 31, fn 177 at threshold 0.05); qa7-only F1 0.000.
Baselines: RGB pre-trained 0.023, RGB fine-tuned 0.000.

Mechanism: at 1 m the CHM is a near-continuous surface in dense urban
fabric, so watershed cannot isolate crowns. In qa1/qa3, houses (7-9 m) and
trees (8-14 m) interlock into multi-building segments; the roughness
suppression feature had no separation power (median roughness 1.02 for
GT-matching vs 0.96 for junk segments). In qa7 (mature canopy) crowns merge
into one canopy surface that the area cap discards wholesale, hence 0.000
on the held-out tile. Height separates vegetation from ground well at 1 m,
but 1 m is too coarse for crown INSTANCE segmentation at IoU 0.5 on 7-8 m
crowns embedded in same-height urban fabric. The Aurora transfer failed
here, informatively: the technique assumes crowns stand out as separable
height bumps against a lower background (true in sparse forestry, false in
dense urban Toronto at 1 m).

## Arm C: shadow-height (2026-10-10) — UNTESTABLE

No acquisition timestamp exists for the cot_ortho_2022_color_8cm imagery
(13 sources checked: tiles.json, qa jsons, export script, method notes,
ArcGIS service metadata, PNG EXIF, memory, web, retired open data page,
repo grep, umbrella repos). Without a sun angle, h = L/tan(elevation) is
an invented experiment. Arm stopped before running; recorded in
data/accuracy_armC_shadow.json. Runnable later if City flight records
surface.

## Arm D: 2018 Tree Canopy polygons as fallback (2026-10-10)

Dataset: City of Toronto Open Data "Forest and Land Cover" package
(id 61642048-56bb-4050-b7c3-f569fcf94527), resource "2018 Tree Canopy Study
Geodatabase" (436,398,730 bytes, verified). CORRECTION to earlier premise:
the geodatabase contains NO raster; it holds one vector layer
LandCover2018, 1,812 multipolygons (EPSG:2952) from NDVI segmentation of
multispectral satellite imagery + LiDAR. Class 1 = tree (233 polys).
Downloaded to data/canopy2018/ (reproducible; binaries gitignored, exact
CKAN URL in data/accuracy_armD_canopy2018.json).

Evaluation (different product, different metric): per-tile canopy fraction
= tree-polygon area within tile / 6400 m^2, vs label-derived fraction
(sum pi*(d/2)^2 / 6400; double-counts overlapping crowns, inflating labels).

| tile | 2018 frac | label frac | abs err |
|------|-----------|------------|---------|
| qa1  | 0.1583    | 0.4068     | 0.2485  |
| qa3  | 0.1380    | 0.3580     | 0.2200  |
| qa7  | 0.4585    | 0.4338     | 0.0247  |

MAE = 0.164, Pearson r = 0.81 (n=3, indicative only). Full results:
data/accuracy_armD_canopy2018.json.

Mechanism: the 2018 product is a coarse land-cover segmentation that
labels whole planting strips as "tree" but cannot resolve individual
crowns or intra-crown gaps, so it under-reports systematically on sparse
street-tree tiles (off by ~0.22-0.25) and only roughly matches dense qa7.
The r=0.81 rank-ordering partly masks a systematic granularity mismatch.
Vintage is 2018 (8 years old); doc does not name the satellite or month.

## Head-to-head verdict (2026-10-10, all measured on the same 182 labels)

| arm | signal | metric | measured |
|-----|--------|--------|----------|
| A | RGB pre-trained DeepForest, 0.40 m | F1@IoU0.5 | 0.023 |
| A2 | RGB fine-tuned 15ep/118 crowns, 0.40 m | F1@IoU0.5 | 0.000 |
| B | CHM watershed, 1 m LiDAR | F1@IoU0.5 | 0.046 (0.000 on held-out qa7) |
| C | shadow-height | — | UNTESTABLE (no acquisition timestamp) |
| D | 2018 canopy polygons | per-tile frac MAE | 0.164 (r=0.81, n=3) |

Winner by measurement: NONE for individual crown detection. Arm B's 0.046
is not meaningfully above the 0.023 baseline and is strictly worse on the
held-out tile. Three independent signals (RGB appearance, RGB fine-tune,
1 m height geometry) all fail, with understood mechanisms: leaf-off kills
appearance; 1 m CHM is a continuous surface in dense urban fabric.
RECOMMENDATION: shelve individual-crown detection from open data. Arm D
can support a much weaker per-parcel canopy-percent product only, with
known MAE ~0.16 and 2018 vintage; it cannot answer the 30 cm / 61 cm
by-law question. Next step if the product matters: commercial leaf-on
imagery or higher-resolution LiDAR (procurement decision, not tested here).

## Track B: tall-canopy LiDAR screen (2026-10-10, SHIPPED)

Round 1 shelved individual-crown detection. Track B ships the guaranteed-shippable
product instead: per-parcel tall-canopy STRUCTURE from 2023 LiDAR plus a
statistically calibrated mature-tree probability. No crown detection anywhere.

### Full-ward CHM

- Source: NRCan HRDEM Mosaic WCS (dsm + dtm), TRCA GTA_2023, 2023 vintage.
- Fetch: `data/lidar/fetch_ward12_full.py`, 40 chunks (4x4 grid at 0.015 deg over
  lon -79.47..-79.41, lat 43.64..43.70, plus a west extension column because the
  ward's western edge sits 0.0006 deg west of the round-1 grid). Reuses cached
  round-1 chunks; 21 fetched fresh 2026-10-10.
- Build: `data/lidar/build_chm_full.py` mosaics to 4994x4540 px, CHM = DSM-DTM,
  nodata -9999, clipped to [-2, 60] m, masked to the Ward 12 polygon.
  Output (gitignored): `data/lidar/wcs/ward12_chm_full.tif`.
- Ward stats: 7,723,049 valid px; pixel 1.064 m E-W x 1.471 m N-S (1.566 m2);
  median CHM 4.02 m, p99 21.45 m; 39.3% of ward pixels > 6 m, 23.5% >= 8 m
  (dense urban fabric: roofs dominate the tall band, stated everywhere).
- Two bugs caught before shipping: (1) the ward mask was inverted on the first
  build (geometry_mask invert semantics), blanking the ward interior; caught by
  checking the ward centroid pixel. (2) the street-tree CSV's WARD column uses a
  different ward numbering than the current 25 wards: trees geometrically inside
  the Davenport polygon carry WARD='09'; filtering WARD=='12' selects 18,077 trees
  that are NOT in Ward 12. Tree selection is geometric (point in ward polygon).

### Calibration: P(DBH >= 30 cm | LiDAR height, canopy area)

- Script: `data/lidar/calibrate_lidar.py`. Output: `data/calibration_lidar.json`.
- Fit set: 13,208 street trees geometrically inside the Ward 12 polygon with known
  DBH (of 13,305 inside; 4 lacked CHM coverage). 29.5% >= 30 cm, 7.2% > 61 cm.
- Features per tree: h = max CHM in ~3 m window; area = CHM >= 6 m area inside
  5 m radius (elliptical footprint, 51 px). Logistic regression, standardized.
- Generic P(DBH>=30): train AUC 0.763, 5-fold CV AUC 0.763 +- 0.009.
  Coefficients (standardized): intercept -1.049, h +0.708, area +0.400.
- Generic P(DBH>61): train AUC 0.805, CV 0.805 +- 0.009.
- Per-genus P(DBH>=30), n >= 500 (reported, not shipped; genus unknown at
  inference): Acer 3422 / 0.776, Gleditsia 1042 / 0.802, Picea 668 / 0.757,
  Quercus 809 / 0.764, Tilia 672 / 0.807, Ulmus 675 / 0.707, Prunus 612 / 0.597.
  Prunus (ornamental cherries/plums) at 0.597 shows height barely predicts DBH
  for small ornamentals; the generic model absorbs this as noise.
- Binned calibration (deciles, fit set), predicted -> observed: 0.06->0.15,
  0.09->0.09, 0.14->0.12, 0.20->0.15, 0.25->0.17, 0.30->0.20, 0.34->0.28,
  0.40->0.46, 0.50->0.65, 0.66->0.69. Monotonic; slight overprediction mid-range.
- Roughness gate: CHM std in the 5 m window at fit trees: p1 0.085 m, p5 0.46 m,
  median 2.09 m. Peaks smoother than p5 (0.46 m) are treated as structures
  (flat roofs) and excluded from parcel scoring. The sub-p5 trees are mostly
  small ornamentals, so the exclusion barely moves P(mature).
- Stated limitations: street trees are managed road-allowance trees (pruned,
  spaced); transfer to private trees is approximate. The model conditions on
  tree presence, so pitched roofs passing the roughness gate still inflate
  parcel rollups. Screening signal only.

### Per-parcel metrics: 27,104 / 27,104 parcels

- Script: `data/lidar/parcel_canopy.py`. Output: `data/parcel_canopy_ward12.json`
  (22 MB, keyed by parcel id; includes WGS84 ring/bbox/centroid so the API does
  point-in-polygon without the 14 MB parcels file).
- Per parcel, for the LOT and the 6 m NEIGHBOUR BUFFER (buffer minus lot):
  tall-canopy area >= 6 m and >= 8 m (m2), max CHM (m), canopy percent
  (tall-canopy area / parcel area_m2, both thresholds), calibrated
  P(any tree >= 30 cm) and P(any tree > 61 cm).
- Probability method: connected components of the >= 6 m mask (one apex per
  contiguous tall structure: a flat roof is one peak, a tree crown is one peak);
  per parcel, the highest pixel of each touching component; roughness gate;
  generic logistic scores; rollup 1 - prod(1 - p_i). Deterministic, no ML.
- Ward distributions (lot): tall-canopy >= 8 m median 32.9 m2, p90 126.8 m2,
  87.4% of parcels > 0; P(any >= 30 cm) median 0.39, 32.0% > 0.5, 2.2% > 0.8.
  High-P parcels are genuine tall-tree cases (max CHM 15-32 m).

### Upgrade paths (not blocking)

- Track A fine CHM (0.25/0.5 m): if it lands, rerun calibrate_lidar.py and
  parcel_canopy.py at the finer GSD; the API contract is resolution-agnostic.
- 2018 land-cover tree/building classes could mask tall pixels to tree canopy,
  at the cost of a 5-year vintage mismatch; not attempted.
- A building-footprint mask (City open data) would remove the pitched-roof
  inflation the roughness gate cannot catch.

## Track A (round 2): label invalidity + strong-method result (2026-10-10)

CRITICAL CORRECTION: the round-1 evaluation labels `data/labels/qa{1,3,7}.json`
("182 hand-labeled crowns") are NOT crowns. They are the cells of the 8x8
labeling grid exported by `pipeline/00_qa_tiles.py` as a labeling reference:
every label center sits within ~1 m of a 10 m grid-cell center, and overlays
show boxes on rooftops, roads, cars, and empty yards in a rigid grid
(`data/lidar/tracka/diag_qa1_labels.png`). The labeling agent labeled the grid
cells instead of crowns. CONSEQUENCE: every round-1 detection F1 is VOID:
0.023 (RGB pre-trained), 0.000 (RGB fine-tuned), 0.046 (1 m CHM watershed)
were all computed against a non-tree grid. The "detection is dead" conclusion
and all arm rankings from round 1 are retracted.

Track A built corrected labels (CHM local-maxima candidates verified one-by-one
against the 8 cm ortho; `data/labels_corrected/qa{1,3,7}.json`: 27+24+109 real
trees) and ran the strong method: raw TRCA GTA_2023 point cloud (NRCan
CanElevation S3, 27.69 pts/m2 measured, far above the 8 pts/m2 bar), 0.5-unit
fine CHM, City of Toronto building-footprint mask (557,694 outlines, 2 m
buffer), Dalponte-style seeded region growing with max_radius cap.
Measured on corrected labels (greedy F1 @ IoU 0.5): tuned qa1+qa3 F1 = 0.611;
held-out qa7 F1 = 0.074 (overall 0.264). The qa7 failure is an understood
domain shift: qa7 is dense mature forest (20-27 m trees, 8-12 m crowns) while
qa1/qa3 are urban (4-8 m crowns); the fixed max_radius=2.5 fragments large
crowns into pieces that cannot reach IoU 0.5. Generalization failure, not
detection failure; the fix is adaptive crown allometry (taller -> wider),
not implemented. Verdict: NOT a winner by the 0.1 held-out bar, but the core
hypothesis is proved on urban trees (0.611 vs 0.000 for the 1 m watershed on
the same corrected labels). Recommended next: proper relabeling + adaptive
radius retest. Full report: `data/TRACKA_REPORT.md`.
