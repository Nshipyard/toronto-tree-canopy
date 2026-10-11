#!/usr/bin/env python3
"""extract_parcels_city.py - extract ALL Toronto parcels from the vendored CKAN dumps.

Reads (same sources as Nshipyard/toronto-parcel-spine, read-only):
  - data/pb_dump.csv : Property Boundaries dump (498,477 parcels city-wide)
  - data/ap_dump.csv : Address Points TOAR dump (525,365 points)

Writes ward-sharded working files (memory-bounded; one ward in RAM at a time):
  - data/parcels_toronto/ward_XX.json  (same record schema as data/parcels_ward12.json)
  - data/parcels_toronto/unplaced.json (parcels whose centroid falls in no ward)
  - data/parcels_toronto/manifest.json (counts per shard + sources)

Schema per parcel: parcel_id ("TOP-<PARCELID>"), parcelid, feature_type,
stated_area, area_m2, centroid_4326, address, address_count, rings_3857
(rings rounded to 0.1 m; plenty for 1 m CHM raster math).

Usage: .venv/bin/python scripts/extract_parcels_city.py
"""
import csv, json, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUTDIR = os.path.join(DATA, "parcels_toronto")
RAWDIR = os.path.join(OUTDIR, "raw")
csv.field_size_limit(10**9)


