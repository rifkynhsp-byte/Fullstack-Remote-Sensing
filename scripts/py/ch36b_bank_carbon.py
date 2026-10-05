#| title: Thesis starters 1-6: embeddings and biomass (Python)
#| description: A first experiment for each topic, run on real data: a label learning curve, embedding change against global loss, predictor-year sensitivity at field plots, conformal intervals, and allometry choice.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 36 | One afternoon experiment per topic. None of them is a thesis;
each one shows that the question is real and gives the first number to beat.

    T1  labels needed with embeddings        WorldCover as reference, train in one area, test in another
    T2  smallholder loss                      embedding change 2020-2021 vs Hansen loss 2021, Jambi
    T3  (the starter above: GEDI biomass from embeddings)
    T4  date mismatch at plots                CIFOR mangrove plots vs Landsat NDVI of each year
    T5  honest uncertainty                    split conformal intervals for the T3 model
    T6  allometry choice                      two published equations on one simulated stand
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

EMB = ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")


def embeddings(year, region):
    return EMB.filterDate(f"{year}-01-01", f"{year + 1}-01-01").filterBounds(region).mosaic()


# ---------------------------------------------------------------------------
# T1. How few labels? Train near Bandung, test near Garut (another landscape).
# ---------------------------------------------------------------------------
train_box = ee.Geometry.Rectangle([107.45, -7.05, 107.80, -6.80], None, False)
test_box = ee.Geometry.Rectangle([107.75, -7.35, 108.05, -7.10], None, False)
wc = ee.Image("ESA/WorldCover/v200/2021").select("Map")
WC = {10: "trees", 30: "grass", 40: "crops", 50: "built", 80: "water"}
wc5 = wc.remap(list(WC), list(range(len(WC))), -1).rename("label")


def labelled(box, n, seed):
    img = embeddings(2021, box).addBands(wc5.updateMask(wc5.gte(0)))
    return img.stratifiedSample(numPoints=n, classBand="label", region=box, scale=10,
                                seed=seed, tileScale=4)


def learning_curve():
    test = labelled(test_box, 150, 99)
    bands = EMB.first().bandNames()
    rows = []
    for n in [5, 10, 20, 50, 100]:
        for seed in [1, 2, 3]:
            rf = (ee.Classifier.smileRandomForest(100, seed=seed)
                  .train(labelled(train_box, n, seed), "label", bands))
            acc = test.classify(rf).errorMatrix("label", "classification").accuracy()
            rows.append({"labels_per_class": n, "seed": seed, "accuracy": acc.getInfo()})
    return pd.DataFrame(rows)


