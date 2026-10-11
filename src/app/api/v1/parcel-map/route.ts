import { NextRequest, NextResponse } from "next/server";
import { join } from "path";
import { readFileSync, existsSync } from "fs";
import sharp from "sharp";
import { fromUrl, fromArrayBuffer } from "geotiff";
import { parcelById, CITY_SCOPE, cogBase } from "@/lib/canopy";

// GET /api/v1/parcel-map?parcel_id=TOP-…&lang=en|fr
// Server-renders a per-parcel tall-canopy overlay PNG on demand: the parcel
// window is read from the ward's masked-CHM COG (uint16 decimetres, buildings
// NaN) via HTTP range reads, then rendered as a TRANSPARENT overlay: green
// tint where CHM >= 8 m, parcel
// boundary (dark line, white underlay) and 6 m neighbour buffer (dashed, the
// image edge). The browser composites this over the City of Toronto 2022
// aerial orthophoto (fetched client-side from the City's MapServer), so the
// map shows real imagery with the LiDAR tint on top. Long edge 1080 px.
// Cacheable basically forever: the render is deterministic over static data.
// ?format=json returns the render window instead of the PNG:
// { bbox_3857, width, height, m_per_px }.

export const maxDuration = 30;

const WEB_MERC = 20037508.34;
const BUFFER_M = 6;
const LONG_EDGE = 1080;
const TALL_M = 8;

function to3857(lon: number, lat: number): [number, number] {
  return [
    (lon * WEB_MERC) / 180,
    Math.log(Math.tan(((90 + lat) * Math.PI) / 360)) * (WEB_MERC / Math.PI),
  ];
}

function mercInv(x: number, y: number): [number, number] {
  return [
    (x / WEB_MERC) * 180,
    ((2 * Math.atan(Math.exp((y / WEB_MERC) * Math.PI)) - Math.PI / 2) * 180) / Math.PI,
  ];
}

function overlaySvg(
  W: number,
  H: number,
  poly: [number, number][],
  mPerPx: number,
): string {
  const dash = `${(4 / mPerPx).toFixed(1)} ${(3 / mPerPx).toFixed(1)}`;
  const s = W / LONG_EDGE;
  const pts = poly.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  return (
    `<svg width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg">` +
    `<rect x="4" y="4" width="${W - 8}" height="${H - 8}" fill="none" stroke="white" stroke-width="${Math.max(4, Math.round(7 * s))}" stroke-dasharray="${dash}"/>` +
    `<rect x="4" y="4" width="${W - 8}" height="${H - 8}" fill="none" stroke="#8a8fa0" stroke-width="${Math.max(2, Math.round(3 * s))}" stroke-dasharray="${dash}"/>` +
    `<polyline points="${pts}" fill="none" stroke="white" stroke-width="${Math.round(9 * s)}" stroke-linejoin="round"/>` +
    `<polyline points="${pts}" fill="none" stroke="#0a0f1e" stroke-width="${Math.max(2, Math.round(4 * s))}" stroke-linejoin="round"/>` +
    `</svg>`
  );
}

