#| title: Three classifiers and a vote (Python)
#| description: The same ensemble as the JavaScript tab, run from Python.

"""
CHAPTER 16 | Tune a random forest, read its importance, train RF, SVM and
gradient boosting, and let them vote. In Python.
"""

import ee
import matplotlib.pyplot as plt

from book_labels import CLASS_NAMES, LULC_PALETTE, labelled_points
from ch10_multisensor_stack import get_analysis_ready_data

aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60])
image2023 = get_analysis_ready_data(2023, aoi)

# Split the POINTS, then sample the image (never the other way round)
with_random = labelled_points(aoi).randomColumn("random", 42)
SPLIT = 0.7
training_set = with_random.filter(ee.Filter.lt("random", SPLIT))
validation_set = with_random.filter(ee.Filter.gte("random", SPLIT))

bands = image2023.bandNames()
training_samples = image2023.sampleRegions(collection=training_set,
                                           properties=["landcover"], scale=10, tileScale=4)
validation_samples = image2023.sampleRegions(collection=validation_set,
                                             properties=["landcover"], scale=10, tileScale=4)

# Tuning: accuracy against number of trees
num_trees_list = ee.List.sequence(10, 150, 20)


def accuracy_for(n):
    model = ee.Classifier.smileRandomForest(n).train(
        features=training_samples, classProperty="landcover", inputProperties=bands)
    return (validation_samples.classify(model)
            .errorMatrix("landcover", "classification").accuracy())


tuning = ee.FeatureCollection(num_trees_list.map(
    lambda n: ee.Feature(None, {"trees": n, "accuracy": accuracy_for(n)})))

# Importance from the forest itself
explainer = ee.Classifier.smileRandomForest(100).train(training_samples, "landcover", bands)
importance = ee.Dictionary(ee.Dictionary(explainer.explain()).get("importance"))
importance_table = ee.FeatureCollection(importance.keys().map(
    lambda k: ee.Feature(None, {"band": k, "importance": importance.get(k)})))

# SVM measures distances, so it needs every band on the same scale. Standardise
# each band with its mean and standard deviation over the study area.
stats = image2023.reduceRegion(
    reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), "", True),
    geometry=aoi, scale=100, maxPixels=1e9, bestEffort=True)
means = ee.Image.constant(bands.map(lambda b: stats.get(ee.String(b).cat("_mean")))).rename(bands)
sds = ee.Image.constant(bands.map(lambda b: stats.get(ee.String(b).cat("_stdDev")))).rename(bands)
image_scaled = image2023.subtract(means).divide(sds)
train_scaled = image_scaled.sampleRegions(collection=training_set, properties=["landcover"],
                                          scale=10, tileScale=4)
valid_scaled = image_scaled.sampleRegions(collection=validation_set, properties=["landcover"],
                                          scale=10, tileScale=4)
svm_scaled = ee.Classifier.libsvm(kernelType="RBF", gamma=0.5, cost=10).train(
    train_scaled, "landcover", bands)
svm_scaled_matrix = valid_scaled.classify(svm_scaled).errorMatrix("landcover", "classification")

# Three models, one vote
rf = ee.Classifier.smileRandomForest(100).train(training_samples, "landcover", bands)
svm = ee.Classifier.libsvm(kernelType="RBF", gamma=0.5, cost=10).train(
    training_samples, "landcover", bands)
gtb = ee.Classifier.smileGradientTreeBoost(100).train(training_samples, "landcover", bands)

classified = {name: image2023.classify(m).rename("classification")
              for name, m in [("RF", rf), ("SVM", svm), ("GTB", gtb)]}
ensemble = (ee.Image.cat(list(classified.values())).reduce(ee.Reducer.mode())
            .rename("classification"))
ensemble_smooth = ensemble.focalMode(radius=3, kernelType="circle", units="pixels")


def model_accuracy(name, model):
    m = validation_samples.classify(model).errorMatrix("landcover", "classification")
    return ee.Feature(None, {"model": name, "overall_accuracy": m.accuracy(),
                             "kappa": m.kappa()})


# Score the vote the same way: sample the voted map at the validation points
vote_samples = ensemble.sampleRegions(collection=validation_set, properties=["landcover"],
                                      scale=10, tileScale=4)
vote_matrix = vote_samples.errorMatrix("landcover", "classification")
accuracy_table = ee.FeatureCollection([
    model_accuracy("Random Forest", rf), model_accuracy("SVM (RBF)", svm),
    ee.Feature(None, {"model": "SVM (RBF), bands standardised",
                      "overall_accuracy": svm_scaled_matrix.accuracy(),
                      "kappa": svm_scaled_matrix.kappa()}),
    model_accuracy("Gradient tree boost", gtb),
    ee.Feature(None, {"model": "Majority vote", "overall_accuracy": vote_matrix.accuracy(),
                      "kappa": vote_matrix.kappa()})])


def plot_tuning(df):
    """Validation accuracy against forest size. Where does it stop improving?"""
    df = df.sort_values("trees")
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(df["trees"], df["accuracy"], marker="o", color="#2166ac")
    ax.set_xlabel("Number of trees")
    ax.set_ylabel("Validation accuracy")
    ax.set_title("Random forest tuning", loc="left")
    return fig


def plot_importance(df):
    """Which bands the forest leaned on. Top 12."""
    df = df.sort_values("importance").tail(12)
    fig, ax = plt.subplots(figsize=(6, 3.8))
    ax.barh(df["band"], df["importance"], color="#1b7837")
    ax.set_xlabel("Importance (random forest)")
    ax.set_title("Which predictors earn their place", loc="left")
    return fig


def products():
    classes = [(n, "#" + c) for n, c in zip(CLASS_NAMES, LULC_PALETTE)]
    vis = {"min": 0, "max": 4, "palette": LULC_PALETTE}
    src = "Stack: Chapter 10. Labels: ESA WorldCover 2021. GEE."
    return [
        {"kind": "map", "name": "ch16-rf", "image": classified["RF"], "vis": vis,
         "region": aoi, "classes": classes, "title": "Random forest alone", "source": src,
         "caption": "One random forest, 100 trees, on the Chapter 10 stack."},
        {"kind": "map", "name": "ch16-ensemble", "image": ensemble_smooth, "vis": vis,
         "region": aoi, "classes": classes,
         "title": "RF, SVM and boosting vote, then smoothed", "source": src,
         "caption": "The majority vote of three models, with a 3 pixel mode filter. "
                    "Smoothing tidies the map and also changes class areas (Chapter 16)."},
        {"kind": "chart", "name": "ch16-tuning", "data": tuning, "plot": plot_tuning,
         "caption": "Accuracy flattens quickly: past a few dozen trees you are "
                    "paying compute for nothing."},
        {"kind": "chart", "name": "ch16-importance", "data": importance_table,
         "plot": plot_importance,
         "caption": "Random forest importance for the 24-band stack."},
        {"kind": "table", "name": "ch16-accuracy", "data": accuracy_table,
         "columns": ["model", "overall_accuracy", "kappa"], "floatfmt": ".3f",
         "caption": "Validation accuracy per model and for the vote (agreement with "
                    "WorldCover 2021 on held-out points). The raw SVM calls everything "
                    "one class (kappa 0): its distances are dominated by bands measured "
                    "in thousands. Standardising the bands helps; the trees still win, "
                    "because the SVM gamma was never tuned for 24 bands."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(accuracy_table.getInfo())
