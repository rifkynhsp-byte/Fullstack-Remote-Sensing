#| title: An EUDR screening for a grid of supplier plots (Python)
#| description: The same cut-off screening as the JavaScript tab, in Python.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 26 | EUDR screening: forest at 31 December 2020 (JRC GFC2020),
loss since (Hansen), a status per plot. A 1 km grid stands in for supplier
plots, which are client data.
"""

import ee
import matplotlib.pyplot as plt

area = ee.Geometry.Rectangle([102.9, -1.9, 103.2, -1.6])   # Jambi

forest2020 = ee.Image("JRC/GFC2020/V4").select("Map").eq(1).unmask(0).rename("forest2020")
hansen = ee.Image("UMD/hansen/global_forest_change_2024_v1_12")
# Deforestation under the EUDR is loss of forest that existed at the cut-off:
# count loss only on pixels the 2020 map calls forest.
loss_after = (hansen.select("lossyear").gte(21).unmask(0).And(forest2020)
              .rename("loss_after_2020"))

plots = (area.coveringGrid(ee.Projection("EPSG:32748").atScale(1000))
         .map(lambda c: c.set("plot_id", c.id())))

ha = forest2020.addBands(loss_after).multiply(ee.Image.pixelArea()).divide(1e4)


def status_of(p):
    forest = ee.Number(p.get("forest2020"))
    loss = ee.Number(p.get("loss_after_2020"))
    status = ee.Algorithms.If(loss.gt(0.5), "deforestation after cut-off",
                              ee.Algorithms.If(forest.gt(10),
                                               "forest standing: check degradation",
                                               "no forest at cut-off"))
    return p.set({"forest2020_ha": forest, "loss_after_2020_ha": loss, "status": status})


screened = (ha.reduceRegions(collection=plots, reducer=ee.Reducer.sum(), scale=30,
                             tileScale=4).map(status_of))


# Loss per year in ONE request: sum pixel area grouped by loss year. Twenty-
# four separate reduceRegion calls fail with "Too many concurrent aggregations".
grouped = (ee.Image.pixelArea().divide(1e4).addBands(hansen.select("lossyear"))
           .reduceRegion(reducer=ee.Reducer.sum().group(groupField=1, groupName="code"),
                         geometry=area, scale=30, maxPixels=1e10))
loss_by_year = ee.FeatureCollection(ee.List(grouped.get("groups")).map(
    lambda g: ee.Feature(None, {"year": ee.Number(ee.Dictionary(g).get("code")).add(2000),
                                "loss_ha": ee.Dictionary(g).get("sum")}))
).filter(ee.Filter.gt("year", 2000))


STATUS_COLOURS = {"deforestation after cut-off": "d7191c",
                  "forest standing: check degradation": "1a9641",
                  "no forest at cut-off": "d9d9d9"}


def status_image():
    img = ee.Image().byte()
    for i, (name, _) in enumerate(STATUS_COLOURS.items()):
        img = img.paint(screened.filter(ee.Filter.eq("status", name)), i)
    return img


plot_map = (hansen.select("lossyear").gte(21).selfMask().visualize(palette=["000000"])
            .blend(status_image().visualize(min=0, max=2, palette=list(STATUS_COLOURS.values()),
                                            opacity=0.55))
            .blend(ee.Image().byte().paint(screened, 1, 1).visualize(palette=["ffffff"]))
            .blend(loss_after.selfMask().visualize(palette=["000000"])))


def summary(df):
    g = (df.groupby("status").agg(plots=("status", "size"),
                                  forest2020_ha=("forest2020_ha", "sum"),
                                  loss_after_2020_ha=("loss_after_2020_ha", "sum"))
         .reset_index())
    return g


def plot_loss_by_year(df):
    """Loss per year; everything right of the line counts against a plot."""
    df = df.sort_values("year")
    colours = ["#d7191c" if y >= 2021 else "#9aa5b1" for y in df["year"]]
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    ax.bar(df["year"].astype(int), df["loss_ha"], color=colours)
    ax.axvline(2020.5, color="black", lw=1, ls="--")
    ax.text(2020.6, ax.get_ylim()[1] * 0.92, "EUDR cut-off\n31 Dec 2020", fontsize=7)
    ax.set_ylabel("Tree cover loss (ha)")
    ax.set_title("Loss per year in the screening area (Hansen v1.12)", loc="left")
    return fig


# PART 4. Second opinions: a second loss map, and what the land was at the cut-off ------------------
# JRC Tropical Moist Forest (TMF) annual change classes: 1 undisturbed forest, 2 degraded forest,
# 3 deforested land, 4 forest regrowth, 5 water, 6 other land.
tmf = ee.ImageCollection("projects/JRC/TMF/v1_2024/AnnualChanges").mosaic()
tmf_forest2020 = tmf.select("Dec2020").lte(2)
tmf_loss_after = tmf_forest2020.And(tmf.select("Dec2024").eq(3)).And(forest2020).rename("tmf_loss_after_2020")

# Forest Data Partnership commodity models: probability that a 10 m pixel is a rubber or an oil
# palm plantation, in 2020 (the cut-off year).
def fdp(crop, year=2020):
    return (ee.ImageCollection(f"projects/forestdatapartnership/assets/{crop}/model_2026a")
            .filterDate(f"{year}-01-01", f"{year + 1}-01-01").mosaic().select("probability"))

rubber2020, palm2020 = fdp("rubber"), fdp("palm")
# What each flagged pixel was at the cut-off: 1 rubber, 2 oil palm, 3 neither (natural forest or unknown)
was = (ee.Image(3).where(palm2020.gt(0.5), 2).where(rubber2020.gt(0.5), 1)
       .updateMask(loss_after).rename("was"))
WAS = {1: "rubber plantation in 2020", 2: "oil palm plantation in 2020", 3: "neither: natural forest or unknown"}


def agreement_table():
    """Plot by plot: does TMF agree with Hansen on deforestation after the cut-off?"""
    import pandas as pd
    fc = (ee.Image.cat([loss_after, tmf_loss_after]).multiply(ee.Image.pixelArea()).divide(1e4)
          .reduceRegions(collection=plots, reducer=ee.Reducer.sum(), scale=30, tileScale=4))
    d = pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]])
    h, t = d.loss_after_2020 > 0.5, d.tmf_loss_after_2020 > 0.5
    rows = [("fail on both", (h & t).sum()), ("fail on Hansen only", (h & ~t).sum()),
            ("fail on TMF only", (~h & t).sum()), ("pass on both", (~h & ~t).sum())]
    out = pd.DataFrame(rows, columns=["outcome", "plots"])
    out["share (%)"] = 100 * out.plots / len(d)
    return out


def what_was_lost():
    """Hansen loss after 2020 on JRC 2020 forest, by year and by what FDP saw there in 2020."""
    import pandas as pd
    code = was.multiply(100).add(hansen.select("lossyear"))
    r = (ee.Image.pixelArea().divide(1e4).addBands(code)
         .reduceRegion(ee.Reducer.sum().group(1, "code"), area, 10, maxPixels=1e10, tileScale=4).getInfo())
    d = pd.DataFrame([{"was": WAS[int(g["code"]) // 100], "year": 2000 + int(g["code"]) % 100, "ha": g["sum"]}
                      for g in r["groups"]])
    return d.pivot_table(index="year", columns="was", values="ha", aggfunc="sum").fillna(0).reset_index()


def plot_what_was_lost(d):
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    bottom = 0
    for col, c in [(WAS[1], "#8c6d31"), (WAS[2], "#e6ab02"), (WAS[3], "#1b7837")]:
        if col in d:
            ax.bar(d.year.astype(int), d[col], bottom=bottom, color=c, label=col)
            bottom = bottom + d[col]
    tot = d.drop(columns="year").sum()
    share = 100 * (tot.get(WAS[1], 0) + tot.get(WAS[2], 0)) / tot.sum()
    ax.set_xticks(d.year.astype(int))
    ax.set_ylabel("flagged loss (ha)"); ax.legend(frameon=False, fontsize=8)
    ax.set_title(f"{share:.0f} % of the flagged loss was on land a commodity model already called plantation in 2020",
                 loc="left", fontsize=9.5, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def patch_sizes():
    """Flagged loss by the size of the patch it belongs to: smallholder clearings or company blocks?"""
    import pandas as pd
    n = loss_after.selfMask().connectedPixelCount(1024, True)          # 30 m pixels per patch, 8-connected
    size_ha = n.multiply(0.09)
    bins = [(0, 0.5), (0.5, 2), (2, 5), (5, 20), (20, 1e9)]
    cls = ee.Image(0)
    for i, (lo, hi) in enumerate(bins):
        cls = cls.where(size_ha.gte(lo).And(size_ha.lt(hi)), i + 1)
    r = (ee.Image.pixelArea().divide(1e4).addBands(cls.updateMask(loss_after).rename("c"))
         .reduceRegion(ee.Reducer.sum().group(1, "c"), area, 30, maxPixels=1e10).getInfo())
    lab = {i + 1: (f"{lo:g}-{hi:g} ha" if hi < 1e9 else f"> {lo:g} ha") for i, (lo, hi) in enumerate(bins)}
    d = pd.DataFrame([{"patch size": lab[int(g["c"])], "flagged loss (ha)": g["sum"]} for g in r["groups"] if int(g["c"]) > 0])
    d["share (%)"] = 100 * d["flagged loss (ha)"] / d["flagged loss (ha)"].sum()
    return d


def products():
    src = "JRC GFC2020 v4, Hansen GFC v1.12 (2024). GEE."
    return [
        {"kind": "map", "name": "ch26-eudr-map", "image": plot_map, "region": area,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "classes": [(n, "#" + c) for n, c in STATUS_COLOURS.items()] +
                    [("loss 2021–2024", "#000000")],
         "title": "1 km plots screened against the EUDR cut-off", "source": src,
         "caption": "Each 1 km cell stands in for a supplier plot. Black pixels are "
                    "tree cover loss after 2020."},
        {"kind": "chart", "name": "ch26-loss-years", "data": loss_by_year,
         "plot": plot_loss_by_year,
         "caption": "Tree cover loss per year across the whole area. Red bars fall after "
                    "the EUDR cut-off."},
        {"kind": "table", "name": "ch26-status", "data": screened.select(
            ["status", "forest2020_ha", "loss_after_2020_ha"], retainGeometry=False),
         "transform": summary, "floatfmt": ("", ".0f", ".0f", ".0f"),
         "caption": ("Plots per screening status. More than half fail. Whether that is forest conversion or replanted rubber agroforest the global maps cannot tell; the sections below test it. A failed screen is a reason to look closer (imagery, farmer records, planting dates), not a verdict.")},
        {"kind": "table", "name": "ch26-agreement", "data": agreement_table, "floatfmt": ("", ".0f", ".0f"),
         "caption": "Hansen and JRC TMF on the same 1 km plots: deforestation after 2020 on JRC 2020 forest, more than 0.5 ha."},
        {"kind": "chart", "name": "ch26-what-was-lost", "data": what_was_lost, "plot": plot_what_was_lost, "live": False,
         "caption": "Every flagged hectare, by loss year and by what the Forest Data Partnership models saw there in 2020."},
        {"kind": "table", "name": "ch26-patches", "data": patch_sizes, "floatfmt": ("", ".0f", ".0f"),
         "caption": "Flagged loss by the size of the clearing it belongs to (connected 30 m pixels)."},
        {"kind": "table", "name": "ch26-what-was-lost-table", "data": what_was_lost, "floatfmt": ".0f",
         "caption": "The same numbers as a table (ha)."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(screened.aggregate_histogram("status").getInfo())
