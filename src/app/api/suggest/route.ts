import { NextRequest, NextResponse } from "next/server";
import { datastoreSearch, RESOURCES } from "@/lib/ckan";

interface AddressPoint {
  ADDRESS_FULL?: string;
}

// Typeahead suggestions backed by the City of Toronto address-points
// dataset (the same source /api/v1/screen geocodes against, so every
// suggestion resolves). CKAN full-text `q` needs complete words, so the
// box fills in once the street name is typed out.
export async function GET(req: NextRequest) {
  const raw = new URL(req.url).searchParams.get("q") ?? "";
  const cleaned = raw
    .replace(/,?\s*toronto\s*(on)?\s*,?\s*$/i, "")
    .replace(/[^a-zA-Z0-9 '\-./]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
  if (cleaned.length < 3) return NextResponse.json({ suggestions: [] });
  try {
    const { records } = await datastoreSearch<AddressPoint>(
      RESOURCES.addressPoints,
      { q: cleaned, limit: "8" },
    );
    const seen = new Set<string>();
    const suggestions: string[] = [];
    for (const r of records) {
      const a = (r.ADDRESS_FULL ?? "").trim();
      if (a && !seen.has(a)) {
        seen.add(a);
        suggestions.push(a);
      }
    }
    return NextResponse.json({ suggestions });
  } catch {
    return NextResponse.json({ suggestions: [] });
  }
}
