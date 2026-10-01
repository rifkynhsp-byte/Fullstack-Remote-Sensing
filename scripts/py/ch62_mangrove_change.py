#| title: Mangrove growth and degradation, year by year (Python)
#| description: Segara Anakan lagoon, Cilacap. A random forest trained on Global Mangrove Watch 2020 and satellite embeddings maps mangrove every year from 2017 to 2024; gain and loss between the ends; inside stable mangrove, a Sentinel-2 moisture trend separates degrading from improving canopy; and Dynamic World says what replaced the lost mangrove.

"""
CHAPTER 62 | Is the mangrove growing or degrading?

The same approach as the author's interactive mangrove explorer, at a public
site: one model, every year, compared with a fixed baseline.

    1. labels     GMW v3 2020: mangrove inside the polygons; non-mangrove more
                  than 100 m outside them (a buffer keeps edge errors out)
    2. model      random forest on the 2020 Satellite Embedding (64 bands)
    3. years      the same model applied to every embedding year 2017-2024
    4. change     gain = not mangrove in 2017, mangrove in 2024; loss = the reverse
    5. condition  inside mangrove in BOTH years: Sen's slope of annual median
                  NDMI (Sentinel-2, 2019-2024). Falling = degrading canopy,
                  rising = improving. Area changes say nothing about this.
    6. after      Dynamic World 2024 label of the lost mangrove
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([108.76, -7.76, 109.06, -7.62], None, False)   # Segara Anakan
YEARS = list(range(2017, 2025))
SLOPE = 0.005          # NDMI per year; beyond this the trend counts as real change

gmw = ee.FeatureCollection("projects/sat-io/open-datasets/GMW/extent/gmw_v3_2020_vec") \
    .filterBounds(aoi)
gmw_img = ee.Image(0).paint(gmw, 1).clip(aoi)
outside = gmw_img.Not().And(gmw_img.focalMax(100, "circle", "meters").Not())
labels = (ee.Image(-1).where(gmw_img.eq(1), 1).where(outside, 0).rename("mangrove")
          .updateMask(ee.Image(-1).where(gmw_img.eq(1), 1).where(outside, 0).gte(0))
          .clip(aoi))


def emb(year):
    return (ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
            .filterDate(f"{year}-01-01", f"{year + 1}-01-01").filterBounds(aoi).mosaic()
            .clip(aoi))


bands = emb(2020).bandNames()
pts = labels.stratifiedSample(numPoints=600, classBand="mangrove", region=aoi, scale=10,
                              seed=3, geometries=True, tileScale=8)
samples = emb(2020).sampleRegions(collection=pts, properties=["mangrove"], scale=10,
                                  tileScale=8).randomColumn("r", 2)
train, test = samples.filter(ee.Filter.lt("r", 0.7)), samples.filter(ee.Filter.gte("r", 0.7))
model = ee.Classifier.smileRandomForest(150, seed=1).train(train, "mangrove", bands)


def mangrove(year):
    return emb(year).classify(model).eq(1).rename("m")


m17, m24 = mangrove(2017), mangrove(2024)
area = ee.Image.pixelArea().divide(1e4)


def area_table():
    rows = []
    gmw_ha = area.updateMask(gmw_img).reduceRegion(ee.Reducer.sum(), aoi, 10,
                                                   maxPixels=1e10).values().get(0).getInfo()
    for y in YEARS:
        ha = (area.updateMask(mangrove(y)).reduceRegion(ee.Reducer.sum(), aoi, 10,
                                                        maxPixels=1e10, tileScale=8)
              .values().get(0).getInfo())
        rows.append({"year": y, "mangrove_ha": ha, "gmw_2020_baseline_ha": gmw_ha})
    acc = test.classify(model).errorMatrix("mangrove", "classification")
    df = pd.DataFrame(rows)
    df["holdout_accuracy_2020"] = acc.accuracy().getInfo()
    return df


def plot_area(df):
    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    ax.bar(df.year, df.mangrove_ha, color="#00a884", label="mangrove, this model")
    ax.plot(df.year, df.gmw_2020_baseline_ha, color="#1f2933", lw=2, ls="--",
            label="GMW 2020 baseline")
    lo = min(df.mangrove_ha.min(), df.gmw_2020_baseline_ha.min())
    ax.set_ylim(lo * 0.9, None)
    ax.set_ylabel("Area (ha)")
    ax.set_title("Mangrove area vs. the GMW 2020 baseline, Segara Anakan", loc="left",
                 fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def tuning_table():
    rows = []
    for n in (10, 25, 50, 100, 150, 250):
        m = ee.Classifier.smileRandomForest(n, seed=1).train(train, "mangrove", bands)
        rows.append({"trees": n, "holdout_accuracy": test.classify(m).errorMatrix(
            "mangrove", "classification").accuracy().getInfo()})
    return pd.DataFrame(rows)


def plot_tuning(df):
    fig, ax = plt.subplots(figsize=(5.6, 3.0))
    ax.plot(df.trees, df.holdout_accuracy, marker="o", color="#2a78d6")
    ax.set_xlabel("Number of trees"); ax.set_ylabel("Hold-out accuracy")
    ax.set_title("Random forest tuning", loc="left", fontsize=10)
    return fig


# Sentinel-2 annual medians for the spectral signature and the moisture trend.
def s2_year(y):
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi)
           .filterDate(f"{y}-01-01", f"{y + 1}-01-01")
           .linkCollection(ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"),
                           ["cs"])
           .map(lambda i: i.updateMask(i.select("cs").gte(0.6))))
    return col.median().divide(10000)


trend_col = ee.ImageCollection([
    ee.Image.constant(y).float().rename("t").addBands(
        s2_year(y).normalizedDifference(["B8", "B11"]).rename("ndmi")) for y in range(2019, 2025)])
slope = trend_col.select(["t", "ndmi"]).reduce(ee.Reducer.sensSlope()).select("slope")
stable = m17.And(m24)
change = (ee.Image(0).where(m17.Not().And(m24), 1).where(m17.And(m24.Not()), 2)
          .where(stable.And(slope.lt(-SLOPE)), 3).where(stable.And(slope.abs().lte(SLOPE)), 4)
          .where(stable.And(slope.gt(SLOPE)), 5).selfMask().rename("change").clip(aoi))
CHANGE = {1: ("gain (new mangrove)", "#00ff7f"), 2: ("loss", "#d7191c"),
          3: ("stable, canopy degrading", "#fdae61"), 4: ("stable, no clear trend", "#1a9641"),
          5: ("stable, canopy improving", "#2b83ba")}


def change_table():
    g = (area.addBands(change).reduceRegion(ee.Reducer.sum().group(1, "change"), aoi, 10,
                                            maxPixels=1e10, tileScale=8)
         .get("groups").getInfo())
    df = pd.DataFrame([{"class": CHANGE[int(x["change"])][0], "ha": x["sum"]} for x in g])
    df["share_of_2017_mangrove_or_gain"] = df.ha / df.ha.sum()
    return df


def after_table():
    dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(aoi)
          .filterDate("2024-01-01", "2025-01-01").select("label").mode())
    names = ["water", "trees", "grass", "flooded vegetation", "crops", "shrub and scrub",
             "built", "bare", "snow"]
    g = (area.updateMask(change.eq(2)).addBands(dw.rename("dw"))
         .reduceRegion(ee.Reducer.sum().group(1, "dw"), aoi, 10, maxPixels=1e10, tileScale=8)
         .get("groups").getInfo())
    df = pd.DataFrame([{"Dynamic World 2024": names[int(x["dw"])], "ha": x["sum"]} for x in g])
    df["share"] = df.ha / df.ha.sum()
    return df.sort_values("ha", ascending=False).reset_index(drop=True)


def plot_after(df):
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    cols = {"water": "#419bdf", "trees": "#397d49", "grass": "#88b053",
            "flooded vegetation": "#7a87c6", "crops": "#e49635", "shrub and scrub": "#dfc35a",
            "built": "#c4281b", "bare": "#a59b8f", "snow": "#b39fe1"}
    ax.pie(df.ha, labels=df["Dynamic World 2024"], colors=[cols[n] for n in df["Dynamic World 2024"]],
           autopct="%1.0f%%", textprops={"fontsize": 8})
    ax.set_title("What the lost mangrove is now", loc="left", fontsize=10)
    return fig


def signature_table():
    s = s2_year(2024).select(["B2", "B3", "B4", "B5", "B8", "B11", "B12"])
    dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(aoi)
          .filterDate("2024-01-01", "2025-01-01").select("label").mode())
    groups = {"mangrove": m24, "open water": dw.eq(0).And(m24.Not()),
              "other trees": dw.eq(1).And(m24.Not()), "crops and ponds edge": dw.eq(4),
              "built": dw.eq(6)}
    rows = []
    for n, m in groups.items():
        v = s.updateMask(m).reduceRegion(ee.Reducer.median(), aoi, 20, maxPixels=1e10,
                                         tileScale=8).getInfo()
        rows.append({"class": n, **v})
    return pd.DataFrame(rows)


def plot_signature(df):
    wl = [490, 560, 665, 705, 842, 1610, 2190]
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    for _, r in df.iterrows():
        ax.plot(wl, [r[b] for b in ["B2", "B3", "B4", "B5", "B8", "B11", "B12"]], marker="o",
                label=r["class"])
    ax.set_xlabel("Wavelength (nm)"); ax.set_ylabel("Surface reflectance (median)")
    ax.set_title("Spectral signatures by class, 2024", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def products():
    src = "Satellite Embedding V1; GMW v3 2020; Sentinel-2 L2A; Dynamic World. GEE."
    return [
        {"kind": "chart", "name": "ch62-area", "data": area_table, "plot": plot_area,
         "caption": "Mangrove area each year from one model, against the Global Mangrove "
                    "Watch 2020 baseline."},
        {"kind": "table", "name": "ch62-area-table", "data": area_table,
         "floatfmt": ("", ",.0f", ",.0f", ".3f"),
         "caption": "Mangrove area by year (ha) and the model's hold-out accuracy in 2020."},
        {"kind": "map", "name": "ch62-change", "image": change, "region": aoi,
         "vis": {"min": 1, "max": 5, "palette": [c for _, c in CHANGE.values()]},
         "classes": list(CHANGE.values()),
         "title": "Mangrove gain, loss and condition, 2017-2024", "source": src,
         "caption": "Gain and loss between 2017 and 2024; inside mangrove present in both "
                    f"years, the 2019-2024 NDMI trend (beyond ±{SLOPE} per year)."},
        {"kind": "table", "name": "ch62-change-table", "data": change_table,
         "floatfmt": ("", ",.0f", ".0%"),
         "caption": "Area in each change and condition class (ha)."},
        {"kind": "chart", "name": "ch62-after", "data": after_table, "plot": plot_after,
         "caption": "Dynamic World 2024 label of the mangrove lost since 2017."},
        {"kind": "chart", "name": "ch62-signature", "data": signature_table,
         "plot": plot_signature,
         "caption": "Median Sentinel-2 reflectance of mangrove and its neighbours, 2024."},
        {"kind": "chart", "name": "ch62-tuning", "data": tuning_table, "plot": plot_tuning,
         "caption": "Hold-out accuracy against the number of trees."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(area_table())
