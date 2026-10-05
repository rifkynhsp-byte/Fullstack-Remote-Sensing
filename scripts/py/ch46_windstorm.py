#| title: Windstorm damage to forest: Cyclone Seroja, 2021 (Python)
#| description: Forest damage from Tropical Cyclone Seroja in Nusa Tenggara Timur, measured as a drop in canopy moisture (NDMI) beyond the normal season, checked with Sentinel-1 radar and summarised per 1 km block.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 46 | Wind damage, separated from the season.

Seroja struck Nusa Tenggara Timur on 4-5 April 2021, at the turn from wet to
dry season. Leaves dry out every April anyway, so a simple before/after drop
would blame the wind for the season. The fix is a baseline year:

    anomaly = (after - before, 2021) - (after - before, 2020)

    index   NDMI = (NIR - SWIR1) / (NIR + SWIR1), canopy water; also NDVI
    before  1 Feb - 31 Mar,  after 10 Apr - 31 May, Sentinel-2 L2A, clear pixels
    forest  ESA WorldCover 2021 tree cover
    check   Sentinel-1 VH change, same windows, same baseline logic

The approach follows the author's wind-damage script (pre/post indices,
summarised per stand), with the baseline added.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ISLANDS = {"Rote": [122.85, -10.95, 123.45, -10.60],
           "Sumba (east)": [119.90, -10.10, 120.60, -9.60],
           "West Timor (Kupang)": [123.60, -10.40, 124.30, -9.90]}
rote = ee.Geometry.Rectangle(ISLANDS["Rote"], None, False)
trees = ee.Image("ESA/WorldCover/v200/2021").select("Map").eq(10)


def s2_index(a, b, box):
    def prep(i):
        clear = i.select("SCL").remap([4, 5], [1, 1], 0)
        return (i.normalizedDifference(["B8", "B11"]).rename("ndmi")
                .addBands(i.normalizedDifference(["B8", "B4"]).rename("ndvi"))
                .updateMask(clear))
    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(box)
            .filterDate(a, b).filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
            .map(prep).median())


def change(year, box):
    return s2_index(f"{year}-04-10", f"{year}-05-31", box).subtract(
        s2_index(f"{year}-02-01", f"{year}-03-31", box))


def anomaly(box):
    # Composites have no native projection; give them Sentinel-2's 20 m grid.
    return (change(2021, box).subtract(change(2020, box)).updateMask(trees)
            .setDefaultProjection("EPSG:4326", None, 20))


def s1_change(year, box):
    vh = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(box)
          .filter(ee.Filter.eq("instrumentMode", "IW")).select("VH"))
    lin = lambda c: c.map(lambda i: ee.Image(10).pow(i.divide(10))).mean().log10().multiply(10)
    return (lin(vh.filterDate(f"{year}-04-10", f"{year}-05-31"))
            .subtract(lin(vh.filterDate(f"{year}-02-01", f"{year}-03-31"))))


def island_table():
    rows = []
    for name, b in ISLANDS.items():
        box = ee.Geometry.Rectangle(b, None, False)
        a = anomaly(box).select("ndmi")
        red = lambda img, r: img.reduceRegion(r, box, 30, maxPixels=1e10, tileScale=8).getInfo()
        med = list(red(a, ee.Reducer.median()).values())[0]
        hit = list(red(a.lt(-0.1), ee.Reducer.mean()).values())[0]
        ha = list(red(ee.Image.pixelArea().divide(1e4).updateMask(a.lt(-0.1)),
                      ee.Reducer.sum()).values())[0]
        s = {"anom_median": med, "hit_mean": hit, "ha_sum": ha}
        r = s1_change(2021, box).subtract(s1_change(2020, box)).updateMask(trees) \
            .reduceRegion(ee.Reducer.median(), box, 60, maxPixels=1e10, tileScale=8).getInfo()
        rows.append({"island": name, "median_NDMI_anomaly": s["anom_median"],
                     "share_forest_below_-0.1": s["hit_mean"], "forest_ha_below_-0.1": s["ha_sum"],
                     "median_VH_anomaly_dB": list(r.values())[0]})
    return pd.DataFrame(rows)


rote_pixels = (change(2020, rote).select("ndmi").rename("y2020")
               .addBands(change(2021, rote).select("ndmi").rename("y2021"))
               .updateMask(trees)
               .sample(region=rote, scale=30, numPixels=6000, seed=4, tileScale=4))


