#| title: Satellite-derived bathymetry around Kepulauan Seribu (Python)
#| description: Water depth from Sentinel-2 colour with the Stumpf log-ratio method, calibrated against GEBCO, limited to the shallow, clear water where it works, with Allen Coral Atlas reefs for context.

"""
CHAPTER 52 | How deep is the water, from colour alone?

Light weakens with depth, and blue light weakens more slowly than green.
Over a uniform bottom in clear water, the log-ratio of blue to green
reflectance rises with depth (Stumpf et al. 2003):

    ratio = ln(n * blue) / ln(n * green)          n a constant (1000) keeping logs positive
    depth = m1 * ratio - m0                         m1, m0 fitted against known depths

    imagery      Sentinel-2 L2A median, low-cloud scenes, B2 (blue), B3 (green)
    land, cloud  masked with the scene classification and NDWI
    calibration  GEBCO 2023 grid (~450 m) in its 0-20 m range: coarse, but public
    context      Allen Coral Atlas geomorphic zones

Real surveys calibrate against ICESat-2 laser photons or echo-sounder tracks.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

aoi = ee.Geometry.Rectangle([106.45, -5.80, 106.75, -5.50], None, False)   # Kepulauan Seribu
N = 1000.0


def prep(i):
    scl = i.select("SCL")
    water = scl.eq(6)                                            # SCL class 6: water
    return i.select(["B2", "B3", "B4", "B8"]).divide(10000).updateMask(water) \
        .copyProperties(i, ["system:time_start"])


s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi)
      .filterDate("2022-05-01", "2024-10-31")
      .filter(ee.Filter.calendarRange(5, 10, "month"))               # dry season, calmer, clearer
      .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 10)).map(prep))
comp = s2.median().clip(aoi)
ratio = (comp.select("B2").multiply(N).log().divide(comp.select("B3").multiply(N).log())
         .rename("ratio").setDefaultProjection("EPSG:32748", None, 10))

gebco = (ee.ImageCollection("projects/sat-io/open-datasets/gebco/gebco_grid").mosaic()
         .rename("elev").setDefaultProjection("EPSG:4326", None, 463))
gebco_depth = gebco.multiply(-1).rename("depth")                      # elevation < 0 under sea


def calibration_frame():
    """Ratio averaged to GEBCO's grid, paired with GEBCO depth, 0.5-20 m."""
    ratio_coarse = ratio.reduceResolution(ee.Reducer.mean(), True, 4096) \
        .reproject(gebco.projection())
    pts = (ratio_coarse.addBands(gebco_depth)
           .updateMask(gebco_depth.gt(0.5).And(gebco_depth.lt(20)))
           .sample(region=aoi, scale=463, numPixels=2000, seed=1))
    return pd.DataFrame([f["properties"] for f in pts.getInfo()["features"]]).dropna()


_fit = {}


def fit():
    if not _fit:
        d = calibration_frame()
        m1, m0 = np.polyfit(d.ratio, d.depth, 1)
        r2 = np.corrcoef(d.ratio, d.depth)[0, 1] ** 2
        _fit.update(m1=m1, m0=m0, r2=r2, n=len(d), df=d)
    return _fit


