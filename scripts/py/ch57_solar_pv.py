#| title: Floating solar from space: the Cirata PV plant (Python)
#| description: The 192 MWp floating solar plant on Cirata reservoir, West Java. Panels are found as reservoir water that stopped being water between 2021 and 2024, separated from older fish cages, measured against the reported 200 ha, and followed month by month through construction with Sentinel-1 radar.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 57 | Watching a power plant appear on a lake.

Cirata floating PV: 192 MWp on about 200 ha of the reservoir, inaugurated
on 9 November 2023 (reported figures). From space:

    1. reservoir  JRC water occurrence >= 80 % (always water, 1984-2021)
    2. panels     open water in the 2021 dry season, not water in the 2024 dry
                  season (Sentinel-2 SWIR, B11 < 0.05 = water): something new floats there
    3. cages      not water in BOTH years: the old floating fish cages
                  (keramba jaring apung), which are not the plant
    4. size       largest connected patch of new non-water, against 200 ha
    5. timeline   Sentinel-1 VV backscatter over that patch, every month:
                  calm water is dark to radar, metal frames and panels are bright
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([107.18, -6.84, 107.42, -6.62], None, False)
reservoir = (ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gte(80)
             .unmask(0).clip(aoi))
REPORTED_HA = 200


def s2(start, end):
    def mask(i):
        return i.updateMask(i.select("cs").gte(0.6)).divide(10000)
    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi)
            .filterDate(start, end)
            .linkCollection(ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"),
                            ["cs"])
            .map(mask).median().select(["B2", "B3", "B4", "B8", "B11", "B12"]))


before, after = s2("2021-05-01", "2021-10-31"), s2("2024-05-01", "2024-10-31")


def water(img):
    """Open water absorbs shortwave infrared almost completely (B11 about 0.015).
    NDWI is NOT used: grey panels on water still give a positive NDWI."""
    return img.select("B11").lt(0.05)


# Not green either: floating weed and algae mats also stop being "water" but have high NDVI.
not_green = after.normalizedDifference(["B8", "B4"]).lt(0.1)
new_float = reservoir.And(water(before)).And(water(after).Not()).And(not_green)
cages = reservoir.And(water(before).Not()).And(water(after).Not())
# Keep patches of at least 1 ha (100 pixels at 10 m); the plant is one big block of arrays.
new_clean = new_float.updateMask(new_float.connectedPixelCount(1024, True).gte(100)).selfMask()
# Find the plant on a coarser 30 m grid (cheap), measure it at 10 m afterwards.
grid30 = ee.Projection("EPSG:32748").atScale(30)
coarse = new_float.reproject(grid30)
# Grow each patch by about 100 m so the separate array blocks of one plant join up.
merged = coarse.unmask(0).focalMax(3, "square", "pixels").reproject(grid30).selfMask()
merged = merged.updateMask(merged.connectedPixelCount(1024, True).gte(50))
patches = merged.reduceToVectors(geometry=aoi, crs=grid30, eightConnected=True,
                                 maxPixels=1e10, tileScale=8)
plant = ee.Feature(patches.map(lambda f: f.set("ha", f.geometry().area(5).divide(1e4)))
                   .sort("ha", False).first())
plant_zone = plant.geometry()
plant_px = new_clean.clip(plant_zone)


def area_table():
    area = ee.Image.pixelArea().divide(1e4)
    s = lambda img, geom: area.updateMask(img).reduceRegion(ee.Reducer.sum(), geom, 10,
                                                            maxPixels=1e10).values().get(0)
    c = plant.geometry().centroid(10).coordinates().getInfo()
    return pd.DataFrame([{
        "detected_plant_ha": ee.Number(s(plant_px, plant_zone)).getInfo(),
        "reported_ha": REPORTED_HA,
        "plant_outline_ha": plant.get("ha").getInfo(),
        "old_fish_cages_ha": ee.Number(s(cages, aoi)).getInfo(),
        "reservoir_ha": ee.Number(s(reservoir.selfMask(), aoi)).getInfo(),
        "plant_lon": round(c[0], 4), "plant_lat": round(c[1], 4)}])


def signature_table():
    """Mean 2024 reflectance of panels, fish cages and open water."""
    groups = {"floating PV (new)": plant_px, "fish cages (old)": cages.selfMask(),
              "open water": reservoir.And(water(after)).selfMask()}
    rows = []
    for name, m in groups.items():
        v = after.updateMask(m).reduceRegion(ee.Reducer.mean(), aoi, 30, maxPixels=1e10,
                                              tileScale=16).getInfo()
        rows.append({"surface": name, **{k: v[k] for k in ["B2", "B3", "B4", "B8", "B11", "B12"]}})
    return pd.DataFrame(rows)


