#| title: Radar water through the seasons, middle Mahakam (Python)
#| description: The same water frequency map and monthly series as the JavaScript tab, in Python.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 10 | Sentinel-1 water frequency and monthly flooded area over the
middle Mahakam floodplain, 2017 to 2024 (GEE101 study area).
"""

import ee
import matplotlib.pyplot as plt
import pandas as pd

roi = ee.Geometry.Polygon([[[115.988, -0.083], [117.020, -0.203],
                            [117.285, 0.919], [116.269, 1.114]]])

s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(roi)
      .filterDate("2017-01-01", "2025-01-01")
      .filter(ee.Filter.eq("instrumentMode", "IW"))
      .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
      .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
      .select("VV"))

THRESHOLD = -13
water = s1.map(lambda img: img.focal_median(100, "circle", "meters").lt(THRESHOLD)
               .rename("water").copyProperties(img, ["system:time_start"]))
frequency = water.mean().clip(roi)


def month_feature(i):
    start = ee.Date("2017-01-01").advance(i, "month")
    m = water.filterDate(start, start.advance(1, "month"))
    km2 = (m.max().multiply(ee.Image.pixelArea()).divide(1e6)
           .reduceRegion(reducer=ee.Reducer.sum(), geometry=roi, scale=100,
                         maxPixels=1e10, tileScale=4).get("water"))
    return ee.Feature(None, {"month": start.format("YYYY-MM"), "water_km2": km2,
                             "passes": m.size()})


monthly = (ee.FeatureCollection(ee.List.sequence(0, 95).map(month_feature))
           .filter(ee.Filter.gt("passes", 0)))


def monthly_frame():
    """Ask for one year at a time.

    Asking for all 96 monthly sums in one request fails with "Too many
    concurrent aggregations". Twelve at a time succeeds. This batching is
    trivial in Python and awkward in the Code Editor.
    """
    frames = []
    for year in range(8):
        batch = (ee.FeatureCollection(ee.List.sequence(12 * year, 12 * year + 11)
                                      .map(month_feature))
                 .filter(ee.Filter.gt("passes", 0)))
        frames.append(pd.DataFrame([f["properties"] for f in batch.getInfo()["features"]]))
    return pd.concat(frames, ignore_index=True)


def plot_monthly_water(df):
    """Monthly maximum water extent. Find the wet seasons, and the dry years."""
    df = df.assign(month=pd.to_datetime(df["month"])).sort_values("month")
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.plot(df["month"], df["water_km2"], color="#2171b5", lw=1)
    ax.fill_between(df["month"], df["water_km2"], df["water_km2"].min(),
                    color="#2171b5", alpha=0.15)
    ax.set_ylabel("Water extent (km²)")
    ax.set_title("Middle Mahakam floodplain, Sentinel-1 descending, VV < −13 dB",
                 loc="left", fontsize=9)
    return fig


def plot_month_of_year(df):
    """The average year: which months flood?"""
    df = df.assign(m=pd.to_datetime(df["month"]).dt.month)
    g = df.groupby("m")["water_km2"]
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(g.median().index, g.median().values, color="#6baed6")
    ax.errorbar(g.median().index, g.median().values,
                yerr=[g.median() - g.quantile(0.1), g.quantile(0.9) - g.median()],
                fmt="none", color="#08306b", lw=1)
    ax.set_xticks(range(1, 13))
    ax.set_xlabel("Month")
    ax.set_ylabel("Water extent (km²)")
    ax.set_title("Median year, with 10th to 90th percentile", loc="left", fontsize=9)
    return fig


def products():
    return [
        {"kind": "map", "name": "ch10-water-frequency", "image": frequency, "region": roi,
         "vis": {"min": 0, "max": 1,
                 "palette": ["ffffff", "c6dbef", "6baed6", "2171b5", "08306b"]},
         "legend": "Share of Sentinel-1 passes classed as water, 2017 to 2024",
         "title": "How often is it water?",
         "source": "Sentinel-1 GRD (Copernicus), descending, VV. GEE.",
         "caption": "Water frequency across 2017 to 2024. Dark blue is permanent water; "
                    "the pale fringes are the floodplain that comes and goes."},
        {"kind": "chart", "name": "ch10-water-monthly", "data": monthly_frame,
         "plot": plot_monthly_water,
         "caption": "Monthly maximum water extent, 2017 to 2024. Look for the wet "
                    "seasons and the dry years; optical sensors would see most of these "
                    "months as cloud."},
        {"kind": "chart", "name": "ch10-water-season", "data": monthly_frame,
         "plot": plot_month_of_year,
         "caption": "The same data folded into one year: the flood season and how much "
                    "it varies between years."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(monthly.limit(5).getInfo())
