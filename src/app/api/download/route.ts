import { NextRequest, NextResponse } from "next/server";
import { loadCanopy, ParcelCanopy } from "@/lib/canopy";

// GET /api/download?format=geojson|csv - the Ward 12 canopy dataset.
// Built on the fly from data/parcel_canopy_ward12.json: one row per parcel.

const CSV_HEADER =
  "parcel_id,address,area_m2,imagery_vintage," +
  "lot_tall_canopy_m2_ge6,lot_tall_canopy_m2_ge8,lot_max_chm_m,lot_canopy_pct_8," +
  "lot_p_any_ge_30cm,lot_p_any_distinctive," +
  "buffer_tall_canopy_m2_ge6,buffer_tall_canopy_m2_ge8,buffer_max_chm_m," +
  "buffer_p_any_ge_30cm,buffer_p_any_distinctive";

function toCsv(canopy: Record<string, ParcelCanopy>): string {
  const q = (s: string) => `"${String(s ?? "").replace(/"/g, '""')}"`;
  const rows: string[] = [CSV_HEADER];
  for (const id of Object.keys(canopy)) {
    const c = canopy[id];
    const L = c.lot;
    const B = c.buffer_6m;
    rows.push(
      [
        c.parcel_id,
        q(c.address),
        c.area_m2,
        c.imagery_vintage,
        L.tall_canopy_m2_ge6,
        L.tall_canopy_m2_ge8,
        L.max_chm_m ?? "",
        L.canopy_pct_8 ?? "",
        L.p_any_ge_30cm,
        L.p_any_distinctive,
        B.tall_canopy_m2_ge6,
        B.tall_canopy_m2_ge8,
        B.max_chm_m ?? "",
        B.p_any_ge_30cm,
        B.p_any_distinctive,
      ].join(","),
    );
  }
  return rows.join("\n");
}

function toGeoJson(canopy: Record<string, ParcelCanopy>): string {
  const features = Object.keys(canopy).map((id) => {
    const c = canopy[id];
    return {
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [c.ring_4326] },
      properties: {
        parcel_id: c.parcel_id,
        address: c.address,
        area_m2: c.area_m2,
        imagery_vintage: c.imagery_vintage,
        lot_tall_canopy_m2_ge6: c.lot.tall_canopy_m2_ge6,
        lot_tall_canopy_m2_ge8: c.lot.tall_canopy_m2_ge8,
        lot_max_chm_m: c.lot.max_chm_m,
        lot_canopy_pct_8: c.lot.canopy_pct_8,
        lot_p_any_ge_30cm: c.lot.p_any_ge_30cm,
        lot_p_any_distinctive: c.lot.p_any_distinctive,
        buffer_tall_canopy_m2_ge6: c.buffer_6m.tall_canopy_m2_ge6,
        buffer_tall_canopy_m2_ge8: c.buffer_6m.tall_canopy_m2_ge8,
        buffer_max_chm_m: c.buffer_6m.max_chm_m,
        buffer_p_any_ge_30cm: c.buffer_6m.p_any_ge_30cm,
        buffer_p_any_distinctive: c.buffer_6m.p_any_distinctive,
      },
    };
  });
  return JSON.stringify({ type: "FeatureCollection", features });
}

export async function GET(req: NextRequest) {
  const format = new URL(req.url).searchParams.get("format") ?? "geojson";
  const canopy = loadCanopy();
  if (format === "csv") {
    return new NextResponse(toCsv(canopy), {
      headers: {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment; filename=toronto-tree-canopy-ward12.csv",
      },
    });
  }
  return new NextResponse(toGeoJson(canopy), {
    headers: {
      "Content-Type": "application/geo+json",
      "Content-Disposition": "attachment; filename=toronto-tree-canopy-ward12.geojson",
    },
  });
}
