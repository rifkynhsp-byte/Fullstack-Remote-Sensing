#| title: A coal mine from orbit: footprint, volume and heat (Python)
#| description: The same footprint, cut-and-fill and thermal analysis as the JavaScript tab, in Python.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

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


# 4. Where did the spoil go? The same elevation change without the 2024 footprint mask
dz_all = after.subtract(before).rename("dz")


def balance_table():
    """Cut and fill inside and outside the 2024 bare footprint (beyond +-30 m)."""
    import pandas as pd
    bare = bare_in(2024)
    rows = []
    for where, m in (("inside the 2024 bare footprint", bare), ("outside it (vegetated or water in 2024)", bare.Not())):
        for kind, sel in (("cut", dz_all.lt(-30)), ("fill", dz_all.gt(30))):
            mm = sel.And(m)
            r = (dz_all.updateMask(mm).multiply(ee.Image.pixelArea()).rename("v")
                 .addBands(ee.Image.pixelArea().updateMask(mm).rename("a"))
                 .reduceRegion(ee.Reducer.sum(), mine, 30, maxPixels=1e10).getInfo())
            rows.append({"where": where, "change": kind, "area_km2": r["a"] / 1e6, "volume_million_m3": r["v"] / 1e6})
    return pd.DataFrame(rows)


# 5. Heat that persists: how often is a pixel much hotter than the bare ground around it?
HOT = 5.0                                           # °C above the median of bare ground in the same scene
heat_scenes = (ee.ImageCollection("LANDSAT/LC09/C02/T1_L2").merge(ee.ImageCollection("LANDSAT/LC08/C02/T1_L2"))
               .filterBounds(mine).filterDate("2019-01-01", "2025-01-01").filter(ee.Filter.calendarRange(6, 10, "month"))
               .map(to_lst))


def scene_hot(img):
    """1 where this scene's LST is HOT degrees above the median of that scene's bare ground, 0 elsewhere (masked if cloudy)."""
    bare = bare_in(2024)
    med = ee.Number(img.updateMask(bare).reduceRegion(ee.Reducer.median(), mine, 90, maxPixels=1e9).get("lst"))
    return ee.Algorithms.If(med, img.subtract(med).gt(HOT).rename("hot"), ee.Image().rename("hot"))


hot_stack = ee.ImageCollection(heat_scenes.map(lambda i: ee.Image(scene_hot(i))))
n_clear = hot_stack.count().rename("n")
persistence = hot_stack.sum().divide(n_clear).updateMask(n_clear.gte(5)).rename("share").clip(mine)


def persistence_table():
    import pandas as pd
    bare = bare_in(2024)
    rows = []
    for lab, thr in (("hot in at least 25 % of clear scenes", 0.25), ("at least 50 %", 0.5), ("at least 75 %", 0.75)):
        m = persistence.gte(thr)
        r = (ee.Image.pixelArea().updateMask(m).rename("a").addBands(ee.Image.pixelArea().updateMask(m.And(bare)).rename("b"))
             .reduceRegion(ee.Reducer.sum(), mine, 30, maxPixels=1e10).getInfo())
        rows.append({"persistence": lab, "area_ha": r["a"] / 1e4, "on the bare footprint (%)": 100 * r["b"] / max(r["a"], 1)})
    n = heat_scenes.size().getInfo()
    out = pd.DataFrame(rows)
    out.attrs["scenes"] = n
    return out


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
        {"kind": "table", "name": "ch25-balance", "data": balance_table, "floatfmt": ("", "", ".2f", ".0f"),
         "caption": "Cut and fill beyond ±30 m, inside and outside the 2024 bare footprint (NASADEM 2000 to Copernicus GLO-30)."},
        {"kind": "map", "name": "ch25-persistence", "image": persistence, "region": mine,
         "vis": {"min": 0, "max": 1, "palette": ["ffffff", "fee391", "fe9929", "cc4c02", "662506"]},
         "legend": "Share of clear dry-season scenes, 2019-2024, at least 5 °C above the scene's bare-ground median",
         "title": "Where the ground is hot again and again", "source": "Landsat 8 and 9 ST_B10. GEE.",
         "caption": "Persistence, not a single hot map, is the stockpile signal. Pixels with fewer than 5 clear scenes are blank."},
        {"kind": "table", "name": "ch25-persistence-table", "data": persistence_table, "floatfmt": ("", ".0f", ".0f"),
         "caption": "Area that was persistently hot, and how much of it lies on the bare footprint."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(volumes.getInfo())
