#| title: Terrain and drainage (Python)
#| description: The same analysis as the JavaScript tab, run from Python.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 11 | Terrain and hydrological context, in Python

The same steps as the JavaScript version: DEM, a canopy corrected ground
estimate, slope, distance to water, the intertidal envelope, then drainage
(HAND and channels from MERIT Hydro) and a transect that shows where a surface
model is measuring trees instead of ground.
"""

import ee
import matplotlib.pyplot as plt

aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60])   # Mahakam Delta

# STEP 1-2. A surface model, and an estimate of the ground under the canopy
# AW3D30 v4.1 is a tiled collection: mosaic it and restore the native
# projection, or slope is computed on a 1 degree grid and comes out as zero.
aw3d = ee.ImageCollection("JAXA/ALOS/AW3D30/V4_1")
dem = (aw3d.select("DSM").filterBounds(aoi).mosaic()
       .setDefaultProjection(aw3d.first().projection()).clip(aoi))
canopy_height = (ee.Image("users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1")
                 .clip(aoi).rename("canopy_height"))
approx_ground = dem.subtract(canopy_height.unmask(0)).rename("ground_est")

# STEP 3. Slope, aspect, hillshade
terrain = ee.Terrain.products(dem)
slope = terrain.select("slope")

# STEP 4. Distance to permanent water (JRC occurrence > 80 %)
water = (ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence")
         .gt(80).selfMask())
distance_to_water = (water.fastDistanceTransform(neighborhood=512, units="pixels")
                     .sqrt().multiply(30).rename("dist_to_water").clip(aoi))

# STEP 5. The ecological rule: low, flat, near water
intertidal = (dem.lt(40).And(slope.lt(5)).And(distance_to_water.lt(5000))
              .rename("intertidal").clip(aoi))

# STEP 7. From terrain to drainage
hydro = ee.Image("MERIT/Hydro/v1_0_1").clip(aoi)
hand = hydro.select("hnd").rename("HAND")
channels = hydro.select("upa").gt(50).selfMask().rename("channel")


def area_within(metres):
    return (hand.lt(metres).multiply(ee.Image.pixelArea()).divide(1e6)
            .reduceRegion(reducer=ee.Reducer.sum(), geometry=aoi, scale=90,
                          maxPixels=1e10, bestEffort=True).get("HAND"))


hand_table = ee.FeatureCollection([
    ee.Feature(None, {"height_above_drainage": f"< {m} m",
                      "area_km2": area_within(m)}) for m in (1, 2, 5, 10)])

land = ee.Image("MERIT/Hydro/v1_0_1").select("hnd").mask()   # open sea is void
elevation_stats = dem.updateMask(land).reduceRegion(
    reducer=ee.Reducer.percentile([1, 50, 99]).combine(ee.Reducer.minMax(), "", True),
    geometry=aoi, scale=30, maxPixels=1e10, bestEffort=True)

# STEP 8. A transect across the delta
transect = ee.Geometry.LineString([[117.35, -0.70], [117.62, -0.78]])
profile = (dem.rename("surface").addBands(approx_ground)
           .addBands(ee.Image.pixelLonLat())
           .sample(region=transect, scale=30, geometries=False))


def plot_profile(df):
    """Surface model versus estimated ground along the transect.

    Faint lines are the raw 30 m samples; bold lines are a 450 m running
    median, which is what the eye should compare. Try window=5 or window=31.
    """
    window = 15
    df = df.sort_values("longitude").reset_index(drop=True)
    smooth = df[["surface", "ground_est"]].rolling(window, center=True, min_periods=3).median()
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    ax.plot(df["longitude"], df["surface"], color="#1b7837", lw=0.5, alpha=0.3)
    ax.plot(df["longitude"], df["ground_est"], color="#8c510a", lw=0.5, alpha=0.3)
    ax.fill_between(df["longitude"], smooth["ground_est"], smooth["surface"],
                    color="#1b7837", alpha=0.2, label="gap = canopy the DSM reports")
    ax.plot(df["longitude"], smooth["surface"], color="#1b7837", lw=1.8,
            label="surface (AW3D30 DSM)")
    ax.plot(df["longitude"], smooth["ground_est"], color="#8c510a", lw=1.8,
            label="DSM minus canopy height")
    ax.axhline(0, color="#616e7c", lw=0.8, ls="--")
    ax.text(df["longitude"].iloc[-1], 0.3, "sea level", ha="right", va="bottom",
            fontsize=7, color="#616e7c")
    ax.set_xlabel("Longitude (°), west to east across the delta")
    ax.set_ylabel("Height (m)")
    ax.set_title("A surface model is not the ground", loc="left")
    ax.legend(frameon=False, fontsize=8, loc="lower left", ncol=3)
    return fig


def plot_hand(df):
    """How much of the delta sits within a few metres of its drainage."""
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.barh(df["height_above_drainage"], df["area_km2"], color="#2171b5")
    for y, v in enumerate(df["area_km2"]):
        ax.text(v, y, f" {v:,.0f}", va="center", fontsize=8)
    ax.set_xlabel("Area (km²)")
    ax.set_title("Land close to its drainage floods first", loc="left")
    return fig


def products():
    src = "Data: JAXA AW3D30, ETH canopy height 2020, JRC GSW, MERIT Hydro. GEE."
    return [
        {"kind": "map", "name": "ch11-elevation", "image": dem,
         "vis": {"min": 0, "max": 40,
                 "palette": ["2b83ba", "abdda4", "ffffbf", "fdae61", "d7191c"]},
         "region": aoi, "legend": "AW3D30 surface height (m)",
         "title": "Surface elevation (a DSM)", "source": src,
         "caption": "AW3D30 over the delta. Over mangrove this is canopy top, not "
                    "ground, which is why the intertidal zone looks higher than it is."},
        {"kind": "map", "name": "ch11-intertidal", "image": intertidal.selfMask(),
         "vis": {"palette": ["14a37f"]}, "region": aoi,
         "classes": [("intertidal envelope", "#14a37f")],
         "title": "The intertidal envelope: low, flat, near water", "source": src,
         "caption": "Where the rule dem < 40 m, slope < 5° and < 5 km from water "
                    "holds. A classifier given this layer stops calling hillside "
                    "forest mangrove."},
        {"kind": "map", "name": "ch11-hand", "image": hand,
         "vis": {"min": 0, "max": 15,
                 "palette": ["08306b", "2171b5", "6baed6", "c6dbef", "f7fbff"]},
         "region": aoi, "legend": "Height above nearest drainage, HAND (m)",
         "title": "HAND: height above the nearest channel", "source": src,
         "caption": "Dark blue is land within a metre or two of its drainage. This "
                    "layer, not the DEM, is the starting point for flood mapping."},
        {"kind": "chart", "name": "ch11-profile", "data": profile, "plot": plot_profile,
         "caption": "Along one line across the delta the surface model rides on the "
                    "canopy. Subtracting a canopy height map should give the ground, but "
                    "the result dips far below sea level, which is impossible on a delta: "
                    "a 10 m canopy model and a 30 m DSM from different years do not agree "
                    "on where the trees are. Real ground under mangrove needs LiDAR (Part VI)."},
        {"kind": "chart", "name": "ch11-hand-area", "data": hand_table, "plot": plot_hand,
         "caption": "Area of the study rectangle within 1, 2, 5 and 10 m of drainage."},
        {"kind": "table", "name": "ch11-elevation-stats", "data": elevation_stats,
         "caption": "Surface elevation over land (m, 30 m sample). Half the delta is under 2.5 m."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(elevation_stats.getInfo())
