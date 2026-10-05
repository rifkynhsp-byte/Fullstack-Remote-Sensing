#| title: How a spending shock travels through Indonesia's economy (Python)
#| description: Builds the Leontief input-output model for Indonesia from the open WIOD national table, computes output, value-added, employment and import multipliers and the backward and forward linkages of every sector, follows a construction shock round by round, and draws the results as a heatmap, stacked rounds, lollipops, a key-sector quadrant, a radar chart and a dumbbell chart.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 68 | How a spending shock travels through an economy

When the government spends a billion dollars on construction, the builders buy
cement, steel and transport; the cement works buy energy and limestone; each
of those buys from others. Wassily Leontief's input-output model adds up all
those rounds at once with one matrix inverse.

Data: WIOD 2016 release, national input-output table of Indonesia (domestic and
imported flows, 56 industries, million USD, 2000-2014) and the Socio-Economic
Accounts (persons engaged). Open download from DataverseNL, no key:
Timmer, Dietzenbacher, Los, Stehrer and de Vries (2015), doi:10.34894/PJ2M1C.

Environment: pip install pandas numpy matplotlib openpyxl requests
"""

import io
import os
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

DATA = Path(os.environ.get("IO_DATA", "data/io_indonesia")); DATA.mkdir(parents=True, exist_ok=True)
FILES = {"NIOTS.zip": 199099, "SEA.xlsx": 199095}         # DataverseNL file ids, WIOD 2016 release
YEAR, BASE = 2014, 2000
FD = ["CONS_h", "CONS_np", "CONS_g", "GFCF", "INVEN", "EXP"]
SHOCK_SECTOR, SHOCK = "Construction", 1000.0               # USD 1 billion = 1,000 million


def fetch(name):
    f = DATA / name
    if not f.exists():
        f.write_bytes(requests.get(f"https://dataverse.nl/api/access/datafile/{FILES[name]}", timeout=900).content)
    return f


# PART 1. Sectors: 56 WIOD industries grouped into 28 readable ones ----------------------
def group(code):
    c = code.replace("_", "-")
    two = lambda: int(c[1:3]) if c[1:3].isdigit() else -1
    if c.startswith("A01"): return "Crops & livestock"
    if c.startswith("A02"): return "Forestry"
    if c.startswith("A03"): return "Fishing"
    if c.startswith("B"): return "Mining"
    if c.startswith("C"):
        n = two()
        return ("Food & beverages" if n <= 12 else "Textiles & apparel" if n <= 15 else "Wood & paper" if n <= 18 else
                "Petroleum refining" if n == 19 else "Chemicals & pharma" if n <= 21 else "Rubber, plastic & minerals" if n <= 23 else
                "Metals" if n <= 25 else "Electronics & machinery" if n <= 28 else "Vehicles" if n <= 30 else "Other manufacturing")
    if c.startswith("D"): return "Electricity & gas"
    if c.startswith("E"): return "Water & waste"
    if c.startswith("F"): return "Construction"
    if c.startswith("G"): return "Trade"
    if c.startswith("H"): return "Transport"
    if c.startswith("I"): return "Hotels & restaurants"
    if c.startswith("J"): return "Information & communication"
    if c.startswith("K"): return "Finance"
    if c.startswith("L"): return "Real estate"
    if c.startswith("M") or c.startswith("N"): return "Business services"
    if c.startswith("O"): return "Public administration"
    if c.startswith("P"): return "Education"
    if c.startswith("Q"): return "Health"
    return "Other services"


_cache = {}


def table(year=YEAR):
    """Aggregated domestic flows Z, final demand f, output x, value added, imports and jobs."""
    if year in _cache:
        return _cache[year]
    if "raw" not in _cache:
        z = zipfile.ZipFile(fetch("NIOTS.zip"))
        raw = pd.read_excel(io.BytesIO(z.read("IDN_NIOT_nov16.xlsx")), sheet_name="National IO-tables")
        raw = raw[raw.Year.notna()]                       # the first row holds industry descriptions
        num = raw.columns.difference(["Code", "Description", "Origin"])
        raw[num] = raw[num].apply(pd.to_numeric, errors="coerce")
        _cache["raw"] = raw
        sea = pd.read_excel(fetch("SEA.xlsx"), sheet_name="DATA")
        _cache["sea"] = sea[(sea.country == "IDN") & (sea.variable == "EMP")]
    d = _cache["raw"]; d = d[d.Year == year]
    codes = d[d.Origin == "Domestic"].Code.tolist()
    g = pd.Series({c: group(c) for c in codes})
    dom = d[d.Origin == "Domestic"].set_index("Code"); imp = d[d.Origin == "Imports"].set_index("Code")
    Z = dom[codes].T.groupby(g).sum().T.groupby(g).sum()          # rows: supplier, columns: buyer
    f = dom[FD].sum(axis=1).groupby(g).sum()
    x = dom["GO"].groupby(g).sum()
    tot = d[d.Origin == "TOT"].set_index("Code")
    va = tot.loc["VA", codes].groupby(g).sum()
    m = imp[codes].sum(axis=0).groupby(g).sum()                   # imported intermediates bought by each sector
    emp = _cache["sea"].set_index("code")[year]
    jobs = pd.Series({k: v for k, v in emp.items()}).groupby(lambda c: group(str(c))).sum() * 1000   # persons
    order = x.sort_values(ascending=False).index
    t = dict(Z=Z.loc[order, order], f=f[order], x=x[order], va=va[order], m=m[order], jobs=jobs.reindex(order).fillna(0))
    _cache[year] = t
    return t


# PART 2. The Leontief model -------------------------------------------------------------------
def model(year=YEAR):
    t = table(year); x = t["x"].values
    A = t["Z"].values / x                                          # technical coefficients a_ij = z_ij / x_j
    L = np.linalg.inv(np.eye(len(x)) - A)                          # Leontief inverse
    B = t["Z"].values / x[:, None]                                 # allocation coefficients (Ghosh)
    G = np.linalg.inv(np.eye(len(x)) - B)
    out = pd.DataFrame(index=t["x"].index)
    out["output_multiplier"] = L.sum(axis=0)                       # total output per 1 of final demand
    out["va_multiplier"] = (t["va"].values / x) @ L                 # value added generated per 1 of final demand
    out["jobs_per_musd"] = (t["jobs"].values / x) @ L               # persons per USD 1 million of final demand
    out["import_leakage"] = (t["m"].values / x) @ L                 # imported inputs pulled in per 1 of final demand
    out["backward_linkage"] = out.output_multiplier / out.output_multiplier.mean()
    out["forward_linkage"] = G.sum(axis=1) / G.sum(axis=1).mean()
    out["output_busd"] = x / 1000
    return dict(A=pd.DataFrame(A, index=t["x"].index, columns=t["x"].index), L=L, table=out)


def multiplier_table():
    return model()["table"].sort_values("output_multiplier", ascending=False).reset_index(names="sector")


# PART 3. The charts, each with a headline --------------------------------------------------------
def insight(fig, title, subtitle, top=0.86):
    fig.suptitle(title, x=0.01, y=0.985, ha="left", fontsize=10, fontweight="bold")
    fig.text(0.01, 0.985 - 0.32 / fig.get_figheight(), subtitle, fontsize=8, color="#444444", va="top")
    fig.subplots_adjust(top=top)


def heatmap_figure():
    A = model()["A"]
    fig, ax = plt.subplots(figsize=(10, 9))
    im = ax.imshow(A.values, cmap="magma_r", vmin=0, vmax=0.3)
    ax.set_xticks(range(len(A)), A.columns, rotation=90, fontsize=7); ax.set_yticks(range(len(A)), A.index, fontsize=7)
    ax.set_xlabel("buying sector (column)"); ax.set_ylabel("supplying sector (row)")
    fig.colorbar(im, ax=ax, shrink=0.7, label="USD of input per USD of the buyer's output")
    off = A.where(~np.eye(len(A), dtype=bool)).stack().sort_values(ascending=False)   # links between different sectors
    (s1, b1), (s2, b2) = off.index[0], off.index[1]
    insight(fig, f"Insight 1: the strongest links run from raw materials into processing: {s1.lower()} into "
                 f"{b1.lower()} ({off.iloc[0]:.2f} per dollar), {s2.lower()} into {b2.lower()} ({off.iloc[1]:.2f})",
            f"Technical coefficients a_ij of Indonesia's domestic input-output table, {YEAR}: the domestic input from row i "
            "needed per dollar of output of column j. Sectors ordered by output, largest first.", top=0.9)
    fig.subplots_adjust(left=0.22, bottom=0.2)
    return fig


def rounds_table(sector=SHOCK_SECTOR, k=6):
    """The multiplier as a series: f + Af + A^2 f + ... The first rows are the direct
    purchases, each later row one more round of suppliers' suppliers."""
    A = model()["A"]; f = pd.Series(0.0, index=A.index); f[sector] = SHOCK
    rows, v = [], f.values.copy()
    for r in range(k + 1):
        rows.append(pd.Series(v, index=A.index, name=f"round {r}" if r else "initial demand"))
        v = A.values @ v
    total = pd.Series(model()["L"] @ f.values, index=A.index)
    rows.append((total - sum(rows)).rename(f"rounds {k + 1}+"))
    return pd.DataFrame(rows).T


