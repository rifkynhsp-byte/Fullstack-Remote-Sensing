#| title: Vector GeoAI site selection
#| description: Hexagonal grid, proximity and density features, Random Forest, SHAP weighting.

"""
CHAPTER 22 | The same machine, a commercial question
===============================================================================
Goal
    Score every part of a city for suitability as a coffee shop location, using
    the identical logic as the mangrove chapters: build features, label
    examples, train a model, interpret it, produce a continuous score map.

Why this chapter exists in a remote sensing book
    Everything before this used raster features derived from satellites.
    Nothing about the machine learning cared. Swap reflectance for distance to
    the nearest school and pixel for hexagon and the same workflow answers a
    completely different commercial question. Recognising that these are one
    problem is what makes the skill portable between sectors.

Environment
    Google Colab, or any Python 3.10+ environment.

        pip install numpy pandas geopandas osmnx scikit-learn shap folium \
                    shapely h3pandas matplotlib

Study area
    Kota Malang, East Java. Substitute any city with reasonable
    OpenStreetMap coverage.
"""

import warnings

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

# =============================================================================
# CONFIGURATION
# =============================================================================
PLACE = "Malang, Indonesia"

# H3 resolution 9 gives hexagons roughly 175 m across, about a two minute
# walk. That is the right unit for a coffee shop catchment. Resolution 8 is
# roughly 460 m and better for a supermarket; resolution 10 is roughly 65 m
# and produces so many cells that most of them hold no information at all.
H3_RESOLUTION = 9

# Projected CRS for the study area. Distance work must never be done in
# degrees. EPSG:32749 is UTM zone 49S, correct for East Java. Using EPSG:4326
# here would give distances in degrees, which vary with latitude and are
# meaningless as metres.
CRS_METRIC = "EPSG:32749"
CRS_GEOGRAPHIC = "EPSG:4326"

# Catchment radius for density features. 500 m is roughly a five minute walk
# in a dense urban grid.
DENSITY_RADIUS_M = 500


# =============================================================================
# PART 1. Acquire the data
# =============================================================================
def fetch_points(place: str, tags: dict) -> gpd.GeoDataFrame:
    """Download OSM features and reduce every geometry to a point.

    OSM returns a mix of nodes, ways and relations, so a school may arrive as
    a point or as a building polygon depending on who mapped it. Taking the
    centroid of anything that is not already a point makes the layer uniform,
    which every distance calculation downstream depends on.
    """
    gdf = ox.features_from_place(place, tags=tags)
    gdf = gdf[["geometry"]].reset_index(drop=True)
    gdf["geometry"] = gdf["geometry"].apply(
        lambda g: g.centroid if g.geom_type in ("Polygon", "MultiPolygon") else g
    )
    return gpd.GeoDataFrame(gdf, geometry="geometry", crs=CRS_GEOGRAPHIC)


education = fetch_points(PLACE, {"amenity": ["school", "university", "college"]})
tourism = fetch_points(
    PLACE,
    {"tourism": ["attraction", "theme_park", "zoo", "museum", "gallery", "viewpoint"]},
)
cafes = fetch_points(PLACE, {"amenity": ["cafe", "coffee_shop"]})

roads = ox.features_from_place(
    PLACE, tags={"highway": ["primary", "secondary", "tertiary"]}
)
roads = gpd.GeoDataFrame(
    roads[["geometry"]].reset_index(drop=True), geometry="geometry",
    crs=CRS_GEOGRAPHIC,
)

print(f"education: {len(education):>5}")
print(f"tourism:   {len(tourism):>5}")
print(f"cafes:     {len(cafes):>5}")
print(f"roads:     {len(roads):>5}")

# A note on data honesty. OSM coverage is uneven and volunteer contributed.
# In a well mapped city the cafe layer is close to complete; in a poorly
# mapped one, absence of a cafe in the data does not mean absence on the
# ground. That distinction matters enormously below, where absence becomes a
# training label. Check a handful of hexagons against street level imagery
# before trusting the result.


