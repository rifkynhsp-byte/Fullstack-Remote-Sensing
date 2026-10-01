#| title: Thesis starters 13-15: methods (Python)
#| description: First experiments for the method topics: random against spatial cross-validation, the area of applicability of a model, and whether an LST trend survives a change of satellite.

"""
CHAPTER 36 | Starters 13 to 15.

    T13  spatial validation      the same model scored with random folds and with 5 km block folds
    T14  area of applicability   dissimilarity index of Meyer and Pebesma (2021), West Java
    T15  LST trends              Terra (10:30) against Aqua (13:30), dry season, West Java
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

EMB = ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
WC = {10: "trees", 30: "grass", 40: "crops", 50: "built", 80: "water"}

# ---------------------------------------------------------------------------
# T13 and T14 share one labelled sample around Bandung, and unlabelled points
# across West Java for the applicability map.
# ---------------------------------------------------------------------------
bandung = ee.Geometry.Rectangle([107.30, -7.20, 107.95, -6.75], None, False)
west_java = ee.Geometry.Rectangle([106.4, -7.8, 108.8, -6.0], None, False)
emb = EMB.filterDate("2021-01-01", "2022-01-01").filterBounds(west_java).mosaic()
label = (ee.Image("ESA/WorldCover/v200/2021").select("Map")
         .remap(list(WC), list(range(len(WC))), -1).rename("label"))
lonlat = ee.Image.pixelLonLat()
train_pts = (emb.addBands(lonlat).addBands(label.updateMask(label.gte(0)))
             .stratifiedSample(numPoints=300, classBand="label", region=bandung, scale=10,
                               seed=8, tileScale=4))
region_pts = (emb.addBands(lonlat)
              .sample(region=west_java, scale=200, numPixels=3000, seed=9, tileScale=4))
FEATS = [f"A{i:02d}" for i in range(64)]


def cv_table(df):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GroupKFold, KFold, cross_val_score
    X, y = df[FEATS].to_numpy(), df["label"].to_numpy()
    blocks = (np.floor(df.longitude / 0.045).astype(int) * 1000
              + np.floor(df.latitude / 0.045).astype(int))           # about 5 km blocks
    rf = RandomForestClassifier(200, random_state=0, n_jobs=-1)
    rows = []
    for name, cv, groups in [("random 5-fold", KFold(5, shuffle=True, random_state=0), None),
                             ("5 km block 5-fold", GroupKFold(5), blocks)]:
        s = cross_val_score(rf, X, y, cv=cv, groups=groups)
        rows.append({"validation": name, "mean_accuracy": s.mean(), "lowest_fold": s.min()})
    return pd.DataFrame(rows)


def aoa_frame():
    tr = pd.DataFrame([f["properties"] for f in train_pts.getInfo()["features"]])
    rg = pd.DataFrame([f["properties"] for f in region_pts.getInfo()["features"]]).dropna()
    T, P = tr[FEATS].to_numpy(), rg[FEATS].to_numpy()
    d_tt = np.sqrt(((T[:, None] - T[None]) ** 2).sum(-1))
    mean_d = d_tt[np.triu_indices(len(T), 1)].mean()
    # Training DI: distance to the nearest training point in a different 5 km block.
    blk = (np.floor(tr.longitude / 0.045) * 1000 + np.floor(tr.latitude / 0.045)).to_numpy()
    d_tt[blk[:, None] == blk[None]] = np.inf
    di_train = d_tt.min(1) / mean_d
    q1, q3 = np.percentile(di_train[np.isfinite(di_train)], [25, 75])
    threshold = q3 + 1.5 * (q3 - q1)
    di = np.sqrt(((P[:, None] - T[None]) ** 2).sum(-1)).min(1) / mean_d
    return rg[["longitude", "latitude"]].assign(DI=di, inside=di <= threshold,
                                                threshold=threshold)


def plot_aoa(df):
    fig, ax = plt.subplots(figsize=(8, 4.4))
    sc = ax.scatter(df.longitude, df.latitude, c=df.DI, s=6, cmap="magma_r",
                    vmin=0, vmax=df.DI.quantile(0.98))
    ax.scatter(df.longitude[~df.inside], df.latitude[~df.inside], s=8, facecolors="none",
               edgecolors="#2a78d6", lw=0.5, label="outside applicability")
    ax.add_patch(plt.Rectangle((107.30, -7.20), 0.65, 0.45, fill=False, ec="#1b7837", lw=2,
                               label="training area"))
    fig.colorbar(sc, ax=ax, shrink=0.8, label="dissimilarity index")
    ax.set_aspect("equal")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.set_title(f"T14: {(~df.inside).mean():.0%} of West Java is outside the model's area "
                 "of applicability", loc="left", fontsize=10)
    ax.legend(frameon=True, fontsize=8, loc="lower left")
    return fig


# ---------------------------------------------------------------------------
# T15. Is the LST trend real or orbital? Terra vs Aqua, West Java
# ---------------------------------------------------------------------------
wj = (ee.FeatureCollection("FAO/GAUL/2025/level2")
      .filter(ee.Filter.eq("GAUL1_NAME", "Jawa Barat")).geometry())


def lst_frame():
    rows = []
    for name, cid in [("Terra (≈10:30)", "MODIS/061/MOD11A2"), ("Aqua (≈13:30)", "MODIS/061/MYD11A2")]:
        col = ee.ImageCollection(cid).select("LST_Day_1km")
        fc = ee.FeatureCollection([ee.Feature(None, {
            "year": y, "sensor": name,
            "lst": col.filterDate(f"{y}-06-01", f"{y}-11-01").mean().multiply(0.02)
                      .subtract(273.15).reduceRegion(ee.Reducer.mean(), wj, 1000,
                                                     maxPixels=1e9).get("LST_Day_1km")})
            for y in range(2003, 2025)])
        rows += [f["properties"] for f in fc.getInfo()["features"]]
    return pd.DataFrame(rows)


def plot_lst(df):
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    for (s, d), c in zip(df.groupby("sensor"), ["#e67e22", "#2a78d6"]):
        d = d.sort_values("year")
        slope, icpt, _, _ = stats.theilslopes(d.lst, d.year)
        ax.plot(d.year, d.lst, "o-", ms=3, color=c,
                label=f"{s}: {slope * 10:+.2f} °C per decade")
        ax.plot(d.year, icpt + slope * d.year, color=c, lw=1, ls="--")
    ax.set_ylabel("Dry-season daytime LST, West Java mean (°C)")
    ax.set_title("T15: two satellites, two trends; the difference is the thesis",
                 loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def products():
    return [
        {"kind": "table", "name": "t13-cv", "data": train_pts, "transform": cv_table,
         "floatfmt": ("", ".2f", ".2f"),
         "caption": "T13. One Random Forest on 2021 embeddings with WorldCover labels near "
                    "Bandung, scored two ways. Here the two agree (0.87 and 0.86), unlike "
                    "the field-label case in chapter “Ground Truth and Sampling Design”. "
                    "When random splits flatter a model and when they do not "
                    "[@ploton2020spatial; @roberts2017cv] is the question."},
        {"kind": "chart", "name": "t14-aoa", "data": aoa_frame, "plot": plot_aoa,
         "caption": "T14. Dissimilarity index [@meyer2021aoa] of 3,000 points across West "
                    "Java to the training data near Bandung. Above the threshold, the model "
                    "is extrapolating and its accuracy is unknown."},
        {"kind": "chart", "name": "t15-lst", "data": lst_frame, "plot": plot_lst,
         "caption": "T15. Mean dry-season daytime LST of West Java from Terra and Aqua, with "
                    "Sen's slope. Both satellites have drifted from their nominal overpass "
                    "times in their final years, so part of any trend can be orbital."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(lst_frame().head())
