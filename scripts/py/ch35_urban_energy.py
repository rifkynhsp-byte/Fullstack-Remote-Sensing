#| title: Urban heat and a solar site screen (Python)
#| description: Land surface temperature of Surabaya by land cover, and a weighted-overlay screen for solar farms on Sumbawa with a test of how much the answer depends on the weights.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 35 | Two city-and-energy questions a planner asks.

    1. Where is the city hottest, and what is there?   Landsat LST x Dynamic World
    2. Where could a solar farm go?                    multi-criteria screen (MCDA)

The screen follows the logic of the author's solar siting tool, rebuilt with
public layers only: ERA5-Land radiation, Copernicus DEM slope, distance to
built-up area (GHSL), exclusions from Dynamic World and WDPA.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Urban heat, Surabaya, dry season 2023
# ---------------------------------------------------------------------------
city = ee.Geometry.Rectangle([112.55, -7.40, 112.85, -7.15], None, False)


def clear_lst(img):
    qa = img.select("QA_PIXEL")
    clear = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
    return (img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15)
            .rename("lst").updateMask(clear))


lst = (ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
       .merge(ee.ImageCollection("LANDSAT/LC08/C02/T1_L2"))
       .filterBounds(city).filterDate("2023-06-01", "2023-11-01")
       .filter(ee.Filter.lt("CLOUD_COVER", 40))
       .map(clear_lst).median().clip(city))

dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(city)
      .filterDate("2023-01-01", "2024-01-01").select("label").mode())
DW_NAMES = {0: "water", 1: "trees", 2: "grass", 3: "flooded vegetation", 4: "crops",
            5: "shrub and scrub", 6: "built", 7: "bare", 8: "snow and ice"}


def lst_by_class():
    g = (lst.addBands(dw.rename("cls"))
         .reduceRegion(ee.Reducer.mean().combine(ee.Reducer.percentile([10, 90]), None, True)
                       .combine(ee.Reducer.count(), None, True).group(1, "cls"),
                       city, 30, maxPixels=1e9, tileScale=4).get("groups").getInfo())
    df = pd.DataFrame([{"land_cover": DW_NAMES[int(d["cls"])], "pixels": d["count"],
                        "mean_C": d["mean"], "p10_C": d["p10"], "p90_C": d["p90"]} for d in g])
    return df[df.pixels > 500].sort_values("mean_C").reset_index(drop=True)


lst_points = lst.addBands(dw.rename("cls")).sample(region=city, scale=30, numPixels=4500,
                                                   seed=2, dropNulls=True, tileScale=4)


def plot_lst_by_class(df):
    df = df.assign(land_cover=df["cls"].astype(int).map(DW_NAMES))
    keep = df["land_cover"].value_counts()
    keep = keep[keep > 50].index
    order = (df[df.land_cover.isin(keep)].groupby("land_cover")["lst"].median()
             .sort_values().index.tolist())
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.boxplot([df.loc[df.land_cover == c, "lst"] for c in order], vert=False,
               tick_labels=order, showfliers=False, widths=0.55,
               medianprops={"color": "#c0392b", "lw": 2})
    rng = np.random.default_rng(0)
    for i, c in enumerate(order, 1):
        v = df.loc[df.land_cover == c, "lst"].sample(min(150, (df.land_cover == c).sum()),
                                                     random_state=0)
        ax.scatter(v, i + rng.uniform(-0.2, 0.2, len(v)), s=3, color="#6b7680", alpha=0.35)
    ax.set_xlabel("Land surface temperature, dry season 2023 (°C)")
    ax.set_title("Built-up land and dry scrub run hottest; water and trees stay coolest", loc="left",
                 fontsize=10)
    return fig


# ---------------------------------------------------------------------------
# 2. Solar farm screen, Sumbawa
# ---------------------------------------------------------------------------
island = ee.Geometry.Rectangle([116.75, -9.10, 118.20, -8.35], None, False)
UTM = ee.Projection("EPSG:32750").atScale(100)

