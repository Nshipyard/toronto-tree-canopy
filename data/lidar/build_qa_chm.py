"""Mosaic qa_cover WCS chunks -> DSM/DTM -> CHM + stats. Adapted from build_chm.py."""
import os
import numpy as np, rasterio
from rasterio.merge import merge

W = os.path.expanduser("~/workspace/toronto-tree-canopy/data/lidar/qa_cover")
CHK = os.path.join(W, "chunks")
NX, NY = 4, 2

def mosaic(layer):
    files = sorted(os.path.join(CHK, f"{layer}_{i}_{j}.tif")
                   for j in range(NY) for i in range(NX))
    assert all(os.path.exists(f) for f in files) and len(files) == NX * NY, files
    srcs = [rasterio.open(f) for f in files]
    arr, transform = merge(srcs, nodata=-32767.0)
    profile = srcs[0].profile.copy()
    profile.update(transform=transform, height=arr.shape[1], width=arr.shape[2],
                   compress="deflate", predictor=2, tiled=True)
    for s in srcs: s.close()
    out = os.path.join(W, f"qa_cover_{layer}.tif")
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(arr)
    print("wrote", out, arr.shape)
    return out

dsm_f = mosaic("dsm")
dtm_f = mosaic("dtm")

with rasterio.open(dsm_f) as dsm_src, rasterio.open(dtm_f) as dtm_src:
    dsm = dsm_src.read(1).astype("float64")
    dtm = dtm_src.read(1).astype("float64")
    assert dsm.shape == dtm.shape, (dsm.shape, dtm.shape)
    assert dsm_src.transform == dtm_src.transform, "grid mismatch"
    nodata = dsm_src.nodata
    valid = (dsm != nodata) & (dtm != nodata)
    chm = np.full(dsm.shape, -9999.0, dtype="float32")
    chm[valid] = (dsm[valid] - dtm[valid]).astype("float32")
    chm[(chm < -2) | (chm > 60)] = -9999.0
    profile = dsm_src.profile.copy()
    profile.update(dtype="float32", nodata=-9999.0, compress="deflate", predictor=2, tiled=True)
    chm_f = os.path.join(W, "qa_cover_chm.tif")
    with rasterio.open(chm_f, "w", **profile) as dst:
        dst.write(chm, 1)
    print("wrote", chm_f)

    v = chm[chm != -9999.0]
    print(f"CHM stats: n={v.size}, p1={np.percentile(v,1):.2f}, median={np.median(v):.2f}, "
          f"p99={np.percentile(v,99):.2f}, max={v.max():.2f}")
    print(f"fraction >2m: {(v > 2).mean()*100:.2f}%, 2-25m: {((v > 2) & (v < 25)).mean()*100:.2f}%")
    print(f"resolution: {dsm_src.res[0]:.2e} deg")
