#| title: A chart over time and a time-lapse (Python)
#| description: The same chart and animation as the JavaScript tab, run from Python.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 13 | NDVI through time at one Bandung point, and an animated GIF of
the IKN core zone, 2019 to 2024, in Python.
"""

import ee
import matplotlib.pyplot as plt
import pandas as pd

point = ee.Geometry.Point([107.6262, -6.9230])   # Bandung


def add_ndvi(image):
    qa = image.select("QA_PIXEL")
    clear = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
    sr = image.select(["SR_B4", "SR_B5"]).multiply(0.0000275).add(-0.2)
    return (sr.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")
            .updateMask(clear).copyProperties(image, ["system:time_start"]))


ndvi_series = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
               .filterBounds(point).filterDate("2013-04-01", "2025-01-01")
               .map(add_ndvi))

# ui.Chart.image.series in Python: sample every image at the point
series = ee.FeatureCollection(ndvi_series.map(lambda im: ee.Feature(None, {
    "date": im.date().format("YYYY-MM-dd"),
    "NDVI": im.reduceRegion(ee.Reducer.first(), point, 30).get("NDVI"),
}))).filter(ee.Filter.notNull(["NDVI"]))


def plot_ndvi_series(df):
    """Every clear observation, plus a 90-day rolling median to show the rhythm."""
    df = df.assign(date=pd.to_datetime(df["date"])).sort_values("date")
    smooth = df.set_index("date")["NDVI"].rolling("90D").median()
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    ax.scatter(df["date"], df["NDVI"], s=8, color="#74A901", alpha=0.6,
               label="clear observations")
    ax.plot(smooth.index, smooth.values, color="#056201", lw=1.5, label="90-day median")
    ax.set_ylabel("NDVI")
    ax.set_title("NDVI over time, one Bandung pixel", loc="left")
    ax.legend(frameon=False, fontsize=8)
    return fig


# The time-lapse
ikn = ee.Geometry.Rectangle([116.66, -1.01, 116.75, -0.93])


def yearly_frame(year):
    def mask(image):
        scl = image.select("SCL")
        return image.updateMask(scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)))
    composite = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                 .filterBounds(ikn)
                 .filterDate(ee.Date.fromYMD(year, 5, 1), ee.Date.fromYMD(year, 10, 31))
                 .map(mask).median())
    return (composite.visualize(bands=["B4", "B3", "B2"], min=200, max=2200, gamma=1.2)
            .set("year", year))


YEARS = list(range(2019, 2025))
frame_list = [yearly_frame(y) for y in YEARS]
frames = ee.ImageCollection(frame_list)

# frames.getVideoThumbURL(...) is the one-line route, and over this area it
# fails with "User memory limit exceeded": six medians are computed in one
# request. Asking for each frame separately and stitching the GIF in Python
# stays under the limit. That trade, one big request against many small
# ones, comes up again in chapter “Statistics and Modelling You Actually Need”.


def products():
    return [
        {"kind": "chart", "name": "ch13-ndvi-series", "data": series,
         "plot": plot_ndvi_series,
         "caption": "Every clear Landsat 8 observation at one Bandung pixel since 2013. "
                    "The gaps are cloud; the rolling median is the pattern a reader "
                    "should take away."},
        {"kind": "animation", "name": "ch13-ikn-timelapse", "frames": frame_list,
         "region": ikn, "labels": [f"IKN core zone, {y}" for y in YEARS], "fps": 1,
         "caption": "One cloud-masked Sentinel-2 composite per year (May to October), "
                    "2019 to 2024: the Nusantara capital core zone in East Kalimantan. "
                    "The bare patches in 2019 are harvested plantation blocks, not "
                    "construction; the road grid and core buildings appear from 2022."},
        {"kind": "map", "name": "ch13-ikn-2024", "image": frame_list[-1],
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "region": ikn, "title": "IKN core zone, 2024",
         "source": "Sentinel-2 SR Harmonized, May to October 2024. GEE.",
         "caption": "The last frame as a map, with coordinates and a scale bar."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(series.size().getInfo())
