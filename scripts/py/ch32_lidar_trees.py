#| title: From points to trees (Python)
#| description: Quality check, terrain model, canopy height model, tree tops and crowns from airborne LiDAR, with laspy, SciPy and scikit-image.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 32 | The airborne LiDAR chain the author teaches in R with lidR,
written here in Python so every step is visible:

    check the points -> ground and terrain -> canopy height model
    -> tree tops (variable window) -> crowns (watershed) -> a tree table

Data: the example point clouds shipped with the lidR package (GPL-3), copied
to data/lidar/. Earth Engine does not read point clouds; this whole chapter
runs on your own machine, in seconds.

    pip install "laspy[lazrs]" numpy scipy scikit-image matplotlib pandas
"""

from pathlib import Path

import laspy
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from scipy.interpolate import griddata
from skimage.feature import peak_local_max
from skimage.segmentation import watershed

DATA = Path(__file__).resolve().parents[2] / "data" / "lidar"
CELL = 0.5                                   # canopy grid, metres


def read(name):
    las = laspy.read(DATA / name)
    return (np.asarray(las.x), np.asarray(las.y), np.asarray(las.z),
            np.asarray(las.classification), np.asarray(las.return_number))


def grid_max(x, y, z, cell):
    """Highest point in every cell: the simplest surface model ('p2r' in lidR)."""
    ix = ((x - x.min()) / cell).astype(int)
    iy = ((y.max() - y) / cell).astype(int)
    out = np.full((iy.max() + 1, ix.max() + 1), np.nan)
    order = np.argsort(z)                     # later (higher) points overwrite lower
    out[iy[order], ix[order]] = z[order]
    return out


# ---------------------------------------------------------------------------
# 1. Check the points before trusting them (Megaplot)
# ---------------------------------------------------------------------------
def qa_figure():
    x, y, z, cls, ret = read("Megaplot.laz")
    ix = ((x - x.min()) // 5).astype(int)
    iy = ((y.max() - y) // 5).astype(int)
    dens = np.zeros((iy.max() + 1, ix.max() + 1))
    np.add.at(dens, (iy, ix), 1)
    dens /= 25                                            # points per m²
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1, 1.4]})
    im = a.imshow(dens, cmap="viridis", vmin=0, vmax=np.percentile(dens, 98))
    fig.colorbar(im, ax=a, shrink=0.8, label="points per m² (5 m cells)")
    a.set_title("Point density", loc="left", fontsize=10)
    a.set_axis_off()
    strip = (y > np.median(y) - 2.5) & (y < np.median(y) + 2.5)      # a 5 m slice
    b.scatter(x[strip] - x.min(), z[strip], s=0.6, c=np.where(cls[strip] == 2, "#8c510a",
                                                             "#1b7837"))
    b.set_xlabel("Distance along the slice (m)")
    b.set_ylabel("Height above ground (m)")
    b.set_title("A 5 m cross-section: ground (brown) and vegetation", loc="left", fontsize=10)
    fig.tight_layout()
    return fig


def qa_table():
    rows = []
    for name in ["Megaplot.laz", "MixedConifer.laz", "Topography.laz"]:
        x, y, z, cls, ret = read(name)
        area = (x.max() - x.min()) * (y.max() - y.min())
        rows.append({"file": name, "points": len(x), "area_m2": area,
                     "points_per_m2": len(x) / area,
                     "ground_share": float((cls == 2).mean()),
                     "first_returns_share": float((ret == 1).mean())})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2. Ground and terrain (Topography)
# ---------------------------------------------------------------------------
def terrain_figure():
    x, y, z, cls, _ = read("Topography.laz")
    g = cls == 2
    xi = np.arange(x.min(), x.max(), 1.0)
    yi = np.arange(y.max(), y.min(), -1.0)
    gx, gy = np.meshgrid(xi, yi)
    dtm = griddata((x[g], y[g]), z[g], (gx, gy), method="linear")     # a TIN, like lidR's tin()
    dsm = grid_max(x, y, z, 1.0)[: dtm.shape[0], : dtm.shape[1]]
    dy, dx = np.gradient(np.nan_to_num(dtm, nan=np.nanmean(dtm)))
    shade = np.cos(np.arctan(np.hypot(dx, dy))) * 0.7 + 0.3 * (dx - dy) / (np.hypot(dx, dy) + 1)
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4.4))
    a.imshow(shade, cmap="gray")
    a.imshow(dtm, cmap="terrain", alpha=0.45)
    a.set_title("Terrain from ground returns only (DTM)", loc="left", fontsize=10)
    im = b.imshow(dsm - dtm, cmap="YlGn", vmin=0, vmax=25)
    fig.colorbar(im, ax=b, shrink=0.8, label="surface minus terrain (m)")
    b.set_title("What sits on the terrain: DSM − DTM", loc="left", fontsize=10)
    for ax in (a, b):
        ax.set_axis_off()
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 3. Canopy height model, tree tops and crowns (MixedConifer)
# ---------------------------------------------------------------------------
_trees = {}


def trees():
    """CHM -> variable-window local maxima -> watershed crowns -> tree table."""
    if _trees:
        return _trees
    x, y, z, cls, _ = read("MixedConifer.laz")
    chm = grid_max(x, y, z, CELL)
    # Fill empty cells and smooth lightly: a simple stand-in for lidR's pit-free CHM.
    chm = np.where(np.isnan(chm), ndi.maximum_filter(np.nan_to_num(chm), 3), chm)
    chm_s = ndi.gaussian_filter(chm, 0.6)
    # Variable window: taller trees have wider crowns, so the search window
    # grows with height. Same rule as the lidR example: ws = 0.07 * h + 2 (m).
    cand = peak_local_max(chm_s, min_distance=2, threshold_abs=2.0)
    keep = []
    for r, c in cand:
        h = chm_s[r, c]
        rad = int(np.ceil((0.07 * h + 2) / 2 / CELL))
        win = chm_s[max(r - rad, 0): r + rad + 1, max(c - rad, 0): c + rad + 1]
        if h >= win.max():
            keep.append((r, c))
    tops = np.array(keep)
    markers = np.zeros(chm.shape, int)
    markers[tops[:, 0], tops[:, 1]] = np.arange(1, len(tops) + 1)
    crowns = watershed(-chm_s, markers, mask=chm_s > 2.0)
    ids, area_px = np.unique(crowns[crowns > 0], return_counts=True)
    table = pd.DataFrame({"tree": ids,
                          "height_m": chm_s[tops[ids - 1, 0], tops[ids - 1, 1]],
                          "crown_area_m2": area_px * CELL * CELL})
    table["crown_diameter_m"] = 2 * np.sqrt(table["crown_area_m2"] / np.pi)
    _trees.update(chm=chm, chm_s=chm_s, tops=tops, crowns=crowns, table=table)
    return _trees


def trees_figure():
    t = trees()
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4.6))
    im = a.imshow(t["chm"], cmap="YlGn", vmin=0, vmax=32)
    a.plot(t["tops"][:, 1], t["tops"][:, 0], "r.", ms=3)
    fig.colorbar(im, ax=a, shrink=0.8, label="canopy height (m)")
    a.set_title(f"CHM at {CELL} m and {len(t['tops'])} tree tops", loc="left", fontsize=10)
    rng = np.random.default_rng(3)
    lut = rng.random((t["crowns"].max() + 1, 3)) * 0.8 + 0.2
    lut[0] = 1
    b.imshow(lut[t["crowns"]])
    b.plot(t["tops"][:, 1], t["tops"][:, 0], "k.", ms=2)
    b.set_title("Crowns from a watershed around each top", loc="left", fontsize=10)
    for ax in (a, b):
        ax.set_axis_off()
    fig.tight_layout()
    return fig


def plot_height_crown(df):
    """Taller trees, wider crowns: the relation allometry builds on."""
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.scatter(df["height_m"], df["crown_diameter_m"], s=10, color="#1b7837", alpha=0.7)
    b, a = np.polyfit(df["height_m"], df["crown_diameter_m"], 1)
    xs = np.linspace(df["height_m"].min(), df["height_m"].max(), 10)
    ax.plot(xs, a + b * xs, color="#c0392b", lw=1.5,
            label=f"crown ≈ {a:.1f} + {b:.2f} × height")
    ax.set_xlabel("Tree height from the CHM (m)")
    ax.set_ylabel("Crown diameter (m)")
    ax.set_title("Every segmented tree, MixedConifer plot", loc="left")
    ax.legend(frameon=False, fontsize=8)
    return fig


def tree_summary():
    df = trees()["table"]
    return pd.DataFrame([{"trees": len(df), "trees_per_ha": len(df) / 0.81,
                          "median_height_m": df["height_m"].median(),
                          "p95_height_m": df["height_m"].quantile(0.95),
                          "median_crown_diameter_m": df["crown_diameter_m"].median()}])


def products():
    return [
        {"kind": "table", "name": "ch32-qa", "data": qa_table,
         "floatfmt": ("", ",.0f", ",.0f", ".1f", ".2f", ".2f"),
         "caption": "First look at three point clouds: size, density and how many "
                    "returns are ground. Low ground share under dense canopy is normal; "
                    "zero is a problem."},
        {"kind": "figure", "name": "ch32-qa-figure", "figure": qa_figure,
         "caption": "Density shows flight-line overlap and gaps; a thin cross-section "
                    "shows whether ground and vegetation were classified sensibly."},
        {"kind": "figure", "name": "ch32-terrain", "figure": terrain_figure,
         "caption": "A terrain model from ground returns (left) and everything above it "
                    "(right). Height above this surface is what every forest metric uses."},
        {"kind": "figure", "name": "ch32-trees", "figure": trees_figure,
         "caption": "Canopy height model with variable-window tree tops, and crowns grown "
                    "from each top by a watershed. Data: lidR example MixedConifer (GPL-3)."},
        {"kind": "chart", "name": "ch32-height-crown", "data": lambda: trees()["table"],
         "plot": plot_height_crown,
         "caption": "Height against crown diameter for every segmented tree."},
        {"kind": "table", "name": "ch32-tree-summary", "data": tree_summary,
         "floatfmt": (".0f", ".0f", ".1f", ".1f", ".1f"),
         "caption": "The tree table in one line (plot area 0.81 ha). Without field "
                    "stems this is detection, not validated counting."},
    ]


if __name__ == "__main__":
    print(tree_summary())
