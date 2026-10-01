#| title: Oil palm age, height and life stage from 34 years of Landsat (Python)
#| description: Planting year of every oil palm pixel from the Landsat archive, checked against GEDI canopy height, and the area in each life stage, for a plantation landscape in Central Kalimantan.

"""
CHAPTER 44 | How old is this plantation?

Planting oil palm starts with clearing: the land is bare for a year or two,
then the canopy closes again over about five years. In a yearly series of
the Normalised Burn Ratio (NBR, sensitive to bare soil and canopy water) the
clearing shows as the deepest dip. The year of that dip is a good estimate
of the planting year, and 2023 minus it is the age.

    palm pixels    Descals et al. (2021) global oil palm map
    time series    Landsat 5, 7, 8, 9 Collection 2 surface reflectance, 1990-2023
    check          GEDI L2A rh98 height should rise with age

The author's TimeseriesAPPsawit app charts the same Landsat signal pixel by
pixel; here it is turned into a map.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([112.60, -2.50, 113.10, -2.00], None, False)   # Kotawaringin Timur
palm = (ee.ImageCollection("BIOPAMA/GlobalOilPalm/v1").select("classification").mosaic()
        .lte(2).selfMask().clip(aoi))
YEARS = list(range(1990, 2024))


def landsat(col, nir, swir2):
    def prep(img):
        qa = img.select("QA_PIXEL")
        ok = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        sr = img.select([nir, swir2]).multiply(0.0000275).add(-0.2)
        # normalizedDifference makes a new image: copy the date, or filterDate finds nothing.
        return (sr.normalizedDifference([nir, swir2]).rename("nbr").updateMask(ok)
                .copyProperties(img, ["system:time_start"]))
    return ee.ImageCollection(col).filterBounds(aoi).map(prep)


ls = (landsat("LANDSAT/LT05/C02/T1_L2", "SR_B4", "SR_B7")
      .merge(landsat("LANDSAT/LE07/C02/T1_L2", "SR_B4", "SR_B7"))
      .merge(landsat("LANDSAT/LC08/C02/T1_L2", "SR_B5", "SR_B7"))
      .merge(landsat("LANDSAT/LC09/C02/T1_L2", "SR_B5", "SR_B7")))

# Some early years have no clear scene here; a masked placeholder keeps the band.
EMPTY = ee.ImageCollection([ee.Image.constant(0).rename("nbr").updateMask(0)])
annual = ee.ImageCollection([
    ls.filterDate(f"{y}-01-01", f"{y + 1}-01-01").merge(EMPTY).median()
      .addBands(ee.Image.constant(y).toInt16().rename("year")).set("year", y)
    for y in YEARS])

# The deepest dip: qualityMosaic picks, per pixel, the year with the highest -NBR.
dip = annual.map(lambda i: i.addBands(i.select("nbr").multiply(-1).rename("q"))) \
            .qualityMosaic("q")
plant_year = dip.select("year").updateMask(palm).updateMask(dip.select("nbr").lt(0.3))
age = ee.Image(2023).subtract(plant_year).rename("age")

# Height from GEDI footprints (good quality, 2019-2023)
rh98 = (ee.ImageCollection("LARSE/GEDI/GEDI02_A_002_MONTHLY").filterBounds(aoi)
        .filterDate("2019-04-01", "2024-01-01")
        .map(lambda i: i.updateMask(i.select("quality_flag").eq(1)
                                    .And(i.select("degrade_flag").eq(0)))
             .select("rh98"))
        .mosaic())
pairs = (rh98.addBands(age).addBands(rh98.mask().And(age.mask()).rename("s").toInt())
         .stratifiedSample(numPoints=3000, classBand="s", region=aoi, scale=25, seed=3,
                           tileScale=8, classValues=[1], classPoints=[3000]))


def plot_height(df):
    df = df[(df.age >= 0) & (df.age <= 33)]
    g = df.groupby("age")["rh98"]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.scatter(df.age + np.random.default_rng(0).uniform(-0.3, 0.3, len(df)), df.rh98,
               s=4, color="#9aa5b1", alpha=0.5, label="GEDI footprints")
    med = g.median()
    ax.plot(med.index, med.values, "o-", color="#c0392b", ms=4, label="median per year of age")
    ax.set_xlabel("Estimated age in 2023 (years since the clearing dip)")
    ax.set_ylabel("GEDI rh98 height (m)")
    ax.set_title("If the age is right, height must rise with it", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def stage_table():
    stage = (ee.Image(0)
             .where(age.lt(3), 1).where(age.gte(3).And(age.lt(9)), 2)
             .where(age.gte(9).And(age.lt(19)), 3).where(age.gte(19).And(age.lt(25)), 4)
             .where(age.gte(25), 5).updateMask(age.mask()).rename("stage"))
    g = (ee.Image.pixelArea().divide(1e4).addBands(stage)
         .reduceRegion(ee.Reducer.sum().group(1, "stage"), aoi, 30, maxPixels=1e10,
                       tileScale=8).get("groups").getInfo())
    names = {1: "immature (0-2 yr)", 2: "young (3-8 yr)", 3: "prime (9-18 yr)",
             4: "mature (19-24 yr)", 5: "replanting due (25+ yr)"}
    df = pd.DataFrame([{"life stage": names[int(d["stage"])], "area_ha": d["sum"]}
                       for d in g if int(d["stage"]) in names])
    df["share"] = df.area_ha / df.area_ha.sum()
    return df


def series_frame():
    """Five random palm pixels, their whole NBR history."""
    pts = palm.addBands(plant_year.rename("py")).sample(region=aoi, scale=30, numPixels=400,
                                                        seed=11, geometries=True).limit(5)
    fc = annual.map(lambda img: img.select("nbr").reduceRegions(pts, ee.Reducer.first(), 30)
                    .map(lambda f: f.set("year", img.get("year"))))
    rows = [f["properties"] for f in fc.flatten().getInfo()["features"]]
    df = pd.DataFrame(rows).rename(columns={"first": "nbr"})
    df["pixel"] = df.groupby("py").ngroup() if "py" in df else 0
    return df


def plot_series(df):
    fig, ax = plt.subplots(figsize=(8, 3.4))
    for (py, d), c in zip(df.groupby("py"), plt.cm.tab10.colors):
        d = d.sort_values("year")
        ax.plot(d.year, d.nbr, "-", color=c, lw=1.2)
        ax.axvline(py, color=c, ls=":", lw=1)
    ax.set_ylabel("Annual median NBR")
    ax.set_title("Five palm pixels: each dotted line is the detected clearing year",
                 loc="left", fontsize=10)
    return fig


def products():
    return [
        {"kind": "map", "name": "ch44-age", "image": age.clip(aoi), "region": aoi,
         "vis": {"min": 0, "max": 33, "palette": ["ffffcc", "a1dab4", "41b6c4", "2c7fb8",
                                                   "253494"]},
         "legend": "Estimated oil palm age in 2023 (years)",
         "title": "Oil palm age, Kotawaringin Timur",
         "source": "Landsat 5/7/8/9 C2; Descals et al. 2021 oil palm map. GEE.",
         "caption": "Age of each oil palm pixel from the year of its deepest NBR dip. "
                    "Whole blocks share an age, as plantations are planted block by block."},
        {"kind": "chart", "name": "ch44-series", "data": series_frame, "plot": plot_series,
         "caption": "The signal behind the map: yearly NBR of five palm pixels, with the "
                    "detected clearing year."},
        {"kind": "chart", "name": "ch44-height", "data": pairs, "plot": plot_height,
         "caption": "GEDI height against estimated age, an independent check: a wrong "
                    "age would scatter, not climb."},
        {"kind": "table", "name": "ch44-stages", "data": stage_table,
         "floatfmt": ("", ",.0f", ".0%"),
         "caption": "Area in each life stage. Productivity follows these stages: none "
                    "while immature, rising while young, highest in the prime years, then "
                    "declining as palms grow too tall to harvest well."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(stage_table())
