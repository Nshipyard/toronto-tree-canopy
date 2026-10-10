# LiDAR / elevation data for the Toronto Tree Canopy project

Hunt completed 2026-10-10. Goal: open 3D elevation over Ward 12 (Davenport) to test
height-based crown detection after RGB failed on leaf-off spring orthophotos (F1 0.023).

## WINNER: NRCan HRDEM Mosaic WCS (DSM + DTM, ~1 m)

- **What:** High Resolution Digital Elevation Model (HRDEM) Mosaic, CanElevation series,
  Natural Resources Canada. Two coverages: `dsm` (digital surface model, first return)
  and `dtm` (digital terrain model, bare earth).
- **Toronto source:** TRCA `GTA_2023` project (Toronto and Region Conservation Authority,
  2023 airborne LiDAR), ingested into the federal mosaic. Ontario added ~259,000 km2 of
  single-photon LiDAR to HRDEM in 2023-2024; 99 of Canada's 100 largest cities are covered.
- **Vintage:** 2023 (Toronto tile set `dsm_mns/1m/TRCA/GTA_2023`, `dtm_mnt/1m/TRCA/GTA_2023`).
- **Resolution:** 1 m nominal. The WCS serves EPSG:4326 at 1.3216e-05 deg
  (~1.47 m N-S x ~1.06 m E-W at Toronto's latitude).
- **Vertical datum:** CGVD2013. Nodata: -32767 (source), -9999 (our CHM).
- **License:** Open Government Licence - Canada (free, commercial use allowed with attribution).
- **Endpoint:** `https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic`
  (WCS 1.1.1, `Identifier=dsm` / `Identifier=dtm`, `format=image/geotiff`).

### Sample pulled for Ward 12 (this directory)

Sample window: lon -79.47..-79.44, lat 43.64..43.67 (south-west ~8 km2 of Ward 12),
fetched 2026-10-10 as 4 WCS chunks per layer (0.015 deg each; full-ward single
requests return HTTP 500, so chunk).

| file | description |
|---|---|
| `wcs/ward12_dsm.tif` | DSM mosaic, 2270x2270 float32, EPSG:4326 |
| `wcs/ward12_dtm.tif` | DTM mosaic, 2270x2270 float32, EPSG:4326 |
| `wcs/ward12_chm.tif` | CHM = DSM - DTM, float32, nodata -9999, clipped to [-2, 60] m |
| `wcs/ward12_chm_preview.png` | side-by-side DSM / CHM rendering |
| `wcs/chunks/` | raw per-chunk WCS downloads (13 DSM + 4 DTM; extra DSM chunks are bonus Ward 12 coverage) |

Reproduce:

```
# one chunk (WCS 1.1.1; Identifier is singular with capital I)
curl -o dsm.tif "https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic?service=WCS&request=GetCoverage&version=1.1.1&Identifier=dsm&boundingbox=43.64,-79.47,43.655,-79.455,urn:ogc:def:crs:EPSG::4326&format=image/geotiff"
```

Scripts: `fetch_ward12.py` (chunked download), `build_chm.py` (mosaic + CHM + PNG + stats).
Needs the repo venv (`../.venv`: rasterio, numpy, matplotlib, scipy).

### Validation (measured, not assumed)

- Flat-surface check (roads/parking lots, DSM local std < 0.25 m): median CHM **0.06 m**,
  so the mosaic DSM and DTM are vertically consistent; CHM is unbiased on bare ground.
- CHM over sample: p1 0.0 m, median 5.8 m, p99 27.8 m. 68.7% of pixels > 2 m
  (buildings + trees in dense urban fabric).
- Tree-like pixels (CHM 8-25 m with rough surface): 2.7% of sample, median height
  **11.1 m**, p90 18.1 m. A 200x200 px window peaked at 28.3 m.
- Visual: streets/rail corridor read ~0 (white), buildings are crisp bright blocks,
  a large wooded patch (bottom-left of preview) reads dark green. No striping or
  tile-edge artifacts visible.

Implication for the pilot: height separates ground (~0 m), houses (~6-10 m, flat tops)
and mature trees (~8-25 m, rough tops) cleanly where RGB failed. CHM + roughness is
the feature set to try first.

### Gotchas found while hunting

- Raw 1 m GeoTIFF tiles on `download-telecharger.services.geo.ca` (DSM `dsm_1m_utm17_e_*`,
  DTM `dtm_1m_utm17_e_*`, 82 tiles each, UTM 17) return **HTTP 403** from this network
  for `.tif` (PDFs and directory listings work). The WCS route above works fine.
- WCS `GetCoverage` needs `Identifier=` (singular); `identifiers=` 400s.
  Full Ward 12 in one request 500s (GeoTrellis backend); keep requests <= ~0.015 deg.
  4 parallel chunk requests were fine.

## Other sources checked

1. **City of Toronto Open Data (CKAN)** `ckan0.cf.opendata.inter.prod-toronto.ca`:
   searches for `lidar`, `elevation`, `DSM`, `DEM`, `DTM`, `contour`, `terrain`,
   `bare-earth`. Found: **Triangular Irregular Network (TIN)**
   (`triangular-irregular-network-tin`): polygon elevation derived from **2023 LiDAR
   2.5 m bare-earth** source, SHP download, NAD83(CSRS)/MTM10 + CGVD2013. DTM only,
   no surface model, so no CHM possible from it. `SolarTO` confirms the City holds
   LiDAR but publishes only the derived solar-potential vectors, not the DSM.
2. **City ArcGIS** `gis.toronto.ca/arcgis/rest/services` (48 services; layer lists for
   cot_geospatial, 2, 6, 7, 8, 10): vector layers only (wards, roads, transit).
   `basemap/cot_LiDAR_2015_Hillshade_BareEarth` and `..._FullFeature` are **rendered
   hillshade tile caches** (2015 LiDAR), not elevation values.
3. **Ontario GeoHub / data.ontario.ca**: province publishes "Ontario Classified Point
   Cloud (Lidar-Derived)", "Ontario Digital Surface Model (Lidar-Derived)" and
   "...Terrain Model (Lidar-Derived)" (1 km LAZ tiles / raster), plus the
   **Provincial DEM** (PDEM, bare-earth DTM only, `ws.gisetl.lrc.gov.on.ca` packages).
   These are the same Ontario single-photon LiDAR that feeds the federal HRDEM above;
   the NRCan WCS was the working download path, so it was used.
4. **Federal (NRCan)**: HRDEM tile FTP exists (see gotchas); CDEM (~20 m) too coarse
   for crowns. The **HRDEM Mosaic WCS** is the usable product.
5. Not needed after the WCS find: university/conservation-authority portals
   (TRCA is the `TRCA/GTA_2023` provider inside HRDEM already).

## Commercial landscape

Not researched: open data was found and validated, so no commercial fallback was needed.
