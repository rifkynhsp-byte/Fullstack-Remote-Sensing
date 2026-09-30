#| title: A defensible sampling design (Python)
#| description: The same design as the JavaScript tab, run from Python.

"""
CHAPTER 15 | Stratified sampling, spatial thinning, a reproducible split and a
separability check, in Python.

Needs two neighbours in the same folder (Colab: upload them first):
    ch10_multisensor_stack.py   the feature stack
    book_labels.py              WorldCover labels until you have field data
"""

import ee
import matplotlib.pyplot as plt

from book_labels import CLASS_NAMES, LULC_PALETTE, worldcover_classes
from ch10_multisensor_stack import get_analysis_ready_data

CLASS_PROPERTY = "landcover"
SCALE = 10            # metres, the finest band in the stack
SPLIT = 0.7           # proportion used for training
SEED = 42             # fixed, so the design is reproducible
CLASS_TARGETS = {0: 300, 1: 250, 2: 150, 3: 200, 4: 150}
MIN_SEPARATION = 60   # metres between retained samples

aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60])
image2023 = get_analysis_ready_data(2023, aoi)

# PART 1-2. Labels, then a fixed number of points per class
class_image = worldcover_classes(aoi)     # or your own polygons, painted to an image
samples = class_image.addBands(ee.Image.pixelLonLat()).stratifiedSample(
    numPoints=0, classBand=CLASS_PROPERTY, region=aoi, scale=SCALE, seed=SEED,
    classValues=list(CLASS_TARGETS), classPoints=list(CLASS_TARGETS.values()),
    geometries=True, tileScale=4)


# PART 3. Spatial thinning: keep one sample per 60 m grid cell
def grid_cell(feature):
    c = feature.geometry().coordinates()
    x = ee.Number(c.get(0)).multiply(111000).divide(MIN_SEPARATION).round().format("%d")
    y = ee.Number(c.get(1)).multiply(111000).divide(MIN_SEPARATION).round().format("%d")
    return feature.set("grid_cell", ee.String(x).cat("_").cat(y))


thinned = samples.map(grid_cell).distinct(["grid_cell"])

# PART 4. Split the POINTS first, then sample the image
with_random = thinned.randomColumn("random", SEED)
training = with_random.filter(ee.Filter.lt("random", SPLIT))
validation = with_random.filter(ee.Filter.gte("random", SPLIT))

# PART 5. Do the classes separate at all?
separability = (image2023.select(["B2", "B3", "B4", "B8", "B11", "NDVI", "S1_VH"])
                .sampleRegions(collection=thinned, properties=[CLASS_PROPERTY],
                               scale=SCALE, tileScale=4))


def count_row(label, fc):
    hist = ee.Dictionary(fc.aggregate_histogram(CLASS_PROPERTY))
    row = {"stage": label, "total": fc.size()}
    for k, name in enumerate(CLASS_NAMES):
        row[name] = hist.get(str(k), 0)
    return ee.Feature(None, row)


design_table = ee.FeatureCollection([
    count_row("drawn", samples), count_row("after thinning", thinned),
    count_row("training", training), count_row("validation", validation)])

# A picture of the design: points over the composite
dots = lambda fc: fc.map(lambda f: f.buffer(250))
design_map = (image2023.visualize(bands=["B4", "B3", "B2"], min=0, max=0.3)
              .blend(ee.Image().byte().paint(dots(training), 1)
                     .visualize(palette=["14a37f"]))
              .blend(ee.Image().byte().paint(dots(validation), 1)
                     .visualize(palette=["c8792b"])))


def plot_separability(df):
    """NDVI against radar backscatter, one colour per class."""
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    for k, name in enumerate(CLASS_NAMES):
        part = df[df["landcover"] == k]
        ax.scatter(part["NDVI"], part["S1_VH"], s=6, alpha=0.6,
                   color="#" + LULC_PALETTE[k], label=f"{name} (n={len(part)})")
    ax.set_xlabel("NDVI")
    ax.set_ylabel("Sentinel-1 VH (dB)")
    ax.set_title("Mangrove and other forest overlap: the hard pair", loc="left")
    ax.legend(frameon=False, fontsize=7, markerscale=2)
    return fig


def products():
    return [
        {"kind": "map", "name": "ch15-design", "image": design_map,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "region": aoi, "classes": [("training", "#14a37f"), ("validation", "#c8792b")],
         "title": "Stratified, thinned, split",
         "source": "Labels: ESA WorldCover 2021. Image: Sentinel-2 2023. GEE.",
         "caption": "Training and validation points after stratified sampling and 60 m "
                    "thinning. Labels come from WorldCover, a map rather than field data."},
        {"kind": "table", "name": "ch15-design-table", "data": design_table,
         "columns": ["stage", "total"] + CLASS_NAMES, "floatfmt": ".0f",
         "caption": "Points per class at each stage of the design."},
        {"kind": "chart", "name": "ch15-separability", "data": separability,
         "plot": plot_separability,
         "caption": "Water and urban sit apart. Mangrove and other forest overlap "
                    "heavily in both NDVI and VH, which is why later chapters add "
                    "terrain, texture and L-band radar."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(design_table.getInfo())
