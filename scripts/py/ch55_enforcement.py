#| title: Satellite evidence for policy enforcement (Python)
#| description: Two enforcement cases from public data. Forest clearing inside Gunung Leuser National Park year by year, with a dated before/after evidence package for the largest recent clearing; and new bare ground and turbid ponds along rivers in Merangin, Jambi, the signature of unlicensed gold mining, as a list of places to inspect.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 55 | From a map to a case file.

An enforcement officer does not need a pretty map. They need: WHERE (coordinates),
WHEN (a date window, bracketed by two dated images), HOW MUCH (area), and HOW WE
KNOW (a method anyone can rerun). This script produces exactly that.

    A  protected-area encroachment: Hansen loss inside Gunung Leuser National Park
       versus a 5 km band outside it, and the largest recent clearings as cases
    B  river gold mining (PETI): vegetation in 2019 that became bare ground or
       turbid water by 2024 within 1 km of a river, Merangin, Jambi

Satellites find LEADS. Whether a clearing is illegal depends on permits and
boundaries that only the authorities hold. The output is a list to inspect.
"""

import ee
import matplotlib.pyplot as plt
import pandas as pd

gfc = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")
lossyear = gfc.select("lossyear").unmask(0)
forest2000 = gfc.select("treecover2000").gte(30)
LAST = 24                                          # last loss year used (2024)

# ---------------------------------------------------------------- A. the park
park = (ee.FeatureCollection("WCMC/WDPA/current/polygons")
        .filter(ee.Filter.eq("NAME", "Gunung Leuser")).geometry().simplify(100))
band5k = park.buffer(5000, 100).difference(park, 100)
aoi_a = park.buffer(5000, 100).bounds(100)


def loss_table():
    """Hectares of forest cleared per year, inside the park and in the 5 km band."""
    area = ee.Image.pixelArea().divide(1e4).updateMask(forest2000)
    zone = ee.Image(0).paint(ee.FeatureCollection([ee.Feature(band5k)]), 2) \
        .paint(ee.FeatureCollection([ee.Feature(park)]), 1).rename("zone")
    img = area.addBands(lossyear.rename("year")).addBands(zone).updateMask(lossyear.gt(0))
    g = (img.reduceRegion(ee.Reducer.sum().group(1, "year").group(2, "zone"),
                          park.buffer(5000, 100), 30,
                          maxPixels=1e11, tileScale=16).get("groups").getInfo())
    rows = []
    for z in g:
        if z["zone"] == 0:
            continue
        for y in z["groups"]:
            if y["year"] <= LAST:
                rows.append({"year": 2000 + y["year"],
                             "zone": "inside the park" if z["zone"] == 1 else "5 km band outside",
                             "loss_ha": y["sum"]})
    df = pd.DataFrame(rows).pivot(index="year", columns="zone", values="loss_ha").fillna(0)
    return df.reset_index()


def plot_loss(df):
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.plot(df.year, df["inside the park"], color="#b2182b", lw=2, marker="o", ms=3,
            label="inside the park")
    ax.plot(df.year, df["5 km band outside"], color="#878787", lw=1.5, ls="--",
            label="5 km band outside")
    ax.set_ylabel("Forest cleared (ha per year)")
    ax.set_title("Forest clearing inside Gunung Leuser National Park", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


# The cases: connected clearings of 2021-2024 inside the park, largest first.
recent = lossyear.gte(21).And(lossyear.lte(LAST)).And(forest2000).selfMask()
patches = (recent.addBands(lossyear.rename("year"))
           .reduceToVectors(geometry=park, scale=30, geometryType="polygon",
                            eightConnected=True, labelProperty="lost",
                            reducer=ee.Reducer.mode(), maxPixels=1e10, tileScale=8)
           .map(lambda f: f.set("ha", f.geometry().area(10).divide(1e4))))
cases = patches.sort("ha", False).limit(10)


def case_table():
    rows = []
    for i, f in enumerate(cases.getInfo()["features"], 1):
        p = f["properties"]
        c = ee.Geometry(f["geometry"]).centroid(10).coordinates().getInfo()
        rows.append({"case": i, "loss_year": 2000 + int(p["mode"]), "area_ha": p["ha"],
                     "lon": round(c[0], 4), "lat": round(c[1], 4)})
    return pd.DataFrame(rows)


top = ee.Feature(cases.first())
top_year = ee.Number(top.get("mode")).add(2000)
box_a = top.geometry().bounds(10).buffer(600, 10).bounds(10)


def s2(start, end, region):
    def mask(i):
        cs = i.select("cs")
        return i.updateMask(cs.gte(0.6)).divide(10000)
    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region)
            .filterDate(start, end)
            .linkCollection(ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"), ["cs"])
            .map(mask).median())


def window(offset):
    y = top_year.add(offset)
    return s2(ee.Date.fromYMD(y, 1, 1), ee.Date.fromYMD(y, 12, 31), box_a)


outline_a = ee.Image().byte().paint(ee.FeatureCollection([top]), 1, 2)


def evidence(offset):
    rgb = window(offset).visualize(bands=["B4", "B3", "B2"], min=0.01, max=0.12, gamma=1.2)
    return rgb.blend(outline_a.visualize(palette=["ffff00"]))


# ---------------------------------------------------------------- B. the rivers
aoi_b = ee.Geometry.Rectangle([101.90, -2.45, 102.70, -1.95], None, False)
water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("max_extent")
near_river = (water.focalMax(1000, "circle", "meters").And(water.Not())
              .Or(water)).rename("near")          # river channel plus 1 km either side
built = ee.ImageCollection("ESA/WorldCover/v200").first().eq(50)


def dry(year):
    return s2(f"{year}-05-01", f"{year}-10-31", aoi_b)


def ndvi(img):
    return img.normalizedDifference(["B8", "B4"])


before, after = dry(2019), dry(2024)       # 2018: one Sentinel-2 SR scene here, half the area
# Bare or turbid: low NDVI and a bright red band (mud and muddy water), not clear water.
bare_after = ndvi(after).lt(0.2).And(after.select("B4").gt(0.06))
mining = (ndvi(before).gt(0.5).And(bare_after).And(near_river).And(built.Not())
          .selfMask().rename("mining"))
mining_clean = mining.updateMask(mining.connectedPixelCount(50, True).gte(10))  # >= 0.1 ha


def river_table():
    rows = []
    area = ee.Image.pixelArea().divide(1e4)
    for y in range(2019, 2025):
        img = dry(y)
        b = (ndvi(img).lt(0.2).And(img.select("B4").gt(0.06)).And(near_river)
             .And(built.Not()))
        ha = area.updateMask(b).reduceRegion(ee.Reducer.sum(), aoi_b, 60, maxPixels=1e11,
                                              tileScale=16).values().get(0)
        rows.append({"year": y, "bare_or_turbid_near_rivers_ha": ee.Number(ha).getInfo()})
    rows.append({"year": "new since 2019 (map)", "bare_or_turbid_near_rivers_ha":
                 area.updateMask(mining_clean).reduceRegion(ee.Reducer.sum(), aoi_b, 60,
                     maxPixels=1e11, tileScale=16).values().get(0).getInfo()})
    return pd.DataFrame(rows)


def plot_river(df):
    d = df[pd.to_numeric(df.year, errors="coerce").notna()]      # drop the summary row
    fig, ax = plt.subplots(figsize=(6.8, 3.2))
    ax.bar(d.year.astype(str), d.bare_or_turbid_near_rivers_ha, color="#a6611a")
    ax.set_ylabel("Bare ground or turbid water\nwithin 1 km of rivers (ha)")
    ax.set_title("Riverside bare ground, Merangin (dry season)", loc="left", fontsize=10)
    return fig


river_vis = (after.visualize(bands=["B4", "B3", "B2"], min=0.01, max=0.14, gamma=1.2)
             .blend(mining_clean.visualize(palette=["ff00ff"])))


def products():
    return [
        {"kind": "chart", "name": "ch55-park-loss", "data": loss_table, "plot": plot_loss,
         "caption": "Forest cleared per year inside Gunung Leuser National Park and in a 5 km "
                    "band around it (Hansen GFC v1.13, tree cover 2000 at least 30 %)."},
        {"kind": "table", "name": "ch55-cases", "data": case_table,
         "floatfmt": ("", "", ",.1f", ".4f", ".4f"),
         "caption": "The ten largest clearings of 2021-2024 inside the park: the start of a "
                    "case file. Year is the most common loss year within the patch."},
        {"kind": "map", "name": "ch55-before", "image": evidence(-1), "region": box_a,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "title": "Case 1, the year before", "source": "Sentinel-2 L2A; Hansen GFC. GEE.",
         "caption": "Case 1, Sentinel-2 median of the year before the clearing. Yellow: the "
                    "patch Hansen flags as lost."},
        {"kind": "map", "name": "ch55-after", "image": evidence(1), "region": box_a,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "title": "Case 1, the year after", "source": "Sentinel-2 L2A; Hansen GFC. GEE.",
         "caption": "The same patch, Sentinel-2 median of the year after. Two dated images "
                    "bracket when the clearing happened."},
        {"kind": "map", "name": "ch55-river", "image": river_vis, "region": aoi_b,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "classes": [("vegetated in 2019, bare or turbid in 2024, within 1 km of a river",
                      "#ff00ff")],
         "title": "New riverside bare ground, Merangin, 2019-2024",
         "source": "Sentinel-2 L2A; JRC GSW; ESA WorldCover. GEE.",
         "caption": "Magenta: vegetation in the 2019 dry season that was bare ground or muddy "
                    "water in 2024, within 1 km of a river, outside settlements. Leads to "
                    "inspect, not proof of illegal mining."},
        {"kind": "chart", "name": "ch55-river-series", "data": river_table, "plot": plot_river,
         "caption": "Bare ground or turbid water within 1 km of rivers, each dry season."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(loss_table())
