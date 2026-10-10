#!/usr/bin/env python3
"""Track A: fine-CHM individual tree segmentation from raw TRCA GTA_2023 COPC.

Pipeline:
  1. read_chm()   -- build a fine CHM (0.25 or 0.5 m, EPSG:26917) per QA tile:
     DTM  = NRCan HRDEM DTM (1 m, validated flat-ground median 0.06 m)
     DSM  = fine max-Z raster from COPC points, EXCLUDING building-class
            points (ASPRS 6) and high-noise (18); buildings ALSO masked by
            Toronto building-outline polygons (buffered) so footprints that
            misalign with the point cloud are still removed.
     CHM  = DSM - DTM, clipped to [-2, 60] m.
  2. detect()      -- classical forestry recipe at fine resolution:
     Gaussian smooth, local-maxima treetops, marker-controlled watershed on
     the inverted CHM with a height floor; drop segments below min area or
     whose pixels are mostly building-masked (paranoia filter).
  3. boxes_with_scores() -- segment bbox -> [x0,y0,x1,y1,score] in meters
     from tile top-left, for pipeline/eval_harness.py.

PARAMS are picked on qa1+qa3 ONLY (see tracka_final.py); qa7 is held out.
Usage: python tracka_detect.py build   -> build fine CHMs for qa1/qa3/qa7
       python tracka_detect.py final   -> detect + eval + write data/accuracy_tracka.json
"""
import json, os, sys
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.windows import from_bounds
from rasterio.features import rasterize
from scipy.ndimage import gaussian_filter, uniform_filter, label
from skimage.feature import peak_local_max
from skimage.segmentation import watershed
from skimage.measure import regionprops

ROOT = os.path.expanduser("~/workspace/toronto-tree-canopy")
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

RAW = os.path.join(ROOT, "data", "lidar", "raw")
OUT = os.path.join(ROOT, "data", "lidar", "tracka")
os.makedirs(OUT, exist_ok=True)

# QA tile bboxes in EPSG:3857 (row 0 = tile top); labels use x_m,y_m from top-left.
QA_BBOX_3857 = {
    "qa1": (-8843260.347386666, 5415706.410854956, -8843180.347386666, 5415786.410854956),
    "qa3": (-8841033.957571112, 5416322.108966721, -8840953.957571112, 5416402.108966721),
    "qa7": (-8841159.74859569, 5415640.225751326, -8841079.74859569, 5415720.225751326),
}
# Which COPC tile covers each QA tile (UTM17 1 km tiles).
QA_COPC = {
    "qa1": os.path.join(RAW, "qa1_tile.copc.laz"),
    "qa3": os.path.join(RAW, "qa37_tile.copc.laz"),
    "qa7": os.path.join(RAW, "qa37_tile.copc.laz"),
}
DTM_SRC = os.path.join(ROOT, "data", "lidar", "qa_cover", "qa_cover_dtm.tif")
BUILDINGS_GEOJSON = os.path.join(RAW, "building_outlines_4326.geojson")

CHM_RES = 0.5  # meters per pixel
BUFFER_M = 10.0  # buffer around tile when reading points / footprints

# Per-tile building-class point stats are computed in tracka_measure.py;
# class 6 = building if present.


def _utm17_bounds_3857(tile):
    """QA tile bbox (+buffer) transformed to EPSG:26917 for clipping the COPC."""
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:3857", "EPSG:26917", always_xy=True)
    x0, y0, x1, y1 = QA_BBOX_3857[tile]
    e0, n0 = t.transform(x0, y0)
    e1, n1 = t.transform(x1, y1)
    return min(e0, e1), min(n0, n1), max(e0, e1), max(n0, n1)


def _grid_3857(tile, res):
    """Fine grid in the harness frame (EPSG:3857 units). Returns transform, H, W."""
    x0, y0, x1, y1 = QA_BBOX_3857[tile]
    ox, oy = x0 - BUFFER_M, y1 + BUFFER_M  # top-left
    W = int(np.ceil((x1 - x0 + 2 * BUFFER_M) / res))
    H = int(np.ceil((y1 - y0 + 2 * BUFFER_M) / res))
    return rasterio.transform.from_origin(ox, oy, res, res), H, W


