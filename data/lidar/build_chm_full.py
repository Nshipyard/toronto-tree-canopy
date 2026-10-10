"""Mosaic the full-ward WCS chunks -> DSM/DTM -> CHM, masked to Ward 12.

Reads data/lidar/wcs/chunks/{dsm,dtm}_{I}_{J}.tif and {dsm,dtm}_W_{J}.tif,
mosaics each layer, computes CHM = DSM - DTM (nodata -9999, clipped to
[-2, 60] m), and masks pixels outside the Ward 12 polygon to nodata.

Outputs (gitignored, reproducible via fetch_ward12_full.py + this script):
  data/lidar/wcs/ward12_dsm_full.tif
  data/lidar/wcs/ward12_dtm_full.tif
  data/lidar/wcs/ward12_chm_full.tif   <- the Track B pilot CHM (1 m, EPSG:4326)

Run: .venv/bin/python3 data/lidar/build_chm_full.py
"""
import glob
import json
import os

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.merge import merge

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, "wcs")
CHK = os.path.join(W, "chunks")
WARD = os.path.join(HERE, "..", "ward12.geojson")


def mosaic(layer):
    files = sorted(glob.glob(os.path.join(CHK, f"{layer}_*.tif")))
    assert files, f"no chunks for {layer}"
    print(f"{layer}: mosaicking {len(files)} chunks", flush=True)
    srcs = [rasterio.open(f) for f in files]
    arr, transform = merge(srcs, nodata=-32767.0)
    profile = srcs[0].profile.copy()
    profile.update(transform=transform, height=arr.shape[1], width=arr.shape[2],
                   compress="deflate", predictor=2, tiled=True)
    for s in srcs:
        s.close()
    out = os.path.join(W, f"ward12_{layer}_full.tif")
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(arr)
    print("wrote", out, arr.shape, flush=True)
    return out


def main():
    dsm_f = mosaic("dsm")
    dtm_f = mosaic("dtm")

    with rasterio.open(dsm_f) as dsm_src, rasterio.open(dtm_f) as dtm_src:
        dsm = dsm_src.read(1).astype("float64")
        dtm = dtm_src.read(1).astype("float64")
        assert dsm.shape == dtm.shape, (dsm.shape, dtm.shape)
        nodata = dsm_src.nodata
        valid = (dsm != nodata) & (dtm != nodata)
        chm = np.full(dsm.shape, -9999.0, dtype="float32")
        chm[valid] = (dsm[valid] - dtm[valid]).astype("float32")
        chm[(chm < -2) | (chm > 60)] = -9999.0

        # mask to the ward polygon (parcels never need pixels outside it)
        ward = json.load(open(WARD))
        geom = ward["features"][0]["geometry"]
        inside = geometry_mask([geom], out_shape=chm.shape,
                               transform=dsm_src.transform, invert=True)
        chm[~inside] = -9999.0

        profile = dsm_src.profile.copy()
        profile.update(dtype="float32", nodata=-9999.0, compress="deflate",
                       predictor=2, tiled=True)
        chm_f = os.path.join(W, "ward12_chm_full.tif")
        with rasterio.open(chm_f, "w", **profile) as dst:
            dst.write(chm, 1)
        print("wrote", chm_f, flush=True)

        v = chm[chm != -9999.0]
        print(f"CHM full ward: n={v.size}, px={dsm_src.res[0]:.2e} deg "
              f"(~{dsm_src.res[0]*111320:.2f} m N-S, ~{dsm_src.res[0]*80280:.2f} m E-W)")
        print(f"  min={v.min():.2f} p1={np.percentile(v,1):.2f} "
              f"median={np.median(v):.2f} p99={np.percentile(v,99):.2f} max={v.max():.2f}")
        print(f"  frac>6m={(v>6).mean()*100:.2f}%  frac>=8m={(v>=8).mean()*100:.2f}% "
              f"frac 8-25m={((v>=8)&(v<25)).mean()*100:.2f}%")


if __name__ == "__main__":
    main()
