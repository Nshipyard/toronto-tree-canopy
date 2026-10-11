"use client";

import { useState } from "react";
import { Strings } from "@/lib/i18n";

// ParcelMap: per-parcel tall-canopy map server-rendered on demand by
// /api/v1/parcel-map from the ward's building-masked 2023 LiDAR CHM, with
// tall-canopy pixels (CHM 8 m and up) tinted green. No schematic diagrams
// anywhere. Falls back to a message when the render is unavailable.
export default function ParcelMap({
  parcelId,
  t,
}: {
  parcelId: string;
  t: Strings;
}) {
  const [imgError, setImgError] = useState(false);
  const src = `/api/v1/parcel-map?parcel_id=${encodeURIComponent(parcelId)}`;
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
        {!imgError && (
          <div className="maplegend maplegend-overlay" aria-label={t.map.title}>
            <span><span className="sw" style={{ background: "rgba(46,125,50,0.45)", border: "2px solid #2e7d32" }} />{t.map.legendTall}</span>
            <span><span className="swsq" />{t.map.legendParcel}</span>
            <span><span className="swdash" />{t.map.legendBuffer}</span>
          </div>
        )}
      </div>
    </div>
  );
}
