#| title: Oil palm from age to height, biomass, health and fruit (Python)
#| description: Building on the planting-year map of the oil palm age chapter (Kotawaringin Timur). GEDI height and GEDI biomass at the same footprints by age, a data-driven height-to-biomass curve, canopy health relative to each palm's own age group from Sentinel-2, and a transparent fresh-fruit-bunch model (age curve and biomass proportion) with annual and monthly totals.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 60 | From the age of a palm to the fruit it can bear.

    1. age        planting year from the Landsat archive (oil palm age chapter)
    2. height     GEDI L2A rh98, good-quality shots, 2019-2023
    3. biomass    oil palm allometry from height, the three height-based equations
                  compared for Indonesian oil palm by Hardiyanti et al. (2026):
                    Khalid (1999)     AGB = 725 + 197 H  (kg per palm; x 136 palms/ha)
                    Dewi (2009)       AGB = 0.0976 H + 0.076  (as reported, t/ha)
                  H = total height (GEDI rh98). Palm DBH barely changes once the
                  trunk forms (48-58 cm in 35-year-old palms), so height carries
                  the biomass signal and a height->DBH step adds nothing.
                  GEDI L4A biomass (a GLOBAL allometry, not built for palms) is
                  shown only for comparison, with field benchmarks.
    4. health     Sentinel-2 NDVI (2023 dry season) compared with the median of
                  palms of the SAME age: a palm is flagged when it is 0.05 or
                  more below its own age group. Pixels that Dynamic World calls
                  water, built or bare, or that the author's 10-class model calls
                  open land or water (ponds, bare patches), are removed first;
                  then low-NDVI lines 1-2 pixels wide (estate roads and drains,
                  too narrow for either map) are removed by a morphological opening.
    5. fruit      fresh fruit bunches (FFB), two transparent estimates:
                  a) age curve: potential rises from age 3 to a peak at 9 years,
                     plateau to 18, declines to 25; peak potential 34.5 t/ha/yr
                     (research-institute standard at age 9-10), multiplied by an
                     achievement ratio of 0.42 (Indonesian smallholder average
                     share of attainable yield)
                  b) biomass proportion: the same peak, scaled by the palm's
                     Khalid biomass relative to the median of prime-age palms.
                     A proportion cancels the units, so the unit doubts in (3)
                     do not affect it.
       Both are models with stated assumptions. Real numbers need mill records.
