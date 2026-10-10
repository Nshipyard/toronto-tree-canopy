# Toronto Tree Canopy — Design Brief

Public Nshipyard project. Repo: `Nshipyard/toronto-tree-canopy`.
Author: Richardson Dackam. Licence: open data + MIT code.

## 1. Problem

A builder evaluating a Toronto lot cannot answer "will trees block my build" from open data.
The binding constraint is the Private Tree By-law (Municipal Code Chapter 813, Article III):
any private tree 30 cm or more in trunk diameter (DBH, measured at 1.4 m) needs a City permit
before it is injured or removed. September 2026 amendments added a "Distinctive Tree" tier
above 61 cm DBH with stronger protections. Construction-related removal permits cost
$436.39 per tree (2026 fee schedule), and the application site plan must show ALL trees
30 cm and up on the property AND on adjacent properties within 6 m of the boundary.

Private trees are invisible in open data: no inventory, no permit dataset (only Community
Council PDFs). The City's Street Tree Data (688,335 records, live) covers only city-owned
road-allowance trees, the wrong trees for the builder's question. Toronto Build Check's
tree section is honest about this ("weak evidence") and needs a stronger signal.

No commercial product sells permit-ready tree detection for Toronto builders. ArborNote
($240/mo) and QuoteIQ ($75/mo) are arborist estimating aids; Arboair/Overstory/AiDash are
enterprise utility tools with unpublished pricing. The "will trees block my build" question
is unowned.

## 2. Product

An AI-derived per-parcel tree screening dataset plus lookup tool, built from open inputs:

1. **Imagery**: City of Toronto orthorectified aerial imagery, 8 cm resolution, 2022 vintage
   (archive back to 2015), via the City's ArcGIS MapServer export. Free, open licence.
2. **Detection**: DeepForest (MIT, RetinaNet, NEON pre-trained weights) fine-tuned on Toronto
   orthos for individual crown delineation. Published accuracy for this job: F1 ~0.76 at
   10 cm (Beloiu et al. 2023); expect 0.64-0.93 depending on species/site. Instance
   delineation is the hard part; per-tree counts carry a stated error bar.
3. **Calibration**: the 688k street-tree inventory (species + measured DBH + approximate
   position) is the labeled training set. Fit crown-diameter to DBH allometry PER SPECIES
   on urban trees only. Species-specific urban equations reach R² 0.91-0.96 (Martin et al.
   2012, oaks); generic equations are far worse (R² < 0.6). Never use forest-derived
   allometry on urban trees (open-grown crowns are much wider per unit DBH).
4. **Parcel join**: intersect crowns with parcel polygons (reuse Nshipyard/toronto-parcel-spine
   TOP-<PARCELID> polygons, 498,477 parcels). Roll up per parcel AND a 6 m neighbour buffer,
   matching the by-law's site-plan rule.

### Output schema (per parcel)

- Detected crowns: polygon, crown diameter (m), estimated DBH with 95% prediction interval
- `p_ge_30cm`: probability trunk clears the 30 cm permit threshold
- `p_gt_61cm`: probability trunk clears the 61 cm Distinctive tier
- Parcel rollup: crown count, canopy percent, P(any crown ≥30cm), P(any distinctive)
- `imagery_vintage`: "2022" stamped on every record (a tree cut in 2024 is a false positive)
- Species: do NOT guess species from RGB. Use broadleaf/conifer split if reliable, else a
  generic urban allometry with wider intervals. State the interval, not a point estimate.

### Honesty constraints (non-negotiable)

- Screening signal only. The product NEVER says "permit required"; it says "3 likely-mature
  crowns on this lot, get an arborist before planning around them."
- Every number carries its vintage and its uncertainty. Detection F1 and calibration R² are
  published in the README and the UI, measured on the pilot, not cited from papers.
- Imagery currency caveat on every result: removals after the vintage are invisible.

## 3. Audience and design

Primary: builders, architects, developers and investors evaluating Toronto lots (the same
audience as Toronto Build Check). They get a per-address lookup with a plain-English
verdict: how many likely-mature crowns, the probability any clears 30 cm / 61 cm, canopy
percent, and what to do next (arborist report, permit fee exposure at $436.39/tree).

Secondary: arborists (pre-screening before a site visit), urban-forestry researchers,
AI agents via MCP.

## 4. App (Nshipyard family template)

- Next.js 16, EN/FR, red/paper civic theme, "Open Nshipyard" eyebrow + footer wordmark
- Explorer: address search (reuse the /api/suggest pattern: CKAN address-points typeahead),
  crown map overlay on parcels, per-parcel screening card
- REST: `GET /api/v1/screen?address=…` returning the schema above; `GET /api/openapi.json`
  (OpenAPI 3.1); `POST /mcp` (Streamable HTTP: `canopy_screen`, `parcel_crowns`)
- McpConnect tab block (ChatGPT / Claude / Claude Code / CLI / Other), same component pattern
- Downloadable dataset: per-parcel GeoJSON + CSV
- README: methodology, measured accuracy, imagery vintage, limitations, screenshots,
  author section (Richardson Dackam + X/GitHub links)

## 5. Pilot, then expand

Pilot on ONE residential ward first (suggest Ward 12 Davenport, mixed housing + mature
trees, matches Build Check's example addresses). The pilot must MEASURE, not assume:
detection F1 against a hand-labeled tile sample, calibration R² per species group against
held-out street trees. Ship the pilot dataset + the ward-parallel pipeline; expand
ward-by-ward. Full city at 8 cm is ~98B pixels; run inference at 25-50 cm (sufficient for
crowns) and keep 8 cm for QA tiles.

## 6. Build Check integration (separate step, after deploy)

Toronto Build Check's tree section calls `GET https://trees.canada.nshipyard.com/api/v1/screen?address=…`
and renders: likely-mature crown count, P(any ≥30cm), P(any distinctive), canopy percent,
imagery vintage, plus the existing street-tree lookup and ravine flag. The "weak evidence"
framing upgrades to a quantified screening signal with stated uncertainty.

## 7. Research sources

- Detection: DeepForest (Weecology, MIT); Beloiu et al. 2023 Remote Sensing 15(5):1463
  (F1 0.76 at 10 cm, training data on Zenodo); OAM-TCD benchmark (NeurIPS 2024);
  Detectree2 (Ball et al. 2023); Restor tcd pipeline.
- Allometry: Martin et al. 2012 (urban oaks, R² 0.91-0.96); Peper et al. 2001 (street trees
  incl. silver maple, R² > 0.80); Lockhart et al. 2005 (crown radius from imagery to DBH);
  Kwon et al. 2024 (end-to-end aerial-photo to DBH pipeline); Coombes et al. 2019.
- By-law: toronto.ca "When to Apply For a Tree or Ravine Permit" (Jan 2026); "How to Apply
  for a Tree or Ravine Permit" (Aug 2026); Application to Injure or Remove Trees form
  41-0064 (2026 fee schedule); Council item 2026.IE27.8 Tree By-law Review (Distinctive
  Tree tier, adopted Mar 2026).
- Inputs: Toronto Open Data "Web Map Services" (orthophoto ArcGIS services, 8 cm);
  Street Tree Data CKAN resource 3dafa392-c6ab-4f37-9bf9-21ddf7308eaf (688,335 records);
  toronto-parcel-spine (TOP-<PARCELID> polygons).
