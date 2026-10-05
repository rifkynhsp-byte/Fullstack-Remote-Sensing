#| title: MRV for forest carbon: a worked district example (Python)
#| description: Activity data from two independent forest-loss maps, an emission factor from GEDI biomass with its uncertainty, Monte Carlo emissions, a reference level and a results table, for Tebo district, Jambi.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 41 | Measurement, Reporting and Verification, done once, end to end.

IPCC gain-loss logic for deforestation:

    emissions (t CO2) = activity data (ha lost) × emission factor (t CO2 per ha)

    emission factor  = AGB × (1 + R) × CF × 44/12
        AGB   above-ground biomass of the forest being cleared (Mg/ha)  GEDI L4B
        R     root-to-shoot ratio, tropical rainforest      0.37  (IPCC 2006 default)
        CF    carbon fraction of dry matter                 0.47  (IPCC 2006 default)
        44/12 carbon to carbon dioxide

Activity data come from two independent maps, so the effect of choosing a
map is visible: Hansen GFC and JRC Tropical Moist Forest (TMF).
Reference period 2013-2019; monitoring period 2020-2023.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

district = (ee.FeatureCollection("FAO/GAUL/2025/level2")
            .filter(ee.Filter.eq("GAUL1_NAME", "Jambi"))
            .filter(ee.Filter.eq("GAUL2_NAME", "Tebo")).geometry())
YEARS = list(range(2013, 2024))
REF, MON = (2013, 2019), (2020, 2023)
R, CF = 0.37, 0.47

gfc = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")
tmf_col = ee.ImageCollection("projects/JRC/TMF/v1_2023/AnnualChanges")
# mosaic() drops the native projection; put it back so it can be aggregated later.
tmf = tmf_col.mosaic().setDefaultProjection(tmf_col.first().projection())

# Hansen: tree cover >= 30 % in 2000, lost in year Y (lossyear = Y - 2000).
hansen_forest = gfc.select("treecover2000").gte(30)


def hansen_loss(y):
    return hansen_forest.And(gfc.select("lossyear").eq(y - 2000))


# TMF: forest (undisturbed 1, degraded 2, regrowth 4) in Dec Y-1, deforested (3) in Dec Y.
def tmf_loss(y):
    before = tmf.select(f"Dec{y - 1}")
    after = tmf.select(f"Dec{y}")
    return before.remap([1, 2, 4], [1, 1, 1], 0).eq(1).And(after.eq(3))


def activity_data():
    area = ee.Image.pixelArea().divide(1e4)                          # hectares
    stack = ee.Image.cat([hansen_loss(y).rename(f"h{y}") for y in YEARS] +
                         [tmf_loss(y).rename(f"t{y}") for y in YEARS]).multiply(area)
    s = stack.reduceRegion(ee.Reducer.sum(), district, 30, maxPixels=1e11,
                           tileScale=8).getInfo()
    return pd.DataFrame([{"year": y, "hansen_ha": s[f"h{y}"], "tmf_ha": s[f"t{y}"]}
                         for y in YEARS])


# Emission factor: GEDI L4B gridded biomass (1 km) over forest that is still
# intact in 2020 (TMF undisturbed), the closest thing to "forest about to be
# cleared" available everywhere.
l4b = ee.Image("LARSE/GEDI/GEDI04_B_002")
intact = tmf.select("Dec2020").eq(1)


def emission_factor():
    share_intact = (intact.reduceResolution(ee.Reducer.mean(), True, 2048)
                    .reproject(l4b.projection()))                     # share of each 1 km cell
    m = l4b.select(["MU", "SE"]).updateMask(share_intact.gte(0.5))
    s = m.reduceRegion(ee.Reducer.mean().combine(ee.Reducer.count(), None, True), district,
                       1000, maxPixels=1e9).getInfo()
    agb, se = s["MU_mean"], s["SE_mean"]
    ef = agb * (1 + R) * CF * 44 / 12
    return pd.DataFrame([{"gedi_cells": s["MU_count"], "agb_Mg_ha": agb,
                          "agb_se_Mg_ha": se, "relative_se": se / agb,
                          "root_shoot": R, "carbon_fraction": CF,
                          "ef_tCO2_ha": ef}])


_c = {}


def _data():
    if not _c:
        _c["ad"], _c["ef"] = activity_data(), emission_factor()
    return _c["ad"], _c["ef"]


