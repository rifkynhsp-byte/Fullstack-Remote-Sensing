#| title: A coal mine from orbit: footprint, volume and heat (Python)
#| description: The same footprint, cut-and-fill and thermal analysis as the JavaScript tab, in Python.

"""
CHAPTER 25 | Open-pit growth, excavated volume and thermal hot spots near
Sangatta, East Kalimantan, from public data.
"""

import ee
import matplotlib.pyplot as plt

mine = ee.Geometry.Rectangle([117.40, 0.48, 117.65, 0.75])

# 1. Footprint
dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(mine)


def bare_in(year):
    return (dw.filterDate(ee.Date.fromYMD(year, 1, 1), ee.Date.fromYMD(year + 1, 1, 1))
            .select("bare").mean().gt(0.5))


def footprint_row(year):
    km2 = (bare_in(year).multiply(ee.Image.pixelArea()).divide(1e6)
           .reduceRegion(reducer=ee.Reducer.sum(), geometry=mine, scale=30,
                         maxPixels=1e10).get("bare"))
    return ee.Feature(None, {"year": year, "bare_km2": km2})


footprint = ee.FeatureCollection([footprint_row(y) for y in range(2016, 2025)])
new_since_2017 = bare_in(2024).And(bare_in(2017).Not()).selfMask()

# 2. Volume
before = ee.Image("NASA/NASADEM_HGT/001").select("elevation")
glo = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").filterBounds(mine).select("DEM")
after = glo.mosaic().setDefaultProjection(glo.first().projection())
dz = after.subtract(before).rename("dz").updateMask(bare_in(2024))
cut, fill = dz.lt(-30), dz.gt(30)


def volume(mask):
    return (dz.updateMask(mask).multiply(ee.Image.pixelArea())
            .reduceRegion(reducer=ee.Reducer.sum(), geometry=mine, scale=30,
                          maxPixels=1e10).get("dz"))


def area_km2(mask):
    return (mask.selfMask().multiply(ee.Image.pixelArea()).divide(1e6)
            .reduceRegion(reducer=ee.Reducer.sum(), geometry=mine, scale=30,
                          maxPixels=1e10).values().get(0))


volumes = ee.FeatureCollection([
    ee.Feature(None, {"change": "cut (pits), deeper than 30 m", "area_km2": area_km2(cut),
                      "volume_million_m3": ee.Number(volume(cut)).divide(1e6)}),
    ee.Feature(None, {"change": "fill (dumps), higher than 30 m", "area_km2": area_km2(fill),
                      "volume_million_m3": ee.Number(volume(fill)).divide(1e6)})])

# 3. Heat
landsat = (ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
           .merge(ee.ImageCollection("LANDSAT/LC08/C02/T1_L2"))
           .filterBounds(mine).filterDate("2023-06-01", "2024-10-31")
           .filter(ee.Filter.calendarRange(6, 10, "month")))


def to_lst(img):
    qa = img.select("QA_PIXEL")
    clear = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
    return (img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15)
            .rename("lst").updateMask(clear))


lst = landsat.map(to_lst).median().clip(mine)
lst_median = ee.Number(lst.reduceRegion(reducer=ee.Reducer.median(), geometry=mine,
                                        scale=30, maxPixels=1e10).get("lst"))
anomaly = lst.subtract(lst_median).rename("anomaly")

# Surface temperature by what the ground is: bare footprint versus the rest
heat_samples = (anomaly.addBands(bare_in(2024).rename("bare"))
                .stratifiedSample(numPoints=600, classBand="bare", region=mine, scale=30,
                                  seed=5, tileScale=4))


def plot_footprint(df):
    """Bare ground per year: the disturbed footprint."""
    df = df.sort_values("year")
    fig, ax = plt.subplots(figsize=(6.5, 3))
    ax.bar(df["year"].astype(int).astype(str), df["bare_km2"], color="#8c510a")
    for x, v in zip(range(len(df)), df["bare_km2"]):
        ax.text(x, v, f"{v:.1f}", ha="center", va="bottom", fontsize=7)
    ax.set_ylabel("Bare ground (km²)")
    ax.set_title("Disturbed footprint, Dynamic World 'bare' > 0.5", loc="left")
    return fig


def plot_heat(df):
    """Surface temperature anomaly on bare ground against everything else."""
    fig, ax = plt.subplots(figsize=(6.5, 3))
    bins = [x / 2 for x in range(-16, 31)]
    ax.hist(df.loc[df["bare"] == 0, "anomaly"], bins=bins, alpha=0.6, density=True,
            color="#1b7837", label="vegetated and other")
    ax.hist(df.loc[df["bare"] == 1, "anomaly"], bins=bins, alpha=0.6, density=True,
            color="#a50026", label="bare footprint")
    ax.axvline(0, color="#616e7c", lw=0.8)
    ax.set_xlabel("Land surface temperature minus the area median (°C)")
    ax.set_ylabel("Density")
    ax.set_title("Pits, dumps and stockpiles run hot", loc="left")
    ax.legend(frameon=False, fontsize=8)
    return fig


def products():
    src = "Dynamic World, NASADEM, Copernicus GLO-30, Landsat 8/9 C2 L2. GEE."
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(mine)
          .filterDate("2024-05-01", "2024-10-31")
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)).median())
    growth_map = (s2.visualize(bands=["B4", "B3", "B2"], min=200, max=2200)
                  .blend(new_since_2017.visualize(palette=["ff7f00"], opacity=0.75)))
    return [
        {"kind": "map", "name": "ch25-growth", "image": growth_map, "region": mine,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "classes": [("bare in 2024, not in 2017", "#ff7f00")],
         "title": "Seven years of expansion", "source": src,
         "caption": "Ground that became bare between 2017 and 2024, over a 2024 "
                    "Sentinel-2 composite."},
        {"kind": "chart", "name": "ch25-footprint", "data": footprint, "plot": plot_footprint,
         "caption": "Disturbed footprint per year inside the study rectangle."},
        {"kind": "map", "name": "ch25-dz", "image": dz, "region": mine,
         "vis": {"min": -80, "max": 80, "palette": ["b2182b", "f7f7f7", "2166ac"]},
         "legend": "GLO-30 minus NASADEM (m), inside the 2024 bare footprint",
         "title": "Cut and fill between two elevation models", "source": src,
         "caption": "Red is lower than in 2000 (pits), blue is higher (waste dumps). "
                    "Both are surface models, so change smaller than about 30 m may be "
                    "cleared forest, not excavation."},
        {"kind": "table", "name": "ch25-volumes", "data": volumes,
         "columns": ["change", "area_km2", "volume_million_m3"], "floatfmt": ("", ".1f", ".0f"),
         "caption": "Volumes from the elevation difference, counting only change "
                    "beyond ±30 m inside the 2024 footprint. The time span is 2000 to "
                    "2011–2015, the dates of the two elevation models, not today."},
        {"kind": "map", "name": "ch25-lst", "image": anomaly, "region": mine,
         "vis": {"min": -5, "max": 10, "palette": ["313695", "ffffbf", "a50026"]},
         "legend": "LST anomaly, dry season 2023–2024 (°C)",
         "title": "Where the ground is hot", "source": src,
         "caption": "Dry-season median land surface temperature relative to the area "
                    "median. Coal stockpiles that self-heat show as persistent hot spots; "
                    "a drone or ground survey is still needed to confirm one."},
        {"kind": "chart", "name": "ch25-heat", "data": heat_samples, "plot": plot_heat,
         "caption": "Temperature anomaly at 600 points on and off the bare footprint."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(volumes.getInfo())
