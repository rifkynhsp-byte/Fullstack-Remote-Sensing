#| title: Spatial block cross validation (Python)
#| description: The same block design as the JavaScript tab, run from Python.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 15 | Block cross validation versus a random split, in Python.
Whole 5 km blocks go to a fold, so a model is tested on places it has not seen.
"""

import ee
import matplotlib.pyplot as plt

from book_labels import labelled_points
from ch10_multisensor_stack import get_analysis_ready_data

CLASS_PROPERTY = "landcover"
SCALE = 10
BLOCK_SIZE_M = 5000
N_FOLDS = 5

aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60])
image2023 = get_analysis_ready_data(2023, aoi)
samples = labelled_points(aoi)            # or your own labelled points

# Blocks: a random fold number per 5 km cell
proj = ee.Projection("EPSG:3857").atScale(BLOCK_SIZE_M)
blocks = ee.Image.random(42).multiply(N_FOLDS).floor().reproject(proj).rename("fold").toInt()

samples_with_fold = blocks.sampleRegions(collection=samples, scale=BLOCK_SIZE_M,
                                         geometries=True, tileScale=4)
bands = image2023.bandNames()


def run_fold(fold):
    fold = ee.Number(fold)
    train_pts = samples_with_fold.filter(ee.Filter.neq("fold", fold))
    test_pts = samples_with_fold.filter(ee.Filter.eq("fold", fold))
    train = image2023.sampleRegions(collection=train_pts, properties=[CLASS_PROPERTY],
                                    scale=SCALE, tileScale=4)
    test = image2023.sampleRegions(collection=test_pts, properties=[CLASS_PROPERTY],
                                   scale=SCALE, tileScale=4)
    model = ee.Classifier.smileRandomForest(100).train(
        features=train, classProperty=CLASS_PROPERTY, inputProperties=bands)
    matrix = test.classify(model).errorMatrix(CLASS_PROPERTY, "classification")
    return ee.Feature(None, {"fold": fold, "n_train": train_pts.size(),
                             "n_test": test_pts.size(), "accuracy": matrix.accuracy()})


results = ee.FeatureCollection(ee.List.sequence(0, N_FOLDS - 1).map(run_fold))

# The comparison: an ordinary random 70/30 split of the same points
with_random = samples_with_fold.randomColumn("random", 42)
random_train = image2023.sampleRegions(collection=with_random.filter(ee.Filter.lt("random", 0.7)),
                                       properties=[CLASS_PROPERTY], scale=SCALE, tileScale=4)
random_test = image2023.sampleRegions(collection=with_random.filter(ee.Filter.gte("random", 0.7)),
                                      properties=[CLASS_PROPERTY], scale=SCALE, tileScale=4)
random_model = ee.Classifier.smileRandomForest(100).train(random_train, CLASS_PROPERTY, bands)
random_accuracy = (random_test.classify(random_model)
                   .errorMatrix(CLASS_PROPERTY, "classification").accuracy())

results_with_random = results.map(lambda f: f.set("random_split_accuracy", random_accuracy))


def plot_folds(df):
    """Block CV per fold against one random split. The gap is the leakage."""
    df = df.sort_values("fold")
    fig, ax = plt.subplots(figsize=(6.5, 3.3))
    ax.bar(df["fold"].astype(int).astype(str), df["accuracy"], color="#5b8db8",
           label="block CV, per fold")
    ax.axhline(df["accuracy"].mean(), color="#2166ac", lw=1.2,
               label=f"block CV mean {df['accuracy'].mean():.3f}")
    ax.axhline(df["random_split_accuracy"].iloc[0], color="#b2182b", lw=1.2, ls="--",
               label=f"random split {df['random_split_accuracy'].iloc[0]:.3f}")
    ax.set_ylim(max(0, df["accuracy"].min() - 0.15), 1.0)
    ax.set_xlabel("Held out fold (5 km blocks)")
    ax.set_ylabel("Overall accuracy")
    ax.set_title("A random split flatters the model", loc="left")
    ax.legend(frameon=False, fontsize=7.5, loc="lower right")
    return fig


def products():
    return [
        {"kind": "map", "name": "ch15-blocks",
         "image": blocks.clip(aoi).randomVisualizer(),
         "vis": {"bands": ["viz-red", "viz-green", "viz-blue"], "min": 0, "max": 255},
         "region": aoi, "title": "5 km blocks, five folds",
         "source": "Fold assignment only; no data behind the colours.",
         "caption": "Each colour is a 5 km block. Every point inside a block goes to "
                    "the same fold, so test points are never next door to training points."},
        {"kind": "chart", "name": "ch15-folds", "data": results_with_random,
         "plot": plot_folds,
         "caption": "Overall accuracy per held-out fold against a random 70/30 split "
                    "of the same points. Labels are WorldCover 2021, so both numbers "
                    "measure agreement with WorldCover."},
        {"kind": "table", "name": "ch15-folds-table", "data": results_with_random,
         "columns": ["fold", "n_train", "n_test", "accuracy", "random_split_accuracy"],
         "floatfmt": (".0f", ".0f", ".0f", ".3f", ".3f"),
         "caption": "Per fold results. The spread between folds is the honest answer "
                    "to how well the model travels."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(results.getInfo())
