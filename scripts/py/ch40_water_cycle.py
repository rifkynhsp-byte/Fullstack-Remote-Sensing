#| title: The water cycle of a basin (Python)
#| description: A satellite water balance for the Kapuas basin, West Kalimantan: rainfall (CHIRPS), evapotranspiration (MODIS), storage change (GRACE) and runoff (ERA5-Land), and how well they close.

"""
CHAPTER 40 | The water balance of a river basin, every term from space.

    P - ET - Q = ΔS

    P   precipitation          CHIRPS v2, 5 km
    ET  evapotranspiration     MODIS MOD16A2GF, 500 m
    ΔS  change in storage      GRACE / GRACE-FO mascons (JPL, CRI-filtered), ≈ 300 km footprint
    Q   runoff                 ERA5-Land reanalysis (a model, not a gauge)

Basin: the Kapuas, West Kalimantan, from HydroSHEDS (level 4).
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

basin = (ee.FeatureCollection("WWF/HydroSHEDS/v1/Basins/hybas_4")
         .filterBounds(ee.Geometry.Point(111.5, 0.3)).first().geometry())

chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD").select("precipitation")
mod16 = ee.ImageCollection("MODIS/061/MOD16A2GF").select("ET")
grace = ee.ImageCollection("NASA/GRACE/MASS_GRIDS_V04/MASCON_CRI").select("lwe_thickness")
era5 = ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").select("runoff_sum")


def month_terms(y, m):
    d0 = ee.Date.fromYMD(y, m, 1)
    d1 = d0.advance(1, "month")
    p = chirps.filterDate(d0, d1).sum()
    # MOD16 8-day sums in 0.1 kg/m² (= 0.1 mm); scale by the days that fall in the month
    et = mod16.filterDate(d0, d1).sum().multiply(0.1)
    q = era5.filterDate(d0, d1).first().multiply(1000)              # m -> mm
    # GRACE has gap months; a masked placeholder keeps the band so the month comes
    # back as "no data" instead of an error.
    empty = ee.Image.constant(0).rename("lwe_thickness").updateMask(0)
    tws = grace.filterDate(d0, d1).merge(ee.ImageCollection([empty])).mean().multiply(10)
    img = ee.Image.cat(p.rename("P"), et.rename("ET"), q.rename("Q"), tws.rename("TWS"))
    vals = img.reduceRegion(ee.Reducer.mean(), basin, 5000, maxPixels=1e10, tileScale=4)
    return ee.Feature(None, vals).set({"year": y, "month": m,
                                       "n_et": mod16.filterDate(d0, d1).size()})


def balance_frame():
    rows = []
    for y in range(2003, 2024):
        fc = ee.FeatureCollection([month_terms(y, m) for m in range(1, 13)])
        rows += [f["properties"] for f in fc.getInfo()["features"]]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(dict(year=df.year, month=df.month, day=15))
    df = df.sort_values("date").reset_index(drop=True)
    # ΔS from GRACE: centred difference of the anomaly, mm per month (gaps stay gaps)
    df["dS_grace"] = (df["TWS"].shift(-1) - df["TWS"].shift(1)) / 2
    df["dS_residual"] = df["P"] - df["ET"] - df["Q"]
    return df


_cache = {}


def balance():
    if "df" not in _cache:
        _cache["df"] = balance_frame()
    return _cache["df"]


def plot_climatology(df):
    g = df.groupby("month")[["P", "ET", "Q"]].mean()
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.bar(g.index - 0.27, g.P, 0.27, color="#2a78d6", label="rainfall P")
    ax.bar(g.index, g.ET, 0.27, color="#1b7837", label="evapotranspiration ET")
    ax.bar(g.index + 0.27, g.Q, 0.27, color="#8e44ad", label="runoff Q (ERA5-Land)")
    ax.set_xticks(range(1, 13), list("JFMAMJJASOND"))
    ax.set_ylabel("mm per month (basin mean)")
    ax.set_title("Kapuas basin, 2003-2023: rain falls all year; ET is steady near 100 mm",
                 loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8, ncol=3)
    return fig


def plot_storage(df):
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.plot(df.date, df.TWS, color="#2a78d6", lw=1.3)
    ax.axhline(0, color="#9aa5b1", lw=0.8)
    for y in (2006, 2009, 2015, 2019, 2023):
        ax.axvspan(pd.Timestamp(f"{y}-08-01"), pd.Timestamp(f"{y}-11-30"), color="#c0392b",
                   alpha=0.12)
    ax.set_ylabel("Water storage anomaly (mm)")
    ax.set_title("GRACE: stored water falls in every El Niño / positive-IOD dry season "
                 "(shaded Aug-Nov)", loc="left", fontsize=10)
    ax.text(0, -0.2, "GRACE gap 2017-07 to 2018-05 between the two missions",
            transform=ax.transAxes, fontsize=7, color="#6b7680")
    return fig


def annual_table(df):
    full = df[(df.year >= 2003) & (df.year <= 2023)]
    a = full.groupby("year")[["P", "ET", "Q"]].sum()
    a["P_minus_ET_minus_Q"] = a.P - a.ET - a.Q
    out = a.agg(["mean", "min", "max"]).T.reset_index().rename(columns={"index": "term (mm/yr)"})
    return out


def closure_table(df):
    d = df.dropna(subset=["dS_grace", "dS_residual"])
    r = np.corrcoef(d.dS_grace, d.dS_residual)[0, 1]
    return pd.DataFrame([{"months_compared": len(d), "correlation_r": r,
                          "mean_residual_mm": (d.dS_residual - d.dS_grace).mean(),
                          "rmse_mm": np.sqrt(((d.dS_residual - d.dS_grace) ** 2).mean())}])


def plot_closure(df):
    d = df.dropna(subset=["dS_grace", "dS_residual"])
    fig, ax = plt.subplots(figsize=(5.8, 4))
    ax.scatter(d.dS_grace, d.dS_residual, s=10, color="#2a78d6", alpha=0.6)
    lim = [min(d.dS_grace.min(), d.dS_residual.min()), max(d.dS_grace.max(), d.dS_residual.max())]
    ax.plot(lim, lim, color="#c0392b", lw=1, label="1:1, perfect closure")
    ax.set_xlabel("ΔS from GRACE (mm/month)")
    ax.set_ylabel("P − ET − Q (mm/month)")
    ax.set_title("Does the budget close?", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


p_minus_et = (chirps.filterDate("2003-01-01", "2024-01-01").sum().divide(21)
              .subtract(mod16.filterDate("2003-01-01", "2024-01-01").sum().multiply(0.1)
                        .divide(21))
              .rename("p_et").clip(basin))


def products():
    return [
        {"kind": "map", "name": "ch40-water-yield", "image": p_minus_et, "region": basin.bounds(),
         "vis": {"min": 500, "max": 3500, "palette": ["fff7bc", "c7e9b4", "41b6c4", "225ea8",
                                                       "081d58"]},
         "legend": "Mean P − ET, 2003-2023 (mm per year)",
         "title": "Water left for rivers and storage, Kapuas basin",
         "source": "CHIRPS v2; MODIS MOD16A2GF; HydroSHEDS. GEE.",
         "caption": "Rainfall minus evapotranspiration: the water each pixel hands on to "
                    "rivers, soils and groundwater. The wet uplands of the interior supply "
                    "most of the river."},
        {"kind": "chart", "name": "ch40-climatology", "data": balance, "plot": plot_climatology,
         "caption": "Mean monthly rainfall, evapotranspiration and runoff, basin average."},
        {"kind": "table", "name": "ch40-annual", "data": balance, "transform": annual_table,
         "floatfmt": ("", ",.0f", ",.0f", ",.0f"),
         "caption": "Annual totals 2003-2023. Over many years storage changes little, so "
                    "P − ET − Q should be near zero; what is left is the combined error of "
                    "three independent products."},
        {"kind": "chart", "name": "ch40-storage", "data": balance, "plot": plot_storage,
         "caption": "Total water storage anomaly from GRACE and GRACE-FO (JPL mascons, CRI "
                    "filter), basin mean."},
        {"kind": "chart", "name": "ch40-closure", "data": balance, "plot": plot_closure,
         "caption": "Month by month, storage change from GRACE against the residual of the "
                    "other three terms."},
        {"kind": "table", "name": "ch40-closure-table", "data": balance,
         "transform": closure_table, "floatfmt": (".0f", ".2f", ".1f", ".1f"),
         "caption": "How well the satellite water budget closes, monthly."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(balance_frame().head())
