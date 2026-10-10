#!/usr/bin/env python3
"""Generate data/sample-parcels.geojson for Toronto Tree Canopy (SAMPLE data).

Five synthetic residential parcels near 407 Arlington Ave, Toronto
(real coordinate anchor ~43.6789N, -79.4414W). Conforms exactly to the
pipeline output schema. Clearly marked synthetic; the pipeline agent will
replace with measured pilot data in data/parcels-ward12.geojson.

Method (sample only):
- crown ellipse polygons (8 vertices, jittered), positions hand-plausible
- dbh_est_cm = 5.0 * crown_diameter_m + jitter (generic urban allometry stand-in)
- 95% PI width = +-35% of estimate; p_ge_30cm/p_gt_61cm from a normal approx
- p_any_* = 1 - prod(1 - p_i) over the parcel's crowns (independence model)
- canopy_pct = sum(crown disc areas) / parcel area * 100
- neighbour_6m: crowns on ADJACENT parcels whose centre is within 6 m of the
  parcel boundary (buffer rule matching the by-law site-plan requirement)
"""
import json, math, random

random.seed(42)

LAT0, LON0 = 43.68976356, -79.43214375  # real City Address Points coordinate for 407 Arlington Ave
M_PER_DEG_LAT = 111320.0
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(LAT0))

# Anchor so lot 3 (index 2, "407 Arlington Ave") contains the real address point.
LOT_W_M, LOT_D_M = 8.0, 30.0  # typical Davenport residential lot
X_OFFSET_M = -2 * LOT_W_M - 4.0  # shift the row so the real point falls inside lot 3
Y_OFFSET_M = -15.0  # centre the real address point mid-lot in depth

def ellipse(cx, cy, r, n=10, jitter=0.12):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r * (1 + random.uniform(-jitter, jitter))
        pts.append([cx + rr * math.cos(a), cy + rr * math.sin(a)])
    return pts

def dbh_prob(dbh_est, pi_w, threshold):
    sd = pi_w / 4.0
    if sd <= 0:
        return 1.0 if dbh_est >= threshold else 0.0
    # P(N(dbh_est, sd) >= threshold) = 0.5 * (1 - erf((threshold - mu) / (sd * sqrt(2))))
    z = (threshold - dbh_est) / (sd * math.sqrt(2))
    return round(0.5 * (1 - math.erf(z)) * 100) / 100

parcels = []
# 5 lots in a row along the street; lot 3 (index 2) is "407 Arlington Ave"
addrs = ["401 Arlington Ave", "403 Arlington Ave", "407 Arlington Ave",
         "409 Arlington Ave", "411 Arlington Ave"]
# desired crown layouts per lot: (x_frac, y_frac, diameter_m)
crown_plan = [
    [(0.30, 0.75, 7.2), (0.65, 0.80, 5.1)],                    # lot 1: two street trees
    [(0.55, 0.72, 8.9), (0.50, 0.35, 4.2)],                    # lot 2: one mature, one young
    [(0.35, 0.70, 11.5), (0.62, 0.55, 9.8), (0.45, 0.25, 3.4)], # lot 3 (407): mature + distinctive candidate + young
    [(0.70, 0.68, 6.3)],                                       # lot 4: one medium
    [],                                                        # lot 5: no crowns (e.g. cleared / corner shop)
]