# =============================================================================
# PART 2. A uniform unit of analysis
# =============================================================================
# Administrative boundaries are the wrong unit for this question: they vary
# wildly in size, so a count per district is not comparable between districts.
# A regular grid fixes that.
#
# Hexagons beat squares for two reasons. Every neighbour is the same distance
# from the centre, whereas a square's diagonal neighbours are 1.41 times
# further, which distorts any distance or adjacency calculation. And hexagons
# have no preferred axis, so they do not impose a north south grid artefact on
# a city whose structure runs diagonally.
import h3pandas  # noqa: E402  (registers the .h3 accessor on GeoDataFrame)

boundary = gpd.read_file("Batas_Kecamatan_Malang.geojson").to_crs(CRS_GEOGRAPHIC)
population = pd.read_csv("Kependudukan_2024.csv")

boundary = boundary.merge(
    population[["Kecamatan", "Kepadatan Penduduk (jiwa/km2)"]],
    on="Kecamatan",
    how="left",
)

city_outline = gpd.GeoDataFrame(
    geometry=[boundary.union_all()], crs=CRS_GEOGRAPHIC
)

grid = city_outline.h3.polyfill_resample(H3_RESOLUTION).reset_index()
print(f"grid cells: {len(grid)}")


# =============================================================================
# PART 3. Feature engineering
# =============================================================================
# Raw geometry cannot enter a model. Every layer has to become a number
# attached to a hexagon. Two families of feature do that work, and they
# answer genuinely different questions.
#
#   Proximity: how far to the NEAREST instance. Answers accessibility.
#   Density:   how MANY within a radius. Answers intensity.
#
# The distinction matters. One school 300 m away and twelve schools 300 m away
# give identical proximity values and very different footfall.

grid_m = grid.to_crs(CRS_METRIC)
centroids = grid_m.geometry.centroid

layers_m = {
    "pendidikan": education.to_crs(CRS_METRIC),
    "wisata": tourism.to_crs(CRS_METRIC),
    "kompetitor": cafes.to_crs(CRS_METRIC),
    "jalan": roads.to_crs(CRS_METRIC),
}

# --- Proximity ---------------------------------------------------------------
# The naive implementation applies .distance().min() per centroid, which is an
# O(n*m) scan and takes minutes on a city sized grid. sjoin_nearest uses a
# spatial index and returns in seconds. The result is identical.
for name, layer in layers_m.items():
    nearest = gpd.sjoin_nearest(
        gpd.GeoDataFrame(geometry=centroids, crs=CRS_METRIC),
        layer,
        how="left",
        distance_col=f"jarak_ke_{name}",
    )
    # sjoin_nearest emits one row per tie, so collapse back to one per cell.
    grid[f"jarak_ke_{name}"] = (
        nearest.groupby(nearest.index)[f"jarak_ke_{name}"].min().values
    )

# --- Density -----------------------------------------------------------------
buffers = gpd.GeoDataFrame(
    geometry=centroids.buffer(DENSITY_RADIUS_M), crs=CRS_METRIC
)


def count_within(buffer_gdf: gpd.GeoDataFrame, target: gpd.GeoDataFrame) -> np.ndarray:
    """Count target points falling inside each buffer, zero where none."""
    joined = gpd.sjoin(buffer_gdf, target, how="left", predicate="contains")
    counts = joined.groupby(joined.index).size()
    # A buffer containing nothing still produces one row from the left join,
    # so a naive size() returns 1 rather than 0. Subtract where the join
    # produced no match.
    empty = joined[joined.index_right.isna()].index
    counts.loc[counts.index.isin(empty)] = 0
    return counts.reindex(buffer_gdf.index, fill_value=0).values


grid["jumlah_kompetitor_500m"] = count_within(buffers, cafes.to_crs(CRS_METRIC))
grid["jumlah_pendidikan_500m"] = count_within(buffers, education.to_crs(CRS_METRIC))
grid["jumlah_wisata_500m"] = count_within(buffers, tourism.to_crs(CRS_METRIC))

# --- Demography --------------------------------------------------------------
# Population density arrives at district resolution and has to be pushed down
# to hexagons. sjoin_nearest guarantees every hexagon gets a value, including
# the ones straddling a boundary.
#
# Be clear about what this does and does not give you. Every hexagon inside a
# district receives that district's average density, so within district
# variation is invisible. It is a coarse proxy for market size, not a
# measurement of who lives in that hexagon. Where it matters, replace it with
# WorldPop or building footprint counts.
grid_m = grid.to_crs(CRS_METRIC)
grid_m = gpd.sjoin_nearest(
    grid_m, boundary.to_crs(CRS_METRIC), how="left", max_distance=100
)
grid["kepadatan_penduduk"] = grid_m["Kepadatan Penduduk (jiwa/km2)"].values
grid["kecamatan"] = grid_m["Kecamatan"].values