def plot_rounds(df):
    top = df.sum(axis=1).sort_values(ascending=False).head(8).index
    d = pd.concat([df.loc[top], df.drop(index=top).sum().to_frame("all other sectors").T]).T
    fig, axs = plt.subplots(1, 2, figsize=(12, 5.2), gridspec_kw=dict(width_ratios=[1.4, 1]))
    d = d.rename(index={"initial demand": "start", "rounds 7+": "R7+"})
    bottom = np.zeros(len(d)); cmap = plt.get_cmap("tab10")
    for i, s in enumerate(d.columns):
        axs[0].bar(range(len(d)), d[s], bottom=bottom, color=cmap(i), label=s); bottom += d[s].values
    axs[0].set_xticks(range(len(d)), [r.replace("round ", "R") for r in d.index], fontsize=8)
    axs[0].set_ylabel("output generated (USD million)"); axs[0].legend(fontsize=6.5, ncol=2)
    cum = d.sum(axis=1).cumsum()
    axs[1].plot(range(len(cum)), cum, "-o", color="#333")
    axs[1].axhline(cum.iloc[-1], ls=":", color="#888"); axs[1].set_xticks(range(len(cum)), [r.replace("round ", "R") for r in cum.index], fontsize=8)
    axs[1].set_ylabel("cumulative output (USD million)")
    first = d.iloc[0].sum(); total = cum.iloc[-1]
    insight(fig, f"Insight 2: USD 1 billion of construction ends up as {total / 1000:.2f} billion of output, "
                 f"{100 * (cum.iloc[2] - first) / (total - first):.0f} % of the knock-on within two rounds",
            "Left: output generated in each round of purchases (initial demand, suppliers, suppliers' suppliers...), by sector. "
            "Right: the running total converging on the Leontief multiplier.")
    return fig


