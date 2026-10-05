#| title: Finding and inspecting a scene (Python)
#| description: The same search as the JavaScript tab, run from Python.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 8 | Filter the archive, pick the clearest scene, look at it.

The JavaScript version prints to the Console and draws on the Map. In Python
the same numbers come back with .getInfo(), and pandas makes the list of
scenes something you can sort and plot.
"""

import ee
import matplotlib.pyplot as plt
import pandas as pd

aoi = ee.Geometry.Point([117.58, -0.84])   # Mahakam Delta, Indonesia
view = aoi.buffer(15000).bounds()          # the area drawn in the figure

s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")

filtered = (s2.filterDate("2023-01-01", "2023-12-01")
            .filterBounds(aoi)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 15)))

image = filtered.sort("CLOUDY_PIXEL_PERCENTAGE").first()
true_colour = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000, "gamma": 1.4}

# Every scene of the year, before the cloud filter
all_scenes = s2.filterDate("2023-01-01", "2023-12-31").filterBounds(aoi)
scene_table = ee.FeatureCollection(all_scenes.map(lambda im: ee.Feature(None, {
    "date": im.date().format("YYYY-MM-dd"),
    "cloud_pct": im.get("CLOUDY_PIXEL_PERCENTAGE"),
    "tile": im.get("MGRS_TILE"),
})))


def plot_scene_cloud(df):
    """One dot per scene. Move the threshold and count what survives."""
    threshold = 15
    df = df.assign(date=pd.to_datetime(df["date"])).sort_values("date")
    keep = df["cloud_pct"] < threshold
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    ax.scatter(df.loc[~keep, "date"], df.loc[~keep, "cloud_pct"], s=12,
               color="#9aa5b1", label="rejected")
    ax.scatter(df.loc[keep, "date"], df.loc[keep, "cloud_pct"], s=18,
               color="#2166ac", label=f"kept ({keep.sum()} of {len(df)})")
    ax.axhline(threshold, color="#b2182b", lw=1, ls="--")
    ax.set_ylabel("Scene cloud cover (%)")
    ax.set_title("Mahakam 2023: most of the year fails a 15 % filter", loc="left")
    ax.legend(frameon=False, fontsize=8)
    fig.autofmt_xdate()
    return fig


def products():
    return [
        {"kind": "map", "name": "ch08-clearest-scene", "image": image,
         "vis": true_colour, "region": view,
         "title": "The clearest Sentinel-2 scene of 2023",
         "source": "Sentinel-2 SR Harmonized (Copernicus). Google Earth Engine.",
         "caption": "The single least cloudy scene the filter found. Even this "
                    "one carries cloud: in the tropics, the best scene is rarely a clear one."},
        {"kind": "chart", "name": "ch08-scene-cloud", "data": scene_table,
         "plot": plot_scene_cloud,
         "caption": "Every 2023 scene over the point, cloud cover against date. "
                    "Grey scenes are the ones a 15 % filter throws away."},
        {"kind": "table", "name": "ch08-selected", "data": ee.Dictionary({
            "scene_id": image.get("system:index"),
            "date": image.date().format("YYYY-MM-dd"),
            "cloud_pct": image.get("CLOUDY_PIXEL_PERCENTAGE"),
            "scenes_passing_filter": filtered.size(),
            "scenes_in_year": all_scenes.size()}),
         "caption": "What the filter kept, and the scene it chose."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print("Scenes after filtering:", filtered.size().getInfo())
    print("Selected scene:", image.get("system:index").getInfo())
