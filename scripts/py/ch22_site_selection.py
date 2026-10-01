#| title: Vector GeoAI site selection (Python)
#| description: Coffee-shop suitability in Kota Malang on an H3 hexagon grid. OpenStreetMap proximity and density features, WorldPop population from Earth Engine, a manufactured presence/pseudo-absence label, the leakage trap, a Random Forest read with SHAP, and a transparent weighted score.

"""
CHAPTER 22 | The same machine, a commercial question

Score every part of a city for suitability as a coffee shop location, with the
same logic as the remote sensing chapters: build features, label examples,
train a model, interpret it, produce a continuous score map. Swap reflectance
for "distance to the nearest school" and pixel for hexagon, and the workflow
answers a commercial question instead.

Environment (Colab or any Python 3.10+):
    pip install osmnx geopandas h3 shap scikit-learn earthengine-api matplotlib

Data, all open:
    OpenStreetMap (via osmnx)  city boundary, schools, tourism, cafes, roads
    WorldPop 2020 (via Earth Engine)  people per hexagon
"""

import ee
import geopandas as gpd
import h3
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
import pandas as pd
from shapely.geometry import Polygon

PLACE = "Kota Malang, Jawa Timur, Indonesia"
# H3 resolution 9: hexagons about 175 m across, a two-minute walk, the right
# unit for a coffee shop catchment. Resolution 8 (~460 m) suits a supermarket.
H3_RESOLUTION = 9
CRS_METRIC = "EPSG:32749"       # UTM 49S: distances in metres, never in degrees
CRS_GEO = "EPSG:4326"
DENSITY_RADIUS_M = 500          # about a five-minute walk


# PART 1. Data -----------------------------------------------------------------
def fetch_points(tags):
    """OSM features reduced to points (a school may be mapped as a building)."""
    gdf = ox.features_from_place(PLACE, tags=tags)[["geometry"]].reset_index(drop=True)
    gdf["geometry"] = gdf.geometry.apply(
        lambda g: g.centroid if g.geom_type in ("Polygon", "MultiPolygon") else g)
    return gpd.GeoDataFrame(gdf, geometry="geometry", crs=CRS_GEO)


# PART 2. A uniform unit: hexagons -------------------------------------------------
def hex_grid(outline):
    cells = h3.geo_to_cells(outline.__geo_interface__, H3_RESOLUTION)
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in cells]
    return gpd.GeoDataFrame({"h3": list(cells)}, geometry=polys, crs=CRS_GEO)


def count_within(buffers, target):
    joined = gpd.sjoin(buffers, target, how="inner", predicate="contains")
    return joined.groupby(joined.index).size().reindex(buffers.index, fill_value=0).values


def worldpop_per_hex(grid):
    """People per hexagon from WorldPop 2020 (100 m), summed in Earth Engine."""
    pop = (ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "IDN"))
           .filter(ee.Filter.eq("year", 2020)).mosaic())
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(g.__geo_interface__), {"i": int(i)})
                               for i, g in zip(grid.index, grid.geometry)])
    out = pop.reduceRegions(collection=fc, reducer=ee.Reducer.sum(), scale=100).getInfo()
    d = {f["properties"]["i"]: f["properties"].get("sum", 0) or 0 for f in out["features"]}
    return grid.index.map(d).astype(float)


_cache = {}


