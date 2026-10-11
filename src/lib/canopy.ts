// Toronto Tree Canopy core: sharded parcel lookup, point-in-polygon, and the
// /api/v1/screen payload builder.
//
// City-wide (Oct 2026): parcel records live in 500 m EPSG:3857 grid shards
// (data/shards/<cx>_<cy>.json), one shard fetched per request over HTTP
// (jsDelivr over the GitHub repo; CANOPY_SHARD_BASE overrides, with a local
// data/shards dir fallback for `next dev`). A 32-entry LRU reuses shards on
// warm instances. A 14.5 MB parcel_id -> cell index (parcel_index.json,
// fetched once per cold start) backs parcelById. A bundled simplified city
// boundary polygon (data/city_boundary.json) gives honest 404s: outside
// Toronto vs inside but uncovered.
//
// The screen serves MEASURED 2023 LiDAR canopy structure (1 m CHM from the
// NRCan HRDEM mosaic, TRCA GTA_2023, City building footprints masked with a
// 2 m buffer) plus a mature-tree probability calibrated on the City's
// street-tree inventory. There is no crown detection in this track, so
// `crowns` is always an empty array, kept in the contract for a future
// segmentation win to fill without breaking clients.

import { readFileSync, existsSync } from "fs";
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
  ward: string; // 25-ward model ward code ("01".."25"); Davenport is "09"
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

const SHARD_CELL_M = 500;
const WEB_MERC = 20037508.34;
// CANOPY_SHARD_BASE wins when set (pin a commit SHA there for immutable
// deploys). Otherwise: jsDelivr over this repo in production, the local
// data/shards dir in dev.
export function shardBase(): string {
  if (process.env.CANOPY_SHARD_BASE) return process.env.CANOPY_SHARD_BASE;
  if (process.env.NODE_ENV === "production")
    return "https://cdn.jsdelivr.net/gh/Nshipyard/toronto-tree-canopy@main/data/shards";
  return join(process.cwd(), "data", "shards");
}
// COGs are pinned to the commit that re-encoded them ZSTD -> DEFLATE
// (the geotiff npm package cannot decode compression 50000). jsDelivr keeps
// serving stale per-file copies of branch URLs after a push, and its purge
// endpoint does not reliably clear them, so the COGs use an immutable commit
// URL instead of the moving @main branch.
const COGS_PIN = "ee4d3671edda03d604a5e7860b03a7b3305e480b";
export function cogBase(): string {
  if (process.env.CANOPY_COG_BASE) return process.env.CANOPY_COG_BASE;
  const sb = shardBase();
  if (sb.startsWith("http"))
    return sb.replace(/\/shards\/?$/, "/cogs").replace("@main", `@${COGS_PIN}`);
  return join(process.cwd(), "data", "cogs");
}
const SHARD_CACHE_MAX = 32;

let calCache: CalibrationDoc | null = null;

export function loadCalibration(): CalibrationDoc {
  if (!calCache) {
    calCache = JSON.parse(
      readFileSync(join(process.cwd(), "data", "calibration_lidar.json"), "utf-8"),
    ) as CalibrationDoc;
  }
  return calCache;
}

// Closed-form lon/lat -> 500 m EPSG:3857 grid cell key. No dependency, no I/O.
export function cellFor(lon: number, lat: number): string {
  const x = (lon * WEB_MERC) / 180;
  const y =
    Math.log(Math.tan(((90 + lat) * Math.PI) / 360)) * (WEB_MERC / Math.PI);
  return `${Math.floor(x / SHARD_CELL_M)}_${Math.floor(y / SHARD_CELL_M)}`;
}

const shardCache = new Map<string, ParcelCanopy[]>();

// One shard read per call. Parcels whose bbox spans cells are stored in every
// cell it touches, so the cell of the point always holds every parcel covering
// it. A missing shard file means no parcels there: null, not an error.
async function loadShard(cell: string): Promise<ParcelCanopy[] | null> {
  const hit = shardCache.get(cell);
  if (hit) return hit;
  const base = shardBase();
  let records: ParcelCanopy[];
  if (base.startsWith("http")) {
    const res = await fetch(`${base}/${cell}.json`);
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`shard fetch failed: ${res.status}`);
    records = (await res.json()) as ParcelCanopy[];
  } else {
    const fn = join(base, `${cell}.json`);
    if (!existsSync(fn)) return null;
    records = JSON.parse(readFileSync(fn, "utf-8")) as ParcelCanopy[];
  }
  shardCache.set(cell, records);
  if (shardCache.size > SHARD_CACHE_MAX)
    shardCache.delete(shardCache.keys().next().value as string);
  return records;
}

// Ray-casting point-in-polygon on a [lon, lat] ring.
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

export async function findParcel(lon: number, lat: number): Promise<ParcelCanopy | null> {
  const shard = await loadShard(cellFor(lon, lat));
  if (!shard) return null;
  for (const p of shard) {
    const b = p.bbox_4326;
    if (lon < b[0] || lon > b[2] || lat < b[1] || lat > b[3]) continue;
    if (pointInParcel(lon, lat, p.ring_4326)) return p;
  }
  return null;
}

let idIndex: Record<string, string> | null = null;

async function loadIdIndex(): Promise<Record<string, string>> {
  if (!idIndex) {
    const base = shardBase();
    if (base.startsWith("http")) {
      const res = await fetch(`${base}/parcel_index.json`);
      if (!res.ok) throw new Error(`index fetch failed: ${res.status}`);
      idIndex = (await res.json()) as Record<string, string>;
    } else {
      idIndex = JSON.parse(
        readFileSync(join(base, "parcel_index.json"), "utf-8"),
      ) as Record<string, string>;
    }
  }
  return idIndex;
}

export async function parcelById(parcelId: string): Promise<ParcelCanopy | null> {
  const key = parcelId.toUpperCase();
  const cell = (await loadIdIndex())[key];
  if (!cell) return null;
  const shard = await loadShard(cell);
  return shard?.find((p) => p.parcel_id === key) ?? null;
}

let cityRings: [number, number][][] | null = null;

function loadCityRings(): [number, number][][] {
  if (!cityRings) {
    cityRings = (
      JSON.parse(
        readFileSync(join(process.cwd(), "data", "city_boundary.json"), "utf-8"),
      ) as { rings_4326: [number, number][][] }
    ).rings_4326;
  }
  return cityRings;
}

// Honest coverage gate: the 2023 LiDAR mosaic covers 100% of Toronto
// (316/316 WCS probes, zero gaps), so inside the boundary a miss means
// genuinely no parcel, never "pilot only".
export function inToronto(lon: number, lat: number): boolean {
  return loadCityRings().some((ring) => pointInParcel(lon, lat, ring));
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

export const CITY_SCOPE = "Toronto-wide 2023 LiDAR canopy screen";

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
    pilot_scope: CITY_SCOPE,
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
    throw new ScreenError(404, { error: t.screen.notFound, pilot_scope: CITY_SCOPE });
  if (!inToronto(geo.lon, geo.lat)) {
    throw new ScreenError(404, {
      error: t.screen.outsideToronto,
      pilot_scope: CITY_SCOPE,
    });
  }
  const parcel = await findParcel(geo.lon, geo.lat);
  if (!parcel) {
    throw new ScreenError(404, {
      error: t.screen.noParcelData,
      pilot_scope: CITY_SCOPE,
    });
  }
  return buildScreenPayload(parcel, geo.address, lang);
}
