"""Mosaic WCS chunks -> DSM/DTM -> CHM -> PNG preview + stats."""
import os, glob
import numpy as np, rasterio
from rasterio.merge import merge
from rasterio.warp import reproject, Resampling

W = os.path.expanduser("~/workspace/toronto-tree-canopy/data/lidar/wcs")
CHK = os.path.join(W, "chunks")

def mosaic(layer):
    files = sorted(os.path.join(CHK, f"{layer}_{i}_{j}.tif") for i in (0, 1) for j in (0, 1))
    assert all(os.path.exists(f) for f in files), files
    assert len(files) == 4, f"{layer}: got {len(files)} chunks"
    srcs = [rasterio.open(f) for f in files]
    arr, transform = merge(srcs, nodata=-32767.0)
    profile = srcs[0].profile.copy()
    profile.update(transform=transform, height=arr.shape[1], width=arr.shape[2],
                   compress="deflate", predictor=2, tiled=True)
    for s in srcs: s.close()
    out = os.path.join(W, f"ward12_{layer}.tif")
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
    # clip absurd values (sensor noise): keep -2..60 m
    chm[(chm < -2) | (chm > 60)] = -9999.0
    profile = dsm_src.profile.copy()
    profile.update(dtype="float32", nodata=-9999.0, compress="deflate", predictor=2, tiled=True)
    chm_f = os.path.join(W, "ward12_chm.tif")
    with rasterio.open(chm_f, "w", **profile) as dst:
        dst.write(chm, 1)
    print("wrote", chm_f)

    v = chm[chm != -9999.0]
    print(f"CHM stats over Ward 12 sample: n={v.size}, min={v.min():.2f}, p1={np.percentile(v,1):.2f}, "
          f"median={np.median(v):.2f}, p99={np.percentile(v,99):.2f}, max={v.max():.2f}")
    print(f"fraction > 2m (probable vegetation/structures): {(v > 2).mean()*100:.2f}%")
    print(f"fraction 2-25m (probable tree canopy band): {((v > 2) & (v < 25)).mean()*100:.2f}%")
    print(f"resolution: {dsm_src.res[0]:.2e} deg (~{dsm_src.res[0]*111320:.2f} m N-S, ~{dsm_src.res[0]*80280:.2f} m E-W)")

    # vegetated spot check: sample a 200x200 window, report max CHM (trees?)
    h, w = chm.shape
    cy, cx = int(h*0.62), int(w*0.45)
    win = chm[cy-100:cy+100, cx-100:cx+100]
    wv = win[win != -9999.0]
    print(f"sample window center-px=({cy},{cx}): max CHM={wv.max():.1f}m, mean={wv.mean():.1f}m, %>2m={(wv>2).mean()*100:.1f}%")

    # PNG preview: CHM colormap 0..25m + hillshade-ish DSM backdrop
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    step = 4
    cs = chm[::step, ::step]
    ds = dsm[::step, ::step]
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    # DSM hillshade-ish grayscale
    d = np.clip(ds, 100, 180)
    axes[0].imshow(d, cmap="gray", vmin=100, vmax=180)
    axes[0].set_title("DSM (m, clipped 100-180)")
    axes[0].axis("off")
    # CHM: green ramp 0-25m
    cmap = LinearSegmentedColormap.from_list("chm", ["#f5f5f5", "#a6d96a", "#1a9850", "#006837"])
    c = np.clip(cs, 0, 25); c[cs == -9999.0] = np.nan
    im = axes[1].imshow(c, cmap=cmap, vmin=0, vmax=25)
    axes[1].set_title("CHM = DSM - DTM (m, 0-25)")
    axes[1].axis("off")
    plt.colorbar(im, ax=axes[1], shrink=0.8, label="height (m)")
    fig.suptitle("Ward 12 (Davenport) HRDEM 1m: DSM vs CHM  |  Ward 12 sample: lon -79.47..-79.44, lat 43.64..43.67 (SW 8 km2)")
    png = os.path.join(W, "ward12_chm_preview.png")
    plt.savefig(png, dpi=90, bbox_inches="tight")
    print("wrote", png)
