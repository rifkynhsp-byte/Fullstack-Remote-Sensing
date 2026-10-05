#| title: Land suitability with the FAO framework (Python)
#| description: The author's Bentala Aksa land-suitability rules for jarak (Jatropha curcas) in Pangandaran, rebuilt with public layers: suitability classes, the factor that limits each place, and what one wrong input band does to the map.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 48 | Is this land suitable for this crop, and if not, why not?

FAO land evaluation sorts land into S1 (highly suitable), S2 (moderately),
S3 (marginally) and N (not suitable). Each factor gets its own class from
threshold ranges; the land takes the class of its WORST factor (the law of
the limiting factor).

Rules: the author's Bentala Aksa script for jarak (Jatropha curcas):

    class  mean temp (°C)  annual rain (mm)   soil pH        slope (°)
    S1     24-35           700-1,400          6.0-7.0        < 8
    S2     20-32           600-1,800          5.5-7.2        < 15
    S3     16-50           500-4,000          < 14 (x10)     < 30
    N      everything else (inside the area)

Inputs: WorldClim V1 (BIO1 mean temperature, BIO12 annual precipitation),
OpenLandMap soil pH (H2O, x10, topsoil), SRTM slope.

The original script read BIO18 (rain of the warmest quarter) as "annual
rain". Both versions are run, to show what one band does.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([108.40, -7.85, 108.85, -7.50], None, False)   # Pangandaran
wc = ee.Image("WORLDCLIM/V1/BIO")
temp = wc.select("bio01").divide(10).rename("temp")             # °C x 10 in WorldClim V1
rain = wc.select("bio12").rename("rain")                          # annual precipitation, mm
rain_bio18 = wc.select("bio18").rename("rain")                    # warmest-quarter rain, mm
ph = ee.Image("OpenLandMap/SOL/SOL_PH-H2O_USDA-4C1A2A_M/v02").select("b0").rename("ph")  # x10
slope = ee.Terrain.slope(ee.Image("USGS/SRTMGL1_003")).rename("slope")

# Factor classes: 1 = S1, 2 = S2, 3 = S3, 4 = N
def factor_class(img, s1, s2, s3):
    """s1, s2, s3 are (low, high) ranges; outside s3 is N."""
    c = ee.Image(4)
    c = c.where(img.gt(s3[0]).And(img.lt(s3[1])), 3)
    c = c.where(img.gt(s2[0]).And(img.lt(s2[1])), 2)
    c = c.where(img.gt(s1[0]).And(img.lt(s1[1])), 1)
    return c


def suitability(rain_img):
    f = ee.Image.cat(
        factor_class(temp, (24, 35), (20, 32), (16, 50)).rename("temp"),
        factor_class(rain_img, (700, 1400), (600, 1800), (500, 4000)).rename("rain"),
        factor_class(ph, (60, 70), (55, 72), (0, 140)).rename("ph"),
        factor_class(slope, (-1, 8), (-1, 15), (-1, 30)).rename("slope"))
    overall = f.reduce(ee.Reducer.max()).rename("class")
    # Which factor sets the class (first factor equal to the worst one)
    lim = ee.Image(0)
    for k, b in reversed(list(enumerate(["temp", "rain", "ph", "slope"], 1))):
        lim = lim.where(f.select(b).eq(overall), k)
    return overall.clip(aoi), lim.rename("limit").updateMask(overall.gt(1)).clip(aoi), f


land = ee.Image("ESA/WorldCover/v200/2021").select("Map").neq(80)   # not water
cls_ok, lim_ok, factors_ok = suitability(rain)
cls_orig, _, _ = suitability(rain_bio18)
NAMES = {1: "S1 highly suitable", 2: "S2 moderately suitable", 3: "S3 marginally suitable",
         4: "N not suitable"}


def area_table():
    area = ee.Image.pixelArea().divide(1e4)
    rows = []
    for label, c in [("annual rain (BIO12, corrected)", cls_ok),
                     ("original script (BIO18 as annual rain)", cls_orig)]:
        g = (area.addBands(c.updateMask(land)).reduceRegion(
            ee.Reducer.sum().group(1, "class"), aoi, 90, maxPixels=1e10).get("groups").getInfo())
        for d in g:
            rows.append({"input": label, "class": NAMES[int(d["class"])], "area_ha": d["sum"]})
    df = pd.DataFrame(rows).pivot(index="class", columns="input", values="area_ha").fillna(0)
    return df.reset_index()


def factor_frame():
    s = (factors_ok.addBands(temp.rename("t")).addBands(rain.rename("r"))
         .addBands(rain_bio18.rename("r18")).addBands(ph.rename("p")).addBands(slope.rename("s"))
         .updateMask(land).sample(region=aoi, scale=250, numPixels=1500, seed=1))
    return pd.DataFrame([f["properties"] for f in s.getInfo()["features"]])


def plot_factors(df):
    fig, axes = plt.subplots(1, 4, figsize=(11, 2.9))
    spec = [("t", "Mean temperature (°C)", [(24, 35), (20, 32)]),
            ("r", "Annual rain BIO12 (mm)", [(700, 1400), (600, 1800)]),
            ("p", "Soil pH (x10)", [(60, 70), (55, 72)]),
            ("s", "Slope (°)", [(0, 8), (0, 15)])]
    for ax, (col, lab, (s1, s2)) in zip(axes, spec):
        ax.hist(df[col].dropna(), 30, color="#9aa5b1")
        ax.axvspan(*s2, color="#fdae61", alpha=0.25, label="S2 range")
        ax.axvspan(*s1, color="#1a9641", alpha=0.25, label="S1 range")
        ax.set_title(lab, loc="left", fontsize=9)
    axes[1].hist(df["r18"].dropna(), 30, color="#c0392b", alpha=0.5, label="BIO18 (wrong)")
    axes[0].legend(frameon=False, fontsize=7)
    axes[1].legend(frameon=False, fontsize=7)
    fig.suptitle("Where the landscape sits against each rule", x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    return fig


def products():
    pal = ["1a9641", "a6d96a", "fdae61", "d7191c"]
    return [
        {"kind": "map", "name": "ch48-suitability", "image": cls_ok.updateMask(land),
         "region": aoi, "vis": {"min": 1, "max": 4, "palette": pal},
         "classes": [(NAMES[k], "#" + p) for k, p in zip(range(1, 5), pal)],
         "title": "Suitability for jarak, Pangandaran",
         "source": "WorldClim V1; OpenLandMap pH; SRTM. Rules: Bentala Aksa. GEE.",
         "caption": "Each pixel takes the class of its worst factor."},
        {"kind": "map", "name": "ch48-limiting", "image": lim_ok.updateMask(land), "region": aoi,
         "vis": {"min": 1, "max": 4, "palette": ["e41a1c", "377eb8", "984ea3", "ff7f00"]},
         "classes": [("temperature", "#e41a1c"), ("rainfall", "#377eb8"),
                     ("soil pH", "#984ea3"), ("slope", "#ff7f00")],
         "title": "What holds each place back", "source": "This chapter's factor classes.",
         "caption": "The factor that sets the class wherever land is below S1. This is the "
                    "map a planner needs: it says what would have to change."},
        {"kind": "chart", "name": "ch48-factors", "data": factor_frame, "plot": plot_factors,
         "caption": "Distribution of each factor over the landscape against the S1 and S2 "
                    "ranges. The red histogram is what the original script used as rain."},
        {"kind": "table", "name": "ch48-area", "data": area_table,
         "floatfmt": ("", ",.0f", ",.0f"),
         "caption": "Area in each class with the corrected and the original rainfall band."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(area_table())