def plot_rote(df):
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    bins = np.linspace(-0.5, 0.3, 60)
    ax.hist(df.y2020, bins, color="#9aa5b1", alpha=0.7, density=True, label="2020 (no cyclone)")
    ax.hist(df.y2021, bins, color="#c0392b", alpha=0.6, density=True, label="2021 (Seroja)")
    ax.axvline(0, color="#1f2933", lw=0.8)
    ax.set_xlabel("NDMI change, Feb-Mar to mid Apr-May (forest pixels, Rote)")
    ax.set_title("The same season, a different year: the whole distribution shifts",
                 loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


# Per-block summary (the "per stand" step): mean anomaly in 1 km blocks of forest
blocks = (anomaly(rote).select("ndmi")
          .reduceResolution(ee.Reducer.mean(), False, 4096)      # 1 km = 2,500 pixels of 20 m
          .reproject(ee.Projection("EPSG:32751").atScale(1000)).rename("block"))


# Sensitivity: does the answer depend on the baseline year, the index or the threshold?
BASELINES = [None, 2019, 2020, 2022, 2023]
THRESHOLDS = [-0.03, -0.05, -0.075, -0.1, -0.15, -0.2]
timor = ee.Geometry.Rectangle(ISLANDS["West Timor (Kupang)"], None, False)


def _anom(box, base, band):
    c = change(2021, box).select(band)
    if base is not None:
        c = c.subtract(change(base, box).select(band))
    return c.updateMask(trees).setDefaultProjection("EPSG:4326", None, 20)


def baseline_frame():
    rows = []
    for band in ("ndmi", "ndvi"):
        for base in BASELINES:
            a = _anom(rote, base, band)
            stack = a.rename("med").addBands(a.lt(-0.1).rename("hit"))
            r = stack.reduceRegion(ee.Reducer.median().combine(ee.Reducer.mean(), "", True), rote, 30,
                                   maxPixels=1e10, tileScale=8).getInfo()
            rows.append({"index": band.upper(), "baseline": "none (raw 2021 change)" if base is None else str(base),
                         "median_anomaly": r["med_median"], "share_below_-0.1": r["hit_mean"]})
    return pd.DataFrame(rows)


def threshold_frame():
    rows = []
    for name, box in (("Rote", rote), ("West Timor", timor)):
        a = _anom(box, 2020, "ndmi")
        stack = ee.Image.cat([a.lt(th).rename(f"t{i}") for i, th in enumerate(THRESHOLDS)])
        r = stack.reduceRegion(ee.Reducer.mean(), box, 30, maxPixels=1e10, tileScale=8).getInfo()
        rows.append([r[f"t{i}"] for i in range(len(THRESHOLDS))])
    d = pd.DataFrame({"threshold": THRESHOLDS, "Rote": rows[0], "West_Timor": rows[1]})
    d["difference"] = d.Rote - d.West_Timor
    d["ratio"] = d.Rote / d.West_Timor
    return d


def plot_threshold(d):
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    ax.plot(d.threshold, d.Rote, "o-", color="#c0392b", label="Rote (cyclone track)")
    ax.plot(d.threshold, d.West_Timor, "o-", color="#9aa5b1", label="West Timor (comparison)")
    ax.set_xlabel("NDMI anomaly threshold for 'damaged'"); ax.set_ylabel("share of forest flagged")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax2 = ax.twinx()
    ax2.plot(d.threshold, d.ratio, "s--", color="#1f2933", ms=4, label="ratio Rote / West Timor")
    ax2.set_ylabel("ratio (higher = cleaner)"); ax2.set_ylim(1, 2.3)
    for a_ in (ax, ax2):
        a_.spines[["top"]].set_visible(False)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=8, loc="upper center")
    ax.set_title("Loose thresholds find more, strict ones find it more cleanly", loc="left", fontsize=10)
    fig.tight_layout()
    return fig

def products():
    return [
        {"kind": "map", "name": "ch46-anomaly", "image": anomaly(rote).select("ndmi").clip(rote),
         "region": rote, "vis": {"min": -0.3, "max": 0.1,
                                 "palette": ["67001f", "d6604d", "fddbc7", "f7f7f7", "4393c3"]},
         "legend": "NDMI change 2021 minus 2020 change (forest)",
         "title": "Canopy moisture lost to Seroja, Rote", "source": "Sentinel-2 L2A; ESA WorldCover. GEE.",
         "caption": "Forest pixels coloured by how much more canopy water they lost across "
                    "April 2021 than across the same weeks of 2020. Red: damage beyond the "
                    "season."},
        {"kind": "map", "name": "ch46-blocks", "image": blocks.clip(rote), "region": rote,
         "vis": {"min": -0.25, "max": 0.0, "palette": ["67001f", "d6604d", "fddbc7", "f7f7f7"]},
         "legend": "Mean anomaly per 1 km block",
         "title": "Damage per block", "source": "This chapter's anomaly map.",
         "caption": "The same anomaly averaged per 1 km block, the unit a forest manager "
                    "would inspect or salvage-log."},
        {"kind": "chart", "name": "ch46-rote", "data": rote_pixels, "plot": plot_rote,
         "caption": "NDMI change across the same weeks in 2020 and 2021, all forest pixels "
                    "sampled on Rote."},
        {"kind": "table", "name": "ch46-islands", "data": island_table,
         "floatfmt": ("", ".3f", ".0%", ",.0f", ".2f"),
         "caption": "Three islands, the same test. The NDMI anomaly is strongest on Rote, "
                    "where the cyclone passed closest. The radar column does not confirm "
                    "it: C-band VH hardly changed anywhere, so radar was no second witness "
                    "here."},
        {"kind": "table", "name": "ch46-baseline", "data": baseline_frame,
         "floatfmt": ("", "", ".3f", ".0%"),
         "caption": "Rote, the same test with each baseline year and with NDVI instead of NDMI. "
                    "Without a baseline the season is blamed on the wind."},
        {"kind": "table", "name": "ch46-threshold", "data": threshold_frame,
         "floatfmt": (".3f", ".0%", ".0%", ".0%", ".1f"),
         "caption": "Share of forest flagged as damaged at each threshold, on Rote and on West Timor."},
        {"kind": "chart", "name": "ch46-threshold-chart", "data": threshold_frame, "plot": plot_threshold, "live": False,
         "caption": "Choosing the damage threshold: the useful one separates the cyclone track from a "
                    "less-hit island, not the one that gives the biggest number."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(island_table())
