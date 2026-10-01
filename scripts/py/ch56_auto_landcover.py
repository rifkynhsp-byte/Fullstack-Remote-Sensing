#| title: Automatic land cover: labels from map consensus, one model for every year (Python)
#| description: Lombok. Training labels are taken automatically where ESA WorldCover and Dynamic World agree in 2021, a random forest learns them from satellite embeddings, and the same model maps 2024 with no new samples. Validated on held-out consensus points and against Dynamic World 2024 at random points, including where the two source maps disagree.

"""
CHAPTER 56 | A land-cover map nobody had to label.

Collecting training points is the slow part of every classification
(Chapter 15). When two independent global maps agree on a pixel, that pixel is
probably right; use the agreement as free training data.

    1. labels    WorldCover 2021 and the 2021 mode of Dynamic World, mapped
                 to 7 shared classes; keep only pixels where both agree
    2. features  Google Satellite Embedding, 2021 (64 bands)
    3. model     random forest, trained once
    4. update    apply the same model to the 2024 embeddings: a new map with
                 no new labels (the embedding space is the same every year)
    5. check     held-out consensus points (optimistic: easy pixels only) and
                 random points against Dynamic World 2024 (includes hard pixels)
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

NAMES = ["water", "trees", "mangrove", "shrub and grass", "cropland", "built", "bare"]
PALETTE = ["2c7fb8", "1a9850", "00a884", "c2e699", "fee08b", "d73027", "bdbdbd"]
lombok = (ee.FeatureCollection("FAO/GAUL/2015/level1")
          .filter(ee.Filter.eq("ADM1_NAME", "Nusatenggara Barat")).geometry()
          .intersection(ee.Geometry.Rectangle([115.80, -9.10, 116.75, -8.20]), 100))
aoi = lombok.bounds(100)


def worldcover7():
    wc = ee.ImageCollection("ESA/WorldCover/v200").first()
    return wc.remap([80, 10, 95, 20, 30, 40, 50, 60, 90],
                    [0, 1, 2, 3, 3, 4, 5, 6, 3], -1).rename("lc")


def dynamicworld7(year):
    dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(aoi)
          .filterDate(f"{year}-01-01", f"{year + 1}-01-01").select("label").mode())
    # Dynamic World has no mangrove class: flooded vegetation stands in for it.
    return dw.remap([0, 1, 3, 2, 5, 4, 6, 7], [0, 1, 2, 3, 3, 4, 5, 6], -1).rename("lc")


def embeddings(year):
    return (ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
            .filterDate(f"{year}-01-01", f"{year + 1}-01-01").filterBounds(aoi)
            .mosaic().clip(lombok))


wc, dw21, dw24 = worldcover7(), dynamicworld7(2021), dynamicworld7(2024)
# WorldCover mangrove (2) is accepted where Dynamic World says trees or flooded vegetation.
agree = wc.eq(dw21).Or(wc.eq(2).And(dw21.eq(1))).And(wc.gte(0))
labels = wc.updateMask(agree).clip(lombok).rename("lc")
emb21, emb24 = embeddings(2021), embeddings(2024)
bands = emb21.bandNames()

PER_CLASS = 300
pts = labels.stratifiedSample(numPoints=PER_CLASS, classBand="lc", region=lombok, scale=10,
                              seed=7, geometries=True, tileScale=8)
samples = (emb21.sampleRegions(collection=pts, properties=["lc"], scale=10, tileScale=8)
           .randomColumn("r", 3))
train, test = samples.filter(ee.Filter.lt("r", 0.7)), samples.filter(ee.Filter.gte("r", 0.7))
model = ee.Classifier.smileRandomForest(150).train(train, "lc", bands)
map21 = emb21.classify(model).rename("lc")
map24 = emb24.classify(model).rename("lc")


def f1_table():
    m = test.classify(model).errorMatrix("lc", "classification", list(range(7)))
    cm = np.array(m.array().getInfo(), float)
    rows = []
    for k, n in enumerate(NAMES):
        p = cm[k, k] / cm[:, k].sum() if cm[:, k].sum() else np.nan
        r = cm[k, k] / cm[k, :].sum() if cm[k, :].sum() else np.nan
        rows.append({"class": n, "test_points": int(cm[k, :].sum()), "precision": p,
                     "recall": r, "f1": 2 * p * r / (p + r) if p + r else np.nan})
    oa = np.trace(cm) / cm.sum()
    rows.append({"class": "overall accuracy", "test_points": int(cm.sum()),
                 "precision": np.nan, "recall": np.nan, "f1": oa})
    return pd.DataFrame(rows)


def check_table():
    """Random points over the whole island, so hard pixels are included too."""
    rnd = ee.FeatureCollection.randomPoints(lombok, 3000, 11)
    stack = (map24.rename("ours").addBands(dw24.rename("dw24"))
             .addBands(map21.rename("ours21")).addBands(wc.rename("wc"))
             .addBands(agree.rename("agree")))
    d = pd.DataFrame([f["properties"] for f in stack.sampleRegions(
        collection=rnd, scale=10, tileScale=8).getInfo()["features"]])
    d = d[(d.dw24 >= 0) & (d.wc >= 0)]
    rows = []
    for name, sub in [("all random points", d), ("where the 2021 maps agreed", d[d.agree == 1]),
                      ("where the 2021 maps disagreed", d[d.agree == 0])]:
        rows.append({"points": name, "n": len(sub),
                     "share_of_island": len(sub) / len(d),
                     "ours_2024_vs_DW_2024": (sub.ours == sub.dw24).mean(),
                     "ours_2021_vs_WorldCover": (sub.ours21 == sub.wc).mean()})
    return pd.DataFrame(rows)


def area_table():
    area = ee.Image.pixelArea().divide(1e4)
    out = {}
    for y, img in [(2021, map21), (2024, map24)]:
        g = (area.addBands(img).reduceRegion(ee.Reducer.sum().group(1, "lc"), lombok, 20,
                                             maxPixels=1e11, tileScale=16)
             .get("groups").getInfo())
        out[y] = {NAMES[int(x["lc"])]: x["sum"] for x in g}
    df = pd.DataFrame(out).reindex(NAMES).fillna(0).reset_index()
    df.columns = ["class", "ha_2021", "ha_2024"]
    df["change_ha"] = df.ha_2024 - df.ha_2021
    return df


def plot_area(df):
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    x = np.arange(len(df))
    ax.bar(x - 0.2, df.ha_2021 / 1000, 0.4, color="#9aa5b1", label="2021")
    ax.bar(x + 0.2, df.ha_2024 / 1000, 0.4, color="#2a78d6", label="2024 (same model)")
    ax.set_xticks(x, df["class"], rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("Area (thousand ha)")
    ax.set_title("Lombok land cover, 2021 and 2024, one model", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def products():
    classes = [(n, "#" + c) for n, c in zip(NAMES, PALETTE)]
    vis = {"min": 0, "max": 6, "palette": PALETTE}
    src = "Satellite Embedding V1; labels: ESA WorldCover 2021 + Dynamic World 2021. GEE."
    return [
        {"kind": "map", "name": "ch56-labels", "image": labels, "region": aoi, "vis": vis,
         "classes": classes, "title": "Free training labels: where two maps agree",
         "source": "ESA WorldCover v200 (2021); Dynamic World 2021 mode. GEE.",
         "caption": "Pixels where WorldCover and Dynamic World gave the same class in 2021. "
                    "Blank land is where they disagree: no label is taken there."},
        {"kind": "map", "name": "ch56-map2024", "image": map24, "region": aoi, "vis": vis,
         "classes": classes, "title": "Lombok 2024, from a model trained on 2021",
         "source": src,
         "caption": "The 2021 model applied to the 2024 embeddings. No 2024 sample was "
                    "collected."},
        {"kind": "table", "name": "ch56-f1", "data": f1_table,
         "floatfmt": ("", ",.0f", ".2f", ".2f", ".2f"),
         "caption": "Held-out consensus points (30 %). Optimistic: these are pixels two maps "
                    "already agreed on, the easy ones."},
        {"kind": "table", "name": "ch56-check", "data": check_table,
         "floatfmt": ("", ",.0f", ".0%", ".0%", ".0%"),
         "caption": "Agreement at 3,000 random points on the island, split by whether the two "
                    "source maps agreed there in 2021."},
        {"kind": "chart", "name": "ch56-area", "data": area_table, "plot": plot_area,
         "caption": "Area of each class in 2021 and 2024 from the same model."},
        {"kind": "table", "name": "ch56-area-table", "data": area_table,
         "floatfmt": ("", ",.0f", ",.0f", "+,.0f"),
         "caption": "Area per class (ha). Small changes are within the model's error."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(f1_table())
