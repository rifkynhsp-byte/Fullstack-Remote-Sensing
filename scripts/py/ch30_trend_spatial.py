#| title: Trends and spatial autocorrelation (Python)
#| description: A per-pixel Sen's slope map of land surface temperature over West Java, one pixel's trend with a bootstrap interval, and a semivariogram.

"""
CHAPTER 30 | Two statistics that satellite data needs more than most:
a robust trend (Sen's slope with a Mann-Kendall test) and a check of how far
apart two samples must be before they stop telling you the same thing.

    pip install earthengine-api numpy pandas scipy matplotlib
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

west_java = (ee.FeatureCollection("FAO/GAUL/2025/level2")
             .filter(ee.Filter.eq("GAUL1_NAME", "Jawa Barat")))
region = west_java.geometry()
YEARS = list(range(2003, 2025))

# One image per year: mean daytime LST in the dry season (June to October),
# when enough clear days exist to make a yearly value meaningful.
modis = ee.ImageCollection("MODIS/061/MOD11A2").select("LST_Day_1km")


def dry_season(y):
    img = (modis.filterDate(f"{y}-06-01", f"{y}-11-01").mean()
           .multiply(0.02).subtract(273.15).rename("lst"))
    return img.addBands(ee.Image.constant(y).float().rename("year")).set("year", y)


annual = ee.ImageCollection([dry_season(y) for y in YEARS])

# Sen's slope per pixel: the median of all pairwise slopes, robust to outliers.
sen = annual.select(["year", "lst"]).reduce(ee.Reducer.sensSlope()).select("slope")
per_decade = sen.multiply(10).rename("trend").clip(region)

# One pixel, all the way through, where the arithmetic can be shown.
bandung = ee.Geometry.Point(107.61, -6.91)
series = ee.FeatureCollection(annual.map(lambda img: ee.Feature(None, {
    "year": img.get("year"),
    "lst": img.select("lst").reduceRegion(ee.Reducer.first(), bandung, 1000).get("lst")})))


def trend_table(df):
    """Mann-Kendall (Kendall's tau against time) and Sen's slope with a bootstrap CI."""
    df = df.dropna().sort_values("year")
    x, y = df["year"].to_numpy(float), df["lst"].to_numpy(float)
    tau, p = stats.kendalltau(x, y)
    slope = stats.theilslopes(y, x)[0]
    rng = np.random.default_rng(0)
    boot = []
    for _ in range(2000):                       # resample years with replacement
        i = rng.integers(0, len(x), len(x))
        if len(np.unique(x[i])) > 2:
            boot.append(stats.theilslopes(y[i], x[i])[0])
    lo, hi = np.percentile(boot, [5, 95])
    return pd.DataFrame([{"years": len(x), "kendall_tau": tau, "p_value": p,
                          "sen_slope_C_per_decade": slope * 10,
                          "bootstrap_90pct_low": lo * 10, "bootstrap_90pct_high": hi * 10}])


def plot_trend(df):
    """The pixel's dry-season LST by year, with the Sen line."""
    df = df.dropna().sort_values("year")
    slope, intercept, lo, hi = stats.theilslopes(df["lst"], df["year"])
    fig, ax = plt.subplots(figsize=(6.8, 3.2))
    ax.plot(df["year"], df["lst"], "o-", color="#d55e00", lw=1, ms=4)
    xs = np.array([df["year"].min(), df["year"].max()])
    ax.plot(xs, intercept + slope * xs, color="#1f2933", lw=1.5,
            label=f"Sen's slope {slope * 10:+.2f} °C per decade")
    ax.set_ylabel("Dry-season daytime LST (°C)")
    ax.set_title("Central Bandung, one MODIS pixel", loc="left")
    ax.legend(frameon=False, fontsize=8)
    return fig


# Spatial autocorrelation: how similar are NDVI values at increasing distance?
landsat = (ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
           .merge(ee.ImageCollection("LANDSAT/LC08/C02/T1_L2"))
           .filterBounds(region).filterDate("2024-06-01", "2024-11-01")
           .filter(ee.Filter.lt("CLOUD_COVER", 40)))
ndvi = (landsat.median().select(["SR_B5", "SR_B4"]).multiply(0.0000275).add(-0.2)
        .normalizedDifference(["SR_B5", "SR_B4"]).rename("ndvi"))
basin = ee.Geometry.Rectangle([107.40, -7.10, 107.85, -6.80])     # Bandung basin
ndvi_points = ndvi.sample(region=basin, scale=30, numPixels=900, seed=11, geometries=True)


def semivariogram_frame():
    info = ndvi_points.getInfo()["features"]
    xy = np.array([f["geometry"]["coordinates"] for f in info])
    v = np.array([f["properties"]["ndvi"] for f in info])
    km = np.c_[xy[:, 0] * 111.32 * np.cos(np.radians(-6.95)), xy[:, 1] * 110.57]
    i, j = np.triu_indices(len(v), 1)
    d = np.hypot(*(km[i] - km[j]).T)
    g = 0.5 * (v[i] - v[j]) ** 2
    bins = np.arange(0, 21, 1)
    k = np.digitize(d, bins)
    rows = [{"lag_km": bins[b - 1] + 0.5, "semivariance": g[k == b].mean(),
             "pairs": int((k == b).sum())} for b in range(1, len(bins)) if (k == b).any()]
    return pd.DataFrame(rows).assign(total_variance=v.var())


def plot_semivariogram(df):
    """Semivariance rises with distance until samples stop being related."""
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    ax.plot(df["lag_km"], df["semivariance"], "o-", color="#2166ac")
    ax.axhline(df["total_variance"].iloc[0], color="#9aa5b1", ls="--", lw=1,
               label="variance of all samples (the sill)")
    ax.set_xlabel("Distance between two samples (km)")
    ax.set_ylabel("Semivariance of NDVI")
    ax.set_title("Nearby samples repeat each other", loc="left")
    ax.legend(frameon=False, fontsize=8)
    return fig


def products():
    return [
        {"kind": "map", "name": "ch30-trend-map", "image": per_decade, "region": region.bounds(),
         "vis": {"min": -1.5, "max": 1.5, "palette": ["2166ac", "92c5de", "f7f7f7", "f4a582",
                                                     "b2182b"]},
         "legend": "Sen's slope of dry-season LST, 2003-2024 (°C per decade)",
         "title": "Where the ground warmed, West Java", "source": "MODIS MOD11A2 v6.1. GEE.",
         "caption": ("Per-pixel Sen's slope of dry-season daytime land surface temperature. Warming (red) follows the Bekasi, Karawang and Bogor growth corridor. Read the blue with care: MODIS Terra's overpass has drifted earlier since about 2020, and an earlier overpass alone makes later daytime values cooler. Check against Aqua or Landsat before calling it real cooling.")},
        {"kind": "chart", "name": "ch30-trend-pixel", "data": series, "plot": plot_trend,
         "caption": "One pixel's series, with the Sen line drawn through it."},
        {"kind": "table", "name": "ch30-trend-table", "data": series, "transform": trend_table,
         "floatfmt": (".0f", ".2f", ".3f", ".2f", ".2f", ".2f"),
         "caption": "Mann-Kendall test and Sen's slope for the pixel, with a bootstrap "
                    "90 % interval. Twenty-two points are few: read the interval, not only "
                    "the slope."},
        {"kind": "chart", "name": "ch30-semivariogram", "data": semivariogram_frame,
         "plot": plot_semivariogram,
         "caption": "Semivariogram of Landsat NDVI from 900 random points in the Bandung "
                    "basin. Where the curve levels off, samples stop sharing information: "
                    "that distance is a sensible minimum spacing for training data and "
                    "for cross-validation blocks (chapter “Ground Truth and Sampling Design”)."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(trend_table(pd.DataFrame([f["properties"] for f in series.getInfo()["features"]])))