export async function GET(req: NextRequest) {
  const params = new URL(req.url).searchParams;
  const parcelId = (params.get("parcel_id") ?? "").trim().toUpperCase();
  if (!parcelId) {
    return NextResponse.json(
      { error: "parcel_id is required", pilot_scope: CITY_SCOPE },
      { status: 400 },
    );
  }
  let parcel;
  try {
    parcel = await parcelById(parcelId);
  } catch {
    parcel = null;
  }
  if (!parcel) {
    return NextResponse.json(
      { error: `parcel ${parcelId} not found`, pilot_scope: CITY_SCOPE },
      { status: 404 },
    );
  }

  // Parcel window in 3857: parcel bbox + 6 m (the image edge is the buffer).
  const pts3857 = parcel.ring_4326.map(([lo, la]) => to3857(lo, la));
  const xs = pts3857.map((p) => p[0]);
  const ys = pts3857.map((p) => p[1]);
  let bx0 = Math.min(...xs) - BUFFER_M;
  let by0 = Math.min(...ys) - BUFFER_M;
  let bx1 = Math.max(...xs) + BUFFER_M;
  let by1 = Math.max(...ys) + BUFFER_M;
  // Clamp the window to at most a 2:1 aspect ratio so very long, narrow
  // parcels do not render as unreadable strips; the short side is expanded
  // with extra map context, centred on the parcel.
  {
    const wM = bx1 - bx0;
    const hM = by1 - by0;
    if (wM > 2 * hM) {
      const nh = wM / 2;
      const cy = (by0 + by1) / 2;
      by0 = cy - nh / 2;
      by1 = cy + nh / 2;
    } else if (hM > 2 * wM) {
      const nw = hM / 2;
      const cx = (bx0 + bx1) / 2;
      bx0 = cx - nw / 2;
      bx1 = cx + nw / 2;
    }
  }
  const [lon0, lat0] = mercInv(bx0, by0);
  const [lon1, lat1] = mercInv(bx1, by1);

  // Read the window from the ward COG (uint16 decimetres, 65535 = nodata).
  const base = cogBase();
  const wardTag = String(parcel.ward).padStart(2, "0");
  const cogUrl = `${base}/ward_${wardTag}_chm.tif`;
  let raw: ArrayLike<number>;
  let rw: number, rh: number;
  try {
    const tiff = base.startsWith("http")
      ? await fromUrl(cogUrl)
      : await (async () => {
          const fn = join(base, `ward_${wardTag}_chm.tif`);
          if (!existsSync(fn)) throw new Error("no local COG");
          return fromArrayBuffer(readFileSync(fn).buffer as ArrayBuffer);
        })();
    const image = await tiff.getImage();
    const origin = image.getOrigin() as [number, number];
    const res = image.getResolution() as [number, number];
    const imgW = image.getWidth();
    const imgH = image.getHeight();
    const left = Math.max(0, Math.floor((lon0 - origin[0]) / res[0]));
    const top = Math.max(0, Math.floor((origin[1] - lat1) / Math.abs(res[1])));
    const right = Math.min(imgW, Math.ceil((lon1 - origin[0]) / res[0]));
    const bottom = Math.min(imgH, Math.ceil((origin[1] - lat0) / Math.abs(res[1])));
    if (right <= left || bottom <= top) throw new Error("window outside COG");
    const rasters = (await image.readRasters({
      window: [left, top, right, bottom],
    })) as unknown as ArrayLike<number>[];
    raw = rasters[0];
    rw = right - left;
    rh = bottom - top;
  } catch (e) {
    console.error("parcel-map", parcelId, e);
    return NextResponse.json(
      {
        error: "canopy map is not available for this parcel yet",
        pilot_scope: CITY_SCOPE,
      },
      { status: 502 },
    );
  }

  // Transparent overlay: green tint where masked CHM >= 8 m (buildings are NaN).
  const scale = Math.max(LONG_EDGE / Math.max(rw, rh), 1);
  const W = Math.max(1, Math.round(rw * scale));
  const H = Math.max(1, Math.round(rh * scale));
  const mPerPx = (bx1 - bx0) / W;

  if (params.get("format") === "json") {
    return NextResponse.json(
      {
        bbox_3857: [bx0, by0, bx1, by1],
        width: W,
        height: H,
        m_per_px: mPerPx,
      },
      { headers: { "Cache-Control": "public, max-age=31536000, immutable" } },
    );
  }

  // baseBuf (CHM grayscale) is no longer composited; the overlay is
  // transparent and the browser supplies the aerial photo underneath.
  const tintBuf = Buffer.alloc(rw * rh * 4);
  for (let k = 0; k < rw * rh; k++) {
    const rv = raw[k] as number;
    const v = rv === 65535 ? NaN : rv / 10;
    if (Number.isFinite(v) && v >= TALL_M) {
      tintBuf[k * 4] = 46;
      tintBuf[k * 4 + 1] = 125;
      tintBuf[k * 4 + 2] = 50;
      tintBuf[k * 4 + 3] = 115;
    }
  }
  const tintPng = await sharp(tintBuf, {
    raw: { width: rw, height: rh, channels: 4 },
  })
    .resize(W, H, { kernel: sharp.kernel.nearest })
    .png()
    .toBuffer();

  const poly: [number, number][] = pts3857.map(([x, y]) => [
    ((x - bx0) / (bx1 - bx0)) * W,
    ((by1 - y) / (by1 - by0)) * H,
  ]);
  const svg = overlaySvg(W, H, poly, mPerPx);

  const png = await sharp({
    create: {
      width: W,
      height: H,
      channels: 4,
      background: { r: 0, g: 0, b: 0, alpha: 0 },
    },
  })
    .composite([{ input: tintPng }, { input: Buffer.from(svg) }])
    .png()
    .toBuffer();

  return new NextResponse(new Uint8Array(png), {
    headers: {
      "Content-Type": "image/png",
      "Cache-Control": "public, max-age=31536000, immutable",
    },
  });
}
