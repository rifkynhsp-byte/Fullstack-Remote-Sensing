#| title: Your first Earth Engine script (Python)
#| description: The same first script as the JavaScript tab, run from Python.

"""
CHAPTER 5 | Load a global elevation model, ask what it is, and draw it.

In Colab:
    import ee
    ee.Authenticate()
    ee.Initialize(project="your-cloud-project")
"""

import ee

# 1. Load a single image from the public catalogue
dem = ee.Image("CGIAR/SRTM90_V4")

# 2. Ask the server what it is holding. In Python you ask explicitly with
#    getInfo(); in the Code Editor, print() does the same round trip.
#    print(dem.getInfo())

# 3-4. Two renderings of the same numbers
grey = {"bands": ["elevation"], "min": 0, "max": 1200}
palette = {"bands": ["elevation"], "min": 0, "max": 1200,
           "palette": ["blue", "cyan", "green", "yellow", "red", "brown"]}

# 5. Longitude first. The same two numbers in the wrong order land somewhere else.
right = ee.Geometry.Point([117.161, -0.53])    # (longitude, latitude): Kalimantan
# Swapped, [-0.53, 117.161] would ask for latitude 117°, which does not exist.


def elevation_at(point, label):
    value = dem.reduceRegion(ee.Reducer.first(), point, 90).get("elevation")
    return ee.Feature(None, {"point": label, "elevation_m": value})


borneo = ee.Geometry.Rectangle([108.5, -4.5, 119.5, 7.5])


def products():
    return [
        {"kind": "map", "name": "ch05-dem-grey", "image": dem, "vis": grey,
         "region": borneo, "title": "SRTM elevation, greyscale",
         "source": "SRTM 90 m v4 (CGIAR-CSI). Google Earth Engine.",
         "caption": "The same data as the next map, stretched from 0 m (black) to "
                    "1,200 m (white). It answers 'how high', but slowly."},
        {"kind": "map", "name": "ch05-dem-palette", "image": dem, "vis": palette,
         "region": borneo, "legend": "Elevation (m)", "title": "SRTM elevation, palette",
         "source": "SRTM 90 m v4 (CGIAR-CSI). Google Earth Engine.",
         "caption": "A palette over the same 0 to 1,200 m range. The central highlands "
                    "of Borneo separate from the coastal lowlands at a glance."},
        {"kind": "table", "name": "ch05-lonlat", "data": ee.FeatureCollection([
            elevation_at(right, "[117.161, -0.53]  longitude first"),
            elevation_at(ee.Geometry.Point([117.161, 0.53]), "[117.161, 0.53]  sign of latitude flipped")]),
         "columns": ["point", "elevation_m"],
         "caption": "One flipped sign moves the point about 120 km. Swapping the two "
                    "numbers entirely gives a latitude of 117°, which does not exist."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(dem.bandNames().getInfo())
