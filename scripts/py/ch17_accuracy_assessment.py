#| title: Accuracy you can defend, and area with an error bar (Python)
#| description: The same assessment as the JavaScript tab, run from Python.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 17 | Confusion matrix, per class accuracy, and an area estimate
adjusted for map error with a 95 % interval (Olofsson et al. 2014), in Python.

Uses the random forest map and the held-out points from the chapter “Classical Supervised Learning” file.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np

from book_labels import CLASS_NAMES
from ch16_ensemble_classification import aoi, classified, validation_set

classified = classified["RF"]
SCALE = 10
AREA_SCALE = 30     # interactive limit; export at 10 m for a report

# PART 1-3. Confusion matrix and per class accuracy
validated = classified.sampleRegions(collection=validation_set, properties=["landcover"],
                                     scale=SCALE, tileScale=4)
matrix = validated.errorMatrix("landcover", "classification")

# PART 5. Map area per class
area_image = ee.Image.pixelArea().divide(10000).addBands(classified)
map_areas = area_image.reduceRegion(
    reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
    geometry=aoi, scale=AREA_SCALE, maxPixels=1e13, tileScale=4)

gmw = ee.FeatureCollection(
    "projects/sat-io/open-datasets/GMW/extent/gmw_v3_2020_vec").filterBounds(aoi)
gmw_ha = (ee.Image.pixelArea().divide(10000).clip(gmw.geometry())
          .reduceRegion(reducer=ee.Reducer.sum(), geometry=aoi, scale=AREA_SCALE,
                        maxPixels=1e13, tileScale=4).get("area"))

# Bring the small numbers home once; the arithmetic below is plain numpy.
summary = ee.Dictionary({"matrix": matrix.array(), "accuracy": matrix.accuracy(),
                         "kappa": matrix.kappa(), "groups": map_areas.get("groups"),
                         "gmw_ha": gmw_ha})


def olofsson(m, map_ha):
    """Rows = reference, columns = map. Returns adjusted ha and 95 % half width."""
    m = np.asarray(m, float)
    total = map_ha.sum()
    w = map_ha / total                        # share of map area, per MAP class
    n_i = m.sum(axis=0)                       # COLUMN totals, per MAP class
    with np.errstate(invalid="ignore", divide="ignore"):
        q = np.where(n_i > 0, m / n_i, 0.0)   # q[j, i] = n_ji / n_i
        var = np.where(n_i > 1, w**2 * q * (1 - q) / (n_i - 1), 0.0)
    p = (w * q).sum(axis=1)
    se = np.sqrt(var.sum(axis=1))
    return p * total, 1.96 * se * total


def assessment_table():
    """One trip to the server, then everything else locally."""
    import pandas as pd
    s = summary.getInfo()
    m = np.array(s["matrix"], float)[:5, :5]
    map_ha = np.zeros(5)
    for g in s["groups"]:
        if int(g["class"]) < 5:
            map_ha[int(g["class"])] = g["sum"]
    adj, ci = olofsson(m, map_ha)
    producer = np.diag(m) / m.sum(axis=1)
    user = np.diag(m) / m.sum(axis=0)
    df = pd.DataFrame({"class": CLASS_NAMES, "producer_pct": 100 * producer,
                       "user_pct": 100 * user, "map_ha": map_ha,
                       "adjusted_ha": adj, "ci95_ha": ci})
    return df, m, s


TABLE, MATRIX, SUMMARY = None, None, None


def _load():
    global TABLE, MATRIX, SUMMARY
    if TABLE is None:
        TABLE, MATRIX, SUMMARY = assessment_table()
    return TABLE


def plot_per_class(df):
    """Producer and user accuracy side by side. Which error matters for your decision?"""
    x = np.arange(len(df))
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.bar(x - 0.2, df["producer_pct"], 0.4, label="producer (1 − omission)", color="#2166ac")
    ax.bar(x + 0.2, df["user_pct"], 0.4, label="user (1 − commission)", color="#b35806")
    ax.set_xticks(x, df["class"], fontsize=8)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Accuracy (%)")
    ax.set_title("Per class accuracy on held-out points", loc="left")
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    return fig


def plot_areas(df):
    """Map area against error-adjusted area with its 95 % interval."""
    x = np.arange(len(df))
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.bar(x - 0.2, df["map_ha"] / 1000, 0.4, label="counted from the map", color="#9aa5b1")
    ax.bar(x + 0.2, df["adjusted_ha"] / 1000, 0.4, yerr=df["ci95_ha"] / 1000, capsize=3,
           label="adjusted, 95 % interval", color="#1b7837")
    ax.set_xticks(x, df["class"], fontsize=8)
    ax.set_ylabel("Area (thousand ha)")
    ax.set_title("A pixel count is not an area estimate", loc="left")
    ax.legend(frameon=False, fontsize=8)
    return fig


def confusion_frame():
    import pandas as pd
    _load()
    return pd.DataFrame(MATRIX.astype(int), columns=[f"map: {c}" for c in CLASS_NAMES]) \
        .assign(reference=CLASS_NAMES)[["reference"] + [f"map: {c}" for c in CLASS_NAMES]]


def products():
    df = _load()
    headline = {"overall_accuracy": SUMMARY["accuracy"], "kappa": SUMMARY["kappa"],
                "GMW_2020_mangrove_ha": SUMMARY["gmw_ha"],
                "this_map_mangrove_ha": df.loc[0, "map_ha"],
                "adjusted_mangrove_ha": df.loc[0, "adjusted_ha"]}
    return [
        {"kind": "table", "name": "ch17-confusion", "data": confusion_frame(),
         "caption": "Confusion matrix: rows are the reference label (WorldCover 2021), "
                    "columns are the map."},
        {"kind": "chart", "name": "ch17-per-class", "data": df, "plot": plot_per_class,
         "caption": "Producer and user accuracy per class, random forest from chapter “Classical Supervised Learning”."},
        {"kind": "chart", "name": "ch17-areas", "data": df, "plot": plot_areas,
         "caption": "Mapped area against the Olofsson error-adjusted estimate. The "
                    "interval is the part a report must carry."},
        {"kind": "table", "name": "ch17-area-table", "data": df,
         "floatfmt": ("", ".1f", ".1f", ".0f", ".0f", ".0f"),
         "caption": "Area by class in hectares (30 m). Adjusted = stratified estimator "
                    "with a 95 % confidence half width."},
        {"kind": "table", "name": "ch17-headline", "data": headline, "floatfmt": ".3f",
         "caption": "Headline numbers, with Global Mangrove Watch 2020 as a second "
                    "source. When two maps of one delta disagree this much, the area "
                    "needs an interval and a second opinion."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(_load())
