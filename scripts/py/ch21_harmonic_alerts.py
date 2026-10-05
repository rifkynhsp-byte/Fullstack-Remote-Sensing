#| title: Harmonic regression, radar change and alert rules on real data (Python)
#| description: Fits a harmonic model to eight years of Sentinel-2 NDVI at a pixel cleared for the new capital and raises an alert with a persistence rule; applies the same model to every pixel of the core zone, compares it with Sentinel-1 log-ratio change, and measures what a minimum mapping unit and a stable test year do to the change map.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 21 | From fitted seasons to change alerts, on real data

The synthetic example earlier in the chapter shows the mechanism. Here it
meets reality: a pixel in the core zone of Nusantara, Indonesia's new capital,
that was vegetated until clearing for construction. Then the same model runs
on every pixel of the core zone, and Sentinel-1 radar gives an independent
second opinion that does not care about cloud.
"""

import json
import os

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PIXEL = [116.6948, -0.9876]                         # vegetated in 2019, bare or built by 2023
BOX = ee.Geometry.Rectangle([116.66, -1.02, 116.75, -0.93], None, False)
# Sentinel-2 surface reflectance with Cloud Score+ starts here in 2019, so the season is learned on
# 2019-2020, two years with no clearing. No trend term: fitted on two years, a trend extrapolates
# wildly (the first version of this script predicted an NDVI of 1.2 by 2024 and raised a false alert).
FIT = ("2019-01-01", "2021-01-01")
Z, RUN = 3.0, 3                                     # alert: three consecutive observations below -3 sigma
T0 = 2017.0


# PART 1. NDVI observations, cloud-screened with Cloud Score+ --------------------------------
def s2_ndvi(region, start="2017-01-01", end="2025-01-01"):
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    def one(im):
        t = ee.Date(im.get("system:time_start"))
        years = t.difference(ee.Date.fromYMD(2017, 1, 1), "year")
        nd = im.updateMask(im.select("cs").gte(0.6)).normalizedDifference(["B8", "B4"]).rename("NDVI")
        return nd.addBands(ee.Image.constant(years).float().rename("t")).set("system:time_start", t.millis())
    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region).filterDate(start, end)
            .linkCollection(cs, ["cs"]).map(one))


def harmonic_terms(img):
    """Intercept and two annual harmonics: 1, cos 2pi t, sin 2pi t, cos 4pi t, sin 4pi t (no trend, see FIT)."""
    t = img.select("t")
    w = t.multiply(2 * np.pi)
    return (ee.Image.constant(1).rename("c")
            .addBands(w.cos().rename("cos1")).addBands(w.sin().rename("sin1"))
            .addBands(w.multiply(2).cos().rename("cos2")).addBands(w.multiply(2).sin().rename("sin2"))
            .addBands(img.select("NDVI")).float()
            .copyProperties(img, ["system:time_start"]))     # keep the date, or filterDate finds nothing


TERMS = ["c", "cos1", "sin1", "cos2", "sin2"]


# PART 2. One pixel: fit, residuals, alert ---------------------------------------------------
_cache = {}


def pixel_frame():
    if "px" in _cache:
        return _cache["px"]
    pt = ee.Geometry.Point(PIXEL)
    col = s2_ndvi(pt)
    fc = col.map(lambda im: ee.Feature(None, im.reduceRegion(ee.Reducer.first(), pt, 10)).set("ms", im.get("system:time_start")))
    d = pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]]).dropna(subset=["NDVI"])
    d["date"] = pd.to_datetime(d.ms, unit="ms")
    d = d.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    X = np.column_stack([np.ones(len(d)), *[f(k * 2 * np.pi * d.t) for k in (1, 2) for f in (np.cos, np.sin)]])
    fit = (d.date >= FIT[0]) & (d.date < FIT[1])
    beta, *_ = np.linalg.lstsq(X[fit], d.NDVI[fit], rcond=None)
    d["fitted"] = X @ beta
    d["resid"] = d.NDVI - d.fitted
    sigma = d.resid[fit].std()
    below = (d.resid < -Z * sigma).astype(int)
    run = below.groupby((below != below.shift()).cumsum()).cumsum() * below     # length of the current run
    d["alert"] = run >= RUN
    _cache.update(px=d, sigma=sigma, fitmask=fit)
    return d


def pixel_table():
    d = pixel_frame()
    fit = _cache["fitmask"]
    first = d[d.alert & ~fit].date.min()
    false_in_fit = int(d[fit].alert.sum())
    first_below = d[(d.resid < -Z * _cache["sigma"]) & ~fit].date.min()
    return pd.DataFrame([
        ("clear observations, 2019-2024", len(d)),
        ("used to fit the season (2019-2020)", int(fit.sum())),
        ("residual standard deviation in the fit period (NDVI)", round(_cache["sigma"], 3)),
        ("first observation below -3 sigma", first_below.strftime("%d %b %Y") if pd.notna(first_below) else "none"),
        ("alert (third consecutive observation below -3 sigma)", first.strftime("%d %b %Y") if pd.notna(first) else "none"),
        ("alerts the same rule raises inside the fit period", false_in_fit),
    ], columns=["measure", "value"])


def plot_pixel(t):
    d = pixel_frame()
    fit = _cache["fitmask"]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True, gridspec_kw={"height_ratios": [1.3, 1]})
    a1.scatter(d.date, d.NDVI, s=9, color=np.where(fit, "#1b7837", "#555555"), label="clear observations")
    a1.plot(d.date, d.fitted, color="#2a78d6", lw=1.3, label="harmonic model, fitted on 2019-2020")
    a1.axvspan(pd.Timestamp(FIT[0]), pd.Timestamp(FIT[1]), color="#eef5ee", zorder=0)
    a1.set_ylabel("NDVI"); a1.legend(frameon=False, fontsize=8, loc="lower left")
    a2.scatter(d.date, d.resid, s=9, color=np.where(d.alert, "#c0392b", "#888888"))
    a2.axhline(-Z * _cache["sigma"], color="#c0392b", ls=":", lw=1)
    a2.axhline(0, color="k", lw=0.5)
    a2.set_ylabel("residual (NDVI)")
    first = d[d.alert & ~fit].date.min()
    if pd.notna(first):
        for a in (a1, a2):
            a.axvline(first, color="#c0392b", lw=1)
        a2.text(first, a2.get_ylim()[0] * 0.9, f" alert {first:%b %Y}", color="#c0392b", fontsize=8)
    for a in (a1, a2):
        a.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"One pixel in the capital's core zone ({PIXEL[0]}° E, {abs(PIXEL[1])}° S): the season, then the clearing",
                 x=0.01, ha="left", fontweight="bold", fontsize=10)
    fig.tight_layout()
    return fig


# PART 3. Every pixel: the same model, as a change map -------------------------------------------
def harmonic_change(test_start, test_end, fit=FIT):
    """Mean residual in the test window, in units of each pixel's own fit-period residual SD."""
    col = s2_ndvi(BOX, fit[0], test_end).map(harmonic_terms)
    train = col.filterDate(*fit)
    coef = (train.select(TERMS + ["NDVI"]).reduce(ee.Reducer.linearRegression(len(TERMS), 1))
            .select("coefficients").arrayProject([0]).arrayFlatten([TERMS]))
    predict = lambda im: im.select("NDVI").subtract(im.select(TERMS).multiply(coef).reduce("sum")).rename("r")
    sd = train.map(predict).reduce(ee.Reducer.stdDev())
    test = col.filterDate(test_start, test_end).map(predict).mean()
    return test.divide(sd).rename("z")


