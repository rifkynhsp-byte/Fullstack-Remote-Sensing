#| title: Solar resource, suitability and potential electricity (Python)
#| description: Sunlight (GHI), temperature and rainfall from ERA5-Land across Indonesia; a generation model calibrated on the Cirata floating plant (reported capacity and output); applied to rooftops in North Bandung (Google Open Buildings, 30 % of roof area) and to floating panels on Saguling reservoir; suitable open land in the Bandung basin; and the share of household electricity it could cover.

"""
CHAPTER 64 | How much electricity could the sun give here?

    1. resource   ERA5-Land monthly, 2019-2023: global horizontal irradiance
                  (GHI, surface solar radiation downwards, J/m2 -> kWh/m2),
                  2 m air temperature and rainfall
    2. calibrate  Cirata floating PV: 192 MWp, 245-300 GWh/yr reported. With
                  Cirata's GHI this gives the specific yield (kWh/kWp/yr) and
                  the performance ratio PR = yield / GHI. Panel density from the
                  floating solar chapter: 192 MWp on about 149 ha of panels
                  (260 ha including the water lanes).
    3. rooftops   North Bandung: Google Open Buildings v3 (confidence >= 0.75),
                  30 % of each roof covered with modules of 20 % efficiency
                  (0.2 kWp per m2)
    4. reservoir  Saguling: floating panels on 5, 10 or 20 % of the surface,
                  at Cirata's density
    5. land       open land (Dynamic World grass, shrub, bare) on slopes < 10 deg
                  outside protected areas, Bandung basin
    6. needs      a planning assumption of 150 kWh per household per month
                  (stated, not measured); national figures given for context
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ERA = (ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").filterDate("2019-01-01", "2024-01-01")
       .select(["surface_solar_radiation_downwards_sum", "temperature_2m",
                "total_precipitation_sum"], ["ghi", "t2m", "rain"]))
SITES = {"Cirata (floating PV)": [107.334, -6.704], "North Bandung": [107.61, -6.87],
         "Saguling reservoir": [107.40, -6.92], "Kupang, NTT": [123.61, -10.17]}
CIRATA_MWP, CIRATA_GWH = 192, (245, 300)
PANEL_HA, OUTLINE_HA = 149, 260            # from the floating solar chapter
ROOF_SHARE, KWP_PER_M2 = 0.30, 0.20
HH_KWH_MONTH = 150                          # planning assumption
north_bandung = ee.Geometry.Rectangle([107.585, -6.885, 107.635, -6.855], None, False)
basin = ee.Geometry.Rectangle([107.25, -7.15, 107.95, -6.75], None, False)
saguling_box = ee.Geometry.Rectangle([107.30, -7.00, 107.50, -6.85], None, False)

_c = {}


def site_monthly():
    if "sites" in _c:
        return _c["sites"]
    rows = []
    for name, xy in SITES.items():
        fc = ERA.map(lambda i: ee.Feature(None, i.reduceRegion(
            ee.Reducer.first(), ee.Geometry.Point(xy), 11132)).set(
            "month", i.date().get("month")))
        d = pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]])
        g = d.groupby("month").mean()
        for m, r in g.iterrows():
            rows.append({"site": name, "month": int(m), "ghi_kwh_m2_day": r.ghi / 3.6e6 / 30.4,
                         "temp_c": r.t2m - 273.15, "rain_mm": r.rain * 1000})
    _c["sites"] = pd.DataFrame(rows)
    return _c["sites"]


def plot_sites(df):
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.6))
    for n, g in df.groupby("site", sort=False):
        a.plot(g.month, g.ghi_kwh_m2_day, marker="o", ms=3, label=n)
        b.plot(g.month, g.rain_mm, marker="o", ms=3, label=n)
    a.set_ylabel("GHI (kWh/m2/day)"); b.set_ylabel("Rainfall (mm/month)")
    for ax in (a, b):
        ax.set_xticks(range(1, 13)); ax.set_xlabel("Month")
    a.set_title("Sunlight through the year, 2019-2023", loc="left", fontsize=10)
    b.set_title("Rainfall through the year", loc="left", fontsize=10)
    a.legend(frameon=False, fontsize=7)
    fig.tight_layout()
    return fig


def site_table():
    d = site_monthly()
    g = d.groupby("site", sort=False)
    out = pd.DataFrame({"ghi_kwh_m2_day": g.ghi_kwh_m2_day.mean(),
                        "ghi_kwh_m2_year": g.ghi_kwh_m2_day.mean() * 365,
                        "worst_month_share": g.ghi_kwh_m2_day.min() / g.ghi_kwh_m2_day.mean(),
                        "temp_c": g.temp_c.mean(), "rain_mm_year": g.rain_mm.sum()})
    return out.reset_index()


def calibration_table():
    s = site_table().set_index("site")
    h = s.loc["Cirata (floating PV)", "ghi_kwh_m2_year"]
    rows = []
    for gwh in CIRATA_GWH:
        y = gwh * 1e6 / (CIRATA_MWP * 1e3)                # kWh per kWp per year
        rows.append({"reported_gwh_yr": gwh, "ghi_kwh_m2_yr": h, "yield_kwh_per_kwp": y,
                     "performance_ratio": y / h, "mwp_per_ha_panels": CIRATA_MWP / PANEL_HA,
                     "mwp_per_ha_outline": CIRATA_MWP / OUTLINE_HA})
    return pd.DataFrame(rows)


def pr_range():
    c = calibration_table()
    return c.performance_ratio.min(), c.performance_ratio.max()


def rooftop_table():
    b = (ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
         .filterBounds(north_bandung).filter(ee.Filter.gte("confidence", 0.75)))
    n = b.size().getInfo()
    roof = b.aggregate_sum("area_in_meters").getInfo()
    s = site_table().set_index("site").loc["North Bandung"]
    lo, hi = pr_range()
    kwp = roof * ROOF_SHARE * KWP_PER_M2
    rows = []
    for name, pr in (("low PR", lo), ("high PR", hi)):
        mwh = kwp * s.ghi_kwh_m2_year * pr / 1000
        per_bld = mwh * 1000 / n
        rows.append({"case": name, "buildings": n, "roof_ha": roof / 1e4,
                     "panel_ha_30pct": roof * ROOF_SHARE / 1e4, "mwp": kwp / 1000,
                     "gwh_per_year": mwh / 1000, "kwh_per_building_month": per_bld / 12,
                     "share_of_150kwh_need": per_bld / 12 / HH_KWH_MONTH,
                     "worst_month_share": per_bld / 12 / HH_KWH_MONTH * s.worst_month_share})
    return pd.DataFrame(rows)


def reservoir_table():
    occ = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence")
    water = occ.gte(80)
    # Saguling: the connected water body around the reservoir point, inside the box
    ha = (ee.Image.pixelArea().divide(1e4).updateMask(water)
          .reduceRegion(ee.Reducer.sum(), saguling_box, 30, maxPixels=1e10)
          .values().get(0).getInfo())
    s = site_table().set_index("site").loc["Saguling reservoir"]
    lo, hi = pr_range()
    rows = []
    for cover in (0.05, 0.10, 0.20):
        mwp = ha * cover * CIRATA_MWP / OUTLINE_HA
        for name, pr in (("low PR", lo), ("high PR", hi)):
            gwh = mwp * 1e3 * s.ghi_kwh_m2_year * pr / 1e6
            rows.append({"surface_covered": cover, "case": name, "reservoir_ha": ha,
                         "mwp": mwp, "gwh_per_year": gwh,
                         "households_at_150kwh": gwh * 1e6 / (HH_KWH_MONTH * 12)})
    return pd.DataFrame(rows)


# Suitable open land in the Bandung basin
dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(basin)
      .filterDate("2024-01-01", "2025-01-01").select("label").mode())
slope = ee.Terrain.slope(ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic()
                         .setDefaultProjection(ee.Projection("EPSG:4326").atScale(30)))
protected = ee.Image(0).paint(ee.FeatureCollection("WCMC/WDPA/current/polygons")
                              .filterBounds(basin), 1)
open_land = dw.eq(2).Or(dw.eq(5)).Or(dw.eq(7))
suitable = open_land.And(slope.lt(10)).And(protected.Not()).selfMask().clip(basin)


def land_table():
    ha = (ee.Image.pixelArea().divide(1e4).updateMask(suitable)
          .reduceRegion(ee.Reducer.sum(), basin, 30, maxPixels=1e10, tileScale=8)
          .values().get(0).getInfo())
    s = site_table().set_index("site").loc["North Bandung"]
    lo, hi = pr_range()
    mwp = ha * CIRATA_MWP / OUTLINE_HA
    return pd.DataFrame([{"suitable_open_land_ha": ha, "mwp_at_cirata_density": mwp,
                          "gwh_per_year_low": mwp * 1e3 * s.ghi_kwh_m2_year * lo / 1e6,
                          "gwh_per_year_high": mwp * 1e3 * s.ghi_kwh_m2_year * hi / 1e6}])


ghi_year = ERA.select("ghi").mean().divide(3.6e6).divide(30.4).rename("ghi")
indonesia = ee.Geometry.Rectangle([95.0, -11.0, 141.0, 6.0], None, False)


def products():
    return [
        {"kind": "map", "name": "ch64-ghi", "image": ghi_year, "region": indonesia,
         "vis": {"min": 3.8, "max": 6.2, "palette": ["313695", "74add1", "ffffbf",
                                                       "fdae61", "a50026"]},
         "legend": "Mean GHI 2019-2023 (kWh/m2/day)", "title": "Sunlight across Indonesia",
         "source": "ERA5-Land monthly (ECMWF). GEE.",
         "caption": "Mean daily global horizontal irradiance, 2019-2023. Nusa Tenggara gets "
                    "the most sun; the wet mountains of Sumatra, Kalimantan and Papua the "
                    "least."},
        {"kind": "chart", "name": "ch64-sites", "data": site_monthly, "plot": plot_sites,
         "caption": "Monthly sunlight and rainfall at four sites (ERA5-Land, 2019-2023)."},
        {"kind": "table", "name": "ch64-site-table", "data": site_table,
         "floatfmt": ("", ".2f", ",.0f", ".0%", ".1f", ",.0f"),
         "caption": "Mean sunlight, the darkest month as a share of the mean, temperature and "
                    "rainfall per site."},
        {"kind": "table", "name": "ch64-calibration", "data": calibration_table,
         "floatfmt": (",.0f", ",.0f", ",.0f", ".2f", ".2f", ".2f"),
         "caption": "Calibration on Cirata: reported output and capacity against the "
                    "satellite sunlight."},
        {"kind": "table", "name": "ch64-rooftops", "data": rooftop_table,
         "floatfmt": ("", ",.0f", ",.1f", ",.1f", ",.1f", ",.1f", ",.0f", ".0%", ".0%"),
         "caption": "North Bandung rooftops with 30 % of the roof area covered, and the "
                    "share of a 150 kWh/month household need per building."},
        {"kind": "table", "name": "ch64-reservoir", "data": reservoir_table,
         "floatfmt": (".0%", "", ",.0f", ",.0f", ",.0f", ",.0f"),
         "caption": "Floating panels on Saguling reservoir at Cirata's density."},
        {"kind": "map", "name": "ch64-land", "image": suitable, "region": basin,
         "vis": {"palette": ["d95f02"]},
         "classes": [("open land, slope < 10 deg, not protected", "#d95f02")],
         "title": "Open land that could host solar, Bandung basin",
         "source": "Dynamic World 2024; Copernicus GLO-30; WDPA. GEE.",
         "caption": "Grass, shrub or bare land on gentle slopes outside protected areas. A "
                    "first screen only: ownership, grid distance and food land come next."},
        {"kind": "table", "name": "ch64-land-table", "data": land_table,
         "floatfmt": (",.0f", ",.0f", ",.0f", ",.0f"),
         "caption": "Suitable open land and its potential at Cirata's density."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(site_table())