def plot_learning(df):
    g = df.groupby("labels_per_class")["accuracy"]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    ax.scatter(df.labels_per_class, df.accuracy, color="#9aa5b1", s=14, label="each run")
    ax.plot(g.mean().index, g.mean(), "o-", color="#1b7837", label="mean of 3 runs")
    ax.set_xscale("log"); ax.set_xticks([5, 10, 20, 50, 100], [5, 10, 20, 50, 100])
    ax.set_xlabel("Training labels per class (Bandung)")
    ax.set_ylabel("Agreement with WorldCover (Garut)")
    ax.set_title("T1: the curve flattens early; where it flattens is the thesis",
                 loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


# ---------------------------------------------------------------------------
# T2. Embedding change against Hansen loss, Jambi smallholder landscape
# ---------------------------------------------------------------------------
jambi = ee.Geometry.Rectangle([102.90, -1.95, 103.30, -1.65], None, False)
gfc = ee.Image("UMD/hansen/global_forest_change_2023_v1_11")
e20, e21 = embeddings(2020, jambi), embeddings(2021, jambi)
# Embeddings are unit vectors: 1 - dot product is a change score from 0 to 2.
change = ee.Image(1).subtract(e20.multiply(e21).reduce(ee.Reducer.sum())).rename("change")
forest2020 = gfc.select("treecover2000").gte(50).And(gfc.select("lossyear").eq(0)
                                                     .Or(gfc.select("lossyear").gt(20)))
loss21 = gfc.select("lossyear").eq(21)
group = (ee.Image(0).where(forest2020.And(loss21.Not()), 1).where(loss21, 2)
         .rename("group").updateMask(forest2020.Or(loss21)))
change_samples = change.addBands(group).stratifiedSample(
    numPoints=1500, classBand="group", region=jambi, scale=30, seed=5, tileScale=4)


def plot_change(df):
    stable = df[df.group == 1]["change"]; lost = df[df.group == 2]["change"]
    thr = stable.quantile(0.95)
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    bins = np.linspace(0, max(df.change.quantile(0.995), thr * 1.5), 50)
    ax.hist(stable, bins, color="#1b7837", alpha=0.6, density=True, label="forest, no Hansen loss")
    ax.hist(lost, bins, color="#c0392b", alpha=0.6, density=True, label="Hansen loss in 2021")
    ax.axvline(thr, color="#1f2933", ls="--", lw=1)
    ax.text(thr, ax.get_ylim()[1] * 0.9, " 95th pct of stable", fontsize=7)
    ax.set_xlabel("Embedding change 2020 to 2021 (1 - cosine)")
    ax.set_title(f"T2: {(lost > thr).mean():.0%} of Hansen-loss pixels exceed the stable "
                 f"95th percentile", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def change_table(df):
    stable = df[df.group == 1]["change"]; lost = df[df.group == 2]["change"]
    thr = stable.quantile(0.95)
    return pd.DataFrame([{"group": "stable forest", "pixels": len(stable),
                          "median_change": stable.median(), "share_above_threshold": (stable > thr).mean()},
                         {"group": "Hansen loss 2021", "pixels": len(lost),
                          "median_change": lost.median(), "share_above_threshold": (lost > thr).mean()}])


# ---------------------------------------------------------------------------
# T4. Which year's image matches the plots? CIFOR mangrove plots, West Papua
# ---------------------------------------------------------------------------
plots = (ee.FeatureCollection("projects/ee-rifkynauvalhsp2/assets/Mangrove_CIFOR_WestPapua_pivot")
         .map(lambda f: f.set("AGB", f.get("AGB (Mg/ha)"))))


def landsat_ndvi(year):
    def prep(img):
        qa = img.select("QA_PIXEL")
        ok = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        sr = img.select(["SR_B5", "SR_B4"]).multiply(0.0000275).add(-0.2)
        return sr.normalizedDifference(["SR_B5", "SR_B4"]).rename("ndvi").updateMask(ok)
    return (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterBounds(plots.geometry())
            .filterDate(f"{year}-01-01", f"{year + 1}-01-01").map(prep).median())


def year_sensitivity():
    rows = []
    for y in range(2013, 2024):
        fc = landsat_ndvi(y).reduceRegions(collection=plots, reducer=ee.Reducer.mean(),
                                           scale=30)
        d = pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]]).dropna(
            subset=["mean", "AGB"])
        r = np.corrcoef(d["mean"], d["AGB"])[0, 1] if len(d) > 5 else np.nan
        rows.append({"year": y, "plots_with_data": len(d), "r_ndvi_agb": r})
    return pd.DataFrame(rows)


def plot_years(df):
    fig, ax = plt.subplots(figsize=(6.6, 3.2))
    ax.plot(df.year, df.r_ndvi_agb, "o-", color="#2a78d6")
    ax.axhline(0, color="#9aa5b1", lw=0.8)
    ax.set_xlabel("Year of the Landsat NDVI composite")
    ax.set_ylabel("Correlation with plot AGB (r)")
    ax.set_title("T4: the same plots, a different answer every year", loc="left",
                 fontsize=10)
    return fig


# ---------------------------------------------------------------------------
# T5. Honest uncertainty: split conformal intervals for GEDI biomass
# ---------------------------------------------------------------------------
aoi5 = ee.Geometry.Rectangle([103.10, -2.40, 103.70, -1.90])


def conformal():
    gedi = (ee.ImageCollection("LARSE/GEDI/GEDI04_A_002_MONTHLY")
            .filterDate("2022-01-01", "2024-01-01").filterBounds(aoi5)
            .map(lambda i: i.updateMask(i.select("l4_quality_flag").eq(1)
                                        .And(i.select("degrade_flag").eq(0))))
            .select("agbd").mosaic())
    emb = embeddings(2023, aoi5)
    block = (ee.Image.random(42).multiply(5).floor()
             .reproject(ee.Projection("EPSG:3857").atScale(5000)).rename("block").toInt())
    pts = gedi.addBands(gedi.gt(0).rename("s").toInt()).stratifiedSample(
        numPoints=2000, classBand="s", region=aoi5, scale=25, seed=7, geometries=True,
        tileScale=4)
    s = emb.addBands(block).sampleRegions(collection=pts, properties=["agbd"], scale=10,
                                          tileScale=4)
    rf = (ee.Classifier.smileRandomForest(100, seed=7).setOutputMode("REGRESSION")
          .train(s.filter(ee.Filter.lte("block", 2)), "agbd", emb.bandNames()))
    rows = []
    for name, part in [("calibration", s.filter(ee.Filter.eq("block", 3))),
                       ("test", s.filter(ee.Filter.eq("block", 4)))]:
        p = part.classify(rf, "pred")
        d = pd.DataFrame({"agbd": p.aggregate_array("agbd").getInfo(),
                          "pred": p.aggregate_array("pred").getInfo()})
        rows.append(d.assign(part=name))
    return pd.concat(rows)


