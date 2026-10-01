#| title: The carbon balance of a peat landscape (Python)
#| description: What satellites can and cannot say about the carbon balance of Tanjung Jabung Timur, Jambi: productivity (MODIS GPP and NPP), the biomass stock (GEDI), losses from clearing, burned area, and CO2 from drained peat with IPCC Tier 1 factors.

"""
CHAPTER 42 | A landscape carbon balance, term by term.

    GPP  gross primary production: carbon fixed by photosynthesis     MODIS MOD17
    NPP  net primary production = GPP - plant respiration              MODIS MOD17
    NEP  = NPP - soil (heterotrophic) respiration                      NOT measurable from space
    NBP  = NEP - disturbance losses (clearing, fire, harvest, peat)    partly measurable

Peat drainage CO2: IPCC 2013 Wetlands Supplement, Table 2.1 (tropical), t CO2-C/ha/yr:
    oil palm 11 (5.6-17); plantations, unknown or long rotation 15 (10-21);
    forest and cleared forest (shrubland), drained 5.3 (-0.7-9.5)
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

district = (ee.FeatureCollection("FAO/GAUL/2025/level2")
            .filter(ee.Filter.eq("GAUL1_NAME", "Jambi"))
            .filter(ee.Filter.eq("GAUL2_NAME", "Tanjung Jabung Timur")).geometry())
C2CO2 = 44 / 12

mod17 = ee.ImageCollection("MODIS/061/MOD17A3HGF")
peat = ee.Image("projects/sat-io/open-datasets/GLOBAL-PEATLAND-DATABASE").gte(1).unmask(0)
palm = (ee.ImageCollection("BIOPAMA/GlobalOilPalm/v1").select("classification").mosaic()
        .lte(2).unmask(0))                                   # 1 industrial, 2 smallholder
tmf_col = ee.ImageCollection("projects/JRC/TMF/v1_2023/AnnualChanges")
tmf23 = tmf_col.mosaic().setDefaultProjection(tmf_col.first().projection()).select("Dec2023")
gfc = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")
l4b = ee.Image("LARSE/GEDI/GEDI04_B_002").select("MU")


# ---------------------------------------------------------------------------
# 1. Productivity: GPP and NPP, 2001-2024
# ---------------------------------------------------------------------------
def productivity_frame():
    def one(img):
        s = (img.select(["Gpp", "Npp"]).multiply(0.0001)              # kg C / m2 / yr
             .multiply(ee.Image.pixelArea()).divide(1e9)              # -> Mt C per pixel
             .reduceRegion(ee.Reducer.sum(), district, 500, maxPixels=1e10))
        return ee.Feature(None, s).set("year", img.date().get("year"))
    fc = mod17.filterDate("2001-01-01", "2025-01-01").map(one)
    df = pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]])
    return df.rename(columns={"Gpp": "GPP_MtC", "Npp": "NPP_MtC"}).sort_values("year")


def plot_productivity(df):
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot(df.year, df.GPP_MtC, "o-", ms=3, color="#1b7837", label="GPP")
    ax.plot(df.year, df.NPP_MtC, "o-", ms=3, color="#7fbf7b", label="NPP")
    ax.set_ylabel("Mt C per year, whole district")
    ax.set_title("Photosynthesis is large and steady; most of it returns to the air "
                 "through respiration", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


# ---------------------------------------------------------------------------
# 2. Land classes on peat, and the peat drainage flux
# ---------------------------------------------------------------------------
# Strata on peat (TMF 2023 and the oil palm map):
#   0 undisturbed forest (taken as undrained)   1 degraded or regrowing forest
#   2 oil palm                                   3 other cleared land
strata = (ee.Image(3)
          .where(tmf23.eq(2).Or(tmf23.eq(4)), 1)
          .where(tmf23.eq(1), 0)
          .where(palm.eq(1), 2)
          .updateMask(peat.eq(1).And(tmf23.neq(5)))                 # peat, not open water
          .rename("stratum"))
NAMES = {0: "undisturbed forest", 1: "degraded / regrowing forest", 2: "oil palm",
         3: "other cleared land"}
# IPCC 2013 Table 2.1 (tropical), t CO2-C/ha/yr: (mean, low, high). Choices per stratum:
EF = {0: (0.0, 0.0, 0.0),        # assumed undrained: no drainage emission
      1: (5.3, -0.7, 9.5),       # "forest and cleared forest (shrubland), drained"
      2: (11.0, 5.6, 17.0),      # "plantations, drained, oil palm"
      3: (15.0, 10.0, 21.0)}     # "plantations, drained, unknown or long rotation"


def peat_table():
    g = (ee.Image.pixelArea().divide(1e4).addBands(strata)
         .reduceRegion(ee.Reducer.sum().group(1, "stratum"), district, 30, maxPixels=1e11,
                       tileScale=8).get("groups").getInfo())
    rows = []
    for d in g:
        k = int(d["stratum"]); ha = d["sum"]; m, lo, hi = EF[k]
        rows.append({"stratum on peat": NAMES[k], "area_ha": ha, "EF_tC_ha_yr": m,
                     "Mt_CO2_yr": ha * m * C2CO2 / 1e6,
                     "low": ha * lo * C2CO2 / 1e6, "high": ha * hi * C2CO2 / 1e6})
    return pd.DataFrame(rows).sort_values("stratum on peat")


# ---------------------------------------------------------------------------
# 3. Biomass stock, clearing and fire
# ---------------------------------------------------------------------------
def stock_and_losses():
    area_ha = ee.Image.pixelArea().divide(1e4)
    forest = tmf23.eq(1).Or(tmf23.eq(2))
    stock = (l4b.multiply(0.47).rename("c")                        # Mg C/ha above ground
             .updateMask(forest.reduceResolution(ee.Reducer.mean(), True, 2048)
                         .reproject(l4b.projection()).gte(0.5))
             .reduceRegion(ee.Reducer.mean(), district, 1000, maxPixels=1e9).get("c"))
    forest_ha = area_ha.updateMask(forest).reduceRegion(ee.Reducer.sum(), district, 30,
                                                        maxPixels=1e11, tileScale=8)
    rows = []
    for y in range(2015, 2024):
        lost = gfc.select("treecover2000").gte(30).And(gfc.select("lossyear").eq(y - 2000))
        burned = (ee.ImageCollection("MODIS/061/MCD64A1").select("BurnDate")
                  .filterDate(f"{y}-01-01", f"{y + 1}-01-01").max().gt(0))
        s = (area_ha.updateMask(lost).rename("lost")
             .addBands(area_ha.updateMask(burned).rename("burned"))
             .addBands(area_ha.updateMask(burned.And(peat.eq(1))).rename("burned_peat"))
             .reduceRegion(ee.Reducer.sum(), district, 30, maxPixels=1e11, tileScale=8))
        rows.append(ee.Feature(None, s).set("year", y))
    stock_c = stock.getInfo()
    forest = forest_ha.getInfo()["area"]
    df = pd.DataFrame([f["properties"] for f in ee.FeatureCollection(rows).getInfo()["features"]])
    df["forest_C_stock_MtC"] = stock_c * forest / 1e6
    df["agb_C_Mg_ha"] = stock_c
    # Clearing emission: above + below ground (R = 0.37) of the mean forest stock
    df["clearing_Mt_CO2"] = df["lost"] * stock_c * 1.37 * C2CO2 / 1e6
    return df


_c = {}


def losses():
    if "df" not in _c:
        _c["df"] = stock_and_losses()
    return _c["df"]


def plot_losses(df):
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.bar(df.year - 0.2, df.lost / 1000, 0.4, color="#c0392b", label="tree cover lost")
    ax.bar(df.year + 0.2, df.burned / 1000, 0.4, color="#e67e22", label="burned (MCD64A1)")
    ax.set_ylabel("Thousand hectares")
    ax.set_title("Disturbance: clearing every year, fire in the drought years",
                 loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def balance_table():
    p = productivity_frame(); pt = peat_table(); ls = losses()
    gpp = p[(p.year >= 2015) & (p.year <= 2023)].GPP_MtC.mean() * C2CO2
    npp = p[(p.year >= 2015) & (p.year <= 2023)].NPP_MtC.mean() * C2CO2
    return pd.DataFrame([
        {"term": "GPP (gross uptake, not a net sink)", "Mt_CO2_per_yr": -gpp,
         "measured_from_space": "modelled from MODIS"},
        {"term": "NPP (after plant respiration, still not a net sink)", "Mt_CO2_per_yr": -npp,
         "measured_from_space": "modelled from MODIS"},
        {"term": "Soil (heterotrophic) respiration", "Mt_CO2_per_yr": np.nan,
         "measured_from_space": "no"},
        {"term": "Clearing of forest biomass (mean 2015-2023)",
         "Mt_CO2_per_yr": ls.clearing_Mt_CO2.mean(), "measured_from_space": "area yes, stock GEDI"},
        {"term": "Peat drainage (IPCC Tier 1)", "Mt_CO2_per_yr": pt.Mt_CO2_yr.sum(),
         "measured_from_space": "area yes, EF from IPCC"},
        {"term": "Peat and vegetation fires", "Mt_CO2_per_yr": np.nan,
         "measured_from_space": "area yes, burn depth no"},
    ])


def products():
    return [
        {"kind": "map", "name": "ch42-peat-strata", "image": strata.clip(district),
         "region": district.bounds(), "vis": {"min": 0, "max": 3,
                                             "palette": ["1b7837", "a6dba0", "e08214", "b2abd2"]},
         "classes": [(NAMES[k], "#" + c) for k, c in
                     zip(range(4), ["1b7837", "a6dba0", "e08214", "b2abd2"])],
         "title": "What covers the peat, Tanjung Jabung Timur 2023",
         "source": "JRC TMF 2023; Descals et al. oil palm; Global Peatland Map 2.0. GEE.",
         "caption": "Land on peat in four strata, each matched to an IPCC drainage "
                    "emission factor. Peat outside the Global Peatland Map is not counted."},
        {"kind": "table", "name": "ch42-peat-table", "data": peat_table,
         "floatfmt": ("", ",.0f", ".1f", ".2f", ".2f", ".2f"),
         "caption": "CO₂ from drained peat by stratum, with the IPCC 95 % range (low, high)."},
        {"kind": "chart", "name": "ch42-productivity", "data": productivity_frame,
         "plot": plot_productivity,
         "caption": "Gross and net primary production of the whole district, MODIS MOD17."},
        {"kind": "chart", "name": "ch42-losses", "data": losses, "plot": plot_losses,
         "caption": "Hectares of tree cover lost (Hansen) and burned (MODIS) each year."},
        {"kind": "table", "name": "ch42-balance", "data": balance_table,
         "floatfmt": ("", ",.1f", ""),
         "caption": "The carbon balance as far as satellites can take it, in Mt CO₂ per "
                    "year (negative = uptake). The missing rows are why a satellite "
                    "'carbon balance' is never complete."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(peat_table())
