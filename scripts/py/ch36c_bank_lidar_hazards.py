#| title: Thesis starters 7-12: LiDAR and hazards (Python)
#| description: First experiments for the LiDAR and hazard topics: tree-detection sensitivity, height-map disagreement, LiDAR plot placement in embedding space, landslide model transfer, building-footprint gaps, and a radar time series at a landslide event.

"""
CHAPTER 36 | Starters 7 to 12.

    T7   stems under canopy        tree count against the variable-window rule (lidR example)
    T8   stretching LiDAR plots    ETH minus GLAD canopy height, Jambi
    T9   placing LiDAR samples     random vs embedding-stratified plots, coverage in feature space
    T10  landslide transfer        Iburi: train west, test east, against a random split
    T11  missing footprints        Microsoft vs Google Open Buildings in seven towns
    T12  radar before a landslide  Sentinel-1 VV inside and outside Iburi landslides, 2018
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from skimage.feature import peak_local_max

from ch32_lidar_trees import CELL, grid_max, read


# ---------------------------------------------------------------------------
# T7. One parameter, many tree counts
# ---------------------------------------------------------------------------
def window_frame():
    x, y, z, _, _ = read("MixedConifer.laz")
    chm = grid_max(x, y, z, CELL)
    chm = np.where(np.isnan(chm), ndi.maximum_filter(np.nan_to_num(chm), 3), chm)
    chm = ndi.gaussian_filter(chm, 0.6)
    cand = peak_local_max(chm, min_distance=1, threshold_abs=2.0)
    rows = []
    for a in [0.03, 0.05, 0.07, 0.09, 0.11, 0.13]:
        keep = 0
        for r, c in cand:
            h = chm[r, c]
            rad = int(np.ceil((a * h + 2) / 2 / CELL))
            if h >= chm[max(r - rad, 0): r + rad + 1, max(c - rad, 0): c + rad + 1].max():
                keep += 1
        rows.append({"window_slope_a": a, "trees_detected": keep})
    return pd.DataFrame(rows)


def plot_window(df):
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    ax.plot(df.window_slope_a, df.trees_detected, "o-", color="#1b7837")
    ax.axvline(0.07, color="#9aa5b1", ls="--", lw=1)
    ax.text(0.071, df.trees_detected.max(), "rule used in “From Points to Trees”", fontsize=7, va="top")
    ax.set_xlabel("a in window = a × height + 2 m")
    ax.set_ylabel("Trees detected (0.81 ha)")
    ax.set_title("T7: the tree count is a parameter until stems are measured",
                 loc="left", fontsize=10)
    return fig


# ---------------------------------------------------------------------------
# T8. Two global height maps, one forest
# ---------------------------------------------------------------------------
jambi = ee.Geometry.Rectangle([102.45, -2.15, 102.90, -1.75], None, False)
eth = ee.Image("users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1").rename("eth")
glad = ee.ImageCollection("users/potapovpeter/GEDI_V27").mosaic().rename("glad")
diff = eth.subtract(glad).rename("diff").clip(jambi)
height_pairs = eth.addBands(glad).sample(region=jambi, scale=30, numPixels=4000, seed=2,
                                         tileScale=4)


def diff_table(df):
    df = df[df.glad > 0]
    bins = pd.cut(df.eth, [0, 10, 20, 30, 60], labels=["0-10", "10-20", "20-30", "30+"])
    g = df.assign(d=df.eth - df.glad).groupby(bins, observed=True)["d"]
    return pd.DataFrame({"pixels": g.size(), "mean_ETH_minus_GLAD_m": g.mean(),
                         "sd_m": g.std()}).reset_index().rename(columns={"eth": "ETH height (m)"})


# ---------------------------------------------------------------------------
# T9. Where to put 30 LiDAR plots? Coverage of the embedding space
# ---------------------------------------------------------------------------
wj = ee.Geometry.Rectangle([106.4, -7.8, 108.8, -6.0], None, False)
emb_points = (ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
              .filterDate("2023-01-01", "2024-01-01").filterBounds(wj).mosaic()
              .sample(region=wj, scale=100, numPixels=3000, seed=4, tileScale=4))


def coverage_frame(df, k=30, repeats=300, seed=0):
    X = df[[c for c in df.columns if c.startswith("A")]].to_numpy()
    rng = np.random.default_rng(seed)

    def cover(idx):                     # mean distance from every pixel to its nearest plot
        d = ((X[:, None, :] - X[None, idx, :]) ** 2).sum(-1)
        return np.sqrt(d.min(1)).mean()

    rand = [cover(rng.choice(len(X), k, replace=False)) for _ in range(repeats)]
    # k-means in embedding space, then the real pixel nearest each centre
    c = X[rng.choice(len(X), k, replace=False)]
    for _ in range(30):
        lab = ((X[:, None, :] - c[None]) ** 2).sum(-1).argmin(1)
        c = np.array([X[lab == j].mean(0) if (lab == j).any() else c[j] for j in range(k)])
    strat = ((X[:, None, :] - c[None]) ** 2).sum(-1).argmin(0)
    return pd.DataFrame({"design": ["random"] * repeats + ["embedding-stratified"],
                         "mean_distance_to_nearest_plot": rand + [cover(strat)]})


def plot_coverage(df):
    r = df[df.design == "random"]["mean_distance_to_nearest_plot"]
    s = df[df.design != "random"]["mean_distance_to_nearest_plot"].iloc[0]
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    ax.hist(r, 30, color="#9aa5b1", label="300 random designs")
    ax.axvline(s, color="#c0392b", lw=2, label="stratified by embedding clusters")
    ax.set_xlabel("Mean distance from a pixel to its nearest plot (embedding space)")
    ax.set_title(f"T9: stratified beats {(r > s).mean():.0%} of random designs",
                 loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


# ---------------------------------------------------------------------------
# T10. Does a landslide model travel? Iburi, west half against east half
# ---------------------------------------------------------------------------
window = ee.Geometry.Rectangle([141.93, 42.70, 142.05, 42.80])
inventory = ee.FeatureCollection("users/rifkynauvalhsp/IburiLandslideInventory/trainingset")


def _s2(start, end):
    def prep(s):
        s = s.updateMask(s.select("QA60").eq(0)).divide(10000)
        return s.addBands([s.normalizedDifference(["B8", "B4"]).rename("ndvi"),
                           s.normalizedDifference(["B3", "B4"]).rename("grvi")])
    return (ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(window)
            .filterDate(start, end).filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            .map(prep).median())


pre, post = _s2("2017-09-01", "2017-10-31"), _s2("2018-09-07", "2018-10-31")
feat = (post.select(["ndvi", "grvi"]).subtract(pre.select(["ndvi", "grvi"]))
        .rename(["dNDVI", "dGRVI"])
        .addBands(ee.Terrain.slope(ee.ImageCollection("JAXA/ALOS/AW3D30/V4_1")
                                   .filterBounds(window).select("DSM").mosaic()
                                   .setDefaultProjection("EPSG:4326", None, 30)).rename("slope"))
        .addBands(ee.Image.pixelLonLat().select("longitude")))
truth = ee.Image(0).paint(inventory, 1).rename("truth").clip(window)
slide_pts = feat.addBands(truth).stratifiedSample(numPoints=1000, classBand="truth",
                                                  region=window, scale=10, seed=3,
                                                  tileScale=4)


def transfer_table(df):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import f1_score
    X = ["dNDVI", "dGRVI", "slope"]
    df = df.dropna(subset=X)
    mid = df.longitude.median()
    rng = np.random.default_rng(0)
    rand = rng.random(len(df)) < 0.5
    rows = []
    for name, train in [("random half / other half", rand),
                        ("west half / east half", (df.longitude < mid).to_numpy())]:
        m = RandomForestClassifier(200, random_state=0).fit(df.loc[train, X], df.loc[train, "truth"])
        p = m.predict(df.loc[~train, X])
        rows.append({"split": name, "test_points": int((~train).sum()),
                     "landslide_F1": f1_score(df.loc[~train, "truth"], p)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# T11. Two footprint layers, seven towns (3 x 3 km each)
# ---------------------------------------------------------------------------
TOWNS = {"Bandung": (107.61, -6.91), "Garut": (107.90, -7.21), "Surabaya": (112.75, -7.26),
         "Sleman": (110.36, -7.72), "Selong, Lombok": (116.53, -8.65),
         "Kuala Simpang, Aceh": (98.06, 4.28), "Jayapura": (140.70, -2.55)}


def footprints_table():
    rows = []
    for town, (lon, lat) in TOWNS.items():
        box = ee.Geometry.Rectangle([lon - 0.0135, lat - 0.0135, lon + 0.0135, lat + 0.0135])
        ms = sum(ee.FeatureCollection(
            f"projects/sat-io/open-datasets/MSBuildings/Indonesia/indonesia_{i}")
            .filterBounds(box).size().getInfo() for i in range(1, 8))
        gob = (ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
               .filterBounds(box).filter(ee.Filter.gte("confidence", 0.75)).size().getInfo())
        rows.append({"town (3 x 3 km)": town, "microsoft": ms, "google_v3_conf75": gob,
                     "ratio_google_to_ms": gob / ms if ms else np.nan})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# T12. Radar amplitude before and after the Iburi landslides (6 Sep 2018)
# ---------------------------------------------------------------------------
def radar_series():
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(window)
          .filterDate("2018-01-01", "2018-12-31").filter(ee.Filter.eq("instrumentMode", "IW"))
          .select("VV"))
    slid = truth.eq(1)

    def one(img):
        v = img.addBands(slid).reduceRegion(ee.Reducer.mean().group(1, "slid"), window, 20,
                                             maxPixels=1e9, tileScale=4).get("groups")
        return ee.Feature(None, {"t": img.date().millis(), "g": v,
                                 "pass": img.get("orbitProperties_pass")})
    rows = []
    for f in s1.map(one).getInfo()["features"]:
        p = f["properties"]
        for g in p["g"]:
            rows.append({"date": pd.Timestamp(p["t"], unit="ms"), "pass": p["pass"],
                         "inside_landslides": bool(g["slid"]), "VV_dB": g["mean"]})
    return pd.DataFrame(rows)


def plot_radar(df):
    fig, ax = plt.subplots(figsize=(8, 3.3))
    for (inside, pas), d in df.groupby(["inside_landslides", "pass"]):
        ax.plot(d.date, d.VV_dB, "o-", ms=3, lw=1,
                color="#c0392b" if inside else "#9aa5b1",
                ls="-" if pas == "DESCENDING" else ":",
                label=f"{'inside' if inside else 'outside'} landslides, {pas.lower()}")
    ax.axvline(pd.Timestamp("2018-09-06"), color="#1f2933", lw=1)
    ax.text(pd.Timestamp("2018-09-08"), ax.get_ylim()[1], "earthquake", fontsize=7, va="top")
    ax.set_ylabel("Mean VV (dB)")
    ax.set_title("T12: averaged amplitude hardly separates landslide ground, before or "
                 "after", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=7, ncol=2)
    return fig


def products():
    return [
        {"kind": "chart", "name": "t07-window", "data": window_frame, "plot": plot_window,
         "caption": "T7. Trees detected in the lidR MixedConifer plot as the window rule "
                    "changes. Without field stems no value of a is 'right'."},
        {"kind": "map", "name": "t08-diff", "image": diff, "region": jambi,
         "vis": {"min": -15, "max": 15, "palette": ["8c510a", "d8b365", "f5f5f5", "5ab4ac",
                                                     "01665e"]},
         "legend": "ETH minus GLAD canopy height (m)",
         "title": "Two height maps, one landscape", "source": "ETH 2020; GLAD 2019. GEE.",
         "caption": "T8. Where the two global canopy height maps disagree. Teal: ETH taller; "
                    "brown: GLAD taller."},
        {"kind": "table", "name": "t08-table", "data": height_pairs, "transform": diff_table,
         "floatfmt": ("", ",.0f", ".1f", ".1f"),
         "caption": "T8. Mean difference by ETH height class: only local airborne LiDAR can "
                    "say which map is right."},
        {"kind": "chart", "name": "t09-coverage", "data": lambda: coverage_frame(
            pd.DataFrame([f["properties"] for f in emb_points.getInfo()["features"]])),
         "plot": plot_coverage,
         "caption": "T9. Thirty LiDAR plots in West Java: how well do they cover the range "
                    "of landscapes, measured as distance in embedding space?"},
        {"kind": "table", "name": "t10-transfer", "data": slide_pts,
         "transform": transfer_table, "floatfmt": ("", ",.0f", ".2f"),
         "caption": "T10. The same Random Forest, tested on a random half and on the other "
                    "geographic half of the Iburi window: no drop. Within one event, one "
                    "landscape and one image pair the model holds. The open question is "
                    "transfer across events, which needs a second inventory such as "
                    "Lombok's [@ferrario2019lombok]."},
        {"kind": "table", "name": "t11-footprints", "data": footprints_table,
         "floatfmt": ("", ",.0f", ",.0f", ".2f"),
         "caption": "T11. Building footprints counted in a 3 × 3 km box at each town centre."},
        {"kind": "chart", "name": "t12-radar", "data": radar_series, "plot": plot_radar,
         "caption": "T12. Sentinel-1 VV averaged inside and outside the Iburi landslide "
                    "inventory through 2018. The two lines follow the seasons together and "
                    "barely separate even after the earthquake. A warning signal, if one "
                    "exists, would have to come from phase coherence (SLC data, outside "
                    "Earth Engine) or from finer texture, not from averaged amplitude."},
    ]


if __name__ == "__main__":
    print(window_frame())
