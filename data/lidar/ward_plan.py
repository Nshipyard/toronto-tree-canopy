"""One-time: per-ward fetch/compute plan for the city-wide masked run.

Reads the 25 ward polygons (data/wards_dump.geojson, CSV format), the ward
parcel shards (data/parcels_toronto/), and unplaced.json; writes
data/ward_plan.json:
  per ward: code, name, bbox_4326, expanded bbox (+150 m), the global 0.015 deg
  WCS chunk index ranges covering it, parcel count, and the unplaced parcel ids
  assigned to it (centroid-in-ward, else nearest ward polygon).

Run: .venv/bin/python3 data/lidar/ward_plan.py
"""
import csv
import json
import math
import os

from shapely.geometry import shape
from shapely.prepared import prep

csv.field_size_limit(10 ** 9)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "ward_plan.json")

STEP = 0.015          # WCS chunk size, degrees (pilot grid)
MARGIN_M = 150.0      # fetch margin around the ward bbox (m)


def load_wards():
    wards = []
    with open(os.path.join(DATA, "wards_dump.geojson"), newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            g = json.loads(row["geometry"])
            poly = shape(g)
            wards.append({
                "code": (row.get("AREA_SHORT_CODE") or "").strip(),
                "name": (row.get("AREA_NAME") or "").strip(),
                "poly": poly,
            })
    wards.sort(key=lambda w: w["code"])
    return wards


def main():
    wards = load_wards()
    assert len(wards) == 25, len(wards)
    for w in wards:
        w["prep"] = prep(w["poly"])
        w["bbox"] = w["poly"].bounds  # lon0, lat0, lon1, lat1
    print(f"{len(wards)} wards", flush=True)

    # unplaced parcels -> ward by centroid-in-polygon, else nearest polygon
    unp = json.load(open(os.path.join(DATA, "parcels_toronto", "unplaced.json")))["parcels"]
    print(f"unplaced parcels: {len(unp)}", flush=True)
    assign = {w["code"]: [] for w in wards}
    for p in unp:
        lon, lat = p["centroid_4326"]
        hit = None
        for w in wards:
            if w["prep"].contains(shape({"type": "Point", "coordinates": [lon, lat]})):
                hit = w["code"]
                break
        if hit is None:
            from shapely.geometry import Point
            pt = Point(lon, lat)
            hit = min(wards, key=lambda w: w["poly"].distance(pt))["code"]
        assign[hit].append(p["parcel_id"])

    plan = {"step_deg": STEP, "margin_m": MARGIN_M, "wards": {}}
    total_chunks = 0
    for w in wards:
        code = w["code"]
        lon0, lat0, lon1, lat1 = w["bbox"]
        lat_c = (lat0 + lat1) / 2
        dlat = MARGIN_M / 111320.0
        dlon = MARGIN_M / (111320.0 * math.cos(math.radians(lat_c)))
        elon0, elat0, elon1, elat1 = lon0 - dlon, lat0 - dlat, lon1 + dlon, lat1 + dlat
        i0, i1 = math.floor(elon0 / STEP), math.floor(elon1 / STEP)
        j0, j1 = math.floor(elat0 / STEP), math.floor(elat1 / STEP)
        n_chunks = (i1 - i0 + 1) * (j1 - j0 + 1)
        total_chunks += n_chunks
        shard = json.load(open(os.path.join(DATA, "parcels_toronto", f"ward_{code}.json")))
        plan["wards"][code] = {
            "name": w["name"],
            "bbox_4326": [lon0, lat0, lon1, lat1],
            "expanded_bbox_4326": [elon0, elat0, elon1, elat1],
            "chunk_i": [i0, i1],
            "chunk_j": [j0, j1],
            "n_chunks_layer": n_chunks,
            "parcels": len(shard["parcels"]),
            "unplaced_ids": assign[code],
        }
        print(f"ward {code} {w['name']}: {len(shard['parcels'])} parcels, "
              f"{n_chunks} chunks/layer, bbox {lon0:.4f},{lat0:.4f}..{lon1:.4f},{lat1:.4f}",
              flush=True)
    plan["total_chunks_both_layers"] = total_chunks * 2
    json.dump(plan, open(OUT, "w"), indent=1)
    print(f"total chunk requests (dsm+dtm): {total_chunks * 2}", flush=True)
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
