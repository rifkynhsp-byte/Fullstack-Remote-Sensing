#| title: Mining against the services it removes: an environmental cost and a break-even (Python)
#| description: Nickel mining around Pomalaa, Kolaka (Southeast Sulawesi). The footprint of forest cleared since 2001 that is still bare, the carbon it held from GEDI biomass, its value at the social cost of carbon, the ecosystem services lost from published unit values, and the break-even net benefit per hectare mining must deliver to outweigh them.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 63 | Does the benefit outweigh the loss?

An environmental impact statement asks what a project removes. A cost-benefit
analysis asks whether what it gives is worth more. Satellites can measure the
first part well; this script measures it and turns it into a break-even.

    1. footprint  forest (Hansen tree cover >= 30 % in 2000) lost since 2001 and
                  still bare in 2024 (Dynamic World mode): the mine. Built land is
                  excluded: a first version counted the growing towns as mine.
    2. carbon     median GEDI L4A biomass of intact forest nearby (Mg/ha),
                  x 1.37 (roots, IPCC 2006 R = 0.37) x 0.47 (carbon fraction)
                  x 44/12 (CO2): tonnes CO2 released per hectare cleared
    3. price      US EPA (2023) social cost of carbon: 120 / 190 / 340 US$ per
                  t CO2 (low / central / high)
    4. services   tropical forest unit values, Costanza et al. (2014): median
                  2,355 and mean 5,264 US$/ha/yr across 96 studies (Table 4),
                  2007 international dollars
    5. break-even net benefit per hectare that mining must deliver over T years
                  to outweigh: carbon (once) + services x T (undiscounted)

