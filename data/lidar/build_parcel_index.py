"""One-time: compact parcel spatial index + tile list for the city-wide run.

Reads data/parcels_toronto/ward_*.json + unplaced.json (+ ward assignments from
data/ward_plan.json) and writes:
  - data/parcel_centroids.npz (gitignored): parcel_id (U16), centroid lon/lat
    (float32), ward code (U2). ~500k rows, fast to load per tile run.
  - data/tile_plan.json: the global 0.015 deg chunk grid tiled into 4x4-chunk
    blocks covering the city; per tile: chunk i/j ranges, core bbox (4326),
    and the ward codes whose bbox intersects the tile.

Run: .venv/bin/python3 data/lidar/build_parcel_index.py
"""
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(ROOT, "data")
STEP = 0.015
TILE_CHUNKS = 4  # 4x4 chunk blocks


def main():
    plan = json.load(open(os.path.join(DATA, "ward_plan.json")))
    wards = plan["wards"]

    ids, lons, lats, wcodes = [], [], [], []
    for code in sorted(wards):
        shard = json.load(open(os.path.join(DATA, "parcels_toronto", f"ward_{code}.json")))
        for p in shard["parcels"]:
            ids.append(p["parcel_id"])
            lon, lat = p["centroid_4326"]
            lons.append(lon)
            lats.append(lat)
            wcodes.append(code)
        for pid in wards[code]["unplaced_ids"]:
            pass  # unplaced handled below from unplaced.json
    # unplaced parcels (full records live in unplaced.json)
    unp = json.load(open(os.path.join(DATA, "parcels_toronto", "unplaced.json")))["parcels"]
    pid2ward = {}
    for code in wards:
        for pid in wards[code]["unplaced_ids"]:
            pid2ward[pid] = code
    for p in unp:
        ids.append(p["parcel_id"])
        lon, lat = p["centroid_4326"]
        lons.append(lon)
        lats.append(lat)
        wcodes.append(pid2ward[p["parcel_id"]])
    ids = np.array(ids)
    assert len(ids) == len(set(ids)), "duplicate parcel ids"
    np.savez_compressed(
        os.path.join(DATA, "parcel_centroids.npz"),
        parcel_id=ids,
        lon=np.array(lons, dtype="float32"),
        lat=np.array(lats, dtype="float32"),
        ward=np.array(wcodes),
    )
    print(f"parcel index: {len(ids)} parcels", flush=True)

    # tile the global chunk grid in 4x4 blocks
    i_min = min(w["chunk_i"][0] for w in wards.values())
    i_max = max(w["chunk_i"][1] for w in wards.values())
    j_min = min(w["chunk_j"][0] for w in wards.values())
    j_max = max(w["chunk_j"][1] for w in wards.values())
    wbbox = {c: wards[c]["bbox_4326"] for c in wards}
    tiles = []
    t = 0
    for ti0 in range(i_min, i_max + 1, TILE_CHUNKS):
        for tj0 in range(j_min, j_max + 1, TILE_CHUNKS):
            ti1 = min(ti0 + TILE_CHUNKS - 1, i_max)
            tj1 = min(tj0 + TILE_CHUNKS - 1, j_max)
            lon0, lat0 = ti0 * STEP, tj0 * STEP
            lon1, lat1 = (ti1 + 1) * STEP, (tj1 + 1) * STEP
            # wards whose bbox intersects this tile
            hit = [c for c, b in wbbox.items()
                   if not (b[2] < lon0 or b[0] > lon1 or b[3] < lat0 or b[1] > lat1)]
            if not hit:
                continue
            tiles.append({
                "tile": t,
                "chunk_i": [ti0, ti1],
                "chunk_j": [tj0, tj1],
                "core_bbox_4326": [lon0, lat0, lon1, lat1],
                "wards": sorted(hit),
            })
            t += 1
    json.dump({"step_deg": STEP, "tile_chunks": TILE_CHUNKS, "tiles": tiles},
              open(os.path.join(DATA, "tile_plan.json"), "w"), indent=1)
    print(f"tiles: {len(tiles)}", flush=True)
    # sanity: every parcel centroid falls in some tile core
    lon = np.array(lons, dtype="float32")
    lat = np.array(lats, dtype="float32")
    covered = np.zeros(len(ids), dtype=bool)
    for tl in tiles:
        b = tl["core_bbox_4326"]  # [lon0, lat0, lon1, lat1]
        covered |= (lon >= b[0]) & (lon <= b[2]) & (lat >= b[1]) & (lat <= b[3])
    print(f"parcels outside all tile cores: {(~covered).sum()}", flush=True)


if __name__ == "__main__":
    main()
