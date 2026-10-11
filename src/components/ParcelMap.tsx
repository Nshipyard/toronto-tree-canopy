"use client";

import { useEffect, useState } from "react";
import { Strings } from "@/lib/i18n";

// ParcelMap: per-parcel tall-canopy map in two layers.
// Base: City of Toronto 2022 aerial orthophoto (8 cm), fetched in the browser
// directly from the City's MapServer for the parcel window.
// Overlay: transparent PNG from /api/v1/parcel-map with the LiDAR tall-canopy
// tint (building-masked 2023 CHM, 8 m and up), parcel boundary, and 6 m
// neighbour buffer. A ?format=json call to the same route supplies the exact
// render window so both layers align pixel-for-pixel. Falls back to the
// overlay alone when the metadata or the photo cannot load.

const ORTHO_EXPORT =
  "https://gis.toronto.ca/arcgis/rest/services/basemap/cot_ortho_2022_color_8cm/MapServer/export";

interface MapMeta {
  bbox_3857: [number, number, number, number];
  width: number;
  height: number;
  m_per_px: number;
}

export default function ParcelMap({
  parcelId,
  t,
}: {
  parcelId: string;
  t: Strings;
}) {
  const [imgError, setImgError] = useState(false);
  const [meta, setMeta] = useState<MapMeta | null>(null);
  const overlaySrc = `/api/v1/parcel-map?parcel_id=${encodeURIComponent(parcelId)}`;

  useEffect(() => {
    let live = true;
    fetch(
      `/api/v1/parcel-map?parcel_id=${encodeURIComponent(parcelId)}&format=json`,
    )
      .then((r) => (r.ok ? r.json() : null))
      .then((m) => {
        if (live && m && Array.isArray(m.bbox_3857)) setMeta(m as MapMeta);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [parcelId]);

  const orthoSrc = meta
    ? `${ORTHO_EXPORT}?bbox=${meta.bbox_3857.map((v) => v.toFixed(2)).join(",")}` +
      `&bboxSR=3857&imageSR=3857&size=${meta.width},${meta.height}&format=jpg&f=image`
    : null;
  const barPct = meta ? ((10 / meta.m_per_px) / meta.width) * 100 : 0;

  return (
    <div className="mapwrap">
      <h3>{t.map.title}</h3>
      <div className="parcelmap">
        {orthoSrc && (
          <img
            src={orthoSrc}
            alt=""
            aria-hidden="true"
            className="orthobase"
            loading="lazy"
          />
        )}
        {!imgError ? (
          <img
            src={overlaySrc}
            alt={t.map.title}
            onError={() => setImgError(true)}
            loading="lazy"
            className={orthoSrc ? "tintoverlay" : "tintalone"}
          />
        ) : (
          <div className="mapmissing">{t.map.missingImage}</div>
        )}
        {!imgError && meta && barPct > 0 && barPct < 90 && (
          <div className="scalebar" style={{ width: `${barPct}%` }}>
            <span>10 m</span>
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
      <p className="mapcredit">{t.map.credit}</p>
    </div>
  );
}
