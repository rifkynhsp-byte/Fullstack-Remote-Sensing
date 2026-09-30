#| title: reduceRegions: a decade of fire detections per district in Riau (Python)
#| description: The same per-district and per-year sums as the JavaScript tab, in Python.

"""
CHAPTER 7 | FIRMS fire detections summed per Riau district with
reduceRegions, and per year for the province.
"""

import ee
import matplotlib.pyplot as plt

districts = (ee.FeatureCollection("FAO/GAUL/2025/level2")
             .filter(ee.Filter.eq("GAUL1_NAME", "Riau")))
riau = districts.geometry()

firms = (ee.ImageCollection("FIRMS").filterBounds(riau)
         .map(lambda img: img.select("confidence").gte(50).selfMask().rename("fire")
              .copyProperties(img, ["system:time_start"])))

fire_days = (firms.filterDate("2015-01-01", "2025-01-01").count()
             .rename("fire_days").clip(riau))


def per_district_props(f):
    km2 = f.geometry().area(100).divide(1e6)
    return f.set({"district": f.get("GAUL2_NAME"), "fire_days": f.get("sum"),
                  "per_1000_km2": ee.Number(f.get("sum")).divide(km2).multiply(1000)})


per_district = (fire_days.reduceRegions(collection=districts, reducer=ee.Reducer.sum(),
                                        scale=1000, tileScale=4)
                .map(per_district_props)
                .select(["district", "fire_days", "per_1000_km2"], retainGeometry=False))


def year_total(y):
    n = (firms.filter(ee.Filter.calendarRange(y, y, "year")).count()
         .reduceRegion(reducer=ee.Reducer.sum(), geometry=riau, scale=1000,
                       maxPixels=1e10, tileScale=4).get("fire"))
    return ee.Feature(None, {"year": y, "fire_days": n})


per_year = ee.FeatureCollection([year_total(y) for y in range(2015, 2025)])

map_image = (fire_days.visualize(min=1, max=30,
                                 palette=["fee391", "fe9929", "cc4c02", "662506"])
             .blend(ee.Image().byte().paint(districts, 1, 1).visualize(palette=["000000"])))


def plot_districts(df):
    """Two rankings: raw totals and density. They do not agree."""
    df = df.sort_values("per_1000_km2")
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True)
    axes[0].barh(df["district"], df["fire_days"], color="#cc4c02")
    axes[0].set_xlabel("Fire detection days, 2015 to 2024")
    axes[1].barh(df["district"], df["per_1000_km2"], color="#662506")
    axes[1].set_xlabel("Per 1,000 km²")
    fig.suptitle("Riau districts: total against density", x=0.02, ha="left")
    fig.tight_layout()
    return fig


def plot_years(df):
    """The province, one bar per year."""
    df = df.sort_values("year")
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.bar(df["year"].astype(int).astype(str), df["fire_days"], color="#cc4c02")
    ax.set_ylabel("Fire detection days")
    ax.set_title("Riau, fire detection days per year", loc="left")
    return fig


def products():
    return [
        {"kind": "map", "name": "ch07-fire-map", "image": map_image, "region": riau.bounds(),
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "classes": [("1 day", "#fee391"), ("10 days", "#fe9929"), ("20 days", "#cc4c02"),
                     ("30+ days", "#662506")],
         "title": "Fire detection days per 1 km pixel, 2015 to 2024",
         "source": "FIRMS (NASA), confidence ≥ 50. Boundaries: FAO GAUL 2025.",
         "caption": "Every 1 km pixel's count of days with a confident fire detection, "
                    "with district boundaries."},
        {"kind": "chart", "name": "ch07-fire-districts", "data": per_district,
         "plot": plot_districts,
         "caption": "reduceRegions returned one row per district in a single call."},
        {"kind": "chart", "name": "ch07-fire-years", "data": per_year, "plot": plot_years,
         "caption": "The province's yearly total."},
        {"kind": "table", "name": "ch07-fire-table", "data": per_district,
         "columns": ["district", "fire_days", "per_1000_km2"], "floatfmt": ("", ".0f", ".1f"),
         "caption": "Per district, 2015 to 2024."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(per_district.getInfo())
