#| title: Is mined land recovering? Bangka tin fields (Python)
#| description: Former tin-mining land on Bangka found in 34 years of Landsat, its greenness recovery against undisturbed forest, its status today, and a GEDI check of whether structure has come back as well as greenness.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 49 | Restoration effectiveness, measured three ways.

Tin mining on Bangka strips the land to bare sand and leaves ponds. Some of
it is reclaimed (planted), some regrows on its own, some stays bare.

    disturbed   a pixel whose annual Landsat NDVI fell below 0.15 at least once
                between 1995 and 2015, and that was vegetated (NDVI > 0.5) before
    reference   pixels that stayed above NDVI 0.6 every year: undisturbed vegetation
    greenness   NDVI years after disturbance, against the reference
    structure   GEDI rh98 height of recovered land against the reference

Greenness returns within a few years; height and biomass take decades. A
restoration report that shows only NDVI overstates success.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([105.95, -2.15, 106.30, -1.75], None, False)     # central Bangka
YEARS = list(range(1990, 2024))
water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gt(80).unmask(0)


def landsat(col, nir, red):
    def prep(img):
        qa = img.select("QA_PIXEL")
        ok = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        sr = img.select([nir, red]).multiply(0.0000275).add(-0.2)
        return (sr.normalizedDifference([nir, red]).rename("ndvi").updateMask(ok)
                .copyProperties(img, ["system:time_start"]))
    return ee.ImageCollection(col).filterBounds(aoi).map(prep)


ls = (landsat("LANDSAT/LT05/C02/T1_L2", "SR_B4", "SR_B3")
      .merge(landsat("LANDSAT/LE07/C02/T1_L2", "SR_B4", "SR_B3"))
      .merge(landsat("LANDSAT/LC08/C02/T1_L2", "SR_B5", "SR_B4"))
      .merge(landsat("LANDSAT/LC09/C02/T1_L2", "SR_B5", "SR_B4")))
EMPTY = ee.ImageCollection([ee.Image.constant(0).rename("ndvi").updateMask(0)])
annual = ee.ImageCollection([
    ls.filterDate(f"{y}-01-01", f"{y + 1}-01-01").merge(EMPTY).median()
      .addBands(ee.Image.constant(y).toInt16().rename("year")).set("year", y)
    for y in YEARS])

window = annual.filter(ee.Filter.rangeContains("year", 1995, 2015))
# First year NDVI dropped below 0.15 in 1995-2015: the mining year
bare = window.map(lambda i: i.addBands(i.select("ndvi").lt(0.15).rename("b")))
first_bare = (bare.map(lambda i: i.select("year").updateMask(i.select("b")))
              .reduce(ee.Reducer.min()).rename("mined_year"))
was_green = annual.filter(ee.Filter.rangeContains("year", 1990, 1994)).select("ndvi").max().gt(0.5)
disturbed = first_bare.updateMask(was_green).updateMask(water.Not()).clip(aoi)
ndvi_2023 = ee.Image(annual.filter(ee.Filter.eq("year", 2023)).first()).select("ndvi")
reference = (annual.filter(ee.Filter.rangeContains("year", 1995, 2023)).select("ndvi")
             .min().gt(0.6).selfMask().rename("ref").clip(aoi))

status = (ee.Image(1).where(ndvi_2023.gte(0.3), 2).where(ndvi_2023.gte(0.6), 3)
          .updateMask(disturbed.mask()).rename("status").clip(aoi))
STATUS = {1: "still bare or ponds (NDVI < 0.3)", 2: "early regrowth (0.3-0.6)",
          3: "green again (>= 0.6)"}


def status_table():
    g = (ee.Image.pixelArea().divide(1e4).addBands(status)
         .reduceRegion(ee.Reducer.sum().group(1, "status"), aoi, 30, maxPixels=1e10,
                       tileScale=8).get("groups").getInfo())
    df = pd.DataFrame([{"status 2023": STATUS[int(d["status"])], "area_ha": d["sum"]} for d in g])
    df["share"] = df.area_ha / df.area_ha.sum()
    return df


def trajectory_frame():
    """Median NDVI by years since mining, for land mined in 2000-2008."""
    pts = (disturbed.updateMask(disturbed.gte(2000).And(disturbed.lte(2008)))
           .sample(region=aoi, scale=30, numPixels=600, seed=3, geometries=True).limit(60))
    refpts = reference.sample(region=aoi, scale=30, numPixels=300, seed=4,
                              geometries=True).limit(30)
    def series(points, kind):
        fc = annual.map(lambda img: img.select("ndvi").reduceRegions(points, ee.Reducer.first(), 30)
                        .map(lambda f: f.set("year", img.get("year"), "kind", kind)))
        return [f["properties"] for f in fc.flatten().getInfo()["features"]]
    df = pd.DataFrame(series(pts, "mined") + series(refpts, "reference"))
    return df.rename(columns={"first": "ndvi"}).dropna(subset=["ndvi"])