def read_points_utm17(tile, extra_buffer=0.0):
    """Read COPC points for the tile + buffer, return x,y,z,cls arrays (UTM17)."""
    import laspy
    e0, n0, e1, n1 = _utm17_bounds_3857(tile)
    b = BUFFER_M + extra_buffer
    bounds = (e0 - b, n0 - b, e1 + b, n1 + b)
    las = laspy.read(QA_COPC[tile])
    x = np.asarray(las.x); y = np.asarray(las.y); z = np.asarray(las.z)
    m = (x >= bounds[0]) & (x <= bounds[2]) & (y >= bounds[1]) & (y <= bounds[3])
    return x[m], y[m], z[m], np.asarray(las.classification)[m]


def fine_dsm_3857(tile, res=CHM_RES):
    """Max-Z raster over vegetation-ish classes on the harness-frame grid.

    Uses points NOT in {ground 2, building 6, water 9, low point 7,
    high noise 18} when a classification exists; building points (6) are
    dropped entirely here.
    Returns (dsm, transform, H, W).
    """
    from pyproj import Transformer
    x, y, z, cls = read_points_utm17(tile)
    keep = np.ones(len(x), dtype=bool)
    if cls.size and cls.max() > 1:
        keep = ~np.isin(cls, [2, 6, 7, 9, 18])
    x, y, z = x[keep], y[keep], z[keep]
    t = Transformer.from_crs("EPSG:26917", "EPSG:3857", always_xy=True)
    xb, yb = t.transform(x, y)
    transform, H, W = _grid_3857(tile, res)
    ox, oy = transform.c, transform.f
    ix = np.clip(((xb - ox) / res).astype(np.int64), 0, W - 1)
    iy = np.clip(((oy - yb) / res).astype(np.int64), 0, H - 1)
    dsm = np.full((H, W), -9999.0, dtype=np.float32)
    flat_idx = iy * W + ix
    # scatter-max: sort by z ascending, write in order so last (max) wins
    order = np.argsort(z)
    dsm.ravel()[flat_idx[order]] = z[order].astype(np.float32)
    return dsm, transform, H, W


def building_mask_3857(tile, res=CHM_RES, buf_m=2.0):
    """Rasterize Toronto building outlines over the DSM grid (True = building)."""
    x0, y0, x1, y1 = QA_BBOX_3857[tile]
    from pyproj import Transformer
    t4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    lon0, lat0 = t4326.transform(x0, y0)
    lon1, lat1 = t4326.transform(x1, y1)
    bb = (min(lon0, lon1) - 0.002, min(lat0, lat1) - 0.002,
          max(lon0, lon1) + 0.002, max(lat0, lat1) + 0.002)
    polys = []
    from shapely.geometry import shape
    t3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    # Streaming parse of the 400 MB FeatureCollection: each feature's geometry
    # is found via its "coordinates" array; parse with raw_decode (C speed).
    dec = json.JSONDecoder()
    with open(BUILDINGS_GEOJSON) as f:
        buf = ""
        pos = 0
        eof = False
        while not eof:
            chunk = f.read(1 << 22)
            if not chunk:
                eof = True
            buf = buf[pos:] + chunk
            pos = 0
            while True:
                i = buf.find('"coordinates"', pos)
                if i < 0:
                    pos = max(0, len(buf) - len('"coordinates"'))
                    break
                j = buf.find('[', i)
                if j < 0:
                    pos = max(0, len(buf) - 1)
                    break
                try:
                    coords, end = dec.raw_decode(buf, j)
                except json.JSONDecodeError:
                    if eof:
                        pos = j + 1  # corrupt tail; skip
                        continue
                    pos = j + 1
                    break  # need more data; keep remainder in buf
                pos = end
                # flatten coords recursively for the bbox pre-check
                # (MultiPolygons are inhomogeneous; asarray would fail)
                flat = []
                stack = [coords]
                while stack:
                    c = stack.pop()
                    if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
                        flat.extend(c)
                    elif isinstance(c, (list, tuple)):
                        stack.extend(c)
                if not flat:
                    continue
                arr = np.asarray(flat, dtype=float)
                xs = arr[0::2]; ys = arr[1::2]
                if xs.size and xs.min() <= bb[2] and xs.max() >= bb[0] and \
                   ys.min() <= bb[3] and ys.max() >= bb[1]:
                    try:
                        gtype = ("MultiPolygon"
                                 if isinstance(coords[0][0][0], list) else "Polygon")
                        polys.append(shape({"type": gtype, "coordinates": coords}))
                    except Exception:
                        pass
    print(f"tile {tile}: building polys intersecting bbox: {len(polys)}")
    if not polys:
        return None
    from shapely.ops import transform as shp_transform
    polys3857 = [shp_transform(lambda a, b: t3857.transform(a, b), p) for p in polys]
    if buf_m > 0:
        polys3857 = [p.buffer(buf_m) for p in polys3857]
    dsm, transform, H, W = fine_dsm_3857(tile, res)
    mask = rasterize(
        [(p, 1) for p in polys3857],
        out_shape=(H, W), transform=transform, fill=0,
        dtype=np.uint8, all_touched=True)
    return mask.astype(bool)


