#| title: Before any statistics: what is missing, and why (Python)
#| description: The same 22 years of daily MODIS land surface temperature over Bandung as the JavaScript tab, checked for missing days, quality flags and outliers.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 30 | A data quality assessment on a satellite time series, in the
same order as a ground-station check: count what is missing, find out why,
read the quality flags, then look for outliers with two different rules.

Pixel: central Bandung, one MODIS 1 km cell. Period: 2003-2024.

    pip install earthengine-api pandas numpy matplotlib
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

point = ee.Geometry.Point(107.61, -6.91)
FIRST, LAST = "2003-01-01", "2025-01-01"
lst = (ee.ImageCollection("MODIS/061/MOD11A1").filterDate(FIRST, LAST)
       .select(["LST_Day_1km", "QC_Day"]))
pentads = (ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD").filterDate(FIRST, LAST)
           .select("precipitation"))


_CACHE = {}


def daily_frame():
    """One row per calendar day, including the days with no MODIS file at all."""
    if "daily" in _CACHE:
        return _CACHE["daily"].copy()
    rows = lst.getRegion(point, 1000).getInfo()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df["date"] = pd.to_datetime(df["time"], unit="ms").dt.normalize()
    df = df.set_index("date")
    # Reindex to every calendar day. A day with no granule is not NaN in the
    # Earth Engine table; it is simply absent, which is easy to miss.
    days = pd.date_range(FIRST, "2024-12-31", freq="D")
    df = df.reindex(days)
    df.index.name = "date"
    df["granule"] = df["time"].notna()
    df["lst_c"] = df["LST_Day_1km"] * 0.02 - 273.15            # scale, then K to °C
    qc = df["QC_Day"].fillna(-1).astype(int).to_numpy()
    df["qc_mandatory"] = np.where(qc < 0, -1, qc & 3)           # bits 0-1
    df["qc_error"] = np.where(qc < 0, -1, (qc >> 6) & 3)        # bits 6-7: LST error
    df["year"] = df.index.year
    df["month"] = df.index.month
    _CACHE["daily"] = df.reset_index()[["date", "year", "month", "granule", "lst_c",
                                        "qc_mandatory", "qc_error"]]
    return _CACHE["daily"].copy()


def monthly_frame():
    """Share of days without a value, and mean CHIRPS rainfall, per calendar month."""
    df = daily_frame()
    miss = df.groupby("month")["lst_c"].apply(lambda s: s.isna().mean()).rename("missing")
    rain = []
    for m in range(1, 13):
        total = (pentads.filter(ee.Filter.calendarRange(m, m, "month")).sum().divide(22)
                 .reduceRegion(ee.Reducer.mean(), point.buffer(5000), 5566)
                 .get("precipitation"))
        rain.append(total)
    rain = ee.List(rain).getInfo()
    return pd.DataFrame({"month": range(1, 13), "missing": miss.values, "rain_mm": rain})


def plot_gap_heatmap(df):
    """Share of days with no LST, year by month: a pivot table as a picture."""
    grid = (df.assign(miss=df["lst_c"].isna())
            .pivot_table(index="year", columns="month", values="miss", aggfunc="mean"))
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    im = ax.imshow(grid.values * 100, cmap="Greys", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(12), ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
    ax.set_yticks(range(len(grid)), grid.index, fontsize=7)
    fig.colorbar(im, ax=ax, label="Days with no LST value (%)", shrink=0.8)
    ax.set_title("Two thirds of the days are missing, and the wet season is "
                 "almost empty", loc="left", fontsize=9.5)
    return fig


def plot_missing_vs_rain(df):
    """Is the gap random? Missing share against rainfall, one point per month."""
    fig, ax = plt.subplots(figsize=(5.6, 3.8))
    ax.scatter(df["rain_mm"], df["missing"] * 100, s=40, color="#2a78d6",
               edgecolor="white", zorder=3)
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
             "Nov", "Dec"]
    for _, r in df.iterrows():
        ax.annotate(names[int(r["month"]) - 1], (r["rain_mm"], r["missing"] * 100),
                    xytext=(5, -3), textcoords="offset points", fontsize=7)
    r = np.corrcoef(df["rain_mm"], df["missing"])[0, 1]
    ax.set_xlabel("Mean monthly rainfall, CHIRPS 2003-2024 (mm)")
    ax.set_ylabel("Days with no LST value (%)")
    ax.set_ylim(0, 100)
    ax.grid(color="#e4e7eb", lw=0.6)
    ax.set_title(f"The wetter the month, the more is missing (r = {r:.2f})",
                 loc="left", fontsize=10)
    return fig


