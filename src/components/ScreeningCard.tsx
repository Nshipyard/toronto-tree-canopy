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
    crown_count: number;
    canopy_pct: number;
    p_any_ge_30cm: number;
    p_any_distinctive: number;
    crowns: {
      polygon: [number, number][];
      crown_diameter_m: number;
      dbh_est_cm: number;
      dbh_pi95: [number, number];
      p_ge_30cm: number;
      p_gt_61cm: number;
    }[];
  };
  neighbour_6m: { crown_count: number; p_any_ge_30cm: number; p_any_distinctive: number };
  verdict: string;
  fee_line: string | null;
  method: { detection_f1: number; sample: boolean; note: string };
  pilot_scope: string;
}

function pct(p: number) {
  return `${Math.round(p * 100)}%`;
}

function crownBadge(c: ScreenResult["lot"]["crowns"][number], t: Strings) {
  if (c.p_ge_30cm >= 0.5) return <span className="badge mature">{t.screen.likelyMature}</span>;
  if (c.p_ge_30cm >= 0.2) return <span className="badge possible">{t.screen.maybeMature}</span>;
  return <span className="badge young">{t.screen.young}</span>;
}

export default function ScreeningCard({ result, t }: { result: ScreenResult; t: Strings }) {
  const s = t.screen;
  return (
    <article className="screencard" aria-live="polite">
      {result.sample && <div className="samplebanner">{s.sampleBanner}</div>}
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
          <div className="k">{s.crownsDetected}</div>
          <div className="v">{result.lot.crown_count}</div>
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

      <ParcelMap parcelId={result.parcel_id} sample={result.sample} t={t} />

      {result.lot.crowns.length > 0 && (
        <div className="crownlist">
          <h3>{s.crownListTitle}</h3>
          {result.lot.crowns.map((c, i) => (
            <div className="crownrow" key={i}>
              <div className="crown-name">
                {s.crownLabel(i + 1)}
                {crownBadge(c, t)}
              </div>
              <div>
                {s.crownDiameter}: <strong>{c.crown_diameter_m} m</strong>
                <div className="dim">
                  {s.dbhEstimate}: <strong>{c.dbh_est_cm} cm</strong> ({s.pi95}: {c.dbh_pi95[0]}–{c.dbh_pi95[1]} cm)
                </div>
              </div>
              <div>
                {s.pGe30}: <strong>{pct(c.p_ge_30cm)}</strong>
                <div className="dim">{s.pGt61}: <strong>{pct(c.p_gt_61cm)}</strong></div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="neighbour">
        <h3>{s.neighbourTitle}</h3>
        <p className="dim">{s.neighbourWhy}</p>
        <div className="nbstats">
          <div><div className="dim">{s.crownsDetected}</div><div className="v">{result.neighbour_6m.crown_count}</div></div>
          <div><div className="dim">{s.pAnyMature}</div><div className="v">{pct(result.neighbour_6m.p_any_ge_30cm)}</div></div>
          <div><div className="dim">{s.pAnyDistinctive}</div><div className="v">{pct(result.neighbour_6m.p_any_distinctive)}</div></div>
        </div>
      </div>

      {result.fee_line && <div className="feeline">{result.fee_line}</div>}

      <div className="honesty">
        <p className="methodline">
          {result.method.sample
            ? s.sampleMethod
            : s.methodLine(result.method.detection_f1.toFixed(2))}
        </p>
        <p>{s.honesty}</p>
        <p>{s.vintageCaveat}</p>
        <p>{s.nextStep}</p>
      </div>
    </article>
  );
}
