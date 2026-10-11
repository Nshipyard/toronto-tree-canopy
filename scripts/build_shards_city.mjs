// build_shards_city.mjs - city-wide uniform-grid sharded parcel index.
//
// Reads data/tiles_out/tile_*.json (per-tile masked parcel records, each with
// a "ward" field) and writes one shard file per 500 m EPSG:3857 cell:
//   data/shards/<cx>_<cy>.json
// Each shard holds the full parcel records whose 3857 bbox intersects the
// cell. A request computes its cell from the point (closed form) and reads
// exactly one shard. Parcels spanning cells are duplicated across them.
//
// Also writes:
//   data/shards/parcel_index.json  - parcel_id -> centroid cell (~14.5 MB)
//   data/shards/manifest.json      - build stats
//
// Two passes bound memory: pass 1 streams records into per-cell JSONL temp
// files (flushed in batches); pass 2 wraps each temp file into a JSON array.
// Run: node scripts/build_shards_city.mjs
import { readFileSync, writeFileSync, mkdirSync, appendFileSync, readdirSync, rmSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const CELL = 500; // metres
const WEB_MERC = 20037508.34;
const TILES_OUT = join(ROOT, "data", "tiles_out");
const TMP = join(ROOT, "data", "shards_tmp");
const OUT = join(ROOT, "data", "shards");

function lonLatTo3857(lon, lat) {
  const x = (lon * WEB_MERC) / 180;
  const y = Math.log(Math.tan(((90 + lat) * Math.PI) / 360)) * (WEB_MERC / Math.PI);
  return [x, y];
}

function cellFor(lon, lat) {
  const [x, y] = lonLatTo3857(lon, lat);
  return `${Math.floor(x / CELL)}_${Math.floor(y / CELL)}`;
}

function bboxCells(ring) {
  let x0 = 1e18, y0 = 1e18, x1 = -1e18, y1 = -1e18;
  for (const [lon, lat] of ring) {
    const [x, y] = lonLatTo3857(lon, lat);
    if (x < x0) x0 = x;
    if (y < y0) y0 = y;
    if (x > x1) x1 = x;
    if (y > y1) y1 = y;
  }
  const cells = [];
  for (let cx = Math.floor(x0 / CELL); cx <= Math.floor(x1 / CELL); cx++)
    for (let cy = Math.floor(y0 / CELL); cy <= Math.floor(y1 / CELL); cy++)
      cells.push(`${cx}_${cy}`);
  return cells;
}

mkdirSync(TMP, { recursive: true });
mkdirSync(OUT, { recursive: true });
for (const f of readdirSync(TMP)) rmSync(join(TMP, f));
for (const f of readdirSync(OUT)) if (f.endsWith(".json")) rmSync(join(OUT, f));

const tileFiles = readdirSync(TILES_OUT).filter((f) => /^tile_\d+\.json$/.test(f)).sort();
console.log(`tile files: ${tileFiles.length}`);

// Tile cores are contiguous, so ~0.02% of parcels have their centroid exactly
// on a tile boundary and appear in two tiles' outputs. Deduplicate: keep the
// record from the tile whose core contains the centroid most interiorly
// (farther from the core edge = less edge-effect in the 6 m buffer).
const tileCores = JSON.parse(readFileSync(join(ROOT, "data", "tile_plan.json"), "utf-8"))
  .tiles.map((t) => ({ tile: t.tile, bbox: t.core_bbox_4326 }));
function interiority(bbox, lon, lat) {
  return Math.min(lon - bbox[0], bbox[2] - lon, lat - bbox[1], bbox[3] - lat);
}
const seen = new Map(); // parcel_id -> { tile, interiority }

// Pass 1: stream records -> per-cell JSONL + id->centroid-cell index.
const idIndex = {};
const cellBufs = new Map();
let buffered = 0;
let nRecords = 0;
function emit(cell, str) {
  let arr = cellBufs.get(cell);
  if (!arr) cellBufs.set(cell, (arr = []));
  arr.push(str);
  if (++buffered >= 50000) flush();
}
function flush() {
  for (const [cell, arr] of cellBufs)
    appendFileSync(join(TMP, `${cell}.jsonl`), arr.join("\n") + "\n");
  cellBufs.clear();
  buffered = 0;
}
const t0 = Date.now();
// Phase 1a: decide the winning tile for each parcel (most interior centroid).
for (const tf of tileFiles) {
  const tileNo = parseInt(tf.match(/^tile_(\d+)\.json$/)[1], 10);
  const core = tileCores.find((t) => t.tile === tileNo).bbox;
  const recs = JSON.parse(readFileSync(join(TILES_OUT, tf), "utf-8"));
  for (const id of Object.keys(recs)) {
    const p = recs[id];
    const inter = interiority(core, p.centroid_4326[0], p.centroid_4326[1]);
    const prev = seen.get(id);
    if (!prev || inter > prev.interiority) seen.set(id, { tile: tileNo, interiority: inter });
  }
}
console.log(`dedup: ${seen.size} unique parcels`);

// Phase 1b: emit winners only.
let nDedup = 0;
for (const tf of tileFiles) {
  const tileNo = parseInt(tf.match(/^tile_(\d+)\.json$/)[1], 10);
  const recs = JSON.parse(readFileSync(join(TILES_OUT, tf), "utf-8"));
  for (const id of Object.keys(recs)) {
    if (seen.get(id).tile !== tileNo) { nDedup++; continue; }
    const p = recs[id];
    const str = JSON.stringify(p);
    for (const cell of bboxCells(p.ring_4326)) emit(cell, str);
    idIndex[id] = cellFor(p.centroid_4326[0], p.centroid_4326[1]);
    if (++nRecords % 100000 === 0)
      console.log(`  ${nRecords} records (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  }
}
flush();
console.log(`pass 1 done: ${nRecords} records, ${Object.keys(idIndex).length} indexed, ${nDedup} boundary duplicates skipped`);
flush();
console.log(`pass 1 done: ${nRecords} records, ${Object.keys(idIndex).length} indexed`);

// Pass 2: JSONL -> JSON array shards.
const tmpFiles = readdirSync(TMP).filter((f) => f.endsWith(".jsonl"));
let totalBytes = 0, maxBytes = 0, maxCell = "";
const shardIndex = {};
for (const tf of tmpFiles) {
  const cell = tf.slice(0, -".jsonl".length);
  const lines = readFileSync(join(TMP, tf), "utf-8").trim().split("\n");
  const body = `[${lines.join(",")}]`;
  writeFileSync(join(OUT, `${cell}.json`), body);
  totalBytes += body.length;
  if (body.length > maxBytes) { maxBytes = body.length; maxCell = cell; }
  shardIndex[cell] = { parcels: lines.length, bytes: body.length };
}
writeFileSync(join(OUT, "parcel_index.json"), JSON.stringify(idIndex));
const idxBytes = readFileSync(join(OUT, "parcel_index.json")).length;
writeFileSync(
  join(OUT, "manifest.json"),
  JSON.stringify(
    {
      cell_m: CELL, shards: tmpFiles.length, records: nRecords,
      total_shard_bytes: totalBytes, max_shard_bytes: maxBytes,
      max_shard_cell: maxCell,
      parcel_index_bytes: idxBytes,
      avg_shard_kb: totalBytes / tmpFiles.length / 1024,
      built: new Date().toISOString(),
    },
    null, 1,
  ),
);
console.log(`shards: ${tmpFiles.length}`);
console.log(`total shard bytes: ${(totalBytes / 1e6).toFixed(1)} MB`);
console.log(`max shard: ${(maxBytes / 1024).toFixed(1)} KB (${maxCell})`);
console.log(`avg shard: ${(totalBytes / tmpFiles.length / 1024).toFixed(1)} KB`);
console.log(`parcel_index.json: ${(idxBytes / 1e6).toFixed(1)} MB`);
console.log(`duplication: ${(Object.values(shardIndex).reduce((a, s) => a + s.parcels, 0) / nRecords).toFixed(3)}x`);
