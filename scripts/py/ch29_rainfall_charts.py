#| title: One rainfall table, charted badly and well (Python)
#| description: The same CHIRPS monthly rainfall for six Indonesian cities as the JavaScript tab: a spaghetti chart, small multiples with a range band, a strip plot of dry years, and an interactive heatmap.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 29 | Earth Engine makes one tidy table: monthly CHIRPS rainfall,
1991-2024, for six cities that sit in different rainfall regimes. Everything
else in this listing is a choice about how to show that table.

    pip install earthengine-api pandas matplotlib plotly
"""

import ee
import matplotlib.pyplot as plt
import numpy as np

# Six cities, west to east, chosen because their rainfall seasons differ.
PLACES = {"Padang": (100.36, -0.95), "Pontianak": (109.34, -0.03),
          "Jakarta": (106.83, -6.20), "Makassar": (119.44, -5.14),
          "Kupang": (123.61, -10.17), "Ambon": (128.18, -3.70)}
ORDER = list(PLACES)
FIRST, LAST = 1991, 2024
# Years with a known dry driver: El Nino in 1997, 2015 and 2023; a strong
# positive Indian Ocean Dipole in 2019 (with only a weak El Nino).
EL_NINO = {1997, 2015, 2019, 2023}

cities = ee.FeatureCollection([
    ee.Feature(ee.Geometry.Point(xy).buffer(10000), {"place": name})
    for name, xy in PLACES.items()])
pentads = ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD").select("precipitation")
start = ee.Date(f"{FIRST}-01-01")


def month_total(i):
    """Rainfall for one calendar month: the sum of its six pentads (mm)."""
    d = start.advance(i, "month")
    return (pentads.filterDate(d, d.advance(1, "month")).sum()
            .set({"year": d.get("year"), "month": d.get("month")}))


months = ee.ImageCollection(
    ee.List.sequence(0, (LAST - FIRST + 1) * 12 - 1).map(month_total))


def city_means(img):
    # 5566 m is CHIRPS's native pixel; each city is a 10 km circle.
    return (img.reduceRegions(collection=cities, reducer=ee.Reducer.mean(), scale=5566)
            .map(lambda f: f.set({"year": img.get("year"), "month": img.get("month"),
                                  "rain_mm": f.get("mean")}).setGeometry(None)))


monthly = months.map(city_means).flatten().select(["place", "year", "month", "rain_mm"])


# ---------------------------------------------------------------------------
# 1. The chart most people make first
# ---------------------------------------------------------------------------
def plot_spaghetti(df):
    """Every city on one axis, rainbow colours, legend off to the side."""
    clim = df.groupby(["place", "month"])["rain_mm"].mean().unstack(0)
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    clim.plot(ax=ax, colormap="jet", lw=1.5, marker="o", ms=3)
    ax.grid(True, color="#888", lw=0.8)
    ax.set_xticks(range(1, 13))
    ax.set_ylabel("mm")
    ax.set_title("Rainfall", loc="left")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=7)
    return fig


# ---------------------------------------------------------------------------
# 2. The same numbers as small multiples, with the spread between years
# ---------------------------------------------------------------------------
def plot_small_multiples(df):
    """One panel per city, same axes; median line and the 10-90 % range."""
    order = ["Padang", "Pontianak", "Jakarta", "Makassar", "Kupang", "Ambon"]
    q = (df.groupby(["place", "month"])["rain_mm"]
         .quantile([0.1, 0.5, 0.9]).unstack())
    fig, axes = plt.subplots(2, 3, figsize=(7.2, 4.4), sharex=True, sharey=True)
    for ax, city in zip(axes.flat, order):
        # Every other city in pale grey behind, so each panel keeps its context.
        for other in order:
            if other != city:
                ax.plot(q.loc[other].index, q.loc[other][0.5], color="#e1e5e9", lw=0.7)
        c = q.loc[city]
        ax.fill_between(c.index, c[0.1], c[0.9], color="#2a78d6", alpha=0.18, lw=0)
        ax.plot(c.index, c[0.5], color="#2a78d6", lw=2)
        ax.set_title(city, loc="left", fontsize=9, fontweight="bold")
        ax.set_xticks([1, 4, 7, 10], ["Jan", "Apr", "Jul", "Oct"])
        ax.grid(axis="y", color="#e4e7eb", lw=0.6)
        ax.set_ylim(0, q[0.9].max() * 1.03)
    for ax in axes[:, 0]:
        ax.set_ylabel("Rainfall (mm/month)")
    fig.suptitle("Ambon's wet season is in the middle of the year; Kupang's almost "
                 "stops raining", x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.text(0.01, -0.02, "Line: median month, 1991-2024. Band: 10th to 90th "
             "percentile of the 34 years. Grey: the other five cities. CHIRPS v2.",
             fontsize=7, color="#52606d")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 3. A question with a yes/no answer: were the El Nino years dry everywhere?
# ---------------------------------------------------------------------------
def plot_dry_years(df):
    """Annual totals, one dot per year, El Nino years coloured and labelled."""
    order = ["Padang", "Pontianak", "Jakarta", "Makassar", "Kupang", "Ambon"]
    nino = {1997, 2015, 2019, 2023}
    yr = df.groupby(["place", "year"])["rain_mm"].sum().reset_index()
    fig, ax = plt.subplots(figsize=(6.8, 3.6))
    rng = np.random.default_rng(1)
    for i, city in enumerate(order):
        d = yr[yr["place"] == city]
        normal = d[~d["year"].isin(nino)]
        ax.scatter(normal["rain_mm"], i + rng.uniform(-0.12, 0.12, len(normal)),
                   s=14, color="#9aa5b1", alpha=0.7, lw=0)
        dry = d[d["year"].isin(nino)]
        ax.scatter(dry["rain_mm"], np.full(len(dry), i), s=30, color="#d55e00",
                   edgecolor="white", lw=0.8, zorder=3)
        # Alternate labels above and below so close years do not collide.
        for k, (_, r) in enumerate(dry.sort_values("rain_mm").iterrows()):
            ax.annotate("'" + str(r["year"])[2:], (r["rain_mm"], i),
                        xytext=(0, 6 if k % 2 == 0 else -6), textcoords="offset points",
                        ha="center", va="bottom" if k % 2 == 0 else "top",
                        fontsize=6.5, color="#b04600")
        ax.plot([d["rain_mm"].median()] * 2, [i - 0.25, i + 0.25], color="#1f2933", lw=1.2)
    ax.set_yticks(range(len(order)), order)
    ax.invert_yaxis()
    ax.set_xlabel("Annual rainfall (mm)")
    ax.grid(axis="x", color="#e4e7eb", lw=0.6)
    ax.set_title("Dry-driver years (orange): 22 of 24 below the city's median",
                 loc="left", fontsize=10)
    ax.text(0, -0.2, "Grey: other years, 1991-2024. Black tick: median year. CHIRPS v2.",
            transform=ax.transAxes, fontsize=7, color="#52606d")
    return fig


# ---------------------------------------------------------------------------
# 4. Interactive: every month of every year, one city at a time
# ---------------------------------------------------------------------------
def heatmap_html(path):
    """Year by month heatmap with a city menu and hover values (plotly)."""
    import plotly.graph_objects as go
    df = monthly_frame()
    months_lbl = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
                  "Oct", "Nov", "Dec"]
    fig = go.Figure()
    zmax = float(df["rain_mm"].quantile(0.99))
    for i, city in enumerate(ORDER):
        grid = df[df["place"] == city].pivot(index="year", columns="month",
                                             values="rain_mm")
        fig.add_trace(go.Heatmap(
            z=grid.values, x=months_lbl, y=grid.index, visible=(i == 0),
            colorscale="Blues", zmin=0, zmax=zmax, xgap=1, ygap=1,
            colorbar=dict(title="mm/month"),
            hovertemplate=city + ", %{x} %{y}: %{z:.0f} mm<extra></extra>"))
    buttons = [dict(label=c, method="update",
                    args=[{"visible": [j == i for j in range(len(ORDER))]},
                          {"title.text": f"{c}: monthly rainfall, {FIRST}-{LAST} (CHIRPS)"}])
               for i, c in enumerate(ORDER)]
    fig.update_layout(
        title=dict(text=f"{ORDER[0]}: monthly rainfall, {FIRST}-{LAST} (CHIRPS)", x=0.01),
        updatemenus=[dict(buttons=buttons, x=1, xanchor="right", y=1.12)],
        yaxis=dict(autorange="reversed", dtick=3), height=560,
        margin=dict(l=50, r=20, t=80, b=40), plot_bgcolor="white",
        font=dict(family="sans-serif", size=12))
    fig.write_html(path, include_plotlyjs="cdn", full_html=True)


_CACHE = {}


def monthly_frame():
    """The monthly table as a pandas frame, fetched once."""
    import pandas as pd
    if "df" not in _CACHE:
        info = monthly.getInfo()
        _CACHE["df"] = pd.DataFrame([f["properties"] for f in info["features"]])
    return _CACHE["df"].copy()


# ---------------------------------------------------------------------------
# A chart with its uncertainty: is annual rainfall trending?
# ---------------------------------------------------------------------------
def trend_table():
    """Theil-Sen slope of annual totals (robust to wet outliers) with a 90 % interval, and Kendall's tau."""
    import pandas as pd
    from scipy import stats
    df = monthly_frame()
    ann = df.groupby(["place", "year"]).rain_mm.sum().reset_index()
    ann = ann[ann.year <= LAST]
    rows = []
    for p in ORDER:
        g = ann[ann.place == p]
        slope, inter, lo, hi = stats.theilslopes(g.rain_mm, g.year, alpha=0.90)
        tau, pv = stats.kendalltau(g.year, g.rain_mm)
        rows.append({"city": p, "mean (mm/yr)": g.rain_mm.mean(), "slope (mm/decade)": 10 * slope,
                     "90% low": 10 * lo, "90% high": 10 * hi, "Kendall tau": tau, "p": pv})
    return pd.DataFrame(rows)


