"use client";

import { useState } from "react";
import { Strings } from "@/lib/i18n";

// ParcelMap: real 2022 aerial imagery (pre-rendered by scripts/render_parcel_maps.py)
// with crown polygons drawn on top. No schematic diagrams anywhere.
export default function ParcelMap({
  parcelId,
  sample,
  t,
}: {
  parcelId: string;
  sample: boolean;
  t: Strings;
}) {
  const [imgError, setImgError] = useState(false);
  const src = `/parcels/${parcelId}.png`;
  return (
    <div className="mapwrap">
      <h3>{t.map.title}</h3>
      <div className="parcelmap">
        {!imgError ? (
          <img
            src={src}
            alt={t.map.title}
            onError={() => setImgError(true)}
            loading="lazy"
          />
        ) : (
          <div className="mapmissing">
            {t.map.missingImage}
          </div>
        )}
        {!sample && (
          <div className="maplegend maplegend-overlay" aria-label={t.map.title}>
            <span><span className="sw" style={{ background: "rgba(216,6,33,0.35)", border: "2px solid #d80621" }} />{t.map.legendMature}</span>
            <span><span className="sw" style={{ background: "rgba(46,125,50,0.35)", border: "2px solid #2e7d32" }} />{t.map.legendPossible}</span>
            <span><span className="swsq" />{t.map.legendParcel}</span>
            <span><span className="swdash" />{t.map.legendBuffer}</span>
          </div>
        )}
      </div>
      {sample && (
        <div className="maplegend" aria-label={t.map.title}>
          <span><span className="swsq" />{t.map.legendParcel}</span>
          <span><span className="swdash" />{t.map.legendBuffer}</span>
        </div>
      )}
    </div>
  );
}
