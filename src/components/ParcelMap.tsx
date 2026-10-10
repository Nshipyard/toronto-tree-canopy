"use client";

import { useState } from "react";
import { Strings } from "@/lib/i18n";

// ParcelMap: per-parcel tall-canopy map pre-rendered by
// scripts/render_parcel_maps.py from the 2023 LiDAR surface, with tall-canopy
// pixels (CHM 8 m and up) tinted green. No schematic diagrams anywhere.
export default function ParcelMap({
  parcelId,
  t,
}: {
  parcelId: string;
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
