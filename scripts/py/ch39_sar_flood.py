#| title: Supervised flood mapping with Sentinel-1 (Python)
#| description: The Jakarta New Year flood of 2020, mapped with a Random Forest on before and after Sentinel-1 images and the author's labelled polygons, with a band-name bug found, fixed and tested on held-out polygons.

"""
CHAPTER 39 | A flood under cloud, mapped by radar.

On 1 January 2020 record rainfall flooded large parts of Jakarta. Clouds
covered the city for days; Sentinel-1 did not care. This listing follows the
author's GEE101 script "15 - Supervised SAR":

    before  ascending passes, 20-31 December 2019
    after   ascending passes, 1-10 January 2020
    labels  50 polygons drawn by the author, 10 per class:
            permanent water, vegetation, flooded vegetation, urban, flooded urban

Two things are added: the inputs keep their names (the original lost the
"after" image through a band-name clash), and accuracy is measured on
polygons the model never saw.
"""

import json
from pathlib import Path

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[2] / "data" / "jakarta_flood2020_training.geojson"
CLASSES = {1: "permanent water", 2: "vegetation", 3: "flooded vegetation", 4: "urban",
           5: "flooded urban"}
PALETTE = ["106fd0", "35ff1c", "12ffc7", "c20000", "ffdb8d"]

roi = ee.Geometry.Rectangle([106.674, -6.329, 106.995, -6.121], None, False)
labels = ee.FeatureCollection(json.loads(DATA.read_text()))

s1 = (ee.ImageCollection("COPERNICUS/S1_GRD")
      .filter(ee.Filter.eq("instrumentMode", "IW"))
      .filter(ee.Filter.eq("orbitProperties_pass", "ASCENDING"))
      .filter(ee.Filter.eq("resolution_meters", 10))
      .filterBounds(roi).select(["VV", "VH"]))
before = s1.filterDate("2019-12-20", "2019-12-31").mosaic().focalMean(50, "circle", "meters")
after = s1.filterDate("2020-01-01", "2020-01-10").mosaic().focalMean(50, "circle", "meters")

# ---------------------------------------------------------------------------
# The bug. ee.Image.cat keeps the first image's names and renames the second
# image's clashing bands to VV_1, VH_1. Selecting "VV" therefore picks the
# BEFORE image only: the model never sees the flood.
# ---------------------------------------------------------------------------
original_stack = ee.Image.cat(before, after)
ORIGINAL_BANDS = ["VV"]

# The fix: name every input, and add the change itself as a feature.
stack = ee.Image.cat(
    before.rename(["VV_before", "VH_before"]),
    after.rename(["VV_after", "VH_after"]),
    after.subtract(before).rename(["VV_change", "VH_change"]))
BANDS = ["VV_before", "VH_before", "VV_after", "VH_after", "VV_change", "VH_change"]

# Polygon-level split: 7 polygons per class train, 3 test. Pixels from one
# polygon never sit on both sides (the lesson of chapter “Ground Truth and Sampling Design”).
train_poly = labels.filter(ee.Filter.lt("polygon", 7))
test_poly = labels.filter(ee.Filter.gte("polygon", 7))


def samples(img, bands, polys):
    return img.select(bands).sampleRegions(collection=polys, properties=["landcover"],
                                           scale=30, tileScale=4)


def fit(img, bands):
    return (ee.Classifier.smileRandomForest(50, seed=1)
            .train(samples(img, bands, train_poly), "landcover", bands))


rf_original = fit(original_stack, ORIGINAL_BANDS)
rf_fixed = fit(stack, BANDS)
classified = stack.select(BANDS).classify(rf_fixed).clip(roi)
smoothed = classified.reduceNeighborhood(ee.Reducer.mode(), ee.Kernel.circle(3))


def accuracy_table():
    rows = []
    for name, img, bands, rf in [
            ("As written: VV of the cat()-ed stack (= before only)", original_stack,
             ORIGINAL_BANDS, rf_original),
            ("Fixed: before, after and change, VV and VH", stack, BANDS, rf_fixed)]:
        train_acc = rf.confusionMatrix().accuracy()
        test = samples(img, bands, test_poly).classify(rf)
        em = test.errorMatrix("landcover", "classification")
        rows.append({"model": name, "training_accuracy": train_acc.getInfo(),
                     "held_out_accuracy": em.accuracy().getInfo(),
                     "held_out_kappa": em.kappa().getInfo()})
    return pd.DataFrame(rows)