def plot_multipliers(df):
    fig, axs = plt.subplots(1, 3, figsize=(13, 7.2), sharey=False)
    for ax, col, lab, c in zip(axs, ["output_multiplier", "va_multiplier", "jobs_per_musd"],
                               ["output per USD of final demand", "value added per USD", "jobs per USD 1 million"],
                               ["#2166ac", "#1b7837", "#b2182b"]):
        s = df.set_index("sector")[col].sort_values()
        ax.hlines(range(len(s)), 0, s.values, color="#cccccc"); ax.plot(s.values, range(len(s)), "o", color=c)
        ax.set_yticks(range(len(s)), s.index, fontsize=7); ax.set_xlabel(lab, fontsize=8); ax.grid(axis="x", alpha=0.3)
    j = df.set_index("sector").jobs_per_musd
    insight(fig, f"Insight 3: the sectors that create the most output are not those that create the most jobs: "
                 f"{j.idxmax().lower()} leads on jobs",
            f"Type I multipliers, {YEAR}: total (direct and indirect) output, value added and persons engaged per unit of "
            "final demand in each sector. Lollipops sorted separately in each panel.", top=0.88)
    fig.subplots_adjust(wspace=0.75, left=0.12)
    return fig


def plot_quadrant(df):
    d = df.set_index("sector")
    fig, ax = plt.subplots(figsize=(9, 6.6))
    key = (d.backward_linkage > 1) & (d.forward_linkage > 1)
    ax.scatter(d.backward_linkage, d.forward_linkage, s=20 + 6 * d.output_busd, c=np.where(key, "#c51b7d", "#7f7f7f"),
               alpha=0.6, edgecolor="white")
    for s, r in d.iterrows():
        ax.annotate(s, (r.backward_linkage, r.forward_linkage), fontsize=6.5, xytext=(3, 2), textcoords="offset points")
    ax.axvline(1, color="#555", lw=0.8, ls="--"); ax.axhline(1, color="#555", lw=0.8, ls="--")
    for x, y, t in [(0.02, 0.02, "weakly linked"), (0.98, 0.02, "pulls on suppliers"), (0.02, 0.98, "supplies others"),
                    (0.98, 0.98, "KEY SECTORS")]:
        ax.text(x, y, t, transform=ax.transAxes, fontsize=8, color="#555", fontweight="bold",
                ha="left" if x < 0.5 else "right", va="bottom" if y < 0.5 else "top")
    ax.set_xlabel("backward linkage (output multiplier / average)"); ax.set_ylabel("forward linkage (Ghosh row sum / average)")
    insight(fig, f"Insight 4: {key.sum()} sectors are key sectors, strongly linked both to their suppliers and to their buyers",
            f"Rasmussen backward and Ghosh forward linkages, {YEAR}; bubble area is gross output. Quadrant lines at the "
            "economy-wide average (1).", top=0.88)
    return fig


