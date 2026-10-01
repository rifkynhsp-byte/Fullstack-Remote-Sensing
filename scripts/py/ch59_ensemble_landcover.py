#| title: Ensemble land cover from field labels, and an honest validation (Python)
#| description: The author's 2,320 labelled points in 10 classes on the Riau coast (2023). Five scikit-learn models and two ensembles on satellite embeddings plus terrain, validated with a random split and with spatial blocks; what the global maps call each class; and an Earth Engine ensemble map with a model-agreement layer.

"""
CHAPTER 59 | Many models, one map, and the validation that tells the truth.

Labels: the author's reference points, 10 classes, made for 2023 imagery:
plantation, forest, agriculture, open land, water, mangrove, paddy,
oil palm, sago and rubber. Classes a global map does not have.

    1. features   Google Satellite Embedding 2023 (64 bands) + elevation and
                  slope (Copernicus GLO-30), sampled at every point in Earth Engine
    2. models     random forest, gradient boosting, SVM, k-nearest neighbours,
                  logistic regression (scikit-learn), then two ensembles:
                  soft voting and stacking
    3. validation (a) random 70/30 split, (b) spatial blocks of about 5 km held
                  out together (GroupKFold): neighbouring points never sit on
                  both sides of the split
    4. global     what WorldCover 2021 calls each of the 10 classes
    5. map        an Earth Engine ensemble (RF + CART + minimum distance, majority vote) and
                  the number of models that agree in every pixel
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

LABELS = "projects/ee-rifkynauvalhsp2/assets/export_training_data_lccagri"
NAMES = {1: "plantation", 2: "forest", 3: "agriculture", 4: "open land", 5: "water",
         6: "mangrove", 7: "paddy", 8: "oil palm", 9: "sago", 10: "rubber"}
PALETTE = ["8c6d31", "1a9850", "fee08b", "d8b365", "2c7fb8", "00a884", "a6d96a",
           "e6550d", "7b3294", "c51b7d"]
BLOCK_DEG = 0.05                       # about 5.5 km at the equator
map_aoi = ee.Geometry.Rectangle([102.65, 0.80, 103.05, 1.05], None, False)

points = ee.FeatureCollection(LABELS)
emb = (ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
       .filterDate("2023-01-01", "2024-01-01").filterBounds(points.geometry().bounds())
       .mosaic())
dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic() \
    .setDefaultProjection(ee.Projection("EPSG:4326").atScale(30))
terrain = dem.rename("elevation").addBands(ee.Terrain.slope(dem).rename("slope"))
stack = emb.addBands(terrain)
wc = ee.ImageCollection("ESA/WorldCover/v200").first().rename("worldcover")

_cache = {}


def table():
    """Every point with its 66 features, its block and its WorldCover class."""
    if "df" not in _cache:
        fc = stack.addBands(wc).sampleRegions(collection=points, properties=["landcover"],
                                              scale=10, geometries=True, tileScale=8)
        rows = []
        for f in fc.getInfo()["features"]:
            p = f["properties"]
            p["lon"], p["lat"] = f["geometry"]["coordinates"]
            rows.append(p)
        df = pd.DataFrame(rows).dropna()
        df["block"] = (np.floor(df.lon / BLOCK_DEG).astype(int) * 10000
                       + np.floor(df.lat / BLOCK_DEG).astype(int))
        _cache["df"] = df
    return _cache["df"]


def models():
    from sklearn.ensemble import (HistGradientBoostingClassifier, RandomForestClassifier,
                                  StackingClassifier, VotingClassifier)
    from sklearn.linear_model import LogisticRegression
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC
    base = {
        "random forest": RandomForestClassifier(300, random_state=0, n_jobs=-1),
        "gradient boosting": HistGradientBoostingClassifier(random_state=0),
        "SVM (RBF)": make_pipeline(StandardScaler(), SVC(C=10, probability=True,
                                                          random_state=0)),
        "k-nearest neighbours": make_pipeline(StandardScaler(), KNeighborsClassifier(7)),
        "logistic regression": make_pipeline(StandardScaler(),
                                             LogisticRegression(max_iter=3000)),
    }
    ens = {
        "ensemble: soft vote": VotingClassifier(list(base.items()), voting="soft"),
        "ensemble: stacking": StackingClassifier(
            list(base.items()), final_estimator=LogisticRegression(max_iter=3000), cv=3),
    }
    return {**base, **ens}


def features(df):
    return [c for c in df.columns if c.startswith("A") and c[1:].isdigit()] + \
        ["elevation", "slope"]


def validation_table():
    if "validation" in _cache:
        return _cache["validation"]
    from sklearn.metrics import accuracy_score, cohen_kappa_score
    from sklearn.model_selection import GroupKFold, train_test_split
    df = table()
    X, y, g = df[features(df)].values, df.landcover.astype(int).values, df.block.values
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=0, stratify=y)
    rows = []
    for name, m in models().items():
        p = m.fit(Xtr, ytr).predict(Xte)
        pred = np.empty_like(y)
        for tr, te in GroupKFold(n_splits=5).split(X, y, g):
            pred[te] = m.fit(X[tr], y[tr]).predict(X[te])
        rows.append({"model": name, "random_split_accuracy": accuracy_score(yte, p),
                     "random_split_kappa": cohen_kappa_score(yte, p),
                     "spatial_block_accuracy": accuracy_score(y, pred),
                     "spatial_block_kappa": cohen_kappa_score(y, pred)})
        if name == "ensemble: soft vote":
            _cache["block_pred"] = pred
    out = pd.DataFrame(rows)
    out["points"] = len(df)
    out["blocks"] = df.block.nunique()
    _cache["validation"] = out
    return out


def plot_validation(df):
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    y = np.arange(len(df))
    ax.barh(y + 0.2, df.random_split_accuracy, 0.4, color="#9aa5b1", label="random 70/30 split")
    ax.barh(y - 0.2, df.spatial_block_accuracy, 0.4, color="#2a78d6",
            label="spatial blocks held out")
    ax.set_yticks(y, df.model, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("Overall accuracy")
    ax.set_title("Same models, two validations", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    return fig


def class_table():
    """Per-class recall of the soft-vote ensemble under spatial blocks, and where the
    points of each class sit (number of blocks)."""
    if "block_pred" not in _cache:
        validation_table()
    df = table()
    y, p = df.landcover.astype(int).values, _cache["block_pred"]
    rows = []
    for k, n in NAMES.items():
        m = y == k
        wrong = pd.Series(p[m][p[m] != k]).map(NAMES).value_counts()
        rows.append({"class": n, "points": int(m.sum()),
                     "blocks_with_this_class": df.block[m].nunique(),
                     "recall_spatial_blocks": (p[m] == k).mean(),
                     "most_often_confused_with": wrong.index[0] if len(wrong) else ""})
    return pd.DataFrame(rows)


def worldcover_table():
    wc_names = {10: "trees", 20: "shrubland", 30: "grassland", 40: "cropland", 50: "built-up",
                60: "bare", 80: "water", 90: "herbaceous wetland", 95: "mangroves"}
    df = table()
    rows = []
    for k, n in NAMES.items():
        s = df[df.landcover.astype(int) == k].worldcover.map(wc_names).value_counts(normalize=True)
        rows.append({"author's class": n, "WorldCover calls it": s.index[0],
                     "share": s.iloc[0],
                     "second": f"{s.index[1]} ({s.iloc[1]:.0%})" if len(s) > 1 else ""})
    return pd.DataFrame(rows)


# Earth Engine ensemble map: three classifiers, majority vote, and agreement.
samples = stack.sampleRegions(collection=points, properties=["landcover"], scale=10,
                              tileScale=8)
bands = stack.bandNames()
# Light models for the map: gradient boosting is too slow to draw over a large area.
ee_models = [ee.Classifier.smileRandomForest(100, seed=1),
             ee.Classifier.smileCart(),
             ee.Classifier.minimumDistance("mahalanobis")]   # scale-aware: elevation is in metres
votes = ee.ImageCollection([stack.clip(map_aoi).classify(m.train(samples, "landcover", bands))
                            for m in ee_models])
ens_map = votes.mode().rename("class")
agreement = votes.map(lambda i: i.eq(ens_map)).sum().rename("agree")


def products():
    classes = [(n, "#" + c) for n, c in zip(NAMES.values(), PALETTE)]
    src = "Author's reference points (2023); Satellite Embedding 2023; Copernicus GLO-30. GEE."
    return [
        {"kind": "table", "name": "ch59-validation", "data": validation_table,
         "floatfmt": ("", ".3f", ".3f", ".3f", ".3f", ",.0f", ",.0f"),
         "caption": "Five models and two ensembles, scored with a random split and with "
                    "spatial blocks of about 5 km held out (5-fold GroupKFold)."},
        {"kind": "chart", "name": "ch59-validation-chart", "data": validation_table,
         "plot": plot_validation,
         "caption": "Overall accuracy under the two validation schemes."},
        {"kind": "table", "name": "ch59-classes", "data": class_table,
         "floatfmt": ("", ",.0f", ",.0f", ".0%", ""),
         "caption": "Soft-vote ensemble, spatial blocks: recall per class, how many blocks "
                    "each class appears in, and its most common confusion."},
        {"kind": "table", "name": "ch59-worldcover", "data": worldcover_table,
         "floatfmt": ("", "", ".0%", ""),
         "caption": "What ESA WorldCover 2021 calls the points of each of the author's "
                    "classes."},
        {"kind": "map", "name": "ch59-map", "image": ens_map, "region": map_aoi,
         "vis": {"min": 1, "max": 10, "palette": PALETTE}, "classes": classes,
         "title": "Ten classes, three models, one vote", "source": src,
         "caption": "Majority vote of random forest, CART and minimum distance in "
                    "Earth Engine, trained on all 2,320 points."},
        {"kind": "map", "name": "ch59-agreement", "image": agreement, "region": map_aoi,
         "vis": {"min": 1, "max": 3, "palette": ["d73027", "fee08b", "1a9850"]},
         "classes": [("1 of 3 models agree", "#d73027"), ("2 of 3", "#fee08b"),
                     ("all 3 agree", "#1a9850")],
         "title": "Where the models agree", "source": src,
         "caption": "Number of the three models that give the majority class. Red and "
                    "yellow areas are where the map is least certain."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(validation_table())
