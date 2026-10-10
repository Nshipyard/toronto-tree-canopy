// Toronto Tree Canopy core: parcel data loading, point-in-polygon lookup,
// and the /api/v1/screen payload builder.
//
// Data source: data/parcels-ward12.geojson when the pipeline has delivered
// it, else data/sample-parcels.geojson (synthetic, clearly marked).

import { readFileSync, existsSync } from "fs";
import { join } from "path";
import { STRINGS, Lang } from "./i18n";
import { geocodeAddress } from "./ckan";

export interface Crown {
  polygon: [number, number][]; // [[lon, lat], ...] ring
  crown_diameter_m: number;
  dbh_est_cm: number;
  dbh_pi95: [number, number];
  p_ge_30cm: number;
  p_gt_61cm: number;
}

export interface Neighbour6m {
  crown_count: number;
  p_any_ge_30cm: number;
  p_any_distinctive: number;
}

export interface Parcel {
  parcel_id: string;
  address: string;
  geometry: [number, number][]; // parcel ring, [lon, lat]
  crowns: Crown[];
  crown_count: number;
  canopy_pct: number;
  p_any_ge_30cm: number;
  p_any_distinctive: number;
  neighbour_6m: Neighbour6m;
  imagery_vintage: string;
}

interface RawCrown {
  polygon: [number, number][];
  crown_diameter_m: number;
  dbh_est_cm: number;
  dbh_pi95_lo: number;
  dbh_pi95_hi: number;
  p_ge_30cm: number;
  p_gt_61cm: number;
}

interface RawProps {
  parcel_id: string;
  address: string;
  crowns: RawCrown[];
  crown_count: number;
  canopy_pct: number;
  p_any_ge_30cm: number;
  p_any_distinctive: number;
  neighbour_6m: Neighbour6m;
  imagery_vintage: string;
}

interface FeatureCollection {
  features: {
    geometry: { type: string; coordinates: unknown };
    properties: RawProps;
  }[];
}

function extractRing(geometry: { type: string; coordinates: unknown }): [number, number][] | null {
  const c = geometry.coordinates;
  if (geometry.type === "Polygon" && Array.isArray(c)) {
    return (c as unknown[][])[0] as [number, number][];
  }
  if (geometry.type === "MultiPolygon" && Array.isArray(c)) {
    return ((c as unknown[][][])[0] as unknown[][])[0] as [number, number][];
  }
  return null;
}

function loadParcels(): { parcels: Parcel[]; sample: boolean } {
  const dir = join(process.cwd(), "data");
  const pilot = join(dir, "parcels-ward12.geojson");
  const sample = join(dir, "sample-parcels.geojson");
  const path = existsSync(pilot) ? pilot : sample;
  const doc = JSON.parse(readFileSync(path, "utf-8")) as FeatureCollection;
  const parcels: Parcel[] = [];
  for (const f of doc.features ?? []) {
    const ring = extractRing(f.geometry);
    if (!ring || !f.properties) continue;
    const p = f.properties;
    parcels.push({
      parcel_id: p.parcel_id,
      address: p.address,
      geometry: ring,
      crowns: (p.crowns ?? []).map((c) => ({
        polygon: c.polygon,
        crown_diameter_m: c.crown_diameter_m,
        dbh_est_cm: c.dbh_est_cm,
        dbh_pi95: [c.dbh_pi95_lo, c.dbh_pi95_hi] as [number, number],
        p_ge_30cm: c.p_ge_30cm,
        p_gt_61cm: c.p_gt_61cm,
      })),
      crown_count: p.crown_count,
      canopy_pct: p.canopy_pct,
      p_any_ge_30cm: p.p_any_ge_30cm,
      p_any_distinctive: p.p_any_distinctive,
      neighbour_6m: p.neighbour_6m,
      imagery_vintage: p.imagery_vintage,
    });
  }
  return { parcels, sample: path === sample };
}

