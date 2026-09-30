#| title: Exploratory data analysis and graphs that explain themselves (Python)
#| description: One rainfall table, explored step by step, and five graphs shown twice: the common version and a better one.

"""
CHAPTER 38 | Look before you model, and draw so the reader does not have to
ask. The data is the CHIRPS monthly rainfall table from Chapter 29 (six
Indonesian cities, 1991-2024), fetched once from Earth Engine.

Each rule below is a pair of panels: left, the graph people usually make;
right, the graph that answers the question. The code for both is here, so
you can see how small the difference in effort is.
"""

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
    ]


if __name__ == "__main__":
    import ee
    ee.Initialize()
    print(summary_table())
