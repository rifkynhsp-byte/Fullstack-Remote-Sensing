#| title: Low shot mapping with satellite embeddings (Python)
#| description: The same embedding workflow as the JavaScript tab, plus a learning curve, in Python.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 19 | AlphaEarth annual embeddings: a classifier from a handful of
points, a similarity search from one point, and a test of the low shot
claim: how does accuracy grow with points per class?
"""

import ee
import matplotlib.pyplot as plt

from book_labels import CLASS_NAMES, LULC_PALETTE, worldcover_classes

YEAR = 2023
aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60])   # Mahakam Delta

# PART 1. One line replaces the chapter “Synthetic Aperture Radar Fusion” stack
embeddings = (ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
              .filterDate(f"{YEAR}-01-01", f"{YEAR + 1}-01-01")
              .filterBounds(aoi).mosaic().clip(aoi))
bands = embeddings.bandNames()
labels = worldcover_classes(aoi)


def points(per_class, seed):
    return labels.stratifiedSample(numPoints=0, classBand="landcover", region=aoi,
                                   scale=10, seed=seed, classValues=[0, 1, 2, 3, 4],
                                   classPoints=[per_class] * 5, geometries=True,
                                   tileScale=4)


# PART 2-3. Twenty points per class for training, a fixed validation set
validation = embeddings.sampleRegions(collection=points(60, seed=999),
                                      properties=["landcover"], scale=10, tileScale=4)


def train(per_class):
    samples = embeddings.sampleRegions(collection=points(per_class, seed=42),
                                       properties=["landcover"], scale=10, tileScale=4)
    return ee.Classifier.smileRandomForest(100).train(samples, "landcover", bands)


classifier = train(20)
classified = embeddings.classify(classifier).rename("classification")


def accuracy_with(per_class):
    m = validation.classify(train(per_class)).errorMatrix("landcover", "classification")
    return ee.Feature(None, {"points_per_class": per_class, "accuracy": m.accuracy(),
                             "kappa": m.kappa()})


learning_curve = ee.FeatureCollection([accuracy_with(n) for n in (5, 10, 20, 50, 100)])

# PART 4. Similarity to one known mangrove pixel (checked in WorldCover and GMW)
reference_point = ee.Geometry.Point([117.4222, -0.7504])
reference_vector = ee.Image.constant(
    embeddings.reduceRegion(reducer=ee.Reducer.first(), geometry=reference_point,
                            scale=10).values())
distance = (embeddings.subtract(reference_vector).pow(2)
            .reduce(ee.Reducer.sum()).sqrt().rename("distance"))

# One pixel turns out to be a noisy reference: from it, water is on average
# CLOSER than other mangrove. Average the embeddings of the 20 mangrove
# training points instead and search from that centroid.
mangrove_refs = embeddings.sampleRegions(
    collection=points(20, seed=42).filter(ee.Filter.eq("landcover", 0)), scale=10)
centroid = ee.Image.constant(ee.List(
    mangrove_refs.reduceColumns(ee.Reducer.mean().repeat(64), bands).get("mean")))
distance_centroid = (embeddings.subtract(centroid).pow(2)
                     .reduce(ee.Reducer.sum()).sqrt().rename("distance"))


def median_distance(img, cls):
    return img.updateMask(labels.eq(cls)).reduceRegion(
        reducer=ee.Reducer.median(), geometry=aoi, scale=60, maxPixels=1e9,
        bestEffort=True).get("distance")


distance_table = ee.FeatureCollection([
    ee.Feature(None, {"class": CLASS_NAMES[c],
                      "from_one_pixel": median_distance(distance, c),
                      "from_20_point_centroid": median_distance(distance_centroid, c)})
    for c in range(5)])


# PART 5. A fair test: embeddings against a hand-built Sentinel-2 stack, same points, same validation
def s2_stack():
    """What you would build by hand: cloud-masked 2023 median, ten bands and three indices."""
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi).filterDate(f"{YEAR}-01-01", f"{YEAR + 1}-01-01")
          .linkCollection(cs, ["cs"]).map(lambda im: im.updateMask(im.select("cs").gte(0.6))).median()
          .select(["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]).divide(10000))
    idx = [s2.normalizedDifference(["B8", "B4"]).rename("NDVI"), s2.normalizedDifference(["B3", "B8"]).rename("NDWI"),
           s2.normalizedDifference(["B3", "B11"]).rename("MNDWI")]
    return s2.addBands(idx).clip(aoi)


def head_to_head():
    """Accuracy of both feature sets on the SAME training points and the SAME validation points, three seeds."""
    import pandas as pd
    s2 = s2_stack()
    both = embeddings.addBands(s2)
    val = both.sampleRegions(collection=points(60, seed=999), properties=["landcover"], scale=10, tileScale=4)
    rows = []
    for n in (5, 10, 20, 50, 100):
        feats = []
        for seed in (1, 2, 3):
            tr = both.sampleRegions(collection=points(n, seed=seed), properties=["landcover"], scale=10, tileScale=4)
            for name, b in (("embeddings (64 bands)", bands), ("Sentinel-2 bands + indices (13)", s2.bandNames())):
                m = val.classify(ee.Classifier.smileRandomForest(100).train(tr, "landcover", b)).errorMatrix("landcover", "classification")
                feats.append(ee.Feature(None, {"features": name, "seed": seed, "acc": m.accuracy()}))
        rows += [f["properties"] | {"points_per_class": n} for f in ee.FeatureCollection(feats).getInfo()["features"]]
    d = pd.DataFrame(rows)
    return d.groupby(["points_per_class", "features"]).acc.agg(["mean", "std"]).reset_index()


def plot_head_to_head(d):
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    for name, c in (("embeddings (64 bands)", "#6a51a3"), ("Sentinel-2 bands + indices (13)", "#1b7837")):
        g = d[d.features == name].sort_values("points_per_class")
        ax.errorbar(g.points_per_class, g["mean"], yerr=g["std"], marker="o", capsize=3, color=c, label=name)
    ax.set_xscale("log"); ax.set_xticks([5, 10, 20, 50, 100], ["5", "10", "20", "50", "100"])
    ax.set_xlabel("training points per class (log scale)"); ax.set_ylabel("overall accuracy, 300 validation points")
    ax.legend(frameon=False, fontsize=8, loc="lower right"); ax.spines[["top", "right"]].set_visible(False)
    e5 = d[(d.features.str.startswith("emb")) & (d.points_per_class == 5)]["mean"].iloc[0]
    s100 = d[(d.features.str.startswith("Sen")) & (d.points_per_class == 100)]["mean"].iloc[0]
    ax.set_title(f"5 points per class with embeddings: {e5:.2f}; 100 points with Sentinel-2: {s100:.2f}",
                 loc="left", fontsize=9.5, fontweight="bold")
    fig.tight_layout()
    return fig


# PART 6. What the 64 dimensions contain: principal components of a sample
def pca_frame():
    import numpy as np
    import pandas as pd
    from sklearn.decomposition import PCA
    smp = embeddings.sampleRegions(collection=points(400, seed=7), properties=["landcover"], scale=10, tileScale=4).getInfo()
    d = pd.DataFrame([f["properties"] for f in smp["features"]])
    X = d[[f"A{i:02d}" for i in range(64)]].values
    pca = PCA().fit(X)
    pcs = pca.transform(X)[:, :2]
    _cache_pca.update(var=pca.explained_variance_ratio_, pcs=pcs, cls=d.landcover.values)
    return pd.DataFrame({"component": np.arange(1, 65), "variance_share": pca.explained_variance_ratio_,
                         "cumulative": np.cumsum(pca.explained_variance_ratio_)})


_cache_pca = {}


def plot_pca(t):
    import numpy as np
    if not _cache_pca:
        pca_frame()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8))
    cum = np.cumsum(_cache_pca["var"])
    a1.plot(range(1, 65), cum, marker=".", color="#6a51a3")
    k90 = int(np.argmax(cum >= 0.9)) + 1
    a1.axhline(0.9, color="grey", ls=":"); a1.axvline(k90, color="grey", ls=":")
    a1.set_xlabel("number of principal components"); a1.set_ylabel("variance explained (cumulative)")
    a1.set_title(f"{k90} of 64 components hold 90 % of the variance", loc="left", fontsize=9)
    for c in range(5):
        m = _cache_pca["cls"] == c
        a2.scatter(_cache_pca["pcs"][m, 0], _cache_pca["pcs"][m, 1], s=6, alpha=0.6, color="#" + LULC_PALETTE[c], label=CLASS_NAMES[c])
    a2.set_xlabel("PC 1"); a2.set_ylabel("PC 2"); a2.legend(frameon=False, fontsize=7, markerscale=2)
    a2.set_title("Classes already separate on two components, before any training", loc="left", fontsize=9)
    for a in (a1, a2):
        a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


# PART 7. Change in embedding space, 2018 to 2023
def emb(year):
    return (ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL").filterDate(f"{year}-01-01", f"{year + 1}-01-01")
            .filterBounds(aoi).mosaic().clip(aoi))


# The vectors have unit length, so their dot product is the cosine similarity: 1 = unchanged.
change = emb(2018).multiply(emb(2023)).reduce(ee.Reducer.sum()).rename("cos")


def change_table():
    """How much changed, and does Dynamic World agree that the land cover changed there?"""
    import pandas as pd
    dw = lambda y: (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(aoi)
                    .filterDate(f"{y}-01-01", f"{y + 1}-01-01").select("label").mode())
    dw_changed = dw(2018).neq(dw(2023))
    rows = []
    for thr in (0.9, 0.8, 0.7, 0.6):
        hit = change.lt(thr)
        r = ee.Image.cat([hit.rename("hit"), hit.And(dw_changed).rename("hit_dw"), ee.Image(1).rename("all")]) \
            .reduceRegion(ee.Reducer.sum(), aoi, 30, maxPixels=1e10, tileScale=4).getInfo()
        rows.append({"cosine similarity below": thr, "share of area (%)": 100 * r["hit"] / r["all"],
                     "of which Dynamic World label changed (%)": 100 * r["hit_dw"] / max(r["hit"], 1)})
    base = dw_changed.reduceRegion(ee.Reducer.mean(), aoi, 30, maxPixels=1e10, tileScale=4).getInfo()["label"]
    rows.append({"cosine similarity below": "any (whole area)", "share of area (%)": 100.0,
                 "of which Dynamic World label changed (%)": 100 * base})
    return pd.DataFrame(rows)


def plot_learning_curve(df):
    """Accuracy against labelled points per class. Where is 'enough'?"""
    df = df.sort_values("points_per_class")
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.plot(df["points_per_class"], df["accuracy"], marker="o", color="#6a51a3",
            label="embeddings + random forest")
    ax.set_xscale("log")
    ax.set_xticks(df["points_per_class"], [str(int(v)) for v in df["points_per_class"]])
    ax.set_xlabel("Training points per class (log scale)")
    ax.set_ylabel("Overall accuracy")
    ax.set_title("How low can 'low shot' go?", loc="left")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    return fig


def products():
    classes = [(n, "#" + c) for n, c in zip(CLASS_NAMES, LULC_PALETTE)]
    src = "Google Satellite Embedding V1 (AlphaEarth), 2023. Labels: WorldCover 2021."
    return [
        {"kind": "map", "name": "ch19-embedding-rgb", "image": embeddings, "region": aoi,
         "vis": {"bands": ["A01", "A16", "A09"], "min": -0.3, "max": 0.3},
         "title": "Three of the 64 embedding dimensions as colour", "source": src,
         "caption": "Bands A01, A16 and A09 shown as red, green and blue. The colours "
                    "mean nothing physical; what matters is that similar places get "
                    "similar colours without any training."},
        {"kind": "map", "name": "ch19-classified", "image": classified, "region": aoi,
         "vis": {"min": 0, "max": 4, "palette": LULC_PALETTE}, "classes": classes,
         "title": "Land cover from 20 points per class", "source": src,
         "caption": "A random forest trained on 20 WorldCover-labelled points per class, "
                    "with no cloud masking, compositing or feature engineering."},
        {"kind": "map", "name": "ch19-similarity", "image": distance, "region": aoi,
         "vis": {"min": 0.4, "max": 1.2, "palette": ["08306b", "4292c6", "deebf7", "ffffff"]},
         "legend": "Distance to ONE reference pixel (dark = similar)",
         "title": "Searching from one mangrove pixel", "source": src,
         "caption": "Distance in embedding space from a single pixel that WorldCover and "
                    "Global Mangrove Watch both call mangrove. Almost nothing lights up."},
        {"kind": "map", "name": "ch19-similarity-centroid", "image": distance_centroid,
         "region": aoi,
         "vis": {"min": 0.4, "max": 1.2, "palette": ["08306b", "4292c6", "deebf7", "ffffff"]},
         "legend": "Distance to the mean of 20 mangrove points (dark = similar)",
         "title": "Searching from 20 points averaged", "source": src,
         "caption": "The same search from the average of 20 mangrove points. The delta's "
                    "mangrove comes out dark and the sea stays white."},
        {"kind": "table", "name": "ch19-distance-table", "data": distance_table,
         "columns": ["class", "from_one_pixel", "from_20_point_centroid"], "floatfmt": ".2f",
         "caption": "Median embedding distance by WorldCover class. From one pixel, water "
                    "is closer than other mangrove; from a 20-point average the order is "
                    "right. One pixel is an anecdote, twenty are a description."},
        {"kind": "chart", "name": "ch19-learning-curve", "data": learning_curve,
         "plot": plot_learning_curve,
         "caption": "Accuracy on a fixed set of 300 WorldCover-labelled points as the "
                    "training set grows from 5 to 100 points per class (one seed)."},
        {"kind": "table", "name": "ch19-learning-table", "data": learning_curve,
         "columns": ["points_per_class", "accuracy", "kappa"],
         "floatfmt": (".0f", ".3f", ".3f"), "caption": "The learning curve as numbers."},
        {"kind": "table", "name": "ch19-head-to-head", "data": head_to_head, "floatfmt": (".0f", "", ".3f", ".3f"),
         "caption": "Embeddings against a Sentinel-2 stack on identical training and validation points: mean and standard deviation over three random training draws."},
        {"kind": "chart", "name": "ch19-head-to-head-chart", "data": head_to_head, "plot": plot_head_to_head, "live": False,
         "caption": "The low-shot claim, tested fairly. Error bars: one standard deviation over three training draws."},
        {"kind": "chart", "name": "ch19-pca", "data": pca_frame, "plot": plot_pca, "live": False,
         "caption": "Principal components of 2,000 embedding vectors (400 per WorldCover class)."},
        {"kind": "map", "name": "ch19-change", "image": change, "region": aoi,
         "vis": {"min": 0.3, "max": 1, "palette": ["67001f", "d6604d", "fddbc7", "f7f7f7", "ffffff"]},
         "legend": "Cosine similarity, 2018 vs 2023 (1 = unchanged)", "title": "Change in embedding space, 2018 to 2023",
         "source": "Google Satellite Embedding V1, 2018 and 2023. GEE.",
         "caption": "Dark red: the 2023 vector points in a very different direction from 2018. No classification was needed to find it."},
        {"kind": "table", "name": "ch19-change-table", "data": change_table, "floatfmt": ("", ".1f", ".0f"),
         "caption": "How much of the delta changed at four similarity thresholds, and how often Dynamic World's own label changed in the same pixels."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(learning_curve.getInfo())