def build():
    if _cache:
        return _cache
    outline = ox.geocode_to_gdf(PLACE).to_crs(CRS_GEO).geometry.iloc[0]
    layers = {
        "education": fetch_points({"amenity": ["school", "university", "college"]}),
        "tourism": fetch_points({"tourism": ["attraction", "theme_park", "zoo", "museum",
                                             "gallery", "viewpoint"]}),
        "cafe": fetch_points({"amenity": ["cafe"]}),
    }
    roads = ox.features_from_place(PLACE, tags={"highway": ["primary", "secondary", "tertiary"]})
    roads = gpd.GeoDataFrame(roads[["geometry"]].reset_index(drop=True), geometry="geometry",
                             crs=CRS_GEO)
    grid = hex_grid(outline)
    gm = grid.to_crs(CRS_METRIC)
    cent = gpd.GeoDataFrame(geometry=gm.geometry.centroid, crs=CRS_METRIC)

    # PART 3. Features: proximity (how far to the nearest) and density (how many nearby)
    for name, layer in {**layers, "road": roads}.items():
        near = gpd.sjoin_nearest(cent, layer.to_crs(CRS_METRIC), how="left", distance_col="d")
        grid[f"dist_{name}"] = near.groupby(near.index)["d"].min().values
    buffers = gpd.GeoDataFrame(geometry=cent.buffer(DENSITY_RADIUS_M), crs=CRS_METRIC)
    for name in ("cafe", "education", "tourism"):
        grid[f"n_{name}_500m"] = count_within(buffers, layers[name].to_crs(CRS_METRIC))
    grid["population"] = worldpop_per_hex(grid)

    # PART 4. Manufacturing a label: presence = a hexagon that already has a cafe;
    # pseudo-absence = an equal random sample of empty hexagons ("typical
    # unoccupied", not "known bad").
    occupied = gpd.sjoin(gm, layers["cafe"].to_crs(CRS_METRIC), how="inner",
                         predicate="contains").index.unique()
    grid["label"] = np.nan
    grid.loc[occupied, "label"] = 1
    empty = grid[grid.label.isna()].sample(n=len(occupied), random_state=42).index
    grid.loc[empty, "label"] = 0
    _cache.update(grid=grid, counts={k: len(v) for k, v in layers.items()} | {"road": len(roads)},
                  n_cells=len(grid), n_presence=len(occupied))
    return _cache


FEATURES_ALL = ["dist_education", "dist_tourism", "dist_cafe", "dist_road",
                "n_cafe_500m", "n_education_500m", "n_tourism_500m", "population"]
FEATURES = [f for f in FEATURES_ALL if f != "dist_cafe"]


def fit(features):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import train_test_split
    t = build()["grid"].dropna(subset=["label"])
    X_tr, X_te, y_tr, y_te = train_test_split(t[features], t.label, test_size=0.2,
                                              random_state=42, stratify=t.label)
    m = RandomForestClassifier(n_estimators=300, random_state=42, oob_score=True).fit(X_tr, y_tr)
    p = m.predict(X_te)
    return m, X_tr, X_te, {"oob": m.oob_score_, "test_accuracy": accuracy_score(y_te, p),
                           "test_f1": f1_score(y_te, p)}


# PART 5. The leakage trap ----------------------------------------------------------
def leakage_table():
    c = build()
    rows = []
    for name, feats in [("all features (includes distance to nearest cafe)", FEATURES_ALL),
                        ("without distance to nearest cafe", FEATURES)]:
        _, _, _, s = fit(feats)
        rows.append({"model": name, **s})
    df = pd.DataFrame(rows)
    df["hexagons"] = c["n_cells"]
    df["presence_hexagons"] = c["n_presence"]
    return df


# PART 6. SHAP: which features, and in which direction ---------------------------
def shap_table():
    import shap
    m, X_tr, X_te, _ = fit(FEATURES)
    ex = shap.TreeExplainer(m)
    sv = ex.shap_values(X_te)
    sv = sv[:, :, 1] if np.ndim(sv) == 3 else sv[1]
    rows = []
    for j, f in enumerate(FEATURES):
        r = np.corrcoef(X_te[f].values, sv[:, j])[0, 1] if X_te[f].std() > 0 else np.nan
        rows.append({"feature": f, "mean_abs_shap": np.abs(sv[:, j]).mean(),
                     "direction": "higher value -> more suitable" if r > 0.1 else
                                  "higher value -> less suitable" if r < -0.1 else "mixed",
                     "corr_value_shap": r})
    df = pd.DataFrame(rows).sort_values("mean_abs_shap", ascending=False)
    df["weight"] = df.mean_abs_shap / df.mean_abs_shap.sum()
    return df.reset_index(drop=True)


