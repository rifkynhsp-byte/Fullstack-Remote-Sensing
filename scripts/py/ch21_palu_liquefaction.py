#| title: Palu, 28 September 2018: before, after, and who was exposed (Python)
#| description: The same change detection and exposure count as the JavaScript tab, in Python.

"""
CHAPTER 21 | Sentinel-2 change after the 2018 Palu earthquake, split into
inland (liquefaction flow slides) and coastal (tsunami) zones, with Open
Buildings and WorldPop counts inside each.
"""

import ee

palu = ee.Geometry.Rectangle([119.84, -0.98, 119.94, -0.87])
petobo = ee.Geometry.Rectangle([119.895, -0.975, 119.935, -0.940])


def prep(image):
    qa = image.select("QA60")
    clear = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
    s = image.updateMask(clear).divide(10000)
    return s.addBands(s.normalizedDifference(["B8", "B4"]).rename("ndvi"))


s2 = ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(palu)
before = (s2.filterDate("2018-07-01", "2018-09-27")
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)).map(prep).median())
after = (s2.filterDate("2018-09-29", "2018-11-30")
         .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)).map(prep).median())

d_ndvi = after.select("ndvi").subtract(before.select("ndvi"))
d_bright = (after.select(["B2", "B3", "B4"]).reduce(ee.Reducer.mean())
            .subtract(before.select(["B2", "B3", "B4"]).reduce(ee.Reducer.mean())))
land = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).lt(50)
changed = d_ndvi.lt(-0.2).And(d_bright.gt(0.02)).And(land)
changed = changed.updateMask(changed.connectedPixelCount(100).gte(50)).selfMask()

sea = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gt(80)
# Distance needs a grid in metres: an unprojected image would measure in degrees
# and call every pixel coastal. 30 m UTM, 256 pixels = 7.7 km search radius.
dist_sea = (sea.unmask(0).reproject(ee.Projection("EPSG:32750").atScale(30))
            .fastDistanceTransform(256).sqrt().multiply(30))
inland = changed.And(dist_sea.gt(500)).selfMask()      # keep only the 1s
coastal = changed.And(dist_sea.lte(500)).selfMask()

buildings = (ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
             .filterBounds(palu).filter(ee.Filter.gte("confidence", 0.75)))
worldpop = (ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "IDN"))
            .filter(ee.Filter.eq("year", 2018)))
# mosaic() forgets the native grid; give it back, or every later step runs at 1 degree.
people = worldpop.mosaic().setDefaultProjection(worldpop.first().projection())


def zone_stats(mask, label):
    ha = (mask.unmask(0).multiply(ee.Image.pixelArea()).divide(1e4)
          .reduceRegion(reducer=ee.Reducer.sum(), geometry=palu, scale=10, maxPixels=1e9)
          .values().get(0))
    hits = (mask.unmask(0).reduceRegions(
        collection=buildings.map(lambda b: ee.Feature(b.geometry().centroid(1))),
        reducer=ee.Reducer.first(), scale=10).filter(ee.Filter.eq("first", 1)).size())
    # A median composite has no fixed grid, so pin the mask to 10 m UTM before
    # asking what share of each 100 m population cell it covers.
    share = (mask.unmask(0).reproject(ee.Projection("EPSG:32750").atScale(10))
             .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=256)
             .reproject(people.projection()))
    pop = (people.updateMask(share.gt(0.5))
           .reduceRegion(reducer=ee.Reducer.sum(), geometry=palu, scale=100).values().get(0))
    return ee.Feature(None, {"zone": label, "changed_ha": ha, "buildings": hits,
                             "people": pop})


exposure = ee.FeatureCollection([
    zone_stats(inland, "inland (liquefaction flow slides)"),
    zone_stats(coastal, "within 500 m of the bay (tsunami)")])

rgb = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 0.25}
change_map = (after.visualize(**rgb)
              .blend(inland.visualize(palette=["d7301f"], opacity=0.7))
              .blend(coastal.visualize(palette=["2171b5"], opacity=0.7)))


def products():
    src = "Sentinel-2 L1C (Copernicus), JRC GSW. GEE."
    return [
        {"kind": "map", "name": "ch21-palu-before", "image": before, "vis": rgb,
         "region": petobo, "title": "Petobo, before (July to September 2018)",
         "source": src, "caption": "Petobo, south-east Palu, before the earthquake."},
        {"kind": "map", "name": "ch21-palu-after", "image": after, "vis": rgb,
         "region": petobo, "title": "Petobo, after (October to November 2018)",
         "source": src,
         "caption": "The same area weeks later. The neighbourhood slid as a single "
                    "sheet of liquefied ground."},
        {"kind": "map", "name": "ch21-palu-change", "image": change_map,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "region": palu, "title": "Change zones across Palu",
         "classes": [("inland change (liquefaction)", "#d7301f"),
                     ("within 500 m of the bay (tsunami)", "#2171b5")],
         "source": src,
         "caption": "Ground that lost vegetation or roofs and turned bright and bare, "
                    "split by distance from the bay. Look for the flow slides, the shore, "
                    "and the false alarms in harvested farmland."},
        {"kind": "table", "name": "ch21-palu-exposure", "data": exposure,
         "columns": ["zone", "changed_ha", "buildings", "people"],
         "floatfmt": ("", ".0f", ",.0f", ",.0f"),
         "caption": "Area of change and what stood inside it: Open Buildings v3 "
                    "footprints (confidence ≥ 0.75, centroid inside) and WorldPop 2018 "
                    "people. The inland figure includes false alarms. An exposure estimate "
                    "from a rule, not a damage census."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(exposure.getInfo())
