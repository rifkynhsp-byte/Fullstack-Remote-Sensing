#| title: The four resolutions (Python)
#| description: Spatial, spectral, radiometric and temporal resolution, each shown with real data: one harbour at 250, 30 and 10 m; Landsat 7 and 8 band widths; a Sentinel-2 patch at 1 to 12 bits; and forty years of acquisitions over one city.

"""
PRINCIPLES P4 | Four resolutions and one coverage.

    spatial      how small a thing you can see          pixel size (GSD)
    spectral     how finely you split the spectrum      number and width of bands
    radiometric  how finely you split brightness        bits: 2^n levels
    temporal     how often you look                      revisit time
    (coverage    how much you see at once                swath)

No sensor is best at all five: they compete for the same light, the same
data volume and the same budget.
"""

import io

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from PIL import Image

port = ee.Geometry.Rectangle([110.36, -6.99, 110.46, -6.92], None, False)   # Semarang harbour


def thumb(img, vis, region, dim=500):
    url = img.visualize(**vis).getThumbURL({"region": region, "dimensions": dim,
                                            "format": "png"})
    return np.array(Image.open(io.BytesIO(requests.get(url, timeout=300).content)))


# ---------------------------------------------------------------------------
# 1. Spatial: the same harbour at three pixel sizes
# ---------------------------------------------------------------------------
def spatial_figure():
    date = ("2023-06-01", "2023-10-01")
    modis = (ee.ImageCollection("MODIS/061/MOD09GQ").filterDate(*date).median()
             .select(["sur_refl_b02", "sur_refl_b01", "sur_refl_b01"], ["nir", "red", "red2"]))
    l8 = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterBounds(port).filterDate(*date)
          .sort("CLOUD_COVER").first().select(["SR_B5", "SR_B4", "SR_B3"]))
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(port)
          .filterDate(*date).sort("CLOUDY_PIXEL_PERCENTAGE").first()
          .select(["B8", "B4", "B3"]))
    panels = [("MODIS, 250 m", modis.reproject("EPSG:32749", None, 250),
               {"min": 0, "max": 4000}),
              ("Landsat 8, 30 m", l8.reproject("EPSG:32749", None, 30),
               {"min": 7500, "max": 25000}),
              ("Sentinel-2, 10 m", s2, {"min": 0, "max": 4000})]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    for ax, (title, img, vis) in zip(axes, panels):
        ax.imshow(thumb(img, vis, port))
        ax.set_title(title, loc="left", fontsize=10)
        ax.set_axis_off()
    fig.suptitle("Semarang harbour, 2023, false colour (NIR, red, green): about 11 × 8 km",
                 x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 2. Spectral: where the bands sit, and how wide they are
# ---------------------------------------------------------------------------
BANDS = {   # published band limits, µm (USGS, ESA)
    "Landsat 7 ETM+": [("1", .45, .52), ("2", .52, .60), ("3", .63, .69), ("4", .77, .90),
                       ("5", 1.55, 1.75), ("7", 2.09, 2.35)],
    "Landsat 8 OLI": [("1", .43, .45), ("2", .45, .51), ("3", .53, .59), ("4", .64, .67),
                      ("5", .85, .88), ("9", 1.36, 1.38), ("6", 1.57, 1.65),
                      ("7", 2.11, 2.29)],
    "Sentinel-2 MSI": [("2", .458, .523), ("3", .543, .578), ("4", .650, .680),
                       ("5", .698, .713), ("6", .733, .748), ("7", .773, .793),
                       ("8", .785, .900), ("8A", .855, .875), ("11", 1.565, 1.655),
                       ("12", 2.100, 2.280)],
}


def spectral_figure():
    fig, ax = plt.subplots(figsize=(10, 3.4))
    cols = {"Landsat 7 ETM+": "#8e44ad", "Landsat 8 OLI": "#c0392b",
            "Sentinel-2 MSI": "#1b7837"}
    for k, (sensor, bands) in enumerate(BANDS.items()):
        y = 2 - k
        for name, lo, hi in bands:
            ax.add_patch(plt.Rectangle((lo, y - 0.3), hi - lo, 0.6, color=cols[sensor],
                                       alpha=0.75))
            ax.text((lo + hi) / 2, y + 0.38, name, ha="center", fontsize=7)
    ax.set_yticks([2, 1, 0], list(BANDS))
    ax.set_xlim(0.40, 2.40); ax.set_ylim(-0.6, 2.7)
    ax.set_xlabel("Wavelength (µm)")
    ax.annotate("ETM+ band 5: 200 nm wide", (1.65, 2.3), xytext=(1.0, 2.55),
                fontsize=8, arrowprops={"arrowstyle": "->", "lw": 0.8})
    ax.annotate("OLI band 6: 80 nm", (1.61, 0.7), xytext=(1.9, 1.35), fontsize=8,
                arrowprops={"arrowstyle": "->", "lw": 0.8})
    ax.set_title("Newer sensors split the spectrum into more, narrower bands",
                 loc="left", fontsize=10)
    return fig


# ---------------------------------------------------------------------------
# 3. Radiometric: the same patch at 1, 2, 4, 8 and 12 bits
# ---------------------------------------------------------------------------
def radiometric_figure():
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(port)
          .filterDate("2023-06-01", "2023-10-01").sort("CLOUDY_PIXEL_PERCENTAGE").first()
          .select("B8"))
    arr = ee.data.computePixels({
        "expression": s2.clip(port).unmask(0),
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {"dimensions": {"width": 400, "height": 280},
                 "affineTransform": {"scaleX": 0.1 / 400, "shearX": 0, "translateX": 110.36,
                                     "shearY": 0, "scaleY": -0.07 / 280, "translateY": -6.92},
                 "crsCode": "EPSG:4326"}})["B8"].astype(float)
    x = np.clip(arr / 5000, 0, 1)                     # reflectance 0 to 0.5, scaled 0..1
    fig, axes = plt.subplots(1, 5, figsize=(13, 2.9))
    for ax, bits in zip(axes, [1, 2, 4, 8, 12]):
        levels = 2 ** bits
        q = np.floor(x * (levels - 1) + 0.5) / (levels - 1)
        ax.imshow(q, cmap="gray", vmin=0, vmax=1)
        ax.set_title(f"{bits} bit: {levels:,} levels", loc="left", fontsize=9)
        ax.set_axis_off()
    fig.suptitle("Sentinel-2 NIR, Semarang harbour, quantised to fewer and fewer grey levels",
                 x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    return fig


def radiometric_table():
    rows = [("Landsat 1-3 MSS", 6), ("Landsat 4-5 TM", 8), ("Landsat 7 ETM+", 8),
            ("Landsat 8 OLI", 12), ("Landsat 9 OLI-2", 14), ("Sentinel-2 MSI", 12),
            ("MODIS", 12)]
    return pd.DataFrame([{"sensor": s, "bits": b, "grey_levels": 2 ** b} for s, b in rows])


# ---------------------------------------------------------------------------
# 4. Temporal: forty years of acquisitions over Bandung
# ---------------------------------------------------------------------------
bandung = ee.Geometry.Point(107.61, -6.91)


def acquisitions_frame():
    cols = {"Landsat 5": "LANDSAT/LT05/C02/T1_L2", "Landsat 7": "LANDSAT/LE07/C02/T1_L2",
            "Landsat 8": "LANDSAT/LC08/C02/T1_L2", "Landsat 9": "LANDSAT/LC09/C02/T1_L2",
            "Sentinel-2": "COPERNICUS/S2_HARMONIZED"}
    rows = []
    for name, cid in cols.items():
        c = ee.ImageCollection(cid).filterBounds(bandung).filterDate("1984-01-01",
                                                                     "2025-01-01")
        years = c.aggregate_array("system:time_start").getInfo()
        for t in years:
            rows.append({"sensor": name, "year": pd.Timestamp(t, unit="ms").year})
    df = pd.DataFrame(rows).groupby(["year", "sensor"]).size().unstack(fill_value=0)
    return df.reset_index()


def plot_acquisitions(df):
    d = df.set_index("year")
    order = ["Landsat 5", "Landsat 7", "Landsat 8", "Landsat 9", "Sentinel-2"]
    cols = ["#9aa5b1", "#8e44ad", "#c0392b", "#e67e22", "#1b7837"]
    fig, ax = plt.subplots(figsize=(10, 3.6))
    bottom = np.zeros(len(d))
    for s, c in zip(order, cols):
        if s in d:
            ax.bar(d.index, d[s], bottom=bottom, color=c, label=s, width=0.85)
            bottom += d[s].to_numpy()
    ax.set_ylabel("Images covering Bandung")
    ax.set_title("From 7 images in 1988 to 137 in 2023: temporal resolution improved "
                 "the most", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8, ncol=5, loc="upper left")
    return fig


def tradeoff_figure():
    s = [("WorldView-3", 0.31, 13.1), ("SPOT 6/7", 1.5, 60), ("Sentinel-2", 10, 290),
         ("Landsat 8/9", 30, 185), ("MODIS", 250, 2330), ("Himawari AHI", 500, 12000)]
    fig, ax = plt.subplots(figsize=(6.8, 3.8))
    for name, gsd, sw in s:
        ax.loglog(gsd, sw, "o", color="#2a78d6", ms=6)
        ax.annotate(name, (gsd, sw), xytext=(6, -3), textcoords="offset points", fontsize=8)
    ax.set_xlabel("Best pixel size (m)"); ax.set_ylabel("Swath or disk width (km)")
    ax.set_xlim(0.1, 3000); ax.set_ylim(5, 40000)
    ax.set_title("Sharper pixels, narrower views", loc="left", fontsize=10)
    ax.text(0.99, -0.2, "Nominal published values. Himawari: full-disk view from GEO; "
            "500 m is its sharpest visible band.", transform=ax.transAxes, ha="right",
            fontsize=7, color="#6b7680")
    return fig


def products():
    return [
        {"kind": "figure", "name": "p4-spatial", "figure": spatial_figure,
         "caption": "Spatial resolution. The same harbour from MODIS (250 m), Landsat 8 "
                    "(30 m) and Sentinel-2 (10 m). Piers, ships and streets appear only when "
                    "the pixel is smaller than they are."},
        {"kind": "figure", "name": "p4-spectral", "figure": spectral_figure,
         "caption": "Spectral resolution. Band positions and widths from the published "
                    "specifications. Landsat 8 narrowed its NIR band to avoid a water-vapour "
                    "absorption near 0.825 µm, and added a coastal band (1) and a cirrus "
                    "band (9)."},
        {"kind": "figure", "name": "p4-radiometric", "figure": radiometric_figure,
         "caption": "Radiometric resolution. The same real Sentinel-2 near-infrared patch "
                    "stored with 2, 4, 16, 256 and 4,096 grey levels. With few levels, "
                    "water, land and everything between merge into flat blocks. 8 and 12 "
                    "bits look the same on screen, because screens and eyes stop near 256 "
                    "levels; the extra levels matter for analysis, above all in dark "
                    "targets such as water."},
        {"kind": "table", "name": "p4-bits", "data": radiometric_table,
         "floatfmt": ("", ".0f", ",.0f"),
         "caption": "Bits per pixel and the number of grey levels they allow, 2ⁿ."},
        {"kind": "chart", "name": "p4-temporal", "data": acquisitions_frame,
         "plot": plot_acquisitions,
         "caption": "Temporal resolution. Every Landsat and Sentinel-2 image in the archive "
                    "that covers central Bandung, per year (all cloud conditions)."},
        {"kind": "figure", "name": "p4-tradeoff", "figure": tradeoff_figure,
         "caption": "Coverage against spatial resolution for six sensors: no sensor is "
                    "both sharp and wide."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(acquisitions_frame().tail())
