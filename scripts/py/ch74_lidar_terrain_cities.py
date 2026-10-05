#| title: LiDAR beyond the forest: landslide terrain and a city in 3D (Python)
#| description: Compares a 1 m LiDAR terrain model with 30 m SRTM and Copernicus DEMs at the 2014 Oso landslide (hillshade, profile, slope distribution, roughness), then uses the Netherlands' 0.5 m AHN4 surface and terrain models to measure building heights, urban tree canopy, rooftop solar potential and land below sea level in central Rotterdam.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 74 | LiDAR beyond the forest: terrain and cities

Airborne LiDAR is best known for trees (Chapters 32, 54 and 33), but most
LiDAR flown in the world is flown for terrain and for cities. Two national
programmes make that data free, and Earth Engine carries both as rasters:

  USGS 3DEP 1 m  bare-earth terrain models for the United States
  AHN4           0.5 m surface (DSM) and terrain (DTM) models for the Netherlands

Part 1 asks what a 1 m LiDAR terrain model shows at a landslide that a 30 m
global DEM cannot: Oso, Washington, where a slope failure on 22 March 2014
buried the Steelhead Haven neighbourhood. Part 2 turns the gap between the
surface and the ground into a 3D city: building heights, tree canopy, roofs
suitable for solar panels and land below sea level in central Rotterdam.

Samples are saved to data/ch74_*.csv so the analysis and the R twin run
without Earth Engine.

