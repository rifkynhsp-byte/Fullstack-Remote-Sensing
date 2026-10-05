#| title: Spectral indices, and which one separates what (Python)
#| description: The same indices as the JavaScript tab, run from Python.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 12 | Band math in Python: NDVI, EVI, SAVI, NDWI, MNDWI, CMRI, MVI.
Same composite, same formulas, same palettes as the JavaScript tab.
"""

import ee
import matplotlib.pyplot as plt

aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60])   # Mahakam Delta


def mask_and_scale(image):
    scl = image.select("SCL")
    clear = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
    return image.updateMask(clear).divide(10000).select("B.*")


composite = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
             .filterDate("2023-01-01", "2023-12-31")
             .filterBounds(aoi)
             .map(mask_and_scale)
             .median()
             .clip(aoi))

ndvi = composite.normalizedDifference(["B8", "B4"]).rename("NDVI")
evi = composite.expression(
    "2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))",
    {"NIR": composite.select("B8"), "RED": composite.select("B4"),
     "BLUE": composite.select("B2")}).rename("EVI")
L = 0.5
savi = composite.expression(
    "((NIR - RED) / (NIR + RED + L)) * (1 + L)",
    {"NIR": composite.select("B8"), "RED": composite.select("B4"), "L": L}).rename("SAVI")
ndwi = composite.normalizedDifference(["B3", "B8"]).rename("NDWI")
mndwi = composite.normalizedDifference(["B3", "B11"]).rename("MNDWI")
cmri = ndvi.subtract(ndwi).rename("CMRI")

green, nir, swir = composite.select("B3"), composite.select("B8"), composite.select("B11")
denominator = swir.subtract(green)
mvi = (nir.subtract(green)
       .divide(denominator.where(denominator.abs().lt(0.001), 0.001))
       .rename("MVI"))

indices = composite.addBands([ndvi, evi, savi, ndwi, mndwi, cmri, mvi])

# The CMRI histogram (ui.Chart.image.histogram in JavaScript)
cmri_hist = cmri.reduceRegion(
    reducer=ee.Reducer.fixedHistogram(-0.5, 1.5, 40), geometry=aoi,
    scale=100, maxPixels=1e9, bestEffort=True).getArray("CMRI")
cmri_table = ee.FeatureCollection(cmri_hist.toList().map(
    lambda row: ee.Feature(None, {"cmri": ee.List(row).get(0),
                                  "pixels": ee.List(row).get(1)})))

# Mean index value over dense vegetation and over permanent water
water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gt(80)
land_veg = ndvi.gt(0.6)


def summarise(mask, label):
    stats = (indices.select(["NDVI", "EVI", "SAVI", "NDWI", "MNDWI", "CMRI"])
             .updateMask(mask).reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi,
                                            scale=60, maxPixels=1e9, bestEffort=True))
    return ee.Feature(None, stats).set("surface", label)


index_means = ee.FeatureCollection([
    summarise(land_veg, "dense vegetation (NDVI > 0.6)"),
    summarise(water, "permanent water (JRC > 80 %)")])


def plot_cmri_histogram(df):
    """Look for two peaks: water on the left, vegetation on the right."""
    df = df.sort_values("cmri")
    fig, ax = plt.subplots(figsize=(7, 3.2))
    width = df["cmri"].diff().median()
    threshold = 0.0            # the valley between the peaks; try moving it
    colours = ["#0047AB" if v < threshold else "#14a37f" for v in df["cmri"]]
    ax.bar(df["cmri"], df["pixels"], width=width, align="edge", color=colours)
    ax.axvline(threshold, color="#b2182b", lw=1, ls="--")
    ax.text(threshold, ax.get_ylim()[1] * 0.95, f"  threshold {threshold}",
            color="#b2182b", fontsize=8, va="top")
    ax.set_xlabel("CMRI = NDVI − NDWI")
    ax.set_ylabel("Pixels (100 m sample)")
    ax.set_title("CMRI across the delta: two peaks, one threshold", loc="left")
    return fig


def products():
    src = "Sentinel-2 SR Harmonized 2023 median. Google Earth Engine."
    return [
        {"kind": "map", "name": "ch12-ndvi", "image": ndvi, "region": aoi,
         "vis": {"min": -0.2, "max": 0.9, "palette": ["AF963C", "F6E652", "0C6316", "023E0A"]},
         "legend": "NDVI", "title": "NDVI", "source": src,
         "caption": "NDVI. Inside the vegetated delta almost everything is dark green: "
                    "the index has saturated and cannot tell one dense canopy from another."},
        {"kind": "map", "name": "ch12-mndwi", "image": mndwi, "region": aoi,
         "vis": {"min": -0.5, "max": 0.5, "palette": ["E9DEB5", "FFFFFF", "8ED2E5", "0047AB"]},
         "legend": "MNDWI", "title": "MNDWI", "source": src,
         "caption": "MNDWI uses SWIR instead of NIR, so wet vegetation stays on the dry "
                    "side and open water, ponds and channels stand out cleanly."},
        {"kind": "map", "name": "ch12-cmri", "image": cmri, "region": aoi,
         "vis": {"min": -0.5, "max": 1.5, "palette": ["0047AB", "FFFFFF", "14a37f", "075e11"]},
         "legend": "CMRI (NDVI − NDWI)", "title": "CMRI, a mangrove-oriented index",
         "source": src,
         "caption": "CMRI stretches the contrast between water and vegetation, which "
                    "is what makes a single threshold usable in the histogram below."},
        {"kind": "chart", "name": "ch12-cmri-hist", "data": cmri_table,
         "plot": plot_cmri_histogram,
         "caption": "CMRI histogram over the study area. The valley between the two "
                    "peaks is where a threshold belongs."},
        {"kind": "table", "name": "ch12-index-means", "data": index_means,
         "columns": ["surface", "NDVI", "EVI", "SAVI", "NDWI", "MNDWI", "CMRI"],
         "floatfmt": ".2f",
         "caption": "Mean index values over dense vegetation and permanent water."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(indices.bandNames().getInfo())