# Criterion 1: sunshine. ERA5-Land monthly sums for 2023 -> kWh per m2 per year.
ghi = (ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").filterDate("2023-01-01",
                                                                    "2024-01-01")
       .select("surface_solar_radiation_downwards_sum").sum().divide(3.6e6).rename("ghi"))
# Criterion 2: slope in degrees from the Copernicus 30 m DEM.
dem = (ee.ImageCollection("COPERNICUS/DEM/GLO30").filterBounds(island).select("DEM")
       .mosaic().setDefaultProjection("EPSG:4326", None, 30))
slope = ee.Terrain.slope(dem).rename("slope")
# Criterion 3: distance to built-up land (a proxy for roads, grid and demand).
built = (ee.Image("JRC/GHSL/P2023A/GHS_BUILT_S/2020").select("built_surface").gt(500)
         .selfMask())
dist_km = (built.unmask(0).reproject(UTM).fastDistanceTransform(256).sqrt()
           .multiply(100).divide(1000).rename("dist_km"))

# Exclusions: water, trees, flooded vegetation, built-up, protected areas, steep land.
dw_island = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(island)
             .filterDate("2023-01-01", "2024-01-01").select("label").mode())
protected = (ee.FeatureCollection("WCMC/WDPA/current/polygons").filterBounds(island)
             .reduceToImage(["WDPAID"], ee.Reducer.first()).gt(0).unmask(0))
land = dem.gt(0)
allowed = (land.And(dw_island.remap([0, 1, 3, 6], [0, 0, 0, 0], 1).eq(1))
           .And(protected.eq(0)).And(slope.lte(15)))

gstats = ghi.reduceRegion(ee.Reducer.percentile([5, 95]), island, 10000).getInfo()
G_LO, G_HI = gstats["ghi_p5"], gstats["ghi_p95"]

scores = {
    "sun": ghi.subtract(G_LO).divide(G_HI - G_LO).clamp(0, 1),
    "flat": slope.divide(10).multiply(-1).add(1).clamp(0, 1),        # 1 at 0°, 0 at 10°
    "near": dist_km.divide(20).multiply(-1).add(1).clamp(0, 1),      # 1 at 0 km, 0 at 20 km
}
BASE = {"sun": 0.4, "flat": 0.3, "near": 0.3}


def suitability(w):
    s = ee.Image.cat([scores[k].multiply(v) for k, v in w.items()]).reduce(ee.Reducer.sum())
    return s.updateMask(allowed).rename("score")


def cutoffs(score):
    """Score at the 50th, 75th and 90th percentile of allowed land."""
    p = score.reduceRegion(ee.Reducer.percentile([50, 75, 90]), island, 100,
                           maxPixels=1e10, tileScale=8).getInfo()
    return p["score_p50"], p["score_p75"], p["score_p90"]


base = suitability(BASE)
P50, P75, P90 = cutoffs(base)
classes = base.gte(P50).add(base.gte(P75)).add(base.gte(P90)).rename("cls")


def mcda_table():
    g = (ee.Image.pixelArea().divide(1e6).addBands(classes)
         .reduceRegion(ee.Reducer.sum().group(1, "cls"), island, 100, maxPixels=1e10,
                       tileScale=8).get("groups").getInfo())
    names = {0: "low: bottom half", 1: "fair: 50th to 75th percentile",
             2: "good: 75th to 90th", 3: "best: top 10 %"}
    lows = {0: base_min(), 1: P50, 2: P75, 3: P90}
    return pd.DataFrame([{"class": names[int(d["cls"])], "score_from": lows[int(d["cls"])],
                          "area_km2": d["sum"]} for d in g])


def base_min():
    return base.reduceRegion(ee.Reducer.min(), island, 100, maxPixels=1e10,
                             tileScale=8).getInfo()["score"]


WEIGHTS = {"base 0.4 / 0.3 / 0.3": BASE,
           "sun first 0.6 / 0.2 / 0.2": {"sun": 0.6, "flat": 0.2, "near": 0.2},
           "flat first 0.2 / 0.6 / 0.2": {"sun": 0.2, "flat": 0.6, "near": 0.2},
           "access first 0.2 / 0.2 / 0.6": {"sun": 0.2, "flat": 0.2, "near": 0.6},
           "equal 1/3 each": {"sun": 1 / 3, "flat": 1 / 3, "near": 1 / 3}}


