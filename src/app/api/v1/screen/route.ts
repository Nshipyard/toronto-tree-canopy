import { NextRequest, NextResponse } from "next/server";
import { screenAddress, ScreenError, PILOT_SCOPE } from "@/lib/canopy";
import { pickLang } from "@/lib/i18n";

// GET /api/v1/screen?address=…&lang=en|fr
// Resolves the address via the City's Address Points, runs point-in-polygon
// against the pilot parcels, and returns the per-parcel screening payload.
// Outside the pilot parcels: HTTP 404.
export async function GET(req: NextRequest) {
  const params = new URL(req.url).searchParams;
  const address = (params.get("address") ?? "").trim();
  const lang = pickLang(params.get("lang"));
  if (!address) {
    return NextResponse.json(
      { error: "address is required", pilot_scope: PILOT_SCOPE },
      { status: 400 },
    );
  }
  try {
    const payload = await screenAddress(address, lang);
    const { sample, ...rest } = payload;
    return NextResponse.json({
      ...rest,
      method: {
        detection_f1: payload.method.detection_f1,
        sample: payload.method.sample,
        note: "Screening signal only; not a permit determination.",
      },
    });
  } catch (e) {
    if (e instanceof ScreenError) {
      return NextResponse.json(e.body, { status: e.status });
    }
    return NextResponse.json(
      { error: "screening failed", pilot_scope: PILOT_SCOPE },
      { status: 500 },
    );
  }
}
