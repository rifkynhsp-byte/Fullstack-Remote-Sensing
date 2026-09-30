#| title: Pixels or objects? Earthquake landslides at Iburi (Python)
#| description: The same detection and scoring as the JavaScript tab, run from Python.

"""
CHAPTER 18 | Iburi, Hokkaido, 6 September 2018. Before/after Sentinel-2,
a pixel rule and an object (SNIC) rule, scored against a landslide inventory.
"""

import ee
import matplotlib.pyplot as plt

window = ee.Geometry.Rectangle([141.93, 42.70, 142.05, 42.80])   # Atsuma hills
inventory = ee.FeatureCollection("users/rifkynauvalhsp/IburiLandslideInventory/trainingset")


def mask_and_index(image):
    qa = image.select("QA60")
    clear = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
    s = image.updateMask(clear).divide(10000)
    return s.addBands([s.normalizedDifference(["B8", "B4"]).rename("ndvi"),
                       s.normalizedDifference(["B3", "B4"]).rename("grvi"),
                       s.normalizedDifference(["B2", "B4"]).rename("ndbrbi")])


s2 = ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(window)
pre = (s2.filterDate("2017-09-01", "2017-10-31")
       .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20)).map(mask_and_index).median())
post = (s2.filterDate("2018-09-07", "2018-10-31")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20)).map(mask_and_index).median())
change = (post.select(["ndvi", "grvi", "ndbrbi"])
          .subtract(pre.select(["ndvi", "grvi", "ndbrbi"]))
          .rename(["dNDVI", "dGRVI", "dNDBRBI"]))

aw3d = ee.ImageCollection("JAXA/ALOS/AW3D30/V4_1")
slope = ee.Terrain.slope(aw3d.select("DSM").filterBounds(window).mosaic()
                         .setDefaultProjection(aw3d.first().projection())).rename("slope")

# STEP 2. Pixel rule
pixel_rule = (change.select("dNDVI").lt(-0.3).And(change.select("dGRVI").lt(-0.05))
              .And(slope.gt(8)).rename("landslide"))

# STEP 2b. Normalise. Thin cloud, haze and sun angle shift the WHOLE scene:
# here the median dNDVI across the window is about -0.3, so a fixed -0.3
# threshold catches healthy forest. Subtract the scene-wide median first and
# threshold the change relative to the landscape.
shift = ee.Number(change.select("dNDVI").reduceRegion(
    reducer=ee.Reducer.median(), geometry=window, scale=30, maxPixels=1e9).get("dNDVI"))
relative = change.select("dNDVI").subtract(shift).rename("dNDVI_rel")
relative_rule = relative.lt(-0.2).And(slope.gt(8)).rename("landslide")

# STEP 3. Object rule, on the normalised change
snic = ee.Algorithms.Image.Segmentation.SNIC(
    image=post.select(["B4", "B8"]).addBands(relative),
    size=8, compactness=1, connectivity=8, neighborhoodSize=64,
    seeds=ee.Algorithms.Image.Segmentation.seedGrid(8))
object_means = (relative.addBands(slope).addBands(snic.select("clusters"))
                .reduceConnectedComponents(reducer=ee.Reducer.mean(),
                                           labelBand="clusters", maxSize=256))
object_rule = (object_means.select("dNDVI_rel").lt(-0.2)
               .And(object_means.select("slope").gt(8)).rename("landslide"))

# STEP 4. Score against the inventory, as areas
truth = ee.Image(0).paint(inventory, 1).rename("truth").clip(window)


def km2(img):
    return ee.Number(img.multiply(ee.Image.pixelArea()).divide(1e6).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=window, scale=10, maxPixels=1e10,
        tileScale=4).values().get(0))


def score(detected, label):
    d = detected.unmask(0)
    tp, fp, fn = km2(d.And(truth)), km2(d.And(truth.Not())), km2(d.Not().And(truth))
    precision, recall = tp.divide(tp.add(fp)), tp.divide(tp.add(fn))
    return ee.Feature(None, {
        "method": label, "detected_km2": tp.add(fp), "inventory_km2": tp.add(fn),
        "precision": precision, "recall": recall,
        "f1": precision.multiply(recall).multiply(2).divide(precision.add(recall))})


