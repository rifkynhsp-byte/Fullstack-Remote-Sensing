#| title: Low shot mapping with satellite embeddings (Python)
#| description: The same embedding workflow as the JavaScript tab, plus a learning curve, in Python.

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


def plot_learning_curve(df):
    """Accuracy against labelled points per class. Where is 'enough'?"""
    df = df.sort_values("points_per_class")
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.plot(df["points_per_class"], df["accuracy"], marker="o", color="#6a51a3",
            label="embeddings + random forest")
    ax.axhline(0.816, color="#1b7837", ls="--", lw=1,
               label="chapter “Classical Supervised Learning” stack, ~200 points per class")
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
                    "training set grows from 5 to 100 points per class. The dashed line "
                    "is the chapter “Classical Supervised Learning” stack on its own validation set, so compare the "
                    "level, not the decimals."},
        {"kind": "table", "name": "ch19-learning-table", "data": learning_curve,
         "columns": ["points_per_class", "accuracy", "kappa"],
         "floatfmt": (".0f", ".3f", ".3f"), "caption": "The learning curve as numbers."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(learning_curve.getInfo())
