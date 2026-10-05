#| title: Out-of-home advertising placement in Sydney (Python)
#| description: Predict weekday pedestrian counts from open urban data with a stacked ensemble, combine them with income, population and points of interest in a multi-criteria score for three advertiser types, and rank bus shelters, city banners and bus routes.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 65 | Where should an advertiser buy a billboard?

Three steps, the same three an out-of-home (OOH) media planner takes:
  1. footfall   predict pedestrians at every candidate location from urban
                form (points of interest, roads, buildings, transit,
                night-time activity, employment), trained on the City of
                Sydney walking counts
  2. audience   combine footfall with income, population by age and nearby
                businesses into a score for each kind of advertiser
                (financial services, fast food, education)
  3. inventory  score the places an advertiser can actually buy: bus
                shelters, city banners and bus routes

Environment (Colab or any Python 3.10+):
    pip install geopandas rasterio exactextract scikit-learn xgboost cubist matplotlib

Data: all open. The exact files used for the book download automatically
(snapshot() below); scripts/py/ch65_ooh_data.py rebuilds them from the live
sources into OOH_DATA - City of
Sydney walking counts, employment survey, bus shelters and banners;
OpenStreetMap points of interest, roads, stops and bus routes; GHSL building
surface and volume, VIIRS night lights and WorldPop age structure (Earth
Engine); ABS Census 2021 income.
"""

import os
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from exactextract import exact_extract

DATA = Path(os.environ.get("OOH_DATA", "data/ooh_sydney"))

SNAPSHOT = "https://github.com/rifkynhsp-byte/Fullstack-Remote-Sensing/releases/download/data-v1/ch65_ooh_sydney_inputs.zip"


def snapshot():
    """The exact inputs used for the book (frozen 2 October 2026), downloaded once if they are not here.
    Rebuild them from the live sources instead with the data-building step described in the chapter."""
    if not (DATA / "counts.gpkg").exists():
        import io, zipfile, requests
        DATA.mkdir(parents=True, exist_ok=True)
        zipfile.ZipFile(io.BytesIO(requests.get(SNAPSHOT, timeout=600).content)).extractall(DATA)


snapshot()
SEED = 12345
TARGET = "weekday_count"
SURFACES = ["poi", "road_density", "nighttime", "bus_station", "building_surface",
            "building_volume", "jobs"]


def buffer_mean(raster, gdf, metres):
    """Area-weighted mean of a raster inside a buffer around every feature."""
    polys = gdf[["geometry"]].copy(); polys["geometry"] = gdf.buffer(metres)
    return exact_extract(str(raster), polys, "mean", output="pandas")["mean"].values


def graticule(ax, crs, n=4):
    """Latitude/longitude lines and edge labels on a map drawn in projected
    coordinates (metres), so every map can be located on the globe."""
    from pyproj import Transformer
    to_ll = Transformer.from_crs(crs, 4326, always_xy=True); to_xy = Transformer.from_crs(4326, crs, always_xy=True)
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    lon, lat = to_ll.transform([x0, x1, x0, x1], [y0, y0, y1, y1])
    span = max(max(lon) - min(lon), max(lat) - min(lat))
    step = next(s for s in (0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5) if span / s <= n + 1)
    fmt = lambda v, pos, neg: f"{abs(v):.{max(0, -int(np.floor(np.log10(step))))}f}°{pos if v >= 0 else neg}"
    for lo in np.arange(np.ceil(min(lon) / step) * step, max(lon), step):
        xs, ys = to_xy.transform(np.full(50, lo), np.linspace(min(lat) - step, max(lat) + step, 50))
        ax.plot(xs, ys, color="#888888", lw=0.4, ls="--", zorder=0.5)
        bx, _ = to_xy.transform(lo, min(lat))
        ax.text(bx, y0, fmt(lo, "E", "W"), ha="center", va="top", fontsize=7, color="#555555")
    for la in np.arange(np.ceil(min(lat) / step) * step, max(lat), step):
        xs, ys = to_xy.transform(np.linspace(min(lon) - step, max(lon) + step, 50), np.full(50, la))
        ax.plot(xs, ys, color="#888888", lw=0.4, ls="--", zorder=0.5)
        _, by = to_xy.transform(min(lon), la)
        ax.text(x0, by, fmt(la, "N", "S") + " ", ha="right", va="center", fontsize=7, color="#555555")
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_xlabel(""); ax.set_ylabel("")
    for s in ax.spines.values():
        s.set_visible(True); s.set_color("#999999"); s.set_linewidth(0.6)


# PART 1. Training points and predictor surfaces --------------------------------
_cache = {}


def add_features(gdf):
    assert gdf.crs.axis_info[0].unit_name == "metre"      # buffers are in metres
    gdf = gdf.copy()
    # Each surface at a street, a neighbourhood and a district scale.
    for name in SURFACES:
        for d in (100, 500, 1000):
            gdf[f"{name}_{d}m"] = buffer_mean(DATA / "surfaces" / f"{name}.tif", gdf, d)
    # Employment-survey attributes of the nearest block. Count sites stand on
    # streets, and streets lie between blocks, so "within" would match almost
    # nothing; an intersection would also drop every unmatched site.
    emp = gpd.read_file(DATA / "employment.gpkg").to_crs(gdf.crs)
    gdf = gpd.sjoin_nearest(gdf, emp[["jobs_per_ha", "floor_ratio", "Businesses", "geometry"]],
                            how="left", max_distance=100).drop(columns="index_right")
    return gdf[~gdf.index.duplicated()]


def features():
    if "counts" not in _cache:
        _cache["counts"] = add_features(gpd.read_file(DATA / "counts.gpkg"))
    return _cache["counts"]


def predictor_names(counts):
    num = counts.drop(columns=["geometry", TARGET], errors="ignore").select_dtypes("number")
    return [c for c in num.columns if c.lower() not in ("site_id", "fid", "objectid", "n_surveys")]


# PART 2. An honest split ---------------------------------------------------------
def split():
    if "split" in _cache:
        return _cache["split"]
    from sklearn.cluster import KMeans
    from sklearn.model_selection import train_test_split
    counts = features(); cols = predictor_names(counts)
    lab = counts[counts[TARGET].notna()].copy()
    X, y = lab[cols].fillna(0), lab[TARGET].values
    # Hold out 20 % of the counted sites before anything is learned.
    tr, te = train_test_split(np.arange(len(lab)), test_size=0.2, random_state=SEED)
    # Spatial folds: five location clusters, so a validation site's
    # neighbourhood is never in its own training fold.
    xy = np.column_stack([lab.geometry.x, lab.geometry.y])[tr]
    groups = KMeans(5, n_init=20, random_state=SEED).fit_predict(xy)
    # Counts run from a few hundred to over 70,000 a day. Models learn log(1 + count),
    # so a quiet laneway and a CBD corner are fitted on comparable terms;
    # predictions are transformed back before any error is reported.
    _cache["split"] = (X.iloc[tr], y[tr], X.iloc[te], y[te], groups, cols)
    return _cache["split"]


def learners():
    """The six base learners, each with pre-processing inside its own pipeline."""
    from cubist import Cubist
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.feature_selection import VarianceThreshold
    from sklearn.linear_model import ElasticNet
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import PowerTransformer, StandardScaler
    from sklearn.svm import SVR
    from xgboost import XGBRegressor
    # Yeo-Johnson instead of Box-Cox: the surfaces contain zeros.
    pre = lambda: [VarianceThreshold(1e-8), PowerTransformer(method="yeo-johnson"), StandardScaler()]
    return {
        "glmnet": (make_pipeline(*pre(), ElasticNet(max_iter=20000)),
                   {"elasticnet__alpha": np.logspace(-3, 2, 50), "elasticnet__l1_ratio": np.linspace(0, 1, 11)}),
        "ranger": (make_pipeline(*pre(), RandomForestRegressor(500, random_state=SEED)),
                   {"randomforestregressor__max_features": [0.2, 0.33, 0.5, 0.7, 1.0],
                    "randomforestregressor__min_samples_leaf": [1, 2, 5, 10]}),
        "cubist": (make_pipeline(*pre(), Cubist()),
                   {"cubist__n_committees": [1, 5, 10, 20], "cubist__neighbors": [None, 1, 5, 9]}),
        "svmL": (make_pipeline(*pre(), SVR(kernel="linear")),
                 {"svr__C": np.logspace(-2, 3, 20), "svr__epsilon": np.logspace(-2, 1, 10)}),
        "xgbTree": (make_pipeline(*pre(), XGBRegressor(random_state=SEED, n_jobs=2)),
                    {"xgbregressor__n_estimators": [100, 300, 600], "xgbregressor__max_depth": [2, 3, 4, 6],
                     "xgbregressor__learning_rate": [0.01, 0.03, 0.1, 0.3],
                     "xgbregressor__subsample": [0.6, 0.8, 1.0]}),
        "nnet": (make_pipeline(*pre(), MLPRegressor(max_iter=5000, random_state=SEED)),
                 {"mlpregressor__hidden_layer_sizes": [(4,), (8,), (16,), (8, 4)],
                  "mlpregressor__alpha": np.logspace(-4, 1, 20)}),
    }


def tuned(cv, groups):
    """Random hyperparameter search for every learner under one CV scheme."""
    from sklearn.model_selection import RandomizedSearchCV
    X, y, *_ = split()
    out = {}
    for name, (est, grid) in learners().items():
        s = RandomizedSearchCV(est, grid, n_iter=20, cv=cv, scoring="neg_mean_absolute_error",
                               random_state=SEED, n_jobs=-1)
        s.fit(X, np.log1p(y), groups=groups)
        out[name] = s
    return out


def models():
    if "models" in _cache:
        return _cache["models"]
    from sklearn.model_selection import GroupKFold, KFold
    X, y, Xt, yt, groups, _ = split()
    _cache["models"] = {"random": tuned(KFold(5, shuffle=True, random_state=SEED), None),
                        "spatial": tuned(GroupKFold(5), groups)}
    return _cache["models"]


# PART 3. Six learners, then a stack -------------------------------------------------
def stack():
    if "stack" in _cache:
        return _cache["stack"]
    from cubist import Cubist
    from sklearn.ensemble import StackingRegressor
    from sklearn.model_selection import GroupKFold
    X, y, Xt, yt, groups, _ = split()
    base = [(k, m.best_estimator_) for k, m in models()["spatial"].items()]
    st = StackingRegressor(base, final_estimator=Cubist(n_committees=5),
                           cv=list(GroupKFold(5).split(X, y, groups)), n_jobs=-1).fit(X, np.log1p(y))
    _cache["stack"] = st
    return st


def cv_table():
    rows = []
    for scheme, ms in models().items():
        for k, m in ms.items():
            rows.append({"model": k, "scheme": scheme, "cv_mae": -m.best_score_})
    t = pd.DataFrame(rows).pivot(index="model", columns="scheme", values="cv_mae")
    t["inflation_%"] = 100 * (t.spatial / t.random - 1)
    return t.sort_values("spatial").reset_index()


# PART 4. The test sites, which nothing above has seen ------------------------------
def test_table():
    X, y, Xt, yt, *_ = split()
    rows = []
    for name, est in [*((k, m.best_estimator_) for k, m in models()["spatial"].items()), ("stack", stack())]:
        p = np.expm1(est.predict(Xt))
        rows.append({"model": name, "test_r2": np.corrcoef(yt, p)[0, 1] ** 2,
                     "test_rmse": np.sqrt(np.mean((yt - p) ** 2)),
                     "test_mape_%": 100 * np.mean(np.abs(p - yt) / yt)})
    return pd.DataFrame(rows).sort_values("test_rmse").reset_index(drop=True)


def test_data():
    X, y, Xt, yt, *_ = split()
    return pd.DataFrame({"actual": yt, "predicted": np.expm1(stack().predict(Xt))})


def plot_test(df):
    r2 = np.corrcoef(df.actual, df.predicted)[0, 1] ** 2
    rmse = np.sqrt(np.mean((df.actual - df.predicted) ** 2))
    mape = 100 * np.mean(np.abs(df.predicted - df.actual) / df.actual)
    fig, ax = plt.subplots(figsize=(5.6, 5))
    lim = [0, max(df.actual.max(), df.predicted.max()) * 1.05]
    ax.plot(lim, lim, ":", color="#555555", lw=1)
    ax.scatter(df.actual, df.predicted, s=36, alpha=0.75, color="#1f4e79")
    ax.text(0.03, 0.97, f"R² = {r2:.2f}\nRMSE = {rmse:,.0f}\nMAPE = {mape:.0f}%", transform=ax.transAxes,
            va="top", fontweight="bold")
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("Counted pedestrians (weekday)"); ax.set_ylabel("Predicted")
    ax.set_title("Held-out count sites: actual vs predicted", loc="left", fontsize=10)
    return fig


# PART 5. Audience: a multi-criteria score per advertiser ----------------------------
def scored_sites():
    if "sites" in _cache:
        return _cache["sites"]
    cols = split()[5]
    cand = add_features(gpd.read_file(DATA / "candidates.gpkg"))
    site = cand[["geometry"]].copy()
    site["walking_count"] = np.expm1(stack().predict(cand[cols].fillna(0)))
    areas = gpd.read_file(DATA / "areas.gpkg").to_crs(site.crs)
    site = gpd.sjoin(site, areas[["income_weekly", "total_population", "pop1545", "pop2035", "pop4065",
                                  "geometry"]], how="left", predicate="within").drop(columns="index_right")
    site = site[~site.index.duplicated()]
    for k in ("fastfood", "education", "financial"):
        site[f"poi_{k}"] = buffer_mean(DATA / "surfaces" / f"{k}_poi.tif", site, 500)
    # Rescale every criterion to 0-1, then weight. The weights are a media
    # planner's judgement of each advertiser's audience, written down so they
    # can be argued with.
    s = site.drop(columns="geometry")
    s = (s - s.min()) / (s.max() - s.min())
    wealth = (s.income_weekly + s.total_population) / 2
    site["MCDA_financial"] = 0.50 * wealth + 0.20 * s.walking_count + 0.20 * s.poi_financial + 0.10 * s.pop4065
    site["MCDA_fastfood"] = 0.15 * wealth + 0.40 * s.walking_count + 0.35 * s.poi_fastfood + 0.10 * s.pop1545
    site["MCDA_education"] = 0.05 * wealth + 0.20 * s.walking_count + 0.35 * s.poi_education + 0.40 * s.pop2035
    _cache["sites"] = site
    return site


# PART 6. Inventory: what can actually be bought -------------------------------------
MCDA = ["MCDA_financial", "MCDA_fastfood", "MCDA_education"]


def score_assets(file):
    site = scored_sites()
    a = gpd.read_file(DATA / file).to_crs(site.crs).reset_index(drop=True)
    buf = a[["geometry"]].copy(); buf["geometry"] = a.buffer(50); buf["asset_id"] = a.index
    j = gpd.sjoin(buf, site[MCDA + ["geometry"]], how="left", predicate="intersects")
    sc = j.groupby("asset_id")[MCDA].mean()
    sc["n_locations"] = j.groupby("asset_id")["MCDA_financial"].count()
    return a.join(sc)


def route_scores():
    """Mean score per scored location the route passes. A sum would reward long
    routes for being long, so length is reported beside the score instead."""
    site = scored_sites()
    r = gpd.read_file(DATA / "routes.gpkg").to_crs(site.crs)
    r = r.dissolve("route").reset_index(); r["length_km"] = r.length / 1000
    buf = site[MCDA + ["geometry"]].copy(); buf["geometry"] = site.buffer(10)
    j = gpd.sjoin(buf, r[["route", "geometry"]], how="inner", predicate="intersects")
    sc = j.groupby("route")[MCDA].agg(["mean", "count"])
    sc.columns = [f"{a}_{b}" for a, b in sc.columns]
    return r.merge(sc.reset_index(), on="route", how="left")


def best_routes():
    r = route_scores()
    rows = []
    for k in MCDA:
        # a route needs enough scored locations for its mean to mean something
        top = r[r[f"{k}_count"] >= 5].sort_values(f"{k}_mean", ascending=False).head(3)
        for i, t in enumerate(top.itertuples(), 1):
            rows.append({"advertiser": k.replace("MCDA_", ""), "rank": i, "route": t.route,
                         "mean_score": getattr(t, f"{k}_mean"), "length_km": t.length_km,
                         "scored_locations": getattr(t, f"{k}_count")})
    return pd.DataFrame(rows)


def map_figure():
    site = scored_sites(); r = route_scores()
    fig, axs = plt.subplots(1, 3, figsize=(15, 5.4))
    for ax, k, cmap in zip(axs, MCDA, ["Blues", "Oranges", "Greens"]):
        r.plot(ax=ax, color="#cccccc", linewidth=0.6)
        r[r[f"{k}_count"] >= 5].nlargest(1, f"{k}_mean").plot(ax=ax, color="#b30000", linewidth=2.5)
        site.plot(ax=ax, column=k, cmap=cmap, markersize=2, legend=True,
                  legend_kwds={"shrink": 0.6, "label": "score (0-1)"})
        ax.set_title(f"{k.replace('MCDA_', '').title()}: scored locations, best route in red", loc="left", fontsize=9)
        graticule(ax, site.crs, n=4)
    fig.tight_layout()
    return fig



# Intermediate results: what the model sees, and what it learned ------------------
def surfaces_figure():
    """The seven predictor surfaces, with the count sites sized by their count."""
    import rasterio
    counts = features()
    fig, axs = plt.subplots(2, 4, figsize=(15, 8.4))
    for ax, name in zip(axs.flat, SURFACES):
        with rasterio.open(DATA / "surfaces" / f"{name}.tif") as src:
            r, b = src.read(1), src.bounds
        ax.imshow(np.log1p(np.clip(r, 0, None)), extent=[b.left, b.right, b.bottom, b.top], cmap="magma")
        ax.set_title(name.replace("_", " "), loc="left", fontsize=9); graticule(ax, "EPSG:7856", n=4)
    ax = axs.flat[-1]
    ok = counts[TARGET].notna()
    counts[ok].plot(ax=ax, column=TARGET, cmap="viridis", markersize=4 + 60 * counts[ok][TARGET] / counts[TARGET].max(),
                    legend=True, legend_kwds={"shrink": 0.6, "label": "weekday pedestrians"})
    ax.set_title("target: weekday walking count", loc="left", fontsize=9); graticule(ax, counts.crs, n=4)
    fig.suptitle("Predictor surfaces (log scale) and the counted sites", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    return fig


def correlation_table():
    """Spearman correlation of every surface with the count, at each buffer size."""
    counts = features(); lab = counts[counts[TARGET].notna()]
    rows = []
    for name in SURFACES:
        rows.append({"surface": name, **{f"{d} m": lab[f"{name}_{d}m"].corr(lab[TARGET], method="spearman")
                                         for d in (100, 500, 1000)}})
    return pd.DataFrame(rows).sort_values("500 m", ascending=False).reset_index(drop=True)


def plot_correlation(df):
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    y = np.arange(len(df))
    for off, d, c in [(-0.25, "100 m", "#9ecae1"), (0, "500 m", "#4292c6"), (0.25, "1000 m", "#08306b")]:
        ax.barh(y + off, df[d], height=0.25, color=c, label=d)
    ax.set_yticks(y, df.surface.str.replace("_", " ")); ax.invert_yaxis(); ax.axvline(0, color="#555", lw=0.8)
    ax.set_xlabel("Spearman correlation with weekday count")
    ax.legend(title="buffer", fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1))
    ax.set_title("Which surroundings go with footfall, and at what scale", loc="left", fontsize=10)
    return fig


def plot_cv(df):
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    y = np.arange(len(df))
    ax.hlines(y, df.random, df.spatial, color="#bbbbbb", lw=2)
    ax.scatter(df.random, y, color="#4292c6", label="random folds", zorder=3)
    ax.scatter(df.spatial, y, color="#cb181d", label="spatial folds", zorder=3)
    ax.set_yticks(y, df.model); ax.invert_yaxis()
    ax.set_xlabel("Cross-validated MAE of log(1 + count)"); ax.legend(fontsize=8)
    ax.set_title("The same models, validated on new places instead of neighbours", loc="left", fontsize=10)
    return fig


def importance_table():
    """Permutation importance on the held-out sites: how much worse the stack gets
    when one feature is shuffled."""
    from sklearn.inspection import permutation_importance
    X, y, Xt, yt, *_ = split()
    imp = permutation_importance(stack(), Xt, np.log1p(yt), n_repeats=30, random_state=SEED,
                                 scoring="neg_mean_absolute_error")
    df = pd.DataFrame({"feature": Xt.columns, "importance": imp.importances_mean, "sd": imp.importances_std})
    return df.sort_values("importance", ascending=False).head(12).reset_index(drop=True)


def plot_importance(df):
    fig, ax = plt.subplots(figsize=(6.4, 4))
    ax.barh(df.feature, df.importance, xerr=df.sd, color="#41ab5d", ecolor="#555")
    ax.invert_yaxis(); ax.set_xlabel("Increase in MAE of log(1 + count) when shuffled")
    ax.set_title("What the stacked model relies on (held-out sites)", loc="left", fontsize=10)
    return fig


def products():
    return [
        {"kind": "figure", "name": "ch65-surfaces", "figure": surfaces_figure,
         "caption": "The seven predictor surfaces built from open data, and the counted sites."},
        {"kind": "chart", "name": "ch65-correlation", "data": correlation_table, "plot": plot_correlation,
         "caption": "Spearman correlation of each surface with the weekday count, at three buffer sizes."},
        {"kind": "chart", "name": "ch65-cv-chart", "data": cv_table, "plot": plot_cv,
         "caption": "Cross-validated error of each learner under random and spatial folds."},
        {"kind": "table", "name": "ch65-cv", "data": cv_table, "floatfmt": ("", ".3f", ".3f", ".0f"),
         "caption": "Cross-validated MAE of log(1 + count) for each learner under random and spatial folds, "
                    "and how much worse the spatial folds are (per cent)."},
        {"kind": "table", "name": "ch65-test", "data": test_table, "floatfmt": ("", ".2f", ",.0f", ".0f"),
         "caption": "The held-out count sites, which no model or pre-processing step saw."},
        {"kind": "chart", "name": "ch65-test-scatter", "data": test_data, "plot": plot_test,
         "caption": "Stacked model on the held-out count sites."},
        {"kind": "chart", "name": "ch65-importance", "data": importance_table, "plot": plot_importance,
         "caption": "Permutation importance of the twelve most important features for the stacked model."},
        {"kind": "table", "name": "ch65-routes", "data": best_routes, "floatfmt": ("", "", "", ".3f", ".1f", ".0f"),
         "caption": "The three best bus routes for each advertiser, by mean score per scored location."},
        {"kind": "figure", "name": "ch65-map", "figure": map_figure,
         "caption": "Advertiser scores at every candidate location and the best bus route for each."},
    ]


if __name__ == "__main__":
    print(cv_table()); print(test_table()); print(best_routes())