def plot_outliers(df):
    """Valid LST by error flag, with the 3 SD and 1.5 IQR fences."""
    v = df.dropna(subset=["lst_c"])
    m, s = v["lst_c"].mean(), v["lst_c"].std()
    q1, q3 = v["lst_c"].quantile([0.25, 0.75])
    bins = np.arange(22, 49, 0.5)
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    labels = {0: "error ≤ 1 K", 1: "error ≤ 2 K", 2: "error ≤ 3 K"}
    colours = {0: "#0072B2", 1: "#9aa5b1", 2: "#E69F00"}
    ax.hist([v.loc[v["qc_error"] == k, "lst_c"] for k in (0, 1, 2)], bins=bins,
            stacked=True, color=[colours[k] for k in (0, 1, 2)],
            label=[labels[k] for k in (0, 1, 2)], edgecolor="white", lw=0.3)
    for x, style, name in [(m - 3 * s, "--", "mean ± 3 SD"), (m + 3 * s, "--", None),
                           (q1 - 1.5 * (q3 - q1), ":", "1.5 × IQR"),
                           (q3 + 1.5 * (q3 - q1), ":", None)]:
        ax.axvline(x, color="#1f2933", ls=style, lw=1, label=name)
    ax.set_xlabel("Daytime land surface temperature (°C)")
    ax.set_ylabel("Days")
    ax.legend(frameon=False, fontsize=7, loc="upper left")
    ax.set_title("Two rules, two different sets of 'outliers'", loc="left", fontsize=10)
    return fig


def summary_frame():
    df = daily_frame()
    v = df["lst_c"].dropna()
    m, s = v.mean(), v.std()
    q1, q3 = v.quantile([0.25, 0.75])
    iqr = q3 - q1
    rows = [
        ("Calendar days, 2003-2024", len(df)),
        ("Days with no MODIS granule at all", int((~df["granule"]).sum())),
        ("Days with a granule but no LST (cloud)", int((df["granule"] & df["lst_c"].isna()).sum())),
        ("Days with a valid LST", int(v.size)),
        ("  of which QC 'good quality' (bits 0-1 = 00)", int((df["qc_mandatory"] == 0).sum())),
        ("  of which LST error ≤ 1 K", int((df["lst_c"].notna() & (df["qc_error"] == 0)).sum())),
        ("  of which LST error ≤ 2 K", int((df["lst_c"].notna() & (df["qc_error"] == 1)).sum())),
        ("  of which LST error ≤ 3 K", int((df["lst_c"].notna() & (df["qc_error"] == 2)).sum())),
        ("Outliers by mean ± 3 SD", int(((v < m - 3 * s) | (v > m + 3 * s)).sum())),
        ("Outliers by 1.5 × IQR", int(((v < q1 - 1.5 * iqr) | (v > q3 + 1.5 * iqr)).sum())),
    ]
    return pd.DataFrame(rows, columns=["check", "days"])


def products():
    return [
        {"kind": "chart", "name": "ch30-gap-heatmap", "data": daily_frame,
         "plot": plot_gap_heatmap, "live": False,
         "caption": "Share of days with no daytime LST, for every month of 22 years. "
                    "Dark is missing. The pattern repeats every year: clouds, not a "
                    "sensor fault."},
        {"kind": "chart", "name": "ch30-missing-vs-rain", "data": monthly_frame,
         "plot": plot_missing_vs_rain,
         "caption": "Missing days against rainfall for the twelve calendar months. The "
                    "gaps are not random, so an average of the days that remain describes "
                    "clear days, not all days."},
        {"kind": "chart", "name": "ch30-outliers", "data": daily_frame,
         "plot": plot_outliers, "live": False,
         "caption": "All valid daytime LST values, stacked by the error class in the QC "
                    "band, with the fences of two outlier rules."},
        {"kind": "table", "name": "ch30-quality-table", "data": summary_frame,
         "floatfmt": ",.0f",
         "caption": "The data quality summary for one pixel. Write this table before "
                    "any trend or model. A zero on the 'good quality' line is common in "
                    "the humid tropics; check it rather than assume a bug."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(summary_frame())
