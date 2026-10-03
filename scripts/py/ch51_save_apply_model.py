#| title: Train once, save, apply anywhere: an Earth Engine model as an asset (Python)
#| description: A Random Forest trained near Bandung is saved as an Earth Engine asset, loaded again, and applied in four other places, with agreement measured in each. The mechanics of reuse, and the limits of transfer.

"""
CHAPTER 51 | A model you can hand to someone else.

    1. train       Random Forest on 2021 satellite embeddings, WorldCover 2021 labels,
                   near Bandung (5 classes: trees, grass, cropland, built, water)
    2. save        route A: Export.classifier.toAsset -> ee.Classifier.load
                   route B: the trees as text (classifier.explain()["trees"]) in a table
                            -> ee.Classifier.decisionTreeEnsemble
    3. check       the reloaded model must reproduce the original's answers
    4. apply       to four other places, each further from home, and measure
                   agreement with WorldCover there

The saved assets live in the book's Earth Engine project and are public, so the
script runs for anyone as is. To save your own copies, set the environment
variable BOOK_ASSET_FOLDER to a folder in your project (for example
projects/YOUR-PROJECT/assets/book); the script then creates them there.
"""

import os
import time

import ee
import matplotlib.pyplot as plt
import pandas as pd

FOLDER = os.environ.get("BOOK_ASSET_FOLDER", "projects/shaped-producer-482312-m0/assets/book")
TRAIN = FOLDER + "/train_bandung_2021"            # the training table, saved once
CLF_ASSET = FOLDER + "/lulc_rf_fromtable"          # route A: Export.classifier.toAsset
TREES = FOLDER + "/lulc_rf_trees"                  # route B: the trees as text, in a table
EMB = ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
WC = {10: "trees", 30: "grass", 40: "cropland", 50: "built", 80: "water"}
label = (ee.Image("ESA/WorldCover/v200/2021").select("Map")
         .remap(list(WC), list(range(len(WC))), -1).rename("label"))

HOME = ee.Geometry.Rectangle([107.45, -7.05, 107.80, -6.80], None, False)
PLACES = {
    "Bandung (home, new points)": [107.45, -7.05, 107.80, -6.80],
    "Garut, West Java (60 km)": [107.75, -7.35, 108.05, -7.10],
    "Lampung, Sumatra (400 km)": [105.10, -5.50, 105.45, -5.20],
    "Pontianak, Kalimantan (800 km)": [109.25, -0.15, 109.60, 0.15],
    "Makassar, Sulawesi (1,300 km)": [119.40, -5.25, 119.75, -4.95],
}


def embeddings(region):
    return EMB.filterDate("2021-01-01", "2022-01-01").filterBounds(region).mosaic()


def samples(region, n, seed, geometries=False):
    return (embeddings(region).addBands(label.updateMask(label.gte(0)))
            .stratifiedSample(numPoints=n, classBand="label", region=region, scale=10,
                              seed=seed, tileScale=4, geometries=geometries))


def _export(task):
    task.start()
    while task.status()["state"] in ("READY", "RUNNING"):
        time.sleep(15)
    return task.status()["state"]


def _exists(asset):
    try:
        ee.data.getAsset(asset)
        return True
    except ee.EEException:
        return False


def trained():
    """Train from a saved table so every run uses exactly the same samples."""
    if not _exists(FOLDER):
        ee.data.createAsset({"type": "FOLDER"}, FOLDER)
    if not _exists(TRAIN):
        _export(ee.batch.Export.table.toAsset(samples(HOME, 200, 1, True), "train", TRAIN))
    bands = EMB.first().bandNames()
    return ee.Classifier.smileRandomForest(100, seed=1).train(
        ee.FeatureCollection(TRAIN), "label", bands)


def saved_models():
    rf = trained()
    if not _exists(CLF_ASSET):                                  # route A
        _export(ee.batch.Export.classifier.toAsset(rf, "clf", CLF_ASSET))
    if not _exists(TREES):                                      # route B
        trees = ee.List(rf.explain().get("trees"))
        fc = ee.FeatureCollection(trees.map(
            lambda t: ee.Feature(ee.Geometry.Point([0, 0]), {"tree": t})))
        _export(ee.batch.Export.table.toAsset(fc, "trees", TREES))
    route_a = ee.Classifier.load(CLF_ASSET)
    route_b = ee.Classifier.decisionTreeEnsemble(
        ee.FeatureCollection(TREES).aggregate_array("tree"))
    return rf, route_a, route_b


def roundtrip_table():
    rf, a, b = saved_models()
    test = samples(HOME, 100, 99)
    acc = lambda c: test.classify(c).errorMatrix("label", "classification").accuracy().getInfo()
    return pd.DataFrame([
        {"model": "in memory, just trained", "agreement_home_test": acc(rf)},
        {"model": "route A: Export.classifier.toAsset, then ee.Classifier.load", "agreement_home_test": acc(a)},
        {"model": "route B: trees saved as text, then decisionTreeEnsemble", "agreement_home_test": acc(b)},
    ])


