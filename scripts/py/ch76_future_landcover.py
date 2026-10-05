#| title: Land cover in 2030 and 2035, predicted with machine learning (Python)
#| description: A random forest learns how Bandung Raya's land cover changed over five years, is tested by predicting 2025 from 2020, and is then run forward to 2030 and 2035.

"""
CHAPTER 76 | Land cover in 2030 and 2035, predicted with machine learning

Classic land-change models (Markov chains, CA-Markov) count how often each
class turned into each other class and spread that rate over a suitability
map. Here a random forest learns the whole thing at once, pixel by pixel:
given what a pixel is now, what surrounds it and where it sits, what will it
be in five years?

    labels     Dynamic World V1, annual mode, grouped into 6 classes:
               water, trees, grass and shrub, crops, built, bare
    features   at year t: the pixel's class (one band per class), the share of
               built, crops and trees within 500 m and 1.5 km, the distance to
               built land, slope, elevation, distance to the city centre and
               population (GHSL 2020)
    train      features in 2017 -> class in 2022
    how much   the model says WHERE change is likely and INTO WHAT; how MUCH
               changes comes from the past: the share of the area that changed
               in the last observed five years (the "quantity" step of every
               land-change model). Without it the forest over-predicts change.
    test       features in 2020 -> predicted 2025, scored against the observed
               2025 map and against the simplest forecast of all, "nothing
               changes" (the 2020 map itself)
    forecast   2025 -> 2030, then the predicted 2030 -> 2035 (neighbourhoods are
               recomputed from the predicted map, so growth can feed growth)
    check      built area in 2030 against the GHSL P2023A projection, an
               independent model

The forecast reads "if the next five years behave like 2017-2022". A new toll
road, a spatial-plan change or a recession is outside what any trend model can
know.

Environment: pip install earthengine-api pandas numpy matplotlib
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# STEP 1. Area, classes and the label maps
# ---------------------------------------------------------------------------
AOI = ee.Geometry.Rectangle([107.40, -7.10, 107.80, -6.80], None, False)     # Bandung Raya
CENTRE = ee.Geometry.Point([107.6098, -6.9218])                              # Alun-alun Bandung
NAMES = ["water", "trees", "grass and shrub", "crops", "built", "bare"]
PALETTE = ["419bdf", "397d49", "a8c88e", "e4c372", "c4281b", "a59b8f"]
# Dynamic World: 0 water, 1 trees, 2 grass, 3 flooded vegetation, 4 crops, 5 shrub and scrub,
# 6 built, 7 bare, 8 snow and ice. Flooded vegetation joins grass and shrub (it is mostly
# wet grass and rice-field edges here).
DW_FROM, DW_TO = [0, 1, 2, 3, 4, 5, 6, 7], [0, 1, 2, 2, 3, 2, 4, 5]
SCALE = 60                                   # a regional forecast: 60 m cells keep the 2035 step within limits


def landcover(year):
    """The most frequent Dynamic World label of the year, in 6 classes."""
    d = ee.Date.fromYMD(year, 1, 1)
    return (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(AOI)
            .filterDate(d, d.advance(1, "year")).select("label").mode()
            .remap(DW_FROM, DW_TO).rename("lc").clip(AOI))


# ---------------------------------------------------------------------------
# STEP 2. Features: what a pixel is, what surrounds it, where it sits
# ---------------------------------------------------------------------------
PROJ = ee.Projection("EPSG:32748").atScale(SCALE)
dem = (ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").select("DEM").mosaic()
       .setDefaultProjection(ee.Projection("EPSG:4326").atScale(30)))
STATIC = ee.Image.cat([
    dem.rename("elev_m"), ee.Terrain.slope(dem).rename("slope_deg"),
    ee.FeatureCollection([ee.Feature(CENTRE)]).distance(60000).divide(1000).rename("km_to_centre"),
    ee.Image("JRC/GHSL/P2023A/GHS_POP/2020").select("population_count").max(0).add(1).log().rename("people_log"),
])


def features(lc):
    """Features computed from a class map, so they can be recomputed from a predicted map."""
    lc = ee.Image(lc).reproject(PROJ)
    onehot = ee.Image.cat([lc.eq(k).rename(f"is_{k}") for k in range(len(NAMES))])
    share = lambda k, m: lc.eq(k).focalMean(m, "circle", "meters").rename(f"share{k}_{m}")
    built = lc.eq(4)
    dist_built = (built.selfMask().fastDistanceTransform(256, "pixels", "squared_euclidean").sqrt()
                  .multiply(SCALE / 1000).unmask(256 * SCALE / 1000).rename("km_to_built"))
    return ee.Image.cat([onehot, share(4, 500), share(4, 1500), share(3, 500), share(1, 500),
                         dist_built, STATIC]).toFloat().clip(AOI)


BANDS = features(landcover(2017)).bandNames()

# ---------------------------------------------------------------------------
# STEP 3. Training data: 2017 features, the class five years later
# ---------------------------------------------------------------------------
# Change is rare, so a random sample would teach "nothing ever changes". Half the
# points come from pixels whose class changed between 2017 and 2022.
lc17, lc20, lc22, lc25 = landcover(2017), landcover(2020), landcover(2022), landcover(2025)
changed = lc17.neq(lc22).rename("changed").toInt()
train_img = features(lc17).addBands(lc22.rename("next")).addBands(changed)
train = train_img.stratifiedSample(numPoints=0, classBand="changed", region=AOI, scale=SCALE, seed=7,
                                   classValues=[0, 1], classPoints=[4000, 4000], tileScale=8)
model = (ee.Classifier.smileRandomForest(numberOfTrees=200, minLeafPopulation=3, seed=1)
         .setOutputMode("MULTIPROBABILITY").train(train, "next", BANDS))


def change_rate(a, b):
    """Share of the area whose class differs between two maps."""
    return ee.Number(a.neq(b).reduceRegion(ee.Reducer.mean(), AOI, 120, maxPixels=1e10, tileScale=8).values().get(0))


def predict(lc_now, rate):
    """Change the `rate` share of the area with the highest probability of change, each to its most likely new class."""
    lc_now = ee.Image(lc_now)
    probs = features(lc_now).classify(model).arrayFlatten([[f"p{k}" for k in range(len(NAMES))]])
    onehot = ee.Image.cat([lc_now.eq(k) for k in range(len(NAMES))])
    p_stay = probs.multiply(onehot).reduce("sum")
    p_change = ee.Image(1).subtract(p_stay).rename("pc")
    # The most likely class other than the current one.
    other = probs.multiply(ee.Image(1).subtract(onehot)).toArray().arrayArgmax().arrayGet([0]).rename("to")
    cut = p_change.reduceRegion(ee.Reducer.percentile([ee.Number(1).subtract(rate).multiply(100)]), AOI, 120,
                                maxPixels=1e10, tileScale=8).values().get(0)
    return lc_now.where(p_change.gt(ee.Number(cut)), other).rename("lc").toInt()


# ---------------------------------------------------------------------------
# STEP 4. The test: predict 2025 from 2020, and compare with what happened
# ---------------------------------------------------------------------------
RATE_17_22 = change_rate(lc17, lc22)          # what was known in 2022
pred25 = predict(lc20, RATE_17_22)

_c = {}


def hindcast_table():
    """Agreement with the observed 2025 map, and the Figure of Merit on change pixels."""
    if "hind" in _c:
        return _c["hind"]
    obs_change = lc20.neq(lc25)
    rows = []
    for name, p in (("random forest, 2020 -> 2025", pred25), ("no change (2020 map as the 2025 forecast)", lc20)):
        pred_change = lc20.neq(p)
        hits = obs_change.And(pred_change).And(p.eq(lc25))           # change predicted, to the right class
        wrong = obs_change.And(pred_change).And(p.neq(lc25))         # change predicted, to the wrong class
        misses = obs_change.And(pred_change.Not())
        false_alarms = obs_change.Not().And(pred_change)
        img = ee.Image.cat([p.eq(lc25).rename("agree"), hits.rename("h"), wrong.rename("w"),
                            misses.rename("m"), false_alarms.rename("f"), obs_change.rename("oc")])
        s = img.reduceRegion(ee.Reducer.mean(), AOI, 120, maxPixels=1e10, tileScale=8).getInfo()
        fom = s["h"] / (s["h"] + s["w"] + s["m"] + s["f"]) if (s["h"] + s["w"] + s["m"] + s["f"]) else 0
        rows.append({"forecast": name, "agreement_with_2025": s["agree"], "observed_change_share": s["oc"],
                     "figure_of_merit": fom, "hits": s["h"], "misses": s["m"], "false_alarms": s["f"]})
    _c["hind"] = pd.DataFrame(rows)
    return _c["hind"]


# ---------------------------------------------------------------------------
# STEP 5. The forecast: 2030 from 2025, then 2035 from the predicted 2030
# ---------------------------------------------------------------------------
RATE_20_25 = change_rate(lc20, lc25)          # the latest observed five years
pred30 = predict(lc25, RATE_20_25)
pred35 = predict(pred30, RATE_20_25)


def area_frame():
    """Hectares per class: observed 2017, 2020, 2025; predicted 2030, 2035."""
    if "area" in _c:
        return _c["area"]
    area = ee.Image.pixelArea().divide(1e4)
    rows = []
    for year, img, kind in ((2017, lc17, "observed"), (2020, lc20, "observed"), (2025, lc25, "observed"),
                            (2030, pred30, "predicted"), (2035, pred35, "predicted")):
        g = (area.addBands(img.rename("lc")).reduceRegion(ee.Reducer.sum().group(1, "lc"), AOI, 120,
                                                         maxPixels=1e10, tileScale=8).get("groups").getInfo())
        for d in g:
            rows.append({"year": year, "kind": kind, "class": NAMES[int(d["lc"])], "ha": d["sum"]})
    _c["area"] = pd.DataFrame(rows)
    return _c["area"]


def area_table(df):
    t = df.pivot_table(index="class", columns="year", values="ha").reindex(NAMES).round(0)
    t["change 2025-2035 (ha)"] = t[2035] - t[2025]
    return t.reset_index()


def plot_area(df):
    fig, ax = plt.subplots(figsize=(8, 4))
    for k, n in enumerate(NAMES):
        d = df[df["class"] == n].sort_values("year")
        ax.plot(d.year, d.ha / 1000, marker="o", color="#" + PALETTE[k], label=n, lw=2)
        p = d[d.kind == "predicted"]
        ax.plot(p.year, p.ha / 1000, marker="o", color="#" + PALETTE[k], lw=2, ls="--")
    ax.axvspan(2025, 2035.5, color="#f0efec", zorder=0)
    ax.text(2025.3, ax.get_ylim()[1] * 0.95, "predicted", fontsize=8, color="#52514e", va="top")
    ax.set_ylabel("thousand ha"); ax.set_xticks([2017, 2020, 2025, 2030, 2035])
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.18))
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def importance_frame():
    imp = model.explain().get("importance").getInfo()
    return pd.DataFrame(sorted(imp.items(), key=lambda x: -x[1]), columns=["feature", "importance"])


def plot_importance(df):
    d = df.head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.barh(d.feature, d.importance, color="#2a78d6")
    ax.set_xlabel("random forest importance"); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def ghsl_check():
    """Built-up area: our 2025 and 2030 against GHSL's own 2025 and 2030 projections (cells >= 20 % built)."""
    area = ee.Image.pixelArea().divide(1e4)
    ghsl = lambda y: ee.Image(f"JRC/GHSL/P2023A/GHS_BUILT_S/{y}").select("built_surface").divide(10000).gte(0.2)
    s = (ee.Image.cat([area.updateMask(lc25.eq(4)).rename("ours_2025"), area.updateMask(pred30.eq(4)).rename("ours_2030"),
                       area.updateMask(ghsl(2025)).rename("ghsl_2025"), area.updateMask(ghsl(2030)).rename("ghsl_2030")])
         .reduceRegion(ee.Reducer.sum(), AOI, 120, maxPixels=1e10, tileScale=8).getInfo())
    return pd.DataFrame([
        {"source": "this model (Dynamic World built)", "built_2025_ha": s["ours_2025"], "built_2030_ha": s["ours_2030"],
         "growth_pct": 100 * (s["ours_2030"] / s["ours_2025"] - 1)},
        {"source": "GHSL P2023A projection (cells >= 20 % built)", "built_2025_ha": s["ghsl_2025"], "built_2030_ha": s["ghsl_2030"],
         "growth_pct": 100 * (s["ghsl_2030"] / s["ghsl_2025"] - 1)}])


