// Minimal MCP server over streamable HTTP (JSON-RPC 2.0 via POST).
// Supports: initialize, tools/list, tools/call. Stateless.
// Tools: canopy_screen, parcel_crowns.

import { NextResponse } from "next/server";
import { screenAddress, parcelById, ScreenError, buildScreenPayload, PILOT_SCOPE } from "@/lib/canopy";
import { pickLang } from "@/lib/i18n";

const SERVER = { name: "toronto-tree-canopy", version: "0.1.0" };

const TOOLS = [
  {
    name: "canopy_screen",
    description:
      "Per-lot tree screening for one Toronto address in the Ward 12 (Davenport) pilot: detected crown polygons with estimated trunk diameters (95% prediction intervals), per-crown probabilities of clearing the Private Tree By-law thresholds (30 cm permit threshold; 61 cm Distinctive tier), the 6 m neighbour-buffer rollup matching the by-law site-plan rule, canopy percent, a plain-English verdict, and the method note with detection F1 and imagery vintage. Screening signal only; not a permit determination. Addresses outside the pilot return a 404-style error.",
    inputSchema: {
      type: "object",
      properties: {
        address: { type: "string", description: "Toronto street address, e.g. '407 Arlington Ave'." },
        lang: { type: "string", enum: ["en", "fr"], description: "Verdict language. Default 'en'." },
      },
      required: ["address"],
    },
  },
  {
    name: "parcel_crowns",
    description:
      "Detected crowns for one pilot parcel by parcel ID (e.g. 'TOP-W12-0103'): crown polygons, crown diameters, estimated DBH with 95% prediction intervals, per-crown 30 cm / 61 cm probabilities, parcel rollups, and the 6 m neighbour-buffer rollup. Screening signal only; not a permit determination.",
    inputSchema: {
      type: "object",
      properties: {
        parcel_id: { type: "string", description: "Parcel ID, e.g. 'TOP-W12-0103'." },
        lang: { type: "string", enum: ["en", "fr"], description: "Verdict language. Default 'en'." },
      },
      required: ["parcel_id"],
    },
  },
];

function ok(id: unknown, result: unknown) {
  return { jsonrpc: "2.0", id, result };
}
function err(id: unknown, code: number, message: string) {
  return { jsonrpc: "2.0", id, error: { code, message } };
}
function textResult(data: unknown) {
  return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}

async function handle(msg: unknown) {
  const m = msg as { jsonrpc?: string; method?: string; id?: unknown; params?: { name?: string; arguments?: Record<string, unknown> } };
  if (!m || m.jsonrpc !== "2.0" || typeof m.method !== "string") {
    return err((m as { id?: unknown })?.id ?? null, -32600, "Invalid Request");
  }
  const id = m.id ?? null;
  switch (m.method) {
    case "initialize":
      return ok(id, {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: SERVER,
      });
    case "notifications/initialized":
      return null;
    case "tools/list":
      return ok(id, { tools: TOOLS });
    case "tools/call": {
      const { name, arguments: args } = m.params ?? {};
      try {
        if (name === "canopy_screen") {
          const address = String(args?.address ?? "").trim();
          if (!address) return err(id, -32602, "address is required");
          const lang = pickLang(typeof args?.lang === "string" ? args.lang : undefined);
          try {
            const payload = await screenAddress(address, lang);
            return ok(id, textResult(payload));
          } catch (e) {
            if (e instanceof ScreenError) return err(id, -32001, JSON.stringify(e.body));
            throw e;
          }
        }
        if (name === "parcel_crowns") {
          const parcelId = String(args?.parcel_id ?? "").trim();
          if (!parcelId) return err(id, -32602, "parcel_id is required");
          const lang = pickLang(typeof args?.lang === "string" ? args.lang : undefined);
          const found = parcelById(parcelId);
          if (!found) {
            return err(id, -32001, JSON.stringify({ error: `parcel ${parcelId} not found`, pilot_scope: PILOT_SCOPE }));
          }
          return ok(id, textResult(buildScreenPayload(found.parcel, found.parcel.address, lang, found.sample)));
        }
        return err(id, -32602, `Unknown tool ${name}`);
      } catch (e) {
        return err(id, -32000, `Tool error: ${(e as Error).message}`);
      }
    }
    default:
      return err(id, -32601, `Method not found: ${m.method}`);
  }
}

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(err(null, -32700, "Parse error"), { status: 400 });
  }
  if (Array.isArray(body)) {
    const out = (await Promise.all(body.map(handle))).filter((r) => r !== null);
    return NextResponse.json(out);
  }
  const out = await handle(body);
  if (out === null) return new NextResponse(null, { status: 202 });
  return NextResponse.json(out);
}

export async function GET() {
  return NextResponse.json(
    { error: "This MCP server accepts JSON-RPC 2.0 via POST only." },
    { status: 405 },
  );
}

export async function DELETE() {
  return new NextResponse(null, { status: 405 });
}
