#| title: Smoke from space: the 2019 haze as a time-lapse (Python)
#| description: Animates the 2019 Sumatra and Kalimantan haze in MODIS true colour and in Sentinel-5P carbon monoxide with FIRMS fires, then turns the same data into daily series, a lag analysis of fire against downwind smoke, an anomaly map against 2020 and a longitude-time diagram of the plume.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 71 | Smoke from space: the 2019 haze, frame by frame

In September 2019 smoke from peat and forest fires in Sumatra and Kalimantan
closed schools from Palangka Raya to Kuala Lumpur. This script shows that
season twice: as the eye would see it (MODIS true colour) and as chemistry
sees it (Sentinel-5P carbon monoxide and the absorbing aerosol index), with
every fire FIRMS detected. Then it asks the questions an animation cannot
answer on its own: when did the smoke peak, where, how long after the fires,
and how unusual was it compared with a wet year.

Data: MODIS Terra and Aqua surface reflectance (MOD09GA, MYD09GA), FIRMS
active fire, Sentinel-5P OFFL L3 CO and aerosol index, FAO GAUL 2025.
All public, all in Earth Engine. The daily series are saved to
data/ch71_haze_daily.csv, so the analysis (and the R twin) runs without
Earth Engine.

Environment: pip install earthengine-api pandas numpy matplotlib scipy
"""

import os
from pathlib import Path

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2] if "__file__" in globals() else Path(".")
CSV = Path(os.environ.get("HAZE_CSV", ROOT / "data" / "ch71_haze_daily.csv"))
HOV = CSV.with_name("ch71_haze_hovmoller.csv")
BOX = [97, -5, 118, 7.5]                     # Sumatra, the Malay Peninsula and Borneo
YEARS = [2019, 2020]                         # 2019: a positive Indian Ocean Dipole, very dry; 2020: wet
START, END = "-07-01", "-12-01"              # July to November
CITIES = {                                   # where people breathed the smoke (lon, lat)
    "Pekanbaru": (101.45, 0.51), "Palangka Raya": (113.92, -2.21), "Pontianak": (109.33, -0.03),
    "Singapore": (103.82, 1.35), "Kuching": (110.35, 1.55), "Kuala Lumpur": (101.69, 3.14)}
SOURCES = {                                  # where the fires were: GAUL 2025 provinces
    "Sumatra": ["Riau", "Jambi", "Sumatera Selatan"],
    "Kalimantan": ["Kalimantan Barat", "Kalimantan Tengah", "Kalimantan Selatan"]}


def region():
    return ee.Geometry.Rectangle(BOX, None, False)


# PART 1. Daily images ----------------------------------------------------------------------
# Sentinel-5P L3 in Earth Engine is one image per orbit, so a day is a mosaic of
# ~14 orbit strips. The mean of the strips is the daily field.
def s5p_day(name, band, day):
    d = ee.Date(day)
    return ee.ImageCollection(name).filterDate(d, d.advance(1, "day")).select(band).mean()


def co_day(day):           # mol/m2 -> mmol/m2, a friendlier number (background is about 30)
    return s5p_day("COPERNICUS/S5P/OFFL/L3_CO", "CO_column_number_density", day).multiply(1000).rename("co")


def ai_day(day):           # > 1 means absorbing aerosol (smoke or dust) above the clouds or under them
    return s5p_day("COPERNICUS/S5P/OFFL/L3_AER_AI", "absorbing_aerosol_index", day).rename("ai")


def fires_day(day):
    d = ee.Date(day)
    return ee.ImageCollection("FIRMS").filterDate(d, d.advance(1, "day")).select("T21").max()


def truecolour_day(day):
    """Terra (morning) and Aqua (afternoon) together, to fill the gaps between swaths."""
    d = ee.Date(day)
    both = (ee.ImageCollection("MODIS/061/MOD09GA").merge(ee.ImageCollection("MODIS/061/MYD09GA"))
            .filterDate(d, d.advance(1, "day")).select(["sur_refl_b01", "sur_refl_b04", "sur_refl_b03"]))
    return both.mosaic().visualize(min=0, max=3000, gamma=1.4)


# PART 2. Two time-lapses: what the eye sees, and what the chemistry sees -------------------------
FRAME_DAYS = pd.date_range("2019-08-01", "2019-10-31", freq="4D").strftime("%Y-%m-%d").tolist()


def basemap():
    """A cloud-free dry-season backdrop, so the smoke is the only thing that moves."""
    clear = (ee.ImageCollection("MODIS/061/MOD09A1").filterDate("2019-06-01", "2019-10-01")
             .select(["sur_refl_b01", "sur_refl_b04", "sur_refl_b03"]).median())
    return clear.visualize(min=0, max=3000, gamma=1.4).multiply(0.75).uint8()    # dim it a little


def chemistry_frame(day):
    """3-day mean CO over the backdrop (one day has gaps under thick cloud), and that day's fires."""
    d = ee.Date(day)
    co = ee.ImageCollection([co_day(d.advance(-1, "day")), co_day(d), co_day(d.advance(1, "day"))]).mean()
    co_vis = co.updateMask(co.gt(40)).visualize(min=40, max=150, palette=["#fff7bc", "#fec44f", "#ec7014", "#993404", "#4d1a02"], opacity=0.8)
    fire_vis = fires_day(day).focalMax(2500, "circle", "meters").mask().selfMask().visualize(palette=["#ff0000"])
    return basemap().blend(co_vis).blend(fire_vis)