NEW_BUILT = (ee.Image(0).where(lc25.eq(4), 1).where(pred30.eq(4).And(lc25.neq(4)), 2)
             .where(pred35.eq(4).And(pred30.neq(4)), 3).selfMask().clip(AOI))


def products():
    vis = {"min": 0, "max": 5, "palette": PALETTE}
    classes = list(zip(NAMES, ["#" + c for c in PALETTE]))
    src = "Dynamic World V1, Copernicus DEM, GHSL. GEE."
    return [
        {"kind": "map", "name": "ch76-lc-2025", "image": lc25, "region": AOI, "vis": vis, "classes": classes,
         "title": "Bandung Raya, land cover 2025 (observed)", "source": src,
         "caption": "The most frequent Dynamic World label of 2025, in six classes: the starting point of the forecast."},
        {"kind": "table", "name": "ch76-hindcast", "data": hindcast_table,
         "floatfmt": ("", ".3f", ".3f", ".3f", ".4f", ".4f", ".4f"),
         "caption": "The test before the forecast: 2025 predicted from 2020, scored against the observed 2025 map and against "
                    "'nothing changes'. Hits, misses and false alarms are shares of the area."},
        {"kind": "map", "name": "ch76-lc-2030", "image": pred30, "region": AOI, "vis": vis, "classes": classes,
         "title": "Bandung Raya, land cover 2030 (predicted)", "source": src,
         "caption": "The model run forward from 2025."},
        {"kind": "map", "name": "ch76-lc-2035", "image": pred35, "region": AOI, "vis": vis, "classes": classes,
         "title": "Bandung Raya, land cover 2035 (predicted)", "source": src,
         "caption": "Run forward again from the predicted 2030, with neighbourhoods recomputed from that map."},
        {"kind": "map", "name": "ch76-new-built", "image": NEW_BUILT, "region": AOI,
         "vis": {"min": 1, "max": 3, "palette": ["9e9e9e", "fd8d3c", "800026"]},
         "classes": [("built in 2025", "#9e9e9e"), ("new by 2030", "#fd8d3c"), ("new by 2035", "#800026")],
         "title": "Where Bandung Raya is predicted to build next", "source": src,
         "caption": "Built land in 2025 and the cells the model expects to become built by 2030 and 2035."},
        {"kind": "chart", "name": "ch76-area", "data": area_frame, "plot": plot_area,
         "caption": "Area per class: observed 2017, 2020 and 2025 (solid), predicted 2030 and 2035 (dashed)."},
        {"kind": "table", "name": "ch76-area-table", "data": area_frame, "transform": area_table, "floatfmt": ".0f",
         "caption": "Hectares per class, observed and predicted."},
        {"kind": "chart", "name": "ch76-importance", "data": importance_frame, "plot": plot_importance,
         "caption": "What the random forest leans on most (top 10 features)."},
        {"kind": "table", "name": "ch76-ghsl-check", "data": ghsl_check, "floatfmt": ("", ".0f", ".0f", ".1f"),
         "caption": "Built-up growth 2025-2030: this model against the GHSL projection, an independent model."},
    ]


if __name__ == "__main__":
    import json, os
    k = os.path.expanduser(os.environ.get("BOOK_EE_KEY", "~/.config/fullstack-rs/ee-key.json")); info = json.load(open(k))
    ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], k), project=info.get("project_id"))
    print(hindcast_table()); print(area_table(area_frame())); print(ghsl_check())