RADAR_SECTORS = ["Construction", "Food & beverages", "Crops & livestock", "Electronics & machinery", "Trade", "Mining"]
# Backward linkage is the output multiplier divided by its mean, so it would duplicate
# that axis exactly; sector size (log of output) takes its place.
RADAR_AXES = {"output_multiplier": "output\nmultiplier", "va_multiplier": "value-added\nmultiplier",
              "jobs_per_musd": "jobs per\nUSD 1 m", "log_output": "size\n(log output)",
              "forward_linkage": "forward\nlinkage", "domestic_share": "domestic\ncontent"}


def radar_table():
    d = model()["table"].copy()
    d["domestic_share"] = 1 - d.import_leakage / d.output_multiplier
    d["log_output"] = np.log10(d.output_busd)
    r = (d[list(RADAR_AXES)] - d[list(RADAR_AXES)].min()) / (d[list(RADAR_AXES)].max() - d[list(RADAR_AXES)].min())
    return r.loc[RADAR_SECTORS].reset_index(names="sector")


def plot_radar(df):
    axes = list(RADAR_AXES); n = len(axes)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist(); ang += ang[:1]
    fig, axs = plt.subplots(2, 3, figsize=(13, 8.8), subplot_kw=dict(polar=True))
    cmap = plt.get_cmap("Dark2")
    for i, (ax, (_, r)) in enumerate(zip(axs.flat, df.iterrows())):
        v = r[axes].tolist(); v += v[:1]
        for other in df.itertuples():                                   # the other sectors as faint context
            o = [getattr(other, a) for a in axes]; o += o[:1]
            ax.plot(ang, o, color="#dddddd", lw=0.7)
        ax.fill(ang, v, color=cmap(i), alpha=0.25); ax.plot(ang, v, color=cmap(i), lw=2)
        ax.set_xticks(ang[:-1], [RADAR_AXES[a] for a in axes], fontsize=6.5); ax.set_yticks([0.25, 0.5, 0.75], [])
        ax.tick_params(axis="x", pad=1)
        ax.set_ylim(0, 1); ax.set_title(r.sector, fontsize=9, pad=14, color=cmap(i), fontweight="bold")
    insight(fig, "Insight 5: no sector wins on every axis: farming keeps jobs and value at home but pulls little "
                 "through supply chains; electronics leaks most abroad",
            f"Six indicators rescaled 0 (lowest of {len(model()['table'])} sectors) to 1 (highest), {YEAR}. Each panel is one "
            "sector; the grey outlines are the other five for comparison.", top=0.86)
    fig.subplots_adjust(hspace=0.5, wspace=0.55)
    return fig


