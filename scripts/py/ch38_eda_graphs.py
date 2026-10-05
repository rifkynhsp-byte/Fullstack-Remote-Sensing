#| title: Exploratory data analysis and graphs that explain themselves (Python)
#| description: One rainfall table, explored step by step, and five graphs shown twice: the common version and a better one.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 38 | Look before you model, and draw so the reader does not have to
ask. The data is the CHIRPS monthly rainfall table from chapter “Data Visualisation That Decides Things” (six
Indonesian cities, 1991-2024), fetched once from Earth Engine.

Each rule below is a pair of panels: left, the graph people usually make;
right, the graph that answers the question. The code for both is here, so
you can see how small the difference in effort is.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ch29_rainfall_charts import monthly_frame   # one Earth Engine request, cached

ORDER = ["Padang", "Pontianak", "Jakarta", "Makassar", "Kupang", "Ambon"]
BLUE, GREY, RED = "#2a78d6", "#b8c0c8", "#c0392b"
MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]


def annual():
    df = monthly_frame()
    return df.groupby(["place", "year"])["rain_mm"].sum().reset_index()


# ---------------------------------------------------------------------------
# Step 1 of any EDA: one table that says what the data is
# ---------------------------------------------------------------------------
def summary_table():
    df = monthly_frame()
    g = df.groupby("place")["rain_mm"]
    out = pd.DataFrame({
        "months": g.size(), "missing": g.apply(lambda s: s.isna().sum()),
        "mean": g.mean(), "sd": g.std(), "min": g.min(),
        "p10": g.quantile(0.1), "median": g.median(), "p90": g.quantile(0.9),
        "max": g.max()}).reindex(ORDER).reset_index()
    return out


