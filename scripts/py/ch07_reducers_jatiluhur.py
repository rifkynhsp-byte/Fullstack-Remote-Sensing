#| title: Images, collections and reducers on a real reservoir (Python)
#| description: The same analysis as the JavaScript tab, run from Python.

"""
CHAPTER 7 | map(), three reductions, and a region reduced to a number, in
Python. Jatiluhur reservoir, West Java.
"""

import ee
import matplotlib.pyplot as plt

jatiluhur = ee.Geometry.Rectangle([107.348, -6.986, 107.506, -6.871])


# STEP 1. One function for one image
def prepare(image):
    qa = image.select("QA_PIXEL")
    clear = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
    sr = image.select("SR_B.").multiply(0.0000275).add(-0.2)
    ndvi = sr.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")
    mndwi = sr.normalizedDifference(["SR_B3", "SR_B6"]).rename("MNDWI")
    return (sr.addBands([ndvi, mndwi]).updateMask(clear)
            .copyProperties(image, ["system:time_start"]))


landsat = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
           .filterBounds(jatiluhur).map(prepare))

# STEP 2. Three reductions of the same collection
year2019 = landsat.filterDate("2019-01-01", "2020-01-01")
median = year2019.median()
greenest = year2019.qualityMosaic("NDVI")
rgb = {"bands": ["SR_B4", "SR_B3", "SR_B2"], "min": 0, "max": 0.25}


# STEP 3. Water area each dry season
def water_area(year):
    start, end = ee.Date.fromYMD(year, 7, 1), ee.Date.fromYMD(year, 10, 31)
    dry = landsat.filterDate(start, end)
    water = dry.median().select("MNDWI").gt(0)
    km2 = (water.multiply(ee.Image.pixelArea()).divide(1e6)
           .reduceRegion(reducer=ee.Reducer.sum(), geometry=jatiluhur,
                         scale=30, maxPixels=1e9).get("MNDWI"))
    return ee.Feature(None, {"year": year, "water_km2": km2, "scenes": dry.size()})


areas = ee.FeatureCollection(ee.List.sequence(2014, 2024).map(water_area))


def plot_water_area(df):
    """Dry season water area by year. Which years stand out, and why?"""
    df = df.sort_values("year")
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.plot(df["year"], df["water_km2"], marker="o", color="#1A5BAB")
    ax.fill_between(df["year"], df["water_km2"], df["water_km2"].min() * 0.95,
                    color="#1A5BAB", alpha=0.1)
    for _, r in df.iterrows():
        ax.text(r["year"], r["water_km2"], f"{r['water_km2']:.0f}", ha="center",
                va="bottom", fontsize=7)
    ax.set_xticks(df["year"])
    ax.set_ylabel("Water area (km²)")
    ax.set_title("Jatiluhur in the dry season, 2014 to 2024", loc="left")
    return fig


def products():
    src = "Landsat 8 Collection 2 Level 2 (USGS). Google Earth Engine."
    return [
        {"kind": "map", "name": "ch07-median", "image": median, "vis": rgb,
         "region": jatiluhur, "title": "Median of 2019, every band separately",
         "source": src,
         "caption": "The per-band median of every clear 2019 observation over Jatiluhur."},
        {"kind": "map", "name": "ch07-greenest", "image": greenest, "vis": rgb,
         "region": jatiluhur, "title": "Greenest pixel of 2019 (qualityMosaic)",
         "source": src,
         "caption": "The same year reduced by keeping, at each pixel, the whole "
                    "observation with the highest NDVI. The reservoir edge moves because "
                    "the greenest date is a different date for every pixel."},
        {"kind": "map", "name": "ch07-water2019",
         "image": median.select("MNDWI").gt(0).selfMask(), "vis": {"palette": ["1A5BAB"]},
         "region": jatiluhur, "classes": [("water, MNDWI > 0", "#1A5BAB")],
         "title": "Water in 2019", "source": src,
         "caption": "The water mask that the reducer below turns into square kilometres."},
        {"kind": "chart", "name": "ch07-water-area", "data": areas,
         "plot": plot_water_area,
         "caption": "Water area inside the rectangle, July to October median of each "
                    "year. One reduceRegion call per year."},
        {"kind": "table", "name": "ch07-water-table", "data": areas,
         "columns": ["year", "water_km2", "scenes"], "floatfmt": (".0f", ".1f", ".0f"),
         "caption": "The numbers behind the chart, with the scene count behind each median."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(areas.getInfo())
