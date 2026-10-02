#| title: Where is it liveable? Greater Bandung (Python)
#| description: The same seven liveability indicators as the Earth Engine App - heat, greenery, flood-prone land, steep slopes, air quality, services and crowding - computed at 100 m for Greater Bandung, scored with the app's default weights, and profiled for three neighbourhoods.

"""
CHAPTER 23 | From script to tool: a liveability explorer

The JavaScript tab is the app: sliders for seven weights, a score map that
re-draws, and a click that shows the profile of any place. This tab computes
the same layers with the same default weights, so the chapter can show what
the app shows.

Every indicator is rescaled to 0 (worst) to 1 (best) between fixed, stated
limits, so a reader can see and argue with each choice:

  heat       Landsat 8/9 dry-season land surface temperature   cooler is better  40 -> 25 C
  greenery   Dynamic World tree + grass probability, 300 m      more is better    0  -> 0.6
  flooding   MERIT Hydro height above nearest drainage          higher is better  0  -> 15 m
  slopes     Copernicus DEM slope                               flatter is better 30 -> 0 deg
  air        Sentinel-5P tropospheric NO2, 2024 mean            less is better    stated in code
  services   VIIRS 2024 night light (a proxy for shops, jobs)   more is better    0  -> 20
  crowding   WorldPop people per hectare                         fewer is better   150 -> 0

Data: all public Earth Engine collections; no uploads needed.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

AREA_NAMES = ["Kota Bandung", "Kota Cimahi", "Bandung", "Bandung Barat"]
NO2_RANGE = (1.5e-5, 5e-5)                 # mol/m2: the 5th-95th percentile over the area in 2024
LIMITS = {"heat": (40, 25), "greenery": (0, 0.6), "flooding": (0, 15), "slopes": (30, 0),
          "air": (NO2_RANGE[1], NO2_RANGE[0]), "services": (0, 20), "crowding": (150, 0)}
WEIGHTS = {"heat": 2, "greenery": 2, "flooding": 2, "slopes": 1, "air": 1, "services": 2, "crowding": 1}
PLACES = {"Braga (city centre)": (107.6091, -6.9175), "Dayeuhkolot (flood plain)": (107.6250, -6.9870),
          "Lembang (northern hills)": (107.6180, -6.8110)}


def area():
    return (ee.FeatureCollection("FAO/GAUL/2025/level2").filter(ee.Filter.eq("GAUL1_NAME", "Jawa Barat"))
            .filter(ee.Filter.inList("GAUL2_NAME", AREA_NAMES)))


def raw_layers():
    """The seven indicators in their physical units."""
    geom = area().geometry()

    def landsat_st(img):
        qa = img.select("QA_PIXEL")
        clear = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))       # no cloud, no shadow
        return img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15).updateMask(clear)

    heat = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
            .filterBounds(geom).filterDate("2023-06-01", "2024-10-01").filter(ee.Filter.calendarRange(6, 9, "month"))
            .map(landsat_st).median().rename("heat"))
    dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geom).filterDate("2024-01-01", "2025-01-01")
          .select(["trees", "grass"]).mean())
    green = dw.select("trees").add(dw.select("grass")).focalMean(300, "circle", "meters").rename("greenery")
    hand = ee.Image("MERIT/Hydro/v1_0_1").select("hnd").rename("flooding")
    slope = ee.Terrain.slope(ee.ImageCollection("COPERNICUS/DEM/GLO30").filterBounds(geom).select("DEM").mosaic()
                             .setDefaultProjection("EPSG:4326", None, 30)).rename("slopes")
    no2 = (ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_NO2").filterDate("2024-01-01", "2025-01-01")
           .select("tropospheric_NO2_column_number_density").mean().rename("air"))
    light = (ee.ImageCollection("NOAA/VIIRS/DNB/ANNUAL_V22").filterDate("2024-01-01", "2025-01-01").first()
             .select("average").rename("services"))
    people = (ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "IDN"))
              .filter(ee.Filter.eq("year", 2020)).mosaic().unmask(0).rename("crowding"))   # per ha; no data = nobody lives there
    return ee.Image.cat([heat, green, hand, slope, no2, light, people]).clip(geom)


def goodness():
    """Each indicator rescaled between its stated limits to 0 (worst) .. 1 (best)."""
    r = raw_layers()
    # (value - worst) / (best - worst) works whichever way round "good" runs
    bands = [r.select(k).subtract(lo).divide(hi - lo).clamp(0, 1).rename(k) for k, (lo, hi) in LIMITS.items()]
    return ee.Image.cat(bands)


def score(weights=WEIGHTS):
    g = goodness(); total = sum(weights.values())
    s = ee.Image(0)
    for k, w in weights.items():
        s = s.add(g.select(k).multiply(w))
    return s.divide(total).rename("score")


def percentile_table():
    """What the data actually look like over the area: the evidence behind the limits."""
    r = raw_layers()
    s = r.reduceRegion(ee.Reducer.percentile([5, 50, 95]), area().geometry(), 200, maxPixels=1e9, tileScale=4).getInfo()
    rows = [{"indicator": k, "p5": s[f"{k}_p5"], "median": s[f"{k}_p50"], "p95": s[f"{k}_p95"],
             "worst limit": LIMITS[k][0], "best limit": LIMITS[k][1]} for k in LIMITS]
    return pd.DataFrame(rows)


def profile_table():
    g = goodness().addBands(score())
    rows = []
    for name, (lon, lat) in PLACES.items():
        v = g.reduceRegion(ee.Reducer.mean(), ee.Geometry.Point(lon, lat).buffer(250), 30).getInfo()
        rows.append({"place": name, **{k: v[k] for k in list(LIMITS) + ["score"]}})
    return pd.DataFrame(rows)


def plot_profile(df):
    """The app's click panel, drawn for three places: one bar per indicator."""
    keys = list(LIMITS); fig, ax = plt.subplots(figsize=(9, 4))
    w = 0.26
    for i, (r, c) in enumerate(zip(df.itertuples(), ["#d73027", "#4575b4", "#1a9850"])):
        ax.bar(np.arange(len(keys)) + (i - 1) * w, [getattr(r, k) for k in keys], width=w, color=c,
               label=f"{r.place}: score {r.score:.2f}")
    ax.set_xticks(range(len(keys)), keys); ax.set_ylim(0, 1); ax.set_ylabel("0 = worst, 1 = best")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False)
    ax.set_title("What the app shows when you click: three places, seven indicators", loc="left", fontsize=10)
    fig.tight_layout()
    return fig


