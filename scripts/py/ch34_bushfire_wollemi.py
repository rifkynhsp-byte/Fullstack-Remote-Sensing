#| title: A bushfire from orbit: dryness, progression and burn severity (Python)
#| description: The same fuel dryness, fire progression and dNBR severity analysis as the JavaScript tab, in Python.

"""
CHAPTER 34 | The 2019-20 Black Summer fires in the Wollemi and Blue
Mountains, New South Wales: how dry the fuel was, how the fire spread, and
how severely it burned, from public data only.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([149.8, -33.8, 151.3, -32.5])
CONFIG = {"pre": ("2018-12-20", "2019-01-18"),      # same season, one year before
          "post": ("2020-02-20", "2020-03-28"),     # after the fires were out
          "fire_season": ("2019-09-01", "2020-03-01")}

# ---------------------------------------------------------------------------
# STEP 1. Fuel: how dry was the forest before the fire?
# ---------------------------------------------------------------------------
forest = (ee.ImageCollection("ESA/WorldCover/v100").first().eq(10)).rename("forest")
mod09 = ee.ImageCollection("MODIS/061/MOD09A1").filterBounds(aoi)


def ndmi(img):
    """NDMI from MODIS: NIR (b2) against SWIR 1.6 um (b6). Water in leaves."""
    qa = img.select("StateQA")
    clear = qa.bitwiseAnd(3).eq(0).And(qa.bitwiseAnd(1 << 2).eq(0))
    return (img.normalizedDifference(["sur_refl_b02", "sur_refl_b06"]).rename("ndmi")
            .updateMask(clear).updateMask(forest)
            .copyProperties(img, ["system:time_start"]))


def month_row(i):
    start = ee.Date("2014-01-01").advance(i, "month")
    value = (mod09.filterDate(start, start.advance(1, "month")).map(ndmi).mean()
             .reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi, scale=1000,
                           maxPixels=1e10).get("ndmi"))
    return ee.Feature(None, {"date": start.format("YYYY-MM"), "ndmi": value})


dryness = ee.FeatureCollection(ee.List.sequence(0, 6 * 12 - 1).map(month_row))

# ---------------------------------------------------------------------------
# STEP 2. Progression: when did each place burn?
# ---------------------------------------------------------------------------
season_start = ee.Date(CONFIG["fire_season"][0])


def days_since_start(img):
    """MCD64A1 stores day-of-year; turn it into days since 1 September 2019."""
    jan1 = ee.Date.fromYMD(img.date().get("year"), 1, 1)
    offset = jan1.difference(season_start, "day")
    return img.select("BurnDate").selfMask().add(offset).rename("day").toFloat()


mcd64 = (ee.ImageCollection("MODIS/061/MCD64A1").filterDate(*CONFIG["fire_season"]))
burn_date = mcd64.select("BurnDate").max()
days = mcd64.map(days_since_start).min().clip(aoi)       # first day each pixel burned

firms = ee.ImageCollection("FIRMS").filterBounds(aoi).filterDate(*CONFIG["fire_season"])


def hotspot_count(img):
    n = (img.select("T21").gt(0).selfMask()
         .reduceRegion(reducer=ee.Reducer.count(), geometry=aoi, scale=1000,
                       maxPixels=1e10).get("T21"))
    return ee.Feature(None, {"date": img.date().format("YYYY-MM-dd"), "hotspots": n})


hotspots = firms.map(hotspot_count)

# ---------------------------------------------------------------------------
# STEP 3. Severity: dNBR with the USGS classes
# ---------------------------------------------------------------------------
s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi)


def mask_s2(img):
    scl = img.select("SCL")
    ok = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
    return img.updateMask(ok).divide(10000)


pre = s2.filterDate(*CONFIG["pre"]).map(mask_s2).median()
post = s2.filterDate(*CONFIG["post"]).map(mask_s2).median()
nbr_pre = pre.normalizedDifference(["B8", "B12"])
nbr_post = post.normalizedDifference(["B8", "B12"])
dnbr = nbr_pre.subtract(nbr_post).multiply(1000).rename("dNBR").clip(aoi)

# Key and Benson (2006) class breaks, scaled by 1000
BREAKS = [-251, -101, 100, 270, 440, 660]
CLASSES = [("enhanced regrowth, high", "#7a8737"), ("enhanced regrowth, low", "#acbe4d"),
           ("unburned", "#0ae042"), ("low severity", "#fff70b"),
           ("moderate-low severity", "#ffaf38"), ("moderate-high severity", "#ff641b"),
           ("high severity", "#a41fd6")]
severity = (ee.Image(0).where(dnbr.gte(BREAKS[0]), 1).where(dnbr.gte(BREAKS[1]), 2)
            .where(dnbr.gte(BREAKS[2]), 3).where(dnbr.gte(BREAKS[3]), 4)
            .where(dnbr.gte(BREAKS[4]), 5).where(dnbr.gte(BREAKS[5]), 6)
            .updateMask(dnbr.mask()).rename("class").clip(aoi))

# Area per class in ONE request, with a grouped reducer.
grouped = (ee.Image.pixelArea().divide(1e4).addBands(severity)
           .reduceRegion(reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
                         geometry=aoi, scale=20, maxPixels=1e11, tileScale=8))
by_class = ee.FeatureCollection(ee.List(grouped.get("groups")).map(
    lambda g: ee.Feature(None, {"class": ee.Dictionary(g).get("class"),
                                "hectares": ee.Dictionary(g).get("sum")})))

# A second, independent source: the MODIS burned-area product.
burned_dnbr = severity.gte(3)


def agreement_frame():
    """dNBR burned area, MODIS burned area, and how well they overlap."""
    # Both maps on one fixed 100 m UTM grid, combined into one code per pixel:
    # 3 = burned in both, 2 = dNBR only, 1 = MODIS only. One grouped sum.
    code = (burned_dnbr.unmask(0).multiply(2).add(burn_date.gt(0).unmask(0))
            .rename("code").clip(aoi))
    stats = (ee.Image.pixelArea().divide(1e4).addBands(code)
             .reduceRegion(reducer=ee.Reducer.sum().group(groupField=1, groupName="code"),
                           geometry=aoi, crs="EPSG:32756", scale=100, maxPixels=1e10,
                           tileScale=8)).getInfo()
    ha = {int(g["code"]): g["sum"] for g in stats["groups"]}
    both_ha, dnbr_only, modis_only = ha.get(3, 0), ha.get(2, 0), ha.get(1, 0)
    return pd.DataFrame([
        {"measure": "burned by both", "hectares": both_ha},
        {"measure": "burned by dNBR only", "hectares": dnbr_only},
        {"measure": "burned by MODIS MCD64A1 only", "hectares": modis_only},
        {"measure": "agreement (both / either)",
         "hectares": both_ha / (both_ha + dnbr_only + modis_only)}])


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def plot_dryness(df):
    """Forest NDMI each month, against the same month in other years."""
    df = df.dropna().copy()
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.month
    clim = df[df["date"] < "2019-01-01"].groupby("month")["ndmi"].mean()
    df["anomaly"] = df["ndmi"] - df["month"].map(clim)
    fig, ax = plt.subplots(figsize=(6.8, 3.2))
    colours = np.where(df["anomaly"] < 0, "#b35806", "#35978f")
    ax.bar(df["date"], df["anomaly"], width=25, color=colours)
    ax.axvspan(pd.Timestamp("2019-10-26"), pd.Timestamp("2020-02-10"), color="#d7191c",
               alpha=0.12, lw=0)
    ax.text(pd.Timestamp("2019-10-26"), ax.get_ylim()[1] * 0.9, " fires", color="#d7191c",
            fontsize=8, va="top")
    ax.axhline(0, color="#616e7c", lw=0.8)
    ax.set_ylabel("NDMI minus 2014-18 mean\nfor that month")
    ax.set_title("The forest was drier than usual for a year before it burned", loc="left")
    return fig


def plot_hotspots(df):
    """MODIS active-fire pixels per day across the study area."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    fig, ax = plt.subplots(figsize=(6.8, 3))
    ax.bar(df["date"], df["hotspots"], width=1, color="#d7191c")
    ax.set_ylabel("Active-fire pixels per day")
    ax.set_title("Fire activity, September 2019 to February 2020", loc="left")
    fig.autofmt_xdate()
    return fig


