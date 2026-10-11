# Toronto Tree Canopy: City-Scale Prep Report (Oct 10, 2026)

Independent prep for scaling the Ward 12 pilot Toronto-wide. Nothing pushed;
all work on disk under `~/workspace/toronto-tree-canopy/`.

## 1. LiDAR coverage: full city covered, no gaps

**Method.** Probed the NRCan HRDEM mosaic WCS
(`https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic`,
WCS 1.1.1, layers `dsm` + `dtm`, the same TRCA GTA_2023 source as the pilot)
at 316 grid points inside the city union polygon (25 wards unioned from
`data/wards_dump.geojson`; single polygon, 643 km², bbox
-79.6393..-79.1155 / 43.581..43.8555). Each probe fetched a ~320 m
GetCoverage window and measured the valid-pixel fraction in both layers.

**Result: 316/316 points covered (100%), 0 gaps, 0 request errors.**
Minimum valid-pixel fraction across all probes was 1.000 in both DSM and DTM,
including probes nearest the four extremes (far east Rouge -79.1155, far north
Steeles 43.8555, far west Etobicoke creek -79.6393, the Islands) and the
southern waterfront.

**Method validated, not assumed.** Positive control: a probe over open Lake
Ontario water returned 0.000 valid in both layers, so the probe genuinely
detects absence. (A probe north of Steeles in Markham returned 1.000: the
GTA_2023 campaign extends past the city line, as expected.)

**Honest caveat.** 316 samples at ~1.6 km spacing cannot rule out sub-km gaps
between samples, but zero partial windows (min valid fraction exactly 1.000)
makes hidden gaps unlikely. **No area of Toronto needs a 404-for-no-coverage
carve-out based on this evidence.** Raw probe data (gitignored):
`data/coverage_probe.json`. Probe script: `scripts/probe_wcs_coverage.py`.

## 2. Parcel extraction: 498,463 parcels, ward-sharded working file

**Exact count.** The vendored spine (`vendor/toronto-parcel-spine`) ships only
a 25,684-row sample; the full `parcel_spine.csv` was never vendored. I rebuilt
the full set from the same city sources the spine used (local dumps
`data/pb_dump.csv` + `data/ap_dump.csv`, read-only):

- 498,477 source rows in Property Boundaries
- **498,463 kept** (14 rows dropped: self-intersecting/degenerate rings; 0.003%)
- The spine's published total is 498,477; the 14 dropped rows are geometrically
  invalid and unrasterizable, so 498,463 is the computable universe.

**Working file** (gitignored): `data/parcels_toronto/` - 25 ward shards +
`unplaced.json` + `manifest.json`, **302.5 MB total** (25 ward shards + `unplaced.json` + `manifest.json`; 475,397 of the parcels carry at least one address). Schema is key-identical to `data/parcels_ward12.json`:
`parcel_id` (`TOP-<PARCELID>`), `parcelid`, `feature_type`, `stated_area`,
`area_m2`, `centroid_4326`, `address`, `address_count`, `rings_3857`
(full precision, consistent with the pilot file).

Ward mapping note: `data/wards_dump.geojson` uses the current 25-ward model,
where **Davenport is Ward 09**, not Ward 12. The pilot's `data/ward12.geojson` /
`data/parcels_ward12.json` (27,104 parcels) used older numbering. Verified: the
`ward_09.json` shard contains exactly the pilot's 27,104 parcel IDs (set diff 0;
no boundary differences). `unplaced.json` holds 154 parcels whose centroid falls
in no ward (boundary slivers).

**Cautionary finding for the final worker.** Rounding `rings_3857` to 0.1 m
silently invalidated 115 real parcels (0.023%), including an 11,351 m² parcel:
rounding collapses near-duplicate vertices into self-intersections. The working
file keeps full precision. Do not round geometry before the validity check.

Extraction script: `scripts/extract_parcels_city.py` (ward-sharded,
memory-bounded: one ward in RAM at a time; full run ~45 min on this VM).

## 3. City-wide compute time estimate (measured, not assumed)

**Measured baseline.** I timed the actual Ward 12 metric pipeline
(`data/lidar/parcel_canopy.py`, unmodified logic, output redirected to /tmp so
the pilot file is untouched): **171 s wall** for 27,104 parcels on a 22.7 Mpx
CHM (~1.06 x 1.47 m px), exit 0, sane output stats.

