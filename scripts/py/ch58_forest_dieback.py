#| title: A forest pest outbreak from space: bark beetle in the Harz (Python)
#| description: Spruce dieback after the 2018 drought in the Harz mountains, Germany. Every conifer pixel's summer canopy moisture (Sentinel-2 NDMI) is compared with 2017; the first year it falls clearly below gives the onset of stress, mapped as a spreading wave and compared with the year Hansen records the trees as lost.

"""
CHAPTER 58 | Seeing an outbreak spread, one summer at a time.

A pest or disease kills trees from the inside before the canopy changes
colour, and the canopy changes before anyone cuts the trees. Satellites see
the middle step: a drop in canopy water and leaf area.

    1. forest   conifer forest (Copernicus land cover 2019, needle-leaved
                evergreen) with Hansen tree cover >= 50 % in 2000
    2. signal   NDMI (NIR - SWIR) / (NIR + SWIR), median of June-August,
                every year 2017-2024 (Sentinel-2)
    3. onset    first year NDMI falls more than 0.15 below its 2017 value
    4. check    year Hansen first records the pixel as lost: stress should
                come first, clearance (salvage logging) after
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([10.40, 51.65, 10.90, 51.95], None, False)
YEARS = list(range(2017, 2025))
DROP = 0.15

cgls = ee.Image("COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019")
gfc = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")
conifer = (cgls.select("forest_type").eq(1)
           .And(gfc.select("treecover2000").gte(50)).clip(aoi))
lossyear = gfc.select("lossyear").unmask(0)


def ndmi(year):
    def prep(i):
        m = i.select("cs").gte(0.6)
        return i.updateMask(m).normalizedDifference(["B8", "B11"]).rename("ndmi")
    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi)
            .filterDate(f"{year}-06-01", f"{year}-09-01")
            .linkCollection(ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"),
                            ["cs"])
            .map(prep).median().rename(f"n{year}"))


stack = ee.Image.cat([ndmi(y) for y in YEARS]).updateMask(conifer)
base = stack.select("n2017")
# Onset: first year (2018 on) more than DROP below 2017. 0 = never.
onset = ee.Image(0)
for y in reversed(YEARS[1:]):
    onset = onset.where(base.subtract(stack.select(f"n{y}")).gt(DROP), y)
onset = onset.updateMask(conifer).rename("onset")
# Ignore single-summer dips that recover: require the drop to last into the next year
# (or to the last year available).
lasting = ee.Image(0)
for y in YEARS[1:]:
    nxt = min(y + 1, YEARS[-1])
    both = (base.subtract(stack.select(f"n{y}")).gt(DROP)
            .And(base.subtract(stack.select(f"n{nxt}")).gt(DROP)))
    lasting = lasting.where(onset.eq(y).And(both), 1)
onset = onset.updateMask(onset.eq(0).Or(lasting)).unmask(0).updateMask(conifer)
loss_y = lossyear.add(2000).where(lossyear.eq(0), 0).rename("loss")


def area_table():
    area = ee.Image.pixelArea().divide(1e4)
    g = (area.addBands(onset).reduceRegion(ee.Reducer.sum().group(1, "onset"), aoi, 20,
                                           maxPixels=1e10, tileScale=8)
         .get("groups").getInfo())
    d = {int(x["onset"]): x["sum"] for x in g}
    total = sum(d.values())
    rows, cum = [], 0
    for y in YEARS[1:]:
        cum += d.get(y, 0)
        rows.append({"year": y, "new_stressed_ha": d.get(y, 0), "cumulative_ha": cum,
                     "cumulative_share": cum / total})
    rows.append({"year": "never stressed", "new_stressed_ha": d.get(0, 0),
                 "cumulative_ha": total, "cumulative_share": np.nan})
    return pd.DataFrame(rows)


def plot_area(df):
    d = df[pd.to_numeric(df.year, errors="coerce").notna()]
    fig, ax = plt.subplots(figsize=(6.8, 3.3))
    ax.bar(d.year.astype(int), d.new_stressed_ha / 1000, color="#b2182b",
           label="newly stressed that summer")
    ax2 = ax.twinx()
    ax2.plot(d.year.astype(int), d.cumulative_share * 100, color="#1f2933", marker="o",
             ms=3, label="cumulative, % of conifer")
    ax.set_ylabel("Newly stressed (thousand ha)")
    ax2.set_ylabel("Cumulative (% of conifer forest)")
    ax.set_title("The outbreak year by year", loc="left", fontsize=10)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=8, loc="upper left")
    return fig


def lag_table():
    """For pixels that were stressed and later lost: years from stress to loss."""
    pts = (onset.addBands(loss_y).updateMask(onset.gt(0))
           .sample(region=aoi, scale=20, numPixels=6000, seed=4, tileScale=8))
    d = pd.DataFrame([f["properties"] for f in pts.getInfo()["features"]])
    d["lag"] = np.where(d.loss > 0, d.loss - d.onset, np.nan)
    rows = [{"group": "stressed, never recorded lost (to 2024)", "share": (d.loss == 0).mean()},
            {"group": "lost before or in the onset year (lag <= 0)", "share": (d.lag <= 0).mean()},
            {"group": "lost 1 year after onset", "share": (d.lag == 1).mean()},
            {"group": "lost 2 years after onset", "share": (d.lag == 2).mean()},
            {"group": "lost 3 or more years after onset", "share": (d.lag >= 3).mean()}]
    out = pd.DataFrame(rows)
    out["median_lag_if_lost_years"] = np.nanmedian(d.lag[d.lag > 0]) if (d.lag > 0).any() else np.nan
    out["sample_pixels"] = len(d)
    return out


def series_table():
    """Mean summer NDMI of conifer pixels grouped by onset year."""
    rows = []
    for y in YEARS:
        img = stack.select(f"n{y}").addBands(onset)
        g = (img.reduceRegion(ee.Reducer.mean().group(1, "onset"), aoi, 40, maxPixels=1e10,
                              tileScale=8).get("groups").getInfo())
        for x in g:
            rows.append({"year": y, "onset": int(x["onset"]), "ndmi": x["mean"]})
    return pd.DataFrame(rows)


def plot_series(df):
    fig, ax = plt.subplots(figsize=(7.0, 3.5))
    cmap = plt.get_cmap("inferno")
    for k, (o, g) in enumerate(df.groupby("onset")):
        if o == 0:
            ax.plot(g.year, g.ndmi, color="#1a9850", lw=2.2, label="never stressed")
        else:
            ax.plot(g.year, g.ndmi, color=cmap(0.15 + 0.7 * (o - 2018) / 6), lw=1.4,
                    label=f"onset {o}")
    ax.set_ylabel("Summer NDMI (conifer pixels)")
    ax.set_title("Each cohort holds, then falls in its own year", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=7, ncol=2)
    return fig


ONSET_PAL = ["fde725", "addc30", "5ec962", "28ae80", "21918c", "2c728e", "3b528b"]
onset_vis = (ee.Image(1).visualize(palette=["ffffff"]).clip(aoi)
             .blend(conifer.selfMask().visualize(palette=["c7e9c0"]))
             .blend(onset.updateMask(onset.gt(0)).visualize(min=2018, max=2024,
                                                             palette=ONSET_PAL[::-1])))


def products():
    rgb = {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255}
    classes = [(str(y), "#" + c) for y, c in zip(range(2018, 2025), ONSET_PAL[::-1])]
    return [
        {"kind": "map", "name": "ch58-onset", "image": onset_vis, "region": aoi, "vis": rgb,
         "classes": [("conifer, not stressed", "#c7e9c0")] + classes,
         "title": "Year the spruce canopy first dried out, Harz",
         "source": "Sentinel-2 L2A; Copernicus Global Land Cover 2019; Hansen GFC. GEE.",
         "caption": "First summer in which a conifer pixel's NDMI fell more than "
                    f"{DROP} below 2017 and stayed down the next summer."},
        {"kind": "chart", "name": "ch58-area", "data": area_table, "plot": plot_area,
         "caption": "Conifer forest newly stressed each summer, and the running total."},
        {"kind": "table", "name": "ch58-area-table", "data": area_table,
         "floatfmt": ("", ",.0f", ",.0f", ".0%"),
         "caption": "Area by onset year (ha)."},
        {"kind": "chart", "name": "ch58-series", "data": series_table, "plot": plot_series,
         "caption": "Mean summer NDMI of conifer pixels, grouped by the year their decline "
                    "began."},
        {"kind": "table", "name": "ch58-lag", "data": lag_table,
         "floatfmt": ("", ".0%", ".1f", ",.0f"),
         "caption": "Stressed pixels against the year Hansen records them as lost."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(area_table())
