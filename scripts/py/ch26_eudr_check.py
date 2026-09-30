#| title: An EUDR screening for a grid of supplier plots (Python)
#| description: The same cut-off screening as the JavaScript tab, in Python.

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
         "caption": ("Plots per screening status. More than half fail, and that is the real lesson: in Jambi's smallholder rubber landscape the 2020 forest map counts old rubber agroforest as forest, and replanting then reads as deforestation. A failed screen is a reason to look closer (imagery, farmer records, planting dates), not a verdict.")},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(screened.aggregate_histogram("status").getInfo())