**Important correction to the "per-parcel speed" framing.** The pipeline is
not per-parcel. Per-parcel work is only polygon union/buffer prep and final
assembly. The dominant stages are per-PIXEL and ward-vectorized: rasterizing
all lots + 6 m buffers at once, `bincount`, argsort-based per-label max,
connected-component labeling of the tall mask, and four `fftconvolve` passes
(5 m area kernel, mean, E[x^2], roughness). A naive per-parcel loop would be
~100x slower; that win is already banked.

**Scaling.** Compute scales with CHM pixels (~20-24x Ward 12 for the city:
643 km² land x ~1.3 bbox factor / 35.5 km² ward-12 raster) and parcels
(18.4x). Estimate: **~57-68 min single-machine sequential** for the masked
metric computation city-wide (mask does not change the cost: same raster ops).

**WCS fetch** (measured: one 0.015° chunk = 7.4 s avg, 6.6 MB per layer):
~724 DSM+DTM requests for the city => **~25 min at 4 workers, ~12 min at 8**.

**Bottom line.** With per-ward parallelism (25 independent wards; biggest ward
14 has 29,350 parcels, same order as Ward 12): **~30-45 min wall clock at
8-way parallelism, ~1.5 h fully sequential**, fetch-dominated. What speeds it
up: (a) per-ward/per-tile workers, the natural unit, each ward raster fits in
RAM (~1-1.5 GB array stack); a single city-wide raster would need ~33 GB and
is not viable; (b) more WCS fetch workers (the pilot's 4 is conservative);
(c) multiprocessing the shapely union/buffer prep loop. Per-tile instead of
per-parcel is the wrong contrast: it is already per-raster; keep it that way
and parallelize by ward with a ~50 m margin for the 6 m buffer and 5 m peak
windows.

## 4. API architecture: grid-sharded index + object storage (proven)

**Why not the status quo.** `src/lib/canopy.ts` loads the 22 MB Ward 12 JSON
into memory and linear-scans point-in-polygon per request. City-wide that is
~400+ MB in memory and a 400+ MB function bundle. Vercel's function bundle
limit is 50 MB compressed / 250 MB unzipped (verified against current docs),
so no variant of "bundle the data" works. The data must live outside the
bundle.

**Recommended design: uniform-grid sharded index, shards on object storage.**
Offline build partitions parcel records into one file per 500 m EPSG:3857
cell (`<cx>_<cy>.json`); a parcel whose bbox spans cells is stored in each.
A request computes its cell from the point (closed-form Web-Mercator math, no
dependency) and reads exactly one shard: 1 file read per request, no index
file needed at request time (the cell key is deterministic). A 32-entry LRU
reuses shards on warm instances. A 14.5 MB `parcel_id -> cell` index
(measured 29 B/entry) backs the MCP `parcelById` path; a bundled 10 KB
simplified city-boundary polygon gives honest 404s (outside Toronto vs inside
but uncovered).

**Prototype, measured on Ward 12 data (27,104 parcels).**
Scripts: `scripts/proto_api/` (`build_shards.mjs`, `lookup.mjs`, `bench.mjs`,
`build_sqlite.mjs`, `sqlite_lookup.mjs`, `make_compact.mjs`,
`canopy_city_proposal.ts`).

| | Grid-shard JSON | SQLite (node:sqlite + rtree) |
|---|---|---|
| Artifact | 126 shards, **22.70 MB** total (1.036x source), max shard 351.5 KB | single **24.87 MB** .db |
| Correctness | 30/30 (20 in-parcel incl. parcel_id match, 5 road points -> miss, 5 outside-ward -> miss) | 30/30 |
| Cold lookup (uncached, local disk) | avg 3.4 ms, p50 3.8 ms, p95 10.0 ms, max 13.3 ms | avg 0.7 ms, p50 0.7 ms, p95 1.0 ms |
| Contract check | **20/20 response payloads byte-identical** to the current `buildScreenPayload` path (compiled from the real `src/lib/canopy.ts`) | n/a (same record shape) |

**City-scale extrapolation** (measured per-parcel bases): full records
854 B/parcel on disk with duplication => **~426 MB total, ~2,700 shards**,
avg shard ~158 KB, max ~350-500 KB. Compact record layout (positional arrays,
5-decimal ring, measured **353 B/parcel** vs 815): ~184 MB total. Either way
per-request cost is one shard fetch (~160 KB avg, ~70 KB compact).

**Why grid-shard wins over SQLite for Vercel.** SQLite is faster per lookup,
but its single ~460 MB .db cannot be bundled (50 MB limit) and cannot be
queried over HTTP without a range-read VFS; downloading it to `/tmp` on cold
start adds 10-30 s. Shards are natively HTTP-fetchable: one `fetch()` per
request (~160 KB, tens of ms), tiny bundle, no cold-start penalty beyond the
normal one. That is the decisive difference on serverless.

**Deploy shape.** Shards (+ `parcel_index.json`) on R2/S3-style object
storage; `CANOPY_SHARD_BASE` env points the API at the bucket URL (local
`data/shards/` dir fallback keeps `next dev` working). Function bundle stays
under a few MB: code + 10 KB city boundary + CKAN client. `findParcel` becomes
async (one shard fetch); `buildScreenPayload` is untouched, so the
`lot` / `neighbour_6m` / `verdict` / `imagery_vintage` contract and the 404
semantics are preserved by construction. `pilot_scope` field name stays;
its value becomes the city-wide scope string.

## 5. Exact `src/lib/canopy.ts` changes for the final worker

Full annotated proposal: `scripts/proto_api/canopy_city_proposal.ts`
(scratch reference; `src/lib/canopy.ts` itself was NOT modified).

1. Delete `canopyCache` and `loadCanopy()` (the in-memory JSON load).
2. Add shard access: `SHARD_CELL_M = 500`, closed-form lon/lat -> EPSG:3857 ->
   cell key, `loadShard()` reading `${SHARD_BASE}/${cell}.json` via `fetch`
   (prod, `SHARD_BASE` an https URL from `CANOPY_SHARD_BASE`) or `readFileSync`
   (dev, local dir), 32-entry LRU, 404-on-missing-shard -> null.
3. Replace `findParcel` with the async sharded version (same `pointInParcel`
   ray-casting, unchanged). One shard read per request.
4. Replace `parcelById` with async index-backed version using the
   `parcel_index.json` id->cell map (fetch once per cold start, ~14.5 MB in
   memory); `src/app/mcp/route.ts` must `await` it.
5. 404 semantics: bundle `data/city_boundary.json` (simplified ward union,
   10 KB at 50 m tolerance); `screenAddress` becomes geocode (unchanged) ->
   outside-Toronto 404 -> `await findParcel` -> no-parcel 404
   ("no canopy data for this location"). Replace `PILOT_SCOPE` with the
   city-wide scope string in `route.ts`, `mcp/route.ts`, and the openapi
   example; keep the `pilot_scope` field name.
6. `buildScreenPayload`: no changes (it consumes one `ParcelCanopy` record;
   the shard returns exactly that; proven 20/20 byte-identical).
7. Follow-ups outside this task: `src/app/api/download/route.ts` calls
   `loadCanopy()` to dump the whole dataset; at city scale it must serve
   pre-generated per-ward static CSV/GeoJSON from object storage instead of
   loading 400 MB. If the compact record layout is adopted, add a
   `fromCompact()` expander after fetch.

## Files

- `scripts/probe_wcs_coverage.py`, `data/coverage_probe.json` (gitignored)
- `scripts/extract_parcels_city.py`, `data/parcels_toronto/` (gitignored,
  25 ward shards + `unplaced.json` + `manifest.json`)
- `scripts/proto_api/` - `build_shards.mjs`, `lookup.mjs`, `bench.mjs`,
  `build_sqlite.mjs`, `sqlite_lookup.mjs`, `make_compact.mjs`,
  `canopy_city_proposal.ts`; prototype artifacts `data/proto_shards/`,
  `data/proto_parcels.db` (gitignored)
- Sibling-worker note: at ~23:38 during this work the sibling rewrote
  `data/parcel_canopy_ward12.json` with the fixed building mask (22.13 MB ->
  21.91 MB); prototype shards were rebuilt from the new file and all
  measurements above are against it.