def sensitivity_table():
    """Top 10 % of allowed land under each weight set, compared with the base."""
    best0 = base.gte(P90)
    rows = []
    for name, w in WEIGHTS.items():
        sc = suitability(w)
        best = sc.gte(cutoffs(sc)[2])
        area = ee.Image.pixelArea().divide(1e6)
        a = (area.updateMask(best.And(best0)).rename("both")
             .addBands(area.updateMask(best.Or(best0)).rename("either"))
             .reduceRegion(ee.Reducer.sum(), island, 100, maxPixels=1e10, tileScale=8)
             .getInfo())
        rows.append({"weights (sun / flat / access)": name,
                     "overlap_with_base": a["both"] / a["either"]})
    return pd.DataFrame(rows)


# How many of the five weight sets put each pixel in their top 10 %?
def robust_count():
    imgs = []
    for w in WEIGHTS.values():
        sc = suitability(w)
        imgs.append(sc.gte(cutoffs(sc)[2]).unmask(0))
    return ee.ImageCollection(imgs).sum().updateMask(allowed).rename("n")


def robust_table():
    n = robust_count()
    g = (ee.Image.pixelArea().divide(1e6).addBands(n)
         .reduceRegion(ee.Reducer.sum().group(1, "n"), island, 100, maxPixels=1e10, tileScale=8)
         .get("groups").getInfo())
    d = pd.DataFrame([{"weight sets agreeing (of 5)": int(r["n"]), "area_km2": r["sum"]} for r in g])
    d = d[d["weight sets agreeing (of 5)"] > 0].sort_values("weight sets agreeing (of 5)", ascending=False)
    d["cumulative_km2"] = d.area_km2.cumsum()
    return d.reset_index(drop=True)


# Does tree cover cool the city? Sentinel-2 NDVI of the same dry season, binned against LST.
ndvi_city = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(city)
             .filterDate("2023-06-01", "2023-11-01").filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
             .map(lambda i: i.normalizedDifference(["B8", "B4"]).updateMask(i.select("SCL").remap([4, 5, 6], [1, 1, 1], 0)))
             .median().rename("ndvi"))
green_points = (lst.addBands(ndvi_city).addBands(dw.rename("cls"))
                .sample(region=city, scale=30, numPixels=4500, seed=7, dropNulls=True, tileScale=4))


def green_frame(df=None):
    from scipy import stats
    if df is None:
        df = ee_to_df(green_points)
    df = df[df.cls != 0]  # water is cool for another reason; leave it out
    bins = np.arange(0, 0.85, 0.1)
    df = df.assign(bin=pd.cut(df.ndvi, bins))
    g = df.groupby("bin", observed=True)["lst"].agg(["median", "count"]).reset_index()
    g["ndvi_mid"] = [b.mid for b in g.bin]
    all_fit = stats.linregress(df.ndvi, df.lst)
    built = df[df.cls == 6]
    b_fit = stats.linregress(built.ndvi, built.lst)
    green_frame.fits = {"all land": (all_fit.slope / 10, len(df)), "built pixels only": (b_fit.slope / 10, len(built))}
    return g[g["count"] >= 30][["ndvi_mid", "median", "count"]]


def ee_to_df(fc):
    return pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]])


def green_fit_table():
    if not hasattr(green_frame, "fits"):
        green_frame()
    return pd.DataFrame([{"pixels": k, "°C per +0.1 NDVI": v[0], "n": v[1]} for k, v in green_frame.fits.items()])


def plot_green(g):
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.plot(g.ndvi_mid, g["median"], "o-", color="#1a9641")
    for x, y, n in zip(g.ndvi_mid, g["median"], g["count"]):
        ax.annotate(f"{n}", (x, y), xytext=(0, 6), textcoords="offset points", fontsize=7, ha="center", color="#6b7680")
    ax.set_xlabel("NDVI (dry season 2023, Sentinel-2)"); ax.set_ylabel("median LST (°C)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Greener pixels are cooler, by several degrees", loc="left", fontsize=10)
    fig.tight_layout()
    return fig


