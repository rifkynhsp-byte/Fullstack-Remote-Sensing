#| title: Peat, drought and fire (Python)
#| description: Where the peat is in Central Kalimantan, how much of it burned in the El Niño years, and how monthly fire follows monthly rain.

"""
CHAPTER 37 | Tropical peat holds carbon that took thousands of years to
build. Drained, it dries; dry, it burns; burning, it releases that carbon in
weeks. This chapter measures the link with open data only:

    peat extent       Global Peatland Map 2.0 (Global Peatlands Initiative,
                      via the GEE community catalog), 1 km
    burned area       MODIS MCD64A1 v6.1, 500 m
    active fire       FIRMS (MODIS), 1 km, daily
    rainfall          CHIRPS pentads

The area is Central Kalimantan around Palangka Raya: Sebangau and the
former Mega Rice Project, one of the most studied drained peatlands in the
world.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([113.3, -3.4, 114.7, -1.2], None, False)
gpm = ee.Image("projects/sat-io/open-datasets/GLOBAL-PEATLAND-DATABASE")
peat = gpm.gte(1).unmask(0).rename("peat")         # 1 = peat or peat mosaic

burned = ee.ImageCollection("MODIS/061/MCD64A1").select("BurnDate")
firms = ee.ImageCollection("FIRMS").select("T21")
chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD").select("precipitation")


def burned_in(year):
    return burned.filterDate(f"{year}-01-01", f"{year + 1}-01-01").max().gt(0).unmask(0)


burn_2015 = burned_in(2015).selfMask()


def burned_table():
    rows = []
    for y in [2015, 2019, 2023, 2024]:
        area = (ee.Image.pixelArea().divide(1e6).updateMask(burned_in(y))
                .addBands(peat)
                .reduceRegion(ee.Reducer.sum().group(1, "peat"), aoi, 500,
                              maxPixels=1e9, tileScale=4).get("groups").getInfo())
        g = {int(d["peat"]): d["sum"] for d in area}
        rows.append({"year": y, "burned_peat_km2": g.get(1, 0.0),
                     "burned_other_km2": g.get(0, 0.0)})
    df = pd.DataFrame(rows)
    df["peat_share"] = df["burned_peat_km2"] / (df["burned_peat_km2"] + df["burned_other_km2"])
    return df


def extent_table():
    g = (ee.Image.pixelArea().divide(1e6).addBands(gpm.unmask(0).rename("cls"))
         .reduceRegion(ee.Reducer.sum().group(1, "cls"), aoi, 1000, maxPixels=1e9)
         .get("groups").getInfo())
    names = {0: "not peat", 1: "peat dominated", 2: "peat in a soil mosaic"}
    return pd.DataFrame([{"class": names[int(d["cls"])], "area_km2": d["sum"]} for d in g])


def monthly_frame():
    """Fire pixel-days on peat and mean rainfall, every month 2012-2024.
    One request per year keeps each request small."""
    rows = []
    for y in range(2012, 2025):
        def month(m, y=y):
            d = ee.Date.fromYMD(y, m, 1)
            fires = (firms.filterDate(d, d.advance(1, "month")).count()
                     .updateMask(peat).reduceRegion(ee.Reducer.sum(), aoi, 1000,
                                                    maxPixels=1e9).get("T21"))
            rain = (chirps.filterDate(d, d.advance(1, "month")).sum()
                    .reduceRegion(ee.Reducer.mean(), aoi, 5000).get("precipitation"))
            return ee.Feature(None, {"year": y, "month": m, "fires": fires, "rain_mm": rain})
        fc = ee.FeatureCollection([month(m) for m in range(1, 13)])
        rows += [f["properties"] for f in fc.getInfo()["features"]]
    df = pd.DataFrame(rows)
    df["fires"] = df["fires"].fillna(0)
    df["date"] = pd.to_datetime(dict(year=df.year, month=df.month, day=1))
    return df


_monthly = {}


def monthly():
    if not _monthly:
        _monthly["df"] = monthly_frame()
    return _monthly["df"]


def plot_series(df):
    fig, (a, b) = plt.subplots(2, 1, figsize=(10, 4.8), sharex=True,
                               gridspec_kw={"height_ratios": [1.3, 1]})
    a.bar(df["date"], df["fires"], width=25, color="#c0392b")
    a.set_ylabel("fire pixel-days\non peat")
    a.set_title("Fire on peat comes in bursts at the end of dry seasons; 2015 and 2019 were the worst",
                loc="left", fontsize=10)
    for y in (2015, 2019, 2023):
        a.text(pd.Timestamp(f"{y}-09-01"), df["fires"].max() * 0.92, str(y),
               ha="center", fontsize=8, color="#6b7680")
    b.bar(df["date"], df["rain_mm"], width=25, color="#2a78d6")
    b.axhline(100, color="#6b7680", ls="--", lw=0.8)
    b.text(df["date"].min(), 104, "100 mm", fontsize=7, color="#6b7680", va="bottom")
    b.set_ylabel("rain (mm\nper month)")
    b.text(0, -0.28, "FIRMS (MODIS) and CHIRPS v2, Central Kalimantan box, 2012-2024",
           transform=b.transAxes, fontsize=7, color="#6b7680")
    fig.tight_layout()
    return fig


def plot_threshold(df):
    """Peat dries over weeks, so use the rain of this month and the two before."""
    df = df.sort_values("date").assign(rain3=lambda d: d["rain_mm"].rolling(3).sum())
    df = df.dropna(subset=["rain3"])
    big = df.fires > 1000
    below = df.rain3 < 450
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.scatter(df.loc[~big, "rain3"], df.loc[~big, "fires"] + 1, s=12, color="#b8c0c8")
    ax.scatter(df.loc[big, "rain3"], df.loc[big, "fires"] + 1, s=16, color="#c0392b",
               label="over 1,000 fire pixel-days")
    ax.set_yscale("log")
    ax.axvline(450, color="#6b7680", ls="--", lw=0.8)
    ax.text(455, 2, "450 mm", fontsize=7, color="#6b7680")
    ax.set_xlabel("Rainfall in this month and the two before (mm)")
    ax.set_ylabel("Fire pixel-days on peat + 1 (log)")
    ax.set_title(f"{(big & below).sum()} of {big.sum()} big fire months came after under "
                 f"450 mm in three months;\nonly {(~big & below).sum()} quiet months did",
                 loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def products():
    return [
        {"kind": "map", "name": "ch37-peat-map", "image": gpm.selfMask().clip(aoi),
         "region": aoi, "vis": {"min": 1, "max": 2, "palette": ["7b3f00", "d2a86e"]},
         "classes": [("peat dominated", "#7b3f00"), ("peat in a soil mosaic", "#d2a86e")],
         "title": "Peat in Central Kalimantan",
         "source": "Global Peatland Map 2.0 (GPI / Greifswald Mire Centre). GEE community catalog.",
         "caption": "Peat covers most of this box. The 1 km map is good for regions and "
                    "bad for field boundaries: use it to know where peat is likely, not "
                    "to decide the status of one parcel."},
        {"kind": "table", "name": "ch37-extent", "data": extent_table,
         "floatfmt": ("", ",.0f"), "caption": "Peat area in the box (km²)."},
        {"kind": "map", "name": "ch37-burn-2015", "image": burn_2015.clip(aoi), "region": aoi,
         "vis": {"min": 1, "max": 1, "palette": ["c0392b"]},
         "classes": [("burned in 2015", "#c0392b")],
         "title": "What burned in 2015",
         "source": "MODIS MCD64A1 v6.1 burned area. GEE.",
         "caption": "Burned area in the 2015 El Niño year. Nearly all of it lies on the "
                    "peat in the south; the mineral uplands in the north barely burned "
                    "(table below)."},
        {"kind": "table", "name": "ch37-burned", "data": burned_table,
         "floatfmt": (".0f", ",.0f", ",.0f", ".0%"),
         "caption": "Burned area on peat and elsewhere in the box. MCD64A1 misses small "
                    "and slow surface fires, so these are lower bounds."},
        {"kind": "chart", "name": "ch37-series", "data": monthly, "plot": plot_series,
         "caption": "Monthly active-fire detections on peat (top) and rainfall (bottom). "
                    "A pixel-day is one 1 km pixel flagged on one day."},
        {"kind": "chart", "name": "ch37-threshold", "data": monthly, "plot": plot_threshold,
         "caption": "Each dot is one month. One month's rain is a weak guide, because "
                    "peat dries over weeks. Three months of rain together separate the "
                    "big fire months from the quiet ones far better. The 450 mm line is "
                    "read off this chart, not a published threshold."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(burned_table())
