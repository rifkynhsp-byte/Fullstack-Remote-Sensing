#| title: Mapping ecosystem services (Python)
#| description: Water yield, carbon storage and habitat quality for the upper Citarum basin, where they overlap, and what a forest-to-farm scenario would cost, in the spirit of InVEST.

"""
CHAPTER 43 | Three services, one landscape, one scenario.

    water yield     P - ET (CHIRPS, MODIS MOD16), mm per year
    carbon storage  GEDI L4A biomass footprints averaged per land-cover class,
                    then mapped back by class (InVEST's carbon "lookup" logic)
    habitat         forest, discounted by closeness to built-up land
    scenario        forest within 500 m of cropland becomes cropland

Land cover: ESA WorldCover 2021, 10 m. Area: Bandung basin, upper Citarum.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([107.30, -7.35, 107.95, -6.75], None, False)
wc = ee.Image("ESA/WorldCover/v200/2021").select("Map").clip(aoi)
CLASSES = {10: "tree cover", 20: "shrubland", 30: "grassland", 40: "cropland", 50: "built-up",
           60: "bare", 80: "water"}
PALETTE = {10: "006400", 20: "ffbb22", 30: "ffff4c", 40: "f096ff", 50: "fa0000",
           60: "b4b4b4", 80: "0064c8"}

# ---------------------------------------------------------------------------
# 1. Water yield
# ---------------------------------------------------------------------------
P = (ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD").select("precipitation")
     .filterDate("2018-01-01", "2024-01-01").sum().divide(6))
ET = (ee.ImageCollection("MODIS/061/MOD16A2GF").select("ET")
      .filterDate("2018-01-01", "2024-01-01").sum().multiply(0.1).divide(6))
# CHIRPS pixels are 5 km. The squares this leaves in the maps are the true
# resolution of the rainfall data; smoothing them would only hide it.
water_yield = P.subtract(ET).rename("water_mm").clip(aoi)

# ---------------------------------------------------------------------------
# 2. Carbon: mean GEDI biomass per land-cover class (footprints 2019-2023)
# ---------------------------------------------------------------------------
gedi = (ee.ImageCollection("LARSE/GEDI/GEDI04_A_002_MONTHLY").filterBounds(aoi)
        .filterDate("2019-04-01", "2024-01-01")
        .map(lambda i: i.updateMask(i.select("l4_quality_flag").eq(1)
                                    .And(i.select("degrade_flag").eq(0))))
        .select("agbd").mosaic())


def carbon_lookup():
    g = (gedi.addBands(wc.rename("cls"))
         .reduceRegion(ee.Reducer.mean().combine(ee.Reducer.count(), None, True)
                       .group(1, "cls"), aoi, 25, maxPixels=1e10, tileScale=8)
         .get("groups").getInfo())
    rows = [{"class": CLASSES.get(int(d["cls"]), str(d["cls"])), "code": int(d["cls"]),
             "gedi_shots": d["count"], "agbd_Mg_ha": d["mean"],
             "carbon_MgC_ha": d["mean"] * 0.47} for d in g if int(d["cls"]) in CLASSES]
    return pd.DataFrame(rows).sort_values("carbon_MgC_ha", ascending=False)


_lookup = {}


def lookup():
    if not _lookup:
        _lookup["df"] = carbon_lookup()
    return _lookup["df"]


def carbon_map(landcover):
    df = lookup()
    return landcover.remap(df.code.tolist(), df.carbon_MgC_ha.tolist()).rename("carbon")


# ---------------------------------------------------------------------------
# 3. Habitat quality: forest, less valuable near built-up land
# ---------------------------------------------------------------------------
def habitat_map(landcover):
    utm = ee.Projection("EPSG:32748").atScale(30)
    built = landcover.eq(50)
    dist_km = (built.reproject(utm).fastDistanceTransform(256).sqrt().multiply(30)
               .divide(1000))
    return (landcover.eq(10).multiply(ee.Image(1).subtract(dist_km.multiply(-1)
                                                            .divide(2).exp()))
            .rename("habitat"))                       # 0 at a settlement edge, -> 1 far away


# ---------------------------------------------------------------------------
# 4. Scenario: forest within 500 m of cropland becomes cropland
# ---------------------------------------------------------------------------
utm = ee.Projection("EPSG:32748").atScale(30)
near_crop = (wc.eq(40).reproject(utm).fastDistanceTransform(32).sqrt().multiply(30)
             .lte(500))
scenario = wc.where(wc.eq(10).And(near_crop), 40)


def summary_table():
    df = lookup()
    # Mean ET per class, to move water yield with land use in the scenario
    et_cls = (ET.addBands(wc.rename("cls"))
              .reduceRegion(ee.Reducer.mean().group(1, "cls"), aoi, 500, maxPixels=1e10)
              .get("groups").getInfo())
    et_map = {int(d["cls"]): d["mean"] for d in et_cls}
    codes = [c for c in df.code if c in et_map]
    p_mean = P.reduceRegion(ee.Reducer.mean(), aoi, 5000).getInfo()["precipitation"]
    area = ee.Image.pixelArea()
    rows = []
    for name, lc in [("today (2021)", wc), ("scenario", scenario)]:
        wy = ee.Image(p_mean).subtract(lc.remap(codes, [et_map[c] for c in codes]))
        s = (area.multiply(carbon_map(lc)).divide(1e4).rename("carbon")      # MgC per pixel
             .addBands(area.multiply(wy).divide(1e3).rename("water"))        # m3 per pixel
             .addBands(habitat_map(lc).multiply(area).divide(1e4).rename("habitat"))
             .addBands(area.updateMask(lc.eq(10)).divide(1e4).rename("forest"))
             .reduceRegion(ee.Reducer.sum(), aoi, 30, maxPixels=1e11, tileScale=8).getInfo())
        rows.append({"case": name, "forest_ha": s["forest"],
                     "carbon_MtC": s["carbon"] / 1e6,
                     "water_yield_million_m3": s["water"] / 1e6,
                     "habitat_units_ha": s["habitat"]})
    return pd.DataFrame(rows)


def hotspot_image():
    """Top 20 % of each service, counted: 0-3 services per pixel."""
    c = carbon_map(wc); h = habitat_map(wc); w = water_yield
    def top(img):
        q = img.reduceRegion(ee.Reducer.percentile([80]), aoi, 300, maxPixels=1e10,
                             tileScale=4).values().get(0)
        return img.gte(ee.Number(q))
    return top(c).add(top(h)).add(top(w)).rename("n").clip(aoi)


def plot_carbon(df):
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    d = df.sort_values("carbon_MgC_ha")
    ax.barh(d["class"], d.carbon_MgC_ha, color=["#" + PALETTE[c] for c in d.code])
    for y, (v, n) in enumerate(zip(d.carbon_MgC_ha, d.gedi_shots)):
        ax.text(v, y, f"  {v:.0f}  (n={n:,})", va="center", fontsize=7)
    ax.set_xlabel("Above-ground carbon (Mg C/ha), mean of GEDI footprints")
    ax.set_title("The carbon lookup table, measured instead of assumed", loc="left",
                 fontsize=10)
    return fig


def products():
    return [
        {"kind": "map", "name": "ch43-landcover", "image": wc, "region": aoi,
         "vis": {"min": 10, "max": 80, "palette": [PALETTE.get(v, "000000") for v in range(10, 81, 10)]},
         "classes": [(CLASSES[k], "#" + PALETTE[k]) for k in CLASSES],
         "title": "Bandung basin land cover, 2021", "source": "ESA WorldCover 2021. GEE.",
         "caption": "The land-cover map every service below is computed from."},
        {"kind": "chart", "name": "ch43-carbon-lookup", "data": lookup, "plot": plot_carbon,
         "caption": "Mean above-ground carbon of each land-cover class from GEDI L4A "
                    "footprints (carbon = 0.47 × biomass). n is the number of footprints."},
        {"kind": "map", "name": "ch43-water-yield", "image": water_yield, "region": aoi,
         "vis": {"min": 500, "max": 3000, "palette": ["fff7bc", "c7e9b4", "41b6c4", "225ea8",
                                                       "081d58"]},
         "legend": "Water yield P − ET, 2018-2023 (mm per year)",
         "title": "Water yield", "source": "CHIRPS v2; MODIS MOD16A2GF. GEE.",
         "caption": "Water left for rivers and groundwater. The volcanic uplands around the "
                    "basin yield most."},
        {"kind": "map", "name": "ch43-hotspots", "image": hotspot_image(), "region": aoi,
         "vis": {"min": 0, "max": 3, "palette": ["f0f0f0", "fdcc8a", "fc8d59", "b30000"]},
         "classes": [("none", "#f0f0f0"), ("one service", "#fdcc8a"),
                     ("two services", "#fc8d59"), ("all three", "#b30000")],
         "title": "Where the services stack up", "source": "This chapter's three service maps.",
         "caption": "Pixels in the top 20 % for carbon, habitat and water yield, counted. "
                    "Where all three overlap is where protection pays three times. Water "
                    "yield rests on 5 km rainfall data: the square edges are that "
                    "resolution showing, not field boundaries."},
        {"kind": "table", "name": "ch43-scenario", "data": summary_table,
         "floatfmt": ("", ",.0f", ".2f", ",.1f", ",.0f"),
         "caption": "Today against a scenario where forest within 500 m of cropland becomes "
                    "cropland. Water yield rises slightly (less ET) while carbon and habitat "
                    "fall: services trade off against each other."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(carbon_lookup())