for i in range(5):
    x0 = i * LOT_W_M + X_OFFSET_M
    poly_m = [[x0, Y_OFFSET_M], [x0 + LOT_W_M, Y_OFFSET_M],
              [x0 + LOT_W_M, LOT_D_M + Y_OFFSET_M], [x0, LOT_D_M + Y_OFFSET_M]]
    parcel_poly = [[
        (LON0 + px / M_PER_DEG_LON, LAT0 + py / M_PER_DEG_LAT) for px, py in poly_m
    ]]
    crowns = []
    for xf, yf, d in crown_plan[i]:
        cx_m, cy_m = x0 + xf * LOT_W_M, Y_OFFSET_M + yf * LOT_D_M
        dbh = round(d * 5.0 + random.uniform(-1.5, 1.5), 1)
        pi_lo = round(max(5.0, dbh * 0.65), 1)
        pi_hi = round(dbh * 1.35, 1)
        crowns.append({
            "polygon": [[
                round(LON0 + px / M_PER_DEG_LON, 7),
                round(LAT0 + py / M_PER_DEG_LAT, 7),
            ] for px, py in ellipse(cx_m, cy_m, d / 2.0)],
            "crown_diameter_m": round(d, 1),
            "dbh_est_cm": dbh,
            "dbh_pi95_lo": pi_lo,
            "dbh_pi95_hi": pi_hi,
            "p_ge_30cm": dbh_prob(dbh, pi_hi - pi_lo, 30),
            "p_gt_61cm": dbh_prob(dbh, pi_hi - pi_lo, 61),
            "_centre_m": [cx_m, cy_m],
        })
    parcels.append({"x0": x0, "addr": addrs[i], "crowns": crowns,
                    "poly": parcel_poly})

# neighbour_6m: crowns on other parcels within 6 m of this parcel's boundary
def dist_to_boundary(px, py, x0):
    # parcel spans [x0, x0+W] x [Y_OFFSET_M, Y_OFFSET_M+D]
    dx = max(x0 - px, 0, px - (x0 + LOT_W_M))
    dy = max(Y_OFFSET_M - py, 0, py - (LOT_D_M + Y_OFFSET_M))
    return math.hypot(dx, dy)

features = []
for i, p in enumerate(parcels):
    crowns = p["crowns"]
    area_parcel = LOT_W_M * LOT_D_M
    canopy = sum(math.pi * (c["crown_diameter_m"] / 2) ** 2 for c in crowns)
    def p_any(key):
        q = 1.0
        for c in crowns:
            q *= (1 - c[key])
        return round(1 - q, 2)
    nb = []
    for j, q in enumerate(parcels):
        if j == i:
            continue
        for c in q["crowns"]:
            if dist_to_boundary(c["_centre_m"][0], c["_centre_m"][1], p["x0"]) <= 6.0:
                nb.append(c)
    def nb_p_any(key):
        q = 1.0
        for c in nb:
            q *= (1 - c[key])
        return round(1 - q, 2)
    crowns_out = [
        {"polygon": c["polygon"], "crown_diameter_m": c["crown_diameter_m"],
         "dbh_est_cm": c["dbh_est_cm"], "dbh_pi95_lo": c["dbh_pi95_lo"],
         "dbh_pi95_hi": c["dbh_pi95_hi"], "p_ge_30cm": c["p_ge_30cm"],
         "p_gt_61cm": c["p_gt_61cm"]} for c in crowns
    ]
    props = {
        "parcel_id": f"TOP-W12-010{i + 1}",
        "address": p["addr"],
        "crowns": crowns_out,
        "crown_count": len(crowns),
        "canopy_pct": round(canopy / area_parcel * 100, 1),
        "p_any_ge_30cm": p_any("p_ge_30cm"),
        "p_any_distinctive": p_any("p_gt_61cm"),
        "neighbour_6m": {"crown_count": len(nb), "p_any_ge_30cm": nb_p_any("p_ge_30cm"),
                          "p_any_distinctive": nb_p_any("p_gt_61cm")},
        "imagery_vintage": "2022",
        "_sample": True,
    }
    features.append({"type": "Feature",
                     "geometry": {"type": "Polygon", "coordinates": p["poly"]},
                     "properties": props})

geojson = {"type": "FeatureCollection",
           "_sample": True,
           "_sample_note": "SYNTHETIC SAMPLE DATA for UI/API development. Replace with "
                           "data/parcels-ward12.geojson from the pilot pipeline.",
           "features": features}

with open("/home/hatch/workspace/toronto-tree-canopy/data/sample-parcels.geojson", "w") as f:
    json.dump(geojson, f, indent=1)
print(f"wrote {len(features)} features")
for feat in features:
    pr = feat["properties"]
    print(pr["parcel_id"], pr["address"], "crowns:", pr["crown_count"],
          "canopy:", pr["canopy_pct"], "p_any_ge_30cm:", pr["p_any_ge_30cm"],
          "nb:", pr["neighbour_6m"]["crown_count"])
