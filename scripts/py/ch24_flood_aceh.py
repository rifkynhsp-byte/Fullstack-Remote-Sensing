#| title: Flood: terrain first, then the event, then who was exposed (Python)
#| description: The same HAND, Sentinel-1 flood extent and exposure count as the JavaScript tab, in Python.

"""
CHAPTER 24 | The November 2025 Sumatra floods in Aceh Tamiang: terrain
(HAND), Sentinel-1 flood extent, and buildings and people inside it.
"""

import ee
import math
import matplotlib.pyplot as plt
import numpy as np

district = (ee.FeatureCollection("FAO/GAUL/2025/level2")
            .filter(ee.Filter.eq("GAUL2_NAME", "Aceh Tamiang")))
aoi = district.geometry()
CONFIG = {"water_threshold": -13.0, "change_ratio": 1.25, "slope_max": 5}

# STEP 1. Terrain
hydro = ee.Image("MERIT/Hydro/v1_0_1")
hand = hydro.select("hnd").clip(aoi)
rivers = hydro.select("upa").gt(100).selfMask().clip(aoi)
slope = ee.Terrain.slope(ee.Image("NASA/NASADEM_HGT/001").select("elevation"))

# STEP 2. The event
s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(aoi)
      .filter(ee.Filter.eq("instrumentMode", "IW"))
      .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING")).select("VV"))


def smooth(img):
    return img.focal_median(50, "circle", "meters")


baseline = smooth(s1.filterDate("2025-09-01", "2025-10-31").median())
flooded = smooth(s1.filterDate("2025-11-26", "2025-11-30").mosaic())
permanent = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gt(80)
drop_db = 10 * math.log10(CONFIG["change_ratio"])      # 1.25x darker = 0.97 dB
flood = (flooded.lt(CONFIG["water_threshold"])
         .And(baseline.subtract(flooded).gt(drop_db))
         .And(slope.lt(CONFIG["slope_max"]))
         .And(permanent.unmask(0).Not())
         .selfMask().clip(aoi).rename("flood"))

# STEP 3. Exposure
# Check a footprint layer's coverage before trusting it. Here Google Open
# Buildings v3 holds about 500 footprints for the whole district; Microsoft's
# footprints (seven tiles for Indonesia) hold about 60,000.
open_buildings = (ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
                  .filterBounds(aoi))
buildings = ee.FeatureCollection([
    ee.FeatureCollection(f"projects/sat-io/open-datasets/MSBuildings/Indonesia/indonesia_{i}")
    .filterBounds(aoi) for i in range(1, 8)]).flatten()
worldpop = (ee.ImageCollection("WorldPop/GP/100m/pop")
            .filter(ee.Filter.eq("country", "IDN")).filter(ee.Filter.eq("year", 2020)))
people = worldpop.mosaic().setDefaultProjection(worldpop.first().projection())

flood_km2 = (flood.multiply(ee.Image.pixelArea()).divide(1e6)
             .reduceRegion(reducer=ee.Reducer.sum(), geometry=aoi, scale=20,
                           maxPixels=1e10, tileScale=8).get("flood"))
flooded_buildings = (flood.unmask(0).reduceRegions(
    collection=buildings.map(lambda b: ee.Feature(b.geometry().centroid(1))),
    reducer=ee.Reducer.first(), scale=20, tileScale=8)
    .filter(ee.Filter.eq("first", 1)).size())
share = (flood.unmask(0).reproject(ee.Projection("EPSG:32647").atScale(20))
         .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=64)
         .reproject(people.projection()))
flooded_people = (people.updateMask(share.gt(0.5))
                  .reduceRegion(reducer=ee.Reducer.sum(), geometry=aoi, scale=100,
                                maxPixels=1e10).values().get(0))