def plot_trends(t):
    fig, ax = plt.subplots(figsize=(7, 3.4))
    y = np.arange(len(t))[::-1]
    sig = (t["90% low"] > 0) | (t["90% high"] < 0)
    ax.hlines(y, t["90% low"], t["90% high"], color=np.where(sig, "#c0392b", "#9aa5b1"), lw=3)
    ax.scatter(t["slope (mm/decade)"], y, color=np.where(sig, "#c0392b", "#555555"), zorder=3)
    ax.axvline(0, color="k", lw=0.8)
    ax.set_yticks(y, t.city); ax.set_xlabel("change in annual rainfall, 1991-2024 (mm per decade, 90 % interval)")
    ax.spines[["top", "right"]].set_visible(False)
    n = int(sig.sum())
    ax.set_title(f"{n} of {len(t)} cities show a trend whose 90 % interval excludes zero", loc="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# A chart that decides: if El Nino is forecast, how likely is a failed dry season?
# ---------------------------------------------------------------------------
def risk_table():
    """Share of years in which July-October rain fell below half of normal, El Nino years against the rest."""
    import pandas as pd
    from ch38_eda_graphs import enso_frame
    d = enso_frame()
    rows = []
    for p in ORDER:
        g = d[d.place == p]
        el, other = g[g.nino34 >= 0.5], g[g.nino34 < 0.5]
        rows.append({"city": p, "El Niño years": len(el), "below half of normal in El Niño years (%)": 100 * (el.anomaly_pct < -50).mean(),
                     "other years": len(other), "below half of normal in other years (%)": 100 * (other.anomaly_pct < -50).mean()})
    return pd.DataFrame(rows)


def plot_risk(t):
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    x = np.arange(len(t))
    ax.bar(x - 0.2, t["below half of normal in other years (%)"], 0.4, color="#9aa5b1", label="other years")
    ax.bar(x + 0.2, t["below half of normal in El Niño years (%)"], 0.4, color="#c0392b", label="El Niño years (Niño 3.4 ≥ +0.5 °C)")
    for i, r in t.iterrows():
        ax.text(i + 0.2, r["below half of normal in El Niño years (%)"] + 2, f'{r["below half of normal in El Niño years (%)"]:.0f}%', ha="center", fontsize=8)
    ax.set_xticks(x, t.city); ax.set_ylabel("years with Jul-Oct rain\nbelow half of normal (%)"); ax.set_ylim(0, 100)
    ax.legend(frameon=False, fontsize=8, loc="upper left"); ax.spines[["top", "right"]].set_visible(False)
    top = t.loc[t["below half of normal in El Niño years (%)"].idxmax()]
    ax.set_title(f"If El Niño is declared: in {top.city}, {top['below half of normal in El Niño years (%)']:.0f} % of such years had a failed dry season",
                 loc="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    return fig


def products():
    return [
        {"kind": "chart", "name": "ch29-spaghetti", "data": monthly_frame,
         "plot": plot_spaghetti, "live": False,
         "caption": "The first draft: six cities on one axis in rainbow colours. The "
                    "numbers are correct, but it is hard to say which line belongs to "
                    "which city, or what the chart wants you to notice."},
        {"kind": "chart", "name": "ch29-small-multiples", "data": monthly_frame,
         "plot": plot_small_multiples,
         "caption": "The same table as small multiples on shared axes. The band shows "
                    "how much a month varies from year to year, which the averaged "
                    "first draft hid."},
        {"kind": "chart", "name": "ch29-dry-years", "data": monthly_frame,
         "plot": plot_dry_years,
         "caption": "Annual totals for 34 years, one dot per year, built to answer one "
                    "question: were the years with a known dry driver actually dry? "
                    "Orange: El Niño in 1997, 2015 and 2023, a strong positive Indian "
                    "Ocean Dipole in 2019. 22 of the 24 orange dots fall below their "
                    "city's median; Ambon and Kupang in 2023 did not."},
        {"kind": "html", "name": "ch29-rain-heatmap", "build": heatmap_html, "height": 600,
         "caption": "Interactive: pick a city, hover a cell for that month's total. "
                    "Each row is a year, so a dry year shows as a pale row."},
        {"kind": "table", "name": "ch29-trends", "data": trend_table, "floatfmt": ("", ".0f", ".0f", ".0f", ".0f", ".2f", ".2f"),
         "caption": "Theil-Sen trend in annual rainfall, 1991-2024, with a 90 % interval, and Kendall's rank test."},
        {"kind": "chart", "name": "ch29-trends-chart", "data": trend_table, "plot": plot_trends, "live": False,
         "caption": "One dot per city with its interval: the chart says how sure, not only how much."},
        {"kind": "table", "name": "ch29-risk", "data": risk_table, "floatfmt": ("", ".0f", ".0f", ".0f", ".0f"),
         "caption": "How often July-October rainfall fell below half of normal, 1991-2024, in El Niño years and in the others."},
        {"kind": "chart", "name": "ch29-risk-chart", "data": risk_table, "plot": plot_risk, "live": False,
         "caption": "The same numbers drawn for a decision: what to expect when an El Niño is forecast."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(monthly_frame().groupby("place")["rain_mm"].mean() * 12)