def products():
    region = area().geometry().bounds()
    src = "Landsat 8/9, Dynamic World, MERIT Hydro, Copernicus DEM, Sentinel-5P, VIIRS, WorldPop"
    return [
        {"kind": "table", "name": "ch23-limits", "data": percentile_table,
         "floatfmt": ("", ".4g", ".4g", ".4g", ".4g", ".4g"),
         "caption": "Each indicator over Greater Bandung (5th, 50th and 95th percentile) and the limits used to rescale "
                    "it from worst (0) to best (1)."},
        {"kind": "map", "name": "ch23-score", "image": score(), "region": region,
         "vis": {"min": 0.2, "max": 0.8, "palette": ["#a50026", "#f46d43", "#fee08b", "#a6d96a", "#1a9850"]},
         "title": "Liveability score with the app's default weights", "source": src, "legend": "score (0 to 1)",
         "caption": "The score the app draws when it opens: heat, greenery, flooding and services weighted 2, the rest 1."},
        {"kind": "map", "name": "ch23-heat", "image": raw_layers().select("heat"), "region": region,
         "vis": {"min": 25, "max": 45, "palette": ["#313695", "#ffffbf", "#a50026"]},
         "title": "Dry-season land surface temperature (°C)", "source": "Landsat 8/9 Collection 2, June to September 2023-2024",
         "legend": "°C", "caption": "One of the seven layers: the city centre and industrial south are hottest."},
        {"kind": "chart", "name": "ch23-profile", "data": profile_table, "plot": plot_profile,
         "caption": "The click panel for three places: the same score can hide very different strengths."},
    ]


if __name__ == "__main__":
    import json, os
    k = os.path.expanduser(os.environ.get("BOOK_EE_KEY", "~/.config/fullstack-rs/ee-key.json")); info = json.load(open(k))
    ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], k), project=info.get("project_id"))
    print(percentile_table().to_string()); print(profile_table().round(2).to_string())
