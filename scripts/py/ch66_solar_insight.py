#| title: Solar insight charts (Python)
#| description: Ten years of hourly PVGIS-ERA5 irradiance for Kupang and Bandung turned into five insight charts - a day-by-hour heatmap, a clearness-index scatter with physical limits, hourly ramp boxes with extreme events, monthly PV yield bars and monthly diurnal small multiples.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 66 | One chart, one question

Ten years of hourly solar data is 87,600 rows per site. No table shows what is
in it; five charts, each chosen for one question, do:

  Insight 1  heatmap (day x hour)       when is there sun, and when is it missing?
  Insight 2  clearness scatter (k-space) is the data physically possible?
  Insight 3  hourly ramp boxes          how fast does the resource change?
  Insight 4  monthly yield bars         what will a PV system produce, and how
                                        much does that vary from year to year?
  Insight 5  small multiples            how do two climates differ, month by month?

Data: PVGIS v5.3 hourly series (EU Joint Research Centre), free, no key.
Kupang (dry, Nusa Tenggara Timur) and Bandung (wet, West Java), 2014-2023,
radiation database PVGIS-ERA5. Timestamps are UTC; both sites are converted
to local time (Kupang UTC+8, Bandung UTC+7).

Environment: pip install pandas numpy matplotlib requests
"""

import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

API = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"
CACHE = Path(os.environ.get("SOLAR_CACHE", "data/solar_insight")); CACHE.mkdir(parents=True, exist_ok=True)
SITES = {"Kupang": dict(lat=-10.17, lon=123.61, utc=8), "Bandung": dict(lat=-6.91, lon=107.61, utc=7)}
YEARS = (2014, 2023)
GREY = "#3a3a3a"


def insight(fig, title, subtitle, top=0.8):
    """The house style: a bold headline that states the finding, and one line
    saying what is plotted. Placed on the figure, not the axes, so they never collide."""
    fig.suptitle(title, x=0.01, y=0.98, ha="left", fontsize=10, fontweight="bold")
    fig.text(0.01, 0.905, subtitle, fontsize=8, color="#444444")
    fig.subplots_adjust(top=top)


def pvgis(site, pv=False):
    """Hourly series for one site. pv=False: global horizontal components.
    pv=True: a 1 kWp system tilted 10 degrees towards the equator, 14 % losses."""
    s = SITES[site]
    f = CACHE / f"{site}_{'pv' if pv else 'h'}.json"
    if not f.exists():
        q = dict(lat=s["lat"], lon=s["lon"], startyear=YEARS[0], endyear=YEARS[1], outputformat="json",
                 raddatabase="PVGIS-ERA5")
        if pv:   # PVGIS aspect: 0 = south, 180 = north; south of the equator face north
            q.update(pvcalculation=1, peakpower=1, loss=14, angle=10, aspect=180)
        else:
            q.update(components=1, angle=0)
        r = requests.get(API, params=q, timeout=300); r.raise_for_status()
        f.write_text(r.text)
    d = pd.DataFrame(json.loads(f.read_text())["outputs"]["hourly"])
    d["utc"] = pd.to_datetime(d.time, format="%Y%m%d:%H%M")
    d["local"] = d.utc + pd.Timedelta(hours=s["utc"])
    return d


_cache = {}


def hourly(site):
    """GHI, DHI, extraterrestrial irradiance and the two clearness indices."""
    if site in _cache:
        return _cache[site]
    d = pvgis(site)
    d["ghi"] = d["Gb(i)"] + d["Gd(i)"]          # horizontal plane: beam + diffuse
    d["dhi"] = d["Gd(i)"]
    doy = d.utc.dt.dayofyear
    # Extraterrestrial irradiance on a horizontal plane at the sun height PVGIS reports.
    e0 = 1361 * (1 + 0.033 * np.cos(2 * np.pi * doy / 365))
    d["g0"] = e0 * np.sin(np.radians(d.H_sun.clip(lower=0)))
    day = d.H_sun > 5                            # ignore the low-sun hours where ratios explode
    d["kt"] = np.where(day, d.ghi / d.g0, np.nan)          # clearness index
    d["kd"] = np.where(day & (d.ghi > 0), d.dhi / d.ghi, np.nan)   # diffuse fraction
    d["date"] = d.local.dt.normalize(); d["hour"] = d.local.dt.hour; d["month"] = d.local.dt.month
    _cache[site] = d
    return d


# Insight 1. Heatmap: when is there sun? -----------------------------------------------
def heatmap_figure(site="Kupang", year=2023):
    d = hourly(site); d = d[d.local.dt.year == year]
    grid = d.pivot_table(index="hour", columns="date", values="ghi")
    grid = grid.reindex(index=range(24), columns=pd.date_range(f"{year}-01-01", f"{year}-12-31"))
    fig, ax = plt.subplots(figsize=(11, 4))
    cmap = plt.get_cmap("inferno").copy(); cmap.set_bad(GREY)        # missing hours in dark grey
    im = ax.imshow(np.ma.masked_invalid(grid.values), aspect="auto", cmap=cmap, origin="lower",
                   extent=[0, grid.shape[1], 0, 24], vmin=0, vmax=1100)
    months = pd.date_range(f"{year}-01-01", periods=12, freq="MS")
    ax.set_xticks([(m - months[0]).days for m in months], [m.strftime("%b") for m in months])
    ax.set_yticks([0, 6, 12, 18, 24]); ax.set_ylabel("local hour")
    fig.colorbar(im, ax=ax, pad=0.01, label="GHI (W/m²)")
    insight(fig, f"Insight 1: {site}'s brightest weeks are September to November; the wet season shows as broken days",
            f"Hourly global horizontal irradiance, {year}. Each column is a day, each row a local hour; dark streaks "
            "inside the daylight band are cloudy days, dark grey would mark missing hours.")
    return fig


# Insight 2. k-space: is the data physically possible? ----------------------------------
def kspace_table():
    rows = []
    for site in SITES:
        d = hourly(site).dropna(subset=["kt", "kd"])
        rows.append({"site": site, "daylight_hours": len(d),
                     "kt_above_1_%": 100 * (d.kt > 1).mean(),
                     "kd_above_1_%": 100 * (d.kd > 1.0).mean(),
                     "overcast_kt<0.3_%": 100 * (d.kt < 0.3).mean(),
                     "clear_kt>0.65_%": 100 * (d.kt > 0.65).mean(),
                     "reconstructed_%": 100 * (hourly(site)["Int"] == 1).mean()})
    return pd.DataFrame(rows)


def kspace_figure():
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for ax, site in zip(axs, SITES):
        d = hourly(site).dropna(subset=["kt", "kd"])
        ax.hexbin(d.kt, d.kd, gridsize=60, extent=(0, 1.1, 0, 1.05), cmap="viridis", bins="log", mincnt=1)
        ax.axhline(1, color="#d73027", lw=1, ls="--")                 # diffuse cannot exceed global
        ax.axvline(1, color="#d73027", lw=1, ls="--")                 # surface cannot exceed top of atmosphere
        x = np.linspace(0.01, 1.1, 100)
        ax.plot(x, np.clip(1 - 0.85 * np.clip(x - 0.2, 0, None) / 0.6, 0.1, 1), color="white", lw=1, ls=":")
        ax.set_xlim(0, 1.1); ax.set_ylim(0, 1.05); ax.set_xlabel("clearness index kt = GHI / extraterrestrial")
        ax.set_title(site, loc="left", fontsize=9)
    axs[0].set_ylabel("diffuse fraction kd = DHI / GHI")
    insight(fig, "Insight 2: no hour breaks the physical limits; Kupang crowds the clear-sky corner, Bandung spreads to overcast",
            "Hourly clearness index against diffuse fraction, sun above 5°, 2014–2023. Points beyond a red line would be "
            "impossible; the dotted curve is the typical clear-to-overcast transition.", top=0.78)
    fig.subplots_adjust(wspace=0.05)
    return fig


# Insight 3. Ramps: how fast does the resource change? -------------------------------------
def ramp_data(site="Kupang"):
    d = hourly(site).sort_values("utc").copy()
    d["ramp"] = d.ghi.diff()                       # W/m2 per hour
    return d[(d.hour >= 6) & (d.hour <= 18)][["hour", "ramp"]].dropna()


def ramp_figure(site="Kupang"):
    d = ramp_data(site)
    hours = sorted(d.hour.unique())
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.boxplot([d[d.hour == h].ramp for h in hours], positions=hours, widths=0.6, whis=(5, 95), showfliers=False,
               patch_artist=True, boxprops=dict(facecolor="#c6dbef", color="#4292c6"),
               medianprops=dict(color="#08306b"), whiskerprops=dict(color="#4292c6"), capprops=dict(color="#4292c6"))
    ax.plot(hours, [d[d.hour == h].ramp.mean() for h in hours], color="#555555", lw=1.2, label="mean")
    lim = d.ramp.abs().quantile(0.999)
    ext = d[d.ramp.abs() > lim]
    ax.scatter(ext.hour, ext.ramp, marker="x", color="#cb181d", s=22, label=f"extreme (|ramp| > {lim:.0f} W/m²/h, top 0.1 %)")
    ax.axhline(0, color="#888", lw=0.6)
    ax.set_xlabel("local hour (change from the previous hour)"); ax.set_ylabel("GHI change (W/m² per hour)")
    ax.legend(fontsize=8, loc="lower left")
    insight(fig, f"Insight 3: in {site} the sharpest changes are sudden afternoon drops, at 13:00 and 14:00",
            "Hour-to-hour change in GHI by local hour, 2014–2023. Boxes hold the middle half, whiskers the 5th–95th "
            "percentiles, crosses the most extreme 0.1 % of hours.")
    return fig


# Insight 4. Monthly PV yield, and its year-to-year spread ---------------------------------
def yield_table():
    rows = []
    for site in SITES:
        p = pvgis(site, pv=True)
        p["year"] = p.local.dt.year; p["month"] = p.local.dt.month
        m = p.groupby(["year", "month"]).P.sum().div(1000).rename("kwh").reset_index()   # 1 kWp -> kWh/kWp
        m = m[(m.year >= YEARS[0]) & (m.year <= YEARS[1])]
        s = m.groupby("month").kwh.agg(["mean", "min", "max"]).reset_index()
        s.insert(0, "site", site)
        rows.append(s)
    return pd.concat(rows, ignore_index=True)


def plot_yield(df):
    fig, ax = plt.subplots(figsize=(10, 4.2))
    w = 0.38
    for i, (site, c) in enumerate(zip(SITES, ["#e6550d", "#3182bd"])):
        s = df[df.site == site]
        x = s.month + (i - 0.5) * w
        ax.bar(x, s["mean"], width=w, color=c, alpha=0.85, label=f"{site} (annual {s['mean'].sum():,.0f} kWh/kWp)")
        ax.errorbar(x, s["mean"], yerr=[s["mean"] - s["min"], s["max"] - s["mean"]], fmt="none", ecolor="#333", lw=0.8, capsize=2)
    ax.set_xticks(range(1, 13), ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
    ax.set_ylabel("PV yield (kWh per kWp per month)"); ax.legend(fontsize=8, loc="lower right")
    insight(fig, "Insight 4: Kupang out-yields Bandung in every month, by the most in October and November",
            "Mean monthly yield of a 1 kWp system (10° tilt towards the equator, 14 % losses); whiskers show the lowest "
            "and highest year, 2014–2023.")
    return fig


# Insight 5. Small multiples: the average day, month by month -------------------------------
def diurnal_table():
    rows = []
    for site in SITES:
        d = hourly(site)
        g = d.groupby(["month", "hour"]).ghi.agg(mean="mean", p90=lambda v: v.quantile(0.9)).reset_index()
        g.insert(0, "site", site); rows.append(g)
    return pd.concat(rows, ignore_index=True)


def plot_diurnal(df):
    fig, axs = plt.subplots(2, 6, figsize=(13, 5), sharex=True, sharey=True)
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for m, ax in zip(range(1, 13), axs.flat):
        for site, c in zip(SITES, ["#e6550d", "#3182bd"]):
            s = df[(df.site == site) & (df.month == m)]
            ax.fill_between(s.hour, s["mean"], s.p90, color=c, alpha=0.15, lw=0)
            ax.plot(s.hour, s["mean"], color=c, lw=1.6, label=site)
        ax.set_title(names[m - 1], loc="left", fontsize=9); ax.set_xticks([6, 12, 18]); ax.set_xlim(5, 19)
        ax.grid(alpha=0.3)
    axs[0, 0].legend(fontsize=7, loc="upper left"); axs[1, 0].set_ylabel("GHI (W/m²)"); axs[0, 0].set_ylabel("GHI (W/m²)")
    insight(fig, "Insight 5: the two sites have almost the same day from June to August and part most from October to March",
            "Mean hourly GHI by local hour (line) up to the 90th percentile (shading), one panel per month, 2014–2023. "
            "The same axes in every panel let the eye compare panels without reading numbers.", top=0.82)
    fig.subplots_adjust(hspace=0.3, wspace=0.08)
    return fig


def summary_table():
    rows = []
    for site in SITES:
        d = hourly(site); daily = (d.groupby("date").ghi.sum() / 1000).rename("kwh").reset_index()
        by_month = daily.groupby(daily.date.dt.month).kwh.mean()
        rows.append({"site": site, "years": f"{YEARS[0]}–{YEARS[1]}", "mean_daily_kWh_m2": daily.kwh.mean(),
                     "worst_month_kWh_m2_day": by_month.min(), "best_month_kWh_m2_day": by_month.max(),
                     "mean_kt": d.kt.mean(), "mean_kd": d.kd.mean(), "max_GHI_W_m2": d.ghi.max()})
    return pd.DataFrame(rows)


def products():
    return [
        {"kind": "table", "name": "ch66-summary", "data": summary_table, "floatfmt": ("", "", ".2f", ".2f", ".2f", ".2f", ".2f", ".0f"),
         "caption": "The two sites in numbers, before any chart."},
        {"kind": "figure", "name": "ch66-heatmap", "figure": heatmap_figure,
         "caption": "Insight 1. Day-by-hour heatmap of hourly GHI in Kupang, 2023."},
        {"kind": "figure", "name": "ch66-kspace", "figure": kspace_figure,
         "caption": "Insight 2. Clearness index against diffuse fraction, with the physical limits."},
        {"kind": "table", "name": "ch66-kspace-table", "data": kspace_table, "floatfmt": ("", ",.0f", ".2f", ".2f", ".1f", ".1f", ".2f"),
         "caption": "Quality checks behind Insight 2: share of daylight hours outside the physical limits, "
                    "and the overcast and clear shares."},
        {"kind": "figure", "name": "ch66-ramps", "figure": ramp_figure,
         "caption": "Insight 3. Hour-to-hour change in GHI, Kupang, with extreme ramps marked."},
        {"kind": "chart", "name": "ch66-yield", "data": yield_table, "plot": plot_yield,
         "caption": "Insight 4. Monthly yield of a 1 kWp PV system and its year-to-year range."},
        {"kind": "chart", "name": "ch66-diurnal", "data": diurnal_table, "plot": plot_diurnal,
         "caption": "Insight 5. The average day in every month, both sites on the same axes."},
    ]


if __name__ == "__main__":
    print(summary_table()); print(kspace_table()); print(yield_table().groupby("site")["mean"].sum())
