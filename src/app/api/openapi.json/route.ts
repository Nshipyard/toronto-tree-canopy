import { NextResponse } from "next/server";

const spec = {
  openapi: "3.1.0",
  info: {
    title: "Toronto Tree Canopy API",
    version: "0.2.0",
    description:
      "Per-parcel tree screening for Toronto builders, architects, and investors: tall-canopy structure measured from 2023 airborne LiDAR (1 m canopy height model, NRCan HRDEM mosaic, TRCA GTA_2023, City building footprints masked with a 2 m buffer), per-parcel tall-canopy area at the 6 m and 8 m thresholds, max height, canopy percent, and calibrated probabilities of a mature tree (30 cm permit threshold) and a Distinctive tree (61 cm tier), for the lot and the 6 m neighbour buffer matching the by-law site-plan rule. Covers all 498,463 Toronto parcels. The crowns array is reserved for a future segmentation win and currently empty. Screening signal only; not a permit determination.",
    license: { name: "MIT" },
  },
  servers: [{ url: "/api" }],
  paths: {
    "/v1/screen": {
      get: {
        summary: "Tree screening for one Toronto address",
        description:
          "Resolves the address against the City's Address Points, runs point-in-polygon against the city-wide 500 m parcel shards, and returns the per-parcel LiDAR screening payload. Outside Toronto the call returns HTTP 404.",
        parameters: [
          { name: "address", in: "query", required: true, schema: { type: "string" }, example: "1843 Eglinton Ave W" },
          { name: "lang", in: "query", required: false, schema: { type: "string", enum: ["en", "fr"] }, example: "en" },
        ],
        responses: {
          "200": {
            description: "The screening payload: address, parcel ID, 2023 LiDAR vintage, lot and 6 m neighbour-buffer tall-canopy metrics, calibrated mature-tree probabilities, an empty crowns array reserved for future segmentation, a plain-English verdict, and the method note with calibration AUC.",
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  properties: {
                    address: { type: "string" },
                    parcel_id: { type: "string", example: "TOP-5293472" },
                    parcel_polygon: {
                      type: "array",
                      description: "Parcel boundary ring as [lon, lat] pairs (WGS84), for the map",
                      items: { type: "array", items: { type: "number" }, minItems: 2, maxItems: 2 },
                    },
                    imagery_vintage: { type: "string", example: "2023 LiDAR" },
                    sample: { type: "boolean", example: false },
                    lot: {
                      type: "object",
                      properties: {
                        tall_canopy_m2_ge6: { type: "number", description: "Lot area with LiDAR surface 6 m or taller, square metres" },
                        tall_canopy_m2_ge8: { type: "number", description: "Lot area with LiDAR surface 8 m or taller, square metres" },
                        max_chm_m: { type: "number", description: "Max canopy height model value on the lot, metres" },
                        canopy_pct: { type: "number", description: "Tall canopy (8 m and up) as percent of parcel area" },
                        p_any_ge_30cm: { type: "number", minimum: 0, maximum: 1, description: "Calibrated probability at least one mature tree (trunk 30 cm or more) stands on the lot" },
                        p_any_distinctive: { type: "number", minimum: 0, maximum: 1, description: "Calibrated probability at least one Distinctive tree (trunk over 61 cm) stands on the lot" },
                        crowns: {
                          type: "array",
                          description: "Reserved for a future segmentation win; currently always empty",
                          items: { type: "object" },
                        },
                      },
                    },
                    neighbour_6m: {
                      type: "object",
                      description: "The 6 m band around the lot boundary (by-law site-plan rule)",
                      properties: {
                        tall_canopy_m2_ge6: { type: "number" },
                        tall_canopy_m2_ge8: { type: "number" },
                        max_chm_m: { type: "number" },
                        p_any_ge_30cm: { type: "number", minimum: 0, maximum: 1 },
                        p_any_distinctive: { type: "number", minimum: 0, maximum: 1 },
                      },
                    },
                    verdict: { type: "string", description: "Plain-English screening sentence. Never a permit determination." },
                    method: {
                      type: "object",
                      properties: {
                        vintage: { type: "string", example: "2023 LiDAR (NRCan HRDEM mosaic, TRCA GTA_2023)" },
                        calibration_auc: { type: "number", description: "Mature-tree calibration AUC on held-out street trees" },
                        calibration_n: { type: "integer", description: "Street trees the calibration was fit on" },
                        sample: { type: "boolean", example: false },
                        note: { type: "string", example: "Screening signal only; not a permit determination." },
                      },
                    },
                    pilot_scope: { type: "string", example: "Toronto-wide 2023 LiDAR canopy screen" },
                  },
                },
              },
            },
          },
          "400": { description: "Missing address" },
          "404": {
            description: "Address not found, address outside Toronto, or no parcel at the location. Body carries the scope.",
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  properties: {
                    error: { type: "string", example: "This address falls outside Toronto. The screen covers Toronto parcels only." },
                    pilot_scope: { type: "string" },
                  },
                },
              },
            },
          },
        },
      },
    },
    "/suggest": {
      get: {
        summary: "Address typeahead backed by the City's Address Points",
        parameters: [
          { name: "q", in: "query", required: true, schema: { type: "string" }, example: "Eglinton Ave W" },
        ],
        responses: {
          "200": {
            description: "Suggestion strings; every suggestion resolves in /v1/screen.",
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  properties: { suggestions: { type: "array", items: { type: "string" } } },
                },
              },
            },
          },
        },
      },
    },
    "/download": {
      get: {
        summary: "Download the Toronto canopy dataset, one ward at a time",
        parameters: [
          { name: "format", in: "query", required: false, schema: { type: "string", enum: ["geojson", "csv"] }, example: "geojson" },
          { name: "ward", in: "query", required: true, schema: { type: "string", enum: ["01","02","03","04","05","06","07","08","09","10","11","12","13","14","15","16","17","18","19","20","21","22","23","24","25"] }, example: "09" },
        ],
        responses: {
          "200": { description: "The ward dataset file: GeoJSON (default, with parcel rings) or CSV (metrics only), one row per parcel with its LiDAR canopy metrics" },
        },
      },
    },
    "/v1/parcel-map": {
      get: {
        summary: "Server-rendered tall-canopy map for one parcel",
        description:
          "Renders a PNG on demand from the ward's building-masked 2023 LiDAR CHM: CHM-grayscale base, green tint where CHM is 8 m and up, parcel boundary, 6 m neighbour buffer (the image edge), a 10 m scale bar, and a caption band naming the sources. Long edge 1080 px.",
        parameters: [
          { name: "parcel_id", in: "query", required: true, schema: { type: "string" }, example: "TOP-5293472" },
        ],
        responses: {
          "200": { description: "The parcel map PNG" },
          "404": { description: "Unknown parcel ID" },
        },
      },
    },
  },
};

export async function GET() {
  return NextResponse.json(spec);
}
