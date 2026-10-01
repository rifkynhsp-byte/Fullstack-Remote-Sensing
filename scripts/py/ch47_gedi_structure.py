#| title: Everything GEDI measures: height, layers, cover and biomass (Python)
#| description: GEDI's full product family over a Jambi landscape: relative height profiles (L2A), cover, plant area and vertical leaf density (L2B), foliage height diversity, and biomass (L4A), compared for intact forest, degraded forest, oil palm and other tree crops.

"""
CHAPTER 47 | One laser shot, many numbers.

GEDI fires a laser from the International Space Station and records the full
returned waveform from a 25 m footprint. From that waveform come:

    L2A  rh0 ... rh100   height below which 0 ... 100 % of the returned energy lies
    L2B  cover, pai      canopy cover, plant area index
         pavd_z0, z1 ... plant area volume density in 5 m layers (0-5, 5-10 m ...)
         fhd_normal      foliage height diversity (how evenly leaves fill the height)
    L4A  agbd            above-ground biomass density, from L2A heights by allometry

Classes: JRC TMF 2022 (undisturbed, degraded), Descals oil palm map, and
other tree cover from ESA WorldCover (mostly rubber, acacia and smallholder mixes).
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([102.45, -2.15, 102.90, -1.75], None, False)
DATES = ("2019-04-01", "2024-01-01")
RH = [f"rh{i}" for i in range(0, 101, 5)]
RH_ALL = RH + ["rh98"]
LAYERS = [f"pavd_z{i}" for i in range(9)]                       # 0-45 m


def good(col, flag):
    return (ee.ImageCollection(col).filterBounds(aoi).filterDate(*DATES)
            .map(lambda i: i.updateMask(i.select(flag).eq(1).And(i.select("degrade_flag").eq(0))
                                        .And(i.select("sensitivity").gt(0.95)
                                             if col.endswith("02_A_002_MONTHLY") else ee.Image(1))))
            )


l2a = good("LARSE/GEDI/GEDI02_A_002_MONTHLY", "quality_flag").select(RH_ALL).mosaic()
l2b = good("LARSE/GEDI/GEDI02_B_002_MONTHLY", "l2b_quality_flag") \
    .select(["cover", "pai", "fhd_normal"] + LAYERS).mosaic()
l4a = good("LARSE/GEDI/GEDI04_A_002_MONTHLY", "l4_quality_flag").select("agbd").mosaic()

tmf_col = ee.ImageCollection("projects/JRC/TMF/v1_2023/AnnualChanges")
tmf = tmf_col.mosaic().select("Dec2022")
palm = (ee.ImageCollection("BIOPAMA/GlobalOilPalm/v1").select("classification").mosaic()
        .lte(2).unmask(0))
wc_trees = ee.Image("ESA/WorldCover/v200/2021").select("Map").eq(10)
NAMES = {1: "intact forest", 2: "degraded forest", 3: "oil palm", 4: "other tree crops"}
cls = (ee.Image(0).where(wc_trees, 4).where(palm.eq(1), 3)
       .where(tmf.eq(2), 2).where(tmf.eq(1), 1).selfMask().rename("cls"))

stack = l2a.addBands(l2b).addBands(l4a).addBands(cls)
# GEDI shots are sparse: sample only where all three products have a shot.
has_shot = (l2a.select("rh98").mask().And(l2b.select("cover").mask())
            .And(l4a.select("agbd").mask()))
shots = stack.updateMask(has_shot).stratifiedSample(
    numPoints=400, classBand="cls", region=aoi, scale=25, seed=2, tileScale=8)


def plot_profiles(df):
    df = df.assign(c=df["cls"].astype(int).map(NAMES))
    cols = {"intact forest": "#00441b", "degraded forest": "#41ab5d", "oil palm": "#e08214",
            "other tree crops": "#8073ac"}
    pct = list(range(0, 101, 5))
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4))
    for name, d in df.groupby("c"):
        a.plot(d[RH].median().to_numpy(), pct, color=cols[name], lw=2, label=f"{name} (n={len(d)})")
        prof = d[LAYERS].median().to_numpy()
        b.plot(prof, np.arange(2.5, 45, 5), "o-", color=cols[name], ms=3)
    a.set_xlabel("Height (m)"); a.set_ylabel("Share of returned energy below (%)")
    a.set_title("L2A: where the energy comes back", loc="left", fontsize=10)
    a.legend(frameon=False, fontsize=7)
    b.set_xlabel("Plant area volume density (m²/m³)"); b.set_ylabel("Height layer (m)")
    b.set_title("L2B: where the leaves are", loc="left", fontsize=10)
    fig.tight_layout()
    return fig


def class_table(df):
    df = df.assign(c=df["cls"].astype(int).map(NAMES))
    g = df.groupby("c")
    out = pd.DataFrame({"shots": g.size(), "rh98_m": g.rh98.median(), "rh50_m": g.rh50.median(),
                        "cover": g.cover.median(), "pai": g.pai.median(),
                        "fhd": g.fhd_normal.median(), "agbd_Mg_ha": g.agbd.median(),
                        "understory_pavd_0_5m": g.pavd_z0.median()})
    return out.reindex(list(NAMES.values())).reset_index().rename(columns={"c": "class"})


GEDI_PROJ = ee.Projection("EPSG:4326").atScale(25)
fhd_grid = (l2b.select("fhd_normal").setDefaultProjection(GEDI_PROJ)
            .reduceResolution(ee.Reducer.mean(), True, 1024)
            .reproject(ee.Projection("EPSG:32748").atScale(500)).clip(aoi))


# ---------------------------------------------------------------------------
# Fuel structure and fire: GEDI shots from before the 2019 fire season
# (Apr-Jul 2019), compared between land that burned in Aug-Nov 2019 and land
# that did not. Ogan Komering Ilir, South Sumatra.
# ---------------------------------------------------------------------------
oki = ee.Geometry.Rectangle([105.30, -3.60, 105.90, -3.10], None, False)
pre_l2a = (ee.ImageCollection("LARSE/GEDI/GEDI02_A_002_MONTHLY").filterBounds(oki)
           .filterDate("2019-04-01", "2019-08-01")
           .map(lambda i: i.updateMask(i.select("quality_flag").eq(1)
                                       .And(i.select("degrade_flag").eq(0))))
           .select(["rh25", "rh50", "rh98"]).mosaic())
pre_l2b = (ee.ImageCollection("LARSE/GEDI/GEDI02_B_002_MONTHLY").filterBounds(oki)
           .filterDate("2019-04-01", "2019-08-01")
           .map(lambda i: i.updateMask(i.select("l2b_quality_flag").eq(1)
                                       .And(i.select("degrade_flag").eq(0))))
           .select(["cover", "pavd_z0", "pavd_z1", "pavd_z2"]).mosaic())
burned19 = (ee.ImageCollection("MODIS/061/MCD64A1").select("BurnDate")
            .filterDate("2019-08-01", "2019-12-01").max().gt(0).unmask(0).rename("burned"))
fuel = (pre_l2a.addBands(pre_l2b)
        .addBands(pre_l2b.select("pavd_z0").add(pre_l2b.select("pavd_z1"))
                  .add(pre_l2b.select("pavd_z2")).rename("low_fuel_0_15m"))
        .addBands(pre_l2b.select("pavd_z1").divide(pre_l2b.select("pavd_z0").add(0.001))
                  .rename("ladder_ratio"))
        .addBands(burned19.toInt()))
fuel_has = pre_l2a.select("rh98").mask().And(pre_l2b.select("cover").mask())
fuel_shots = fuel.updateMask(fuel_has).stratifiedSample(
    numPoints=500, classBand="burned", region=oki, scale=25, seed=6, tileScale=8)


def fuel_table(df):
    g = df.groupby("burned")
    cols = ["rh98", "rh25", "cover", "low_fuel_0_15m", "ladder_ratio"]
    out = g[cols].median().T
    out.columns = ["did not burn" if c == 0 else "burned Aug-Nov 2019" for c in out.columns]
    out["shots_each"] = g.size().min()
    return out.reset_index().rename(columns={"index": "pre-fire GEDI metric (median)"})


def plot_fuel(df):
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.4))
    for ax, col, lab in zip(axes, ["rh98", "cover", "low_fuel_0_15m"],
                            ["Canopy height rh98 (m)", "Canopy cover", "Plant area 0-15 m (m²/m³)"]):
        data = [df.loc[df.burned == b, col].dropna() for b in (0, 1)]
        ax.boxplot(data, tick_labels=["no fire", "burned"], showfliers=False, widths=0.5,
                   medianprops={"color": "#c0392b", "lw": 2})
        ax.set_title(lab, loc="left", fontsize=9)
    fig.suptitle("Fuel structure measured by GEDI months before the 2019 fires",
                 x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    return fig


def products():
    return [
        {"kind": "map", "name": "ch47-classes", "image": cls.clip(aoi), "region": aoi,
         "vis": {"min": 1, "max": 4, "palette": ["00441b", "41ab5d", "e08214", "8073ac"]},
         "classes": [(v, c) for v, c in zip(NAMES.values(),
                                            ["#00441b", "#41ab5d", "#e08214", "#8073ac"])],
         "title": "Four kinds of tree cover, Jambi", "source": "JRC TMF; Descals et al.; ESA WorldCover. GEE.",
         "caption": "The classes compared below."},
        {"kind": "chart", "name": "ch47-profiles", "data": shots, "plot": plot_profiles,
         "caption": "Median GEDI profiles of 400 shots per class. Left: cumulative "
                    "returned energy by height (L2A). Right: leaf area by 5 m layer (L2B)."},
        {"kind": "table", "name": "ch47-table", "data": shots, "transform": class_table,
         "floatfmt": ("", ".0f", ".1f", ".1f", ".2f", ".2f", ".2f", ".0f", ".3f"),
         "caption": "Median of every GEDI structure variable per class."},
        {"kind": "map", "name": "ch47-fhd", "image": fhd_grid, "region": aoi,
         "vis": {"min": 1.5, "max": 3.3, "palette": ["fff5eb", "fdae6b", "e6550d", "7f2704"]},
         "legend": "Foliage height diversity (mean of GEDI shots, 500 m)",
         "title": "Structural complexity", "source": "GEDI L2B. GEE.",
         "caption": "Foliage height diversity averaged on a 500 m grid: high where leaves "
                    "fill many layers, a common proxy for habitat for birds and mammals."},
        {"kind": "chart", "name": "ch47-fuel", "data": fuel_shots, "plot": plot_fuel,
         "caption": "GEDI shots from April-July 2019 in Ogan Komering Ilir, split by "
                    "whether the place burned in August-November 2019 (MODIS MCD64A1)."},
        {"kind": "table", "name": "ch47-fuel-table", "data": fuel_shots, "transform": fuel_table,
         "floatfmt": ("", ".2f", ".2f", ".0f"),
         "caption": "Pre-fire fuel structure, burned against unburned. Ladder ratio: leaf "
                    "area at 5-10 m over 0-5 m, a crude measure of fuel connecting the "
                    "ground to the crowns."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(shots.size().getInfo())
