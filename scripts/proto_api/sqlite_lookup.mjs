// sqlite_lookup.mjs - prototype variant B lookup (uncached).
// Usage: node sqlite_lookup.mjs <lon> <lat>
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { DatabaseSync } from "node:sqlite";
import { pointInParcel } from "./lookup.mjs";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const DB = join(ROOT, "data", "proto_parcels.db");

export function findParcelSqliteUncached(lon, lat) {
  const db = new DatabaseSync(DB, { readOnly: true });
  try {
    const q = db.prepare(
      `SELECT p.record FROM rtree_parcels r JOIN parcels p ON p.seq = r.id
       WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ?`,
    );
    for (const row of q.iterate(lon, lon, lat, lat)) {
      const p = JSON.parse(row.record);
      if (pointInParcel(lon, lat, p.ring_4326)) return p;
    }
    return null;
  } finally {
    db.close();
  }
}

const [lonArg, latArg] = process.argv.slice(2).map(Number);
if (Number.isFinite(lonArg) && Number.isFinite(latArg)) {
  const t0 = process.hrtime.bigint();
  const p = findParcelSqliteUncached(lonArg, latArg);
  const t1 = process.hrtime.bigint();
  console.log(p ? p.parcel_id : "null");
  console.error(`lookup_ms=${Number(t1 - t0) / 1e6}`);
}