Mining older than 2001 is not in the footprint: Hansen starts in 2001.
"""

from functools import lru_cache

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([121.50, -4.35, 121.78, -4.02], None, False)   # Pomalaa, Kolaka
CF, ROOT, CO2 = 0.47, 0.37, 44 / 12
SCC = {"low": 120, "central": 190, "high": 340}
SERVICES = {"median": 2355, "mean": 5264}
YEARS_OF_SERVICE = (10, 30)

gfc = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")
forest2000 = gfc.select("treecover2000").gte(30)
lossyear = gfc.select("lossyear").unmask(0)
dw24 = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(aoi)
        .filterDate("2024-01-01", "2025-01-01").select("label").mode())
open_now = dw24.eq(7)        # bare in 2024 (built is excluded: towns and roads grew too)
mine = forest2000.And(lossyear.gt(0)).And(open_now).selfMask().clip(aoi).rename("mine")
intact = forest2000.And(lossyear.eq(0)).And(gfc.select("treecover2000").gte(60))
area = ee.Image.pixelArea().divide(1e4)


@lru_cache(maxsize=1)
def _footprint():
    return _footprint_compute()


def footprint_table():
    return _footprint().copy()


def _footprint_compute():
    g = (area.updateMask(mine).addBands(lossyear.rename("y"))
         .reduceRegion(ee.Reducer.sum().group(1, "y"), aoi, 30, maxPixels=1e10, tileScale=8)
         .get("groups").getInfo())
    df = pd.DataFrame([{"year": 2000 + int(x["y"]), "new_mine_ha": x["sum"]} for x in g])
    df = df.sort_values("year")
    df["cumulative_ha"] = df.new_mine_ha.cumsum()
    return df.reset_index(drop=True)


def plot_footprint(df):
    fig, ax = plt.subplots(figsize=(7, 3.3))
    ax.bar(df.year, df.new_mine_ha, color="#b2182b", label="forest cleared, still bare in 2024")
    ax2 = ax.twinx()
    ax2.plot(df.year, df.cumulative_ha, color="#1f2933", marker="o", ms=3, label="cumulative")
    ax.set_ylabel("ha per year"); ax2.set_ylabel("cumulative ha")
    ax.set_title("The mine footprint grows, Pomalaa", loc="left", fontsize=10)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=8, loc="upper left")
    return fig


@lru_cache(maxsize=1)
def forest_agb():
    l4a = (ee.ImageCollection("LARSE/GEDI/GEDI04_A_002_MONTHLY").filterBounds(aoi)
           .filterDate("2019-04-01", "2024-01-01")
           .map(lambda i: i.updateMask(i.select("l4_quality_flag").eq(1)
                                       .And(i.select("degrade_flag").eq(0))))
           .select("agbd").mosaic().updateMask(intact))
    pts = l4a.sample(region=aoi, scale=25, numPixels=20000, seed=2, tileScale=8)
    v = np.array(pts.aggregate_array("agbd").getInfo())
    return v[(v > 0) & (v < 1000)]


@lru_cache(maxsize=1)
def _cost():
    return _cost_compute()


def cost_table():
    return _cost().copy()


def _cost_compute():
    fp = footprint_table()
    ha = fp.new_mine_ha.sum()
    agb = forest_agb()
    rows = []
    for name, q in (("biomass p25", 25), ("biomass median", 50), ("biomass p75", 75)):
        b = np.percentile(agb, q)
        tco2 = b * (1 + ROOT) * CF * CO2
        rows.append({"case": name, "forest_agb_mg_ha": b, "t_co2_per_ha": tco2,
                     "carbon_usd_per_ha_central": tco2 * SCC["central"],
                     "mine_ha_since_2001": ha, "gedi_shots": len(agb)})
    return pd.DataFrame(rows)


def breakeven_table():
    c = cost_table()
    tco2 = c.loc[c.case == "biomass median", "t_co2_per_ha"].iloc[0]
    rows = []
    for sname, scc in SCC.items():
        for vname, val in SERVICES.items():
            for T in YEARS_OF_SERVICE:
                rows.append({"carbon price": f"{sname} ({scc} $/t)",
                             "service value": f"{vname} ({val:,} $/ha/yr)", "years": T,
                             "carbon_usd_ha": tco2 * scc, "services_usd_ha": val * T,
                             "breakeven_usd_ha": tco2 * scc + val * T})
    df = pd.DataFrame(rows)
    df["breakeven_for_footprint_musd"] = df.breakeven_usd_ha * c.mine_ha_since_2001.iloc[0] / 1e6
    return df


def plot_breakeven(df):
    d = df[df.years == 30]
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    labels = [f"{a.split(' ')[0]} C / {b.split(' ')[0]} ES" for a, b in
              zip(d["carbon price"], d["service value"])]
    ax.barh(labels, d.carbon_usd_ha / 1000, color="#525252", label="carbon (once)")
    ax.barh(labels, d.services_usd_ha / 1000, left=d.carbon_usd_ha / 1000, color="#1a9850",
            label="ecosystem services, 30 years")
    ax.set_xlabel("Thousand US$ per hectare")
    ax.set_title("What mining must earn per hectare to outweigh the loss", loc="left",
                 fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def s2(start, end):
    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi)
            .filterDate(start, end)
            .linkCollection(ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"),
                            ["cs"])
            .map(lambda i: i.updateMask(i.select("cs").gte(0.6))).median()
            .visualize(bands=["B4", "B3", "B2"], min=200, max=2200))


after_vis = s2("2024-01-01", "2025-01-01").blend(
    ee.Image().byte().paint(ee.FeatureCollection(
        mine.reduceToVectors(geometry=aoi, scale=60, maxPixels=1e10, tileScale=8)), 1, 1)
    .visualize(palette=["ffff00"]))


def products():
    rgb = {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255}
    return [
        {"kind": "map", "name": "ch63-mine", "image": after_vis, "region": aoi, "vis": rgb,
         "classes": [("forest cleared since 2001, bare in 2024", "#ffff00")],
         "title": "Pomalaa, 2024: the mine footprint", "source":
             "Sentinel-2 L2A; Hansen GFC v1.13; Dynamic World. GEE.",
         "caption": "Sentinel-2 2024 with the outline of forest cleared since 2001 that is "
                    "still bare ground in 2024 (yellow)."},
        {"kind": "chart", "name": "ch63-footprint", "data": footprint_table,
         "plot": plot_footprint,
         "caption": "Forest cleared each year that is still bare ground in 2024, and the "
                    "running total."},
        {"kind": "table", "name": "ch63-cost", "data": cost_table,
         "floatfmt": ("", ".0f", ".0f", ",.0f", ",.0f", ",.0f"),
         "caption": "Carbon released per hectare cleared, from GEDI biomass of intact forest "
                    "nearby, valued at the central social cost of carbon."},
        {"kind": "table", "name": "ch63-breakeven", "data": breakeven_table,
         "floatfmt": ("", "", ",.0f", ",.0f", ",.0f", ",.0f", ",.0f"),
         "caption": "Break-even: the net benefit per hectare mining must deliver to outweigh "
                    "the carbon and ecosystem services lost (undiscounted)."},
        {"kind": "chart", "name": "ch63-breakeven-chart", "data": breakeven_table,
         "plot": plot_breakeven,
         "caption": "Break-even per hectare over 30 years, for each carbon price and service "
                    "value."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(footprint_table())
