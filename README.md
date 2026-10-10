# Toronto Tree Canopy

A per-parcel tree screening tool for Toronto builders, architects, and investors: type an address and see the lot's tall-canopy structure measured from 2023 LiDAR, the calibrated chance a mature tree stands on the lot, and what to do next. An Open Nshipyard project. Ward 12 (Davenport) pilot: 27,104 parcels.

**Screening signal only; not a permit determination.** This tool never says "permit required." It says "2023 LiDAR measured 50 m² of surface 8 m or taller on this lot; the calibrated chance a mature tree stands on it is 27%; get an arborist before planning around it."

## The problem it solves

A builder evaluating a Toronto lot cannot answer "will trees block my build" from open data. The Private Tree By-law (Municipal Code Chapter 813, Article III) requires a City permit before injuring or removing any private tree 30 cm or more in trunk diameter (DBH, measured at 1.4 m); September 2026 amendments added a Distinctive tier above 61 cm with stronger protections. Construction-related removal permits cost $436.39 per tree (2026 fee schedule), and the application site plan must show ALL trees 30 cm and up on the property AND on adjacent properties within 6 m of the boundary. Private trees are invisible in open data: no inventory exists (the City's street-tree records cover city-owned road-allowance trees only, the wrong trees for this question). This project measures canopy structure from 2023 airborne LiDAR and converts it into per-lot permit-threshold probabilities.

## Methodology

1. **Measure canopy structure.** The NRCan HRDEM mosaic (CanElevation series, open data) serves 2023 airborne LiDAR flown for the Toronto and Region Conservation Authority at 1 m. Surface minus terrain gives a canopy height model (CHM). Per parcel the screen reports tall-canopy area at 6 m and 8 m, max height, and canopy percent, for the lot and for the 6 m neighbour band the by-law's site-plan rule cares about. Tall-canopy pixels include buildings: the numbers measure elevated surface, not trees alone.
2. **Calibrate mature-tree probability.** A logistic regression maps LiDAR height (max CHM in ~3 m window) and canopy area (CHM 6 m and up inside 5 m radius) around 13,208 Ward 12 street trees to P(trunk 30 cm or more), plus P(trunk over 61 cm) for the Distinctive tier. Street trees are managed road-allowance trees, so the transfer to private trees is approximate. One apex peak per contiguous tall structure is scored (a flat roof is one peak, a tree crown is one peak); peaks smoother than 95% of measured street-tree crowns are treated as roofs and excluded.
3. **Score against the by-law.** Peaks on the lot are rolled up to the chance at least one mature tree stands on the lot, and the same for the 6 m neighbour band. The `crowns` array in the API is reserved for a future segmentation win and currently empty.

## Accuracy

| Metric | Measured | How measured |
|---|---|---|
| Mature-tree calibration P(DBH ≥ 30 cm) | **AUC 0.763** (5-fold CV 0.763 ± 0.009) | 13,208 Ward 12 street trees with known trunk diameters, geometric selection inside the ward polygon |
| Distinctive-tree calibration P(DBH > 61 cm) | **AUC 0.805** (5-fold CV 0.805 ± 0.009) | Same trees, 7.2% positive |
| Per-genus P(DBH ≥ 30 cm), n ≥ 500 | Acer 0.776, Gleditsia 0.802, Picea 0.757, Quercus 0.764, Tilia 0.807, Ulmus 0.707; Prunus 0.597 | Same fit, reported not shipped (genus unknown at inference) |
| Binned calibration | Monotonic; e.g. predicted 0.40 → observed 0.46, predicted 0.66 → observed 0.69 | Deciles on the fit set |
| Individual crown detection (round 1) | **Failed honestly, not shipped**: pre-trained DeepForest F1 0.023, fine-tuned F1 0.000, 1 m watershed F1 0.046 | 182 hand-labeled crowns, 3 QA tiles; all five City orthophoto vintages are leaf-off spring captures |

Full reasoning in `data/METHOD_NOTES.md`. The screen sidesteps detection entirely: it measures canopy structure, not crowns.

## LiDAR vintage

**2023** (TRCA GTA_2023 airborne LiDAR via the NRCan HRDEM mosaic). Every record is stamped `2023 LiDAR`. A tree cut in 2024 is a false positive; new growth since 2023 is missing. The vintage caveat appears on every screening result.

## Limitations

- The pilot covers **Ward 12 (Davenport)** only: 27,104 parcels. Addresses outside get HTTP 404 with the pilot scope.
- Screening signal only; never a permit determination. Only a certified arborist can confirm trunk diameter on site.
- Tall-canopy area counts elevated surface 6 m and up, **including buildings**. The mature-tree probability is calibrated on street trees and applied to tree-like LiDAR peaks; pitched roofs still read as canopy and inflate it.
- The calibration is fit on managed road-allowance street trees; transfer to private backyard trees is approximate.
- The screen cannot see trees removed after the 2023 LiDAR, and cannot see under-canopy trees.

## App

Next.js 16 + React 19, TypeScript strict, EN/FR (`/en`, `/fr`), red/paper civic theme.

- **Explorer** (`/`): address search with typeahead (`/api/suggest`, backed by the City's Address Points), a per-parcel tall-canopy map (2022 ortho with 2023 LiDAR canopy tint, pre-rendered PNGs), and a screening card with a plain-English verdict.
- **REST**: `GET /api/v1/screen?address=…` (per-parcel screening payload), `GET /api/suggest?q=…` (typeahead), `GET /api/download?format=geojson|csv` (Ward 12 dataset, built on the fly), `GET /api/openapi.json` (OpenAPI 3.1).
- **MCP**: `POST /mcp` (Streamable HTTP JSON-RPC 2.0) with tools `canopy_screen(address)` and `parcel_crowns(parcel_id)`.

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

The app reads `data/parcel_canopy_ward12.json` (per-parcel LiDAR metrics for all 27,104 Ward 12 parcels) and `data/calibration_lidar.json` (the fitted calibration). Reproduce both with the repo venv:

```bash
.venv/bin/python3 data/lidar/fetch_ward12_full.py  # 40 WCS chunks, NRCan HRDEM
.venv/bin/python3 data/lidar/build_chm_full.py     # mosaic -> ward12_chm_full.tif
.venv/bin/python3 data/lidar/calibrate_lidar.py    # -> data/calibration_lidar.json
.venv/bin/python3 data/lidar/parcel_canopy.py      # -> data/parcel_canopy_ward12.json
.venv/bin/python3 scripts/render_parcel_maps.py --only TOP-5293472  # demo map
```

## Licence

MIT. Data carries the City of Toronto and NRCan open data terms.

## Author

**Richardson Dackam** — [X](https://x.com/richardsondx) · [GitHub](https://github.com/richardsondx)