# =============================================================================
# PART 4. Manufacturing a label
# =============================================================================
# This is the conceptually hardest step and the one most often glossed over.
#
# There is no dataset of "good coffee shop locations". So we assume that a
# location where a coffee shop already operates is a location that works, and
# label it 1. That assumption is doing a lot of work and it deserves to be
# stated out loud: it encodes the existing market's judgement, including its
# blind spots. A genuinely underserved neighbourhood looks like a bad location
# to this model, because nobody has opened there yet.
#
# The absence side is worse. An empty hexagon is not a proven failure; it may
# simply be untried. This is the presence and pseudo absence problem, borrowed
# from species distribution modelling, and the standard treatment is to sample
# a balanced number of empty cells at random and label them 0, understanding
# that they represent "typical unoccupied location" rather than "known bad".
grid_m = grid.to_crs(CRS_METRIC)
cafes_m = cafes.to_crs(CRS_METRIC)

occupied = gpd.sjoin(grid_m, cafes_m, how="inner", predicate="contains").index.unique()

grid["potensi"] = np.nan
grid.loc[occupied, "potensi"] = 1

candidates = grid[grid["potensi"].isna()]
pseudo_absence = candidates.sample(n=len(occupied), random_state=42).index
grid.loc[pseudo_absence, "potensi"] = 0

training_data = grid.dropna(subset=["potensi"])
print(f"presence: {len(occupied)}   pseudo absence: {len(pseudo_absence)}")


# =============================================================================
# PART 5. The leakage trap
# =============================================================================
# Train once with every feature and read the result carefully.
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.metrics import classification_report  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

features_all = [
    "jarak_ke_pendidikan",
    "jarak_ke_wisata",
    "jarak_ke_kompetitor",
    "jarak_ke_jalan",
    "jumlah_kompetitor_500m",
    "jumlah_pendidikan_500m",
    "jumlah_wisata_500m",
    "kepadatan_penduduk",
]

X_all = training_data[features_all]
y = training_data["potensi"]

X_tr, X_te, y_tr, y_te = train_test_split(X_all, y, test_size=0.2, random_state=42)
naive = RandomForestClassifier(n_estimators=100, random_state=42, oob_score=True)
naive.fit(X_tr, y_tr)

print("\n--- With all features ---")
print(f"OOB score: {naive.oob_score_:.4f}")
print(classification_report(y_te, naive.predict(X_te)))

# The output is 1.00 across precision, recall and f1. That is not success.
# Outside a textbook, a perfect classifier means a feature is leaking the
# answer, and here the culprit is obvious once seen: a presence hexagon
# CONTAINS a cafe, so its distance to the nearest competitor is close to zero
# BY CONSTRUCTION. The model is not predicting suitability. It has learned to
# recognise a hexagon with a cafe in it, which is the label restated as a
# feature.
#
# This is the same class of error as including a post treatment variable in a
# causal model, and it is worth internalising as a general reflex: when a
# model reports perfect accuracy, look for the leak before celebrating.

features = [f for f in features_all if f != "jarak_ke_kompetitor"]

X = training_data[features]
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestClassifier(n_estimators=100, random_state=42, oob_score=True)
model.fit(X_tr, y_tr)

print("\n--- After removing the leaking feature ---")
print(f"OOB score: {model.oob_score_:.4f}")
print(classification_report(y_te, model.predict(X_te)))

# Around 0.84. Lower, and far more trustworthy. Note that the count of
# competitors within 500 m is retained: that is a genuine measure of
# agglomeration, not a restatement of the label, because it describes the
# neighbourhood rather than the cell itself.


# =============================================================================
# PART 6. Interpretation with SHAP
# =============================================================================
# Feature importance from a Random Forest tells you which variables the model
# used. It does not tell you in which DIRECTION, and for a business decision
# the direction is the whole point.
#
# SHAP values decompose each individual prediction into per feature
# contributions, so you learn not just that competitor density mattered but
# that MORE competitors pushed the prediction UP.
import shap  # noqa: E402

