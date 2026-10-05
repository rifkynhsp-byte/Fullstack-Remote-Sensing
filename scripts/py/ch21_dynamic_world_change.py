#| title: Change through time with Dynamic World (Python)
#| description: The same yearly count and change map as the JavaScript tab, in Python.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 21 | Dynamic World in Python: a confidence-shaded map, built-up area
year by year, and where new built-up land appeared since 2017.
"""

import ee
import matplotlib.pyplot as plt
import pandas as pd

area = ee.Geometry.Rectangle([105.16, -4.10, 105.28, -4.02])   # GEE101 Lampung area
CLASSES = ["water", "trees", "grass", "flooded_vegetation", "crops",
           "shrub_and_scrub", "built", "bare", "snow_and_ice"]
BUILT = CLASSES.index("built")   # 6, not 2: 2 is grass
PALETTE = ["419BDF", "397D49", "88B053", "7A87C6", "E49635", "DFC35A", "C4281B",
           "A59B8F", "B39FE1"]

dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(area)


def year_composite(year):
    yr = dw.filterDate(ee.Date.fromYMD(year, 1, 1), ee.Date.fromYMD(year + 1, 1, 1))
    label = yr.select("label").reduce(ee.Reducer.mode()).rename("label")
    confidence = yr.select(CLASSES).mean().reduce(ee.Reducer.max()).rename("confidence")
    return label.addBands(confidence).set("year", year)


y2024 = year_composite(2024)
shaded = (y2024.select("label").visualize(min=0, max=8, palette=PALETTE).divide(255)
          .multiply(ee.Terrain.hillshade(
              # a composite has no fixed grid; terrain operators need one (10 m UTM 48S)
              y2024.select("confidence").multiply(100)
              .setDefaultProjection(ee.Projection("EPSG:32748").atScale(10))).divide(255)))


def built_km2(year):
    c = year_composite(year)
    km2 = (c.select("label").eq(BUILT).multiply(ee.Image.pixelArea()).divide(1e6)
           .reduceRegion(reducer=ee.Reducer.sum(), geometry=area, scale=10, maxPixels=1e9)
           .get("label"))
    yr = dw.filterDate(ee.Date.fromYMD(year, 1, 1), ee.Date.fromYMD(year + 1, 1, 1))
    # The steadier alternative: average the 'built' probability over the year
    # and call a pixel built when that average passes one half.
    km2_prob = (yr.select("built").mean().gt(0.5).multiply(ee.Image.pixelArea()).divide(1e6)
                .reduceRegion(reducer=ee.Reducer.sum(), geometry=area, scale=10,
                              maxPixels=1e9).get("built"))
    return ee.Feature(None, {"year": year, "built_km2": km2, "built_km2_prob": km2_prob,
                             "scenes": yr.size()})


_series = []


def series():
    """One year per request: asking for all nine years at once overloads Earth Engine
    ("Too many concurrent aggregations")."""
    if not _series:
        for y in range(2016, 2025):
            _series.append(built_km2(y).getInfo()["properties"])
    return pd.DataFrame(_series)
new_built = (year_composite(2024).select("label").eq(BUILT)
             .And(year_composite(2017).select("label").neq(BUILT)))
change_map = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(area)
              .filterDate("2024-05-01", "2024-10-31")
              .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30)).median()
              .visualize(bands=["B4", "B3", "B2"], min=200, max=2200)
              .blend(new_built.selfMask().visualize(palette=["ff00ff"], opacity=0.8)))


def plot_built_series(df):
    """Built-up area by year, with the number of scenes behind each year."""
    df = df.sort_values("year")
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.plot(df["year"], df["built_km2"], marker="o", color="#C4281B", label="yearly mode label")
    ax.plot(df["year"], df["built_km2_prob"], marker="s", color="#6a51a3",
            label="mean 'built' probability > 0.5")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_ylabel("Built-up area (km²)", color="#C4281B")
    ax2 = ax.twinx()
    ax2.bar(df["year"], df["scenes"], color="#9aa5b1", alpha=0.35, width=0.6)
    ax2.set_ylabel("Scenes in the year", color="#616e7c")
    ax2.spines["right"].set_visible(True)
    ax.set_zorder(ax2.get_zorder() + 1)
    ax.patch.set_visible(False)
    ax.set_xticks(df["year"])
    ax.set_title("Built-up land, Dynamic World yearly mode", loc="left")
    return fig


def products():
    src = "Dynamic World V1 (Google, WRI), Sentinel-2. GEE."
    legend = [(n.replace("_", " "), "#" + c) for n, c in zip(CLASSES[:8], PALETTE[:8])]
    return [
        {"kind": "map", "name": "ch21-dw-2024", "image": shaded, "region": area,
         "vis": {"min": 0, "max": 0.8}, "classes": legend,
         "title": "Dynamic World 2024, shaded by confidence", "source": src,
         "caption": "The most frequent Dynamic World label of 2024, with relief drawn from "
                    "the model's confidence: flat, dull areas are where it hesitated."},
        {"kind": "map", "name": "ch21-new-built", "image": change_map, "region": area,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "classes": [("built in 2024, not in 2017", "#ff00ff")],
         "title": "New built-up land since 2017", "source": src,
         "caption": "Magenta: labelled built in 2024 but not in 2017, over a 2024 "
                    "Sentinel-2 composite."},
        {"kind": "chart", "name": "ch21-built-series", "data": series,
         "plot": plot_built_series,
         "caption": ("Built-up area per year two ways, with the scene count behind each year. The probability rule is stricter, so its numbers are lower, but it is not steadier: both series dip in 2020 and 2022. Nothing was demolished; the dips come from the data. A single year here is not a result. Report a multi-year window, or a trend with its uncertainty.")},
        {"kind": "table", "name": "ch21-built-table", "data": series,
         "columns": ["year", "built_km2", "built_km2_prob", "scenes"],
         "floatfmt": (".0f", ".2f", ".2f", ".0f"),
         "caption": "The yearly numbers."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(series())
