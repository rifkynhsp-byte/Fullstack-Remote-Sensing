#| title: Habitat for biodiversity: forest loss, fragmentation and structure (Python)
#| description: Around Bukit Barisan Selatan National Park, Sumatra: forest in 2000 and 2023 inside and outside the park, how much core (interior) forest was lost compared with forest overall, and GEDI structural complexity as a measure of habitat quality.

"""
CHAPTER 53 | What satellites can say about biodiversity: habitat.

Species are not seen from space; their habitat is. Three habitat measures:

    amount         forest area (Hansen GFC: tree cover >= 30 % in 2000, minus loss)
    configuration  core forest = forest more than 300 m from any non-forest edge,
                   where edge effects (light, wind, hunters, fire) fade
    quality        GEDI foliage height diversity (Chapter 47)

Inside versus outside the national park boundary (WDPA).
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([103.80, -5.95, 104.60, -4.90], None, False)
park = (ee.FeatureCollection("WCMC/WDPA/current/polygons")
        .filter(ee.Filter.stringContains("NAME", "Bukit Barisan Selatan")).geometry())
gfc = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")
forest2000 = gfc.select("treecover2000").gte(30)
lossyear = gfc.select("lossyear").unmask(0)          # masked where no loss: 0 = never lost
forest2023 = forest2000.And(lossyear.eq(0).Or(lossyear.gt(23)))
UTM = ee.Projection("EPSG:32748").atScale(30)
EDGE_M = 300


def core(forest):
    """Forest farther than EDGE_M from any non-forest pixel."""
    dist = (forest.Not().reproject(UTM).fastDistanceTransform(32).sqrt().multiply(30))
    return forest.And(dist.gt(EDGE_M))


core2000, core2023 = core(forest2000), core(forest2023)
inside = ee.Image(0).paint(ee.FeatureCollection([ee.Feature(park)]), 1).rename("inside")


def metrics_table():
    area = ee.Image.pixelArea().divide(1e4)
    stack = ee.Image.cat([area.updateMask(i).rename(n) for i, n in
                          [(forest2000, "f2000"), (forest2023, "f2023"),
                           (core2000, "c2000"), (core2023, "c2023")]]).addBands(inside)
    g = (stack.reduceRegion(ee.Reducer.sum().repeat(4).group(4, "inside"), aoi, 30,
                            maxPixels=1e11, tileScale=16).get("groups").getInfo())
    rows = []
    for d in g:
        f0, f1, c0, c1 = d["sum"]
        rows.append({"where": "inside the park" if d["inside"] == 1 else "outside the park",
                     "forest_2000_ha": f0, "forest_2023_ha": f1,
                     "forest_change": f1 / f0 - 1,
                     "core_2000_ha": c0, "core_2023_ha": c1, "core_change": c1 / c0 - 1})
    return pd.DataFrame(rows)


def plot_change(df):
    fig, ax = plt.subplots(figsize=(6.8, 3.4))
    x = np.arange(len(df))
    ax.bar(x - 0.18, df.forest_change * 100, 0.36, color="#41ab5d", label="all forest")
    ax.bar(x + 0.18, df.core_change * 100, 0.36, color="#00441b", label=f"core (> {EDGE_M} m from edge)")
    ax.set_xticks(x, df["where"])
    ax.axhline(0, color="#1f2933", lw=0.8)
    ax.set_ylabel("Change 2000-2023 (%)")
    ax.set_title("Core forest is lost faster than forest", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


fhd = (ee.ImageCollection("LARSE/GEDI/GEDI02_B_002_MONTHLY").filterBounds(aoi)
       .filterDate("2019-04-01", "2024-01-01")
       .map(lambda i: i.updateMask(i.select("l2b_quality_flag").eq(1)
                                   .And(i.select("degrade_flag").eq(0))))
       .select(["fhd_normal", "cover"]).mosaic())
grp = (ee.Image(0).where(forest2023.And(inside.eq(1)), 1)
       .where(forest2023.And(inside.eq(0)), 2).selfMask().rename("grp"))
fhd_pts = fhd.addBands(grp).updateMask(fhd.select("fhd_normal").mask()).stratifiedSample(
    numPoints=400, classBand="grp", region=aoi, scale=25, seed=2, tileScale=8)


def plot_fhd(df):
    names = {1: "forest inside the park", 2: "forest outside the park"}
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    data = [df.loc[df.grp == k, "fhd_normal"] for k in names]
    ax.boxplot(data, tick_labels=[f"{v}\n(n={len(d)})" for v, d in zip(names.values(), data)],
               showfliers=False, widths=0.5, medianprops={"color": "#c0392b", "lw": 2})
    ax.set_ylabel("Foliage height diversity (GEDI)")
    ax.set_title("Structural habitat quality of the forest that remains", loc="left",
                 fontsize=10)
    return fig


status = (ee.Image(0).where(forest2000, 1).where(forest2023, 2).where(core2023, 3)
          .selfMask().rename("s").clip(aoi))
park_line = ee.Image().byte().paint(ee.FeatureCollection([ee.Feature(park)]), 1, 2)
status_vis = (status.visualize(min=1, max=3, palette=["e6550d", "a1d99b", "00441b"])
              .blend(park_line.visualize(palette=["000000"])))


def products():
    return [
        {"kind": "map", "name": "ch53-habitat", "image": status_vis, "region": aoi,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "classes": [("forest lost 2000-2023", "#e6550d"), ("forest edge zone 2023", "#a1d99b"),
                     ("core forest 2023", "#00441b"), ("national park boundary", "#000000")],
         "title": "Habitat around Bukit Barisan Selatan, 2023",
         "source": "Hansen GFC v1.13; WDPA. GEE.",
         "caption": f"Forest lost since 2000, forest within {EDGE_M} m of an edge, and core "
                    "forest beyond it. The black line is the national park."},
        {"kind": "table", "name": "ch53-metrics", "data": metrics_table,
         "floatfmt": ("", ",.0f", ",.0f", ".0%", ",.0f", ",.0f", ".0%"),
         "caption": "Forest and core forest, 2000 and 2023, inside and outside the park."},
        {"kind": "chart", "name": "ch53-change", "data": metrics_table, "plot": plot_change,
         "caption": "Percent change in all forest and in core forest."},
        {"kind": "chart", "name": "ch53-fhd", "data": fhd_pts, "plot": plot_fhd,
         "caption": "GEDI foliage height diversity of remaining forest, 2019-2023."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(metrics_table())