def emissions_frame(n=5000, seed=1):
    """Monte Carlo. EF: AGB ~ Normal(mean, SE), treated as fully correlated across the
    district (conservative). CF: IPCC 2006 Table 4.3 gives 0.47 (0.44-0.49), taken as a
    95 % range (sd ≈ 0.0128). R: IPCC 2006 Table 4.4 gives 0.37 with no range; ± 30 %
    (1 sd) is OUR assumption, stated so it can be changed. AD: the two maps are
    reported side by side; their spread stands in for AD uncertainty until a
    reference sample exists (chapter “Accuracy Assessment”)."""
    ad, ef = _data()
    rng = np.random.default_rng(seed)
    agb = ef.agb_Mg_ha[0] + ef.agb_se_Mg_ha[0] * rng.standard_normal(n)
    r = R * (1 + 0.30 * rng.standard_normal(n))
    cf = CF + 0.0128 * rng.standard_normal(n)
    ef_draws = agb * (1 + r) * cf * 44 / 12
    rows = []
    for _, a in ad.iterrows():
        for src in ["hansen", "tmf"]:
            e = a[f"{src}_ha"] * ef_draws / 1e6                      # Mt CO2
            rows.append({"year": int(a.year), "source": src.upper() if src == "tmf" else "Hansen",
                         "Mt_CO2": np.median(e), "p05": np.percentile(e, 5),
                         "p95": np.percentile(e, 95)})
    return pd.DataFrame(rows)


def plot_ad(df):
    fig, ax = plt.subplots(figsize=(8, 3.4))
    w = 0.38
    ax.bar(df.year - w / 2, df.hansen_ha / 1000, w, color="#c0392b", label="Hansen GFC")
    ax.bar(df.year + w / 2, df.tmf_ha / 1000, w, color="#2a78d6", label="JRC TMF")
    ax.axvspan(REF[0] - 0.5, REF[1] + 0.5, color="#9aa5b1", alpha=0.12)
    ax.text(REF[0] - 0.4, ax.get_ylim()[1] * 0.92, "reference period", fontsize=8)
    ax.set_ylabel("Forest lost (thousand ha)")
    ax.set_title("Activity data, Tebo: two maps, two answers every year", loc="left",
                 fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def plot_emissions(df):
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for (src, d), c, off in zip(df.groupby("source"), ["#c0392b", "#2a78d6"], [-0.12, 0.12]):
        ax.errorbar(d.year + off, d.Mt_CO2, yerr=[d.Mt_CO2 - d.p05, d.p95 - d.Mt_CO2],
                    fmt="o", color=c, ms=4, capsize=2, label=f"{src} (90 % interval)")
        ref = d[(d.year >= REF[0]) & (d.year <= REF[1])].Mt_CO2.mean()
        ax.hlines(ref, REF[0] - 0.4, MON[1] + 0.4, colors=c, linestyles="--", lw=1)
    ax.set_ylabel("Emissions (Mt CO₂ per year)")
    ax.set_title("Gross deforestation emissions with uncertainty; dashed: reference level "
                 "(2013-2019 mean)", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def results_table(df):
    rows = []
    for src, d in df.groupby("source"):
        ref = d[(d.year >= REF[0]) & (d.year <= REF[1])].Mt_CO2.mean()
        mon = d[(d.year >= MON[0]) & (d.year <= MON[1])].Mt_CO2.mean()
        rows.append({"activity data": src, "reference_level_Mt_yr": ref,
                     "monitoring_mean_Mt_yr": mon, "reduction_Mt_yr": ref - mon,
                     "reduction_pct": (ref - mon) / ref})
    return pd.DataFrame(rows)


loss_year = gfc.select("lossyear").updateMask(
    hansen_forest.And(gfc.select("lossyear").gte(13)).And(gfc.select("lossyear").lte(23))
).add(2000).clip(district)


def products():
    return [
        {"kind": "map", "name": "ch41-loss-map", "image": loss_year,
         "region": district.bounds(),
         "vis": {"min": 2013, "max": 2023, "palette": ["fde725", "5ec962", "21918c", "3b528b",
                                                        "440154"]},
         "legend": "Year of forest loss (Hansen GFC)",
         "title": "Where Tebo's forest went, 2013-2023",
         "source": "Hansen et al. GFC v1.13; GAUL 2025. GEE.",
         "caption": "Activity data on the map: every 30 m pixel of forest loss, coloured by "
                    "year."},
        {"kind": "table", "name": "ch41-ad", "data": lambda: _data()[0],
         "floatfmt": (".0f", ",.0f", ",.0f"),
         "caption": "Hectares of forest lost per year by each map. The two use different "
                    "forest definitions and methods; neither is 'the truth'."},
        {"kind": "chart", "name": "ch41-ad-chart", "data": lambda: _data()[0], "plot": plot_ad,
         "caption": "Activity data from both maps."},
        {"kind": "table", "name": "ch41-ef", "data": lambda: _data()[1],
         "floatfmt": (",.0f", ".0f", ".1f", ".1%", ".2f", ".2f", ".0f"),
         "caption": "Emission factor: GEDI L4B biomass over intact forest, IPCC default "
                    "root-to-shoot ratio and carbon fraction."},
        {"kind": "chart", "name": "ch41-emissions", "data": emissions_frame,
         "plot": plot_emissions,
         "caption": "Annual gross emissions from deforestation with Monte Carlo 90 % "
                    "intervals for the emission factor, for each activity-data source."},
        {"kind": "table", "name": "ch41-results", "data": emissions_frame,
         "transform": results_table, "floatfmt": ("", ".2f", ".2f", ".2f", ".0%"),
         "caption": "The results table an MRV report would carry: reference level, "
                    "monitoring-period result and the reduction, for each map."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(activity_data())
