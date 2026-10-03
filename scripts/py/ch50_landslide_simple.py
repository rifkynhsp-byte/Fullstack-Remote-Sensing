#| title: A first landslide susceptibility map, and an honest test of it (Python)
#| description: A weighted overlay of slope, rainfall and land cover for West Java, tested against the NASA Global Landslide Catalog with ROC AUC, against slope alone, and with the location uncertainty of the catalogue taken into account.

"""
CHAPTER 50 | The simplest landslide map worth making.

    score each factor 1 (low) to 5 (high), then add with weights:

    factor      1         2          3          4          5         weight
    slope (°)   < 8       8-15       15-25      25-35      > 35      0.5
    rain (mm)   < 2,000   2,000-2,500 2,500-3,000 3,000-3,500 > 3,500 0.3
    land cover  -         trees,     cropland   grass,     bare      0.2
                          built                 shrub

These classes and weights are choices made for teaching, not published
values. The test decides whether they are any good:
    NASA Global Landslide Catalog points in West Java (1970-2019), each with a
    location accuracy (1 km, 5 km ...). Each point is compared with the mean
    score within its accuracy radius; random points get the same radii.
    ROC AUC: 0.5 = no better than chance, 1 = perfect.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([106.3, -7.9, 108.9, -6.3], None, False)        # West Java
dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").filterBounds(aoi).select("DEM").mosaic() \
    .setDefaultProjection("EPSG:4326", None, 30)
slope = ee.Terrain.slope(dem)
rain = (ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD").select("precipitation")
        .filterDate("2001-01-01", "2021-01-01").sum().divide(20))
wc = ee.Image("ESA/WorldCover/v200/2021").select("Map")
land = wc.neq(80)


def classes(img, breaks):
    out = ee.Image(1)
    for k, b in enumerate(breaks, start=2):
        out = out.where(img.gte(b), k)
    return out


s_slope = classes(slope, [8, 15, 25, 35])
s_rain = classes(rain, [2000, 2500, 3000, 3500])
s_lc = wc.remap([10, 50, 40, 20, 30, 60], [2, 2, 3, 4, 4, 5], 2)
score = (s_slope.multiply(0.5).add(s_rain.multiply(0.3)).add(s_lc.multiply(0.2))
         .updateMask(land).rename("score").clip(aoi))

RADIUS = {"exact": 250, "1km": 1000, "5km": 5000}
glc = (ee.FeatureCollection("projects/sat-io/open-datasets/events/global_landslide_1970-2019")
       .filterBounds(aoi).filter(ee.Filter.inList("location_a", list(RADIUS))))


def test_frame():
    pts = glc.getInfo()["features"]
    rows = []
    rng = np.random.default_rng(1)
    lon0, lat0, lon1, lat1 = 106.3, -7.9, 108.9, -6.3
    feats = []
    for f in pts:
        acc = f["properties"]["location_a"]
        lon, lat = f["geometry"]["coordinates"]
        feats.append(ee.Feature(ee.Geometry.Point([lon, lat]).buffer(RADIUS[acc]),
                                {"kind": 1, "acc": acc}))
        for _ in range(4):                                   # 4 random places per landslide
            feats.append(ee.Feature(ee.Geometry.Point([rng.uniform(lon0, lon1),
                                                       rng.uniform(lat0, lat1)]).buffer(RADIUS[acc]),
                                    {"kind": 0, "acc": acc}))
    # A second control: random places within 2 km of built-up land, where a
    # landslide would be noticed and reported. The catalogue comes from news.
    utm = ee.Projection("EPSG:32748").atScale(100)
    near = (wc.eq(50).reproject(utm).fastDistanceTransform(32).sqrt().multiply(100)
            .lte(2000).rename("near").toInt())
    near_pts = (near.selfMask().stratifiedSample(numPoints=4 * len(pts), classBand="near",
                                                 region=aoi, scale=100, seed=7,
                                                 geometries=True).getInfo()["features"])
    accs = [f["properties"]["location_a"] for f in pts]
    for k, f in enumerate(near_pts):
        acc = accs[k % len(accs)]
        feats.append(ee.Feature(ee.Geometry.Point(f["geometry"]["coordinates"]).buffer(RADIUS[acc]),
                                {"kind": 2, "acc": acc}))
    stack = score.addBands(slope.rename("slope").updateMask(land))
    fc = stack.reduceRegions(ee.FeatureCollection(feats), ee.Reducer.mean(), 90, tileScale=8)
    df = pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]])
    return df.dropna(subset=["score"])


def auc(y, s):
    """Rank-based ROC AUC (Mann-Whitney)."""
    r = pd.Series(s).rank().to_numpy()
    n1 = (y == 1).sum(); n0 = (y == 0).sum()
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def auc_table(df):
    rows = []
    for ctrl, ctrl_label in [(0, "random anywhere"), (2, "random near settlements")]:
        for label, d in [("exact, 1 km, 5 km", df),
                         ("1 km or better", df[df.acc.isin(["exact", "1km"])])]:
            d = d[d.kind.isin([1, ctrl])]
            y = (d.kind == 1).astype(int).to_numpy()
            rows.append({"landslides located to": label, "compared with": ctrl_label,
                         "landslides": int(y.sum()),
                         "AUC_weighted_overlay": auc(y, d.score.to_numpy()),
                         "AUC_slope_alone": auc(y, d.slope.to_numpy())})
    return pd.DataFrame(rows)


def plot_scores(df):
    fig, ax = plt.subplots(figsize=(6.8, 3.4))
    bins = np.linspace(df.score.min(), df.score.max(), 25)
    ax.hist(df[df.kind == 0].score, bins, density=True, color="#9aa5b1", alpha=0.6,
            label="random places")
    ax.hist(df[df.kind == 2].score, bins, density=True, histtype="step", color="#2a78d6", lw=1.8,
            label="random places near settlements")
    ax.hist(df[df.kind == 1].score, bins, density=True, color="#c0392b", alpha=0.6,
            label="recorded landslides")
    ax.set_xlabel("Mean susceptibility score within the location radius")
    ax.set_title("Do recorded landslides sit on higher scores?", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


# The same overlay where the inventory is good: Iburi, Hokkaido, 2018 earthquake
# landslides mapped as polygons (Chapter on objects and landslides).
iburi = ee.Geometry.Rectangle([141.93, 42.70, 142.05, 42.80])
inventory = ee.FeatureCollection("users/rifkynauvalhsp/IburiLandslideInventory/trainingset")


def iburi_table():
    dem_i = (ee.ImageCollection("COPERNICUS/DEM/GLO30").filterBounds(iburi).select("DEM")
             .mosaic().setDefaultProjection("EPSG:4326", None, 30))
    sl = ee.Terrain.slope(dem_i)
    sc = (classes(sl, [8, 15, 25, 35]).multiply(0.5)
          .add(classes(rain, [2000, 2500, 3000, 3500]).multiply(0.3))
          .add(wc.remap([10, 50, 40, 20, 30, 60], [2, 2, 3, 4, 4, 5], 2).multiply(0.2)))
    truth = ee.Image(0).paint(inventory, 1).rename("truth")
    pts = (sc.rename("score").addBands(sl.rename("slope")).addBands(truth)
           .stratifiedSample(numPoints=800, classBand="truth", region=iburi, scale=30, seed=2,
                             tileScale=4))
    d = pd.DataFrame([f["properties"] for f in pts.getInfo()["features"]]).dropna()
    y = d.truth.to_numpy()
    return pd.DataFrame([{"inventory": "Iburi 2018, mapped polygons", "landslide_pixels": int(y.sum()),
                          "AUC_weighted_overlay": auc(y, d.score.to_numpy()),
                          "AUC_slope_alone": auc(y, d.slope.to_numpy())}])


# Sensitivity on the good inventory: the weights, and the optimum slope threshold.
_iburi = {}
SPLIT_LON = 141.99                                 # west half tunes, east half tests


def iburi_sample():
    if "d" not in _iburi:
        dem_i = (ee.ImageCollection("COPERNICUS/DEM/GLO30").filterBounds(iburi).select("DEM")
                 .mosaic().setDefaultProjection("EPSG:4326", None, 30))
        sl = ee.Terrain.slope(dem_i)
        img = ee.Image.cat([sl.rename("slope"), classes(sl, [8, 15, 25, 35]).rename("c_slope"),
                            classes(rain, [2000, 2500, 3000, 3500]).rename("c_rain"),
                            wc.remap([10, 50, 40, 20, 30, 60], [2, 2, 3, 4, 4, 5], 2).rename("c_lc"),
                            ee.Image(0).paint(inventory, 1).rename("truth"), ee.Image.pixelLonLat().select("longitude")])
        pts = img.stratifiedSample(numPoints=1500, classBand="truth", region=iburi, scale=30, seed=11, tileScale=4)
        _iburi["d"] = pd.DataFrame([f["properties"] for f in pts.getInfo()["features"]]).dropna()
    return _iburi["d"]


def weight_frame():
    d = iburi_sample(); y = d.truth.to_numpy()
    rows = []
    for w in np.round(np.arange(0, 1.01, 0.1), 1):
        s = w * d.c_slope + (1 - w) * 0.6 * d.c_rain + (1 - w) * 0.4 * d.c_lc
        rows.append({"slope_weight": w, "rain_weight": round((1 - w) * 0.6, 2), "cover_weight": round((1 - w) * 0.4, 2),
                     "AUC": auc(y, s.to_numpy())})
    rows.append({"slope_weight": "slope in degrees, unclassed", "rain_weight": 0, "cover_weight": 0,
                 "AUC": auc(y, d.slope.to_numpy())})
    return pd.DataFrame(rows)


def threshold_frame():
    d = iburi_sample()
    rows = []
    for th in np.arange(5, 45.1, 2.5):
        r = {"slope_threshold": th}
        for half, dd in (("west", d[d.longitude < SPLIT_LON]), ("east", d[d.longitude >= SPLIT_LON])):
            pos, neg = dd[dd.truth == 1], dd[dd.truth == 0]
            tpr, fpr = (pos.slope >= th).mean(), (neg.slope >= th).mean()
            r.update({f"hit_rate_{half}": tpr, f"false_alarm_{half}": fpr, f"J_{half}": tpr - fpr})
        rows.append(r)
    return pd.DataFrame(rows)


def threshold_table(d):
    b = d.loc[d.J_west.idxmax()]
    e = d.loc[d.J_east.idxmax()]
    return pd.DataFrame([
        {"step": "tuned on the west half", "threshold_deg": b.slope_threshold, "hit_rate": b.hit_rate_west,
         "false_alarm": b.false_alarm_west, "J": b.J_west},
        {"step": "same threshold, tested on the east half", "threshold_deg": b.slope_threshold,
         "hit_rate": b.hit_rate_east, "false_alarm": b.false_alarm_east, "J": b.J_east},
        {"step": "best possible on the east half (for reference)", "threshold_deg": e.slope_threshold,
         "hit_rate": e.hit_rate_east, "false_alarm": e.false_alarm_east, "J": e.J_east}])


def plot_threshold(d):
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.plot(d.slope_threshold, d.J_west, "o-", color="#2a78d6", ms=4, label="west half (tuning)")
    ax.plot(d.slope_threshold, d.J_east, "s--", color="#c0392b", ms=4, label="east half (testing)")
    b = d.loc[d.J_west.idxmax()]
    ax.axvline(b.slope_threshold, color="#6b7680", lw=0.8)
    ax.set_xlabel("slope threshold for 'susceptible' (°)"); ax.set_ylabel("Youden J = hit rate - false alarm rate")
    ax.spines[["top", "right"]].set_visible(False); ax.legend(frameon=False, fontsize=8)
    ax.set_title("The optimum slope threshold, and how well it travels", loc="left", fontsize=10)
    fig.tight_layout()
    return fig


def products():
    return [
        {"kind": "map", "name": "ch50-score", "image": score, "region": aoi,
         "vis": {"min": 1.5, "max": 4.5, "palette": ["1a9850", "a6d96a", "ffffbf", "fdae61", "d73027"]},
         "legend": "Landslide susceptibility score (weighted overlay)",
         "title": "A first susceptibility map, West Java",
         "source": "Copernicus DEM; CHIRPS 2001-2020; ESA WorldCover. GEE.",
         "caption": "Slope (0.5), annual rainfall (0.3) and land cover (0.2), each scored 1 to 5."},
        {"kind": "chart", "name": "ch50-scores", "data": test_frame, "plot": plot_scores,
         "caption": "Scores around recorded landslides against random places with the same "
                    "location radii."},
        {"kind": "table", "name": "ch50-auc", "data": test_frame, "transform": auc_table,
         "floatfmt": ("", "", ".0f", ".2f", ".2f"),
         "caption": "ROC AUC of the overlay and of slope alone against the NASA catalogue, "
                    "with two kinds of control places."},
        {"kind": "table", "name": "ch50-iburi", "data": iburi_table,
         "floatfmt": ("", ",.0f", ".2f", ".2f"),
         "caption": "The same scores tested where landslides were mapped as polygons."},
        {"kind": "table", "name": "ch50-weights", "data": weight_frame, "floatfmt": ("", "", "", ".3f"),
         "caption": "Iburi: AUC of the overlay as the slope weight changes (rain and cover share the rest 60:40), "
                    "and of slope alone without classes."},
        {"kind": "table", "name": "ch50-threshold", "data": threshold_frame, "transform": threshold_table,
         "floatfmt": ("", ".1f", ".0%", ".0%", ".2f"),
         "caption": "Iburi: the slope threshold that best separates landslide from stable pixels, chosen on one "
                    "half of the area and tested on the other."},
        {"kind": "chart", "name": "ch50-threshold-chart", "data": threshold_frame, "plot": plot_threshold, "live": False,
         "caption": "Youden J for every slope threshold, on the half used for tuning and on the held-out half."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(auc_table(test_frame()))
