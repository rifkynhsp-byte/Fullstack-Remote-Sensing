#| title: Urban growth and population: fifty years of Indonesian cities (Python)
#| description: Measures how Indonesia urbanised from 1975 to 2030 with the GHSL degree of urbanisation, animates Jabodetabek's built-up growth, draws its sprawl as a radial profile, scores twelve cities on SDG 11.3.1 (land consumption against population growth), trains an urban growth model and applies it in Earth Engine, and maps 2016-2023 densification from Google Open Buildings.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 72 | Urban growth: where Indonesian cities grew, how fast, and where next

Urban planners ask four questions of a satellite archive: how many people
live in cities, how fast is land being built on compared with how fast the
population grows, in which direction is the city spreading, and where will it
go next. This script answers each with open data, for Indonesia and in detail
for Jabodetabek.

Data: GHSL P2023A built-up surface, population and settlement model (SMOD),
1975-2030 in 5-year epochs (100 m and 1 km; 2025 and 2030 are projections);
Google Open Buildings 2.5D Temporal (2016-2023); Copernicus DEM; FAO GAUL 2025.
All public, all in Earth Engine. Tables are saved to data/ch72_*.csv so the
analysis and the R twin run without Earth Engine.

Environment: pip install earthengine-api pandas numpy matplotlib scikit-learn statsmodels
"""

import os
from pathlib import Path

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2] if "__file__" in globals() else Path(".")
DATA = Path(os.environ.get("URBAN_DATA", ROOT / "data"))
EPOCHS = list(range(1975, 2035, 5))
OBSERVED = [y for y in EPOCHS if y <= 2020]          # 2025 and 2030 are GHSL projections
JABO = [106.35, -6.80, 107.25, -5.95]                 # Jabodetabek
MONAS = (106.8272, -6.1754)                           # the national monument, Jakarta's centre
CITIES = ["Kota Surabaya", "Kota Bandung", "Kota Medan", "Kota Semarang", "Kota Makassar", "Kota Palembang",
          "Kota Denpasar", "Kota Pekanbaru", "Kota Balikpapan", "Kota Batam", "Kota Yogyakarta", "Kota Malang"]
METRO = ["Kota Bogor", "Bogor", "Kota Depok", "Kota Tangerang", "Kota Tangerang Selatan", "Tangerang", "Kota Bekasi", "Bekasi"]
SMOD_CLASS = {30: "urban centre", 23: "dense urban cluster", 22: "semi-dense urban cluster", 21: "suburban",
              13: "rural cluster", 12: "low-density rural", 11: "very low-density rural", 10: "water"}


def ghsl(name, year):
    return ee.Image(f"JRC/GHSL/P2023A/{name}/{year}")


def built_frac(year):
    """Share of each 100 m cell covered by buildings (built_surface is m2 per 10,000 m2 cell)."""
    return ghsl("GHS_BUILT_S", year).select("built_surface").divide(10000).rename("built")


def jabo():
    return ee.Geometry.Rectangle(JABO, None, False)


def cached(name, build):
    f = DATA / f"ch72_{name}.csv"
    if f.exists():
        return pd.read_csv(f)
    df = build()
    DATA.mkdir(parents=True, exist_ok=True)
    df.to_csv(f, index=False, float_format="%.6g")
    return df


# PART 1. How urban is Indonesia? The degree of urbanisation, 1975-2030 -----------------------------
def urbanisation():
    """Population in each settlement class (GHSL SMOD, the UN-endorsed Degree of Urbanisation)."""
    def build():
        # The national outline has too many edges for one region, so paint it as a mask instead.
        idn_mask = ee.Image(0).paint(ee.FeatureCollection("FAO/GAUL/2025/level1").filter(ee.Filter.eq("ISO3_CODE", "IDN")), 1)
        idn = ee.Geometry.Rectangle([94, -11.5, 141.5, 6.5], None, False)
        rows = []
        for y in EPOCHS:
            smod = ee.Image(f"JRC/GHSL/P2023A/GHS_SMOD_V2-0/{y}").select("smod_code")
            # People are counted per 100 m cell; sum them into the 1 km SMOD grid (a sample would undercount 100x).
            pop = (ghsl("GHS_POP", y).select("population_count")
                   .reduceResolution(ee.Reducer.sum().unweighted(), maxPixels=1024).reproject(smod.projection()))
            r = (pop.addBands(smod).updateMask(idn_mask).reduceRegion(ee.Reducer.sum().group(1, "smod"), idn, 1000,
                                                  crs=smod.projection(), maxPixels=1e10, tileScale=4).get("groups").getInfo())
            rows += [{"year": y, "smod": g["smod"], "people": g["sum"]} for g in r]
        return pd.DataFrame(rows)
    df = cached("urbanisation", build)
    df["class"] = df.smod.map(lambda c: "city (urban centre)" if c == 30 else "town and suburb (urban cluster)" if c >= 21 else "rural")
    t = df.groupby(["year", "class"]).people.sum().unstack()
    t = (100 * t.div(t.sum(axis=1), axis=0)).round(1)
    t.insert(0, "population (million)", (df.groupby("year").people.sum() / 1e6).round(1))
    return t.reset_index()


def plot_urbanisation(t):
    fig, ax = plt.subplots(figsize=(8, 3.8))
    cols = ["city (urban centre)", "town and suburb (urban cluster)", "rural"]
    ax.stackplot(t.year, *[t[c] for c in cols], labels=cols, colors=["#b2182b", "#f4a582", "#a6d96a"], alpha=0.9)
    ax.axvspan(2020, 2030, color="white", alpha=0.45); ax.text(2025, 4, "projection", ha="center", fontsize=8)
    ax.set_ylabel("share of population (%)"); ax.set_xlim(1975, 2030); ax.set_ylim(0, 100)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    a, b = t.set_index("year").loc[[1975, 2020], "city (urban centre)"]
    ax.set_title(f"Indonesians living in cities: {a:.0f} % in 1975, {b:.0f} % in 2020", loc="left", fontweight="bold", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


# PART 2. Jabodetabek: a time-lapse and a radial profile ---------------------------------------------
def growth_frame(y):
    vis = dict(min=0, max=0.6, palette=["#f7f7f7", "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#67001f"])
    water = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").select("WBM").mosaic().gt(0)
    base = ee.Image(1).visualize(palette=["#ffffff"]).where(water, ee.Image(1).visualize(palette=["#c6dbef"]))
    b = built_frac(y)
    return base.blend(b.updateMask(b.gt(0.02)).visualize(**vis))


def radial_profile():
    """Mean built-up share in 2 km rings around Monas, every observed epoch."""
    def build():
        centre = ee.Geometry.Point(MONAS)
        ring = lambda r: centre.buffer(r + 2000, 50) if r == 0 else centre.buffer(r + 2000, 50).difference(centre.buffer(r, 50), 50)
        rings = ee.FeatureCollection([ee.Feature(ring(r), {"km": (r + 1000) / 1000})
                                      for r in range(0, 60000, 2000)])
        img = ee.Image.cat([built_frac(y).rename(f"y{y}") for y in OBSERVED])
        fc = img.reduceRegions(rings, ee.Reducer.mean(), 100).getInfo()["features"]
        return pd.DataFrame([f["properties"] for f in fc])
    df = cached("radial", build)
    return df.melt("km", var_name="year", value_name="built").assign(year=lambda d: d.year.str[1:].astype(int))


def plot_radial(t):
    df = radial_profile()
    fig, ax = plt.subplots(figsize=(8, 3.8))
    cmap = plt.get_cmap("viridis")
    for i, (y, g) in enumerate(df.groupby("year")):
        ax.plot(g.km, 100 * g.built, color=cmap(i / (len(OBSERVED) - 1)), lw=2 if y in (1975, 2020) else 1, label=str(y))
    w = df.pivot(index="km", columns="year", values="built")
    edge = lambda y: w.index[(w[y] >= 0.10).values][-1]
    ax.set_xlabel("distance from Monas (km)"); ax.set_ylabel("built-up share of land (%)")
    ax.legend(frameon=False, ncol=2, fontsize=7, title="epoch", title_fontsize=8)
    ax.set_title(f"Where the built-up share falls below 10 %: {edge(1975):.0f} km from the centre in 1975, {edge(2020):.0f} km in 2020",
                 loc="left", fontweight="bold", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


# PART 3. SDG 11.3.1: is land consumed faster than the population grows? ----------------------------
def sdg_table():
    """LCRPGR = (ln(U2020/U2000)/20) / (ln(P2020/P2000)/20). Above 1: land is built on faster than people arrive."""
    def build():
        g = ee.FeatureCollection("FAO/GAUL/2025/level2").filter(ee.Filter.eq("ISO3_CODE", "IDN"))
        dki = ee.Feature(g.filter(ee.Filter.eq("GAUL1_NAME", "Dki Jakarta")).filter(
            ee.Filter.stringContains("GAUL2_NAME", "Seribu").Not()).geometry(), {"GAUL2_NAME": "DKI Jakarta"})
        # The same measure for the whole metropolitan region, to show how much the boundary matters
        metro = ee.Feature(dki.geometry().union(g.filter(ee.Filter.inList("GAUL2_NAME", METRO)).geometry(), 100),
                           {"GAUL2_NAME": "Jabodetabek (metro region)"})
        fc = g.filter(ee.Filter.inList("GAUL2_NAME", CITIES)).merge(ee.FeatureCollection([dki, metro]))
        img = ee.Image.cat([ghsl("GHS_BUILT_S", y).select("built_surface").rename(f"built{y}") for y in (2000, 2020)] +
                           [ghsl("GHS_POP", y).select("population_count").rename(f"pop{y}") for y in (2000, 2020)])
        out = img.reduceRegions(fc, ee.Reducer.sum(), 100, tileScale=4).getInfo()["features"]
        return pd.DataFrame([{k: f["properties"][k] for k in ["GAUL2_NAME", "built2000", "built2020", "pop2000", "pop2020"]} for f in out])
    df = cached("sdg11", build).drop_duplicates("GAUL2_NAME")
    df["city"] = df.GAUL2_NAME.str.replace("Kota ", "")
    df["land consumption rate (%/yr)"] = 100 * np.log(df.built2020 / df.built2000) / 20
    df["population growth rate (%/yr)"] = 100 * np.log(df.pop2020 / df.pop2000) / 20
    df["LCRPGR"] = df["land consumption rate (%/yr)"] / df["population growth rate (%/yr)"]
    df["built m² per person 2000"] = df.built2000 / df.pop2000
    df["built m² per person 2020"] = df.built2020 / df.pop2020
    cols = ["city", "land consumption rate (%/yr)", "population growth rate (%/yr)", "LCRPGR",
            "built m² per person 2000", "built m² per person 2020"]
    return df[cols].sort_values("LCRPGR", ascending=False).reset_index(drop=True)


def plot_sdg(t):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.8), gridspec_kw={"width_ratios": [1.3, 1]})
    x, y = t["population growth rate (%/yr)"], t["land consumption rate (%/yr)"]
    lo, hi = 0.01, 10
    a1.fill_between([lo, hi], [lo, hi], hi, color="#fddbc7", alpha=0.5)
    a1.plot([lo, hi], [lo, hi], color="grey", lw=0.8)
    a1.text(0.012, 6, "land built faster than\npeople arrive (spreading)", fontsize=8, va="top")
    a1.text(8, 0.013, "people arrive faster than\nland is built (densifying)", fontsize=8, ha="right")
    a1.scatter(x, y, s=40, color="#b2182b", zorder=3)
    for _, r in t.iterrows():
        a1.annotate(r.city.replace(" (metro region)", " metro"), (r["population growth rate (%/yr)"], r["land consumption rate (%/yr)"]),
                    fontsize=7.5, xytext=(4, 2), textcoords="offset points")
    a1.set_xscale("log"); a1.set_yscale("log"); a1.set_xlim(0.15, hi); a1.set_ylim(lo, hi)
    a1.set_xlabel("population growth rate, 2000-2020 (%/yr, log)"); a1.set_ylabel("land consumption rate (%/yr, log)")
    tt = t.sort_values("LCRPGR")
    a2.barh(tt.city, tt.LCRPGR, color=["#b2182b" if v > 1 else "#4393c3" for v in tt.LCRPGR])
    a2.axvline(1, color="k", lw=0.8); a2.set_xlabel("LCRPGR (1 = land and people grow at the same rate)")
    a2.tick_params(axis="y", labelsize=8)
    for a in (a1, a2):
        a.spines[["top", "right"]].set_visible(False)
    n = int((t.LCRPGR > 1).sum())
    fig.suptitle(f"SDG 11.3.1: only {n} of {len(t)} areas built on land faster than they gained people, 2000-2020",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


# PART 4. A model of where the city grows ---------------------------------------------------------
PREDICTORS = ["km_to_centre", "km_to_urban", "built_1km", "people_ha", "slope_deg", "elev_m"]
LABELS = {"km_to_centre": "distance to Monas (km)", "km_to_urban": "distance to the urban edge (km)",
          "built_1km": "built-up share within 1 km", "people_ha": "people per ha (log)",
          "slope_deg": "slope (degrees)", "elev_m": "elevation (m)"}


def predictor_image(year=2000):
    """The six drivers as they were in `year`: 2000 to fit the model, 2020 to look ahead."""
    urban = built_frac(year).gt(0.2)
    proj = ee.Projection("EPSG:32748").atScale(100)
    dist_urban = urban.selfMask().fastDistanceTransform(256, "pixels", "squared_euclidean").sqrt() \
        .multiply(0.1).reproject(proj).rename("km_to_urban")
    dist_centre = ee.FeatureCollection([ee.Feature(ee.Geometry.Point(MONAS))]).distance(80000).divide(1000).rename("km_to_centre")
    dem = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").select("DEM").mosaic().setDefaultProjection(proj)
    return ee.Image.cat([
        dist_centre, dist_urban,
        built_frac(year).focalMean(1000, "circle", "meters").rename("built_1km"),
        ghsl("GHS_POP", year).select("population_count").max(0).rename("people_ha"),   # -200 = no data at sea
        ee.Terrain.slope(dem).rename("slope_deg"), dem.rename("elev_m")]).toFloat()


def growth_sample():
    """Cells not urban in 2000 (built share < 20 %) on land; did they become urban (>= 20 %) by 2020?"""
    def build():
        water = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").select("WBM").mosaic().gt(0)
        b0, b1 = built_frac(2000), built_frac(2020)
        cand = b0.lt(0.2).And(water.Not())
        img = predictor_image().addBands(b1.gte(0.2).rename("urbanised").toInt()).updateMask(cand)
        s = img.stratifiedSample(numPoints=0, classBand="urbanised", region=jabo(), scale=100, seed=42,
                                 classValues=[0, 1], classPoints=[2500, 2500], geometries=True, tileScale=4)
        feats = s.getInfo()["features"]          # the 2000 values of the six drivers, and the 2020 outcome
        return pd.DataFrame([{**f["properties"], "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1]}
                             for f in feats])
    return cached("growth_sample", build).dropna()


_fit = {}


def fit_models():
    """Logistic regression (interpretable) against a random forest (flexible), on spatial blocks."""
    if _fit:
        return _fit
    import statsmodels.api as sm
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import StandardScaler
    d = growth_sample().copy()
    d["people_ha"] = np.log1p(d["people_ha"].clip(lower=0))     # very skewed; -200 is no data
    X, y = d[PREDICTORS], d["urbanised"]
    blocks = (np.floor(d.lon / 0.1) * 100 + np.floor(d.lat / 0.1)).astype(int)   # ~11 km blocks
    oof = {"logistic": np.zeros(len(d)), "random forest": np.zeros(len(d))}
    for tr, te in GroupKFold(5).split(X, y, blocks):
        sc = StandardScaler().fit(X.iloc[tr])
        oof["logistic"][te] = LogisticRegression(max_iter=1000).fit(sc.transform(X.iloc[tr]), y.iloc[tr]).predict_proba(sc.transform(X.iloc[te]))[:, 1]
        oof["random forest"][te] = RandomForestClassifier(300, min_samples_leaf=5, random_state=0, n_jobs=-1).fit(
            X.iloc[tr], y.iloc[tr]).predict_proba(X.iloc[te])[:, 1]
    sc = StandardScaler().fit(X)
    logit = sm.Logit(y, sm.add_constant(pd.DataFrame(sc.transform(X), columns=PREDICTORS, index=X.index))).fit(disp=0)
    _fit.update(d=d, oof=oof, auc={k: roc_auc_score(y, v) for k, v in oof.items()}, logit=logit, scaler=sc)
    return _fit


def model_table():
    f = fit_models()
    lg = f["logit"]
    ci = lg.conf_int()
    t = pd.DataFrame({"predictor (per 1 SD)": [LABELS.get(i, i) for i in lg.params.index], "odds ratio": np.exp(lg.params.values),
                      "95% CI low": np.exp(ci[0].values), "95% CI high": np.exp(ci[1].values), "p": lg.pvalues.values})
    t = t[t["predictor (per 1 SD)"] != "const"]
    t.insert(1, "1 SD =", [f"{v:.3g}" for v in f["scaler"].scale_])
    return t.reset_index(drop=True)


def plot_model(t):
    from sklearn.metrics import roc_curve
    f = fit_models()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4))
    for k, c in [("logistic", "#2166ac"), ("random forest", "#b2182b")]:
        fpr, tpr, _ = roc_curve(f["d"].urbanised, f["oof"][k])
        a1.plot(fpr, tpr, color=c, label=f"{k}: AUC {f['auc'][k]:.2f}")
    a1.plot([0, 1], [0, 1], color="grey", ls=":")
    a1.set_xlabel("false positive rate"); a1.set_ylabel("true positive rate"); a1.legend(frameon=False)
    a1.set_title("Spatially blocked 5-fold ROC", loc="left", fontsize=10)
    tt = t.sort_values("odds ratio")
    a2.errorbar(tt["odds ratio"], tt["predictor (per 1 SD)"], xerr=[tt["odds ratio"] - tt["95% CI low"], tt["95% CI high"] - tt["odds ratio"]],
                fmt="o", color="#2166ac")
    a2.axvline(1, color="grey", ls=":"); a2.set_xscale("log")
    a2.set_xticks([0.3, 0.5, 1, 2, 3]); a2.set_xticklabels(["0.3", "0.5", "1", "2", "3"]); a2.minorticks_off()
    a2.set_xlabel("odds ratio of becoming urban, per 1 SD (log scale)")
    a2.set_title("What drives growth (logistic regression)", loc="left", fontsize=10)
    for a in (a1, a2):
        a.spines[["top", "right"]].set_visible(False)
    top = t.loc[(np.log(t["odds ratio"])).abs().idxmax()]
    fig.suptitle(f"The strongest single driver: {top['predictor (per 1 SD)']} (odds ratio {top['odds ratio']:.2f} per SD)",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


def growth_probability(year=2020):
    """The fitted logistic model, written out as an Earth Engine expression and applied to every cell.

    Fitted on what happened 2000-2020 and applied to the city of 2020, it reads as
    "where would growth go in the next twenty years if the same forces kept working".
    """
    f = fit_models()
    lg, sc = f["logit"], f["scaler"]
    img = predictor_image(year)
    img = img.addBands(img.select("people_ha").add(1).log(), overwrite=True)   # log1p, as in the fit
    z = ee.Image.constant(float(lg.params["const"]))
    for i, p in enumerate(PREDICTORS):
        z = z.add(img.select(p).subtract(float(sc.mean_[i])).divide(float(sc.scale_[i])).multiply(float(lg.params[p])))
    prob = ee.Image(1).divide(ee.Image(1).add(z.multiply(-1).exp()))
    water = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").select("WBM").mosaic().gt(0)
    return prob.updateMask(built_frac(year).lt(0.2)).updateMask(water.Not()).clip(jabo())


# PART 5. Up, not only out: Open Buildings 2016 to 2023 ------------------------------------------------
def buildings(year):
    return (ee.ImageCollection("GOOGLE/Research/open-buildings-temporal/v1").filterBounds(jabo())
            .filter(ee.Filter.calendarRange(year, year, "year")).mosaic())


def densification_image():
    """Change in building cover (presence > 0.5) and mean height between 2016 and 2023, at 50 m."""
    a, b = buildings(2016), buildings(2023)
    cover = lambda im: im.select("building_presence").gt(0.5)
    proj = ee.Projection("EPSG:32748").atScale(50)
    d_cover = cover(b).subtract(cover(a)).setDefaultProjection(ee.Projection("EPSG:32748").atScale(4)) \
        .reduceResolution(ee.Reducer.mean(), maxPixels=1024).reproject(proj)
    return d_cover.rename("new_cover").clip(jabo())


def densification_by_ring():
    """Mean change in building cover in 5 km rings around Monas: does the city fill in, or grow at the edge?"""
    def build():
        centre = ee.Geometry.Point(MONAS)
        ring = lambda r: centre.buffer(r + 5000, 50) if r == 0 else centre.buffer(r + 5000, 50).difference(centre.buffer(r, 50), 50)
        fc = ee.FeatureCollection([ee.Feature(ring(r), {"ring_km": f"{r // 1000}-{r // 1000 + 5}"}) for r in range(0, 40000, 5000)])
        a, b = buildings(2016).select("building_presence").gt(0.5), buildings(2023).select("building_presence").gt(0.5)
        img = a.rename("cover_2016").addBands(b.rename("cover_2023"))
        out = img.reduceRegions(fc, ee.Reducer.mean(), 20, tileScale=8).getInfo()["features"]
        return pd.DataFrame([f["properties"] for f in out])
    df = cached("densification", build)
    df["change (points)"] = 100 * (df.cover_2023 - df.cover_2016)
    df["cover_2016"] *= 100; df["cover_2023"] *= 100
    return df.rename(columns={"ring_km": "km from Monas", "cover_2016": "building cover 2016 (%)", "cover_2023": "building cover 2023 (%)"})


def products():
    jab = jabo()
    return [
        {"kind": "table", "name": "ch72-urbanisation", "data": urbanisation, "floatfmt": (".0f", ".1f", ".1f", ".1f", ".1f"),
         "caption": "Population of Indonesia by degree of urbanisation (GHSL SMOD), 1975-2030. 2025 and 2030 are GHSL projections."},
        {"kind": "chart", "name": "ch72-urbanisation-chart", "data": urbanisation, "plot": plot_urbanisation,
         "caption": "Half a century of urbanisation in one stacked chart."},
        {"kind": "animation", "name": "ch72-jabodetabek-growth", "frames": [growth_frame(y) for y in OBSERVED],
         "region": jab, "width": 600, "fps": 1.5, "labels": [f"Jabodetabek built-up, {y}" for y in OBSERVED],
         "caption": "Built-up share of each 100 m cell, GHSL 1975-2020, every five years. The city grows along the "
                    "toll roads east to Bekasi and Cikarang, west to Tangerang and south to Bogor."},
        {"kind": "map", "name": "ch72-built-2020", "image": built_frac(2020), "region": jab,
         "vis": {"min": 0, "max": 0.6, "palette": ["#f7f7f7", "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#67001f"]},
         "title": "Built-up share of land, 2020", "source": "GHSL P2023A GHS_BUILT_S. GEE.",
         "caption": "The last frame as a map, with coordinates and a scale bar."},
        {"kind": "chart", "name": "ch72-radial", "data": urbanisation, "plot": plot_radial, "live": False,
         "caption": "Built-up share in 2 km rings around Monas, one line per five-year epoch: the city's edge moving outwards."},
        {"kind": "table", "name": "ch72-sdg", "data": sdg_table, "floatfmt": ("", ".2f", ".2f", ".2f", ".0f", ".0f"),
         "caption": "SDG 11.3.1, the ratio of land consumption rate to population growth rate, 2000-2020, within each city's administrative boundary."},
        {"kind": "chart", "name": "ch72-sdg-chart", "data": sdg_table, "plot": plot_sdg,
         "caption": "Each city against the 1:1 line."},
        {"kind": "table", "name": "ch72-model", "data": model_table, "floatfmt": ("", "", ".2f", ".2f", ".2f", ".2g"),
         "caption": "Logistic regression of becoming urban between 2000 and 2020, standardised predictors."},
        {"kind": "chart", "name": "ch72-model-chart", "data": model_table, "plot": plot_model, "live": False,
         "caption": "Left: how well each model ranks cells, on spatially separate test blocks. Right: the drivers."},
        {"kind": "map", "name": "ch72-growth-probability", "image": growth_probability(), "region": jab,
         "vis": {"min": 0, "max": 1, "palette": ["#ffffcc", "#c2e699", "#78c679", "#fd8d3c", "#e31a1c", "#800026"]},
         "title": "Where growth goes next: probability of becoming urban, 2020-2040", "source": "Model fitted on 2000-2020 in Python, applied to 2020 in GEE.",
         "caption": "The logistic model fitted on 2000-2020 and applied to the drivers as they were in 2020. Cells already urban in 2020 are blank."},
        {"kind": "map", "name": "ch72-densification", "image": densification_image(), "region": ee.Geometry.Rectangle([106.6, -6.45, 107.1, -6.1], None, False),
         "vis": {"min": -0.2, "max": 0.4, "palette": ["#2166ac", "#f7f7f7", "#fdae61", "#d7191c"]},
         "title": "Change in building cover, 2016 to 2023 (share of each 50 m cell)", "source": "Google Open Buildings 2.5D Temporal v1. GEE.",
         "caption": "Where building cover rose (red) or fell (blue) in seven years, central Jakarta to the inner suburbs."},
        {"kind": "table", "name": "ch72-densification-rings", "data": densification_by_ring, "floatfmt": ("", ".1f", ".1f", ".1f"),
         "columns": ["km from Monas", "building cover 2016 (%)", "building cover 2023 (%)", "change (points)"],
         "caption": "Building cover in 5 km rings around Monas, 2016 and 2023 (Open Buildings presence > 0.5)."},
    ]


if __name__ == "__main__":
    import json
    k = os.path.expanduser(os.environ.get("BOOK_EE_KEY", "~/.config/fullstack-rs/ee-key.json")); info = json.load(open(k))
    ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], k), project=info.get("project_id"))
    print(urbanisation()); print(radial_profile().pivot(index="km", columns="year", values="built").round(2).iloc[::3])
    print(sdg_table().round(2)); print(model_table().round(3)); print(fit_models()["auc"])
