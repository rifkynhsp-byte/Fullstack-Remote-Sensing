#!/usr/bin/env python3
"""
produce_maps.py
===============

The Python equivalent of the Earth Engine scripts in this book, written to
produce the REAL maps that the figures in images/ deliberately do not.

Why this file exists
--------------------
Every figure in images/ is a diagram: computed from published reference values
or from a synthetic pattern, and honest about that in its caption. None of
them contains a real satellite pixel.

Real maps of your own study area have to come from Earth Engine with your own
credentials. This script does that, and exports PNG files straight into
images/ so they can be referenced from a chapter like any other figure.

Run it in Google Colab
----------------------
    !pip install earthengine-api geemap -q
    import ee
    ee.Authenticate()

then paste this file into a cell, set PROJECT and AOI, and run.

Run it locally
--------------
    pip install earthengine-api geemap
    earthengine authenticate
    python3 notebooks/produce_maps.py

What it produces
----------------
    images/map-composite-truecolour.png    annual cloud free composite
    images/map-composite-falsecolour.png   the same scene, B8 B4 B3
    images/map-ndvi.png                    NDVI with the book's palette
    images/map-mndwi.png                   MNDWI, water against wet vegetation
    images/map-radar-vh.png                Sentinel-1 VH, speckle filtered
    images/map-elevation.png               ALOS AW3D30 with the intertidal band

Each one is the direct output of the corresponding chapter's JavaScript, so a
reader can compare what they get against what the book shows.
"""

from pathlib import Path

import ee
import geemap

# ---------------------------------------------------------------------------
# CONFIGURE THIS
# ---------------------------------------------------------------------------
PROJECT = "your-cloud-project"          # from Settings, API in the Cloud console
YEAR = 2023

# Mahakam Delta by default. Replace with your own study area, longitude first.
AOI = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60])

OUT = Path(__file__).resolve().parents[1] / "images"
OUT.mkdir(exist_ok=True)

# Figure size in pixels. 1600 wide keeps text sharp on high density screens
# without producing a file that slows the page down. See images/README.md.
WIDTH = 1600


def initialise():
    try:
        ee.Initialize(project=PROJECT)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=PROJECT)
    print("Earth Engine ready")


# ---------------------------------------------------------------------------
# The same logic as scripts/en/ch09_annual_composite.js, in Python
# ---------------------------------------------------------------------------
def mask_and_index(image):
    """Cloud mask from the Scene Classification Layer, then add indices.

    Identical to the JavaScript version, including the SCL classes excluded
    and the division by 10000. Chapter 9 explains each choice.
    """
    scl = image.select("SCL")
    clear = (scl.neq(3)          # cloud shadow
             .And(scl.neq(8))    # medium probability cloud
             .And(scl.neq(9))    # high probability cloud
             .And(scl.neq(10))   # thin cirrus
             .And(scl.neq(11)))  # snow, which Sen2Cor assigns to bright sand

    scaled = image.updateMask(clear).divide(10000)

    ndvi = scaled.normalizedDifference(["B8", "B4"]).rename("NDVI")
    mndwi = scaled.normalizedDifference(["B3", "B11"]).rename("MNDWI")

    return (scaled.addBands([ndvi, mndwi])
            .copyProperties(image, ["system:time_start"]))


def annual_composite(year, aoi):
    collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                  .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
                  .filterBounds(aoi)
                  .map(mask_and_index))
    print(f"  scenes contributing: {collection.size().getInfo()}")
    return collection.median().clip(aoi)


def radar_composite(year, aoi):
    """Sentinel-1 VH, speckle filtered. Chapter 10."""
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD")
          .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
          .filterBounds(aoi)
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          # Single orbit direction. Mixing ascending and descending adds a
          # geometric signal that has nothing to do with the ground.
          .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
          .select(["VH"]))
    print(f"  radar scenes: {s1.size().getInfo()}")
    return s1.median().focal_median(50, "circle", "meters").clip(aoi)


def terrain(aoi):
    """Elevation with the intertidal band highlighted. Chapter 11."""
    return ee.Image("JAXA/ALOS/AW3D30/V2_2").select("AVE_DSM").clip(aoi)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def export_png(image, vis, filename, aoi, caption):
    """Render a thumbnail and write it into images/.

    getThumbURL is used rather than a Drive export because it returns
    immediately. It is limited in size, which is fine for a figure and not
    for analysis. For anything you intend to analyse, export to an Asset.
    """
    path = OUT / filename
    url = image.visualize(**vis).getThumbURL({
        "region": aoi,
        "dimensions": WIDTH,
        "format": "png",
    })
    geemap.download_file(url, str(path), quiet=True)
    print(f"  wrote images/{filename}")
    print(f"     caption suggestion: {caption}")
    return path


def main():
    initialise()

    print(f"\nBuilding {YEAR} optical composite")
    composite = annual_composite(YEAR, AOI)

    export_png(
        composite, {"bands": ["B4", "B3", "B2"], "min": 0, "max": 0.3, "gamma": 1.4},
        "map-composite-truecolour.png", AOI,
        f"Annual median composite, {YEAR}, true colour. Assembled from every "
        f"clear observation in the year rather than from a single scene.")

    export_png(
        composite, {"bands": ["B8", "B4", "B3"], "min": 0, "max": 0.4, "gamma": 1.3},
        "map-composite-falsecolour.png", AOI,
        "The same composite in false colour infrared. Vegetation reads red "
        "because the near infrared band drives the red display channel.")

    export_png(
        composite, {"bands": ["NDVI"], "min": -0.2, "max": 0.9,
                    "palette": ["#AF963C", "#F6E652", "#0C6316", "#023E0A"]},
        "map-ndvi.png", AOI,
        "NDVI over the study area. Note how little variation there is inside "
        "the forest: this is the saturation described in Chapter 12.")

    export_png(
        composite, {"bands": ["MNDWI"], "min": -0.5, "max": 0.5,
                    "palette": ["#E9DEB5", "#FFFFFF", "#8ED2E5", "#0047AB"]},
        "map-mndwi.png", AOI,
        "MNDWI. Aquaculture ponds separate cleanly from vegetated ground.")

    print(f"\nBuilding {YEAR} radar composite")
    radar = radar_composite(YEAR, AOI)
    export_png(
        radar, {"bands": ["VH"], "min": -25, "max": -5},
        "map-radar-vh.png", AOI,
        "Sentinel-1 VH backscatter, speckle filtered with a 50 m focal median. "
        "Bright areas are volume scattering from canopy; near black is calm water.")

    print("\nBuilding terrain")
    dem = terrain(AOI)
    export_png(
        dem, {"min": 0, "max": 60,
              "palette": ["#2b83ba", "#abdda4", "#ffffbf", "#fdae61", "#d7191c"]},
        "map-elevation.png", AOI,
        "ALOS AW3D30 elevation. Remember this is a surface model: over tall "
        "mangrove it reports canopy top, not ground.")

    print("\nDone. Reference these from a chapter with, for example:")
    print("    ![Caption.](../images/map-composite-falsecolour.png){#fig-composite}")


if __name__ == "__main__":
    main()
