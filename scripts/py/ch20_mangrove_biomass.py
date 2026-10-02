#| title: Mangrove biomass from 45 field plots (Python)
#| description: The same three models and leave-one-out test as the JavaScript tab, in Python.

"""
CHAPTER 20 | Above ground biomass from CIFOR field plots in West Papua.
Straight line on canopy height, random forest on a sensor stack, random
forest on embeddings; every model scored by leave-one-plot-out.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np

plots = (ee.FeatureCollection("projects/ee-rifkynauvalhsp2/assets/Mangrove_CIFOR_WestPapua_pivot")
         .map(lambda f: f.set("AGB", f.get("AGB (Mg/ha)"))))
region = plots.geometry().bounds().buffer(5000)


def mask_s2(i):
    scl = i.select("SCL")
    return i.updateMask(scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))).divide(10000)


# STEP 1. Predictors, all 2020
s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region)
      .filterDate("2020-01-01", "2021-01-01").map(mask_s2).median())
s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(region)
      .filterDate("2020-01-01", "2021-01-01")
      .filter(ee.Filter.eq("instrumentMode", "IW"))
      .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
      .select(["VV", "VH"]).median())
aw3d = ee.ImageCollection("JAXA/ALOS/AW3D30/V4_1")
stack = (s2.normalizedDifference(["B8", "B4"]).rename("NDVI")
         .addBands(s2.normalizedDifference(["B8", "B11"]).rename("NDMI"))
         .addBands(s1)
         .addBands(ee.Image("users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1").rename("canopy_height"))
         .addBands(aw3d.select("DSM").filterBounds(region).mosaic().rename("elevation"))
         .float())
embeddings = (ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
              .filterBounds(region).filterDate("2020-01-01", "2021-01-01").mosaic())

table = (stack.addBands(embeddings)
         .reduceRegions(collection=plots.map(lambda f: f.buffer(20)),
                        reducer=ee.Reducer.mean(), scale=10, tileScale=4)
         .filter(ee.Filter.notNull(["canopy_height", "NDVI", "VH", "A00"])))
as_list = table.toList(100)
indexed = ee.FeatureCollection(as_list.map(
    lambda f: ee.Feature(f).set("idx", as_list.indexOf(f))))

# STEP 2. Leave one out, three models
STACK_BANDS = ["NDVI", "NDMI", "VV", "VH", "canopy_height", "elevation"]
EMB_BANDS = embeddings.bandNames()


def rf(training, bands):
    return (ee.Classifier.smileRandomForest(numberOfTrees=200, seed=7)
            .setOutputMode("REGRESSION").train(training, "AGB", bands))


def leave_one_out(held):
    others = indexed.filter(ee.Filter.neq("idx", held.get("idx")))
    fit = others.reduceColumns(ee.Reducer.linearFit(), ["canopy_height", "AGB"])
    linear = ee.Number(fit.get("offset")).add(
        ee.Number(fit.get("scale")).multiply(held.get("canopy_height")))
    one = ee.FeatureCollection([held])
    return held.set({
        "pred_linear": linear,
        "pred_rf_stack": one.classify(rf(others, STACK_BANDS), "p").first().get("p"),
        "pred_rf_embed": one.classify(rf(others, EMB_BANDS), "p").first().get("p"),
    })


loo = indexed.map(leave_one_out).select(
    ["AGB", "Category", "canopy_height", "NDVI", "pred_linear", "pred_rf_stack",
     "pred_rf_embed"])

MODELS = {"pred_linear": "line on canopy height",
          "pred_rf_stack": "random forest, sensor stack",
          "pred_rf_embed": "random forest, embeddings"}


def scores_frame(df):
    """RMSE, R² and bias per model, plus a bootstrap 90 % interval on RMSE.

    The bootstrap is the part that is awkward in Earth Engine and one line of
    numpy here: resample the 45 plots with replacement 2,000 times.
    """
    import pandas as pd
    rng = np.random.default_rng(1)
    rows = []
    for col, name in MODELS.items():
        e = (df[col] - df["AGB"]).to_numpy()
        boot = [np.sqrt(np.mean(rng.choice(e, e.size) ** 2)) for _ in range(2000)]
        r = np.corrcoef(df[col], df["AGB"])[0, 1]
        rows.append({"model": name, "rmse": np.sqrt(np.mean(e ** 2)),
                     "rmse_90pct_low": np.percentile(boot, 5),
                     "rmse_90pct_high": np.percentile(boot, 95),
                     "r2": r ** 2, "bias": e.mean()})
    return pd.DataFrame(rows)


def by_category(df):
    """What the field saw against what the 2020 satellites saw, per category."""
    return (df.groupby("Category")[["AGB", "canopy_height"]].mean()
            .assign(plots=df.groupby("Category").size())
            .sort_values("AGB").reset_index())


def plot_predicted_vs_observed(df):
    """Leave-one-out predictions against field AGB, one panel per model."""
    fig, axes = plt.subplots(1, 3, figsize=(9.5, 3.4), sharex=True, sharey=True)
    lim = [0, max(df["AGB"].max(), df[list(MODELS)].max().max()) * 1.05]
    for ax, (col, name) in zip(axes, MODELS.items()):
        ax.scatter(df["AGB"], df[col], s=14, color="#1b7837", alpha=0.8)
        ax.plot(lim, lim, color="#9aa5b1", lw=1, ls="--")
        rmse = np.sqrt(np.mean((df[col] - df["AGB"]) ** 2))
        ax.set_title(f"{name}\nRMSE {rmse:.0f} Mg/ha", fontsize=8.5, loc="left")
        ax.set_xlabel("Field AGB (Mg/ha)")
    axes[0].set_ylabel("Predicted, plot left out (Mg/ha)")
    fig.tight_layout()
    return fig


def plot_agb_by_category(df):
    """Field AGB by plot category: the gradient the models have to learn."""
    order = df.groupby("Category")["AGB"].median().sort_values().index
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for y, cat in enumerate(order):
        vals = df.loc[df["Category"] == cat, "AGB"]
        ax.scatter(vals, [y] * len(vals), s=18, color="#006837", alpha=0.8)
    ax.set_yticks(range(len(order)), order, fontsize=7.5)
    ax.set_xlabel("Field above ground biomass (Mg/ha)")
    ax.set_title("45 plots, from fish pond to undisturbed mangrove", loc="left")
    return fig


gmw = (ee.FeatureCollection("projects/sat-io/open-datasets/GMW/extent/gmw_v3_2020_vec")
       .filterBounds(region))
agb_map = (stack.classify(rf(indexed, STACK_BANDS))
           .updateMask(ee.Image(0).paint(gmw, 1)).rename("AGB"))
map_window = ee.Geometry.Rectangle([133.35, -4.0, 133.95, -3.45])


def range_frame(df):
    """Random forests average their training targets, so they cannot predict outside the
    range they saw and pull extremes towards the mean. How much does each model shrink it?"""
    import pandas as pd
    rows = [{"series": "field AGB", "min": df["AGB"].min(), "p10": df["AGB"].quantile(0.1),
             "p90": df["AGB"].quantile(0.9), "max": df["AGB"].max(), "sd": df["AGB"].std()}]
    for col, name in MODELS.items():
        v = df[col]
        rows.append({"series": name, "min": v.min(), "p10": v.quantile(0.1), "p90": v.quantile(0.9),
                     "max": v.max(), "sd": v.std()})
    return pd.DataFrame(rows)


# Carbon, with its error bar: AGB -> carbon (x 0.47, the IPCC default carbon fraction of dry
# biomass) -> CO2 (x 44/12). The map uses the best model, the embedding forest.
CARBON_FRACTION, CO2_PER_C = 0.47, 44 / 12
agb_emb = (embeddings.classify(rf(indexed, EMB_BANDS)).updateMask(ee.Image(0).paint(gmw, 1)).rename("AGB"))


def carbon_frame(df):
    """Total for the mapped mangrove, and two honest error bars.

    Pixel errors are not independent: a model that is wrong for one plot of a
    category is wrong for the whole category. So the uncertainty of a total is
    driven by the systematic error (the bias), not by RMSE divided by the square
    root of millions of pixels. Bootstrap the leave-one-out residuals of the 45
    plots to get an interval on the mean error, and apply it to the whole area.
    """
    import pandas as pd
    r = (agb_emb.multiply(ee.Image.pixelArea().divide(1e4)).rename("agb_x_ha")
         .addBands(ee.Image.pixelArea().divide(1e4).updateMask(agb_emb.mask()).rename("ha"))
         .reduceRegion(ee.Reducer.sum(), map_window, 30, maxPixels=1e10, tileScale=4).getInfo())
    area, total = r["ha"], r["agb_x_ha"]
    mean = total / area
    e = (df["pred_rf_embed"] - df["AGB"]).to_numpy()
    rng = np.random.default_rng(2)
    boot_bias = np.array([rng.choice(e, e.size).mean() for _ in range(5000)])
    lo, hi = np.percentile(boot_bias, [5, 95])
    to_co2 = lambda agb_mg_ha: agb_mg_ha * area * CARBON_FRACTION * CO2_PER_C / 1e6     # Mt CO2
    naive = np.sqrt(np.mean(e ** 2)) / np.sqrt(area)                                   # pretends pixels are independent
    rows = [
        ("mapped mangrove area (ha)", area, None, None),
        ("mean predicted AGB (Mg/ha)", mean, mean - hi, mean - lo),
        ("above ground carbon stock (Mt CO2e)", to_co2(mean), to_co2(mean - hi), to_co2(mean - lo)),
        ("same, if pixel errors were independent (wrong)", to_co2(mean), to_co2(mean - 1.645 * naive), to_co2(mean + 1.645 * naive)),
    ]
    return pd.DataFrame(rows, columns=["quantity", "estimate", "90% low", "90% high"])


def products():
    return [
        {"kind": "chart", "name": "ch20-agb-by-category", "data": loo,
         "plot": plot_agb_by_category,
         "caption": "Field AGB of the CIFOR SWAMP Bintuni plots (Murdiyarso et al. 2019, doi:10.17528/CIFOR/DATA.00108) by category. Regrowth climbs from "
                    "about 27 Mg/ha at 5 years to about 112 at 25."},
        {"kind": "chart", "name": "ch20-pred-vs-obs", "data": loo,
         "plot": plot_predicted_vs_observed,
         "caption": "Each point is a plot predicted by a model that never saw it. The "
                    "dashed line is a perfect prediction; the flat clouds are models "
                    "falling back on the average."},
        {"kind": "table", "name": "ch20-scores", "data": loo, "transform": scores_frame,
         "floatfmt": ("", ".1f", ".1f", ".1f", ".2f", ".1f"),
         "caption": "Leave-one-out error per model, with a bootstrap 90 % interval on "
                    "RMSE. Field AGB has a standard deviation of about 48 Mg/ha, so an "
                    "RMSE near 48 means the model does no better than guessing the mean. "
                    "Only the embeddings explain anything, and not much."},
        {"kind": "table", "name": "ch20-diagnosis", "data": loo, "transform": by_category,
         "columns": ["Category", "plots", "AGB", "canopy_height"],
         "floatfmt": ("", ".0f", ".1f", ".1f"),
         "caption": "Why the models fail. The 2020 canopy height map puts fish-pond "
                    "plots at about 22 m and five-year regrowth at 27 m, taller than "
                    "undisturbed stands. The plot table carries no survey dates: if ponds "
                    "have since regrown, or plot coordinates are off by a pixel or two, "
                    "the satellites and the field are describing different forests. No "
                    "model can fix that; matching dates and positions can."},
        {"kind": "map", "name": "ch20-agb-map", "image": agb_map, "region": map_window,
         "vis": {"min": 0, "max": 200, "palette": ["ffffcc", "78c679", "006837"]},
         "legend": "Above ground biomass (Mg/ha), mangrove only",
         "title": "Predicted mangrove AGB, sensor-stack forest",
         "source": "Field plots: CIFOR SWAMP Bintuni 2011 (Murdiyarso et al. 2019). Predictors 2020: S2, S1, ETH canopy height, "
                   "AW3D30. Mask: GMW 2020.",
         "caption": "The stack model trained on all plots, applied inside Global "
                    "Mangrove Watch 2020. Given the scores above, this map shows what the "
                    "model believes, not what is there. It is here so you can see how "
                    "convincing an unvalidated map looks."},
        {"kind": "table", "name": "ch20-range", "data": loo, "transform": range_frame,
         "floatfmt": ("", ".0f", ".0f", ".0f", ".0f", ".0f"),
         "caption": "The spread of field AGB against the spread of each model's leave-one-out predictions (Mg/ha)."},
        {"kind": "table", "name": "ch20-carbon", "data": loo, "transform": carbon_frame,
         "floatfmt": ("", ".2f", ".2f", ".2f"),
         "caption": "Above ground carbon of the mapped mangrove (map window, GMW 2020), from the embedding forest, with a 90 % interval from the bootstrapped bias of the 45 plots, and the falsely narrow interval that assumes independent pixel errors."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(loo.limit(3).getInfo())