def confusion_table():
    test = samples(stack, BANDS, test_poly).classify(rf_fixed)
    m = np.array(test.errorMatrix("landcover", "classification", list(CLASSES)).getInfo())
    df = pd.DataFrame(m, index=[f"true {c}" for c in CLASSES.values()],
                      columns=list(CLASSES.values()))
    df["recall"] = np.diag(m) / m.sum(1)
    return df.reset_index().rename(columns={"index": "held-out pixels"})


# What each class did between the two dates: the physics of P5, measured.
class_points = stack.select(["VV_before", "VV_after", "VH_before", "VH_after"]).sampleRegions(
    collection=labels, properties=["landcover"], scale=30, tileScale=4)


def plot_change(df):
    df = df.assign(cls=df["landcover"].astype(int).map(CLASSES))
    order = list(CLASSES.values())
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True)
    for ax, pol in zip(axes, ["VV", "VH"]):
        pos = np.arange(len(order))
        for k, (when, col) in enumerate([("before", "#9aa5b1"), ("after", "#2a78d6")]):
            data = [df.loc[df.cls == c, f"{pol}_{when}"] for c in order]
            bp = ax.boxplot(data, positions=pos + (k - 0.5) * 0.35, widths=0.3, vert=False,
                            patch_artist=True, showfliers=False)
            for b in bp["boxes"]:
                b.set_facecolor(col)
            ax.plot([], [], color=col, lw=6, label=when)
        ax.set_yticks(pos, order)
        ax.set_xlabel(f"{pol} backscatter (dB)")
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle("Flooded classes change, the rest do not: before (grey) and after (blue)",
                 x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    return fig


def area_table():
    g = (ee.Image.pixelArea().divide(1e6).addBands(smoothed.rename("cls"))
         .reduceRegion(ee.Reducer.sum().group(1, "cls"), roi, 30, maxPixels=1e9,
                       tileScale=4).get("groups").getInfo())
    return pd.DataFrame([{"class": CLASSES[int(d["cls"])], "area_km2": d["sum"]} for d in g])


change_rgb = ee.Image.cat(before.select("VV"), after.select("VV"), after.select("VV")).clip(roi)


def products():
    return [
        {"kind": "map", "name": "ch39-change", "image": change_rgb, "region": roi,
         "vis": {"min": -20, "max": 0},
         "title": "Jakarta, Sentinel-1 VV: before (red), after (green, blue)",
         "source": "Sentinel-1 GRD, ascending. GEE.",
         "caption": "A change composite: before in red, after in green and blue. Places "
                    "that were bright before and dark after (open ground turned into water) "
                    "appear red; places that became brighter appear cyan; unchanged places "
                    "stay grey."},
        {"kind": "table", "name": "ch39-accuracy", "data": accuracy_table,
         "floatfmt": ("", ".2f", ".2f", ".2f"),
         "caption": "Training accuracy flatters both models. On the 15 held-out polygons the "
                    "original band choice still scores 0.75 overall, but only because urban "
                    "pixels dominate the test set: its recall is 0.11 for permanent water, "
                    "0.16 for vegetation and 0.15 for flooded urban. Without the after "
                    "image it cannot know what flooded."},
        {"kind": "table", "name": "ch39-confusion", "data": confusion_table,
         "floatfmt": ("", ".0f", ".0f", ".0f", ".0f", ".0f", ".2f"),
         "caption": "Held-out confusion matrix of the fixed model (pixels from the 3 test "
                    "polygons per class)."},
        {"kind": "map", "name": "ch39-classified", "image": smoothed.clip(roi), "region": roi,
         "vis": {"min": 1, "max": 5, "palette": PALETTE},
         "classes": [(v, "#" + p) for v, p in zip(CLASSES.values(), PALETTE)],
         "title": "Flood classes, Jakarta, early January 2020",
         "source": "Sentinel-1 GRD; author's labels. GEE.",
         "caption": "Random Forest on before, after and change, smoothed with a 3-pixel "
                    "majority filter as in the original script."},
        {"kind": "chart", "name": "ch39-change-chart", "data": class_points,
         "plot": plot_change,
         "caption": "Backscatter of every labelled pixel before and after the flood."},
        {"kind": "table", "name": "ch39-area", "data": area_table, "floatfmt": ("", ",.1f"),
         "caption": "Area per class in the study box. A first estimate; it inherits every "
                    "error in the held-out matrix above."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(accuracy_table())
