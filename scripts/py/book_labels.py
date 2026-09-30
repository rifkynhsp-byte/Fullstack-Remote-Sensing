"""
book_labels.py | Labelled points for Chapters 15 to 18 when you have no field data yet.

ESA WorldCover 2021 (10 m) has a mangrove class, so it can stand in for
training polygons over the Mahakam Delta. It is a map, not ground truth:
any accuracy you compute against these labels measures agreement with
WorldCover, not correctness. Chapter 15 explains why that matters.

The book's five classes:
    0 mangrove         WorldCover 95
    1 other forest     WorldCover 10
    2 water            WorldCover 80
    3 bare/agriculture WorldCover 20, 30, 40, 60
    4 urban            WorldCover 50
"""

import ee

CLASS_PROPERTY = "landcover"
CLASS_NAMES = ["mangrove", "other forest", "water", "bare or agriculture", "urban"]
LULC_PALETTE = ["075e11", "358221", "1A5BAB", "FFDB5C", "ED022A"]


def worldcover_classes(aoi):
    """WorldCover 2021 remapped to the book's five classes, as an integer image."""
    wc = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
    return (wc.remap([95, 10, 80, 20, 30, 40, 60, 50],
                     [0, 1, 2, 3, 3, 3, 3, 4])
            .rename(CLASS_PROPERTY).toInt().clip(aoi))


def labelled_points(aoi, per_class=(300, 250, 150, 200, 150), seed=42, scale=10):
    """Stratified random points with a `landcover` property and geometry."""
    return worldcover_classes(aoi).stratifiedSample(
        numPoints=0, classBand=CLASS_PROPERTY, region=aoi, scale=scale, seed=seed,
        classValues=[0, 1, 2, 3, 4], classPoints=list(per_class),
        geometries=True, tileScale=4)
