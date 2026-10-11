import { NextRequest, NextResponse } from "next/server";
import { screenAddress, ScreenError, CITY_SCOPE } from "@/lib/canopy";
import { pickLang } from "@/lib/i18n";

// GET /api/v1/screen?address=…&lang=en|fr
// Resolves the address via the City's Address Points, runs point-in-polygon
// against the city-wide parcel shards, and returns the measured 2023 LiDAR
// canopy payload for the lot plus the 6 m neighbour buffer. Screening signal
// only; never a permit determination. Outside Toronto: HTTP 404.
export async function GET(req: NextRequest) {
  const params = new URL(req.url).searchParams;
  const address = (params.get("address") ?? "").trim();
  const lang = pickLang(params.get("lang"));
  if (!address) {
    return NextResponse.json(
      { error: "address is required", pilot_scope: CITY_SCOPE },
      { status: 400 },
    );
  }
  try {
    const payload = await screenAddress(address, lang);
    return NextResponse.json(payload);
  } catch (e) {
    if (e instanceof ScreenError) {
      return NextResponse.json(e.body, { status: e.status });
    }
    return NextResponse.json(
      { error: "screening failed", pilot_scope: CITY_SCOPE },
      { status: 500 },
    );
  }
}