def conformal_table(df):
    cal = df[df.part == "calibration"]; test = df[df.part == "test"]
    out = []
    for level in [0.8, 0.9]:
        q = np.quantile(np.abs(cal.agbd - cal.pred), level)
        cover = (np.abs(test.agbd - test.pred) <= q).mean()
        out.append({"target_coverage": level, "half_width_Mg_ha": q,
                    "coverage_on_new_blocks": cover, "test_footprints": len(test)})
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# T6. Allometry choice on one simulated mangrove stand (method demonstration)
# ---------------------------------------------------------------------------
def allometry_frame(n_trees=600, n_sim=2000, seed=1):
    """A SIMULATED stand (not field data): diameters from a reverse-J
    distribution, 5-60 cm. Two published no-height equations:
      Chave et al. 2005, moist forest: ρ exp(-1.499 + 2.148 lnD + 0.207 lnD² - 0.0281 lnD³)
      Komiyama et al. 2005, mangroves: 0.251 ρ D^2.46
    Monte Carlo: wood density ±10 % (1 sd), diameter ±2 % per tree."""
    rng = np.random.default_rng(seed)
    d = np.clip(5 + rng.exponential(9, n_trees), 5, 60)
    rows = []
    for _ in range(n_sim):
        rho = 0.70 * (1 + 0.10 * rng.standard_normal())
        dd = d * (1 + 0.02 * rng.standard_normal(n_trees))
        ln = np.log(dd)
        chave = rho * np.exp(-1.499 + 2.148 * ln + 0.207 * ln ** 2 - 0.0281 * ln ** 3)
        komi = 0.251 * rho * dd ** 2.46
        rows.append({"Chave 2005 (moist)": chave.sum() / 1000,
                     "Komiyama 2005 (mangrove)": komi.sum() / 1000})
    return pd.DataFrame(rows)                      # Mg per hectare (stand = 1 ha)


def plot_allometry(df):
    fig, ax = plt.subplots(figsize=(6.6, 3.2))
    for col, c in zip(df.columns, ["#2a78d6", "#c0392b"]):
        ax.hist(df[col], 50, color=c, alpha=0.6, label=col)
    diff = (df.iloc[:, 0].median() / df.iloc[:, 1].median() - 1) * 100
    ax.set_xlabel("Above-ground biomass of the stand (Mg/ha)")
    spread = (df.iloc[:, 0].quantile(0.95) / df.iloc[:, 0].median() - 1) * 100
    ax.set_title(f"T6: the equation shifts the answer by {diff:+.0f} %; wood density "
                 f"alone spreads it by about ±{spread:.0f} %", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    ax.text(0.99, -0.22, "Simulated stand: 600 trees, ρ = 0.70 ± 10 %, D ± 2 %",
            transform=ax.transAxes, ha="right", fontsize=7, color="#6b7680")
    return fig


def products():
    return [
        {"kind": "chart", "name": "t01-learning", "data": learning_curve, "plot": plot_learning,
         "caption": "T1. Random Forest on 2021 embeddings, trained with n WorldCover labels "
                    "per class near Bandung and tested on 750 labels near Garut. WorldCover "
                    "is itself a map, so this measures agreement, not truth."},
        {"kind": "chart", "name": "t02-change", "data": change_samples, "plot": plot_change,
         "caption": "T2. Embedding change between 2020 and 2021 in Jambi, for forest that "
                    "Hansen says stayed and forest Hansen says was lost in 2021."},
        {"kind": "table", "name": "t02-table", "data": change_samples, "transform": change_table,
         "floatfmt": ("", ",.0f", ".3f", ".0%"),
         "caption": "T2. The thesis question lives in the 5 % of 'stable' forest that "
                    "changes as much as lost forest: missed loss, or something else?"},
        {"kind": "chart", "name": "t04-years", "data": year_sensitivity, "plot": plot_years,
         "caption": "T4. Correlation of Landsat 8 NDVI with field AGB at the CIFOR West "
                    "Papua plots, for each year's composite. Without survey dates the "
                    "'right' year is unknown."},
        {"kind": "table", "name": "t05-conformal", "data": conformal,
         "transform": conformal_table, "floatfmt": (".0%", ".0f", ".0%", ".0f"),
         "caption": "T5. Split conformal intervals for GEDI biomass from embeddings: "
                    "calibrated on one spatial block, checked on another."},
        {"kind": "chart", "name": "t06-allometry", "data": allometry_frame,
         "plot": plot_allometry,
         "caption": "T6. One simulated stand, two published equations "
                    "(Chave et al. 2005; Komiyama et al. 2005), with Monte Carlo noise in "
                    "wood density and diameter. A method demonstration, not a field result."},
    ]


if __name__ == "__main__":
    print(allometry_frame(n_sim=50).median())
