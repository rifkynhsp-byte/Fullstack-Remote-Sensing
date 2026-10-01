#| title: A thesis starter: GEDI biomass from embeddings, tested two ways (Python)
#| description: The same model and the same two tests as the JavaScript tab, with the scores and plots done in pandas.

"""
CHAPTER 36 | A one-week starting point for three open topics at once:
embeddings, biomass and LiDAR. GEDI's spaceborne LiDAR gives above ground
biomass density (AGBD) at scattered 25 m footprints. Can the 64 AlphaEarth
embedding dimensions spread those footprints into a wall-to-wall map, and
how much of the answer depends on how you test it?

Area: lowland forest and plantations on the Jambi / South Sumatra border.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([103.10, -2.40, 103.70, -1.90])
N_POINTS = 1500
N_FOLDS = 5
BLOCK_SIZE_M = 5000

# PART 1. GEDI L4A footprints, good quality only, 2022-2023
def good_quality(img):
    ok = img.select("l4_quality_flag").eq(1).And(img.select("degrade_flag").eq(0))
    return img.updateMask(ok)


agbd = (ee.ImageCollection("LARSE/GEDI/GEDI04_A_002_MONTHLY")
        .filterDate("2022-01-01", "2024-01-01").filterBounds(aoi)
        .map(good_quality).select("agbd").mosaic().clip(aoi))

# PART 2. The 2023 embeddings, one line
embeddings = (ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
              .filterDate("2023-01-01", "2024-01-01").filterBounds(aoi).mosaic())
bands = embeddings.bandNames()

# PART 3. Sample footprints; give each one a random fold and a block fold
has_shot = agbd.gt(0).rename("shot").toInt()
footprints = agbd.addBands(has_shot).stratifiedSample(
    numPoints=N_POINTS, classBand="shot", region=aoi, scale=25, seed=7,
    geometries=True, tileScale=4)

block_proj = ee.Projection("EPSG:3857").atScale(BLOCK_SIZE_M)
block_fold = (ee.Image.random(42).multiply(N_FOLDS).floor()
              .reproject(block_proj).rename("block_fold").toInt())

samples = (embeddings.addBands(block_fold)
           .sampleRegions(collection=footprints, properties=["agbd"], scale=10,
                          tileScale=4, geometries=True)
           .randomColumn("r", 42)
           .map(lambda f: f.set("random_fold",
                                ee.Number(f.get("r")).multiply(N_FOLDS).floor())))


def forest():
    return ee.Classifier.smileRandomForest(numberOfTrees=100, seed=7).setOutputMode("REGRESSION")


def out_of_fold(fold_property):
    """Train on four folds, predict the fifth, five times. Every point is
    predicted by a model that never saw it."""
    def one(k):
        k = ee.Number(k)
        train = samples.filter(ee.Filter.neq(fold_property, k))
        test = samples.filter(ee.Filter.eq(fold_property, k))
        model = forest().train(train, "agbd", bands)
        return test.classify(model, "predicted").map(
            lambda f: f.set("scheme", fold_property))
    return ee.FeatureCollection(ee.List.sequence(0, N_FOLDS - 1).map(one)).flatten()


predictions = (out_of_fold("random_fold").merge(out_of_fold("block_fold"))
               .select(["agbd", "predicted", "scheme", "block_fold"]))

# PART 4. A map from a model trained on every footprint
model_all = forest().train(samples, "agbd", bands)
agbd_map = embeddings.clip(aoi).classify(model_all).rename("agbd")

SCHEMES = {"random_fold": "random 5-fold", "block_fold": "5 km block 5-fold"}


def scores(df):
    """R², RMSE and bias per test design. The SD row is the 'guess the mean' bar."""
    rows = []
    for key, name in SCHEMES.items():
        d = df[df["scheme"] == key]
        e = d["predicted"] - d["agbd"]
        rows.append({"test design": name, "points": len(d),
                     "r2": 1 - (e ** 2).sum() / ((d["agbd"] - d["agbd"].mean()) ** 2).sum(),
                     "rmse_Mg_ha": np.sqrt((e ** 2).mean()), "bias_Mg_ha": e.mean(),
                     "sd_of_gedi_agbd": d["agbd"].std()})
    return pd.DataFrame(rows)


def plot_two_tests(df):
    """Out-of-fold predictions against GEDI AGBD, random folds beside block folds."""
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.4), sharex=True, sharey=True)
    top = float(np.percentile(df["agbd"], 99))
    for ax, (key, name) in zip(axes, SCHEMES.items()):
        d = df[df["scheme"] == key]
        e = d["predicted"] - d["agbd"]
        r2 = 1 - (e ** 2).sum() / ((d["agbd"] - d["agbd"].mean()) ** 2).sum()
        ax.scatter(d["agbd"], d["predicted"], s=5, alpha=0.35, color="#35618f")
        ax.plot([0, top], [0, top], ls="--", lw=1, color="#555555")
        ax.set_xlim(0, top)
        ax.set_ylim(0, top)
        ax.set_title(f"{name}: R² {r2:.2f}", loc="left", fontsize=9)
        ax.set_xlabel("GEDI L4A AGBD (Mg/ha)")
    axes[0].set_ylabel("Predicted from embeddings (Mg/ha)")
    fig.tight_layout()
    return fig


def products():
    src = "GEDI L4A 2022-2023 (footprints); Google Satellite Embedding V1, 2023."
    return [
        {"kind": "chart", "name": "ch36-two-tests", "data": predictions,
         "plot": plot_two_tests,
         "caption": "Each dot is one GEDI footprint predicted by a model that never saw "
                    "it. Left: folds drawn at random. Right: whole 5 km blocks held out, "
                    "so neighbours of a test point are never in training. The dashed "
                    "line is a perfect prediction."},
        {"kind": "table", "name": "ch36-scores", "data": predictions, "transform": scores,
         "floatfmt": ("", ".0f", ".2f", ".1f", ".1f", ".1f"),
         "caption": "Scores for the same 1,500 footprints under the two test designs. "
                    "An RMSE close to the SD column means the model does little better "
                    "than guessing the mean. The reference is GEDI's own modelled AGBD, "
                    "not field plots, so these numbers measure agreement with GEDI. Unlike "
                    "chapter “Ground Truth and Sampling Design”, block and random folds agree here: 1,500 footprints "
                    "drawn from a 55 by 55 km box are seldom close neighbours, so "
                    "there was little leakage to remove."},
        {"kind": "map", "name": "ch36-agbd-map", "image": agbd_map, "region": aoi,
         "vis": {"min": 0, "max": 250,
                 "palette": ["f7fcb9", "addd8e", "41ab5d", "006837", "00361c"]},
         "legend": "Predicted AGBD (Mg/ha), a model of a model", "source": src,
         "title": "GEDI biomass spread wall to wall by the embeddings",
         "caption": "A random forest trained on all 1,500 footprints, applied to every "
                    "10 m pixel. Read it with the block-CV score above, not the random "
                    "one, and remember the target is itself a model output."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(predictions.size().getInfo())