# PART 3. Daily series: fires at the source, smoke at the cities --------------------------------
def sources_fc():
    g = ee.FeatureCollection("FAO/GAUL/2025/level1").filter(ee.Filter.eq("ISO3_CODE", "IDN"))
    return ee.FeatureCollection([ee.Feature(g.filter(ee.Filter.inList("GAUL1_NAME", v)).geometry(), {"name": k})
                                 for k, v in SOURCES.items()])


def cities_fc():
    return ee.FeatureCollection([ee.Feature(ee.Geometry.Point(xy).buffer(30000), {"name": k}) for k, xy in CITIES.items()])


def daily_series():
    """One row per day and place: fire pixel count (sources) or mean CO and AI (cities)."""
    if CSV.exists():
        return pd.read_csv(CSV, parse_dates=["date"])
    src, cty = sources_fc(), cities_fc()
    rows = []
    for y in YEARS:
        days = pd.date_range(f"{y}{START}", f"{y}{END}", freq="D", inclusive="left").strftime("%Y-%m-%d")
        for chunk in np.array_split(days, len(days) // 5):        # 5 days a request keeps aggregations few
            def one(day):
                f = fires_day(day).gt(0).unmask(0).rename("fires")
                fc = f.reduceRegions(src, ee.Reducer.sum().setOutputs(["fires"]), 1000).map(lambda x: x.set("date", day))
                ch = co_day(day).addBands(ai_day(day)).reduceRegions(cty, ee.Reducer.mean(), 5000)
                return fc.merge(ch.map(lambda x: x.set("date", day)))
            fc = ee.FeatureCollection([one(d) for d in chunk]).flatten()
            rows += fetch(fc)
    df = pd.DataFrame(rows).reindex(columns=["date", "name", "fires", "co", "ai"])
    df["date"] = pd.to_datetime(df["date"])
    CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV, index=False, float_format="%.4g")
    return df


