#!/usr/bin/env python3
"""04_calibrate.py — crown-diameter to DBH allometry per genus group.

Pairs detected crowns (data/crowns_ward12.json) with street-tree inventory
positions (Ward 12 subset of data/street_trees.csv), then fits, per genus:

    log10(DBH_cm) = a + b * log10(crown_diameter_m)

on an 80% train split and reports R^2 on the held-out 20% per group.
Prediction intervals assume lognormal DBH (normal residuals in log10 space,
homoscedastic); p_ge_30cm / p_gt_61cm come from that normal CDF.

Outputs: data/allometry.json  (params per group + generic fallback)
         data/accuracy_calibration.json
"""
import csv, json, math, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

PAIR_RADIUS_M = 5.0
MIN_GROUP_N = 100
SEED = 42

def to3857(lon, lat):
    x = lon * 20037508.34 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) * 20037508.34 / math.pi
    return x, y

def genus_of(botanical):
    b = (botanical or "").strip()
    if not b or b.lower() in ("none", "unknown", "null"):
        return None
    g = b.split()[0]
    # hybrids like "Acer x freemanii" -> Acer
    return g if g[0].isupper() else None

def ols(x, y):
    n = len(x)
    mx = sum(x)/n; my = sum(y)/n
    sxx = sum((v-mx)**2 for v in x)
    sxy = sum((xi-mx)*(yi-my) for xi, yi in zip(x, y))
    b = sxy/sxx if sxx > 0 else 0.0
    a = my - b*mx
    resid = [yi - (a + b*xi) for xi, yi in zip(x, y)]
    s = math.sqrt(sum(r*r for r in resid)/max(n-2, 1))
    return a, b, s

def r2_score(y_true, y_pred):
    m = sum(y_true)/len(y_true)
    ss_tot = sum((v-m)**2 for v in y_true)
    ss_res = sum((t-p)**2 for t, p in zip(y_true, y_pred))
    return 1 - ss_res/ss_tot if ss_tot > 0 else 0.0

def main():
    crowns = json.load(open(os.path.join(DATA, "crowns_ward12.json")))["crowns"]
    print(f"loaded {len(crowns)} crowns")
    # spatial hash on crown centers
    CELL = 10.0
    grid = {}
    for c in crowns:
        key = (int(c["cx_3857"]//CELL), int(c["cy_3857"]//CELL))
        grid.setdefault(key, []).append(c)

    def nearby(x, y, r):
        out = []
        c0x, c0y = int(x//CELL), int(y//CELL)
        cr = int(r//CELL) + 1
        for ix in range(c0x-cr, c0x+cr+1):
            for iy in range(c0y-cr, c0y+cr+1):
                for c in grid.get((ix, iy), []):
                    d = math.hypot(c["cx_3857"]-x, c["cy_3857"]-y)
                    if d <= r:
                        out.append((d, c))
        return sorted(out, key=lambda t: t[0])

    pairs = []  # (genus, crown_d_m, dbh_cm)
    n_trees = n_nopair = n_ambiguous = 0
    with open(os.path.join(DATA, "street_trees.csv")) as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            if row.get("WARD") != "12":
                continue
            try:
                dbh = float(row["DBH_TRUNK"])
            except (TypeError, ValueError):
                continue
            if not (1.0 <= dbh <= 300.0):
                continue
            try:
                g = json.loads(row["geometry"].replace('""', '"'))
                lon, lat = g["coordinates"]
            except Exception:
                continue
            x, y = to3857(lon, lat)
            n_trees += 1
            near = nearby(x, y, PAIR_RADIUS_M)
            if not near:
                n_nopair += 1
                continue
            if len(near) > 1 and near[1][0] <= PAIR_RADIUS_M:
                # ambiguous: two crowns within radius; skip unless nearest is much closer
                if near[1][0] - near[0][0] < 2.0:
                    n_ambiguous += 1
                    continue
            c = near[0][1]
            cd = c["crown_diameter_m"]
            if not (1.0 <= cd <= 40.0):
                continue
            genus = genus_of(row.get("BOTANICAL_NAME"))
            pairs.append((genus or "UNKNOWN", cd, dbh))
    print(f"street trees ward12 with valid DBH: {n_trees}; no crown within {PAIR_RADIUS_M}m: {n_nopair}; ambiguous: {n_ambiguous}; paired: {len(pairs)}")

    rng = random.Random(SEED)
    groups = {}
    for genus, cd, dbh in pairs:
        groups.setdefault(genus, []).append((cd, dbh))
    # fold small genera into generic pool but keep them fitted separately if >= MIN_GROUP_N
    all_pairs = [(cd, dbh) for _, cd, dbh in pairs]

    results, fitted = [], {}
    def fit_group(name, data):
        data = data[:]
        rng.shuffle(data)
        n = len(data)
        n_train = int(0.8*n)
        train, hold = data[:n_train], data[n_train:]
        lx = [math.log10(cd) for cd, _ in train]
        ly = [math.log10(dbh) for _, dbh in train]
        a, b, s = ols(lx, ly)
        hx = [math.log10(cd) for cd, _ in hold]
        hy = [math.log10(dbh) for _, dbh in hold]
        pred = [a + bb*h for h, bb in zip(hx, [b]*len(hx))]
        r2 = r2_score(hy, pred)
        fitted[name] = {"a": a, "b": b, "sigma_log10": s, "n_train": len(train)}
        results.append({"group": name, "n": n, "n_train": len(train),
                        "n_holdout": len(hold), "r2_holdout": round(r2, 4),
                        "a": round(a, 4), "b": round(b, 4),
                        "sigma_log10": round(s, 4)})
        return r2

    for genus in sorted(groups):
        if genus == "UNKNOWN":
            continue
        if len(groups[genus]) >= MIN_GROUP_N:
            fit_group(genus, groups[genus])
    fit_group("GENERIC", all_pairs)  # fallback incl. UNKNOWN + small genera

    results.sort(key=lambda r: -r["n"])
    for r in results:
        print(f"  {r['group']:12s} n={r['n']:6d} holdout={r['n_holdout']:5d} R2={r['r2_holdout']:.4f} "
              f"a={r['a']:.3f} b={r['b']:.3f} sigma={r['sigma_log10']:.3f}")

    json.dump({"groups": fitted,
               "pair_radius_m": PAIR_RADIUS_M,
               "model": "log10(DBH_cm) = a + b*log10(crown_diameter_m); DBH lognormal | crown",
               "distributional_assumption": ("residuals normal in log10 space, homoscedastic; "
                 "p_ge_30cm = 1-Phi((log10(30)-mu)/sigma); 95% PI = mu +/- 1.96*sigma back-transformed"),
               "fit_on": "urban street trees, Ward 12 Toronto, paired to detected crowns (2022 leaf-off ortho)",
               "n_paired": len(pairs)},
              open(os.path.join(DATA, "allometry.json"), "w"), indent=1)
    json.dump({"imagery_vintage": "2022",
               "calibration": results,
               "n_paired": len(pairs),
               "n_ward12_street_trees": n_trees,
               "note": "fitted on URBAN street trees only; never forest-derived allometry"},
              open(os.path.join(DATA, "accuracy_calibration.json"), "w"), indent=1)
    print("wrote data/allometry.json + data/accuracy_calibration.json")

if __name__ == "__main__":
    main()