SUIT = ["d7191c", "fdae61", "a6d96a", "1a9641"]


def products():
    return [
        {"kind": "map", "name": "ch35-lst-map", "image": lst, "region": city,
         "vis": {"min": 28, "max": 46, "palette": ["313695", "74add1", "e0f3f8", "fee090",
                                                   "f46d43", "a50026"]},
         "legend": "Land surface temperature, June-October 2023 median (°C)",
         "title": "Surabaya's surface heat", "source": "Landsat 8/9 Collection 2 L2. GEE.",
         "caption": "Median daytime land surface temperature (about 10:00 local time) "
                    "over the 2023 dry season. This is the temperature of surfaces, "
                    "not of the air people breathe; the two differ most at midday."},
        {"kind": "table", "name": "ch35-lst-table", "data": lst_by_class,
         "floatfmt": ("", ",.0f", ".1f", ".1f", ".1f"),
         "caption": "Surface temperature by Dynamic World land cover (2023 mode). "
                    "p10 and p90 show the spread inside each class."},
        {"kind": "chart", "name": "ch35-lst-chart", "data": lst_points,
         "plot": plot_lst_by_class,
         "caption": "The same comparison for a random sample of about 4,500 pixels: boxes for "
                    "the middle half, dots for individual pixels."},
        {"kind": "map", "name": "ch35-mcda-map", "image": classes.clip(island),
         "region": island, "vis": {"min": 0, "max": 3, "palette": SUIT},
         "classes": [("low", "#d7191c"), ("fair", "#fdae61"), ("good", "#a6d96a"),
                     ("best", "#1a9641")],
         "title": "Where a solar farm could go, Sumbawa",
         "source": "ERA5-Land, Copernicus DEM, GHSL 2023A, Dynamic World, WDPA. GEE.",
         "caption": "Weighted overlay: sunshine 0.4, flat ground 0.3, near built-up land "
                    "0.3. Blank land is excluded (forest, water, built-up, protected, "
                    "slopes over 15°). The straight-edged blocks come from the 9 km ERA5-Land "
                    "cells; a finer solar resource layer would remove them. A screen for "
                    "where to look, not a site decision."},
        {"kind": "table", "name": "ch35-mcda-table", "data": mcda_table,
         "floatfmt": ("", ".2f", ",.0f"),
         "caption": "Classes are ranks of the allowed land, so 'best' always means the "
                    "top 10 %. The score column shows where each class starts."},
        {"kind": "table", "name": "ch35-sensitivity", "data": sensitivity_table,
         "floatfmt": ("", ".2f"),
         "caption": "The top 10 % of allowed land under five sets of weights, compared "
                    "with the base set. Overlap is intersection over union: 1 means the "
                    "same land, 0 means none in common."},
        {"kind": "map", "name": "ch35-robust-map", "image": robust_count().selfMask().clip(island), "region": island,
         "vis": {"min": 1, "max": 5, "palette": ["fee5d9", "fcae91", "fb6a4a", "de2d26", "a50f15"]},
         "legend": "Weight sets that put the pixel in their top 10 %",
         "title": "The robust answer: land that is 'best' whatever the weights",
         "source": "This chapter's five weight sets.",
         "caption": "Dark red land is in the top 10 % under all five weight sets: the place to start a site study. "
                    "Pale land is 'best' only under one opinion about what matters."},
        {"kind": "table", "name": "ch35-robust", "data": robust_table, "floatfmt": ("", ",.0f", ",.0f"),
         "caption": "Area by the number of weight sets that agree it is in the top 10 %."},
        {"kind": "chart", "name": "ch35-green", "data": green_frame, "plot": plot_green, "live": False,
         "caption": "Median surface temperature in bins of NDVI, Surabaya, dry season 2023 (water excluded). "
                    "Small numbers: pixels per bin."},
        {"kind": "table", "name": "ch35-green-fit", "data": green_fit_table, "floatfmt": ("", ".2f", ",.0f"),
         "caption": "Slope of a straight line through the pixels: change in surface temperature per 0.1 more NDVI."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(sensitivity_table())