def load_wards():
    from shapely.geometry import shape
    from shapely.prepared import prep
    wards = []
    with open(os.path.join(DATA, "wards_dump.geojson"), newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            g = json.loads(row["geometry"])
            poly = shape(g)
            wards.append({
                "ward": (row.get("AREA_SHORT_CODE") or "").strip(),
                "name": (row.get("AREA_NAME") or "").strip(),
                "poly": poly,
                "prep": prep(poly),
                "bbox": poly.bounds,
            })
    return wards


def assign_ward(wards, lon, lat):
    for w in wards:
        x0, y0, x1, y1 = w["bbox"]
        if x0 <= lon <= x1 and y0 <= lat <= y1 and w["prep"].contains(
                __import__("shapely.geometry", fromlist=["Point"]).Point(lon, lat)):
            return w["ward"]
    return None


def parse_rings(geom_text):
    try:
        g = json.loads(geom_text)
    except Exception:
        return []
    t, coords = g.get("type"), g.get("coordinates", [])
    if t == "Polygon":
        return [coords[0]] if coords else []
    if t == "MultiPolygon":
        return [p[0] for p in coords if p]
    return []


def main():
    from pyproj import Transformer
    from shapely.geometry import Polygon, Point
    fwd = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    inv = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    os.makedirs(RAWDIR, exist_ok=True)
    wards = load_wards()
    print(f"wards loaded: {len(wards)}", flush=True)

    # ---- Phase B: property boundaries -> per-ward raw parcel files ----
    print("Phase B: property boundaries", flush=True)
    raw_fhs = {}
    def raw_fh(ward):
        key = ward or "unplaced"
        if key not in raw_fhs:
            raw_fhs[key] = open(os.path.join(RAWDIR, f"parcels_{key}.jsonl"), "w")
        return raw_fhs[key]

    ward_counts = defaultdict(int)
    n_rows = kept = multi = 0
    parcels_seen = set()
    with open(os.path.join(DATA, "pb_dump.csv"), newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            n_rows += 1
            if n_rows % 100000 == 0:
                print(f"  scanned {n_rows}, kept {kept}", flush=True)
            try:
                pid = int(row["PARCELID"])
            except (TypeError, ValueError):
                continue
            if pid in parcels_seen:
                multi += 1
                continue
            parcels_seen.add(pid)
            rings = parse_rings(row.get("geometry") or "")
            rr, areas = [], []
            for ring in rings:
                try:
                    p = Polygon(ring)
                except Exception:
                    continue
                if not p.is_valid or p.area == 0:
                    continue
                # Full precision, consistent with data/parcels_ward12.json.
                # (0.1 m rounding was tried and silently invalidated 115 real
                # parcels, including an 11,351 m2 one: rounding can collapse
                # near-duplicate vertices into self-intersections.)
                r3857 = [[x, y]
                         for x, y in (fwd.transform(a, b) for a, b in p.exterior.coords)]
                try:
                    q = Polygon(r3857)
                except Exception:
                    continue
                if q.is_valid and q.area > 0:
                    rr.append(r3857)
                    areas.append(q.area)
            if not rr:
                continue
            xs = [pt[0] for r in rr for pt in r]
            ys = [pt[1] for r in rr for pt in r]
            cx = sum(a * Polygon(r).centroid.x for a, r in zip(areas, rr)) / sum(areas)
            cy = sum(a * Polygon(r).centroid.y for a, r in zip(areas, rr)) / sum(areas)
            lon, lat = inv.transform(cx, cy)
            ward = assign_ward(wards, lon, lat)
            rec = {
                "parcelid": pid,
                "feature_type": (row.get("FEATURE_TYPE") or "").strip(),
                "stated_area": (row.get("STATEDAREA") or "").strip(),
                "area_m2": round(sum(areas), 1),
                "centroid_4326": [round(lon, 6), round(lat, 6)],
                "bbox_3857": [min(xs), min(ys), max(xs), max(ys)],
                "rings_3857": rr,
                "ward": ward,
            }
            raw_fh(ward).write(json.dumps(rec) + "\n")
            ward_counts[ward or "unplaced"] += 1
            kept += 1
    for fh in raw_fhs.values():
        fh.close()
    print(f"Phase B done: scanned {n_rows} rows, kept {kept} parcels, "
          f"dup PARCELIDs skipped={multi}", flush=True)

    # ---- Phase C: address points -> per-ward raw address files ----
    print("Phase C: address points", flush=True)
    addr_fhs = {}
    def addr_fh(ward):
        key = ward or "unplaced"
        if key not in addr_fhs:
            addr_fhs[key] = open(os.path.join(RAWDIR, f"addr_{key}.jsonl"), "w")
        return addr_fhs[key]
    n_ap = placed = 0
    with open(os.path.join(DATA, "ap_dump.csv"), newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            n_ap += 1
            if n_ap % 100000 == 0:
                print(f"  scanned {n_ap}", flush=True)
            try:
                pt = json.loads(row["geometry"])["coordinates"]
            except Exception:
                continue
            ward = assign_ward(wards, pt[0], pt[1])
            addr_fh(ward).write(json.dumps({
                "lon": pt[0], "lat": pt[1],
                "address": (row.get("ADDRESS_FULL") or "").strip(),
            }) + "\n")
            if ward:
                placed += 1
    for fh in addr_fhs.values():
        fh.close()
    print(f"Phase C done: {n_ap} address points, {placed} inside a ward", flush=True)

    # ---- Phase D: per ward, grid-join addresses onto parcels, write shard ----
    print("Phase D: join + write shards", flush=True)
    CELL = 0.005
    manifest = {"wards": {}, "sources": {
        "property_boundaries": "City of Toronto Open Data, Property Boundaries (local dump)",
        "address_points": "City of Toronto Open Data, Address Points TOAR (local dump)",
        "wards": "data/wards_dump.geojson (union = city boundary)",
    }}
    total = 0
    ward_keys = sorted(k for k in ward_counts if k != "unplaced") + (
        ["unplaced"] if "unplaced" in ward_counts else [])
    for wk in ward_keys:
        pf = os.path.join(RAWDIR, f"parcels_{wk}.jsonl")
        parcels = [json.loads(line) for line in open(pf)] if os.path.exists(pf) else []
        # grid index on 4326 bboxes
        grid = defaultdict(list)
        polys = {}
        for rec in parcels:
            x0, y0, x1, y1 = rec["bbox_3857"]
            lon0, lat0 = inv.transform(x0, y0)
            lon1, lat1 = inv.transform(x1, y1)
            rec["_bb"] = (lon0, lat0, lon1, lat1)
            rec["_polys"] = [Polygon([inv.transform(x, y) for x, y in r])
                             for r in rec["rings_3857"]]
            polys[rec["parcelid"]] = rec
            for cx in range(int(lon0 / CELL), int(lon1 / CELL) + 1):
                for cy in range(int(lat0 / CELL), int(lat1 / CELL) + 1):
                    grid[(cx, cy)].append(rec["parcelid"])
        addr_count = defaultdict(int)
        addr_first = {}
        af = os.path.join(RAWDIR, f"addr_{wk}.jsonl")
        if os.path.exists(af):
            for line in open(af):
                a = json.loads(line)
                for pid in grid.get((int(a["lon"] / CELL), int(a["lat"] / CELL)), []):
                    rec = polys[pid]
                    x0, y0, x1, y1 = rec["_bb"]
                    if not (x0 <= a["lon"] <= x1 and y0 <= a["lat"] <= y1):
                        continue
                    if any(poly.contains(Point(a["lon"], a["lat"]))
                           for poly in rec["_polys"]):
                        addr_count[pid] += 1
                        if pid not in addr_first and a["address"]:
                            addr_first[pid] = a["address"]
                        break
        out = []
        for rec in sorted(parcels, key=lambda r: r["parcelid"]):
            pid = rec["parcelid"]
            out.append({
                "parcel_id": f"TOP-{pid}",
                "parcelid": pid,
                "feature_type": rec["feature_type"],
                "stated_area": rec["stated_area"],
                "area_m2": rec["area_m2"],
                "centroid_4326": rec["centroid_4326"],
                "address": addr_first.get(pid),
                "address_count": addr_count.get(pid, 0),
                "rings_3857": rec["rings_3857"],
            })
        wname = next((w["name"] for w in wards if w["ward"] == wk), wk)
        shard = os.path.join(OUTDIR, f"ward_{wk}.json" if wk != "unplaced" else "unplaced.json")
        json.dump({"parcels": out,
                   "ward": f"{wk} {wname}" if wk != "unplaced" else "unplaced",
                   "sources": manifest["sources"]}, open(shard, "w"))
        sz = os.path.getsize(shard)
        manifest["wards"][wk] = {"parcels": len(out), "bytes": sz,
                                 "with_address": sum(1 for p in out if p["address_count"])}
        total += len(out)
        print(f"  ward {wk}: {len(out)} parcels -> {os.path.basename(shard)} "
              f"({sz/1e6:.1f} MB)", flush=True)
        del parcels, grid, polys  # free before next ward

    manifest["total_parcels"] = total
    manifest["total_bytes"] = sum(w["bytes"] for w in manifest["wards"].values())
    json.dump(manifest, open(os.path.join(OUTDIR, "manifest.json"), "w"), indent=2)
    print(f"DONE: {total} parcels, {manifest['total_bytes']/1e6:.1f} MB total", flush=True)


if __name__ == "__main__":
    main()
