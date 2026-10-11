// lookup.mjs - prototype sharded lookup (no caching, mirrors canopy.ts logic).
//
// Usage: node lookup.mjs <lon> <lat>
// Prints the matched parcel_id, or "null" when no parcel covers the point.
// Exactly one shard file is read per call.
import { readFileSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SHARDS = join(ROOT, "data", "proto_shards");
const CELL = 500;

export function lonLatTo3857(lon, lat) {
  const x = (lon * 20037508.34) / 180;
  const y =
    Math.log(Math.tan(((90 + lat) * Math.PI) / 360)) * (20037508.34 / Math.PI);
  return [x, y];
}

// Ray-casting point-in-polygon (same algorithm as src/lib/canopy.ts).
export function pointInParcel(lon, lat, ring) {
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

// Uncached: reads the shard file from disk on every call.
export function findParcelUncached(lon, lat) {
  const [x, y] = lonLatTo3857(lon, lat);
  const key = `${Math.floor(x / CELL)}_${Math.floor(y / CELL)}`;
  const fn = join(SHARDS, `${key}.json`);
  if (!existsSync(fn)) return null;
  const arr = JSON.parse(readFileSync(fn, "utf-8"));
  for (const p of arr) {
    const b = p.bbox_4326;
    if (lon < b[0] || lon > b[2] || lat < b[1] || lat > b[3]) continue;
    if (pointInParcel(lon, lat, p.ring_4326)) return p;
  }
  return null;
}

import { basename } from "path";
const isMain = process.argv[1] && basename(process.argv[1]) === "lookup.mjs";
const [lonArg, latArg] = isMain ? process.argv.slice(2).map(Number) : [];
if (isMain && Number.isFinite(lonArg) && Number.isFinite(latArg)) {
  const t0 = process.hrtime.bigint();
  const p = findParcelUncached(lonArg, latArg);
  const t1 = process.hrtime.bigint();
  console.log(p ? p.parcel_id : "null");
  console.error(`lookup_ms=${Number(t1 - t0) / 1e6}`);
}