def plot_trajectory(df):
    m = df[df.kind == "mined"].copy()
    m["since"] = m.year - m.mined_year
    g = m[(m.since >= -5) & (m.since <= 20)].groupby("since").ndvi
    ref = df[df.kind == "reference"].groupby("year").ndvi.median().median()
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.fill_between(g.median().index, g.quantile(0.25), g.quantile(0.75), color="#e08214",
                    alpha=0.25, label="middle half of mined pixels")
    ax.plot(g.median().index, g.median(), "o-", color="#e08214", ms=3, label="median, mined 2000-2008")
    ax.axhline(ref, color="#1b7837", ls="--", label=f"undisturbed reference ({ref:.2f})")
    ax.axvline(0, color="#1f2933", lw=0.8)
    ax.set_xlabel("Years since the land was laid bare")
    ax.set_ylabel("Annual median NDVI")
    ax.set_title("Greenness after tin mining, against land never mined", loc="left",
                 fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


gedi = (ee.ImageCollection("LARSE/GEDI/GEDI02_A_002_MONTHLY").filterBounds(aoi)
        .filterDate("2019-04-01", "2024-01-01")
        .map(lambda i: i.updateMask(i.select("quality_flag").eq(1).And(i.select("degrade_flag").eq(0))))
        .select("rh98").mosaic())
grp = (ee.Image(0).where(reference.mask(), 1).where(status.eq(3), 2).where(status.eq(2), 3)
       .selfMask().rename("grp"))
height_pts = gedi.addBands(grp).updateMask(gedi.mask()).stratifiedSample(
    numPoints=300, classBand="grp", region=aoi, scale=25, seed=5, tileScale=8)


def plot_height(df):
    names = {1: "never mined", 2: "mined, green again", 3: "mined, early regrowth"}
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    data = [df.loc[df.grp == k, "rh98"] for k in names]
    ax.boxplot(data, tick_labels=[f"{v}\n(n={len(d)})" for v, d in zip(names.values(), data)],
               showfliers=False, widths=0.5, medianprops={"color": "#c0392b", "lw": 2})
    ax.set_ylabel("GEDI rh98 height (m)")
    ax.set_title("Green is not the same as grown", loc="left", fontsize=10)
    return fig


# Does older mean more recovered? Status in 2023 by the period the land was mined
COHORTS = [(1995, 1999), (2000, 2004), (2005, 2009), (2010, 2015)]


def cohort_table():
    cohort = ee.Image(0)
    for i, (a, b) in enumerate(COHORTS):
        cohort = cohort.where(disturbed.gte(a).And(disturbed.lte(b)), i + 1)
    code = cohort.multiply(10).add(status).updateMask(disturbed.mask())
    g = (ee.Image.pixelArea().divide(1e4).addBands(code.rename("c"))
         .reduceRegion(ee.Reducer.sum().group(1, "c"), aoi, 30, maxPixels=1e10, tileScale=8).get("groups").getInfo())
    d = pd.DataFrame([{"cohort": int(x["c"]) // 10, "status": int(x["c"]) % 10, "ha": x["sum"]} for x in g])
    w = d.pivot_table(index="cohort", columns="status", values="ha", aggfunc="sum").fillna(0)
    out = pd.DataFrame({"mined": [f"{a}-{b}" for a, b in COHORTS], "area_ha": w.sum(axis=1).values,
                        "still bare or ponds": (w[1] / w.sum(axis=1)).values,
                        "green again": (w[3] / w.sum(axis=1)).values})
    out["years since mining (to 2023)"] = [f"{2023 - b}-{2023 - a}" for a, b in COHORTS]
    return out


# How long until green again? A survival curve, because recent pits have not had time
def recovery_frame():
    """For a sample of mined pixels: years until annual NDVI first reached 0.5, or censored at 2023."""
    after = annual.filter(ee.Filter.rangeContains("year", 1996, 2023)).map(
        lambda i: i.select("year").updateMask(i.select("ndvi").gte(0.5).And(i.select("year").gt(disturbed))))
    recovered = after.reduce(ee.Reducer.min()).rename("recovered_year")
    smp = (disturbed.rename("mined_year").addBands(recovered.unmask(0))
           .sample(region=aoi, scale=30, numPixels=100000, seed=9, geometries=False, tileScale=8).limit(4900).getInfo())
    d = pd.DataFrame([f["properties"] for f in smp["features"]])
    d["event"] = d.recovered_year > 0
    d["years"] = np.where(d.event, d.recovered_year - d.mined_year, 2023 - d.mined_year)
    return d


def kaplan_meier(years, event):
    """Share still not recovered after t years, allowing for pixels observed for different lengths of time."""
    t = np.sort(np.unique(years[event]))
    s, out = 1.0, [(0, 1.0)]
    for ti in t:
        at_risk = (years >= ti).sum()
        if at_risk == 0:
            break
        s *= 1 - ((years == ti) & event).sum() / at_risk
        out.append((ti, s))
    return pd.DataFrame(out, columns=["years", "not_yet_green"])


def plot_recovery(d):
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    for (a, b), c in zip([(1995, 2004), (2005, 2015)], ["#3b528b", "#e08214"]):
        g = d[(d.mined_year >= a) & (d.mined_year <= b)]
        km = kaplan_meier(g.years.values, g.event.values)
        ax.step(km.years, 1 - km.not_yet_green, where="post", color=c, lw=2, label=f"mined {a}-{b} (n = {len(g)})")
    km = kaplan_meier(d.years.values, d.event.values)
    half = km[km.not_yet_green <= 0.5].years.min()
    ax.set_xlabel("years since the land was laid bare"); ax.set_ylabel("share that has reached NDVI 0.5")
    ax.set_ylim(0, 1); ax.legend(frameon=False, fontsize=8, loc="lower right"); ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(f"Half of the mined land reached NDVI 0.5 within {half:.0f} years (Kaplan-Meier, all pixels)" if pd.notna(half)
                 else "Fewer than half of the mined pixels have reached NDVI 0.5", loc="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    return fig


# The ponds: new water created on mined land (JRC Global Surface Water transitions, 1984-2021)
def ponds_table():
    trans = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("transition")
    mined_any = first_bare.updateMask(was_green).mask().clip(aoi)          # without the permanent-water exclusion
    area = ee.Image.pixelArea().divide(1e4)
    rows = []
    for code, name in ((2, "new permanent water"), (5, "new seasonal water")):
        r = (area.updateMask(trans.eq(code)).rename("all").addBands(area.updateMask(trans.eq(code)).updateMask(mined_any).rename("mined"))
             .reduceRegion(ee.Reducer.sum(), aoi, 30, maxPixels=1e10, tileScale=8).getInfo())
        rows.append({"water class (1984-2021)": name, "whole box (ha)": r["all"], "on land mined 1995-2015 (ha)": r["mined"]})
    return pd.DataFrame(rows)


def products():
    return [
        {"kind": "map", "name": "ch49-status", "image": status, "region": aoi,
         "vis": {"min": 1, "max": 3, "palette": ["d7301f", "fdae61", "1a9850"]},
         "classes": [(STATUS[k], c) for k, c in zip((1, 2, 3), ["#d7301f", "#fdae61", "#1a9850"])],
         "title": "Former tin-mining land, central Bangka, 2023",
         "source": "Landsat 5/7/8/9 C2; JRC Global Surface Water. GEE.",
         "caption": "Land that was vegetated before 1995 and laid bare between 1995 and 2015, "
                    "coloured by its greenness in 2023. Permanent water is excluded; mine "
                    "ponds that formed later count as bare."},
        {"kind": "map", "name": "ch49-year", "image": disturbed, "region": aoi,
         "vis": {"min": 1995, "max": 2015, "palette": ["440154", "3b528b", "21918c", "5ec962", "fde725"]},
         "legend": "Year the land was first laid bare",
         "title": "When each pit was opened", "source": "Landsat C2. GEE.",
         "caption": "The first year annual NDVI fell below 0.15."},
        {"kind": "table", "name": "ch49-status-table", "data": status_table,
         "floatfmt": ("", ",.0f", ".0%"), "caption": "Area of former mining land by 2023 status."},
        {"kind": "chart", "name": "ch49-trajectory", "data": trajectory_frame,
         "plot": plot_trajectory,
         "caption": "NDVI before and after mining for land laid bare in 2000-2008, against "
                    "never-mined vegetation."},
        {"kind": "chart", "name": "ch49-height", "data": height_pts, "plot": plot_height,
         "caption": "GEDI canopy height (2019-2023) on never-mined land and on former mining "
                    "land by its 2023 greenness."},
        {"kind": "table", "name": "ch49-cohorts", "data": cohort_table, "floatfmt": ("", "", ",.0f", ".0%", ".0%"),
         "columns": ["mined", "years since mining (to 2023)", "area_ha", "still bare or ponds", "green again"],
         "caption": "Status in 2023 by the period the land was first laid bare."},
        {"kind": "chart", "name": "ch49-recovery", "data": recovery_frame, "plot": plot_recovery, "live": False,
         "caption": "Share of mined pixels that have reached NDVI 0.5, by years since mining. Pixels not yet green count until 2023 and then drop out (right-censored), which is what the Kaplan-Meier estimate is for."},
        {"kind": "table", "name": "ch49-ponds", "data": ponds_table, "floatfmt": ("", ",.0f", ",.0f"),
         "caption": "Water that did not exist before (JRC Global Surface Water transitions), in the whole box and on land mined 1995-2015."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(status_table())