explainer = shap.Explainer(model, X_tr)
explanation = explainer(X_te)

# Slice to the positive class. Tree explainers return one set of values per
# class, and [:, :, 1] selects the "suitable" one.
shap.summary_plot(explanation[:, :, 1], X_te)

# Reading the plot for this city:
#
#   jumlah_kompetitor_500m dominates, and high values push the prediction UP.
#   Clustering attracts rather than repels. Coffee shops benefit from
#   agglomeration, because a street known for cafes draws people looking for
#   a cafe. This contradicts the intuition that competitors are bad and it is
#   the single most commercially useful thing the model found.
#
#   kepadatan_penduduk pushes up, as expected. Market size is market size.
#
#   jarak_ke_jalan pushes down when large. Accessibility matters and being
#   far from an arterial road is a real penalty.
#
#   jumlah_wisata_500m pushes DOWN, which is counterintuitive and worth
#   investigating rather than accepting. Plausible explanations include
#   tourist areas being dominated by other business types, or footfall being
#   seasonal rather than daily. This is a hypothesis the model generated, not
#   a finding. Test it before acting on it.

mean_abs = np.abs(explanation.values[:, :, 1]).mean(axis=0)
weights = pd.DataFrame({"feature": features, "shap": mean_abs})
weights["weight"] = weights["shap"] / weights["shap"].sum()
weights = weights.sort_values("weight", ascending=False)
print("\n", weights.to_string(index=False))


# =============================================================================
# PART 7. From classification to a continuous score
# =============================================================================
# The classifier answers a binary question about the 223 labelled cells. The
# business needs a continuous score for all 1,306. Rather than predicting
# probability directly, we use the SHAP weights to build a transparent
# weighted sum, which has a decisive practical advantage: a client can see
# exactly why a cell scored what it scored, and can override a weight they
# disagree with on business grounds.
from sklearn.preprocessing import MinMaxScaler  # noqa: E402

scored = grid[features].copy()
normalised = pd.DataFrame(
    MinMaxScaler().fit_transform(scored), columns=features, index=grid.index
)

# For distance features, LOWER is better, so the normalised scale is inverted.
# Forgetting this inverts the whole map and produces a result that looks
# plausible and recommends exactly the wrong places.
for column in ["jarak_ke_pendidikan", "jarak_ke_wisata", "jarak_ke_jalan"]:
    normalised[column] = 1 - normalised[column]

grid["skor_potensi"] = sum(
    normalised[row.feature] * row.weight for row in weights.itertuples()
)

fig, ax = plt.subplots(figsize=(11, 11))
grid.plot(
    column="skor_potensi",
    cmap="YlOrRd",
    edgecolor="black",
    linewidth=0.2,
    legend=True,
    legend_kwds={"label": "Suitability score (0 to 1)"},
    ax=ax,
)
ax.set_title(f"Coffee shop suitability, {PLACE}")
ax.set_axis_off()
plt.tight_layout()
plt.show()

grid.to_file("suitability_score.geojson", driver="GeoJSON")


# =============================================================================
# WHAT THIS SCORE IS AND IS NOT
# =============================================================================
# It is a structured, reproducible, interpretable ranking of locations by
# measurable characteristics, and it is a large improvement on intuition.
#
# It is not a prediction of profit. It contains no rent, no lease
# availability, no parking, no local regulation, no competitor quality and no
# knowledge of who actually walks down which street at 8am. Its highest
# scoring cell may be a cemetery.
#
# Use it to shortlist ten candidate areas from a thousand. Then send someone
# to stand on the corner for an hour. The model narrows the search; it does
# not make the decision, and any consultant who says otherwise is selling
# a spreadsheet with extra steps.
#
# -----------------------------------------------------------------------------
# Exercise
# -----------------------------------------------------------------------------
# 1. Change H3_RESOLUTION to 8 and rerun. Explain what happens to the SHAP
#    weights and why the agglomeration effect weakens.
# 2. Replace the pseudo absence sample with cells more than 1 km from any
#    existing cafe. Argue for or against that being a better definition.
# 3. Add a feature of your own, for example distance to the nearest office
#    building, and check with SHAP whether it earned its place.
# 4. Take the top ten scoring cells and look at each on street level imagery.
#    Count how many are plausible. That count is your real accuracy.
