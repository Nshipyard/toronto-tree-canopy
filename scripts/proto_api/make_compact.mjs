// make_compact.mjs - rewrite parcel_canopy_ward12.json into a compact record
// layout and rebuild the grid shards from it, to MEASURE the compact size.
//
// Compact record: [parcel_id, address, area_m2, vintage,
//   cx, cy, x0, y0, x1, y1,            // centroid + bbox, 5 decimals
//   [[lot_ge6, lot_ge8, lot_max, lot_pct6, lot_pct8, lot_p30, lot_pdist, lot_peaks],
//    [buf_ge6, buf_ge8, buf_max, buf_pct6, buf_pct8, buf_p30, buf_pdist, buf_peaks]],
//   [[lon,lat],...]]                    // ring, 5 decimals
import { readFileSync, writeFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const r5 = (v) => (v === null || v === undefined ? null : Math.round(v * 1e5) / 1e5);
const r2 = (v) => (v === null || v === undefined ? null : Math.round(v * 100) / 100);
const r1 = (v) => (v === null || v === undefined ? null : Math.round(v * 10) / 10);

const raw = JSON.parse(
  readFileSync(join(ROOT, "data", "parcel_canopy_ward12.json"), "utf-8"),
);
const out = {};
for (const id of Object.keys(raw)) {
  const p = raw[id];
  const L = p.lot, B = p.buffer_6m;
  out[id] = [
    p.parcel_id, p.address || "", r1(p.area_m2), p.imagery_vintage,
    r5(p.centroid_4326[0]), r5(p.centroid_4326[1]),
    r5(p.bbox_4326[0]), r5(p.bbox_4326[1]), r5(p.bbox_4326[2]), r5(p.bbox_4326[3]),
    [[r1(L.tall_canopy_m2_ge6), r1(L.tall_canopy_m2_ge8),
      L.max_chm_m === null ? null : r2(L.max_chm_m),
      L.canopy_pct_6 === null ? null : r1(L.canopy_pct_6),
      L.canopy_pct_8 === null ? null : r1(L.canopy_pct_8),
      +L.p_any_ge_30cm.toFixed(4), +L.p_any_distinctive.toFixed(4), L.peak_count],
     [r1(B.tall_canopy_m2_ge6), r1(B.tall_canopy_m2_ge8),
      B.max_chm_m === null ? null : r2(B.max_chm_m),
      B.canopy_pct_6 === null ? null : r1(B.canopy_pct_6),
      B.canopy_pct_8 === null ? null : r1(B.canopy_pct_8),
      +B.p_any_ge_30cm.toFixed(4), +B.p_any_distinctive.toFixed(4), B.peak_count]],
    p.ring_4326.map(([lo, la]) => [r5(lo), r5(la)]),
  ];
}
const body = JSON.stringify(out);
writeFileSync(join(ROOT, "data", "parcel_canopy_ward12_compact.json"), body);
console.log(
  `compact records: ${(body.length / 1e6).toFixed(2)} MB for ${Object.keys(out).length} parcels ` +
  `(${(body.length / Object.keys(out).length).toFixed(0)} B/parcel)`,
);