def plot_severity(df):
    """Hectares per dNBR severity class."""
    names = [c[0] for c in CLASSES]
    colours = [c[1] for c in CLASSES]
    df = df.copy()
    df["class"] = df["class"].astype(int)
    df = df.set_index("class").reindex(range(7)).fillna(0)
    fig, ax = plt.subplots(figsize=(6.8, 3.2))
    ax.barh(names, df["hectares"] / 1000, color=colours, edgecolor="#616e7c", lw=0.4)
    for y, v in enumerate(df["hectares"] / 1000):
        ax.text(v, y, f" {v:,.0f}", va="center", fontsize=7)
    ax.set_xlabel("Area (thousand hectares)")
    ax.set_title("Burn severity from Sentinel-2 dNBR", loc="left")
    return fig


def products():
    src = "Sentinel-2 L2A, MODIS MOD09A1/MCD64A1, FIRMS, ESA WorldCover. GEE."
    false_colour = {"bands": ["B12", "B8", "B4"], "min": 0.0, "max": 0.4, "gamma": 1.2}
    return [
        {"kind": "chart", "name": "ch34-dryness", "data": dryness, "plot": plot_dryness,
         "caption": "Monthly forest NDMI (MODIS, 500 m) minus the 2014-2018 mean for the "
                    "same month. Negative bars mean less water in the canopy than usual."},
        {"kind": "map", "name": "ch34-pre", "image": pre.clip(aoi), "region": aoi,
         "vis": false_colour, "title": "Before: summer 2018-19 (SWIR, NIR, red)",
         "source": src, "caption": "Pre-fire Sentinel-2 median, December 2018 to January "
                                   "2019. Healthy forest is green in this band combination."},
        {"kind": "map", "name": "ch34-post", "image": post.clip(aoi), "region": aoi,
         "vis": false_colour, "title": "After: February-March 2020 (SWIR, NIR, red)",
         "source": src, "caption": "Post-fire median, late February to March 2020. Burned "
                                   "forest turns red-brown: SWIR up, NIR down."},
        {"kind": "map", "name": "ch34-progression", "image": days, "region": aoi,
         "vis": {"min": 50, "max": 160, "palette": ["ffffb2", "fd8d3c", "e31a1c", "4a1486"]},
         "legend": "Days after 1 September 2019 (MODIS MCD64A1 burn date)",
         "title": "When each place burned", "source": src,
         "caption": "Burn date from MODIS MCD64A1 at 500 m. Day 56 is 26 October 2019; "
                    "day 100 is 9 December; day 130 is 8 January 2020."},
        {"kind": "chart", "name": "ch34-hotspots", "data": hotspots, "plot": plot_hotspots,
         "caption": "Daily count of 1 km MODIS active-fire pixels (FIRMS) in the study "
                    "rectangle. Smoke and cloud hide some fire on some days."},
        {"kind": "map", "name": "ch34-severity", "image": severity, "region": aoi,
         "vis": {"min": 0, "max": 6, "palette": [c[1].lstrip("#") for c in CLASSES]},
         "classes": CLASSES, "title": "Burn severity, dNBR with USGS classes",
         "source": src,
         "caption": "dNBR (x1000) from the two Sentinel-2 medians, classed with the "
                    "Key and Benson breaks. Uncalibrated for this forest type."},
        {"kind": "chart", "name": "ch34-severity-area", "data": by_class,
         "plot": plot_severity,
         "caption": "Area per severity class inside the study rectangle, at 20 m."},
        {"kind": "table", "name": "ch34-agreement", "data": agreement_frame,
         "columns": ["measure", "hectares"], "floatfmt": ",.2f",
         "caption": "dNBR 'low severity or worse' against the MODIS burned-area "
                    "product, both on the 500 m MODIS grid. The last row is a share, "
                    "not hectares."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(by_class.getInfo())
