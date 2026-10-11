"""Build per-ward static download files from the tile records.

Reads data/tiles_out/tile_*.json and writes, per ward:
  data/downloads/ward_<NN>.csv     - one row per parcel, metrics only
  data/downloads/ward_<NN>.geojson - FeatureCollection with parcel rings
Served by /api/download?format=…&ward=NN from the shard storage.

Run: .venv/bin/python3 scripts/build_downloads.py
"""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
TILES_OUT = os.path.join(DATA, "tiles_out")
OUT = os.path.join(DATA, "downloads")

CSV_HEADER = ("parcel_id,address,area_m2,ward,imagery_vintage,"
              "lot_tall_canopy_m2_ge6,lot_tall_canopy_m2_ge8,lot_max_chm_m,lot_canopy_pct_8,"
              "lot_p_any_ge_30cm,lot_p_any_distinctive,"
              "buffer_tall_canopy_m2_ge6,buffer_tall_canopy_m2_ge8,buffer_max_chm_m,"
              "buffer_p_any_ge_30cm,buffer_p_any_distinctive")


def q(s):
    return '"' + str(s if s is not None else "").replace('"', '""') + '"'


def main():
    os.makedirs(OUT, exist_ok=True)
    # Deduplicate boundary parcels (same most-interior rule as shard build).
    import re as _re
    tile_plan = json.load(open(os.path.join(DATA, "tile_plan.json")))["tiles"]
    cores = {t["tile"]: t["core_bbox_4326"] for t in tile_plan}

    def interiority(bbox, lon, lat):
        return min(lon - bbox[0], bbox[2] - lon, lat - bbox[1], bbox[3] - lat)

    best = {}
    for fn in sorted(os.listdir(TILES_OUT)):
        m = _re.match(r"tile_(\d+)\.json", fn)
        if not m:
            continue
        cb = cores[int(m.group(1))]
        recs = json.load(open(os.path.join(TILES_OUT, fn)))
        for pid, p in recs.items():
            inter = interiority(cb, p["centroid_4326"][0], p["centroid_4326"][1])
            if pid not in best or inter > best[pid][0]:
                best[pid] = (inter, p)
    by_ward = {}
    for pid, (_, p) in best.items():
        by_ward.setdefault(p["ward"], []).append(p)
    n = len(best)
    print(f"{n} records in {len(by_ward)} wards", flush=True)
    assert n == 498463, f"count {n}"
    for ward in sorted(by_ward):
        recs = by_ward[ward]
        # CSV
        with open(os.path.join(OUT, f"ward_{ward}.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(CSV_HEADER.split(","))
            for p in recs:
                L, B = p["lot"], p["buffer_6m"]
                w.writerow([p["parcel_id"], p["address"], p["area_m2"], p["ward"],
                            p["imagery_vintage"],
                            L["tall_canopy_m2_ge6"], L["tall_canopy_m2_ge8"],
                            L["max_chm_m"] if L["max_chm_m"] is not None else "",
                            L["canopy_pct_8"] if L["canopy_pct_8"] is not None else "",
                            L["p_any_ge_30cm"], L["p_any_distinctive"],
                            B["tall_canopy_m2_ge6"], B["tall_canopy_m2_ge8"],
                            B["max_chm_m"] if B["max_chm_m"] is not None else "",
                            B["p_any_ge_30cm"], B["p_any_distinctive"]])
        # GeoJSON
        feats = []
        for p in recs:
            L, B = p["lot"], p["buffer_6m"]
            feats.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [p["ring_4326"]]},
                "properties": {
                    "parcel_id": p["parcel_id"], "address": p["address"],
                    "area_m2": p["area_m2"], "ward": p["ward"],
                    "imagery_vintage": p["imagery_vintage"],
                    "lot_tall_canopy_m2_ge6": L["tall_canopy_m2_ge6"],
                    "lot_tall_canopy_m2_ge8": L["tall_canopy_m2_ge8"],
                    "lot_max_chm_m": L["max_chm_m"],
                    "lot_canopy_pct_8": L["canopy_pct_8"],
                    "lot_p_any_ge_30cm": L["p_any_ge_30cm"],
                    "lot_p_any_distinctive": L["p_any_distinctive"],
                    "buffer_tall_canopy_m2_ge6": B["tall_canopy_m2_ge6"],
                    "buffer_tall_canopy_m2_ge8": B["tall_canopy_m2_ge8"],
                    "buffer_max_chm_m": B["max_chm_m"],
                    "buffer_p_any_ge_30cm": B["p_any_ge_30cm"],
                    "buffer_p_any_distinctive": B["p_any_distinctive"],
                },
            })
        with open(os.path.join(OUT, f"ward_{ward}.geojson"), "w") as fh:
            json.dump({"type": "FeatureCollection", "features": feats}, fh)
        csv_mb = os.path.getsize(os.path.join(OUT, f"ward_{ward}.csv")) / 1e6
        gj_mb = os.path.getsize(os.path.join(OUT, f"ward_{ward}.geojson")) / 1e6
        print(f"ward {ward}: {len(recs)} parcels, csv {csv_mb:.1f} MB, "
              f"geojson {gj_mb:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