Environment: pip install earthengine-api pandas numpy matplotlib
"""

import os
from pathlib import Path

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2] if "__file__" in globals() else Path(".")
DATA = Path(os.environ.get("LIDAR_DATA", ROOT / "data"))
OSO = [-121.875, 48.266, -121.815, 48.300]          # the slide, the river and SR 530
TRANSECT = ((-121.848, 48.297), (-121.848, 48.270))  # north to south across the slide
ROTTERDAM = [4.462, 51.900, 4.500, 51.925]           # city centre, the Maas and Kop van Zuid
SOLAR_KWH_M2 = 1000      # assumption: yearly irradiation on a well-oriented roof in the Netherlands, kWh/m2
PANEL_EFF = 0.20         # assumption: module efficiency, with system losses taken as 0 for a screening estimate


def box(b):
    return ee.Geometry.Rectangle(b, None, False)


def cached(name, build):
    f = DATA / f"ch74_{name}.csv"
    if f.exists():
        return pd.read_csv(f)
    df = build()
    DATA.mkdir(parents=True, exist_ok=True)
    df.to_csv(f, index=False, float_format="%.5g")
    return df


# PART 1. Oso: three terrain models of the same slope ---------------------------------------------
def dems():
    """1 m LiDAR (3DEP, flown 2016), 30 m SRTM (2000) and 30 m Copernicus GLO-30 (2011-2015)."""
    g = box(OSO)
    lidar = ee.ImageCollection("USGS/3DEP/1m").filterBounds(g).mosaic().rename("elev")
    lidar = lidar.setDefaultProjection(ee.ImageCollection("USGS/3DEP/1m").filterBounds(g).first().projection())
    srtm = ee.Image("USGS/SRTMGL1_003").rename("elev")
    cop = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").filterBounds(g).select("DEM").mosaic() \
        .setDefaultProjection(ee.Projection("EPSG:4326").atScale(30)).rename("elev")
    return {"LiDAR 1 m (3DEP 2016)": (lidar, 1), "SRTM 30 m (2000)": (srtm, 30), "Copernicus 30 m": (cop, 30)}


def hillshade(dem):
    return ee.Terrain.hillshade(dem, 315, 35)


def profile():
    """Elevation every 5 m along the transect, from each DEM at its own resolution."""
    def build():
        (x0, y0), (x1, y1) = TRANSECT
        n = 600
        pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x0 + (x1 - x0) * i / (n - 1), y0 + (y1 - y0) * i / (n - 1)]),
                                               {"i": i}) for i in range(n)])
        rows = None
        for name, (img, scale) in dems().items():
            vals = img.reduceRegions(pts, ee.Reducer.first(), scale).getInfo()["features"]
            col = pd.DataFrame([{"i": v["properties"]["i"], name: v["properties"].get("first")} for v in vals])
            rows = col if rows is None else rows.merge(col, on="i")
        length = 6378137 * np.radians(abs(y1 - y0))
        rows["distance_m"] = rows.i / (n - 1) * length
        return rows.drop(columns="i").sort_values("distance_m")
    return cached("oso_profile", build)


def slope_stats():
    """Slope distribution and roughness for each DEM over the same box."""
    def build():
        g = box(OSO)
        rows = []
        for name, (img, scale) in dems().items():
            s = ee.Terrain.slope(img)
            rough = s.reduceNeighborhood(ee.Reducer.stdDev(), ee.Kernel.square(15, "meters")).rename("rough")
            st = s.rename("slope").addBands(s.gt(35).rename("steep")).addBands(rough).reduceRegion(
                ee.Reducer.mean().combine(ee.Reducer.percentile([50, 95]), "", True), g, scale, maxPixels=1e9).getInfo()
            rows.append({"DEM": name, "cell (m)": scale, "mean slope (°)": st["slope_mean"], "95th pct slope (°)": st["slope_p95"],
                         "area steeper than 35° (%)": 100 * st["steep_mean"], "roughness (SD of slope, °)": st["rough_mean"]})
        return pd.DataFrame(rows)
    return cached("oso_slopes", build)


def plot_profile(t):
    p = profile()
    fig, ax = plt.subplots(figsize=(9, 3.8))
    for c, col, lw in [("LiDAR 1 m (3DEP 2016)", "k", 1.2), ("SRTM 30 m (2000)", "#d95f02", 1.6), ("Copernicus 30 m", "#1b9e77", 1.6)]:
        ax.plot(p.distance_m, p[c], color=col, lw=lw, label=c)
    ax.set_xlabel("distance along the transect, north to south (m)"); ax.set_ylabel("elevation (m)")
    ax.legend(frameon=False, fontsize=8); ax.spines[["top", "right"]].set_visible(False)
    L = p["LiDAR 1 m (3DEP 2016)"]
    seg = lambda a, b: p[(p.distance_m >= a) & (p.distance_m < b)]
    plat, dep = seg(700, 1250), seg(1650, 2000)       # forested plateau; the 2014 deposit on the valley floor
    up = (plat["SRTM 30 m (2000)"] - plat["LiDAR 1 m (3DEP 2016)"]).mean(), (plat["Copernicus 30 m"] - plat["LiDAR 1 m (3DEP 2016)"]).mean()
    down = (dep["LiDAR 1 m (3DEP 2016)"] - dep[["SRTM 30 m (2000)", "Copernicus 30 m"]].mean(axis=1)).mean()
    for a, b, txt in [(700, 1250, "forested plateau"), (1650, 2000, "2014 deposit")]:
        ax.axvspan(a, b, color="#eeeeee", zorder=0); ax.text((a + b) / 2, ax.get_ylim()[1] * 0.97, txt, ha="center", va="top", fontsize=8)
    ax.set_title(f"The 30 m DEMs sit {up[0]:.0f}-{up[1]:.0f} m above the LiDAR ground on the forested plateau (they see the canopy),\n"
                 f"and the LiDAR sits {down:.0f} m above them on the valley floor, where the 2014 deposit now lies",
                 loc="left", fontsize=9.5, fontweight="bold")
    fig.tight_layout()
    return fig


# PART 2. Rotterdam: a city from the surface minus the ground ---------------------------------------------
def ahn():
    g = box(ROTTERDAM)
    a = ee.ImageCollection("AHN/AHN4").filterBounds(g).mosaic()
    proj = ee.ImageCollection("AHN/AHN4").filterBounds(g).first().select("dsm").projection()
    dsm, dtm = a.select("dsm").setDefaultProjection(proj), a.select("dtm").setDefaultProjection(proj)
    # The DTM has no ground under buildings (LiDAR never reached it): fill the holes from the
    # surrounding ground, widening the search until even large buildings are filled.
    # Ground is smooth, so the filling runs on a 2 m copy (16 times fewer cells) and is resampled back.
    filled = dtm.reduceResolution(ee.Reducer.mean(), maxPixels=64).reproject(proj.atScale(2))
    for r in (10, 30, 80):
        filled = filled.unmask(filled.focalMedian(r, "square", "meters"))
    filled = filled.resample("bilinear")
    ndsm = dsm.subtract(filled).max(0).rename("ndsm")
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(g).filterDate("2022-05-01", "2022-09-30")
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20)).median())
    ndvi = s2.normalizedDifference(["B8", "B4"]).rename("ndvi")
    water = dtm.mask().Not().And(dsm.mask().Not()).rename("water")      # no LiDAR return at all: open water
    roof_slope = ee.Terrain.slope(dsm.focalMedian(1, "square", "meters")).rename("roof_slope")
    aspect = ee.Terrain.aspect(dsm.focalMedian(1, "square", "meters")).rename("aspect")
    return {"dsm": dsm, "dtm": filled.rename("ground"), "ndsm": ndsm, "ndvi": ndvi, "slope": roof_slope, "aspect": aspect, "water": water}


def classes(a):
    """Building: taller than 2.5 m and not green. Tree: taller than 2.5 m and green."""
    tall = a["ndsm"].gt(2.5)
    building = tall.And(a["ndvi"].lt(0.3)).rename("building")
    tree = tall.And(a["ndvi"].gte(0.4)).rename("tree")
    # Slope at a building's edge measures the wall, not the roof: judge roofs on the interior only,
    # 1 m in from every edge.
    roof = building.focalMin(1, "square", "meters").rename("roof")
    # Solar: flat roofs (< 10°) or pitched roofs (10-60°) facing between south-east and south-west
    south = a["aspect"].gte(135).And(a["aspect"].lte(225))
    suitable = roof.And(a["slope"].lt(10).Or(a["slope"].lt(60).And(south))).rename("solar")
    return building, tree, suitable, roof


def city_sample():
    """A random sample of 0.5 m cells with every layer, for the charts and the R twin."""
    def build():
        a = ahn()
        b, t, s, rf = classes(a)
        img = ee.Image.cat([a["ndsm"], a["dtm"], a["ndvi"], a["slope"], a["aspect"], b, t, s, rf]).unmask(-9999)
        rows = []
        for seed in range(4):              # getInfo returns at most 5,000 features, so draw four batches
            fc = img.sample(box(ROTTERDAM), 0.5, numPixels=5000, seed=seed, geometries=False, tileScale=4)
            rows += [f["properties"] for f in fc.getInfo()["features"]]
        return pd.DataFrame(rows).replace(-9999, np.nan)
    return cached("rotterdam_sample", build)


def city_table():
    """Area shares and totals over the whole box at 0.5 m (Earth Engine), not from the sample."""
    def build():
        a = ahn()
        b, t, s, rf = classes(a)
        area = ee.Image.pixelArea()
        img = ee.Image.cat([area.rename("total"), area.updateMask(b).rename("building"), area.updateMask(rf).rename("roof"), area.updateMask(t).rename("tree"),
                            area.updateMask(s).rename("solar"), a["ndsm"].updateMask(b).multiply(area).rename("volume"),
                            area.updateMask(a["dtm"].lt(0)).rename("below_sea"), area.updateMask(a["water"]).rename("water")])
        r = img.reduceRegion(ee.Reducer.sum(), box(ROTTERDAM), 1, maxPixels=1e10, tileScale=16).getInfo()   # 1 m is plenty for totals
        return pd.DataFrame([r])
    r = cached("rotterdam_totals", build).iloc[0]
    land = r.total - r.water
    rows = [
        ("area of the box (ha)", r.total / 1e4),
        ("open water, no LiDAR return (%)", 100 * r.water / r.total),
        ("ground below sea level (NAP 0 m), share of land (%)", 100 * r.below_sea / land),
        ("building footprint, share of land (%)", 100 * r.building / land),
        ("tree canopy, share of land (%)", 100 * r.tree / land),
        ("mean building height (m)", r.volume / r.building),
        ("built volume per hectare of land (m³)", r.volume / (land / 1e4)),
        ("roof area suitable for solar (% of roof interiors)", 100 * r.solar / r.roof),
        ("screening solar yield (GWh/yr)", r.solar * SOLAR_KWH_M2 * PANEL_EFF / 1e6),
    ]
    return pd.DataFrame(rows, columns=["measure", "value"])


def plot_city(t):
    d = city_sample()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    b, tr = d[d.building == 1].ndsm, d[d.tree == 1].ndsm
    bins = np.arange(2.5, 60, 1.5)
    a1.hist(b, bins=bins, color="#636363", alpha=0.8, label=f"buildings (median {b.median():.0f} m)")
    a1.hist(tr, bins=bins, color="#1b7837", alpha=0.7, label=f"trees (median {tr.median():.0f} m)")
    a1.set_yscale("log"); a1.set_xlabel("height above ground (m)"); a1.set_ylabel("0.5 m cells in the sample (log)")
    a1.legend(frameon=False, fontsize=8); a1.set_title("Heights: buildings against trees", loc="left", fontsize=9)
    roofs = d[d.roof == 1]
    a2.hist(roofs.roof_slope.clip(upper=70), bins=np.arange(0, 72, 2), color="#e6550d")
    a2.axvline(10, color="k", ls=":", lw=1); a2.text(11, a2.get_ylim()[1] * 0.9, "flat roofs < 10°", fontsize=8)
    a2.set_xlabel("roof slope (°)"); a2.set_ylabel("cells")
    a2.set_title("Roof slopes: the flat roof dominates a modern centre", loc="left", fontsize=9)
    for a in (a1, a2):
        a.spines[["top", "right"]].set_visible(False)
    tt = t.set_index("measure").value
    fig.suptitle(f"Central Rotterdam: {tt.iloc[3]:.0f} % of the land under buildings averaging {tt.iloc[5]:.0f} m, "
                 f"{tt.iloc[4]:.0f} % under trees, {tt.iloc[2]:.0f} % of the ground below sea level",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


def products():
    oso = box(OSO)
    d = dems()
    rot = box(ROTTERDAM)
    a = ahn()
    b, tr, s, _ = classes(a)
    hs = hillshade(a["dsm"]).visualize(min=60, max=255)
    return [
        {"kind": "map", "name": "ch74-oso-lidar", "image": hillshade(d["LiDAR 1 m (3DEP 2016)"][0]), "region": oso,
         "vis": {"min": 0, "max": 255, "palette": ["#000000", "#ffffff"]}, "title": "Oso landslide: LiDAR 1 m hillshade (2016)", "source": "USGS 3DEP 1 m. GEE.",
         "caption": "Bare-earth LiDAR two years after the slide: the head scarp, the hummocky deposit across the river, "
                    "and older slide scars along the valley wall that the forest hides from optical imagery."},
        {"kind": "map", "name": "ch74-oso-srtm", "image": hillshade(d["SRTM 30 m (2000)"][0]), "region": oso,
         "vis": {"min": 0, "max": 255, "palette": ["#000000", "#ffffff"]}, "title": "The same slope in SRTM 30 m (2000)", "source": "NASA SRTM v3. GEE.",
         "caption": "The global 30 m DEM, fourteen years before the slide. Valley and plateau are there; the landforms are not."},
        {"kind": "chart", "name": "ch74-oso-profile", "data": slope_stats, "plot": plot_profile, "live": False,
         "caption": "Elevation along a north-south transect across the slide, from each terrain model."},
        {"kind": "table", "name": "ch74-oso-slopes", "data": slope_stats, "floatfmt": ("", ".0f", ".1f", ".1f", ".1f", ".1f"),
         "caption": "Slope and roughness of the same box in three terrain models."},
        {"kind": "map", "name": "ch74-rotterdam-ndsm", "image": hs.blend(a["ndsm"].updateMask(a["ndsm"].gt(2.5)).visualize(
             min=2.5, max=60, palette=["#ffffcc", "#fd8d3c", "#e31a1c", "#800026", "#3f007d"], opacity=0.75)),
         "region": rot, "vis": {"min": 0, "max": 255, "bands": ["vis-red", "vis-green", "vis-blue"]},
         "title": "Central Rotterdam: height above ground (nDSM = DSM - DTM)", "source": "AHN4 0.5 m. GEE.",
         "caption": "Heights above 2.5 m over a hillshade of the surface model. Purple marks the towers of the centre and "
                    "Kop van Zuid; colours are capped at 60 m."},
        {"kind": "map", "name": "ch74-rotterdam-classes",
         "image": ee.Image(0).where(tr, 1).where(b, 2).where(s, 3).updateMask(a["ndsm"].mask()),
         "region": rot, "vis": {"min": 0, "max": 3, "palette": ["#f0f0f0", "#1b7837", "#969696", "#fd8d3c"]},
         "classes": [("ground and low objects", "#f0f0f0"), ("tree canopy", "#1b7837"), ("building (other roof)", "#969696"), ("roof suitable for solar", "#fd8d3c")],
         "title": "Buildings, trees and solar-suitable roofs", "source": "AHN4 + Sentinel-2 NDVI. GEE.",
         "caption": "Tall and not green is a building, tall and green a tree; suitable roofs are flat or face south."},
        {"kind": "map", "name": "ch74-rotterdam-below-sea", "image": a["dtm"], "region": rot,
         "vis": {"min": -6, "max": 6, "palette": ["#08306b", "#4292c6", "#c6dbef", "#ffffff", "#fdd49e", "#d7301f", "#7f0000"]},
         "title": "Ground elevation relative to NAP (≈ mean sea level), m", "source": "AHN4 DTM 0.5 m, gaps under buildings filled. GEE.",
         "caption": "Blue is below sea level. The quays along the Maas are built up above it; the polders behind lie below."},
        {"kind": "table", "name": "ch74-rotterdam", "data": city_table, "floatfmt": ("", ".1f"),
         "caption": f"Central Rotterdam in numbers. Solar yield assumes {SOLAR_KWH_M2} kWh/m² per year and {PANEL_EFF:.0%} efficiency: a screening figure, not a design."},
        {"kind": "chart", "name": "ch74-rotterdam-chart", "data": city_table, "plot": plot_city, "live": False,
         "caption": "Height distributions and roof slopes from a random sample of 20,000 cells."},
    ]


if __name__ == "__main__":
    import json
    k = os.path.expanduser(os.environ.get("BOOK_EE_KEY", "~/.config/fullstack-rs/ee-key.json")); info = json.load(open(k))
    ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], k), project=info.get("project_id"))
    pd.set_option("display.width", 200)
    print(slope_stats().round(1)); print(profile().describe().round(1)); print(city_table().round(1))
    print(city_sample().describe().round(1))