def plot_calibration(df):
    f = fit()
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.scatter(df.ratio, df.depth, s=10, color="#2a78d6", alpha=0.6)
    xs = np.linspace(df.ratio.min(), df.ratio.max(), 20)
    ax.plot(xs, f["m1"] * xs + f["m0"], color="#c0392b", lw=1.5,
            label=f"depth = {f['m1']:.1f} × ratio {f['m0']:+.1f}   (R² = {f['r2']:.2f})")
    ax.invert_yaxis()
    ax.set_xlabel("Stumpf ratio ln(n·blue) / ln(n·green), mean per GEBCO cell")
    ax.set_ylabel("GEBCO depth (m)")
    ax.set_title("Calibrating colour against charted depth", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def calibration_table(df):
    f = fit()
    return pd.DataFrame([{"cells": f["n"], "slope_m1": f["m1"], "intercept_m0": f["m0"],
                          "R2": f["r2"]}])


def depth_map():
    f = fit()
    d = ratio.multiply(f["m1"]).add(f["m0"]).rename("sdb")
    return d.updateMask(d.gte(0).And(d.lte(20)))


# Allen Coral Atlas geomorphic classes (values, names and colours from the asset)
REEF = [(11, "Shallow lagoon", "77d0fc"), (12, "Deep lagoon", "2ca2f9"),
        (13, "Inner reef flat", "c5a7cb"), (14, "Outer reef flat", "92739d"),
        (15, "Reef crest", "614272"), (16, "Terrestrial reef flat", "fbdefb"),
        (21, "Sheltered reef slope", "10bda6"), (22, "Reef slope", "288471"),
        (23, "Plateau", "cd6812"), (24, "Back reef slope", "befbff"), (25, "Patch reef", "ffba15")]
reefs = (ee.Image("ACA/reef_habitat/v2_0").select("geomorphic")
         .remap([v for v, _, _ in REEF], list(range(len(REEF)))).clip(aoi))
TRUE = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 0.12}


ORDER = ["Inner reef flat", "Outer reef flat", "Reef crest", "Shallow lagoon",
         "Back reef slope", "Reef slope", "Sheltered reef slope", "Plateau", "Deep lagoon"]
ratio_by_zone = (ratio.addBands(reefs.rename("zone"))
                 .stratifiedSample(numPoints=300, classBand="zone", region=aoi, scale=10,
                                   seed=3, tileScale=4))


def plot_zones(df):
    names = {k: n for k, (_, n, _) in enumerate(REEF)}
    df = df.assign(zone_name=df["zone"].astype(int).map(names))
    order = [z for z in ORDER if z in set(df.zone_name)]
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    ax.boxplot([df.loc[df.zone_name == z, "ratio"] for z in order], vert=False,
               tick_labels=order, showfliers=False, widths=0.55,
               medianprops={"color": "#c0392b", "lw": 2})
    ax.set_xlabel("Stumpf ratio (higher = deeper, if the method works)")
    ax.set_title("Does the colour ratio follow the reef zones' depth order?", loc="left",
                 fontsize=10)
    return fig


# Sensitivity: which choices make the ratio rank the reef zones by depth better?
# Expected depth rank of each zone (1 shallowest). Spearman rho between this rank and the ratio
# measures how well a version of the ratio orders depth, without any depth soundings.
DEPTH_RANK = {"Inner reef flat": 1, "Outer reef flat": 1, "Terrestrial reef flat": 1, "Reef crest": 2,
              "Shallow lagoon": 3, "Patch reef": 3, "Back reef slope": 4, "Reef slope": 4,
              "Sheltered reef slope": 4, "Deep lagoon": 5, "Plateau": 5}
NS = [10.0, 100.0, 1000.0, 10000.0]
MASKS = {"none": None,
         "red < 0.02 (threshold copied from clear-water studies)": ("red", 0.02),
         "NIR < 0.02 (glint and turbid plumes)": ("nir", 0.02)}


def _composites():
    clearest = ee.Image(s2.sort("CLOUDY_PIXEL_PERCENTAGE").first())
    return {"median of all dry-season scenes": comp,
            "20th percentile (darkest, less glint)": s2.reduce(ee.Reducer.percentile([20]))
                .rename(["B2", "B3", "B4", "B8"]).clip(aoi),
            "single clearest scene": clearest.clip(aoi)}


def _stack(c):
    bands = [c.select("B2").multiply(n).log().divide(c.select("B3").multiply(n).log()).rename(f"r{int(n)}")
             for n in NS]
    return ee.Image.cat(bands + [c.select("B4").rename("red"), c.select("B8").rename("nir"), reefs.rename("zone")])


