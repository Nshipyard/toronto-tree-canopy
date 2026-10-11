import { NextRequest, NextResponse } from "next/server";
import { join } from "path";
import { readFileSync, existsSync } from "fs";
import sharp from "sharp";
import { fromUrl, fromArrayBuffer } from "geotiff";
import { parcelById, CITY_SCOPE, cogBase } from "@/lib/canopy";

// GET /api/v1/parcel-map?parcel_id=TOP-…&lang=en|fr
// Server-renders a per-parcel tall-canopy PNG on demand: the parcel window is
// read from the ward's masked-CHM COG (uint16 decimetres, buildings NaN) via
// HTTP range reads, then rendered in the same visual language as the
// pre-rendered maps: CHM-grayscale base, green tint where CHM >= 8 m, parcel
// boundary (dark line, white underlay), 6 m neighbour buffer (dashed, the
// image edge), a 10 m scale bar, and a caption band naming the sources.
// Long edge 1080 px. Cacheable basically forever: the render is deterministic
// over static data.

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
  caption: string,
): string {
  const s = W / LONG_EDGE;
  const pts = poly.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const dash = `${(4 / mPerPx).toFixed(1)} ${(3 / mPerPx).toFixed(1)}`;
  const barPx = 10 / mPerPx;
  const bandH = Math.round(44 * s);
  const sbY = H - bandH - Math.round(26 * s);
  const sbX = Math.round(24 * s);
  const fsBar = Math.round(26 * s);
  const fsCap = Math.max(14, Math.round(22 * s));
  const esc = caption.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  return (
    `<svg width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg">` +
    `<rect x="4" y="4" width="${W - 8}" height="${H - 8}" fill="none" stroke="white" stroke-width="${Math.max(4, Math.round(7 * s))}" stroke-dasharray="${dash}"/>` +
    `<rect x="4" y="4" width="${W - 8}" height="${H - 8}" fill="none" stroke="#8a8fa0" stroke-width="${Math.max(2, Math.round(3 * s))}" stroke-dasharray="${dash}"/>` +
    `<polyline points="${pts}" fill="none" stroke="white" stroke-width="${Math.round(9 * s)}" stroke-linejoin="round"/>` +
    `<polyline points="${pts}" fill="none" stroke="#0a0f1e" stroke-width="${Math.max(2, Math.round(4 * s))}" stroke-linejoin="round"/>` +
    `<rect x="0" y="${H - bandH}" width="${W}" height="${bandH}" fill="black" fill-opacity="0.62"/>` +
    `<line x1="${sbX}" y1="${sbY}" x2="${sbX + barPx}" y2="${sbY}" stroke="white" stroke-width="${Math.max(3, Math.round(7 * s))}"/>` +
    `<line x1="${sbX}" y1="${sbY - Math.round(7 * s)}" x2="${sbX}" y2="${sbY + Math.round(7 * s)}" stroke="white" stroke-width="${Math.max(3, Math.round(7 * s))}"/>` +
    `<line x1="${sbX + barPx}" y1="${sbY - Math.round(7 * s)}" x2="${sbX + barPx}" y2="${sbY + Math.round(7 * s)}" stroke="white" stroke-width="${Math.max(3, Math.round(7 * s))}"/>` +
    `<text x="${sbX + barPx / 2}" y="${sbY - Math.round(12 * s)}" text-anchor="middle" font-family="DejaVu Sans, Verdana, sans-serif" font-weight="bold" font-size="${fsBar}" fill="white">10 m</text>` +
    `<text x="${W - Math.round(20 * s)}" y="${H - bandH + Math.round(28 * s)}" text-anchor="end" font-family="DejaVu Sans, Verdana, sans-serif" font-size="${fsCap}" fill="white">${esc}</text>` +
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
  const bx0 = Math.min(...xs) - BUFFER_M;
  const by0 = Math.min(...ys) - BUFFER_M;
  const bx1 = Math.max(...xs) + BUFFER_M;
  const by1 = Math.max(...ys) + BUFFER_M;
  const [lon0, lat0] = mercInv(bx0, by0);
  const [lon1, lat1] = mercInv(bx1, by1);

  // Read the window from the ward COG (uint16 decimetres, 65535 = nodata).
  const base = cogBase();
  const cogUrl = `${base}/ward_${parcel.ward}_chm.tif`;
  let raw: ArrayLike<number>;
  let rw: number, rh: number;
  try {
    const tiff = base.startsWith("http")
      ? await fromUrl(cogUrl)
      : await (async () => {
          const fn = join(base, `ward_${parcel.ward}_chm.tif`);
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
    return NextResponse.json(
      {
        error: "canopy map is not available for this parcel yet",
        pilot_scope: CITY_SCOPE,
      },
      { status: 502 },
    );
  }

  // Base: CHM grayscale; tint: green where CHM >= 8 m (buildings are NaN).
  const n = rw * rh;
  const baseBuf = Buffer.alloc(n * 3);
  const tintBuf = Buffer.alloc(n * 4);
  for (let k = 0; k < n; k++) {
    const rv = raw[k] as number;
    const v = rv === 65535 ? NaN : rv / 10;
    const g = Number.isFinite(v)
      ? Math.round(235 - (Math.min(Math.max(v, 0), 30) / 30) * 165)
      : 235;
    baseBuf[k * 3] = g;
    baseBuf[k * 3 + 1] = g;
    baseBuf[k * 3 + 2] = g;
    if (Number.isFinite(v) && v >= TALL_M) {
      tintBuf[k * 4] = 46;
      tintBuf[k * 4 + 1] = 125;
      tintBuf[k * 4 + 2] = 50;
      tintBuf[k * 4 + 3] = 115;
    }
  }

  const scale = Math.max(LONG_EDGE / Math.max(rw, rh), 1);
  const W = Math.max(1, Math.round(rw * scale));
  const H = Math.max(1, Math.round(rh * scale));
  const mPerPx = (bx1 - bx0) / W;

  const basePng = await sharp(baseBuf, {
    raw: { width: rw, height: rh, channels: 3 },
  })
    .resize(W, H, { kernel: sharp.kernel.lanczos3 })
    .png()
    .toBuffer();
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
  const caption = "Base: 2023 LiDAR surface · Canopy: 2023 LiDAR, buildings masked";
  const svg = overlaySvg(W, H, poly, mPerPx, caption);

  const png = await sharp(basePng)
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
