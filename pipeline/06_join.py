#!/usr/bin/env python3
"""06_join.py — join detected crowns to parcels; write the pilot GeoJSON.

For each parcel: crowns whose center falls inside (canopy area clipped to the
parcel), plus a 6 m neighbour buffer (crown centers within 6 m of the parcel
boundary but outside it), per the Private Tree By-law site-plan rule.

DBH comes from the GENERIC urban allometry (species is NOT guessed from RGB):
  mu = a + b*log10(crown_diameter_m); DBH | crown ~ LogNormal(mu, sigma)
  p_ge_30cm = 1 - Phi((log10(30)-mu)/sigma); p_gt_61cm likewise.

Output: data/parcels-ward12.geojson (EPSG:4326), per the app contract.
"""
import json, math, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

NEIGHBOUR_M = 6.0

def norm_cdf(z):
    return 0.5*(1.0 + math.erf(z/math.sqrt(2.0)))

def main():
    from pyproj import Transformer
    from shapely.geometry import Polygon, Point, box
    inv = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    crowns = json.load(open(os.path.join(DATA, "crowns_ward12.json")))["crowns"]
    allo = json.load(open(os.path.join(DATA, "allometry.json"))
    gen = allo["groups"]["GENERIC"]
    a, b, sig = gen["a"], gen["b"], gen["sigma_log10"]
    parcels = json.load(open(os.path.join(DATA, "parcels_ward12.json")))["parcels"]
    print(f"crowns={len(crowns)} parcels={len(parcels)}", flush=True)

    # per-crown DBH stats (generic urban allometry; species unknown from RGB)
    for c in crowns:
        mu = a + b*math.log10(max(c["crown_diameter_m"], 0.5))
        c["_mu"] = mu
        c["_p30"] = 1.0 - norm_cdf((math.log10(30)-mu)/sig)
        c["_p61"] = 1.0 - norm_cdf((math.log10(61)-mu)/sig)
        c["_lo"] = 10**(mu-1.96*sig)
        c["_hi"] = 10**(mu+1.96*sig)
        c["_est"] = 10**mu

    # spatial hash of crown centers
    CELL = 50.0
    grid = defaultdict(list)
    for c in crowns:
        grid[(int(c["cx_3857"]//CELL), int(c["cy_3857"]//CELL))].append(c)

    def crowns_near(x0, y0, x1, y1):
        out = []
        for ix in range(int(x0//CELL), int(x1//CELL)+1):
            for iy in range(int(y0//CELL), int(y1//CELL)+1):
                out.extend(grid.get((ix, iy), []))
        return out

    def crown_feature(c):
        x0, y0, x1, y1 = c["bbox_3857"]
        ring = [inv.transform(x, y) for x, y in
                [(x0,y0),(x1,y0),(x1,y1),(x0,y1),(x0,y0)]]
        return {
            "polygon": [[round(lon,7), round(lat,7)] for lon, lat in ring],
            "crown_diameter_m": round(c["crown_diameter_m"], 2),
            "dbh_est_cm": round(c["_est"], 1),
            "dbh_pi95_lo": round(c["_lo"], 1),
            "dbh_pi95_hi": round(c["_hi"], 1),
            "p_ge_30cm": round(c["_p30"], 4),
            "p_gt_61cm": round(c["_p61"], 4),
        }

    features = []
    total_crowns = 0
    for pi, p in enumerate(parcels):
        polys = []
        for ring in p["rings_3857"]:
            try:
                poly = Polygon(ring)
            except Exception:
                continue
            if poly.is_valid and poly.area > 0:
                polys.append(poly)
        if not polys:
            continue
        area = sum(pp.area for pp in polys)
        # candidate crowns in bbox expanded by neighbour distance
        xs = [pt[0] for r in p["rings_3857"] for pt in r]
        ys = [pt[1] for r in p["rings_3857"] for pt in r]
        cand = crowns_near(min(xs)-NEIGHBOUR_M, min(ys)-NEIGHBOUR_M,
                           max(xs)+NEIGHBOUR_M, max(ys)+NEIGHBOUR_M)
        inside, neigh = [], []
        for c in cand:
            pt = Point(c["cx_3857"], c["cy_3857"])
            if any(pp.contains(pt) for pp in polys):
                inside.append(c)
            else:
                # within 6 m of boundary?
                if any(pp.boundary.distance(pt) <= NEIGHBOUR_M for pp in polys):
                    neigh.append(c)
        canopy_area = 0.0
        crown_feats = []
        for c in inside:
            crown_feats.append(crown_feature(c))
            bb = box(*c["bbox_3857"])
            for pp in polys:
                inter = bb.intersection(pp)
                if not inter.is_empty:
                    canopy_area += inter.area
                    break
        def rollup(cs):
            if not cs:
                return {"crown_count": 0, "p_any_ge_30cm": 0.0, "p_any_distinctive": 0.0}
            p30 = 1.0 - math.prod(1.0 - c["_p30"] for c in cs)
            p61 = 1.0 - math.prod(1.0 - c["_p61"] for c in cs)
            return {"crown_count": len(cs), "p_any_ge_30cm": round(p30, 4),
                    "p_any_distinctive": round(p61, 4)}
        r_in, r_nb = rollup(inside), rollup(neigh)
        # parcel polygon -> 4326 (largest ring as geometry; multipolygons kept as MultiPolygon)
        polys4326 = []
        for ring in p["rings_3857"]:
            polys4326.append([[round(lon,7), round(lat,7)] for lon, lat in
                              (inv.transform(x, y) for x, y in ring)])
        geom = ({"type": "Polygon", "coordinates": [polys4326[0]]} if len(polys4326) == 1
                else {"type": "MultiPolygon", "coordinates": [[r] for r in polys4326]})
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "parcel_id": p["parcel_id"],
                "address": p["address"],
                "crowns": crown_feats,
                "crown_count": r_in["crown_count"],
                "canopy_pct": round(100.0*canopy_area/max(area,1e-9), 2),
                "p_any_ge_30cm": r_in["p_any_ge_30cm"],
                "p_any_distinctive": r_in["p_any_distinctive"],
                "neighbour_6m": {"crown_count": r_nb["crown_count"],
                                 "p_any_ge_30cm": r_nb["p_any_ge_30cm"],
                                 "p_any_distinctive": r_nb["p_any_distinctive"]},
                "imagery_vintage": "2022",
            },
        })
        total_crowns += len(inside)
        if (pi+1) % 2000 == 0:
            print(f"  {pi+1}/{len(parcels)} parcels", flush=True)

    fc = {"type": "FeatureCollection", "features": features,
          "crs_note": "EPSG:4326",
          "disclaimer": ("SCREENING SIGNAL ONLY — not a permit determination. "
                         "Crowns detected by AI on 2022 leaf-off ortho; DBH estimated "
                         "from a generic urban allometry with 95% prediction intervals. "
                         "Trees removed after 2022 are invisible. Confirm with an arborist.")}
    out = os.path.join(DATA, "parcels-ward12.geojson")
    json.dump(fc, open(out, "w"))
    print(f"wrote {len(features)} parcels, {total_crowns} crowns -> {out}")

if __name__ == "__main__":
    main()