def sensitivity_frame():
    from scipy import stats
    names = {k: n for k, (_, n, _) in enumerate(REEF)}
    rows = []
    for cname, c in _composites().items():
        pts = (_stack(c).stratifiedSample(numPoints=150, classBand="zone", region=aoi, scale=10, seed=5,
                                         tileScale=4).getInfo()["features"])
        d = pd.DataFrame([f["properties"] for f in pts]).dropna()
        d["rank"] = d.zone.astype(int).map(names).map(DEPTH_RANK)
        for mname, m in MASKS.items():
            dd = d if m is None else d[d[m[0]] < m[1]]
            for n in NS:
                rho = stats.spearmanr(dd["rank"], dd[f"r{int(n)}"])[0] if len(dd) > 30 else np.nan
                rows.append({"composite": cname, "mask": mname,
                             "n": int(n), "spearman_rho": rho,
                             "points": len(dd)})
    return pd.DataFrame(rows)


def sensitivity_table(d):
    w = d.pivot_table(index=["composite", "mask"], columns="n", values="spearman_rho", dropna=False, sort=False)
    w.columns = [f"rho, n={c:,}" for c in w.columns]
    pts = d.groupby(["composite", "mask"], sort=False)["points"].first()
    return w.assign(points=pts).reset_index()


def products():
    return [
        {"kind": "map", "name": "ch52-truecolour", "image": comp, "region": aoi, "vis": TRUE,
         "title": "Kepulauan Seribu, water pixels only", "source": "Sentinel-2 L2A, dry seasons 2022-2024. GEE.",
         "caption": "A dry-season median of clear water pixels, stretched to show the reef flats."},
        {"kind": "chart", "name": "ch52-calibration", "data": calibration_frame,
         "plot": plot_calibration,
         "caption": "The Stumpf ratio averaged to GEBCO's ~450 m grid against GEBCO depth "
                    "(0.5 to 20 m)."},
        {"kind": "table", "name": "ch52-fit", "data": calibration_frame,
         "transform": calibration_table, "floatfmt": (",.0f", ".1f", ".1f", ".2f"),
         "caption": "The calibration against GEBCO fails (R² near zero): a 450 m chart cell "
                    "averages reef flats and channels together, so it cannot calibrate a "
                    "10 m depth estimate."},
        {"kind": "map", "name": "ch52-ratio", "image": ratio.clip(aoi), "region": aoi,
         "vis": {"min": 1.0, "max": 1.15, "palette": ["c6dbef", "6baed6", "2171b5", "08306b"]},
         "legend": "Stumpf ratio: relative depth index (uncalibrated)",
         "title": "Relative depth from colour, Kepulauan Seribu",
         "source": "Sentinel-2 L2A. GEE.",
         "caption": "The log-ratio of blue to green over water pixels. Without good depth "
                    "soundings it is a relative index: lighter is shallower."},
        {"kind": "chart", "name": "ch52-zones", "data": ratio_by_zone, "plot": plot_zones,
         "caption": "The ratio within each Allen Coral Atlas reef zone, ordered roughly from "
                    "shallow (top) to deep (bottom)."},
        {"kind": "map", "name": "ch52-reefs", "image": reefs, "region": aoi,
         "vis": {"min": 0, "max": len(REEF) - 1, "palette": [c for _, _, c in REEF]},
         "classes": [(n, "#" + c) for _, n, c in REEF],
         "title": "Reef zones (Allen Coral Atlas)", "source": "Allen Coral Atlas v2. GEE.",
         "caption": "Mapped reef geomorphology for comparison: the shallow reef flats should "
                    "match the shallowest estimated depths."},
        {"kind": "table", "name": "ch52-sensitivity", "data": sensitivity_frame, "transform": sensitivity_table,
         "floatfmt": ("", "", ".2f", ".2f", ".2f", ".2f", ",.0f"),
         "caption": "How well each version of the ratio ranks the reef zones from shallow to deep (Spearman rho; "
                    "1 = perfect order, 0 = none). Rows: image composite and mask; columns: the constant n. Empty cells: too few points left to test."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(calibration_table(calibration_frame()))