scores = ee.FeatureCollection([
    score(pixel_rule, "pixel rule, fixed threshold"),
    score(relative_rule, "pixel rule, normalised"),
    score(object_rule, "object rule (SNIC), normalised")])

# dNDVI inside and outside mapped landslides, for the chart
dndvi_samples = change.select("dNDVI").addBands(relative).addBands(truth).stratifiedSample(
    numPoints=600, classBand="truth", region=window, scale=10, seed=3, tileScale=4)


def plot_dndvi(df):
    """Change in NDVI on inventory landslides against everywhere else."""
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    bins = [x / 20 for x in range(-20, 9)]
    ax.hist(df.loc[df["truth"] == 0, "dNDVI"], bins=bins, alpha=0.6, color="#1b7837",
            label="outside inventory", density=True)
    ax.hist(df.loc[df["truth"] == 1, "dNDVI"], bins=bins, alpha=0.6, color="#d7301f",
            label="inside inventory", density=True)
    ax.axvline(-0.3, color="black", lw=1, ls="--")
    ax.text(-0.31, ax.get_ylim()[1] * 0.9, "fixed rule −0.3 ", ha="right", fontsize=7)
    shift = df.loc[df["truth"] == 0, "dNDVI"].median()
    ax.axvline(shift, color="#616e7c", lw=1, ls=":")
    ax.text(shift + 0.01, ax.get_ylim()[1] * 0.75, f" whole-scene shift {shift:.2f}",
            fontsize=7, color="#616e7c")
    ax.set_xlabel("dNDVI (Sep–Oct 2018 − Sep–Oct 2017)")
    ax.set_ylabel("Density")
    ax.set_title("Scars lose their canopy signal", loc="left")
    ax.legend(frameon=False, fontsize=8)
    return fig


inventory_outline = ee.Image().byte().paint(inventory, 1, 1).visualize(palette=["ffff00"])
detections_map = (post.visualize(bands=["B4", "B3", "B2"], min=0, max=0.25)
                  .blend(object_rule.selfMask().visualize(palette=["d7301f"], opacity=0.6))
                  .blend(inventory_outline))


def products():
    src = "Sentinel-2 L1C (Copernicus), AW3D30 v4.1. Inventory: GEE101 asset. GEE."
    rgb = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 0.25}
    return [
        {"kind": "map", "name": "ch18-before", "image": pre, "vis": rgb, "region": window,
         "title": "Before: September to October 2017", "source": src,
         "caption": "Forested hills around Atsuma one year before the earthquake, same season as the after image."},
        {"kind": "map", "name": "ch18-after", "image": post, "vis": rgb, "region": window,
         "title": "After: September to October 2018", "source": src,
         "caption": "The same hills weeks after the 6 September 2018 Iburi earthquake."},
        {"kind": "map", "name": "ch18-detections", "image": detections_map,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "region": window, "title": "Object rule (red) against the inventory (yellow)",
         "classes": [("object rule", "#d7301f"), ("inventory outline", "#ffff00")],
         "source": src,
         "caption": "SNIC objects flagged as landslide, with inventory polygons outlined."},
        {"kind": "chart", "name": "ch18-dndvi", "data": dndvi_samples, "plot": plot_dndvi,
         "caption": "dNDVI at 600 points inside and 600 outside the inventory. Even "
                    "outside, the change sits well below zero: the whole scene shifted, "
                    "which is why the fixed threshold over-detects."},
        {"kind": "table", "name": "ch18-scores", "data": scores,
         "columns": ["method", "detected_km2", "inventory_km2", "precision", "recall", "f1"],
         "floatfmt": ".2f",
         "caption": "Three rules scored by area against the inventory inside the window. "
                    "Normalising the change first trades some recall for far fewer "
                    "false alarms. Objects did not beat pixels here: many scars are "
                    "narrower than an 8-pixel SNIC object, so they merge into their "
                    "surroundings. That is the case Chapter 18 warns about."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(scores.getInfo())
