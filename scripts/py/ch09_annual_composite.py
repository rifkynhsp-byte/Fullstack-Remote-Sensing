#| title: A cloud free annual composite (Python)
#| description: The same analysis as the JavaScript tab, run from Python.

"""
CHAPTER 9 | From a stack of cloudy scenes to one clean image, in Python

Line for line the same recipe as the JavaScript version. Run it in Colab or
locally after `pip install earthengine-api matplotlib pandas`:

    import ee
    ee.Authenticate()
    ee.Initialize(project="your-cloud-project")

The map, chart and table under this listing were produced by this file.
"""

import ee
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# STEP 1. Area of interest and raw collection
# ---------------------------------------------------------------------------
aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60])   # Mahakam Delta

s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
      .filterDate("2023-01-01", "2023-12-31")
      .filterBounds(aoi))


# ---------------------------------------------------------------------------
# STEP 2. One function, applied to every scene
# ---------------------------------------------------------------------------
def mask_clouds_and_add_indices(image):
    scl = image.select("SCL")
    clear = (scl.neq(3)          # not cloud shadow
             .And(scl.neq(8))    # not medium probability cloud
             .And(scl.neq(9))    # not high probability cloud
             .And(scl.neq(10))   # not thin cirrus
             .And(scl.neq(11)))  # not snow or ice
    ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndwi = image.normalizedDifference(["B3", "B8"]).rename("NDWI")
    # Add the indices FIRST, then mask: addBands() keeps each new band's own
    # mask, so masking first would leave NDVI and NDWI full of cloud.
    return image.addBands(ndvi).addBands(ndwi).updateMask(clear)


# ---------------------------------------------------------------------------
# STEPS 3 and 4. Map over the archive, then reduce to one image
# ---------------------------------------------------------------------------
processed = s2.map(mask_clouds_and_add_indices)
annual_composite = processed.median().clip(aoi)

# ---------------------------------------------------------------------------
# STEP 5. Visualisation parameters, the same numbers as the JavaScript
# ---------------------------------------------------------------------------
vis_true_colour = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000, "gamma": 1.4}
vis_ndvi = {"bands": ["NDVI"], "min": -0.5, "max": 1,
            "palette": ["AF963C", "F6E652", "0C6316", "023E0A"]}
vis_ndwi = {"bands": ["NDWI"], "min": -0.5, "max": 0.5,
            "palette": ["E9DEB5", "FFFFFF", "8ED2E5", "0047AB"]}

# ---------------------------------------------------------------------------
# STEP 7. How much clear sky did each pixel actually get?
# ---------------------------------------------------------------------------
clear_count = processed.select("B4").count().rename("clear_obs").clip(aoi)
vis_count = {"min": 0, "max": 40,
             "palette": ["b2182b", "f4a582", "f7f7f7", "92c5de", "2166ac"]}


def month_feature(m):
    in_month = s2.filter(ee.Filter.calendarRange(m, m, "month"))
    return ee.Feature(None, {
        "month": m,
        "scenes": in_month.size(),
        "mean_cloud_pct": in_month.aggregate_mean("CLOUDY_PIXEL_PERCENTAGE"),
    })


monthly = ee.FeatureCollection(ee.List.sequence(1, 12).map(month_feature))

count_summary = clear_count.reduceRegion(
    reducer=ee.Reducer.minMax().combine(ee.Reducer.median(), "", True),
    geometry=aoi, scale=100, maxPixels=1e9, bestEffort=True)


def plot_monthly_cloud(df):
    """Mean scene cloud cover by month. Change the colour or the threshold line."""
    df = df.sort_values("month")
    fig, ax = plt.subplots(figsize=(7, 3.2))
    bars = ax.bar(df["month"], df["mean_cloud_pct"], color="#5b8db8")
    ax.axhline(50, color="#b2182b", lw=1, ls="--", label="half the scene cloudy")
    for bar, n in zip(bars, df["scenes"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"n={int(n)}", ha="center", fontsize=7)
    ax.set_xticks(range(1, 13))
    ax.set_xlabel("Month (2023)")
    ax.set_ylabel("Mean scene cloud cover (%)")
    ax.set_title("Mahakam Delta: how cloudy is each month?", loc="left")
    ax.legend(frameon=False, fontsize=8)
    return fig


# ---------------------------------------------------------------------------
# What the book shows under this listing
# ---------------------------------------------------------------------------
def products():
    return [
        {"kind": "map", "name": "ch09-truecolour", "image": annual_composite,
         "vis": vis_true_colour, "region": aoi,
         "title": "Annual median composite, 2023, true colour",
         "caption": "Every clear pixel of 2023, reduced to one image by the median. "
                    "No single scene of the delta looks like this.",
         "source": "Sentinel-2 SR Harmonized (Copernicus), 2023. Google Earth Engine."},
        {"kind": "map", "name": "ch09-ndvi", "image": annual_composite,
         "vis": vis_ndvi, "region": aoi, "legend": "NDVI",
         "title": "Annual NDVI",
         "caption": "NDVI from the same composite: the vegetated delta is green, the "
                    "sea and river plumes sit near zero. Inside the forest the colour "
                    "barely changes, the saturation Chapter 12 takes on.",
         "source": "Sentinel-2 SR Harmonized, 2023."},
        {"kind": "map", "name": "ch09-ndwi", "image": annual_composite,
         "vis": vis_ndwi, "region": aoi, "legend": "NDWI",
         "title": "Annual NDWI",
         "caption": "NDWI. Aquaculture ponds and river channels stand out; the "
                    "vegetated delta sits below zero.",
         "source": "Sentinel-2 SR Harmonized, 2023."},
        {"kind": "map", "name": "ch09-clear-count", "image": clear_count,
         "vis": vis_count, "region": aoi, "legend": "Clear observations in 2023",
         "title": "How many clear looks built each pixel",
         "caption": "Clear observations per pixel after masking. Red pixels were "
                    "assembled from very few looks and deserve less trust. The dark "
                    "blue band is not clearer sky: it is where two Sentinel-2 tiles "
                    "overlap, so every date is counted twice. Check for this before "
                    "you report a count.",
         "source": "Sentinel-2 SCL mask, 2023."},
        {"kind": "chart", "name": "ch09-monthly-cloud", "data": monthly,
         "plot": plot_monthly_cloud,
         "caption": "Mean scene cloud cover by month, from metadata alone. "
                    "n is the number of scenes that month."},
        {"kind": "table", "name": "ch09-count-summary", "data": count_summary,
         "caption": "Clear observations per pixel across the delta (100 m sample)."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print("Scenes available:", s2.size().getInfo())
    print("Clear observations per pixel:", count_summary.getInfo())
    import pandas as pd
    plot_monthly_cloud(pd.DataFrame(monthly.getInfo()["features"])
                       .pipe(lambda d: pd.DataFrame(list(d["properties"]))))
    plt.show()
