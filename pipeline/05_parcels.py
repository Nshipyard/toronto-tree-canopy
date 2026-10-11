#!/usr/bin/env python3
"""05_parcels.py — build Ward 12 parcel set from local CKAN dumps.

Reads (downloaded with curl; the datastore_search API truncates on this
sandbox for the property-boundaries resource):
  - data/pb_dump.csv : Property Boundaries dump (resource 4270614e-...)
  - data/ap_dump.csv : Address Points TOAR dump (resource 0b3756af-...)
Same sources as Nshipyard/toronto-parcel-spine, used read-only.

Keeps parcels whose centroid falls inside the ward polygon, joins addresses
by point-in-polygon, writes data/parcels_ward12.json with rings in EPSG:3857
(for metric math) plus centroid in EPSG:4326.

Usage: python3 05_parcels.py [ward_geojson] [--out data/parcels_ward12.json]
"""
import argparse, csv, json, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
csv.field_size_limit(10**9)

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
    ap = argparse.ArgumentParser()
    ap.add_argument("ward_geojson", default=os.path.join(DATA, "ward12.geojson"), nargs="?")
    ap.add_argument("--out", default=os.path.join(DATA, "parcels_ward12.json"))
    ap.add_argument("--pb", default=os.path.join(DATA, "pb_dump.csv"))
    ap.add_argument("--ap", default=os.path.join(DATA, "ap_dump.csv"))
    args = ap.parse_args()

    from pyproj import Transformer
    from shapely.geometry import Polygon, Point
    from shapely.ops import unary_union
    fwd = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    inv = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    wg = json.load(open(args.ward_geojson))
    wgeom = wg["features"][0]["geometry"] if wg["type"] == "FeatureCollection" else wg["geometry"]
    coords = wgeom["coordinates"]
    rings4326 = [coords[0]] if wgeom["type"] == "Polygon" else [p[0] for p in coords]
    ward_poly = unary_union([Polygon(r) for r in rings4326])
    wx0, wy0, wx1, wy1 = ward_poly.bounds
    print(f"ward bounds: {wx0:.4f},{wy0:.4f} -> {wx1:.4f},{wy1:.4f}", flush=True)

    print("Pass 1: property boundaries (local dump)", flush=True)
    parcels = {}
    n_rows = 0
    with open(args.pb, newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            n_rows += 1
            if n_rows % 100000 == 0:
                print(f"  scanned {n_rows}, kept {len(parcels)}", flush=True)
            try:
                pid = int(row["PARCELID"])
            except (TypeError, ValueError):
                continue
            rings = parse_rings(row.get("geometry") or "")
            if not rings:
                continue
            keep = []
            for ring in rings:
                try:
                    p = Polygon(ring)
                except Exception:
                    continue
                if not p.is_valid or p.area == 0:
                    continue
                c = p.centroid
                if not (wx0 <= c.x <= wx1 and wy0 <= c.y <= wy1):
                    continue
                if not ward_poly.contains(c):
                    continue
                keep.append(p)
            if not keep:
                continue
            agg = parcels.get(pid)
            if agg is None:
                agg = parcels[pid] = {"parcelid": pid,
                                      "feature_type": (row.get("FEATURE_TYPE") or "").strip(),
                                      "stated_area": (row.get("STATEDAREA") or "").strip(),
                                      "rings_3857": []}
            for p in keep:
                r3857 = [fwd.transform(x, y) for x, y in p.exterior.coords]
                poly = Polygon(r3857)
                if poly.is_valid and poly.area > 0:
                    agg["rings_3857"].append([list(pt) for pt in poly.exterior.coords])
    print(f"scanned {n_rows} rows; parcels in ward: {len(parcels)}", flush=True)

    for pid, agg in parcels.items():
        areas, cxs, cys = [], [], []
        for ring in agg["rings_3857"]:
            poly = Polygon(ring)
            areas.append(poly.area)
            c = poly.centroid
            cxs.append(c.x); cys.append(c.y)
        tot = sum(areas)
        agg["area_m2"] = tot
        agg["centroid_3857"] = ([sum(a*x for a, x in zip(areas, cxs))/tot,
                                sum(a*y for a, y in zip(areas, cys))/tot] if tot > 0 else [0, 0])

    print("Pass 2: address points (local dump, grid join)", flush=True)
    CELL = 0.005
    grid = defaultdict(list)
    for pid, agg in parcels.items():
        xs = [p[0] for r in agg["rings_3857"] for p in r]
        ys = [p[1] for r in agg["rings_3857"] for p in r]
        if not xs:
            continue
        lon0, lat0 = inv.transform(min(xs), min(ys))
        lon1, lat1 = inv.transform(max(xs), max(ys))
        bb = (lon0, lat0, lon1, lat1)
        agg["_bb4326"] = bb
        agg["_polys4326"] = [Polygon([inv.transform(x, y) for x, y in ring])
                             for ring in agg["rings_3857"]]
        for cx in range(int(bb[0]/CELL), int(bb[2]/CELL)+1):
            for cy in range(int(bb[1]/CELL), int(bb[3]/CELL)+1):
                grid[(cx, cy)].append(pid)

    addr_count = defaultdict(int)
    addr_first = {}
    n_ap = 0
    with open(args.ap, newline="") as f:
        rdr = csv.DictReader(f)
        cols = rdr.fieldnames
        addr_col = "ADDRESS_FULL" if "ADDRESS_FULL" in cols else cols[1]
        for row in rdr:
            n_ap += 1
            try:
                pt = json.loads(row["geometry"])["coordinates"]
            except Exception:
                continue
            px, py = pt[0], pt[1]
            for pid in grid.get((int(px/CELL), int(py/CELL)), []):
                agg = parcels[pid]
                x0, y0, x1, y1 = agg["_bb4326"]
                if not (x0 <= px <= x1 and y0 <= py <= y1):
                    continue
                if any(poly.contains(Point(px, py)) for poly in agg["_polys4326"]):
                    addr_count[pid] += 1
                    if pid not in addr_first:
                        addr_first[pid] = (row.get(addr_col) or "").strip()
                    break
    print(f"address points scanned: {n_ap}; parcels with >=1 address: {len(addr_count)}", flush=True)

    out = []
    for pid in sorted(parcels):
        agg = parcels[pid]
        cx3857, cy3857 = agg["centroid_3857"]
        lon, lat = inv.transform(cx3857, cy3857)
        out.append({
            "parcel_id": f"TOP-{pid}",
            "parcelid": pid,
            "feature_type": agg["feature_type"],
            "stated_area": agg["stated_area"],
            "area_m2": round(agg["area_m2"], 1),
            "centroid_4326": [round(lon, 6), round(lat, 6)],
            "address": addr_first.get(pid),
            "address_count": addr_count.get(pid, 0),
            "rings_3857": agg["rings_3857"],
        })
    json.dump({"parcels": out, "ward": "12 Davenport",
               "sources": {"property_boundaries": "4270614e-0b5e-4b54-a2bb-18ef92237646",
                           "address_points": "0b3756af-9caf-4f0f-ac28-9c6617adede4"}},
              open(args.out, "w"))
    print(f"wrote {len(out)} parcels -> {args.out}")

if __name__ == "__main__":
    main()
