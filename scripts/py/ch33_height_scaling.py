#| title: One plot, one footprint, one map (Python)
#| description: What "canopy height" means at 0.5 m, 10 m and 25 m, how two satellite height maps compare with GEDI footprints over a Sumatran lowland, and what a height error does to biomass.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 33 | Scaling up from a LiDAR plot.

    1. Scale: the chapter “Airborne LiDAR: From Points to Trees” canopy height model, summarised the way a 10 m
       map and a 25 m GEDI footprint summarise it.
    2. Agreement: GEDI rh98 footprints against two satellite height maps,
       ETH 10 m (Lang et al. 2023) and GLAD 30 m (Potapov et al. 2021).
    3. Biomass: why a height bias becomes a biomass bias of the same size.

    pip install earthengine-api "laspy[lazrs]" numpy scipy scikit-image pandas matplotlib
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ch32_lidar_trees import CELL, trees     # the 0.5 m CHM from chapter “Airborne LiDAR: From Points to Trees”

aoi = ee.Geometry.Rectangle([102.45, -2.15, 102.90, -1.75], None, False)  # Jambi lowland

eth = ee.Image("users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1").rename("eth")
glad = ee.ImageCollection("users/potapovpeter/GEDI_V27").mosaic().rename("glad")


def good_shots(img):
    """Keep GEDI shots that are trustworthy over dense tropical canopy."""
    ok = (img.select("quality_flag").eq(1)
          .And(img.select("degrade_flag").eq(0))
          .And(img.select("sensitivity").gt(0.95)))
    return img.select("rh98").updateMask(ok)


# Shots from 2019-04 to 2020-12, close in time to both maps.
gedi = (ee.ImageCollection("LARSE/GEDI/GEDI02_A_002_MONTHLY")
        .filterBounds(aoi).filterDate("2019-04-01", "2021-01-01")
        .map(good_shots).mosaic().rename("gedi"))
shots = (gedi.addBands(eth).addBands(glad)
         .addBands(gedi.mask().rename("stratum").toInt())
         .stratifiedSample(numPoints=2500, classBand="stratum", region=aoi, scale=25,
                           seed=4, dropNulls=True, tileScale=4))

agbd = (ee.Image("LARSE/GEDI/GEDI04_B_002").select("MU").rename("agbd"))


# ---------------------------------------------------------------------------
# 1. What one plot's "height" is, at three scales
# ---------------------------------------------------------------------------
def blocks(chm, size_m, q):
    """Summarise the CHM in square blocks of size_m, by a percentile."""
    n = int(round(size_m / CELL))
    r, c = chm.shape[0] // n, chm.shape[1] // n
    b = chm[: r * n, : c * n].reshape(r, n, c, n).swapaxes(1, 2).reshape(r, c, -1)
    return np.nanpercentile(b, q, axis=2)


def scale_figure():
    chm = trees()["chm"]
    m10, m25 = blocks(chm, 10, 98), blocks(chm, 25, 98)
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.9))
    for ax, img, cell, title in zip(axes, [chm, m10, m25], [CELL, 10, 25],
                              ["LiDAR CHM, 0.5 m", "98th percentile per 10 m cell",
                               "98th percentile per 25 m cell"]):
        ext = (0, img.shape[1] * cell, 0, img.shape[0] * cell)
        im = ax.imshow(img, cmap="YlGn", vmin=0, vmax=32, extent=ext)
        ax.set_title(title, loc="left", fontsize=10)
        ax.tick_params(labelsize=7)
    axes[0].set_ylabel("metres")
    fig.colorbar(im, ax=axes, shrink=0.8, label="height (m)")
    return fig


def scale_table():
    chm = np.nan_to_num(trees()["chm"])
    t = trees()["table"]
    return pd.DataFrame([
        {"definition": "mean of every 0.5 m cell (gaps count as 0)", "height_m": chm.mean()},
        {"definition": "median tree top", "height_m": t["height_m"].median()},
        {"definition": "median of 10 m cells, 98th percentile (like a 10 m map)",
         "height_m": np.median(blocks(chm, 10, 98))},
        {"definition": "median of 25 m cells, 98th percentile (like GEDI rh98)",
         "height_m": np.median(blocks(chm, 25, 98))},
        {"definition": "tallest point", "height_m": chm.max()}])


# ---------------------------------------------------------------------------
# 2. Satellite maps against GEDI footprints
# ---------------------------------------------------------------------------
def plot_agreement(df):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, col, name in zip(axes, ["eth", "glad"], ["ETH 10 m (2020)", "GLAD 30 m (2019)"]):
        ax.hexbin(df["gedi"], df[col], gridsize=35, cmap="Greens", mincnt=1,
                  extent=(0, 45, 0, 45))
        ax.plot([0, 45], [0, 45], color="#c0392b", lw=1, label="1:1")
        ax.set_xlim(0, 45); ax.set_ylim(0, 45)
        ax.set_xlabel("GEDI rh98 (m)")
        ax.set_title(name, loc="left", fontsize=10)
        ax.legend(frameon=False, fontsize=8, loc="upper left")
    axes[0].set_ylabel("Map height at the footprint (m)")
    fig.suptitle(f"{len(df):,} good GEDI shots, Jambi lowland", x=0.01, ha="left",
                 fontweight="bold")
    fig.tight_layout()
    return fig


