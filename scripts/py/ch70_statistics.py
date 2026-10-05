#| title: Statistics every remote sensing analyst needs (Python)
#| description: One question - how much hotter is built-up land in Greater Bandung, and does greenery cool it? - answered with central tendency and spread, outliers by IQR and z-score, the central limit theorem, confidence intervals and the bootstrap, t, Mann-Whitney and Kolmogorov-Smirnov tests, and regression with its diagnostics.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 70 | Statistics every remote sensing analyst needs

A confusion matrix tells you how often a map is right. It does not tell you
whether two places really differ, how sure you are of an average, or how much
one thing changes with another. That is what this chapter is for.

The data: a stratified random sample of 30 m pixels across Greater Bandung,
each with its dry-season land surface temperature (Landsat 8/9), its Dynamic
World land cover, the greenery around it and its population density. The
sample is saved to data/ch70_bandung_lst_sample.csv, so every method below
runs without Earth Engine; sample() re-draws it from Earth Engine if the file
is missing.

Environment: pip install pandas numpy scipy statsmodels matplotlib earthengine-api
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2] if "__file__" in globals() else Path(".")
CSV = Path(os.environ.get("STATS_CSV", ROOT / "data" / "ch70_bandung_lst_sample.csv"))
CLASSES = {1: "trees", 2: "grass", 4: "crops", 6: "built"}        # Dynamic World label codes kept
COLOURS = {"trees": "#1b7837", "grass": "#a6dba0", "crops": "#e6ab02", "built": "#d73027"}
N_PER_CLASS = 600
SEED = 42


