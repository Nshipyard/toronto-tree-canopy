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