def plot_shap(df):
    fig, ax = plt.subplots(figsize=(6.8, 3.4))
    cols = ["#1a9850" if r > 0.1 else "#d73027" if r < -0.1 else "#9aa5b1"
            for r in df.corr_value_shap]
    ax.barh(df.feature[::-1], df.weight[::-1], color=cols[::-1])
    ax.set_xlabel("Weight (share of mean |SHAP|)")
    ax.set_title("What the model used (green: more is better; red: less is better)",
                 loc="left", fontsize=9)
    return fig


# PART 7. A transparent continuous score ----------------------------------------
def score():
    grid = build()["grid"].copy()
    w = shap_table()
    norm = (grid[FEATURES] - grid[FEATURES].min()) / (grid[FEATURES].max() - grid[FEATURES].min())
    # Use the direction SHAP found, not the one we assumed: a feature where more
    # meant less suitable is inverted before weighting.
    for r in w.itertuples():
        if r.corr_value_shap < -0.1:
            norm[r.feature] = 1 - norm[r.feature]
    grid["score"] = sum(norm[r.feature] * r.weight for r in w.itertuples())
    return grid


def score_figure():
    g = score()
    cafes = build()["grid"]
    fig, ax = plt.subplots(figsize=(8, 8.5))
    g.plot(column="score", cmap="YlOrRd", linewidth=0.1, edgecolor="#555555", legend=True,
           legend_kwds={"label": "Suitability score (0 to 1)", "shrink": 0.6}, ax=ax)
    g[g.label == 1].boundary.plot(ax=ax, color="#1f2933", linewidth=0.6)
    ax.set_title("Coffee-shop suitability, Kota Malang (outlined: hexagons with a cafe today)",
                 loc="left", fontsize=10)
    ax.set_axis_off()
    return fig


def top_table():
    g = score()
    t = g[g.label != 1].sort_values("score", ascending=False).head(10)
    c = t.geometry.to_crs(CRS_METRIC).centroid.to_crs(CRS_GEO)
    return pd.DataFrame({"rank": range(1, 11), "score": t.score.values,
                         "lat": c.y.round(5).values, "lon": c.x.round(5).values,
                         "people_in_hexagon": t.population.round().values,
                         "cafes_within_500m": t.n_cafe_500m.values})


def products():
    return [
        {"kind": "table", "name": "ch22-leakage", "data": leakage_table,
         "floatfmt": ("", ".3f", ".3f", ".3f", ",.0f", ",.0f"),
         "caption": "The leakage trap: the same Random Forest with and without the distance "
                    "to the nearest cafe."},
        {"kind": "chart", "name": "ch22-shap", "data": shap_table, "plot": plot_shap,
         "caption": "SHAP weights of the honest model, coloured by the direction of each "
                    "feature's effect."},
        {"kind": "table", "name": "ch22-shap-table", "data": shap_table,
         "floatfmt": ("", ".4f", "", ".2f", ".1%"),
         "caption": "Mean |SHAP| per feature, its direction, and the weight used in the score."},
        {"kind": "figure", "name": "ch22-score", "figure": score_figure,
         "caption": "Suitability score per H3 hexagon (resolution 9) from the SHAP-weighted "
                    "features. Outlined hexagons already have a cafe in OpenStreetMap."},
        {"kind": "table", "name": "ch22-top", "data": top_table,
         "floatfmt": ("", ".3f", ".5f", ".5f", ",.0f", ",.0f"),
         "caption": "The ten highest-scoring hexagons without a cafe today: a shortlist to "
                    "visit, not a decision."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(leakage_table())
