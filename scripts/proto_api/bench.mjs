// bench.mjs - time 30 cold (uncached) point-in-parcel lookups against the
// grid-sharded prototype. Each lookup reads its shard file fresh from disk.
// Categories: inside (expect hit + correct parcel_id), roads (expect miss),
// outside (expect miss). Prints per-query ms plus summary stats.
import { readFileSync } from "fs";
import { findParcelUncached } from "./lookup.mjs";

const pts = JSON.parse(readFileSync("/tmp/proto_points.json", "utf-8"));

const queries = [
  ...pts.inside.map((p) => ({ ...p, expect: "hit" })),
  ...pts.roads.map((p) => ({ ...p, expect: "miss" })),
  ...pts.outside.map((p) => ({ ...p, expect: "miss" })),
];

const times = [];
let wrong = 0;
for (const q of queries) {
  const t0 = process.hrtime.bigint();
  const p = findParcelUncached(q.lon, q.lat);
  const ms = Number(process.hrtime.bigint() - t0) / 1e6;
  times.push(ms);
  let ok;
  if (q.expect === "hit") ok = !!p && p.parcel_id === q.parcel_id;
  else ok = !p;
  if (!ok) wrong++;
  console.log(
    `${ok ? "OK " : "FAIL"} ${ms.toFixed(2)}ms ${q.expect}->${p ? "hit" : "miss"} ${q.address} ${p ? p.parcel_id : ""}`,
  );
}
times.sort((a, b) => a - b);
const avg = times.reduce((s, t) => s + t, 0) / times.length;
console.log(
  `\nn=${times.length} wrong=${wrong} min=${times[0].toFixed(2)}ms p50=${times[times.length >> 1].toFixed(2)}ms p95=${times[Math.floor(times.length * 0.95)].toFixed(2)}ms max=${times[times.length - 1].toFixed(2)}ms avg=${avg.toFixed(2)}ms`,
);
