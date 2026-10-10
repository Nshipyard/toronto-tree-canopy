import { NextRequest, NextResponse } from "next/server";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

// GET /api/download?format=geojson|csv - the pilot parcel dataset.
function datasetPath(): string {
  const dir = join(process.cwd(), "data");
  const pilot = join(dir, "parcels-ward12.geojson");
  return existsSync(pilot) ? pilot : join(dir, "sample-parcels.geojson");
}

interface RawProps {
  parcel_id: string;
  address: string;
  crowns: { crown_diameter_m: number; dbh_est_cm: number; dbh_pi95_lo: number; dbh_pi95_hi: number; p_ge_30cm: number; p_gt_61cm: number }[];
  crown_count: number;
  canopy_pct: number;
  p_any_ge_30cm: number;
  p_any_distinctive: number;
  neighbour_6m: { crown_count: number; p_any_ge_30cm: number; p_any_distinctive: number };
  imagery_vintage: string;
}

export async function GET(req: NextRequest) {
  const format = new URL(req.url).searchParams.get("format") ?? "geojson";
  const raw = readFileSync(datasetPath(), "utf-8");
  if (format === "csv") {
    const doc = JSON.parse(raw) as { features: { properties: RawProps }[] };
    const rows: string[] = [
      "parcel_id,address,imagery_vintage,crown_count,canopy_pct,p_any_ge_30cm,p_any_distinctive,neighbour_6m_crown_count,neighbour_6m_p_any_ge_30cm,crown_index,crown_diameter_m,dbh_est_cm,dbh_pi95_lo,dbh_pi95_hi,p_ge_30cm,p_gt_61cm",
    ];
    const q = (s: string) => `"${s.replace(/"/g, '""')}"`;
    for (const f of doc.features) {
      const p = f.properties;
      const base = `${p.parcel_id},${q(p.address)},${p.imagery_vintage},${p.crown_count},${p.canopy_pct},${p.p_any_ge_30cm},${p.p_any_distinctive},${p.neighbour_6m.crown_count},${p.neighbour_6m.p_any_ge_30cm}`;
      if (p.crowns.length === 0) {
        rows.push(`${base},,,,,,,`);
      } else {
        p.crowns.forEach((c, i) => {
          rows.push(`${base},${i + 1},${c.crown_diameter_m},${c.dbh_est_cm},${c.dbh_pi95_lo},${c.dbh_pi95_hi},${c.p_ge_30cm},${c.p_gt_61cm}`);
        });
      }
    }
    return new NextResponse(rows.join("\n"), {
      headers: {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment; filename=toronto-tree-canopy-pilot.csv",
      },
    });
  }
  return new NextResponse(raw, {
    headers: {
      "Content-Type": "application/geo+json",
      "Content-Disposition": "attachment; filename=toronto-tree-canopy-pilot.geojson",
    },
  });
}
