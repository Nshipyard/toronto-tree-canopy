"use client";

import ParcelMap from "./ParcelMap";
import { Strings } from "@/lib/i18n";

export interface ScreenResult {
  address: string;
  parcel_id: string;
  parcel_polygon: [number, number][];
  imagery_vintage: string;
  sample: boolean;
  lot: {
    tall_canopy_m2_ge6: number;
    tall_canopy_m2_ge8: number;
    max_chm_m: number | null;
    canopy_pct: number;
    p_any_ge_30cm: number;
    p_any_distinctive: number;
    crowns: never[];
  };
  neighbour_6m: {
    tall_canopy_m2_ge6: number;
    tall_canopy_m2_ge8: number;
    max_chm_m: number | null;
    p_any_ge_30cm: number;
    p_any_distinctive: number;
  };
  verdict: string;
  method: {
    vintage: string;
    calibration_auc: number;
    calibration_n: number;
    sample: boolean;
    note: string;
  };
  pilot_scope: string;
}

function pct(p: number) {
  return `${Math.round(p * 100)}%`;
}

function m2(v: number) {
  return v >= 100 ? `${Math.round(v)}` : v.toFixed(1);
}

function height(v: number | null) {
  return v === null ? "–" : `${v.toFixed(1)}`;
}

export default function ScreeningCard({ result, t }: { result: ScreenResult; t: Strings }) {
  const s = t.screen;
  const m = result.method;
  return (
    <article className="screencard" aria-live="polite">
      <div className="screencard-head">
        <h2 className="display">{s.lotLabel}: {result.address}</h2>
        <div className="screencard-meta">
          <span>{s.parcelId}: <code>{result.parcel_id}</code></span>
          <span>{s.imageryVintage}: <strong>{result.imagery_vintage}</strong></span>
          <span>{result.pilot_scope}</span>
        </div>
      </div>

      <p className="verdict">{result.verdict}</p>

      <div className="statgrid">
        <div className="stat">
          <div className="k">{s.tallCanopyArea}</div>
          <div className="v">{m2(result.lot.tall_canopy_m2_ge8)}<small> m²</small></div>
        </div>
        <div className="stat">
          <div className="k">{s.maxHeight}</div>
          <div className="v">{height(result.lot.max_chm_m)}<small> m</small></div>
        </div>
        <div className="stat">
          <div className="k">{s.canopyCover}</div>
          <div className="v">{result.lot.canopy_pct}<small>%</small></div>
        </div>
        <div className="stat">
          <div className="k">{s.pAnyMature}</div>
          <div className="v">{pct(result.lot.p_any_ge_30cm)}</div>
        </div>
        <div className="stat">
          <div className="k">{s.pAnyDistinctive}</div>
          <div className="v">{pct(result.lot.p_any_distinctive)}</div>
        </div>
      </div>

      <ParcelMap parcelId={result.parcel_id} t={t} />

      <div className="neighbour">
        <h3>{s.neighbourTitle}</h3>
        <p className="dim">{s.neighbourWhy}</p>
        <div className="nbstats">
          <div><div className="dim">{s.tallCanopyArea}</div><div className="v">{m2(result.neighbour_6m.tall_canopy_m2_ge8)} m²</div></div>
          <div><div className="dim">{s.maxHeight}</div><div className="v">{height(result.neighbour_6m.max_chm_m)} m</div></div>
          <div><div className="dim">{s.pAnyMature}</div><div className="v">{pct(result.neighbour_6m.p_any_ge_30cm)}</div></div>
          <div><div className="dim">{s.pAnyDistinctive}</div><div className="v">{pct(result.neighbour_6m.p_any_distinctive)}</div></div>
        </div>
      </div>

      <div className="honesty">
        <p className="methodline">
          {s.methodLine(m.calibration_auc.toFixed(2), m.calibration_n.toLocaleString("en-US"))}
        </p>
        <p>{s.honesty}</p>
        <p>{s.vintageCaveat}</p>
        <p>{s.nextStep}</p>
      </div>
    </article>
  );
}