def optical_change():
    return harmonic_change("2023-01-01", "2024-01-01").lt(-Z).rename("optical")


def radar_change():
    """Sentinel-1 VH, same orbit direction, 2019 against 2023: change in dB (the log ratio)."""
    s1 = lambda y: (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(BOX).filterDate(f"{y}-01-01", f"{y + 1}-01-01")
                    .filter(ee.Filter.eq("instrumentMode", "IW")).filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
                    .select("VH").median().focalMedian(30, "circle", "meters"))
    return s1(2023).subtract(s1(2019)).rename("dB")


def change_table():
    opt = optical_change()
    db = radar_change()
    sar = db.abs().gt(3).rename("sar")
    mmu = opt.selfMask().connectedPixelCount(100, True).gte(10).unmask(0).And(opt).rename("opt_mmu")   # 10 px = 0.1 ha
    stable_test = harmonic_change("2020-01-01", "2021-01-01", fit=("2019-01-01", "2020-01-01")).lt(-Z).rename("stable")
    dw = lambda y: (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(BOX)
                    .filterDate(f"{y}-01-01", f"{y + 1}-01-01").select("label").mode())
    dwc = dw(2019).neq(dw(2023)).rename("dw")
    one_year = harmonic_change("2023-01-01", "2024-01-01", fit=("2019-01-01", "2020-01-01")).lt(-Z).rename("one_year")
    img = ee.Image.cat([opt, mmu, sar, opt.And(sar).rename("both"), stable_test, one_year, dwc,
                        opt.And(dwc).rename("opt_dw"), sar.And(dwc).rename("sar_dw"), ee.Image(1).rename("all")])
    r = img.multiply(ee.Image.pixelArea().divide(1e4)).reduceRegion(ee.Reducer.sum(), BOX, 10, maxPixels=1e10, tileScale=8).getInfo()
    rows = [
        ("area of the box (ha)", r["all"]),
        ("optical harmonic change, 2023 (ha)", r["optical"]),
        ("  after a 0.1 ha minimum mapping unit (ha)", r["opt_mmu"]),
        ("radar change, VH 2023 vs 2019 differs by more than 3 dB (ha)", r["sar"]),
        ("both optical and radar (ha)", r["both"]),
        ("optical change where Dynamic World's label also changed (%)", 100 * r["opt_dw"] / max(r["optical"], 1)),
        ("radar change where Dynamic World's label also changed (%)", 100 * r["sar_dw"] / max(r["sar"], 1)),
        ("Dynamic World label changed, whole box (%)", 100 * r["dw"] / r["all"]),
        ("same rule, fit on 2019 only: change in 2023 (ha)", r["one_year"]),
        ("same rule, fit on 2019 only: 'change' in 2020, before clearing (ha)", r["stable"]),
    ]
    return pd.DataFrame(rows, columns=["measure", "value"])


