# Toronto Tree Canopy

A per-parcel tree screening tool for Toronto builders, architects, and investors: type an address and see the lot's tall-canopy structure measured from 2023 LiDAR, the calibrated chance a mature tree stands on the lot, and what to do next. An Open Nshipyard project. Toronto-wide: 498,463 parcels, 25 wards.

**Screening signal only; not a permit determination.** This tool never says "permit required." It says "2023 LiDAR measured 50 m² of surface 8 m or taller on this lot; the calibrated chance a mature tree stands on it is 27%; get an arborist before planning around it."

## The problem it solves

A builder evaluating a Toronto lot cannot answer "will trees block my build" from open data. The Private Tree By-law (Municipal Code Chapter 813, Article III) requires a City permit before injuring or removing any private tree 30 cm or more in trunk diameter (DBH, measured at 1.4 m); September 2026 amendments added a Distinctive tier above 61 cm with stronger protections. Construction-related removal permits cost $436.39 per tree (2026 fee schedule), and the application site plan must show ALL trees 30 cm and up on the property AND on adjacent properties within 6 m of the boundary. Private trees are invisible in open data: no inventory exists (the City's street-tree records cover city-owned road-allowance trees only, the wrong trees for this question). This project measures canopy structure from 2023 airborne LiDAR and converts it into per-lot permit-threshold probabilities.

## Methodology

1. **Measure canopy structure.** The NRCan HRDEM mosaic (CanElevation series, open data) serves 2023 airborne LiDAR flown for the Toronto and Region Conservation Authority at 1 m. Surface minus terrain gives a canopy height model (CHM). City of Toronto building footprints (557,694 outlines, 2 m buffer) are masked out of the CHM before measurement, so rooftops no longer read as canopy. Per parcel the screen reports tall-canopy area at 6 m and 8 m, max height, and canopy percent, for the lot and for the 6 m neighbour band the by-law's site-plan rule cares about. Coverage is 100% of Toronto (316/316 WCS probes across the city union, zero gaps, zero request errors).
2. **Calibrate mature-tree probability.** A logistic regression maps LiDAR height (max CHM in ~3 m window) and canopy area (CHM 6 m and up inside 5 m radius) around 9,811 street trees with known trunk diameters to P(trunk 30 cm or more), plus P(trunk over 61 cm) for the Distinctive tier. The fit samples the building-masked CHM, so roofs contribute neither height nor canopy area to the features. Street trees are managed road-allowance trees, so the transfer to private trees is approximate. One apex peak per contiguous tall structure is scored; peaks smoother than 95% of measured street-tree crowns are treated as roofs and excluded.
3. **Score against the by-law.** Peaks on the lot are rolled up to the chance at least one mature tree stands on the lot, and the same for the 6 m neighbour band. The `crowns` array in the API is reserved for a future segmentation win and currently empty.

## Accuracy

| Metric | Measured | How measured |
|---|---|---|
| Mature-tree calibration P(DBH ≥ 30 cm) | **AUC 0.826** (5-fold CV 0.826 ± 0.005) | 9,811 street trees with known trunk diameters, sampled on the building-masked CHM |
| Distinctive-tree calibration P(DBH > 61 cm) | **AUC 0.896** (5-fold CV 0.896 ± 0.010) | Same trees |
| Binned calibration | Monotonic; e.g. predicted 0.32 → observed 0.31, predicted 0.67 → observed 0.70 | Deciles on the fit set |
| Individual crown detection (round 1) | **Failed honestly, not shipped**: pre-trained DeepForest F1 0.023, fine-tuned F1 0.000, 1 m watershed F1 0.046 | 182 hand-labeled crowns, 3 QA tiles; all five City orthophoto vintages are leaf-off spring captures |

Full reasoning in `data/METHOD_NOTES.md`. The screen sidesteps detection entirely: it measures canopy structure, not crowns.

## LiDAR vintage

**2023** (TRCA GTA_2023 airborne LiDAR via the NRCan HRDEM mosaic). Every record is stamped `2023 LiDAR`. A tree cut in 2024 is a false positive; new growth since 2023 is missing. The vintage caveat appears on every screening result.

## Limitations

- The screen covers **all of Toronto**: 498,463 parcels in 25 wards. Addresses outside Toronto get HTTP 404; addresses inside Toronto that match no parcel get HTTP 404 "no canopy data for this location".
- Screening signal only; never a permit determination. Only a certified arborist can confirm trunk diameter on site.
- City building footprints (2 m buffer) are masked out before measurement, so rooftops no longer read as canopy. Other tall structures (sheds, gazebos, retaining walls, construction equipment) still do, and the mature-tree probability is applied to tree-like LiDAR peaks, so non-tree structures can inflate it.
- The calibration is fit on managed road-allowance street trees; transfer to private backyard trees is approximate.
- The screen cannot see trees removed after the 2023 LiDAR, and cannot see under-canopy trees.

## App

Next.js 16 + React 19, TypeScript strict, EN/FR (`/en`, `/fr`), red/paper civic theme.

- **Explorer** (`/`): address search with typeahead (`/api/suggest`, backed by the City's Address Points), a per-parcel tall-canopy map (server-rendered on demand from the ward's masked 2023 LiDAR CHM), and a screening card with a plain-English verdict.
- **REST**: `GET /api/v1/screen?address=…` (per-parcel screening payload, backed by 500 m parcel shards fetched one per request), `GET /api/v1/parcel-map?parcel_id=…` (server-rendered parcel map PNG), `GET /api/suggest?q=…` (typeahead), `GET /api/download?format=geojson|csv&ward=NN` (per-ward static dataset files), `GET /api/openapi.json` (OpenAPI 3.1).
- **MCP**: `POST /mcp` (Streamable HTTP JSON-RPC 2.0) with tools `canopy_screen(address)` and `parcel_crowns(parcel_id)`.

Parcel records live in `data/shards/` (one JSON per 500 m EPSG:3857 cell, plus `parcel_index.json`), served over HTTP via `CANOPY_SHARD_BASE` (jsDelivr over this repo in production, local `data/shards` in dev). The function bundle stays small: code plus a 10 KB simplified city boundary for honest 404s.

### Screenshots

![Explorer with a screened lot, tall-canopy map, and verdict](public/screenshots/explorer-en.png)
![Screening card detail](public/screenshots/card-en.png)
![Explorer in French](public/screenshots/explorer-fr.png)

### Development

```bash
npm install
npm run dev        # http://localhost:3000/en
npx tsc --noEmit   # type check
npm run build      # production build
```

The app reads `data/calibration_lidar.json` (the fitted calibration) and `data/city_boundary.json` (simplified Toronto boundary for 404s) from its bundle, and fetches parcel shards plus the parcel index over HTTP (`CANOPY_SHARD_BASE`). Reproduce the data pipeline with the repo venv:

```bash
.venv/bin/python3 data/lidar/build_footprint_index.py  # one-time footprint bbox index
.venv/bin/python3 data/lidar/ward_plan.py              # per-ward fetch plan
.venv/bin/python3 data/lidar/build_parcel_index.py     # parcel centroid index + tile plan
.venv/bin/python3 data/lidar/prefetch_chunks.py        # WCS DSM/DTM chunks, NRCan HRDEM
for t in $(seq 0 36); do .venv/bin/python3 data/lidar/compute_tile.py --tile $t; done
.venv/bin/python3 scripts/build_city_boundary.py       # -> data/city_boundary.json
node scripts/build_shards_city.mjs                     # -> data/shards/
.venv/bin/python3 scripts/build_ward_cogs.py           # -> data/cogs/ (map endpoint)
.venv/bin/python3 scripts/build_downloads.py           # -> data/downloads/ (per-ward files)
```

## Licence

MIT. Data carries the City of Toronto and NRCan open data terms.

## Author

**Richardson Dackam** · [X](https://x.com/richardsondx) · [GitHub](https://github.com/richardsondx)