# ---------------------------------------------------------------------------
# Rule 1. Show the distribution, not only the average
# ---------------------------------------------------------------------------
def rule1_distribution():
    a = annual()
    fig, (l, r) = plt.subplots(1, 2, figsize=(10, 3.6))
    means = a.groupby("place")["rain_mm"].mean().reindex(ORDER)
    l.bar(ORDER, means, color=GREY)
    l.set_title("Common: mean annual rainfall", loc="left", fontsize=10)
    l.set_ylabel("mm per year")
    rng = np.random.default_rng(0)
    for i, c in enumerate(ORDER):
        v = a.loc[a.place == c, "rain_mm"]
        r.scatter(np.full(len(v), i) + rng.uniform(-0.18, 0.18, len(v)), v, s=10,
                  color=BLUE, alpha=0.55, lw=0)
        r.plot([i - 0.3, i + 0.3], [v.median()] * 2, color="black", lw=1.5)
    r.set_xticks(range(len(ORDER)), ORDER)
    r.set_title("Better: every year, with the median", loc="left", fontsize=10)
    for ax in (l, r):
        ax.tick_params(axis="x", labelsize=8)
    fig.suptitle("Rule 1. A bar of means hides how much the years differ",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Rule 2. Do not average the variation away
# ---------------------------------------------------------------------------
def rule2_variation():
    df = monthly_frame()
    d = df[df.place == "Kupang"]
    fig, (l, r) = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    l.plot(range(1, 13), d.groupby("month")["rain_mm"].mean(), color=GREY, lw=2.5)
    l.set_title("Common: the average year", loc="left", fontsize=10)
    for _, y in d.groupby("year"):
        r.plot(y["month"], y["rain_mm"], color=GREY, lw=0.6, alpha=0.6)
    q = d.groupby("month")["rain_mm"].quantile([0.1, 0.5, 0.9]).unstack()
    r.fill_between(range(1, 13), q[0.1], q[0.9], color=BLUE, alpha=0.2,
                   label="10th to 90th percentile")
    r.plot(range(1, 13), q[0.5], color=BLUE, lw=2.2, label="median")
    r.set_title("Better: every year faint, the typical range shaded", loc="left",
                fontsize=10)
    r.legend(frameon=False, fontsize=8)
    for ax in (l, r):
        ax.set_xticks(range(1, 13), MONTHS)
    l.set_ylabel("Kupang rainfall (mm per month)")
    fig.suptitle("Rule 2. The average year never happened; show the range",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Rule 3. Honest axes
# ---------------------------------------------------------------------------
def rule3_axes():
    a = annual()
    means = a.groupby("place")["rain_mm"].mean().reindex(["Jakarta", "Makassar"])
    fig, (l, r) = plt.subplots(1, 2, figsize=(10, 3.4))
    l.bar(means.index, means, color=[GREY, RED])
    l.set_ylim(means.min() * 0.97, means.max() * 1.01)
    l.set_title("Common: the axis starts near the smaller bar", loc="left", fontsize=10)
    r.bar(means.index, means, color=[GREY, RED])
    r.set_ylim(0, means.max() * 1.1)
    for x, v in enumerate(means):
        r.text(x, v, f"{v:,.0f} mm", ha="center", va="bottom", fontsize=9)
    diff = (means.iloc[1] / means.iloc[0] - 1) * 100
    r.set_title(f"Better: bars start at zero; the gap is {diff:.0f} %", loc="left",
                fontsize=10)
    fig.suptitle("Rule 3. A bar's length is its message; do not cut it",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Rule 4. Enough, not too much
# ---------------------------------------------------------------------------
def rule4_enough():
    df = monthly_frame()
    clim = df.groupby(["place", "month"])["rain_mm"].median().unstack(0)[ORDER]
    fig, (l, r) = plt.subplots(1, 2, figsize=(10, 3.8))
    colours = plt.cm.jet(np.linspace(0, 1, len(ORDER)))
    for c, col in zip(ORDER, colours):
        l.plot(clim.index, clim[c], marker="o", color=col, label=c)
    l.legend(fontsize=7, ncol=2)
    l.grid(True, color="#999999")
    l.set_title("Common: six colours, a legend to decode", loc="left", fontsize=10)
    for c in ORDER:
        hl = c == "Ambon"
        r.plot(clim.index, clim[c], color=RED if hl else GREY, lw=2.4 if hl else 1)
        r.text(12.2, clim[c].iloc[-1], c, color=RED if hl else "#6b7680", fontsize=8,
               va="center", fontweight="bold" if hl else "normal")
    r.set_xlim(1, 13.5)
    r.set_title("Better: grey context, one story in colour, direct labels",
                loc="left", fontsize=10)
    for ax in (l, r):
        ax.set_xticks(range(1, 13), MONTHS)
        ax.set_ylabel("median mm per month")
    fig.suptitle("Rule 4. Highlight what matters; let the rest be context",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Rule 5. A graph that explains itself
# ---------------------------------------------------------------------------
def rule5_self_explanatory():
    a = annual()
    k = a[a.place == "Kupang"].sort_values("year")
    fig, (l, r) = plt.subplots(1, 2, figsize=(10, 3.6))
    l.plot(k["year"], k["rain_mm"])
    l.set_title("Kupang", fontsize=10)
    med = k["rain_mm"].median()
    r.plot(k["year"], k["rain_mm"], color=BLUE, lw=1.5)
    r.axhline(med, color=GREY, ls="--", lw=1)
    r.text(k["year"].min(), med, " median", va="bottom", fontsize=8, color="#6b7680")
    driest = k.nsmallest(2, "rain_mm")
    for _, row in driest.iterrows():
        r.annotate(f"{int(row.year)}: {row.rain_mm:,.0f} mm", (row.year, row.rain_mm),
                   xytext=(0, -14), textcoords="offset points", ha="center",
                   fontsize=8, color=RED)
        r.plot(row.year, row.rain_mm, "o", color=RED)
    r.set_ylabel("Annual rainfall (mm)")
    r.set_title(f"Kupang's two driest years were {int(driest.year.iloc[0])} and "
                f"{int(driest.year.iloc[1])}", loc="left", fontsize=10)
    r.text(0, -0.2, "CHIRPS v2, 10 km around the city centre, 1991-2024",
           transform=r.transAxes, fontsize=7, color="#6b7680")
    fig.suptitle("Rule 5. The title states the finding; units, source and labels "
                 "remove the guessing", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# EDA: which cities rise and fall together?
# ---------------------------------------------------------------------------
def correlation_figure():
    df = monthly_frame()
    wide = df.pivot_table(index=["year", "month"], columns="place", values="rain_mm")[ORDER]
    anom = wide - wide.groupby(level="month").transform("mean")    # remove the season
    corr = anom.corr()
    fig, ax = plt.subplots(figsize=(5.2, 4.4))
    im = ax.imshow(corr, cmap="RdBu", vmin=-1, vmax=1)
    ax.set_xticks(range(len(ORDER)), ORDER, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(ORDER)), ORDER, fontsize=8)
    for i in range(len(ORDER)):
        for j in range(len(ORDER)):
            v = corr.iloc[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7,
                    color="white" if abs(v) > 0.6 else "black")
    fig.colorbar(im, ax=ax, shrink=0.8, label="correlation of monthly anomalies")
    ax.set_title("Which cities have wet and dry months together?", loc="left", fontsize=10)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Question 4: the rhythm. Season, trend and what is left (STL decomposition)
# ---------------------------------------------------------------------------
def stl_figure(place="Kupang"):
    """Split one city's monthly rainfall into a repeating season, a slow trend and a remainder."""
    from statsmodels.tsa.seasonal import STL
    df = monthly_frame()
    s = (df[df.place == place].assign(date=lambda d: pd.to_datetime(dict(year=d.year, month=d.month, day=1)))
         .set_index("date")["rain_mm"].asfreq("MS"))
    r = STL(np.sqrt(s), period=12, robust=True).fit()          # square root tames the wet-season spikes
    fig, axes = plt.subplots(4, 1, figsize=(9, 7), sharex=True)
    for ax, y, lab, c in zip(axes, [np.sqrt(s), r.seasonal, r.trend, r.resid],
                             ["observed", "season", "trend", "remainder"], ["#444444", BLUE, RED, GREY]):
        ax.plot(y.index, y, color=c, lw=0.9)
        ax.set_ylabel(f"{lab}\n(√mm)", fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    big = r.resid.abs().nlargest(3)
    for d in big.index:
        axes[3].annotate(d.strftime("%b %Y"), (d, r.resid[d]), fontsize=7, xytext=(3, 3), textcoords="offset points")
    share = 1 - r.resid.var() / np.sqrt(s).var()
    fig.suptitle(f"{place}: the season and trend explain {share:.0%} of the month-to-month variation in √rainfall",
                 x=0.01, ha="left", fontweight="bold", fontsize=10)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Relationships: does the Pacific decide the dry season? (ENSO, Niño 3.4)
# ---------------------------------------------------------------------------
NINO_URL = "https://psl.noaa.gov/data/correlation/nina34.anom.data"
NINO_CSV = Path(__file__).resolve().parents[2] / "data" / "ch38_nino34.csv" if "__file__" in globals() else Path("data/ch38_nino34.csv")


def nino34():
    """Monthly Niño 3.4 SST anomaly (NOAA PSL, ERSST), saved once to data/ for reproducibility."""
    if NINO_CSV.exists():
        return pd.read_csv(NINO_CSV)
    import requests
    txt = requests.get(NINO_URL, timeout=60, headers={"User-Agent": "fullstack-remote-sensing-book"}).text
    rows = []
    for line in txt.splitlines()[1:]:
        parts = line.split()
        if len(parts) == 13 and parts[0].isdigit():
            rows += [{"year": int(parts[0]), "month": m + 1, "nino34": float(v)} for m, v in enumerate(parts[1:]) if float(v) > -99]
    d = pd.DataFrame(rows)
    NINO_CSV.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(NINO_CSV, index=False)
    return d


DRY = [7, 8, 9, 10]          # July-October: the dry season south of the equator, and the ENSO peak build-up


def enso_frame():
    df = monthly_frame()
    rain = df[df.month.isin(DRY)].groupby(["place", "year"]).rain_mm.sum().reset_index()
    rain["anomaly_pct"] = rain.groupby("place").rain_mm.transform(lambda x: 100 * (x / x.mean() - 1))
    n = nino34()
    n = n[n.month.isin(DRY)].groupby("year").nino34.mean().reset_index()
    return rain.merge(n, on="year")


def enso_table():
    from scipy import stats
    d = enso_frame()
    rows = []
    for p in ORDER:
        g = d[d.place == p]
        r, pv = stats.spearmanr(g.nino34, g.anomaly_pct)
        el, la = g[g.nino34 >= 0.5], g[g.nino34 <= -0.5]    # the usual ±0.5 °C ENSO thresholds
        rows.append({"city": p, "Spearman r": r, "p": pv, "El Niño years (%)": el.anomaly_pct.median(),
                     "La Niña years (%)": la.anomaly_pct.median(), "n El Niño": len(el), "n La Niña": len(la)})
    return pd.DataFrame(rows)


def enso_figure():
    d = enso_frame()
    t = enso_table().set_index("city")
    fig, axes = plt.subplots(2, 3, figsize=(10, 6), sharex=True, sharey=True)
    for ax, p in zip(axes.flat, ORDER):
        g = d[d.place == p]
        c = np.where(g.nino34 >= 0.5, RED, np.where(g.nino34 <= -0.5, BLUE, GREY))
        ax.scatter(g.nino34, g.anomaly_pct, c=c, s=18)
        ax.axhline(0, color="k", lw=0.5); ax.axvline(0, color="k", lw=0.5)
        for _, row in g[(g.nino34 >= 1.5)].iterrows():
            ax.annotate(int(row.year), (row.nino34, row.anomaly_pct), fontsize=6.5, xytext=(2, 2), textcoords="offset points")
        ax.set_title(f"{p}  (r = {t.loc[p, 'Spearman r']:.2f})", fontsize=9, loc="left")
        ax.spines[["top", "right"]].set_visible(False)
    for ax in axes[1]:
        ax.set_xlabel("Niño 3.4 anomaly, Jul-Oct (°C)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Jul-Oct rain vs normal (%)")
    strongest = t["Spearman r"].idxmin()
    fig.suptitle(f"El Niño dries July to October in all six cities, most strongly in {strongest}",
                 x=0.01, ha="left", fontweight="bold", fontsize=10)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Question 3: values that cannot be right. Daily satellite LST, raw and quality-filtered
# ---------------------------------------------------------------------------
def lst_frame():
    """MODIS Terra daily daytime LST at one Bandung pixel, 2023, with its quality flags."""
    import ee
    pt = ee.Geometry.Point([107.6098, -6.9147])
    col = ee.ImageCollection("MODIS/061/MOD11A1").filterDate("2023-01-01", "2024-01-01").select(["LST_Day_1km", "QC_Day"])
    fc = col.map(lambda im: ee.Feature(None, im.reduceRegion(ee.Reducer.first(), pt, 1000)).set("date", im.date().format("YYYY-MM-dd")))
    d = pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]]).dropna(subset=["LST_Day_1km"])
    d["lst_c"] = d.LST_Day_1km * 0.02 - 273.15
    qc = d.QC_Day.astype(int)
    # Bits 0-1: 00 good, 01 produced but check the other bits. In the humid tropics almost every
    # day is 01, so the useful split is bits 6-7, the estimated LST error: 00 <= 1 K, 01 <= 2 K.
    d["good"] = ((qc & 3) <= 1) & (((qc // 64) & 3) <= 1)
    d["date"] = pd.to_datetime(d.date)
    med = d.lst_c.rolling(15, center=True, min_periods=5).median()
    mad = (d.lst_c - med).abs().rolling(15, center=True, min_periods=5).median()
    d["robust_z"] = (d.lst_c - med) / (1.4826 * mad)
    return d


def lst_figure():
    d = lst_frame()
    flag = d.robust_z.abs() > 3
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8), gridspec_kw={"width_ratios": [2.2, 1]})
    a1.scatter(d.date[~d.good], d.lst_c[~d.good], s=10, color=GREY, label=f"error > 2 K or not produced ({(~d.good).sum()} days)")
    a1.scatter(d.date[d.good], d.lst_c[d.good], s=10, color=BLUE, label=f"error ≤ 2 K ({d.good.sum()} days)")
    a1.scatter(d.date[flag], d.lst_c[flag], s=40, facecolor="none", edgecolor=RED, label=f"robust |z| > 3 ({flag.sum()})")
    a1.set_ylabel("daytime LST (°C)"); a1.legend(frameon=False, fontsize=7.5, loc="lower left")
    a1.set_title("One Bandung pixel, every clear-enough day of 2023", loc="left", fontsize=9)
    bins = np.arange(np.floor(d.lst_c.min()), np.ceil(d.lst_c.max()) + 1, 1)
    a2.hist([d.lst_c[d.good], d.lst_c[~d.good]], bins=bins, color=[BLUE, GREY], stacked=True,
            label=["error ≤ 2 K", "error > 2 K"])
    a2.set_xlabel("°C"); a2.legend(frameon=False, fontsize=7.5)
    a2.set_title("Where the uncertain days sit", loc="left", fontsize=9)
    for a in (a1, a2):
        a.spines[["top", "right"]].set_visible(False)
    passed = int((flag & d.good).sum())
    fig.suptitle(f"The quality flag keeps {d.good.mean():.0%} of the days, yet {passed} of the {int(flag.sum())} cold outliers pass it",
                 x=0.01, ha="left", fontweight="bold", fontsize=10)
    fig.tight_layout()
    return fig


def products():
    return [
        {"kind": "table", "name": "ch38-summary", "data": summary_table,
         "floatfmt": ("", ".0f", ".0f", ".0f", ".0f", ".0f", ".0f", ".0f", ".0f", ".0f"),
         "caption": "Step one of any exploration: what the data is, how much is missing, "
                    "and how wide the range is (monthly rainfall, mm)."},
        {"kind": "figure", "name": "ch38-rule1", "figure": rule1_distribution,
         "caption": "The bar chart says the cities differ in average. The dot plot also "
                    "shows that a single city's years differ by more than that."},
        {"kind": "figure", "name": "ch38-rule2", "figure": rule2_variation,
         "caption": "Kupang's average year is smooth. Real years are not; the band says "
                    "how far a normal year can stray."},
        {"kind": "figure", "name": "ch38-rule3", "figure": rule3_axes,
         "caption": "The same two numbers. Cutting the axis makes a modest gap look huge."},
        {"kind": "figure", "name": "ch38-rule4", "figure": rule4_enough,
         "caption": "Six lines in six colours ask the reader to work. Grey context and one "
                    "highlighted city tell a story: Ambon's wet season falls in the middle "
                    "of the year, when most of the other cities are dry."},
        {"kind": "figure", "name": "ch38-rule5", "figure": rule5_self_explanatory,
         "caption": "Left needs its author standing next to it. Right does not."},
        {"kind": "figure", "name": "ch38-correlation", "figure": correlation_figure,
         "caption": "Correlation of monthly rainfall anomalies (season removed). Cities "
                    "in the same rainfall regime move together (Makassar and Kupang 0.44, "
                    "Padang and Pontianak 0.38), but no pair passes 0.5: most of each "
                    "city's wet and dry months are its own."},
        {"kind": "figure", "name": "ch38-stl", "figure": stl_figure,
         "caption": "STL decomposition of Kupang's monthly rainfall (square-root scale): a fixed season, a slow trend, and the remainder where unusual months stand out."},
        {"kind": "table", "name": "ch38-enso", "data": enso_table, "floatfmt": ("", ".2f", ".2g", ".0f", ".0f", ".0f", ".0f"),
         "caption": "July-October rainfall against the Niño 3.4 sea-surface temperature anomaly, 1991-2024: rank correlation, and the median departure from normal in El Niño (≥ +0.5 °C) and La Niña (≤ -0.5 °C) years."},
        {"kind": "figure", "name": "ch38-enso-chart", "figure": enso_figure,
         "caption": "One panel per city, same axes. Red: El Niño years; blue: La Niña years."},
        {"kind": "figure", "name": "ch38-lst-outliers", "figure": lst_figure,
         "caption": "MODIS Terra daily LST at one pixel in central Bandung, with the product's own quality flag and a robust (median and MAD) outlier rule."},
    ]


if __name__ == "__main__":
    import ee
    ee.Initialize()
    print(summary_table())
