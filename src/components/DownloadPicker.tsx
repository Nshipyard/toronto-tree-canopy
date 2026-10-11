"use client";

import { useState } from "react";

const WARDS = Array.from({ length: 25 }, (_, i) => String(i + 1).padStart(2, "0"));

// Per-ward dataset downloads: the ward picker drives both format buttons at
// /api/download?format=…&ward=NN, which serves pre-generated static files.
// Takes plain strings (not the i18n object: it carries functions, which
// cannot cross the server/client boundary).
export default function DownloadPicker({
  wardLabel,
  geojsonLabel,
  csvLabel,
}: {
  wardLabel: string;
  geojsonLabel: string;
  csvLabel: string;
}) {
  const [ward, setWard] = useState("09");
  return (
    <div>
      <label className="dllabel">
        {wardLabel}{" "}
        <select
          value={ward}
          onChange={(e) => setWard(e.target.value)}
          aria-label={wardLabel}
        >
          {WARDS.map((w) => (
            <option key={w} value={w}>
              {w}
            </option>
          ))}
        </select>
      </label>
      <div className="dlbuttons">
        <a className="dlbutton" href={`/api/download?format=geojson&ward=${ward}`}>
          {geojsonLabel}
        </a>
        <a className="dlbutton" href={`/api/download?format=csv&ward=${ward}`}>
          {csvLabel}
        </a>
      </div>
    </div>
  );
}
