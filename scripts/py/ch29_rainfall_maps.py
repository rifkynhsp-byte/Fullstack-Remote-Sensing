#| title: Three maps, three kinds of colour (Python)
#| description: The same three CHIRPS maps of Indonesia as the JavaScript tab: a sequential map of how much, a diverging map of wetter or drier, and a categorical map of which season.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 29 | One dataset (CHIRPS pentads), three questions, three colour jobs.

    How much rain falls in a year?          sequential: one hue, light to dark
    Was 2023 wetter or drier than normal?   diverging: two hues, neutral at zero
    In which season is the wettest month?   categorical: distinct hues, no order
"""

import ee

indonesia = ee.Geometry.Rectangle([94.8, -11.2, 141.2, 6.2], None, False)
pentads = (ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD").select("precipitation")
           .filterBounds(indonesia))
BASE = ("1991-01-01", "2021-01-01")          # the 1991-2020 normal period

# 1. Sequential: mean annual rainfall, 1991-2020 (mm per year)
annual_mean = pentads.filterDate(*BASE).sum().divide(30).rename("rain")

# 2. Diverging: 2023 as a percentage of that normal
rain_2023 = pentads.filterDate("2023-01-01", "2024-01-01").sum()
anomaly_pct = rain_2023.divide(annual_mean).subtract(1).multiply(100).rename("anom")

# 3. Categorical: the season that holds the wettest calendar month
normal = pentads.filterDate(*BASE)
monthly_clim = ee.ImageCollection([
    normal.filter(ee.Filter.calendarRange(m, m, "month")).sum().divide(30)
    .rename("rain").set("month", m) for m in range(1, 13)])
# Stack the 12 monthly means as an array and take the index of the largest.
wettest = monthly_clim.toArray().arrayProject([0]).arrayArgmax().arrayGet([0]).add(1)
# Dec-Feb = 0, Mar-May = 1, Jun-Aug = 2, Sep-Nov = 3
season = wettest.mod(12).divide(3).floor().rename("season")

land = annual_mean.mask()
SEQ = ["f7fbff", "deebf7", "c6dbef", "9ecae1", "6baed6", "4292c6", "2171b5",
       "08519c", "08306b"]                                   # one hue: blues
DIV = ["8c510a", "bf812d", "dfc27d", "f6e8c3", "f5f5f5", "c7eae5", "80cdc1",
       "35978f", "01665e"]                                   # brown to teal
CAT = ["0072B2", "E69F00", "D55E00", "009E73"]               # Okabe-Ito
SRC = "CHIRPS v2.0 pentads (Funk et al. 2015), Google Earth Engine"


def products():
    return [
        {"kind": "map", "name": "ch29-map-sequential", "image": annual_mean,
         "region": indonesia, "vis": {"min": 1000, "max": 4500, "palette": SEQ},
         "legend": "Mean annual rainfall, 1991-2020 (mm)", "width": 1600,
         "title": "How much? Mean annual rainfall", "source": SRC,
         "caption": "Sequential: one hue from light to dark, because the question has one "
                    "direction (more rain). The stretch runs from 1,000 to 4,500 mm; "
                    "values outside it are drawn at the ends."},
        {"kind": "map", "name": "ch29-map-diverging", "image": anomaly_pct,
         "region": indonesia, "vis": {"min": -50, "max": 50, "palette": DIV},
         "legend": "2023 rainfall compared with 1991-2020 (%)", "width": 1600,
         "title": "Wetter or drier? 2023 against normal", "source": SRC,
         "caption": "Diverging: brown for drier, teal for wetter, near-white for normal. "
                    "The colour scale is symmetric around zero, so equal colours mean "
                    "equal departures in both directions."},
        {"kind": "map", "name": "ch29-map-categorical", "image": season.updateMask(land),
         "region": indonesia, "vis": {"min": 0, "max": 3, "palette": CAT}, "width": 1600,
         "classes": [("Dec-Feb", "#0072B2"), ("Mar-May", "#E69F00"),
                     ("Jun-Aug", "#D55E00"), ("Sep-Nov", "#009E73")],
         "title": "Which season? The wettest month, 1991-2020", "source": SRC,
         "caption": "Categorical: four seasons, four unrelated hues from the Okabe-Ito "
                    "set, which stays distinct for the common forms of colour blindness."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(annual_mean.reduceRegion(ee.Reducer.percentile([5, 50, 95]), indonesia,
                                   5566 * 4, maxPixels=1e9).getInfo())