def agreement_table(df):
    rows = []
    bins = [(0, 15, "under 15 m"), (15, 25, "15 to 25 m"), (25, 999, "over 25 m"),
            (-999, 999, "all shots")]
    for lo, hi, label in bins:
        d = df[(df.gedi >= lo) & (df.gedi < hi)]
        row = {"GEDI rh98": label, "shots": len(d)}
        for col in ["eth", "glad"]:
            e = d[col] - d["gedi"]
            row[f"{col}_bias_m"] = e.mean()
            row[f"{col}_rmse_m"] = np.sqrt((e ** 2).mean())
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. From height error to biomass error
# ---------------------------------------------------------------------------
def biomass_figure():
    """Chave et al. (2014), eq. 4: AGB = 0.0673 (rho D^2 H)^0.976.
    With wood density and diameter fixed, AGB scales with H^0.976, so a
    relative height error passes almost one-for-one into biomass. If diameter
    is itself estimated from height (as with LiDAR), the error grows."""
    e = np.linspace(-0.4, 0.4, 81)
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    ax.plot(e * 100, ((1 + e) ** 0.976 - 1) * 100, color="#1b7837", lw=2,
            label="height only (D measured)")
    ax.plot(e * 100, ((1 + e) ** (0.976 * 2) - 1) * 100, color="#c0392b", lw=2, ls="--",
            label="D also from height, D ∝ H (illustration)")
    ax.axhline(0, color="#9aa5b1", lw=0.8); ax.axvline(0, color="#9aa5b1", lw=0.8)
    ax.set_xlabel("Error in height (%)")
    ax.set_ylabel("Error in AGB (%)")
    ax.set_title("A 20 % height bias is at least a 20 % biomass bias", loc="left",
                 fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


SRC = "ETH Global Canopy Height 2020 (Lang et al. 2023). GEE."


def products():
    return [
        {"kind": "figure", "name": "ch33-scale", "figure": scale_figure,
         "caption": "The same 90 m plot seen at three cell sizes. Coarser cells keep the "
                    "tall crowns and lose the gaps between them."},
        {"kind": "table", "name": "ch33-scale-table", "data": scale_table,
         "floatfmt": ("", ".1f"),
         "caption": "Five honest answers to 'how tall is this forest?' Always say which "
                    "one you mean."},
        {"kind": "map", "name": "ch33-eth-map", "image": eth.clip(aoi), "region": aoi,
         "vis": {"min": 0, "max": 35, "palette": ["ffffe5", "d9f0a3", "addd8e", "41ab5d",
                                                   "238443", "005a32"]},
         "legend": "Canopy height 2020 (m)", "title": "Canopy height, Jambi lowland",
         "source": SRC,
         "caption": "A 10 m canopy height map from a deep network trained on GEDI. "
                    "Remaining forest, plantation blocks of different ages, and cleared "
                    "land are all visible as height."},
        {"kind": "chart", "name": "ch33-agreement", "data": shots, "plot": plot_agreement,
         "caption": "Map height against GEDI rh98 at the same place. Points below the red "
                    "line are where the map is lower than the laser."},
        {"kind": "table", "name": "ch33-agreement-table", "data": shots,
         "transform": agreement_table,
         "floatfmt": ("", ".0f", ".1f", ".1f", ".1f", ".1f"),
         "caption": "Bias (map minus GEDI) and RMSE by GEDI height class. Both maps pull "
                    "toward the middle: too tall over short vegetation, too short over "
                    "tall forest. The 30 m GLAD map saturates hardest, about 12 m low "
                    "where GEDI sees more than 25 m."},
        {"kind": "figure", "name": "ch33-biomass-error", "figure": biomass_figure,
         "caption": "Height error carried into biomass through the Chave et al. (2014) "
                    "equation. The dashed line is an illustration of what happens when "
                    "diameter is not measured but predicted from height."},
        {"kind": "map", "name": "ch33-l4b-map", "image": agbd.clip(aoi), "region": aoi,
         "vis": {"min": 0, "max": 300, "palette": ["ffffcc", "c2e699", "78c679", "31a354",
                                                    "006837"]},
         "legend": "Mean above-ground biomass density (Mg/ha)",
         "title": "GEDI L4B biomass, 1 km", "source": "GEDI L4B v2.1. GEE.",
         "caption": "GEDI's own gridded biomass: 1 km cells, averaged from footprints "
                    "through GEDI's allometric models. Coarse, but independent of any "
                    "optical map, which makes it a useful check."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(shots.size().getInfo())
