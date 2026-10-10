import { NextResponse } from "next/server";

const crownSchema = {
  type: "object",
  properties: {
    polygon: {
      type: "array",
      description: "Crown outline ring as [lon, lat] pairs (WGS84)",
      items: { type: "array", items: { type: "number" }, minItems: 2, maxItems: 2 },
    },
    crown_diameter_m: { type: "number", description: "Detected crown diameter in metres" },
    dbh_est_cm: { type: "number", description: "Estimated trunk diameter at 1.4 m, centimetres" },
    dbh_pi95: {
      type: "array",
      description: "95% prediction interval [lo, hi] for DBH in centimetres",
      items: { type: "number" },
      minItems: 2,
      maxItems: 2,
    },
    p_ge_30cm: { type: "number", minimum: 0, maximum: 1, description: "Probability the trunk clears the 30 cm permit threshold" },
    p_gt_61cm: { type: "number", minimum: 0, maximum: 1, description: "Probability the trunk clears the 61 cm Distinctive tier" },
  },
  required: ["polygon", "crown_diameter_m", "dbh_est_cm", "dbh_pi95", "p_ge_30cm", "p_gt_61cm"],
};

const spec = {
  openapi: "3.1.0",
  info: {
    title: "Toronto Tree Canopy API",
    version: "0.1.0",
    description:
      "Per-parcel tree screening for Toronto builders, architects, and investors, from the Ward 12 (Davenport) pilot: crown polygons detected on City of Toronto 2022 orthorectified aerial imagery, estimated trunk diameters with 95% prediction intervals, and per-crown probabilities of clearing the Private Tree By-law thresholds (30 cm permit threshold; 61 cm Distinctive tier). Crowns are rolled up per parcel and over the 6 m neighbour buffer, matching the by-law site-plan rule. Screening signal only; not a permit determination.",
    license: { name: "MIT" },
  },
  servers: [{ url: "/api" }],
  paths: {
    "/v1/screen": {
      get: {
        summary: "Tree screening for one Toronto address",
        description:
          "Resolves the address against the City's Address Points, runs point-in-polygon against the pilot parcels, and returns the per-parcel screening payload. Outside the pilot parcels the call returns HTTP 404.",
        parameters: [
          { name: "address", in: "query", required: true, schema: { type: "string" }, example: "407 Arlington Ave" },
          { name: "lang", in: "query", required: false, schema: { type: "string", enum: ["en", "fr"] }, example: "en" },
        ],
        responses: {
          "200": {
            description: "The screening payload: address, parcel ID, imagery vintage, lot crowns with DBH estimates and threshold probabilities, the 6 m neighbour buffer, a plain-English verdict, the method note with detection F1, and the pilot scope.",
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  properties: {
                    address: { type: "string" },
                    parcel_id: { type: "string", example: "TOP-W12-0103" },
                    imagery_vintage: { type: "string", example: "2022" },
                    lot: {
                      type: "object",
                      properties: {
                        crown_count: { type: "integer" },
                        canopy_pct: { type: "number" },
                        p_any_ge_30cm: { type: "number" },
                        p_any_distinctive: { type: "number" },
                        crowns: { type: "array", items: crownSchema },
                      },
                    },
                    neighbour_6m: {
                      type: "object",
                      properties: {
                        crown_count: { type: "integer" },
                        p_any_ge_30cm: { type: "number" },
                        p_any_distinctive: { type: "number" },
                      },
                    },
                    verdict: { type: "string", description: "Plain-English screening sentence. Never a permit determination." },
                    method: {
                      type: "object",
                      properties: {
                        detection_f1: { type: "number" },
                        sample: { type: "boolean", description: "True while the pilot has not measured its own accuracy yet" },
                        note: { type: "string", example: "Screening signal only; not a permit determination." },
                      },
                    },
                    pilot_scope: { type: "string", example: "Ward 12 Davenport pilot" },
                  },
                },
              },
            },
          },
          "400": { description: "Missing address" },
          "404": {
            description: "Address not found, or address outside the pilot parcels. Body carries the pilot scope.",
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  properties: {
                    error: { type: "string", example: "pilot covers Ward 12 (Davenport) only" },
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
          { name: "q", in: "query", required: true, schema: { type: "string" }, example: "407 Arlington" },
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
        summary: "Download the pilot parcel dataset",
        parameters: [
          { name: "format", in: "query", required: false, schema: { type: "string", enum: ["geojson", "csv"] }, example: "geojson" },
        ],
        responses: {
          "200": { description: "The dataset file: GeoJSON (default) or CSV, one row per parcel with its crowns" },
        },
      },
    },
  },
};

export async function GET() {
  return NextResponse.json(spec);
}