# PART 1. The sample -------------------------------------------------------------------
def sample():
    """Stratified random sample: N_PER_CLASS pixels of each land cover, with LST, greenery and people."""
    if CSV.exists():
        return pd.read_csv(CSV)
    import ee
    area = (ee.FeatureCollection("FAO/GAUL/2025/level2").filter(ee.Filter.eq("GAUL1_NAME", "Jawa Barat"))
            .filter(ee.Filter.inList("GAUL2_NAME", ["Kota Bandung", "Kota Cimahi", "Bandung", "Bandung Barat"])))
    geom = area.geometry()

    def st(img):
        qa = img.select("QA_PIXEL")
        clear = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        return img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15).updateMask(clear)
    lst = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
           .filterBounds(geom).filterDate("2023-06-01", "2024-10-01").filter(ee.Filter.calendarRange(6, 9, "month"))
           .map(st).median().rename("lst"))
    dwc = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geom).filterDate("2024-01-01", "2025-01-01")
    label = dwc.select("label").mode().rename("label")
    probs = dwc.select(["trees", "grass"]).mean()
    green = probs.select("trees").add(probs.select("grass")).focalMean(300, "circle", "meters").rename("greenery")
    people = (ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "IDN"))
              .filter(ee.Filter.eq("year", 2020)).mosaic().unmask(0).rename("people_ha"))
    img = lst.addBands(green).addBands(people).addBands(label).clip(geom)
    # numPoints=0: sample only the classes listed in classValues, not every land cover
    pts = img.stratifiedSample(numPoints=0, classBand="label", region=geom, scale=30, seed=SEED,
                               classValues=list(CLASSES), classPoints=[N_PER_CLASS] * len(CLASSES),
                               geometries=True, tileScale=8)
    rows = [{**f["properties"], "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1]}
            for f in pts.getInfo()["features"]]
    d = pd.DataFrame(rows).dropna()
    d["cover"] = d.label.map(CLASSES)
    d = d[["lon", "lat", "cover", "lst", "greenery", "people_ha"]].round(5)
    CSV.parent.mkdir(parents=True, exist_ok=True); d.to_csv(CSV, index=False)
    return d


ORDER = ["trees", "grass", "crops", "built"]


# PART 2. Central tendency and spread --------------------------------------------------------
def summary_table():
    d = sample()
    def mad(x): return stats.median_abs_deviation(x, scale="normal")
    t = d.groupby("cover").lst.agg(n="count", mean="mean", median="median", sd="std",
                                    iqr=lambda x: x.quantile(0.75) - x.quantile(0.25), mad=mad, skew=lambda x: stats.skew(x))
    return t.reindex(ORDER).reset_index()


def plot_distributions(df):
    d = sample()
    fig, ax = plt.subplots(figsize=(9, 4.4))
    xs = np.linspace(d.lst.quantile(0.002), d.lst.quantile(0.998), 400)
    for c in ORDER:
        x = d[d.cover == c].lst; k = stats.gaussian_kde(x)
        ax.plot(xs, k(xs), color=COLOURS[c], lw=2, label=c)
        ax.axvline(x.mean(), color=COLOURS[c], lw=1, ls="-"); ax.axvline(x.median(), color=COLOURS[c], lw=1, ls=":")
    ax.set_xlabel("dry-season land surface temperature (°C)"); ax.set_ylabel("density")
    ax.legend(title="land cover (solid line: mean, dotted: median)", fontsize=8, title_fontsize=8)
    b, t_ = df.set_index("cover").loc["built"], df.set_index("cover").loc["trees"]
    ax.set_title(f"Built-up land is {b['median'] - t_['median']:.1f} °C hotter than trees at the median, and its spread is wider",
                 loc="left", fontsize=10)
    fig.tight_layout()
    return fig


# PART 3. Outliers: the IQR rule and the z-score --------------------------------------------
def outlier_table():
    d = sample(); rows = []
    for c in ORDER:
        x = d[d.cover == c].lst; q1, q3 = x.quantile([0.25, 0.75]); iqr = q3 - q1
        z = (x - x.mean()) / x.std()
        rows.append({"cover": c, "low fence": q1 - 1.5 * iqr, "high fence": q3 + 1.5 * iqr,
                     "outside fences": int(((x < q1 - 1.5 * iqr) | (x > q3 + 1.5 * iqr)).sum()),
                     "|z| > 3": int((z.abs() > 3).sum()), "|z| > 2": int((z.abs() > 2).sum())})
    return pd.DataFrame(rows)


def plot_outliers(df):
    d = sample()
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw=dict(width_ratios=[1, 1.2]))
    axs[0].boxplot([d[d.cover == c].lst for c in ORDER], whis=1.5, widths=0.55, patch_artist=True,
                   boxprops=dict(facecolor="#f0f0f0"), flierprops=dict(marker="o", markersize=3, markerfacecolor="#d73027"))
    axs[0].set_xticks(range(1, 5), ORDER); axs[0].set_ylabel("LST (°C)")
    axs[0].set_title("Box plots: whiskers at 1.5 × IQR, red points beyond them", loc="left", fontsize=9)
    d = d.copy(); d["z"] = (d.lst - d.lst.mean()) / d.lst.std()
    sc = axs[1].scatter(d.lon, d.lat, c=d.z, cmap="RdBu_r", vmin=-3, vmax=3, s=6)
    fig.colorbar(sc, ax=axs[1], shrink=0.8, label="z-score of LST (whole sample)")
    xt = np.arange(np.ceil(d.lon.min() * 10) / 10, d.lon.max(), 0.1); yt = np.arange(np.ceil(d.lat.min() * 10) / 10, d.lat.max(), 0.1)
    axs[1].set_xticks(xt, [f"{v:.1f}°E" for v in xt], fontsize=7); axs[1].set_yticks(yt, [f"{abs(v):.1f}°S" for v in yt], fontsize=7)
    axs[1].grid(color="#999", lw=0.4, ls="--"); axs[1].set_aspect("equal")
    axs[1].set_title("Where the sample is hot (z > 0) and cool (z < 0)", loc="left", fontsize=9)
    fig.suptitle("Two rules for 'unusual': the IQR fences per class, and the z-score against the whole area",
                 x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    return fig


# PART 4. The central limit theorem -------------------------------------------------------------
SIZES = [2, 5, 30, 100]


def clt_table(reps=5000):
    """Treat the whole sample's population density (strongly right-skewed) as the population;
    draw many samples of size n; look at their means."""
    x = sample().people_ha.values
    rng = np.random.default_rng(SEED); rows = []
    for n in SIZES:
        means = rng.choice(x, size=(reps, n), replace=True).mean(axis=1)
        rows.append({"n": n, "sd of sample means": means.std(ddof=1), "sigma / sqrt(n)": x.std(ddof=1) / np.sqrt(n),
                     "skew of means": stats.skew(means)})
    return pd.DataFrame(rows)


def plot_clt(df, reps=5000):
    x = sample().people_ha.values
    rng = np.random.default_rng(SEED)
    fig, axs = plt.subplots(1, 5, figsize=(15, 3.4))
    axs[0].hist(x, bins=40, color="#999999"); axs[0].set_title(f"population (skew {stats.skew(x):.2f})", fontsize=9, loc="left")
    for ax, n in zip(axs[1:], SIZES):
        m = rng.choice(x, size=(reps, n), replace=True).mean(axis=1)
        ax.hist(m, bins=40, density=True, color="#d73027", alpha=0.7)
        se = x.std(ddof=1) / np.sqrt(n); g = np.linspace(max(0, x.mean() - 4 * se), x.mean() + 4 * se, 300)
        ax.plot(g, stats.norm.pdf(g, x.mean(), se), color="#000", lw=1)
        ax.set_title(f"means of n = {n}", fontsize=9, loc="left"); ax.set_yticks([])
    axs[0].set_xlabel("people per hectare")
    fig.suptitle("The central limit theorem: population density is far from normal, yet averages of larger samples "
                 "become normal and narrow as σ/√n (black curve)", x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    return fig


# PART 5. How sure? Confidence intervals and the bootstrap -------------------------------------
def difference_table(boot=5000):
    d = sample(); a = d[d.cover == "built"].lst.values; b = d[d.cover == "trees"].lst.values
    diff = a.mean() - b.mean()
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    rng = np.random.default_rng(SEED)
    bd = np.array([rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(boot)])
    return pd.DataFrame([{"quantity": "mean LST, built minus trees (°C)", "estimate": diff,
                          "95 % CI (normal)": f"{diff - 1.96 * se:.2f} to {diff + 1.96 * se:.2f}",
                          "95 % CI (bootstrap)": f"{np.percentile(bd, 2.5):.2f} to {np.percentile(bd, 97.5):.2f}"}])


# PART 6. Tests: t, Mann-Whitney and Kolmogorov-Smirnov ----------------------------------------
def tests_table():
    d = sample(); rows = []
    for a, b in [("built", "trees"), ("crops", "grass"), ("crops", "trees")]:
        x = d[d.cover == a].lst; y = d[d.cover == b].lst
        t = stats.ttest_ind(x, y, equal_var=False); u = stats.mannwhitneyu(x, y); k = stats.ks_2samp(x, y)
        rows.append({"comparison": f"{a} vs {b}", "mean difference (°C)": x.mean() - y.mean(),
                     "Welch t p": t.pvalue, "Mann-Whitney p": u.pvalue, "KS D": k.statistic, "KS p": k.pvalue})
    return pd.DataFrame(rows)


def plot_ecdf(df):
    d = sample()
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, (a, b) in zip(axs, [("built", "trees"), ("crops", "grass")]):
        xa = np.sort(d[d.cover == a].lst); xb = np.sort(d[d.cover == b].lst)
        for x, c in [(xa, a), (xb, b)]:
            ax.step(x, np.arange(1, len(x) + 1) / len(x), where="post", color=COLOURS[c], lw=2, label=c)
        grid = np.sort(np.concatenate([xa, xb]))
        fa = np.searchsorted(xa, grid, side="right") / len(xa); fb = np.searchsorted(xb, grid, side="right") / len(xb)
        i = np.argmax(np.abs(fa - fb))
        ax.vlines(grid[i], min(fa[i], fb[i]), max(fa[i], fb[i]), color="#000", lw=2)
        ax.text(grid[i], (fa[i] + fb[i]) / 2, f"  D = {abs(fa[i] - fb[i]):.2f}", va="center", fontsize=9)
        ax.set_xlabel("LST (°C)"); ax.legend(fontsize=8, loc="lower right"); ax.grid(alpha=0.3)
    axs[0].set_ylabel("share of pixels at or below")
    fig.suptitle("Kolmogorov-Smirnov: D is the largest vertical gap between two cumulative distributions",
                 x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    return fig


# PART 7. Regression: does greenery cool, and how much? -----------------------------------------
def regression_table():
    import statsmodels.formula.api as smf
    d = sample()
    m1 = smf.ols("lst ~ greenery", d).fit()
    m2 = smf.ols("lst ~ greenery + np.log1p(people_ha)", d).fit()
    rows = []
    for name, m in [("LST ~ greenery", m1), ("LST ~ greenery + log(1 + people/ha)", m2)]:
        ci = m.conf_int()
        for term in m.params.index:
            rows.append({"model": name, "term": term, "coefficient": m.params[term],
                         "95 % CI": f"{ci.loc[term, 0]:.2f} to {ci.loc[term, 1]:.2f}", "p": m.pvalues[term],
                         "R²": m.rsquared, "RMSE (°C)": np.sqrt(m.mse_resid)})
    return pd.DataFrame(rows)


def plot_regression(df):
    import statsmodels.formula.api as smf
    d = sample(); m = smf.ols("lst ~ greenery", d).fit()
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.3))
    for c in ORDER:
        s = d[d.cover == c]; axs[0].scatter(s.greenery, s.lst, s=5, alpha=0.4, color=COLOURS[c], label=c)
    g = np.linspace(0, d.greenery.max(), 50)
    axs[0].plot(g, m.params["Intercept"] + m.params["greenery"] * g, color="#000", lw=2)
    axs[0].set_xlabel("greenery (trees + grass probability, 300 m)"); axs[0].set_ylabel("LST (°C)"); axs[0].legend(fontsize=7, markerscale=2)
    axs[0].set_title(f"Fit: {m.params['greenery'] / 10:.2f} °C per +0.1 greenery, R² = {m.rsquared:.2f}", loc="left", fontsize=9)
    axs[1].scatter(m.fittedvalues, m.resid, s=4, alpha=0.4, color="#555"); axs[1].axhline(0, color="#d73027")
    axs[1].set_xlabel("fitted LST (°C)"); axs[1].set_ylabel("residual (°C)")
    axs[1].set_title("Residuals against fitted: look for funnels and curves", loc="left", fontsize=9)
    stats.probplot(m.resid, plot=axs[2]); axs[2].get_lines()[0].set_markersize(2)
    axs[2].set_title("")                                      # scipy adds its own centred title
    axs[2].set_title("Q-Q plot: residuals against a normal distribution", loc="left", fontsize=9)
    axs[2].set_xlabel("normal quantiles"); axs[2].set_ylabel("residual quantiles (°C)")
    fig.suptitle("Regression of LST on greenery, and the two plots to check before believing it",
                 x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    return fig


def products():
    return [
        {"kind": "table", "name": "ch70-summary", "data": summary_table, "floatfmt": ("", "", ".0f", ".2f", ".2f", ".2f", ".2f", ".2f", ".2f"),
         "caption": "Central tendency and spread of dry-season LST (°C) by land cover. MAD is scaled to match the SD for normal data."},
        {"kind": "chart", "name": "ch70-distributions", "data": summary_table, "plot": plot_distributions,
         "caption": "Density of LST by land cover, with mean (solid) and median (dotted)."},
        {"kind": "chart", "name": "ch70-outliers", "data": outlier_table, "plot": plot_outliers,
         "caption": "Box plots with IQR fences, and the z-score of every sampled pixel."},
        {"kind": "table", "name": "ch70-outlier-table", "data": outlier_table, "floatfmt": ("", ".1f", ".1f", ".0f", ".0f", ".0f"),
         "caption": "How many pixels each rule calls unusual."},
        {"kind": "chart", "name": "ch70-clt", "data": clt_table, "plot": plot_clt,
         "caption": "The central limit theorem with real data: means of repeated samples of population density."},
        {"kind": "table", "name": "ch70-clt-table", "data": clt_table, "floatfmt": (".0f", ".3f", ".3f", ".2f"),
         "caption": "The spread of the sample means against the theoretical standard error σ/√n."},
        {"kind": "table", "name": "ch70-ci", "data": difference_table, "floatfmt": ("", ".2f", "", ""),
         "caption": "How much hotter built-up land is, with two 95 % confidence intervals."},
        {"kind": "table", "name": "ch70-tests", "data": tests_table, "floatfmt": ("", ".2f", ".2g", ".2g", ".2f", ".2g"),
         "caption": "Welch's t-test, the Mann-Whitney U test and the two-sample Kolmogorov-Smirnov test."},
        {"kind": "chart", "name": "ch70-ecdf", "data": tests_table, "plot": plot_ecdf,
         "caption": "Empirical cumulative distributions and the KS statistic D."},
        {"kind": "table", "name": "ch70-regression", "data": regression_table, "floatfmt": ("", "", ".3f", "", ".2g", ".2f", ".2f"),
         "caption": "Ordinary least squares: LST on greenery, then adding population density."},
        {"kind": "chart", "name": "ch70-regression-chart", "data": regression_table, "plot": plot_regression,
         "caption": "The fit, the residuals against fitted values, and the Q-Q plot."},
    ]


if __name__ == "__main__":
    if not CSV.exists():                              # Earth Engine is only needed to draw the sample
        import ee, json
        k = os.path.expanduser(os.environ.get("BOOK_EE_KEY", "~/.config/fullstack-rs/ee-key.json")); info = json.load(open(k))
        ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], k), project=info.get("project_id"))
    print(summary_table().round(2)); print(outlier_table()); print(clt_table().round(3)); print(difference_table())
    print(tests_table().round(4)); print(regression_table().round(3))