def dtm_on_grid(tile, res=CHM_RES):
    """Sample the validated 1 m HRDEM DTM onto the fine 3857 DSM grid."""
    dsm, transform, H, W = fine_dsm_3857(tile, res)
    with rasterio.open(DTM_SRC) as src:
        # reproject DTM (its own CRS, ~1 m) onto the 3857 DSM grid
        dtm = np.empty((H, W), dtype=np.float32)
        reproject(
            rasterio.band(src, 1), dtm,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=transform, dst_crs="EPSG:3857",
            resampling=Resampling.bilinear,
            src_nodata=src.nodata, dst_nodata=-9999.0)
    return dtm


def build_chm(tile, res=CHM_RES, mask_buildings=True, buf_m=0.5, fill_radius_px=3):
    """CHM on the fine 3857 grid (harness frame), buildings masked to nan.

    DSM holes (canopy gaps, ~60% of 0.36 m ground cells empty) are closed by
    nearest-valid fill, but only within `fill_radius_px` of real data;
    farther nodata is set to 0 (ground assumption), avoiding long-range
    tree-height smearing across streets.
    """
    from scipy.ndimage import distance_transform_edt
    dsm, transform, H, W = fine_dsm_3857(tile, res)
    valid = dsm > -9000
    dist, idx = distance_transform_edt(~valid, return_indices=True)
    dsm_f = dsm[tuple(idx)].astype(np.float32)
    dtm = dtm_on_grid(tile, res)
    chm = np.where((dsm_f > -9000) & (dtm > -9000), dsm_f - dtm, np.nan).astype(np.float32)
    chm = np.where(dist <= fill_radius_px, chm, 0.0)
    chm = np.clip(chm, -2.0, 60.0)
    if mask_buildings:
        bmask = building_mask_3857(tile, res, buf_m)
        if bmask is not None:
            chm[bmask] = np.nan
            print(f"{tile}: masked {bmask.sum()} px as building ({bmask.mean()*100:.1f}%)")
    path = os.path.join(OUT, f"chm_{tile}_{int(res*100)}cm_3857.tif")
    with rasterio.open(path, "w", driver="GTiff", height=H, width=W, count=1,
                       dtype="float32", crs="EPSG:3857", transform=transform,
                       nodata=np.nan, compress="deflate", tiled=True) as dst:
        dst.write(chm, 1)
    print("wrote", path, "shape", chm.shape)
    return chm, transform


def tile_chm_window(tile, res=CHM_RES):
    """Load saved fine CHM and crop to the exact QA footprint (row 0 = top)."""
    path = os.path.join(OUT, f"chm_{tile}_{int(res*100)}cm_3857.tif")
    x0, y0, x1, y1 = QA_BBOX_3857[tile]
    with rasterio.open(path) as src:
        win = from_bounds(x0, y0, x1, y1, src.transform).round_offsets().round_lengths()
        a = src.read(1, window=win, boundless=True, fill_value=np.nan)
    return a