def hovmoller():
    """Mean CO in 0.5 degree longitude strips, 3 S to 3 N, every day of 2019: the plume as a picture of time."""
    if HOV.exists():
        return pd.read_csv(HOV, parse_dates=["date"])
    lons = np.arange(BOX[0], BOX[2], 0.5)
    strips = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x, -3, x + 0.5, 3], None, False), {"lon": float(x + 0.25)})
                                   for x in lons])
    days = pd.date_range(f"2019{START}", f"2019{END}", freq="D", inclusive="left").strftime("%Y-%m-%d")
    rows = []
    for chunk in np.array_split(days, len(days) // 5):
        fc = ee.FeatureCollection([co_day(d).reduceRegions(strips, ee.Reducer.mean(), 10000).map(lambda x, d=d: x.set("date", d))
                                   for d in chunk]).flatten()
        rows += fetch(fc)
    df = pd.DataFrame(rows).rename(columns={"mean": "co"})[["date", "lon", "co"]]
    df["date"] = pd.to_datetime(df["date"])
    df.to_csv(HOV, index=False, float_format="%.4g")
    return df


def fetch(fc, tries=5):
    """getInfo with a pause and retry: Earth Engine limits concurrent aggregations per user."""
    import time
    for i in range(tries):
        try:
            return [f["properties"] for f in fc.getInfo()["features"]]
        except ee.EEException as err:
            if "concurrent" not in str(err) or i == tries - 1:
                raise
            time.sleep(20 * (i + 1))


def wide(df, col, year):
    d = df[df.date.dt.year == year]
    return d.pivot_table(index="date", columns="name", values=col)


# PART 4. What the series say ---------------------------------------------------------------------
def season_table():
    """Totals and peaks per year: how much worse was 2019?"""
    df = daily_series()
    out = []
    for y in YEARS:
        f, c = wide(df, "fires", y), wide(df, "co", y)
        for s in SOURCES:
            out.append({"year": y, "place": f"{s} (fire source)", "measure": "fire pixels, Jul-Nov",
                        "value": f[s].sum(), "peak day": f[s].idxmax().strftime("%d %b")})
        for k in CITIES:
            out.append({"year": y, "place": k, "measure": "days with CO > 50 mmol/m²",
                        "value": int((c[k] > 50).sum()), "peak day": c[k].idxmax().strftime("%d %b")})
    t = pd.DataFrame(out)
    return t.pivot_table(index=["place", "measure"], columns="year", values="value", aggfunc="first").reset_index().merge(
        t[t.year == 2019][["place", "peak day"]], on="place").rename(columns={"peak day": "2019 peak"})


def lag_table(max_lag=7):
    """Correlation of daily fire counts with CO at each city, shifting the city series 0..7 days later.

    Fire counts and CO both rise through the dry season, so a raw correlation is
    mostly the season. Each series is first differenced from its own 15-day
    running mean (an anomaly), so what remains is day-to-day co-variation.
    """
    df = daily_series()
    f, c = wide(df, "fires", 2019), wide(df, "co", 2019)
    anom = lambda s: s - s.rolling(15, center=True, min_periods=5).mean()
    pairs = [("Sumatra", "Pekanbaru"), ("Sumatra", "Singapore"), ("Sumatra", "Kuala Lumpur"),
             ("Kalimantan", "Palangka Raya"), ("Kalimantan", "Pontianak"), ("Kalimantan", "Kuching")]
    rows = []
    for s, k in pairs:
        r = [anom(f[s]).corr(anom(c[k]).shift(-lag)) for lag in range(max_lag + 1)]
        best = int(np.nanargmax(r))
        rows.append({"fires in": s, "CO at": k, **{f"lag {i}": v for i, v in enumerate(r)},
                     "best lag (days)": best, "r at best": r[best]})
    return pd.DataFrame(rows)


# PART 5. Charts --------------------------------------------------------------------------------------
def plot_series(t):
    df = daily_series()
    fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True, gridspec_kw={"height_ratios": [1, 1.2, 1]})
    f19, c19, c20 = wide(df, "fires", 2019), wide(df, "co", 2019), wide(df, "co", 2020)
    axes[0].bar(f19.index, f19["Sumatra"], color="#e08214", width=1, label="Sumatra")
    axes[0].bar(f19.index, f19["Kalimantan"], bottom=f19["Sumatra"], color="#b2182b", width=1, label="Kalimantan")
    axes[0].set_ylabel("fire pixels per day"); axes[0].legend(frameon=False, loc="upper left")
    axes[0].set_title("1. The fires: FIRMS detections in the six fire provinces, 2019", loc="left", fontsize=10)
    for k, col in zip(CITIES, ["#e08214", "#b2182b", "#d6604d", "#2166ac", "#4393c3", "#542788"]):
        axes[1].plot(c19.index, c19[k].rolling(3, center=True, min_periods=1).mean(), color=col, lw=1.4, label=k)
    axes[1].axhline(50, color="grey", ls=":", lw=1); axes[1].text(c19.index[2], 52, "50 mmol/m²", fontsize=8, color="grey")
    axes[1].set_ylabel("CO column (mmol/m²)"); axes[1].legend(frameon=False, ncol=3, fontsize=8, loc="upper left")
    axes[1].set_title("2. The smoke: Sentinel-5P CO over six cities (3-day mean)", loc="left", fontsize=10)
    shift = lambda s: s.set_axis(s.index - pd.DateOffset(years=1))      # put 2020 on the 2019 calendar
    for k, col in [("Palangka Raya", "#b2182b"), ("Singapore", "#2166ac")]:
        # min_periods: a cloudy day should shorten the window, not break the line
        axes[2].plot(c19.index, c19[k].rolling(7, center=True, min_periods=2).mean(), color=col, lw=1.6, label=f"{k} 2019")
        axes[2].plot(shift(c20[k]).index, shift(c20[k]).rolling(7, center=True, min_periods=2).mean(), color=col, lw=1.2, ls="--", label=f"{k} 2020")
    axes[2].set_ylabel("CO (7-day mean)"); axes[2].legend(frameon=False, ncol=2, fontsize=8, loc="upper left")
    axes[2].set_title("3. The baseline: the same months in 2020, a wet year", loc="left", fontsize=10)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    peak = c19["Palangka Raya"].idxmax()
    fig.suptitle(f"In 2019 the smoke peaked in mid-September; Palangka Raya's worst day was {peak:%d %B}",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


def plot_lags(t):
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    lags = [c for c in t.columns if c.startswith("lag ")]
    for _, r in t.iterrows():
        ls = "-" if r["fires in"] == "Kalimantan" else "--"
        ax.plot(range(len(lags)), r[lags].astype(float), ls, marker="o", ms=3, label=f'{r["fires in"]} → {r["CO at"]}')
    ax.axhline(0, color="grey", lw=0.6)
    ax.set_xlabel("CO measured this many days after the fires"); ax.set_ylabel("correlation of anomalies")
    ax.legend(frameon=False, fontsize=8, ncol=2); ax.spines[["top", "right"]].set_visible(False)
    best = t.loc[t["r at best"].idxmax()]
    ax.set_title(f'Strongest link: {best["fires in"]} fires → CO at {best["CO at"]}, {best["best lag (days)"]} day(s) later (r = {best["r at best"]:.2f})',
                 loc="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    return fig


def plot_hovmoller(t):
    h = hovmoller().pivot_table(index="date", columns="lon", values="co")
    fig, ax = plt.subplots(figsize=(8, 5.5))
    m = ax.pcolormesh(h.columns, h.index, h.values, cmap="YlOrBr", vmin=25, vmax=120, shading="nearest")
    for k, (x, y) in CITIES.items():
        if -3 <= y <= 3:
            ax.axvline(x, color="k", lw=0.5, ls=":"); ax.text(x, h.index[0], k, rotation=90, fontsize=7, va="bottom", ha="right")
    ax.set_xlabel("longitude (°E), mean over 3° S to 3° N"); ax.set_ylabel("2019")
    fig.colorbar(m, ax=ax, label="CO column (mmol/m²)", shrink=0.8)
    ax.set_title("Longitude-time (Hovmöller) diagram: each row is a day (time runs up), each column a strip of longitude.\n"
                 "The smoke builds in September, peaks over Kalimantan first and Sumatra later, and fades in October.",
                 loc="left", fontsize=9.5)
    fig.tight_layout()
    return fig


# PART 6. The peak as a map: 2019 against the same fortnight in 2020 --------------------------------
def peak_mean(y):
    return (ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CO").filterDate(f"{y}-09-08", f"{y}-09-23")
            .select("CO_column_number_density").mean().multiply(1000))


def products():
    frames = FRAME_DAYS
    return [
        {"kind": "animation", "name": "ch71-haze-truecolour", "frames": [truecolour_day(d) for d in frames],
         "region": region(), "width": 540, "fps": 3, "labels": [pd.Timestamp(d).strftime("%d %b %Y") for d in frames],
         "caption": "What the eye sees: MODIS Terra and Aqua true colour every fourth day, August to October 2019. "
                    "Most of each frame is cloud, and where smoke shows it is a grey veil hard to tell from thin cloud."},
        {"kind": "animation", "name": "ch71-haze-co-fires", "frames": [chemistry_frame(d) for d in frames],
         "region": region(), "width": 540, "fps": 3, "labels": [pd.Timestamp(d).strftime("%d %b %Y") for d in frames],
         "caption": "What the chemistry sees: Sentinel-5P carbon monoxide (3-day mean, above 40 mmol/m²) over a "
                    "cloud-free backdrop, with that day's FIRMS fires in red. CO passes through cloud, so the plume "
                    "is continuous where the true-colour view is not."},
        {"kind": "table", "name": "ch71-season", "data": season_table, "floatfmt": ("", "", ".0f", ".0f", ""),
         "caption": "The 2019 season against 2020: fire pixels in the source provinces, and smoky days at each city."},
        {"kind": "chart", "name": "ch71-series", "data": season_table, "plot": plot_series, "live": False,
         "caption": "Three panels, one story: the fires, the smoke over the cities, and the wet-year baseline."},
        {"kind": "chart", "name": "ch71-hovmoller", "data": season_table, "plot": plot_hovmoller, "live": False,
         "caption": "The whole season in one picture."},
        {"kind": "table", "name": "ch71-lags", "data": lag_table,
         "floatfmt": ("", "", ".2f", ".2f", ".2f", ".2f", ".2f", ".2f", ".2f", ".2f", ".0f", ".2f"),
         "caption": "Correlation of day-to-day anomalies in fire counts with CO at each city, for lags of 0 to 7 days."},
        {"kind": "chart", "name": "ch71-lag-chart", "data": lag_table, "plot": plot_lags, "live": False,
         "caption": "How long the smoke takes to arrive."},
        {"kind": "map", "name": "ch71-co-anomaly", "image": peak_mean(2019).subtract(peak_mean(2020)),
         "vis": {"min": -10, "max": 80, "palette": ["#2166ac", "#f7f7f7", "#fee391", "#fe9929", "#cc4c02", "#662506"]},
         "region": region(), "title": "CO, 8-22 September: 2019 minus 2020 (mmol/m²)",
         "source": "Sentinel-5P OFFL L3 CO. GEE.",
         "caption": "The peak fortnight against the same fortnight a year later. The anomaly is centred on the "
                    "peat of Central Kalimantan and southern Sumatra and stretches north-west."},
    ]


if __name__ == "__main__":
    import json
    k = os.path.expanduser(os.environ.get("BOOK_EE_KEY", "~/.config/fullstack-rs/ee-key.json")); info = json.load(open(k))
    ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], k), project=info.get("project_id"))
    print(season_table()); print(lag_table().round(2)); hovmoller()