def transfer_table():
    model = saved_models()[2]                       # the route that survived the round trip
    rows = []
    for name, b in PLACES.items():
        box = ee.Geometry.Rectangle(b, None, False)
        test = samples(box, 100, 99)
        em = test.classify(model).errorMatrix("label", "classification")
        rows.append({"place": name, "agreement_with_WorldCover": em.accuracy().getInfo(),
                     "kappa": em.kappa().getInfo()})
    return pd.DataFrame(rows)


def plot_transfer(df):
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    ax.barh(df.place[::-1], df.agreement_with_WorldCover[::-1], color="#2a78d6")
    for y, v in enumerate(df.agreement_with_WorldCover[::-1]):
        ax.text(v, y, f" {v:.2f}", va="center", fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Agreement with WorldCover 2021 (500 test points per place)")
    ax.set_title("One saved model, five places", loc="left", fontsize=10)
    return fig


def applied_map():
    box = ee.Geometry.Rectangle(PLACES["Makassar, Sulawesi (1,300 km)"], None, False)
    return embeddings(box).classify(saved_models()[2]).clip(box)


# How many local samples does it take to fix a poor transfer? Pontianak, the weakest place.
LOCAL_K = [0, 5, 10, 25, 50, 100]


def local_frame():
    box = ee.Geometry.Rectangle(PLACES["Pontianak, Kalimantan (800 km)"], None, False)
    bands = EMB.first().bandNames()
    home = ee.FeatureCollection(TRAIN)
    pool = samples(box, 100, 7)                         # local training pool, a different seed from the test
    test = samples(box, 100, 99)
    rows = []
    for k in LOCAL_K:
        local = pool.randomColumn("r", 3).sort("r").map(lambda f: f.set("one", 1))
        local = ee.FeatureCollection([local.filter(ee.Filter.eq("label", c)).limit(k) for c in range(len(WC))]).flatten()
        acc = {}
        for name, train in (("Bandung + local", home.merge(local)), ("local only", local)):
            if k == 0 and name == "local only":
                acc[name] = None
                continue
            m = ee.Classifier.smileRandomForest(100, seed=1).train(train, "label", bands)
            acc[name] = test.classify(m).errorMatrix("label", "classification").accuracy()
        r = ee.Dictionary({k_: v for k_, v in acc.items() if v is not None}).getInfo()
        rows.append({"local_per_class": k, "Bandung + local": r.get("Bandung + local"), "local only": r.get("local only")})
    return pd.DataFrame(rows)


def plot_local(d):
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.plot(d.local_per_class, d["Bandung + local"], "o-", color="#2a78d6", label="Bandung model + local samples")
    ax.plot(d.local_per_class, d["local only"], "s--", color="#c0392b", label="local samples only")
    ax.set_xlabel("local training samples per class, Pontianak"); ax.set_ylabel("agreement with WorldCover")
    ax.set_ylim(0.5, 1); ax.spines[["top", "right"]].set_visible(False); ax.legend(frameon=False, fontsize=8)
    ax.set_title("A handful of local samples is worth more than distance", loc="left", fontsize=10)
    fig.tight_layout()
    return fig


PAL = ["006400", "ffff4c", "f096ff", "fa0000", "0064c8"]


def products():
    return [
        {"kind": "table", "name": "ch51-roundtrip", "data": roundtrip_table,
         "floatfmt": ("", ".3f"),
         "caption": "The same model before and after saving, scored on the same 500 home "
                    "test points. A saved model must give the same answers as the one you "
                    "trained; here only route B does."},
        {"kind": "table", "name": "ch51-transfer", "data": transfer_table,
         "floatfmt": ("", ".2f", ".2f"),
         "caption": "The Bandung model, saved and reloaded, applied in five places. "
                    "Agreement is with WorldCover, itself a map, so it measures consistency, "
                    "not truth."},
        {"kind": "chart", "name": "ch51-transfer-chart", "data": transfer_table,
         "plot": plot_transfer, "caption": "Agreement by place."},
        {"kind": "map", "name": "ch51-makassar", "image": applied_map(),
         "region": ee.Geometry.Rectangle(PLACES["Makassar, Sulawesi (1,300 km)"], None, False),
         "vis": {"min": 0, "max": 4, "palette": PAL},
         "classes": [(v, "#" + p) for v, p in zip(WC.values(), PAL)],
         "title": "The Bandung model applied in Makassar",
         "source": "Satellite Embedding 2021; model trained on WorldCover near Bandung. GEE.",
         "caption": "A model trained 1,300 km away, used without retraining."},
        {"kind": "table", "name": "ch51-local", "data": local_frame, "floatfmt": (",.0f", ".2f", ".2f"),
         "caption": "Pontianak, 500 test points: the Bandung training table plus k local samples per class, "
                    "against a model trained on the local samples alone."},
        {"kind": "chart", "name": "ch51-local-chart", "data": local_frame, "plot": plot_local, "live": False,
         "caption": "Agreement in Pontianak as local samples are added."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(transfer_table())