def exposure_frame():
    """Count flooded buildings one Microsoft tile at a time, then add up locally.

    One request over all ~60,000 footprints times out interactively; seven
    smaller requests do not. (In the Code Editor, export the count instead.)
    """
    import pandas as pd
    n_flooded = 0
    for i in range(1, 8):
        tile = (ee.FeatureCollection(
            f"projects/sat-io/open-datasets/MSBuildings/Indonesia/indonesia_{i}")
            .filterBounds(aoi))
        n_flooded += (flood.unmask(0).reduceRegions(
            collection=tile.map(lambda b: ee.Feature(b.geometry().centroid(1))),
            reducer=ee.Reducer.first(), scale=20, tileScale=8)
            .filter(ee.Filter.eq("first", 1)).size().getInfo())
    rest = ee.Dictionary({"flood_km2": flood_km2, "people_in_flood": flooded_people,
                          "buildings_in_district_microsoft": buildings.size(),
                          "buildings_in_district_open_buildings_v3": open_buildings.size()
                          }).getInfo()
    return pd.DataFrame([{**rest, "buildings_in_flood": n_flooded}])


exposure = ee.Dictionary({"flood_km2": flood_km2, "buildings_in_flood": flooded_buildings,
                          "people_in_flood": flooded_people,
                          "buildings_in_district_microsoft": buildings.size(),
                          "buildings_in_district_open_buildings_v3": open_buildings.size()})

# Where on the terrain did the water sit? HAND inside the flood vs the district.
hand_samples = (hand.rename("HAND").addBands(flood.unmask(0))
                .stratifiedSample(numPoints=800, classBand="flood", region=aoi, scale=90,
                                  seed=4, tileScale=4))

relief = ee.Terrain.hillshade(ee.Image("NASA/NASADEM_HGT/001").select("elevation")).clip(aoi)
flood_map = (relief.visualize(min=120, max=255)
             .blend(hand.lt(5).selfMask().visualize(palette=["c6dbef"], opacity=0.5))
             .blend(rivers.visualize(palette=["08306b"]))
             .blend(flood.visualize(palette=["00b4ff"]))
             .blend(ee.Image().byte().paint(district, 1, 1).visualize(palette=["000000"])))


def plot_hand(df):
    """HAND of flooded pixels against the district as a whole."""
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    bins = np.arange(0, 41, 1)
    ax.hist(df.loc[df["flood"] == 0, "HAND"].clip(0, 40), bins=bins, density=True,
            alpha=0.6, color="#9aa5b1", label="district")
    ax.hist(df.loc[df["flood"] == 1, "HAND"].clip(0, 40), bins=bins, density=True,
            alpha=0.7, color="#00b4ff", label="flooded, 26-30 Nov 2025")
    ax.set_xlabel("Height above nearest drainage (m)")
    ax.set_ylabel("Density")
    ax.set_title("The water went where the terrain said it would", loc="left")
    ax.legend(frameon=False, fontsize=8)
    return fig


def products():
    src = "Sentinel-1 GRD, MERIT Hydro, NASADEM, JRC GSW, MS Building Footprints, WorldPop. GEE."
    return [
        {"kind": "map", "name": "ch24-flood-map", "image": flood_map, "region": aoi.bounds(),
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "classes": [("flood, 26-30 Nov 2025", "#00b4ff"), ("HAND < 5 m", "#c6dbef"),
                     ("rivers > 100 km²", "#08306b")],
         "title": "Aceh Tamiang, late November 2025", "source": src,
         "caption": "Radar flood extent over relief, with the low terrain (HAND under 5 m) "
                    "that terrain alone would have flagged beforehand."},
        {"kind": "chart", "name": "ch24-flood-hand", "data": hand_samples, "plot": plot_hand,
         "caption": "HAND at 800 flooded and 800 unflooded points (values above 40 m "
                    "are gathered in the last bar). If the flood sat high on the terrain, "
                    "the radar rule would be suspect."},
        {"kind": "table", "name": "ch24-exposure", "data": exposure_frame,
         "columns": ["flood_km2", "buildings_in_flood", "people_in_flood",
                     "buildings_in_district_microsoft",
                     "buildings_in_district_open_buildings_v3"],
         "floatfmt": ",.0f",
         "caption": "Extent and exposure from one post-event pass. If WorldPop and the "
                    "footprints disagree, report both and say why. With Microsoft "
                    "building footprints and WorldPop 2020. The last column is why: Google "
                    "Open Buildings v3 barely covers this district. A first estimate for "
                    "response planning, not a damage assessment."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(exposure.getInfo())
