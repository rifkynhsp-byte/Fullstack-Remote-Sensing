#| title: Counting oil palms without deep learning (Python)
#| description: Excess-green index, a Gaussian blur and local maxima on a drone orthophoto of smallholder oil palm in South Kalimantan.

"""
CHAPTER 27 | One point per crown, from a drone orthophoto.

The author's GEE method (sawitML, GEE101 PalmOil_Detection): blur a
vegetation index, find the crown centres, count them. No neural network:
mature oil palm is planted on a regular grid and each crown is a bright,
round, well separated blob, which is exactly what a local-maximum filter
finds.

Image: OpenAerialMap, "53672_33413kebun_sawit_bangkal_baru", 3.7 cm drone
orthophoto near Banjarbaru, South Kalimantan, CC BY 4.0. Read straight from
the cloud-optimised GeoTIFF at 0.3 m, the resolution the original method used.

    pip install rasterio scikit-image scipy matplotlib pandas
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.feature import peak_local_max

# OpenAerialMap orthophoto (CC BY 4.0), originally at oin-hotosm-temp.s3.us-east-1.amazonaws.com/
# 6a13018bb96dbc8d970d888e/0/6a13018bb96dbc8d970d888f.tif. That bucket is temporary, so the book
# keeps an identical copy with its data snapshots; it is read in place, by HTTP range requests.
URL = "https://github.com/rifkynhsp-byte/Fullstack-Remote-Sensing/releases/download/data-v1/ch27_ch61_drone_orthophoto.tif"
OVERVIEW = 8          # 3.7 cm x 8 = 0.30 m
MIN_SPACING_M = 5.5   # two crowns closer than this are one palm
SIGMA_M = 0.9         # blur about a third of a crown radius

_cache = {}


def load():
    """RGB at 0.3 m, straight from the cloud; no download of the full 1 GB."""
    if "rgb" not in _cache:
        with rasterio.open("/vsicurl/" + URL) as src:
            h, w = src.height // OVERVIEW, src.width // OVERVIEW
            rgb = src.read(out_shape=(3, h, w), resampling=Resampling.average).astype(float)
            res = src.res[0] * OVERVIEW
        _cache.update(rgb=rgb, res=res)
    return _cache["rgb"], _cache["res"]


def count_palms():
    """Excess green, blur, local maxima: one point per crown."""
    if "peaks" in _cache:
        return _cache["peaks"]
    rgb, res = load()
    r, g, b = rgb
    exg = (2 * g - r - b) / np.maximum(r + g + b, 1)          # excess green index
    smooth = ndi.gaussian_filter(exg, SIGMA_M / res)
    valid = (rgb.sum(0) > 0).astype(int)                      # skip the no-data frame
    peaks = peak_local_max(smooth, min_distance=int(MIN_SPACING_M / res),
                           threshold_abs=0.04, labels=valid)
    _cache["peaks"] = peaks
    return peaks


def spacing_frame():
    """Distance from every counted palm to its nearest neighbour, in metres."""
    peaks = count_palms()
    _, res = load()
    d, _ = cKDTree(peaks * res).query(peaks * res, k=2)
    return pd.DataFrame({"nearest_m": d[:, 1]})


def density_frame():
    """Palms per hectare in a 50 m grid, which is what an estate manager asks for."""
    rgb, res = load()
    peaks = count_palms()
    cell = int(50 / res)
    rows, cols = rgb.shape[1] // cell, rgb.shape[2] // cell
    grid = np.zeros((rows, cols))
    for y, x in peaks:
        if y // cell < rows and x // cell < cols:
            grid[y // cell, x // cell] += 1
    return grid * 4          # 50 m cell = 0.25 ha


def figure_crowns():
    """The orthophoto with every counted crown, and a zoom on one corner."""
    rgb, res = load()
    peaks = count_palms()
    img = np.clip(np.moveaxis(rgb, 0, -1) / 255, 0, 1)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.6), gridspec_kw={"width_ratios": [1.2, 1]})
    axes[0].imshow(img)
    axes[0].plot(peaks[:, 1], peaks[:, 0], ".", color="#ff2d55", ms=1.6)
    axes[0].set_title(f"{len(peaks):,} crowns counted", loc="left", fontsize=10)
    zy, zx, zs = int(0.55 * img.shape[0]), int(0.05 * img.shape[1]), int(120 / res)
    axes[0].add_patch(plt.Rectangle((zx, zy), zs, zs, fill=False, ec="yellow", lw=1.5))
    axes[1].imshow(img[zy:zy + zs, zx:zx + zs])
    sel = ((peaks[:, 0] >= zy) & (peaks[:, 0] < zy + zs) &
           (peaks[:, 1] >= zx) & (peaks[:, 1] < zx + zs))
    axes[1].plot(peaks[sel, 1] - zx, peaks[sel, 0] - zy, "o", mfc="none", mec="#ff2d55",
                 ms=9, mew=1.2)
    axes[1].set_title("Zoom, 120 m across", loc="left", fontsize=10)
    for ax in axes:
        ax.set_axis_off()
    fig.text(0.01, 0.01, "Imagery: OpenAerialMap contributors, CC BY 4.0", fontsize=7,
             color="#616e7c")
    fig.tight_layout()
    return fig


def figure_density():
    """Palms per hectare, 50 m cells."""
    grid = density_frame()
    fig, ax = plt.subplots(figsize=(6, 5.2))
    im = ax.imshow(np.ma.masked_equal(grid, 0), cmap="YlGn", vmin=0, vmax=180)
    fig.colorbar(im, ax=ax, label="Palms per hectare (50 m cells)", shrink=0.8)
    ax.set_title("Planting density", loc="left", fontsize=10)
    ax.set_axis_off()
    return fig


def plot_spacing(df):
    """Nearest-neighbour distance. A planted grid shows one sharp peak."""
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    ax.hist(df["nearest_m"].clip(0, 16), bins=np.arange(4, 16.5, 0.5), color="#1b7837")
    ax.axvline(9, color="#b2182b", ls="--", lw=1)
    ax.text(9.1, ax.get_ylim()[1] * 0.9, "9 m, a common planting distance", fontsize=7,
            color="#b2182b")
    ax.set_xlabel("Distance to the nearest counted palm (m)")
    ax.set_ylabel("Palms")
    ax.set_title("Does the count look like a plantation?", loc="left")
    return fig


def summary_frame():
    peaks = count_palms()
    rgb, res = load()
    sp = spacing_frame()["nearest_m"]
    grid = density_frame()
    area_ha = (rgb.sum(0) > 0).sum() * res * res / 1e4
    return pd.DataFrame([{
        "palms_counted": len(peaks), "image_area_ha": area_ha,
        "median_spacing_m": sp.median(),
        "share_spacing_7_to_11_m": ((sp >= 7) & (sp <= 11)).mean(),
        "median_density_per_ha_in_planted_cells": np.median(grid[grid > 60]),
    }])


def products():
    return [
        {"kind": "figure", "name": "ch27-palm-crowns", "figure": figure_crowns,
         "caption": "Every red dot is a crown centre found by the local-maximum filter. "
                    "Inside planted blocks it is one dot per palm; outside them, dots "
                    "fall on ordinary trees, so count inside a plantation boundary."},
        {"kind": "figure", "name": "ch27-palm-density", "figure": figure_density,
         "caption": "Counts turned into palms per hectare on a 50 m grid: the gaps, "
                    "young blocks and edges an estate manager needs to see."},
        {"kind": "chart", "name": "ch27-palm-spacing", "data": spacing_frame,
         "plot": plot_spacing,
         "caption": "Nearest-neighbour distance between counted palms. A clean peak "
                    "near the planting distance is a quick sanity check on the count; "
                    "a long tail below 6 m means double counts."},
        {"kind": "table", "name": "ch27-palm-summary", "data": summary_frame,
         "floatfmt": (".0f", ".1f", ".1f", ".2f", ".0f"),
         "caption": "The count in numbers. Without field counts this is not an "
                    "accuracy; the spacing check is the evidence available."},
    ]


if __name__ == "__main__":
    print(summary_frame())