def dumbbell_table():
    a = model(BASE)["table"].output_multiplier.rename(str(BASE)); b = model(YEAR)["table"].output_multiplier.rename(str(YEAR))
    d = pd.concat([a, b], axis=1); d["change"] = d[str(YEAR)] - d[str(BASE)]
    return d.sort_values(str(YEAR)).reset_index(names="sector")


def plot_dumbbell(df):
    fig, ax = plt.subplots(figsize=(8.4, 7.4))
    y = np.arange(len(df))
    ax.hlines(y, df[str(BASE)], df[str(YEAR)], color="#bbbbbb", lw=2)
    ax.plot(df[str(BASE)], y, "o", color="#9ecae1", label=str(BASE)); ax.plot(df[str(YEAR)], y, "o", color="#08519c", label=str(YEAR))
    ax.set_yticks(y, df.sector, fontsize=7); ax.set_xlabel("output multiplier"); ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    up = (df.change > 0).sum()
    insight(fig, f"Insight 6: between {BASE} and {YEAR}, {up} of {len(df)} sectors became more tightly woven into the "
                 "domestic economy",
            "Output multiplier of each sector in the two years; a dot moving right means each dollar of final demand now "
            "pulls more domestic output through the supply chain.", top=0.88)
    fig.subplots_adjust(left=0.3)
    return fig


def products():
    return [
        {"kind": "table", "name": "ch68-multipliers", "data": multiplier_table,
         "floatfmt": ("", ".2f", ".2f", ".0f", ".2f", ".2f", ".2f", ",.0f"),
         "caption": f"Multipliers and linkages of the 28 sector groups, Indonesia {YEAR}."},
        {"kind": "figure", "name": "ch68-heatmap", "figure": heatmap_figure,
         "caption": "Insight 1. Technical coefficients: who buys from whom."},
        {"kind": "chart", "name": "ch68-rounds", "data": rounds_table, "plot": plot_rounds,
         "caption": "Insight 2. A USD 1 billion construction shock, round by round."},
        {"kind": "chart", "name": "ch68-multiplier-chart", "data": multiplier_table, "plot": plot_multipliers,
         "caption": "Insight 3. Output, value-added and employment multipliers."},
        {"kind": "chart", "name": "ch68-quadrant", "data": multiplier_table, "plot": plot_quadrant,
         "caption": "Insight 4. Key sectors: backward against forward linkage."},
        {"kind": "chart", "name": "ch68-radar", "data": radar_table, "plot": plot_radar,
         "caption": "Insight 5. Radar profiles of six sectors."},
        {"kind": "chart", "name": "ch68-dumbbell", "data": dumbbell_table, "plot": plot_dumbbell,
         "caption": f"Insight 6. Output multipliers, {BASE} against {YEAR}."},
    ]


if __name__ == "__main__":
    print(multiplier_table().round(2).to_string()); print(rounds_table().sum().round(0))
