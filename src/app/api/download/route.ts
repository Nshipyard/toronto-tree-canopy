import { NextRequest, NextResponse } from "next/server";
import { readFileSync, existsSync } from "fs";
import { join } from "path";
import { CITY_SCOPE, shardBase } from "@/lib/canopy";

// GET /api/download?format=geojson|csv&ward=NN - the Toronto canopy dataset,
// one ward at a time. Serves the pre-generated per-ward static files from the
// shard storage (never loads the 400+ MB city dataset into the function).
//
//   /api/download?format=csv&ward=09  -> ward 09 CSV (metrics, no geometry)
//   /api/download?format=geojson&ward=09 -> ward 09 GeoJSON (with parcel rings)

const WARDS = Array.from({ length: 25 }, (_, i) => String(i + 1).padStart(2, "0"));

const CSV_HEADER =
  "parcel_id,address,area_m2,ward,imagery_vintage," +
  "lot_tall_canopy_m2_ge6,lot_tall_canopy_m2_ge8,lot_max_chm_m,lot_canopy_pct_8," +
  "lot_p_any_ge_30cm,lot_p_any_distinctive," +
  "buffer_tall_canopy_m2_ge6,buffer_tall_canopy_m2_ge8,buffer_max_chm_m," +
  "buffer_p_any_ge_30cm,buffer_p_any_distinctive";

// jsDelivr 403s files over 20 MB (measured); the per-ward GeoJSONs exceed
// that, so on a non-OK from jsDelivr we fall back to raw.githubusercontent.com
// for the same file. CSVs stay on the fast CDN path.
function rawBase(): string | null {
  const sb = shardBase();
  const m = sb.match(
    /^https:\/\/cdn\.jsdelivr\.net\/gh\/([^/]+\/[^/]+)@([^/]+)\/data\/shards\/?$/,
  );
  return m ? `https://raw.githubusercontent.com/${m[1]}/${m[2]}/data` : null;
}

async function readStatic(rel: string): Promise<Buffer | null> {
  // rel is relative to data/, e.g. "downloads/ward_09.geojson"
  const sb = shardBase();
  if (!sb.startsWith("http")) {
    const fn = join(process.cwd(), "data", rel);
    if (!existsSync(fn)) return null;
    return readFileSync(fn);
  }
  const dataBase = sb.replace(/\/shards\/?$/, "");
  let res = await fetch(`${dataBase}/${rel}`);
  if (res.ok) return Buffer.from(await res.arrayBuffer());
  const rb = rawBase();
  if (rb) {
    res = await fetch(`${rb}/${rel}`);
    if (res.ok) return Buffer.from(await res.arrayBuffer());
  }
  return null;
}

export async function GET(req: NextRequest) {
  const params = new URL(req.url).searchParams;
  const format = params.get("format") ?? "geojson";
  const ward = (params.get("ward") ?? "").trim();
  if (!WARDS.includes(ward)) {
    return NextResponse.json(
      {
        error: `ward is required: one of ${WARDS.join(", ")}`,
        wards: WARDS,
        pilot_scope: CITY_SCOPE,
      },
      { status: 400 },
    );
  }
  if (format !== "geojson" && format !== "csv") {
    return NextResponse.json(
      { error: "format must be geojson or csv", pilot_scope: CITY_SCOPE },
      { status: 400 },
    );
  }
  const rel = `downloads/ward_${ward}.${format}`;
  const body = await readStatic(rel);
  if (!body) {
    return NextResponse.json(
      { error: `ward ${ward} ${format} is not published yet`, pilot_scope: CITY_SCOPE },
      { status: 404 },
    );
  }
  const filename = `toronto-tree-canopy-ward${ward}.${format}`;
  return new NextResponse(new Uint8Array(body), {
    headers: {
      "Content-Type": format === "csv" ? "text/csv" : "application/geo+json",
      "Content-Disposition": `attachment; filename=${filename}`,
      "Cache-Control": "public, max-age=86400",
    },
  });
}
