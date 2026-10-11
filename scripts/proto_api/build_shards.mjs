// build_shards.mjs - prototype: uniform-grid sharded parcel index.
//
// Reads data/parcel_canopy_ward12.json (27,104 full parcel records) and writes
// one shard file per 500 m grid cell (EPSG:3857):
//   data/proto_shards/<cx>_<cy>.json
// Each shard holds every parcel whose 3857 bbox intersects the cell, as full
// ParcelCanopy records. A request computes its cell from the point and reads
// exactly one shard file. Parcels spanning cells are duplicated across them,
// so the cell containing the point always holds every parcel covering it.
//
// Also writes data/proto_shards/manifest.json (shard count, bytes, index of
// cell -> shard for a compact single-file index variant).
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CELL = 500; // metres
const OUT = join(ROOT, "data", "proto_shards");

function lonLatTo3857(lon, lat) {
  const x = (lon * 20037508.34) / 180;
  const y =
    Math.log(Math.tan(((90 + lat) * Math.PI) / 360)) * (20037508.34 / Math.PI);
  return [x, y];
}

function bbox3857(ring) {
  let x0 = 1e18, y0 = 1e18, x1 = -1e18, y1 = -1e18;
  for (const [lon, lat] of ring) {
    const [x, y] = lonLatTo3857(lon, lat);
    if (x < x0) x0 = x;
    if (y < y0) y0 = y;
    if (x > x1) x1 = x;
    if (y > y1) y1 = y;
  }
  return [x0, y0, x1, y1];
}

const raw = JSON.parse(
  readFileSync(join(ROOT, "data", "parcel_canopy_ward12.json"), "utf-8"),
);
const ids = Object.keys(raw);
console.log(`records: ${ids.length}`);

mkdirSync(OUT, { recursive: true });
// clear old shards
for (const f of readdirSync(OUT)) {
  if (f.endsWith(".json")) {
    const { unlinkSync } = await import("fs");
    unlinkSync(join(OUT, f));
  }
}

const shards = new Map(); // key -> record[]
for (const id of ids) {
  const p = raw[id];
  const [x0, y0, x1, y1] = bbox3857(p.ring_4326);
  const cx0 = Math.floor(x0 / CELL), cx1 = Math.floor(x1 / CELL);
  const cy0 = Math.floor(y0 / CELL), cy1 = Math.floor(y1 / CELL);
  for (let cx = cx0; cx <= cx1; cx++) {
    for (let cy = cy0; cy <= cy1; cy++) {
      const key = `${cx}_${cy}`;
      let arr = shards.get(key);
      if (!arr) shards.set(key, (arr = []));
      arr.push(p);
    }
  }
}

let totalBytes = 0;
let maxBytes = 0;
const index = {};
for (const [key, arr] of shards) {
  const fn = `${key}.json`;
  const body = JSON.stringify(arr);
  writeFileSync(join(OUT, fn), body);
  totalBytes += body.length;
  if (body.length > maxBytes) maxBytes = body.length;
  index[key] = { file: fn, parcels: arr.length, bytes: body.length };
}
writeFileSync(
  join(OUT, "manifest.json"),
  JSON.stringify(
    { cell_m: CELL, shards: shards.size, total_bytes: totalBytes,
      max_shard_bytes: maxBytes, index },
    null,
    1,
  ),
);
const srcBytes = readFileSync(
  join(ROOT, "data", "parcel_canopy_ward12.json"),
).length;
console.log(`shards: ${shards.size}`);
console.log(`total shard bytes: ${(totalBytes / 1e6).toFixed(2)} MB (source ${(srcBytes / 1e6).toFixed(2)} MB)`);
console.log(`max shard: ${(maxBytes / 1024).toFixed(1)} KB`);
console.log(
  `avg parcels/shard: ${(ids.length / shards.size).toFixed(1)}`,
);
