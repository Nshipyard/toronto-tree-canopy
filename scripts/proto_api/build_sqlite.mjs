// build_sqlite.mjs - prototype variant B: single SQLite .db via node:sqlite.
// Table parcels(parcel_id TEXT PK, record TEXT); rtree index on bbox_4326.
import { readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { DatabaseSync } from "node:sqlite";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const DB = join(ROOT, "data", "proto_parcels.db");

const raw = JSON.parse(
  readFileSync(join(ROOT, "data", "parcel_canopy_ward12.json"), "utf-8"),
);
const ids = Object.keys(raw);

const db = new DatabaseSync(DB);
db.exec(`DROP TABLE IF EXISTS parcels; DROP TABLE IF EXISTS rtree_parcels;
  CREATE TABLE parcels(seq INTEGER PRIMARY KEY, parcel_id TEXT UNIQUE, record TEXT NOT NULL);
  CREATE VIRTUAL TABLE rtree_parcels USING rtree(id, minx, maxx, miny, maxy);`);

const insP = db.prepare("INSERT INTO parcels(seq, parcel_id, record) VALUES (?, ?, ?)");
const insR = db.prepare("INSERT INTO rtree_parcels VALUES (?, ?, ?, ?, ?)");
const t0 = Date.now();
let i = 0;
db.exec("BEGIN");
for (const id of ids) {
  const p = raw[id];
  const b = p.bbox_4326;
  insP.run(i, id, JSON.stringify(p));
  insR.run(i, b[0], b[2], b[1], b[3]);
  if (++i % 5000 === 0) { db.exec("COMMIT"); db.exec("BEGIN"); process.stdout.write(`\r${i}/${ids.length}`); }
}
db.exec("COMMIT");
console.log(`\ninserted ${i} in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
db.close();
const { statSync } = await import("fs");
console.log(`db bytes: ${(statSync(DB).size / 1e6).toFixed(2)} MB`);