def plot_signature(df):
    wl = [490, 560, 665, 842, 1610, 2190]
    cols = {"floating PV (new)": "#6a3d9a", "fish cages (old)": "#ff7f00", "open water": "#1f78b4"}
    fig, ax = plt.subplots(figsize=(6.8, 3.4))
    for _, r in df.iterrows():
        ax.plot(wl, [r[b] for b in ["B2", "B3", "B4", "B8", "B11", "B12"]], marker="o",
                color=cols[r.surface], label=r.surface)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Surface reflectance")
    ax.set_title("What panels, fish cages and water look like to Sentinel-2", loc="left",
                 fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def radar_table():
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(plant_zone)
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
          .filterDate("2021-01-01", "2025-01-01").select("VV"))
    water_ref = reservoir.And(water(after)).And(plant_px.unmask(0).Not()).selfMask()

    def month(m):
        start = ee.Date("2021-01-01").advance(m, "month")
        img = s1.filterDate(start, start.advance(1, "month")).mean()
        pv = img.updateMask(plant_px).reduceRegion(ee.Reducer.mean(), plant_zone, 20,
                                                   maxPixels=1e9).get("VV")
        ow = img.updateMask(water_ref).reduceRegion(ee.Reducer.mean(), plant_zone.buffer(2000),
                                                    20, maxPixels=1e9).get("VV")
        return ee.Feature(None, {"month": start.format("YYYY-MM"), "pv_vv_db": pv,
                                 "water_vv_db": ow})
    fc = ee.FeatureCollection(ee.List.sequence(0, 47).map(month))
    return pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]]).dropna()


def plot_radar(df):
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    x = pd.to_datetime(df.month)
    ax.plot(x, df.pv_vv_db, color="#6a3d9a", lw=2, marker="o", ms=3,
            label="inside the plant footprint")
    ax.plot(x, df.water_vv_db, color="#1f78b4", lw=1.2, ls="--", label="open water nearby")
    ax.axvline(pd.Timestamp("2023-11-09"), color="#4b5563", lw=0.8)
    ax.text(pd.Timestamp("2023-11-20"), ax.get_ylim()[0] + 1, "inaugurated\n9 Nov 2023",
            fontsize=7, color="#4b5563")
    ax.set_ylabel("Sentinel-1 VV (dB)")
    ax.set_title("A power plant appearing on a lake, month by month", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    return fig


box = plant_zone.bounds(10)
outline = ee.Image().byte().paint(ee.FeatureCollection([ee.Feature(plant_zone)]), 1, 2)


def rgb(img):
    return img.visualize(bands=["B4", "B3", "B2"], min=0.0, max=0.12, gamma=1.3)


overview = (rgb(after).blend(cages.selfMask().visualize(palette=["ff7f00"]))
            .blend(new_clean.visualize(palette=["d000ff"])))


def products():
    rgbvis = {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255}
    return [
        {"kind": "map", "name": "ch57-overview", "image": overview, "region": aoi, "vis": rgbvis,
         "classes": [("new since 2021: floating PV", "#d000ff"),
                     ("not water in 2021 or 2024: fish cages", "#ff7f00")],
         "title": "Cirata reservoir, dry season 2024",
         "source": "Sentinel-2 L2A; JRC Global Surface Water. GEE.",
         "caption": "Magenta: reservoir water in 2021 that was no longer water in 2024. "
                    "Orange: surfaces that were not water in either year, mostly floating fish "
                    "cages."},
        {"kind": "map", "name": "ch57-before", "image": rgb(before).blend(
            outline.visualize(palette=["ffff00"])), "region": box, "vis": rgbvis,
         "title": "2021 dry season", "source": "Sentinel-2 L2A. GEE.",
         "caption": "The plant's footprint (yellow) in 2021: open water."},
        {"kind": "map", "name": "ch57-after", "image": rgb(after).blend(
            outline.visualize(palette=["ffff00"])), "region": box, "vis": rgbvis,
         "title": "2024 dry season", "source": "Sentinel-2 L2A. GEE.",
         "caption": "The same place in 2024: rows of dark panel blocks with water lanes "
                    "between them."},
        {"kind": "table", "name": "ch57-area", "data": area_table,
         "floatfmt": (",.0f", ",.0f", ",.0f", ",.0f", ",.0f", ".4f", ".4f"),
         "caption": "Detected plant area against the reported 200 ha."},
        {"kind": "chart", "name": "ch57-signature", "data": signature_table,
         "plot": plot_signature,
         "caption": "Mean 2024 reflectance of the three floating surfaces."},
        {"kind": "chart", "name": "ch57-radar", "data": radar_table, "plot": plot_radar,
         "caption": "Monthly Sentinel-1 VV backscatter over the plant footprint and over open "
                    "water nearby, 2021-2024."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(area_table())