// Ray-casting point-in-polygon on the parcel ring.
export function pointInParcel(lon: number, lat: number, ring: [number, number][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

export interface AccuracyDoc {
  detection_f1: number;
  calibration_r2_broadleaf: number;
  calibration_r2_conifer: number;
  imagery_vintage: string;
  sample: boolean;
}

export function loadAccuracy(): AccuracyDoc {
  const doc = JSON.parse(
    readFileSync(join(process.cwd(), "data", "accuracy.json"), "utf-8"),
  ) as AccuracyDoc;
  return doc;
}

export interface ScreenPayload {
  address: string;
  parcel_id: string;
  parcel_polygon: [number, number][]; // parcel ring for the map (additive to the API schema)
  imagery_vintage: string;
  sample: boolean;
  lot: {
    crown_count: number;
    canopy_pct: number;
    p_any_ge_30cm: number;
    p_any_distinctive: number;
    crowns: Crown[];
  };
  neighbour_6m: Neighbour6m;
  verdict: string;
  fee_line: string | null;
  method: { detection_f1: number; sample: boolean; note: string };
  pilot_scope: string;
}

export const PILOT_SCOPE = "Ward 12 Davenport pilot";

function pct(p: number): string {
  return `${Math.round(p * 100)}%`;
}

export function buildScreenPayload(parcel: Parcel, address: string, lang: Lang, sample: boolean): ScreenPayload {
  const t = STRINGS[lang];
  const v = t.verdict;
  const nb = parcel.neighbour_6m.crown_count;
  const verdict =
    parcel.crown_count === 0
      ? v.noCrowns(nb)
      : v.withCrowns(
          parcel.crown_count,
          `${parcel.canopy_pct}%`,
          pct(parcel.p_any_ge_30cm),
          pct(parcel.p_any_distinctive),
          nb,
        );
  const likelyMature = parcel.crowns.filter((c) => c.p_ge_30cm >= 0.5).length;
  const fee_line =
    likelyMature > 0
      ? t.screen.feeLine(likelyMature, `$${(likelyMature * 436.39).toFixed(2)}`)
      : null;
  const acc = loadAccuracy();
  return {
    address,
    parcel_id: parcel.parcel_id,
    parcel_polygon: parcel.geometry,
    imagery_vintage: parcel.imagery_vintage,
    sample,
    lot: {
      crown_count: parcel.crown_count,
      canopy_pct: parcel.canopy_pct,
      p_any_ge_30cm: parcel.p_any_ge_30cm,
      p_any_distinctive: parcel.p_any_distinctive,
      crowns: parcel.crowns,
    },
    neighbour_6m: parcel.neighbour_6m,
    verdict,
    fee_line,
    method: {
      detection_f1: acc.detection_f1,
      sample: acc.sample,
      note: t.screen.honesty,
    },
    pilot_scope: PILOT_SCOPE,
  };
}

export class ScreenError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(typeof body === "object" && body !== null && "error" in body ? String((body as { error: unknown }).error) : "screen error");
  }
}

// Resolve address -> parcel -> payload. Throws ScreenError with status/body.
export async function screenAddress(raw: string, lang: Lang): Promise<ScreenPayload> {
  const t = STRINGS[lang];
  const geo = await geocodeAddress(raw).catch((e: Error) => {
    if (e.message === "CKAN_UNAVAILABLE") throw new ScreenError(503, { error: t.screen.lookupError });
    throw e;
  });
  if (!geo) throw new ScreenError(404, { error: t.screen.notFound, pilot_scope: PILOT_SCOPE });
  const { parcels, sample } = loadParcels();
  const parcel = parcels.find((p) => pointInParcel(geo.lon, geo.lat, p.geometry));
  if (!parcel) {
    throw new ScreenError(404, { error: "pilot covers Ward 12 (Davenport) only", pilot_scope: PILOT_SCOPE });
  }
  return buildScreenPayload(parcel, geo.address, lang, sample);
}

export function parcelById(parcelId: string): { parcel: Parcel; sample: boolean } | null {
  const { parcels, sample } = loadParcels();
  const parcel = parcels.find((p) => p.parcel_id === parcelId);
  return parcel ? { parcel, sample } : null;
}
