#| title: Paddy rice: crops per year, timing, calibrated yield and flood failure (Python)
#| description: Sentinel-1 VH time series of rice in Karawang (intensive, irrigated) and around Kasepuhan Ciptagelar (traditional, upland Sukabumi): crops per year, transplanting months, season length, a yield map calibrated to the official district production, and failed seasons.

"""
CHAPTER 45 | Rice through the clouds, in two very different places.

A rice field is flooded before transplanting: smooth water, very low VH
backscatter. As the crop grows, VH rises; at harvest it drops. Counting and
timing those cycles tells how a landscape farms.

    Karawang            irrigated lowland, the second-largest rice district of West Java
    Ciptagelar area     Cisolok, Sukabumi: the Kasepuhan Ciptagelar community keeps a
                        traditional calendar on terraced valleys inside a forested landscape

    data       Sentinel-1 IW GRD VH, 12-day composites, 2021-2024
    paddy      >= 1 flooding dip (VH < -21 dB) per year and a seasonal VH range >= 6 dB,
               on ESA WorldCover cropland
    yield      BPS: Karawang produced about 1.09 million t of dry milled grain (GKG) in 2023
               (preliminary figure, BPS West Java, 1 Nov 2023). Spread over the mapped
               harvests in proportion to MODIS GPP: a calibrated t/ha map.
    failure    a second dip within 25-75 days of the first, before any clear rise: the
               crop was drowned or failed and the field was replanted
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SITES = {"Karawang": [107.25, -6.35, 107.55, -6.05],
         "Ciptagelar area (Cisolok)": [106.40, -6.90, 106.60, -6.75]}
karawang_district = (ee.FeatureCollection("FAO/GAUL/2025/level2")
                     .filter(ee.Filter.eq("GAUL1_NAME", "Jawa Barat"))
                     .filter(ee.Filter.eq("GAUL2_NAME", "Karawang")).geometry())
PRODUCTION_2023_T = 1.09e6        # t GKG, BPS West Java preliminary figure (1 Nov 2023)

s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filter(ee.Filter.eq("instrumentMode", "IW"))
      .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")).select("VH"))
cropland = ee.Image("ESA/WorldCover/v200/2021").select("Map").eq(40)


def composites(region, start, end, step=12):
    col = s1.filterBounds(region)
    d0 = ee.Date(start)
    n = ee.Date(end).difference(d0, "day").divide(step).floor()
    def one(i):
        a = d0.advance(ee.Number(i).multiply(step), "day")
        empty = ee.Image.constant(0).rename("VH").updateMask(0)
        img = col.filterDate(a, a.advance(step, "day")).merge(ee.ImageCollection([empty])).mean()
        return (img.focalMedian(1.5, "square", "pixels").rename("VH")
                .set("system:time_start", a.millis()))
    return ee.ImageCollection(ee.List.sequence(0, n.subtract(1)).map(one))


def paddy_mask(region, start="2021-01-01", end="2024-01-01"):
    ts = composites(region, start, end)
    years = ee.Date(end).difference(ee.Date(start), "year")
    # A flooded spell lasts two or three composites: count only its start
    # (flooded now, not flooded in the previous composite).
    fl = ts.map(lambda i: i.lt(-21).unmask(0)).toList(200)
    n = fl.size()
    onsets = ee.ImageCollection(ee.List.sequence(1, n.subtract(1)).map(
        lambda i: ee.Image(fl.get(i)).And(ee.Image(fl.get(ee.Number(i).subtract(1))).Not())))
    dips = onsets.sum().divide(years)
    rng = (ts.reduce(ee.Reducer.percentile([90]))
           .subtract(ts.reduce(ee.Reducer.percentile([10]))))
    return dips.updateMask(dips.gte(1).And(rng.gte(6)).And(cropland)).rename("dips")


def site_series(name, n_fields=35):
    box = ee.Geometry.Rectangle(SITES[name], None, False)
    pts = (paddy_mask(box).sample(region=box, scale=20, numPixels=400, seed=5,
                                  geometries=True).limit(n_fields))
    col = composites(box, "2021-01-01", "2024-07-01")
    fc = col.map(lambda img: img.reduceRegions(pts, ee.Reducer.first(), 20)
                 .map(lambda f: f.set("t", img.get("system:time_start"))))
    rows = [dict(f["properties"], id=f["id"].split("_")[-1])
            for f in fc.flatten().getInfo()["features"]]
    df = pd.DataFrame(rows).rename(columns={"first": "VH"}).dropna(subset=["VH"])
    df["date"] = pd.to_datetime(df.t, unit="ms")
    return df[["id", "date", "VH"]].assign(site=name)


def ndvi_series(name="Ciptagelar area (Cisolok)", n_fields=35):
    """Small terraced fields among trees never reach the radar flooding threshold
    here (median seasonal VH range about 3.6 dB), so seasons are counted from
    Sentinel-2 NDVI instead: monthly medians of clear pixels, 2019-2023."""
    box = ee.Geometry.Rectangle(SITES[name], None, False)
    def prep(i):
        clear = i.select("SCL").remap([4, 5], [1, 1], 0)
        return i.normalizedDifference(["B8", "B4"]).rename("ndvi").updateMask(clear) \
            .copyProperties(i, ["system:time_start"])
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(box)
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80)).map(prep))
    months = [(y, m) for y in range(2019, 2024) for m in range(1, 13)]
    empty = ee.ImageCollection([ee.Image.constant(0).rename("ndvi").updateMask(0)])
    col = ee.ImageCollection([
        s2.filterDate(f"{y}-{m:02d}-01", ee.Date(f"{y}-{m:02d}-01").advance(1, "month"))
        .merge(empty).median().set("system:time_start", ee.Date(f"{y}-{m:02d}-15").millis())
        for y, m in months])
    pts = (cropland.selfMask().sample(region=box, scale=10, numPixels=500, seed=5,
                                      geometries=True).limit(n_fields))
    fc = col.map(lambda img: img.reduceRegions(pts, ee.Reducer.first(), 10)
                 .map(lambda f: f.set("t", img.get("system:time_start"))))
    rows = [dict(f["properties"], id=f["id"].split("_")[-1])
            for f in fc.flatten().getInfo()["features"]]
    df = pd.DataFrame(rows).rename(columns={"first": "ndvi"}).dropna(subset=["ndvi"])
    df["date"] = pd.to_datetime(df.t, unit="ms")
    return df[["id", "date", "ndvi"]].assign(site=name)


def ndvi_cycles(df):
    """A crop = an NDVI trough <= 0.45 followed within 5 months by a peak >= 0.6."""
    out = []
    for pid, d in df.sort_values("date").groupby("id"):
        v, t = d.ndvi.to_numpy(), d.date.to_numpy()
        i = 0
        while i < len(v):
            if v[i] <= 0.45:
                ahead = [j for j in range(i + 1, min(i + 6, len(v))) if v[j] >= 0.6]
                if ahead:
                    out.append({"id": pid, "trough": pd.Timestamp(t[i]),
                                "peak": pd.Timestamp(t[ahead[0]])})
                    i = ahead[0] + 1
                    continue
            i += 1
    return pd.DataFrame(out)


_c = {}


def series():
    if "df" not in _c:
        _c["df"] = site_series("Karawang")
    return _c["df"]


def cipta():
    if "df" not in _c:
        pass
    if "ndvi" not in _c:
        _c["ndvi"] = ndvi_series()
    return _c["ndvi"]


def seasons(df):
    out = []
    for (site, pid), d in df.sort_values("date").groupby(["site", "id"]):
        v, t = d.VH.to_numpy(), d.date.to_numpy()
        dips = [i for i in range(1, len(v) - 1)
                if v[i] < -21 and v[i] <= v[i - 1] and v[i] <= v[i + 1]]
        for k, i in enumerate(dips):
            j_end = dips[k + 1] if k + 1 < len(dips) else len(v)
            seg = v[i:j_end]
            j = i + int(np.argmax(seg))
            gap = ((t[dips[k + 1]] - t[i]) / np.timedelta64(1, "D")) if k + 1 < len(dips) else np.nan
            out.append({"site": site, "id": pid, "dip": pd.Timestamp(t[i]),
                        "days_to_peak": (t[j] - t[i]) / np.timedelta64(1, "D"),
                        "rise_dB": v[j] - v[i], "days_to_next_dip": gap})
    s = pd.DataFrame(out)
    s["failed"] = (s.days_to_next_dip.between(25, 75)) & (s.rise_dB < 4)
    return s


def plot_series(df):
    nd = cipta()
    fig, axes = plt.subplots(2, 1, figsize=(9, 5), sharex=True)
    for pid, f in list(df.groupby("id"))[:5]:
        axes[0].plot(f.date, f.VH, lw=1, alpha=0.85)
    axes[0].axhline(-21, color="#2a78d6", ls="--", lw=1)
    axes[0].set_ylabel("VH (dB)")
    axes[0].set_title("Karawang: Sentinel-1 VH, flooding dips and growth", loc="left", fontsize=10)
    for pid, f in list(nd.groupby("id"))[:5]:
        axes[1].plot(f.date, f.ndvi, lw=1, alpha=0.85)
    axes[1].axhline(0.6, color="#1b7837", ls="--", lw=1)
    axes[1].set_ylabel("NDVI")
    axes[1].set_title("Ciptagelar area: Sentinel-2 NDVI (radar dips too weak here)",
                      loc="left", fontsize=10)
    fig.tight_layout()
    return fig


def compare_table(df):
    s = seasons(df[(df.date >= "2021-01-01") & (df.date < "2024-01-01")])
    k_crops = s.groupby("id").size().div(3)
    nd = ndvi_cycles(cipta())
    c_crops = nd.groupby("id").size().div(5)
    def months(ts):
        c = ts.dt.month.value_counts()
        return ", ".join(pd.to_datetime(c.nlargest(3).index, format="%m").strftime("%b"))
    return pd.DataFrame([
        {"site": "Karawang (Sentinel-1 VH)", "fields": k_crops.size,
         "crops_per_year_median": k_crops.median(),
         "crops_per_year_range": f"{k_crops.min():.1f}-{k_crops.max():.1f}",
         "main_planting_months": months(s.dip),
         "median_days_to_peak": s.days_to_peak.median()},
        {"site": "Ciptagelar area (Sentinel-2 NDVI)", "fields": cipta().id.nunique(),
         "crops_per_year_median": c_crops.reindex(cipta().id.unique(), fill_value=0).median(),
         "crops_per_year_range": f"{c_crops.min() if len(c_crops) else 0:.1f}-{c_crops.max() if len(c_crops) else 0:.1f}",
         "main_planting_months": months(nd.trough) if len(nd) else "-",
         "median_days_to_peak": ((nd.peak - nd.trough).dt.days.median() if len(nd) else np.nan)}])


def plot_months(df):
    s = seasons(df[(df.date >= "2021-01-01") & (df.date < "2024-01-01")])
    nd = ndvi_cycles(cipta())
    fig, ax = plt.subplots(figsize=(8, 3.2))
    w = 0.4
    for k, (lab, ts, col) in enumerate([("Karawang (radar flooding dips)", s.dip, "#2a78d6"),
                                       ("Ciptagelar area (NDVI troughs)",
                                        nd.trough if len(nd) else pd.Series(dtype="datetime64[ns]"),
                                        "#1b7837")]):
        c = ts.dt.month.value_counts(normalize=True).reindex(range(1, 13), fill_value=0)
        ax.bar(np.arange(1, 13) + (k - 0.5) * w, c, w, label=lab, color=col)
    ax.set_xticks(range(1, 13), list("JFMAMJJASOND"))
    ax.set_ylabel("Share of season starts")
    ax.set_title("When each place starts a crop", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def failure_table(df):
    s = seasons(df)
    k = s[s.site == "Karawang"]
    k = k.assign(period=k.dip.dt.to_period("Q").astype(str))
    g = k.groupby("period").agg(seasons=("failed", "size"), failed=("failed", "sum"))
    g["failed_share"] = g.failed / g.seasons
    return g.reset_index()


# Calibrated yield, Karawang 2023
def yield_frame():
    pad = paddy_mask(karawang_district, "2023-01-01", "2024-01-01")
    gpp = (ee.ImageCollection("MODIS/061/MOD17A2HGF").select("Gpp")
           .filterDate("2023-01-01", "2024-01-01").sum().multiply(0.0001))   # kg C/m2
    area_ha = ee.Image.pixelArea().divide(1e4)
    s = (area_ha.updateMask(pad.mask()).rename("paddy_ha")
         .addBands(area_ha.multiply(pad).rename("harvested_ha"))
         .addBands(area_ha.multiply(gpp).updateMask(pad.mask()).rename("gpp_w"))
         .reduceRegion(ee.Reducer.sum(), karawang_district, 30, maxPixels=1e11, tileScale=16)
         .getInfo())
    implied = PRODUCTION_2023_T / s["harvested_ha"]
    return pd.DataFrame([{"paddy_area_ha": s["paddy_ha"], "harvested_area_ha_2023": s["harvested_ha"],
                          "crops_per_year_mean": s["harvested_ha"] / s["paddy_ha"],
                          "official_production_t": PRODUCTION_2023_T,
                          "implied_yield_t_per_ha": implied}])


def yield_map():
    pad = paddy_mask(karawang_district, "2023-01-01", "2024-01-01")
    gpp = (ee.ImageCollection("MODIS/061/MOD17A2HGF").select("Gpp")
           .filterDate("2023-01-01", "2024-01-01").sum().multiply(0.0001))
    per_season = gpp.divide(pad)                                   # GPP per crop
    mean_ps = per_season.reduceRegion(ee.Reducer.mean(), karawang_district, 500,
                                      maxPixels=1e10, tileScale=8).values().get(0)
    implied = ee.Number(PRODUCTION_2023_T).divide(
        ee.Image.pixelArea().divide(1e4).multiply(pad)
        .reduceRegion(ee.Reducer.sum(), karawang_district, 30, maxPixels=1e11, tileScale=16)
        .values().get(0))
    return per_season.divide(ee.Number(mean_ps)).multiply(implied).rename("t_ha").clip(
        karawang_district)


# Crops drowned: paddy that was growing in February (VH > -17 dB) and under
# water in March (VH < -21 dB). 2023 had floods in March; 2022 is the baseline.
def submerged(year):
    pad = paddy_mask(karawang_district).mask()
    col = s1.filterBounds(karawang_district)
    feb = col.filterDate(f"{year}-02-01", f"{year}-03-01").mean()
    mar = col.filterDate(f"{year}-03-01", f"{year}-04-01").min()
    return feb.gt(-17).And(mar.lt(-21)).And(pad).selfMask().rename("sub")


def submerged_table():
    rows = []
    for y in (2022, 2023):
        a = (ee.Image.pixelArea().divide(1e4).updateMask(submerged(y))
             .reduceRegion(ee.Reducer.sum(), karawang_district, 20, maxPixels=1e11,
                           tileScale=16).getInfo())
        rows.append({"year": y, "growing_paddy_flooded_in_March_ha": list(a.values())[0]})
    return pd.DataFrame(rows)


# Where did the 2023 loss come from: fewer crops or lower yield per crop?
# BPS West Java (1 Nov 2023): Karawang 2023 = 1.09 Mt GKG, down 130.2 kt on 2022.
PRODUCTION_T = {2022: 1.09e6 + 130.2e3, 2023: 1.09e6}


def years_table():
    area = ee.Image.pixelArea().divide(1e4)
    rows = []
    for y in (2021, 2022, 2023):
        pad = paddy_mask(karawang_district, f"{y}-01-01", f"{y + 1}-01-01")
        late = paddy_mask(karawang_district, f"{y}-07-01", f"{y + 1}-01-01")
        h = area.multiply(pad).reduceRegion(ee.Reducer.sum(), karawang_district, 30,
                                            maxPixels=1e11, tileScale=16).values().get(0)
        h2 = area.multiply(late.multiply(0.5)).reduceRegion(
            ee.Reducer.sum(), karawang_district, 30, maxPixels=1e11, tileScale=16).values().get(0)
        h, h2 = ee.Number(h).getInfo(), ee.Number(h2).getInfo()
        prod = PRODUCTION_T.get(y)
        rows.append({"year": y, "harvested_area_ha": h, "crops_started_Jul_Dec_ha": h2,
                     "official_production_t": prod if prod else np.nan,
                     "implied_yield_t_ha": prod / h if prod else np.nan})
    return pd.DataFrame(rows)


def products():
    return [
        {"kind": "map", "name": "ch45-paddy", "image": paddy_mask(karawang_district),
         "region": karawang_district.bounds(),
         "vis": {"min": 1, "max": 3, "palette": ["c7e9c0", "41ab5d", "005a32"]},
         "legend": "Rice crops per year (flooding dips, 2021-2023 mean)",
         "title": "Paddy fields of Karawang, seen by radar",
         "source": "Sentinel-1 GRD; ESA WorldCover cropland; GAUL. GEE.",
         "caption": "Cropland pixels with at least one flooding dip a year and a strong "
                    "seasonal VH range. Darker green: closer to three crops a year."},
        {"kind": "chart", "name": "ch45-series", "data": series, "plot": plot_series,
         "caption": "The rice signature in 12-day Sentinel-1 composites, five fields per site."},
        {"kind": "table", "name": "ch45-compare", "data": series, "transform": compare_table,
         "floatfmt": ("", ".0f", ".1f", "", "", ".0f"),
         "caption": "Two ways of farming rice. Karawang from radar (2021-2023); the "
                    "Ciptagelar area from optical NDVI cycles (2019-2023), because the "
                    "radar flooding signal is too weak in small terraced fields."},
        {"kind": "chart", "name": "ch45-months", "data": series, "plot": plot_months,
         "caption": "Months in which each place starts its crops."},
        {"kind": "table", "name": "ch45-yield", "data": yield_frame,
         "floatfmt": (",.0f", ",.0f", ".2f", ",.0f", ".2f"),
         "caption": "Karawang 2023: paddy and harvested area mapped from radar, and the "
                    "average yield they imply when set against the official production."},
        {"kind": "map", "name": "ch45-yield-map", "image": yield_map(),
         "region": karawang_district.bounds(),
         "vis": {"min": 3, "max": 9, "palette": ["fee08b", "d9ef8b", "66bd63", "1a9850"]},
         "legend": "Calibrated yield 2023 (t GKG per ha per crop)",
         "title": "A yield map that adds up to the official total",
         "source": "Sentinel-1; MODIS MOD17; BPS West Java 2023 (preliminary). GEE.",
         "caption": "Official district production shared out over the mapped harvests in "
                    "proportion to MODIS GPP per crop. The total is right by construction; "
                    "the pattern is only as good as GPP's link to grain."},
        {"kind": "table", "name": "ch45-years", "data": years_table,
         "floatfmt": (".0f", ",.0f", ",.0f", ",.0f", ".2f"),
         "caption": "Karawang, three years. The mapped harvested area falls by about 12 % "
                    "in 2023, close to the official fall in production; yield per harvested "
                    "hectare hardly changes. The 2023 loss came from fewer crops, not "
                    "poorer ones."},
        {"kind": "map", "name": "ch45-submerged", "image": submerged(2023).clip(karawang_district),
         "region": karawang_district.bounds(), "vis": {"min": 1, "max": 1, "palette": ["2a78d6"]},
         "classes": [("growing paddy under water, March 2023", "#2a78d6")],
         "title": "Crops under water, March 2023", "source": "Sentinel-1 GRD. GEE.",
         "caption": "Paddy that was growing in February 2023 (VH above -17 dB) and under "
                    "water at some pass in March 2023 (VH below -21 dB)."},
        {"kind": "table", "name": "ch45-submerged-table", "data": submerged_table,
         "floatfmt": (".0f", ",.0f"),
         "caption": "Growing paddy that went under water in March: MORE in 2022 than in "
                    "the 2023 flood year. In Karawang, March is when the first crop is "
                    "harvested and fields are re-flooded for the next, so this test mixes "
                    "normal re-flooding with flood damage. A negative result, kept on "
                    "purpose."},
        {"kind": "table", "name": "ch45-failure", "data": series, "transform": failure_table,
         "floatfmt": ("", ".0f", ".0f", ".0%"),
         "caption": "Karawang sample fields: seasons that ended in a second flooding dip "
                    "within 25-75 days without a clear rise, by quarter."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(yield_frame())
