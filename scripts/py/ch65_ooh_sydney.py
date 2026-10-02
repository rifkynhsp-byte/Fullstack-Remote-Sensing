#| title: Out-of-home advertising placement in Sydney (Python)
#| description: Predict weekday pedestrian counts from open urban data with a stacked ensemble, combine them with income, population and points of interest in a multi-criteria score for three advertiser types, and rank bus shelters, city banners and bus routes.

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

Data (all open): City of Sydney walking count sites, floor space and
employment survey, bus shelters and banner poles (data.cityofsydney.nsw.gov.au);
Transport for NSW bus routes; ABS income and NSW population projections;
POI, road and building density surfaces derived from OpenStreetMap.
Set OOH_DATA to the folder that holds them (layout as in the chapter).
"""

import os
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from exactextract import exact_extract

DATA = Path(os.environ.get("OOH_DATA", "data/ooh_sydney"))
SEED = 12345
SURFACES = {"poi": "Heatmap_POI.tif", "road_density": "Road_density.tif",
            "nighttime": "NightimeArea.tif", "bus_station": "Heatmap_busstation.tif",
            "building_surface": "Heatmap_building_surface.tif",
            "building_volume": "Heatmap_building_volume.tif",
            "economic": "Heatmap_economic_potential.tif"}


def buffer_mean(raster, gdf, metres):
    """Area-weighted mean of a raster inside a buffer around every feature."""
    polys = gdf[["geometry"]].copy(); polys["geometry"] = gdf.buffer(metres)
    return exact_extract(str(raster), polys, "mean", output="pandas")["mean"].values


# PART 1. Training points and predictor surfaces --------------------------------
_cache = {}


def features():
    if "counts" in _cache:
        return _cache["counts"]
    counts = gpd.read_file(DATA / "Walking_count" / "WalkingCountTraining.shp")
    assert counts.crs.axis_info[0].unit_name == "metre"      # buffers are in metres
    # Each surface at a street, a neighbourhood and a district scale.
    for name, f in SURFACES.items():
        for d in (100, 500, 1000):
            counts[f"{name}_{d}m"] = buffer_mean(DATA / "Walking_count" / f, counts, d)
    # Attributes of the employment-survey zone each point falls in. A left join
    # keeps every point; an intersection drops points outside the zones.
    emp = gpd.read_file(DATA / "Walking_count" / "Employment_Survey.shp").to_crs(counts.crs)
    counts = gpd.sjoin(counts, emp, how="left", predicate="within").drop(columns="index_right")
    counts = counts[~counts.index.duplicated()]
    _cache["counts"] = counts
    return counts


def predictor_names(counts):
    num = counts.drop(columns=["geometry", "Mon_Count"], errors="ignore").select_dtypes("number")
    return [c for c in num.columns if c.lower() not in ("site_id", "fid", "objectid")]


# PART 2. An honest split ---------------------------------------------------------
def split():
    if "split" in _cache:
        return _cache["split"]
    from sklearn.cluster import KMeans
    from sklearn.model_selection import train_test_split
    counts = features(); cols = predictor_names(counts)
    lab = counts[counts.Mon_Count.notna()].copy()
    X, y = lab[cols].fillna(0), lab.Mon_Count.values
    # Hold out 20 % of the counted sites before anything is learned.
    tr, te = train_test_split(np.arange(len(lab)), test_size=0.2, random_state=SEED)
    # Spatial folds: five location clusters, so a validation site's
    # neighbourhood is never in its own training fold.
    xy = np.column_stack([lab.geometry.x, lab.geometry.y])[tr]
    groups = KMeans(5, n_init=20, random_state=SEED).fit_predict(xy)
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
        s.fit(X, y, groups=groups)
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
                           cv=list(GroupKFold(5).split(X, y, groups)), n_jobs=-1).fit(X, y)
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
        p = est.predict(Xt)
        rows.append({"model": name, "test_r2": np.corrcoef(yt, p)[0, 1] ** 2,
                     "test_rmse": np.sqrt(np.mean((yt - p) ** 2)),
                     "test_mape_%": 100 * np.mean(np.abs(p - yt) / yt)})
    return pd.DataFrame(rows).sort_values("test_rmse").reset_index(drop=True)


def test_data():
    X, y, Xt, yt, *_ = split()
    return pd.DataFrame({"actual": yt, "predicted": stack().predict(Xt)})


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
def band(pop, ages):
    return sum(pop[f"prj_m_{a}"] + pop[f"prj_f_{a}"] for a in ages)


def scored_sites():
    if "sites" in _cache:
        return _cache["sites"]
    counts = features(); cols = split()[5]
    site = counts[["geometry"]].copy()
    site["walking_count"] = stack().predict(counts[cols].fillna(0))
    inc = gpd.read_file(DATA / "Buying Potential" / "Income_Data.shp").to_crs(site.crs)
    inc = inc.assign(income_weekly=inc.equiv_2202)[["income_weekly", "geometry"]]
    pop = gpd.read_file(DATA / "Buying Potential" / "Population_Data.shp").to_crs(site.crs)
    pop = pop.assign(total_population=pop.prj_person,
                     pop1545=band(pop, ["1519", "2024", "2529", "3034", "3539", "4044"]),
                     pop2035=band(pop, ["2024", "2529", "3034"]),
                     pop4065=band(pop, ["4044", "4549", "5054", "5559", "6064"]))
    pop = pop[["total_population", "pop1545", "pop2035", "pop4065", "geometry"]]
    for layer in (inc, pop):
        site = gpd.sjoin(site, layer, how="left", predicate="within").drop(columns="index_right")
        site = site[~site.index.duplicated()]
    for k in ("fastfood", "education", "financial"):
        site[f"poi_{k}"] = buffer_mean(DATA / "POI" / f"{k}_heatmap.tif", site, 500)
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
    a = gpd.read_file(DATA / "OOH places" / file).to_crs(site.crs).reset_index(drop=True)
    buf = a[["geometry"]].copy(); buf["geometry"] = a.buffer(50); buf["asset_id"] = a.index
    j = gpd.sjoin(buf, site[MCDA + ["geometry"]], how="left", predicate="intersects")
    sc = j.groupby("asset_id")[MCDA].mean()
    sc["n_locations"] = j.groupby("asset_id")["MCDA_financial"].count()
    return a.join(sc)


def route_scores():
    """Mean score per scored location the route passes. A sum would reward long
    routes for being long, so length is reported beside the score instead."""
    site = scored_sites()
    r = gpd.read_file(DATA / "OOH places" / "Bus Routes clipped.shp").to_crs(site.crs)
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
        top = r.sort_values(f"{k}_mean", ascending=False).head(3)
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
        r.nlargest(1, f"{k}_mean").plot(ax=ax, color="#b30000", linewidth=2.5)
        site.plot(ax=ax, column=k, cmap=cmap, markersize=14, legend=True,
                  legend_kwds={"shrink": 0.6, "label": "score (0-1)"})
        ax.set_title(f"{k.replace('MCDA_', '').title()}: scored locations, best route in red", loc="left", fontsize=9)
        ax.set_axis_off()
    fig.tight_layout()
    return fig


def products():
    return [
        {"kind": "table", "name": "ch65-cv", "data": cv_table, "floatfmt": ("", ".0f", ".0f", ".0f"),
         "caption": "Cross-validated MAE of each learner under random and spatial folds. The gap is how much "
                    "a random split flatters a model when count sites share their neighbourhood."},
        {"kind": "table", "name": "ch65-test", "data": test_table, "floatfmt": ("", ".2f", ",.0f", ".0f"),
         "caption": "The held-out count sites, which no model or pre-processing step saw."},
        {"kind": "chart", "name": "ch65-test-scatter", "data": test_data, "plot": plot_test,
         "caption": "Stacked model on the held-out count sites."},
        {"kind": "table", "name": "ch65-routes", "data": best_routes, "floatfmt": ("", "", "", ".3f", ".1f", ".0f"),
         "caption": "The three best bus routes for each advertiser, by mean score per scored location."},
        {"kind": "figure", "name": "ch65-map", "figure": map_figure,
         "caption": "Advertiser scores at every candidate location and the best bus route for each."},
    ]


if __name__ == "__main__":
    print(cv_table()); print(test_table()); print(best_routes())