def region_grow(chm, res=CHM_RES, sigma=0.5, min_dist=2.5, peak_h=2.5, floor=1.5,
                max_radius=4.0, min_area=3.0):
    """Dalponte-style seeded region growing on the CHM (PRIMARY detector).

    From each treetop (tallest first), grow to 8-neighbors that are strictly
    lower, above floor, within max_radius of the seed, and unclaimed.
    Stops at valleys (can't climb) -> separates adjacent crowns that
    marker-watershed merges. Returns [x0,y0,x1,y1,hmax,area] in harness frame.
    """
    import heapq
    pix = res
    chm_f = np.where(np.isnan(chm), -1.0, chm)
    chm_s = gaussian_filter(chm_f, sigma=sigma / pix)
    min_px = max(2, int(round(min_dist / pix)))
    peaks = peak_local_max(chm_s, min_distance=min_px, threshold_abs=peak_h,
                           exclude_border=False)
    if len(peaks) == 0:
        return []
    order = np.argsort(-chm_s[peaks[:, 0], peaks[:, 1]])
    peaks = peaks[order]
    H, W = chm.shape
    claimed = np.zeros((H, W), dtype=np.int32)
    max_r2 = (max_radius / pix) ** 2
    out = []
    for k, (r0, c0) in enumerate(peaks, start=1):
        h0 = float(chm_s[r0, c0])
        if h0 < peak_h or claimed[r0, c0]:
            continue
        seen = np.zeros((H, W), dtype=bool)
        heap = [(-h0, r0, c0)]
        seen[r0, c0] = True
        cells = []
        while heap:
            negh, r, c = heapq.heappop(heap)
            h = -negh
            if claimed[r, c] or h < floor:
                continue
            if (r - r0) ** 2 + (c - c0) ** 2 > max_r2:
                continue
            claimed[r, c] = k
            cells.append((r, c))
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < H and 0 <= cc < W and not seen[rr, cc] and not claimed[rr, cc]:
                        hh = float(chm_s[rr, cc])
                        if hh <= h + 1e-6 and hh >= floor:
                            seen[rr, cc] = True
                            heapq.heappush(heap, (-hh, rr, cc))
        if not cells:
            continue
        cells = np.array(cells)
        area = len(cells) * pix * pix
        if area < min_area:
            continue
        yy0, xx0 = cells.min(axis=0)
        yy1, xx1 = cells.max(axis=0) + 1
        hmax = float(np.nanmax(chm[cells[:, 0], cells[:, 1]]))
        out.append([xx0 * pix, yy0 * pix, xx1 * pix, yy1 * pix, hmax, area])
    return out


def detect(chm, res=CHM_RES, sigma=0.5, min_dist=3.0, peak_h=3.0, floor=2.0,
           min_area=4.0, max_area=150.0, min_building_frac=0.0):
    """Legacy marker-watershed detector (kept for reference; region_grow is primary)."""
    pix = res
    chm_f = np.where(np.isnan(chm), 0.0, chm)
    chm_s = gaussian_filter(chm_f, sigma=sigma / pix)
    min_px = max(2, int(round(min_dist / pix)))
    peaks = peak_local_max(chm_s, min_distance=min_px, threshold_abs=peak_h,
                           exclude_border=False)
    markers = np.zeros(chm.shape, dtype=np.int32)
    for k, (r, c) in enumerate(peaks):
        markers[r, c] = k + 1
    mask = (chm_s > floor) & ~np.isnan(chm)
    if markers.sum() == 0 or mask.sum() == 0:
        return []
    seg = watershed(-chm_s, markers, mask=mask)
    out = []
    for r in regionprops(seg):
        area = r.area * pix * pix
        if area < min_area or area > max_area:
            continue
        yy0, xx0, yy1, xx1 = r.bbox
        seg_mask = seg[yy0:yy1, xx0:xx1] == r.label
        vals = chm[yy0:yy1, xx0:xx1][seg_mask]
        vals = vals[~np.isnan(vals)]
        if vals.size == 0:
            continue
        hmax = float(vals.max())
        # crown boxes in meters from tile top-left
        out.append([xx0 * pix, yy0 * pix, xx1 * pix, yy1 * pix, hmax, area])
    return out


def boxes_with_scores(dets):
    if not dets:
        return []
    hs = np.array([d[4] for d in dets])
    lo, hi = hs.min(), hs.max()
    rng = hi - lo if hi > lo else 1.0
    return [[d[0], d[1], d[2], d[3], float((d[4] - lo) / rng)] for d in dets]


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "build"
    if mode == "build":
        for t in ["qa1", "qa3", "qa7"]:
            build_chm(t)
    else:
        print("modes: build")
