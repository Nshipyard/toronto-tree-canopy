// Toronto Tree Canopy core: parcel canopy data loading, point-in-polygon
// lookup, and the /api/v1/screen payload builder.
//
// Track B (round 2): the screen serves MEASURED 2023 LiDAR canopy structure
// (1 m CHM from the NRCan HRDEM mosaic, TRCA GTA_2023) plus a mature-tree
// probability calibrated on the street-tree inventory. There is no crown
// detection in this track (round 1 detection arms failed: F1 0.023 / 0.000),
// so `crowns` is always an empty array, kept in the contract for a future
// segmentation win to fill without breaking clients.

import { readFileSync } from "fs";
import { join } from "path";
import { STRINGS, Lang } from "./i18n";
import { geocodeAddress } from "./ckan";

export interface ZoneMetrics {
  tall_canopy_m2_ge6: number;
  tall_canopy_m2_ge8: number;
  max_chm_m: number | null;
  canopy_pct_6: number;
  canopy_pct_8: number | null;
  p_any_ge_30cm: number;
  p_any_distinctive: number;
  peak_count: number;
}

export interface ParcelCanopy {
  parcel_id: string;
  address: string;
  area_m2: number;
  centroid_4326: [number, number];
  bbox_4326: [number, number, number, number];
  ring_4326: [number, number][];
  lot: ZoneMetrics;
  buffer_6m: ZoneMetrics;
  imagery_vintage: string;
}

export interface CalibrationDoc {
  vintage: string;
  generic_ge_30: { train_auc: number; cv_auc_mean: number; cv_auc_sd: number };
  generic_gt_61: { train_auc: number; cv_auc_mean: number; cv_auc_sd: number };
  n_trees: number;
}

let canopyCache: Record<string, ParcelCanopy> | null = null;
let calCache: CalibrationDoc | null = null;

export function loadCanopy(): Record<string, ParcelCanopy> {
  if (!canopyCache) {
    const raw = readFileSync(
      join(process.cwd(), "data", "parcel_canopy_ward12.json"),
      "utf-8",
    );
    canopyCache = JSON.parse(raw) as Record<string, ParcelCanopy>;
  }
  return canopyCache;
}

export function loadCalibration(): CalibrationDoc {
  if (!calCache) {
    calCache = JSON.parse(
      readFileSync(join(process.cwd(), "data", "calibration_lidar.json"), "utf-8"),
    ) as CalibrationDoc;
  }
  return calCache;
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

export function findParcel(lon: number, lat: number): ParcelCanopy | null {
  const all = loadCanopy();
  for (const id of Object.keys(all)) {
    const p = all[id];
    const b = p.bbox_4326;
    if (lon < b[0] || lon > b[2] || lat < b[1] || lat > b[3]) continue;
    if (pointInParcel(lon, lat, p.ring_4326)) return p;
  }
  return null;
}

export function parcelById(parcelId: string): ParcelCanopy | null {
  return loadCanopy()[parcelId] ?? null;
}

export interface ScreenPayload {
  address: string;
  parcel_id: string;
  parcel_polygon: [number, number][]; // parcel ring for the map
  imagery_vintage: string;
  sample: false;
  lot: {
    tall_canopy_m2_ge6: number;
    tall_canopy_m2_ge8: number;
    max_chm_m: number | null;
    canopy_pct: number; // tall canopy (>= 8 m) as % of parcel area
    p_any_ge_30cm: number;
    p_any_distinctive: number;
    crowns: never[]; // reserved: a future segmentation win fills this
  };
  neighbour_6m: {
    tall_canopy_m2_ge6: number;
    tall_canopy_m2_ge8: number;
    max_chm_m: number | null;
    p_any_ge_30cm: number;
    p_any_distinctive: number;
  };
  verdict: string;
  method: {
    vintage: string;
    calibration_auc: number;
    calibration_n: number;
    sample: false;
    note: string;
  };
  pilot_scope: string;
}

export const PILOT_SCOPE = "Ward 12 Davenport pilot";

function pct(p: number): string {
  return `${Math.round(p * 100)}%`;
}

function m2(v: number): string {
  return v >= 100 ? `${Math.round(v)}` : `${v.toFixed(1)}`;
}

export function buildScreenPayload(
  parcel: ParcelCanopy,
  address: string,
  lang: Lang,
): ScreenPayload {
  const t = STRINGS[lang];
  const v = t.verdict;
  const lot = parcel.lot;
  const buf = parcel.buffer_6m;
  const cal = loadCalibration();
  const verdict =
    lot.tall_canopy_m2_ge8 < 0.5
      ? v.noTallCanopy(
          pct(lot.p_any_ge_30cm),
          m2(buf.tall_canopy_m2_ge8),
          pct(buf.p_any_ge_30cm),
        )
      : v.withCanopy(
          m2(lot.tall_canopy_m2_ge8),
          `${lot.canopy_pct_8 ?? 0}`,
          lot.max_chm_m === null ? "–" : `${lot.max_chm_m}`,
          pct(lot.p_any_ge_30cm),
          pct(lot.p_any_distinctive),
          m2(buf.tall_canopy_m2_ge8),
          pct(buf.p_any_ge_30cm),
          lot.peak_count,
        );
  return {
    address,
    parcel_id: parcel.parcel_id,
    parcel_polygon: parcel.ring_4326,
    imagery_vintage: parcel.imagery_vintage,
    sample: false,
    lot: {
      tall_canopy_m2_ge6: lot.tall_canopy_m2_ge6,
      tall_canopy_m2_ge8: lot.tall_canopy_m2_ge8,
      max_chm_m: lot.max_chm_m,
      canopy_pct: lot.canopy_pct_8 ?? 0,
      p_any_ge_30cm: lot.p_any_ge_30cm,
      p_any_distinctive: lot.p_any_distinctive,
      crowns: [],
    },
    neighbour_6m: {
      tall_canopy_m2_ge6: buf.tall_canopy_m2_ge6,
      tall_canopy_m2_ge8: buf.tall_canopy_m2_ge8,
      max_chm_m: buf.max_chm_m,
      p_any_ge_30cm: buf.p_any_ge_30cm,
      p_any_distinctive: buf.p_any_distinctive,
    },
    verdict,
    method: {
      vintage: cal.vintage,
      calibration_auc: cal.generic_ge_30.cv_auc_mean,
      calibration_n: cal.n_trees,
      sample: false,
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
    super(
      typeof body === "object" && body !== null && "error" in body
        ? String((body as { error: unknown }).error)
        : "screen error",
    );
  }
}

// Resolve address -> parcel -> payload. Throws ScreenError with status/body.
export async function screenAddress(raw: string, lang: Lang): Promise<ScreenPayload> {
  const t = STRINGS[lang];
  const geo = await geocodeAddress(raw).catch((e: Error) => {
    if (e.message === "CKAN_UNAVAILABLE")
      throw new ScreenError(503, { error: t.screen.lookupError });
    throw e;
  });
  if (!geo)
    throw new ScreenError(404, { error: t.screen.notFound, pilot_scope: PILOT_SCOPE });
  const parcel = findParcel(geo.lon, geo.lat);
  if (!parcel) {
    throw new ScreenError(404, {
      error: "pilot covers Ward 12 (Davenport) only",
      pilot_scope: PILOT_SCOPE,
    });
  }
  return buildScreenPayload(parcel, geo.address, lang);
}