def change_rgb():
    """Red: optical only; blue: radar only; magenta: both."""
    opt, sar = optical_change(), radar_change().abs().gt(3)
    code = ee.Image(0).where(opt.And(sar.Not()), 1).where(sar.And(opt.Not()), 2).where(opt.And(sar), 3).selfMask()
    base = (s2_ndvi(BOX, "2023-01-01", "2024-01-01").select("NDVI").median()
            .visualize(min=0, max=0.9, palette=["ffffff", "d9d9d9", "737373"]))
    return base.blend(code.visualize(min=1, max=3, palette=["e41a1c", "377eb8", "984ea3"]))


def products():
    return [
        {"kind": "chart", "name": "ch21-pixel", "data": pixel_table, "plot": plot_pixel, "live": False,
         "caption": "Every clear Sentinel-2 observation of one pixel, 2019-2024. Green: the observations the model was fitted on."},
        {"kind": "table", "name": "ch21-pixel-table", "data": pixel_table, "caption": "The alert in numbers."},
        {"kind": "map", "name": "ch21-change-map", "image": change_rgb(), "region": BOX,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "classes": [("optical (harmonic) only", "#e41a1c"), ("radar (log ratio) only", "#377eb8"), ("both", "#984ea3")],
         "title": "Change in the core zone of Nusantara, 2023", "source": "Sentinel-2 (Cloud Score+), Sentinel-1 VH. GEE.",
         "caption": "Over a 2023 NDVI backdrop (dark = green)."},
        {"kind": "table", "name": "ch21-change-table", "data": change_table, "floatfmt": ("", ".0f"),
         "caption": "Optical and radar change in the box, checked against Dynamic World and against a year with no expected clearing."},
    ]


if __name__ == "__main__":
    k = os.path.expanduser(os.environ.get("BOOK_EE_KEY", "~/.config/fullstack-rs/ee-key.json")); info = json.load(open(k))
    ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], k), project=info.get("project_id"))
    print(pixel_table()); print(change_table())