"""

import sys
from pathlib import Path

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ch44_oil_palm_age as base  # noqa: E402  (aoi, palm, age)

aoi, palm, age = base.aoi, base.palm, base.age
PEAK_T_HA = 34.5           # potential FFB at age 9-10 (Daud et al. 2026, PPKS standard)
ACHIEVE = 0.42             # actual / attainable, smallholders (Monzon et al. 2023)
LOW = 0.05                 # NDVI below the age-group median that counts as "below"


def quality(col, flag):
    return (ee.ImageCollection(col).filterBounds(aoi).filterDate("2019-04-01", "2024-01-01")
            .map(lambda i: i.updateMask(i.select(flag).eq(1).And(i.select("degrade_flag").eq(0)))))


rh98 = quality("LARSE/GEDI/GEDI02_A_002_MONTHLY", "quality_flag").select("rh98").mosaic()
agbd = quality("LARSE/GEDI/GEDI04_A_002_MONTHLY", "l4_quality_flag").select("agbd").mosaic()
both = rh98.mask().And(agbd.mask()).And(age.mask()).rename("s").toInt()

_c = {}


def shots():
    """GEDI footprints on palm pixels with height, biomass and age."""
    if "shots" not in _c:
        fc = (rh98.addBands(agbd).addBands(age).addBands(both)
              .stratifiedSample(numPoints=4000, classBand="s", region=aoi, scale=25, seed=5,
                                tileScale=8, classValues=[1], classPoints=[4000]))
        d = pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]])
        d = d[(d.rh98 > 0) & (d.rh98 < 40) & (d.agbd >= 0) & (d.age >= 1)]
        _c["shots"] = d
    return _c["shots"]


PALMS_HA = 136                 # planting density used to convert per-palm biomass


def khalid(h):
    """Khalid (1999) as applied by Hardiyanti et al. (2026): kg/palm -> Mg/ha."""
    return (725 + 197 * np.asarray(h, float)) * PALMS_HA / 1000


def dewi(h):
    """Dewi et al. (2009) as reported by Hardiyanti et al. (2026), t/ha."""
    return 0.0976 * np.asarray(h, float) + 0.076


# Field benchmarks (Mg/ha), all from destructive or field studies:
BENCH = [(7, 22.2, "Sunaryathy 2016, 4-10 yr, destructive"),
         (15, 105.4, "Sunaryathy 2016, 11-20 yr, destructive"),
         (12, 6.39 * 12, "Lewis et al. 2020, 6.39 Mg/ha/yr x 12 yr, on peat"),
         (14, 40.8, "Asari et al. 2013, Corley & Tinker eq., mature"),
         (14, 47.2, "Asari et al. 2013, Khalid eq., mature")]


def by_age_table():
    d = shots()
    g = d.groupby(d.age.astype(int))
    out = pd.DataFrame({"shots": g.size(), "height_median_m": g.rh98.median()})
    out["agb_khalid_mg_ha"] = khalid(out.height_median_m)
    out["agb_dewi_as_reported"] = dewi(out.height_median_m)
    out["agb_gedi_l4a_global"] = g.agbd.median()
    out = out[out.shots >= 10].reset_index().rename(columns={"age": "age_years"})
    return out


def plot_by_age(df):
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.8))
    a.plot(df.age_years, df.height_median_m, color="#1a9850", marker="o", ms=3)
    a.set_xlabel("Palm age (years)"); a.set_ylabel("GEDI rh98, median (m)")
    a.set_title("Height grows with age", loc="left", fontsize=10)
    b.plot(df.age_years, df.agb_khalid_mg_ha, color="#d7301f", marker="o", ms=3,
           label="Khalid (1999), palm equation")
    b.plot(df.age_years, df.agb_dewi_as_reported, color="#4575b4", marker="s", ms=3,
           label="Dewi (2009), as reported")
    b.plot(df.age_years, df.agb_gedi_l4a_global, color="#7f7f7f", ls="--",
           label="GEDI L4A (global, not for palms)")
    for x, y, _ in BENCH:
        b.scatter(x, y, marker="*", s=90, color="black", zorder=5)
    b.scatter([], [], marker="*", s=90, color="black", label="field studies")
    b.set_yscale("log")
    b.set_xlabel("Palm age (years)"); b.set_ylabel("AGB (Mg/ha, log scale)")
    b.set_title("Same heights, three equations, 300-fold apart", loc="left", fontsize=10)
    b.legend(frameon=False, fontsize=7, loc="lower right")
    fig.tight_layout()
    return fig


def equation_table():
    d = shots()
    prime = d[(d.age >= 9) & (d.age <= 18)]
    rows = []
    for name, fn, unit in [("Khalid (1999): (725 + 197 H) kg/palm x 136/ha", khalid, "Mg/ha"),
                           ("Dewi (2009): 0.0976 H + 0.076", dewi, "t/ha as reported")]:
        rows.append({"equation": name, "units": unit, "agb_at_10m": float(fn(10)),
                     "agb_at_15m": float(fn(15)),
                     "prime_age_median": float(np.median(fn(prime.rh98)))})
    rows.append({"equation": "GEDI L4A (global allometry)", "units": "Mg/ha",
                 "agb_at_10m": np.nan, "agb_at_15m": np.nan,
                 "prime_age_median": float(prime.agbd.median())})
    rows.append({"equation": "Field studies, mature palms (range)", "units": "Mg/ha",
                 "agb_at_10m": np.nan, "agb_at_15m": np.nan, "prime_age_median": np.nan})
    df = pd.DataFrame(rows)
    df.loc[df.index[-1], "units"] = "41-105 Mg/ha"
    return df


# Health: NDVI against the median of palms of the same age.
s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi)
      .filterDate("2023-06-01", "2023-10-01")
      .linkCollection(ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"), ["cs"])
      .map(lambda i: i.updateMask(i.select("cs").gte(0.6)))
      .median())
# Not palm canopy: estate roads, drains, ponds and bare edges are mapped as "palm" by the
# oil palm layer. Remove them before judging health, with two independent maps:
#   Dynamic World 2023 (mode): water, built or bare
#   the author's 10-class model (embeddings + SRTM elevation and slope): open land or water
dw23 = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(aoi)
        .filterDate("2023-01-01", "2024-01-01").select("label").mode())
dw_not_palm = dw23.eq(0).Or(dw23.eq(6)).Or(dw23.eq(7))
srtm = ee.Image("USGS/SRTMGL1_003").select("elevation")
author_stack = ee.Image.cat([
    ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
    .filter(ee.Filter.calendarRange(2023, 2023, "year")).mosaic(),
    srtm, ee.Terrain.slope(srtm)])
author_class = author_stack.classify(
    ee.Classifier.load("projects/ee-rifkynauvalhsp2/assets/LULC_Classifier_Embeddings_Topo_rubber"))
author_not_palm = author_class.eq(3).Or(author_class.eq(4))          # open land, water
not_palm = dw_not_palm.Or(author_not_palm)
core = age.mask().And(not_palm.Not())
ndvi = s2.normalizedDifference(["B8", "B4"]).rename("ndvi").updateMask(core)
age_int = age.toInt().rename("age_int")


def cohort_median():
    if "cm" not in _c:
        g = (ndvi.addBands(age_int).reduceRegion(ee.Reducer.median().group(1, "age_int"), aoi,
                                                 30, maxPixels=1e10, tileScale=16)
             .get("groups").getInfo())
        _c["cm"] = {int(x["age_int"]): x["median"] for x in g if x.get("median") is not None}
    return _c["cm"]


def health_image():
    cm = cohort_median()
    keys = sorted(cm)
    expected = age_int.remap(keys, [cm[k] for k in keys]).rename("expected")
    dev = ndvi.subtract(expected).rename("dev")
    # Estate roads and drains are 5-8 m wide: too narrow for Dynamic World or the
    # 10-class model to see at 10 m. They show up as low-NDVI LINES one or two pixels
    # wide. A morphological opening (erode, then dilate) of the low mask keeps weak
    # blocks and drops the lines; the dropped pixels are masked out as "not palm".
    low = dev.lt(-LOW).unmask(0)
    opened = low.focalMin(1, "square", "pixels").focalMax(1, "square", "pixels")
    lines = low.And(opened.Not())
    return dev.updateMask(lines.Not())


def health_table():
    dev = health_image()
    stage = (ee.Image(0).where(age.gte(3).And(age.lt(9)), 2).where(age.gte(9).And(age.lt(19)), 3)
             .where(age.gte(19).And(age.lt(25)), 4).where(age.gte(25), 5)
             .where(age.lt(3), 1).updateMask(age.mask()).rename("stage"))
    area = ee.Image.pixelArea().divide(1e4)
    # Same mask on both bands: area where below (else 0), and all palm area.
    img = (area.multiply(dev.lt(-LOW)).rename("low")
           .addBands(area.updateMask(dev.mask()).rename("all")).addBands(stage))
    g = (img.reduceRegion(ee.Reducer.sum().repeat(2).group(2, "stage"), aoi, 30,
                          maxPixels=1e10, tileScale=16).get("groups").getInfo())
    names = {1: "immature (0-2 yr)", 2: "young (3-8 yr)", 3: "prime (9-18 yr)",
             4: "mature (19-24 yr)", 5: "replanting due (25+ yr)"}
    rows = [{"life stage": names[int(x["stage"])], "palm_ha": x["sum"][1],
             "below_age_group_ha": x["sum"][0], "share_below": x["sum"][0] / x["sum"][1]}
            for x in g if int(x["stage"]) in names and x["sum"][1]]
    return pd.DataFrame(rows)


def mask_table():
    area = ee.Image.pixelArea().divide(1e4).updateMask(age.mask())
    imgs = {"oil palm map (age known)": ee.Image(1), "Dynamic World: water, built, bare": dw_not_palm,
            "author's model: open land, water": author_not_palm, "removed by either": not_palm,
            "kept for health scoring": not_palm.Not()}
    rows = []
    for name, m in imgs.items():
        ha = area.updateMask(m).reduceRegion(ee.Reducer.sum(), aoi, 30, maxPixels=1e10,
                                             tileScale=16).values().get(0).getInfo()
        rows.append({"layer": name, "ha": ha})
    df = pd.DataFrame(rows)
    df["share_of_palm_map"] = df.ha / df.ha.iloc[0]
    return df


def potential(a):
    """FFB potential (t/ha/yr) by age: rise 3-9, plateau 9-18, decline to 70 % at 25."""
    a = np.asarray(a, float)
    p = np.where(a < 3, 0, np.where(a < 9, (a - 3) / 6, np.where(a <= 18, 1,
                 np.where(a <= 25, 1 - 0.3 * (a - 18) / 7, 0.7))))
    return PEAK_T_HA * p


def fruit_table():
    """At GEDI footprints: FFB from the age curve and from the biomass proportion."""
    d = shots().copy()
    d["agb_k"] = khalid(d.rh98)
    ref = d[(d.age >= 9) & (d.age <= 18)].agb_k.median()      # units cancel in the ratio
    d["ffb_age_curve"] = potential(d.age) * ACHIEVE
    d["ffb_biomass_prop"] = np.clip(d.agb_k / ref, 0, 1.5) * PEAK_T_HA * ACHIEVE
    d["ffb_biomass_prop"] = np.where(d.age < 3, 0, d.ffb_biomass_prop)
    r = np.corrcoef(d.ffb_age_curve, d.ffb_biomass_prop)[0, 1]
    _c["fruit_pts"] = d
    g = d.groupby(pd.cut(d.age, [0, 3, 9, 19, 25, 60], right=False,
                         labels=["0-2", "3-8", "9-18", "19-24", "25+"]), observed=True)
    out = pd.DataFrame({"shots": g.size(), "ffb_age_curve_t_ha": g.ffb_age_curve.mean(),
                        "ffb_biomass_prop_t_ha": g.ffb_biomass_prop.mean()}).reset_index()
    out = out.rename(columns={"age": "age class"})
    out["prime_age_median_agb_khalid"] = ref
    out["corr_between_methods"] = r
    return out


def monthly_table():
    """Landscape FFB per month from the age-curve model (seasonality not modelled)."""
    stage_ha = []
    g = (ee.Image.pixelArea().divide(1e4).addBands(age_int)
         .reduceRegion(ee.Reducer.sum().group(1, "age_int"), aoi, 30, maxPixels=1e10,
                       tileScale=16).get("groups").getInfo())
    for x in g:
        stage_ha.append((int(x["age_int"]), x["sum"]))
    df = pd.DataFrame(stage_ha, columns=["age", "ha"])
    df["t_per_year"] = potential(df.age) * ACHIEVE * df.ha
    annual = df.t_per_year.sum()
    months = pd.date_range("2024-01-01", periods=12, freq="MS")
    return pd.DataFrame({"month": months.strftime("%Y-%m"),
                         "ffb_tonnes_model": annual / 12,
                         "palm_ha_mapped": df.ha.sum(),
                         "mean_t_ha_yr": annual / df.ha.sum()})


def plot_monthly(df):
    fig, ax = plt.subplots(figsize=(6.8, 3.0))
    ax.bar(df.month.str[5:], df.ffb_tonnes_model / 1000, color="#e6550d")
    ax.set_ylabel("FFB (thousand t)")
    ax.set_xlabel("Month of 2024")
    ax.set_title("Modelled fresh fruit bunches per month (flat: seasonality not modelled)",
                 loc="left", fontsize=9)
    return fig


def health_vis():
    """Three classes instead of a colour ramp: as expected, below, well below."""
    dev = health_image()
    cls = (ee.Image(1).where(dev.lt(-0.05), 2).where(dev.lt(-0.15), 3)
           .updateMask(dev.mask()))
    return cls.visualize(min=1, max=3, palette=["d9f0d3", "fdae61", "b2182b"])



# ---------------------------------------------------------------------------
# Fruit as a MAP, not only a total: the age curve per pixel, discounted by canopy health
# ---------------------------------------------------------------------------
HEALTH_MULT = (1.0, 0.9, 0.6)      # as expected / below / well below: assumed costs, as in the drone chapter
DESA = ee.FeatureCollection("projects/shaped-producer-482312-m0/assets/ijb/idn_desa_bps").filterBounds(aoi)


def ffb_image():
    """Modelled FFB in t/ha/yr for every palm pixel: potential(age) x achievement x health multiplier."""
    a = age.toFloat()
    pot = (ee.Image(0).where(a.gte(3).And(a.lt(9)), a.subtract(3).divide(6))
           .where(a.gte(9).And(a.lte(18)), 1)
           .where(a.gt(18).And(a.lte(25)), ee.Image(1).subtract(a.subtract(18).multiply(0.3 / 7)))
           .where(a.gt(25), 0.7)).multiply(PEAK_T_HA * ACHIEVE)
    dev = health_image()
    mult = (ee.Image(HEALTH_MULT[0]).where(dev.lt(-0.05), HEALTH_MULT[1]).where(dev.lt(-0.15), HEALTH_MULT[2]))
    return pot.multiply(mult).updateMask(dev.mask()).rename("ffb")


def ffb_desa():
    """Tonnes and t/ha per desa (official BPS boundaries), the unit a district office plans with."""
    ffb = ffb_image()
    stack = ffb.multiply(ee.Image.pixelArea().divide(1e4)).rename("t").addBands(ee.Image.pixelArea().divide(1e4).updateMask(ffb.mask()).rename("ha"))
    fc = stack.reduceRegions(DESA, ee.Reducer.sum(), 30, tileScale=16)
    d = pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]])
    d = d[d.ha > 50].assign(t_ha=lambda x: x.t / x.ha)
    _c["desa"] = d
    return d.sort_values("t", ascending=False)[["nama", "kab", "ha", "t", "t_ha"]].rename(
        columns={"nama": "desa", "kab": "kabupaten", "ha": "palm_ha", "t": "ffb_t_per_year", "t_ha": "t_per_ha_yr"}).head(15)


def ffb_desa_map():
    if "desa" not in _c: ffb_desa()
    d = _c["desa"]
    fc = DESA.filter(ee.Filter.inList("pcode", d.pcode.tolist())).map(
        lambda f: f.set("t_ha", ee.Dictionary(dict(zip(d.pcode, d.t_ha.round(2)))).get(f.get("pcode"))))
    img = fc.reduceToImage(["t_ha"], ee.Reducer.first())
    edge = ee.Image().byte().paint(DESA, 1, 1)
    return img.visualize(min=11, max=14.5, palette=["fff7bc", "fec44f", "fe9929", "cc4c02", "662506"]).blend(edge.visualize(palette=["555555"]))


# ---------------------------------------------------------------------------
# N, P, K: what a satellite can and cannot say
# ---------------------------------------------------------------------------
def cire_dev():
    """Red-edge chlorophyll index CIre = B7/B5 - 1 (Gitelson), compared, like NDVI, with palms of the same age."""
    cire = s2.select("B7").divide(s2.select("B5")).subtract(1).rename("cire").updateMask(core)
    if "cm_cire" not in _c:
        g = (cire.addBands(age_int).reduceRegion(ee.Reducer.median().group(1, "age_int"), aoi, 30,
                                                 maxPixels=1e10, tileScale=16).get("groups").getInfo())
        _c["cm_cire"] = {int(x["age_int"]): x["median"] for x in g if x.get("median") is not None}
    cm = _c["cm_cire"]; keys = sorted(cm)
    rel = cire.divide(age_int.remap(keys, [cm[k] for k in keys])).subtract(1).rename("rel")
    return rel.updateMask(health_image().mask())


def cire_vis():
    rel = cire_dev()
    cls = ee.Image(1).where(rel.lt(-0.10), 2).where(rel.lt(-0.25), 3).updateMask(rel.mask())
    return cls.visualize(min=1, max=3, palette=["d9f0d3", "fdae61", "b2182b"])


def cire_table():
    rel = cire_dev(); dev = health_image()
    st = (rel.lt(-0.10).rename("low_cire").addBands(dev.lt(-0.05).rename("low_ndvi"))
          .addBands(rel.lt(-0.10).And(dev.gte(-0.05)).rename("cire_only")))
    r = st.reduceRegion(ee.Reducer.mean(), aoi, 30, maxPixels=1e10, tileScale=16).getInfo()
    corr = (rel.addBands(dev).sample(aoi, 30, numPixels=4000, seed=5, tileScale=8)
            .reduceColumns(ee.Reducer.pearsonsCorrelation(), ["rel", "dev"]).get("correlation").getInfo())
    return pd.DataFrame([
        {"measure": "palm area with red-edge chlorophyll > 10 % below its age group", "value": f"{100*r['low_cire']:.0f} %"},
        {"measure": "palm area with NDVI > 0.05 below its age group (the health map)", "value": f"{100*r['low_ndvi']:.0f} %"},
        {"measure": "low chlorophyll although NDVI looks normal (a hint NDVI misses)", "value": f"{100*r['cire_only']:.0f} %"},
        {"measure": "correlation, chlorophyll deviation vs NDVI deviation (4,000 pixels)", "value": f"{corr:.2f}"}])


def products():
    src = "GEDI L2A and L4A; Sentinel-2 L2A; Landsat age map (oil palm age chapter). GEE."
    return [
        {"kind": "chart", "name": "ch60-by-age", "data": by_age_table, "plot": plot_by_age,
         "caption": "Median GEDI height by planting age (left) and the biomass that two "
                    "published oil palm equations and the global GEDI L4A model give for the "
                    "same palms, with field measurements (stars). Log scale."},
        {"kind": "table", "name": "ch60-by-age-table", "data": by_age_table,
         "floatfmt": ("", ",.0f", ".1f", ".0f", ".2f", ".0f"),
         "caption": "GEDI footprints by palm age (ages with at least 10 shots): height and "
                    "biomass from each method."},
        {"kind": "table", "name": "ch60-equations", "data": equation_table,
         "floatfmt": ("", "", ".1f", ".1f", ".1f"),
         "caption": "The equations side by side, at 10 m and 15 m and for prime-age palms "
                    "(9-18 years), against the range found in field studies."},
        {"kind": "map", "name": "ch60-health", "image": health_vis(), "region": aoi,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "classes": [("as expected (above, or 0 to -0.05 below its age group)", "#d9f0d3"),
                     ("below (-0.05 to -0.15)", "#fdae61"), ("well below (< -0.15)", "#b2182b")],
         "title": "Oil palm canopy against its own age group, 2023", "source": src,
         "caption": "Each palm pixel's dry-season NDVI against the median of palms of the "
                    "same age, in three classes. Estate roads and drains are masked out."},
        {"kind": "table", "name": "ch60-mask", "data": mask_table,
         "floatfmt": ("", ",.0f", ".1%"),
         "caption": "Palm-map pixels removed before health scoring because they are not palm "
                    "canopy, by each map."},
        {"kind": "table", "name": "ch60-health-table", "data": health_table,
         "floatfmt": ("", ",.0f", ",.0f", ".0%"),
         "caption": f"Palm area more than {LOW} NDVI below the median of its age group, by "
                    "life stage."},
        {"kind": "table", "name": "ch60-fruit", "data": fruit_table,
         "floatfmt": ("", ",.0f", ".1f", ".1f", ".0f", ".2f"),
         "caption": "Modelled FFB (t/ha/yr) at GEDI footprints by age class, from the age "
                    "curve and from the biomass proportion."},
        {"kind": "chart", "name": "ch60-monthly", "data": monthly_table, "plot": plot_monthly,
         "caption": "Modelled landscape FFB per month from the age curve."},
        {"kind": "map", "name": "ch60-ffb-map", "image": ffb_image(), "region": aoi,
         "vis": {"min": 0, "max": 15, "palette": ["ffffe5", "fee391", "fe9929", "cc4c02", "662506"]},
         "legend": "Modelled FFB (t/ha/yr), 0 to 15", "title": "Fresh fruit bunches, pixel by pixel", "source": src,
         "caption": "The age curve applied to every palm pixel, discounted where the canopy is below its age group "
                    "(x0.9 below, x0.6 well below). Young blocks give nothing yet; old blocks are declining."},
        {"kind": "map", "name": "ch60-ffb-desa", "image": ffb_desa_map(), "region": aoi,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "legend": "", "classes": [("11 t/ha/yr or less", "#fff7bc"), ("12", "#fec44f"), ("12.8", "#fe9929"), ("13.6", "#cc4c02"), ("14.5 or more", "#662506")],
         "title": "Modelled FFB per desa (t/ha of palm per year)", "source": src + " Desa: BPS via OCHA COD-AB.",
         "caption": "The same model summarised per desa (official BPS boundaries), the unit a district office plans with."},
        {"kind": "table", "name": "ch60-ffb-desa-table", "data": ffb_desa, "floatfmt": ("", "", ",.0f", ",.0f", ".1f"),
         "caption": "The 15 desa with the largest modelled FFB output (desa with at least 50 ha of mapped palm)."},
        {"kind": "map", "name": "ch60-cire", "image": cire_vis(), "region": aoi,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "classes": [("chlorophyll as expected for its age", "#d9f0d3"), ("10-25 % below", "#fdae61"), ("more than 25 % below", "#b2182b")],
         "title": "Red-edge chlorophyll against the palm's own age group, 2023", "source": src,
         "caption": "CIre = B7/B5 - 1 from Sentinel-2's red-edge bands, a proxy for leaf chlorophyll and so for nitrogen status, "
                    "compared with palms of the same age."},
        {"kind": "table", "name": "ch60-cire-table", "data": cire_table,
         "caption": "How the chlorophyll screen compares with the NDVI health map."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(by_age_table())
