// Server-side Toronto Open Data CKAN client with in-memory caching.
// Public CKAN, no key. Mirrors the toronto-build-check pattern.

const CKAN_BASE =
  "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action";
const UA = "toronto-tree-canopy/1.0 (open-source civic data tool)";

interface CacheEntry {
  at: number;
  payload: unknown;
}

const cache = new Map<string, CacheEntry>();
const TTL_MS = 10 * 60 * 1000;

function cacheGet<T>(key: string): T | null {
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.payload as T;
  return null;
}

function cacheSet(key: string, payload: unknown) {
  cache.set(key, { at: Date.now(), payload });
  if (cache.size > 500) {
    const oldest = [...cache.entries()].sort((a, b) => a[1].at - b[1].at)[0];
    cache.delete(oldest[0]);
  }
}

async function ckanAction<T>(
  action: string,
  params: Record<string, string>,
  cacheKey: string,
): Promise<{ data: T; cached: boolean }> {
  const hit = cacheGet<T>(cacheKey);
  if (hit) return { data: hit, cached: true };
  const url = new URL(`${CKAN_BASE}/${action}`);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  const res = await fetch(url.toString(), {
    cache: "no-store",
    headers: { "User-Agent": UA },
  });
  if (!res.ok) throw new Error(`Toronto Open Data returned HTTP ${res.status}`);
  const json = (await res.json()) as { success: boolean; result?: T };
  if (!json.success || json.result === undefined)
    throw new Error("Toronto Open Data request failed");
  cacheSet(cacheKey, json.result);
  return { data: json.result, cached: false };
}

export interface DatastoreResult<T> {
  records: T[];
  total: number;
  cached: boolean;
}

export async function datastoreSearch<T>(
  resourceId: string,
  params: Record<string, string>,
): Promise<DatastoreResult<T>> {
  const cacheKey = `ds:${resourceId}:${JSON.stringify(params)}`;
  const { data, cached } = await ckanAction<{
    records: T[];
    total: number;
  }>("datastore_search", { resource_id: resourceId, ...params }, cacheKey);
  return { records: data.records, total: data.total, cached };
}

// Resource IDs (verified 2026-10-09 against live CKAN by toronto-build-check)
export const RESOURCES = {
  addressPoints: "0b3756af-9caf-4f0f-ac28-9c6617adede4",
} as const;

export interface AddressPointRow {
  ADDRESS_FULL?: string;
  geometry?: string;
  LATITUDE?: string | number;
  LONGITUDE?: string | number;
  GEOMETRY_X?: string | number;
  GEOMETRY_Y?: string | number;
}

export interface GeocodeResult {
  address: string;
  lon: number;
  lat: number;
}

function toNum(v: string | number | undefined): number | null {
  if (v === undefined || v === null) return null;
  const n = typeof v === "number" ? v : Number(String(v).trim());
  return Number.isFinite(n) ? n : null;
}

function rowCoords(r: AddressPointRow): { lon: number; lat: number } | null {
  // The address-points resource carries coordinates as a geometry JSON string.
  const g = r.geometry;
  if (typeof g === "string" && g) {
    try {
      const geo = JSON.parse(g) as { coordinates?: [number, number] };
      const c = geo.coordinates;
      if (Array.isArray(c) && c.length >= 2 && Number.isFinite(c[0]) && Number.isFinite(c[1])) {
        return { lon: c[0], lat: c[1] };
      }
    } catch {
      // fall through to column fields
    }
  }
  const lon = toNum(r.LONGITUDE ?? r.GEOMETRY_X);
  const lat = toNum(r.LATITUDE ?? r.GEOMETRY_Y);
  return lon === null || lat === null ? null : { lon, lat };
}

// Geocode one address against the City's Address Points (same source as
// /api/suggest, so every suggestion resolves).
export async function geocodeAddress(raw: string): Promise<GeocodeResult | null> {
  const cleaned = raw
    .replace(/,?\s*toronto\s*(on)?\s*,?\s*$/i, "")
    .replace(/[^a-zA-Z0-9 '\-./]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
  if (!cleaned) return null;
  let records: AddressPointRow[];
  try {
    const res = await datastoreSearch<AddressPointRow>(RESOURCES.addressPoints, {
      q: cleaned,
      limit: "5",
    });
    records = res.records;
  } catch {
    throw new Error("CKAN_UNAVAILABLE");
  }
  for (const r of records) {
    const label = (r.ADDRESS_FULL ?? "").trim();
    if (!label) continue;
    // Prefer rows whose full address matches the query closely.
    const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
    if (cleaned.length >= 4 && !norm(label).includes(norm(cleaned).split(" ").slice(0, 2).join(" "))) {
      continue;
    }
    const lonlat = rowCoords(r);
    if (!lonlat) continue;
    return { address: label, lon: lonlat.lon, lat: lonlat.lat };
  }
  return null;
}
