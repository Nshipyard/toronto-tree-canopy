# data/ directory

- `sample-parcels.geojson` — SYNTHETIC sample: 5 plausible parcels near 407 Arlington Ave
  for UI/API development. Hand it to the app when the pilot dataset is missing.
- `accuracy.json` — SAMPLE placeholder (`"sample": true`). **Owned by the pilot pipeline
  agent**, which will overwrite it with measured detection F1 and calibration R2 from
  the Ward 12 pilot. Do not treat the current numbers as measured.
- `parcels-ward12.geojson` — owned by the pilot pipeline agent (real pilot data, not yet
  delivered). The app prefers it over `sample-parcels.geojson` whenever it exists.
- `METHOD_NOTES.md` — owned by the pilot pipeline agent.

Ward boundary working files (`wards_dump.geojson`, `ward-2952.geojson`,
`ward12_geometry.txt`, `chips/`, `qa-tiles/`) are pipeline inputs, not app data.
