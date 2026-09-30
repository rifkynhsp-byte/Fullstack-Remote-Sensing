#| title: Print-ready maps and an automated report (Python)
#| description: A map layout built in code, repeated for every district, bound into one PDF report.

"""
CHAPTER 28 | From an Earth Engine image to a map a client can print, then to
a report that builds itself.

The layout below has what a finished map needs: a title that says what and
when, a legend with units, a scale bar, a north arrow, a locator inset,
coordinates on the frame, and a data credit. Write it once as a function,
then call it for every district. The last step binds the pages into one PDF,
the way the author's monitoring pipelines deliver reports to clients.
"""

import io
import math

import ee
import matplotlib.pyplot as plt
import numpy as np
import requests
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image

DISTRICTS = ["Kota Bandung", "Kota Bekasi", "Garut"]
PALETTE = ["313695", "74add1", "ffffbf", "f46d43", "a50026"]
VMIN, VMAX = 22, 42                      # °C, the same for every page

gaul = ee.FeatureCollection("FAO/GAUL/2025/level2")
java = gaul.filter(ee.Filter.eq("GAUL1_NAME", "Jawa Barat"))


def landsat_lst(region):
    """Dry-season 2024 median land surface temperature, °C, clouds masked."""
    def to_lst(img):
        qa = img.select("QA_PIXEL")
        clear = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        return (img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15)
                .rename("lst").updateMask(clear))
    return (ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
            .merge(ee.ImageCollection("LANDSAT/LC08/C02/T1_L2"))
            .filterBounds(region).filterDate("2024-06-01", "2024-10-31")
            .map(to_lst).median().clip(region))


def fetch(image, region, vis, width=1200):
    """Earth Engine renders; Python receives a picture and its bounds."""
    url = image.visualize(**vis).getThumbURL({"region": region, "dimensions": width,
                                              "format": "png"})
    img = Image.open(io.BytesIO(requests.get(url, timeout=300).content))
    xs, ys = zip(*region.bounds().coordinates().getInfo()[0])
    return img, (min(xs), max(xs), min(ys), max(ys))


def scale_bar(ax, x0, x1, y0, y1):
    km_per_deg = 111.32 * math.cos(math.radians((y0 + y1) / 2))
    target = (x1 - x0) * km_per_deg / 5
    step = max(m * 10 ** math.floor(math.log10(target)) for m in (1, 2, 5)
               if m * 10 ** math.floor(math.log10(target)) <= target)
    px, py = x0 + (x1 - x0) * 0.05, y0 + (y1 - y0) * 0.05
    for i in range(2):                       # alternating black and white halves
        ax.add_patch(plt.Rectangle((px + i * step / 2 / km_per_deg, py),
                                   step / 2 / km_per_deg, (y1 - y0) * 0.012,
                                   fc="black" if i == 0 else "white", ec="black", lw=0.6))
    ax.text(px, py + (y1 - y0) * 0.02, "0", fontsize=7, ha="center")
    ax.text(px + step / km_per_deg, py + (y1 - y0) * 0.02, f"{step:g} km", fontsize=7,
            ha="center")


def map_page(name):
    """One finished map: layout, inset, legend, stats. Returns the figure."""
    district = gaul.filter(ee.Filter.eq("GAUL2_NAME", name))
    region = district.geometry()
    lst = landsat_lst(region)
    img, (x0, x1, y0, y1) = fetch(lst, region.bounds(),
                                  {"min": VMIN, "max": VMAX, "palette": PALETTE})
    outline, _ = fetch(ee.Image().byte().paint(district, 1, 2), region.bounds(),
                       {"palette": ["000000"]})
    stats = lst.reduceRegion(ee.Reducer.percentile([10, 50, 90]), region, 30,
                             maxPixels=1e10, bestEffort=True).getInfo()

    fig = plt.figure(figsize=(8.27, 11.69))            # A4 portrait
    ax = fig.add_axes([0.08, 0.30, 0.84, 0.60])
    ax.imshow(img, extent=[x0, x1, y0, y1])
    ax.imshow(outline, extent=[x0, x1, y0, y1])
    ax.set_xlabel("Longitude (°E)", fontsize=8)
    ax.set_ylabel("Latitude (°)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.ticklabel_format(useOffset=False, style="plain")
    scale_bar(ax, x0, x1, y0, y1)
    ax.annotate("N", xy=(0.95, 0.95), xytext=(0.95, 0.86), xycoords="axes fraction",
                ha="center", fontweight="bold", arrowprops=dict(arrowstyle="-|>", color="k"))

    # Locator inset: where is this district in West Java?
    inset = fig.add_axes([0.70, 0.705, 0.20, 0.17])
    wj, (a0, a1, b0, b1) = fetch(ee.Image().byte().paint(java, 1).paint(java, 2, 1)
                                 .paint(district, 3), java.geometry().bounds(),
                                 {"min": 1, "max": 3, "palette": ["dddddd", "888888",
                                                                  "e31a1c"]}, 400)
    inset.imshow(wj, extent=[a0, a1, b0, b1])
    inset.set_xticks([]), inset.set_yticks([])
    inset.set_title("West Java", fontsize=7)

    cmap = LinearSegmentedColormap.from_list("lst", ["#" + c for c in PALETTE])
    cax = fig.add_axes([0.25, 0.255, 0.5, 0.012])
    cb = fig.colorbar(plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(VMIN, VMAX)),
                      cax=cax, orientation="horizontal")
    cb.set_label("Land surface temperature (°C), median June to October 2024", fontsize=8)

    fig.text(0.08, 0.955, f"{name}: how hot is the ground?", fontsize=16, weight="bold")
    fig.text(0.08, 0.935, "Landsat 8 and 9 surface temperature, dry season 2024",
             fontsize=10, color="#444444")
    fig.text(0.08, 0.20, "Summary", fontsize=11, weight="bold")
    fig.text(0.08, 0.17, f"10 % of the district is cooler than {stats['lst_p10']:.1f} °C; "
             f"half is below {stats['lst_p50']:.1f} °C; the hottest 10 % is above "
             f"{stats['lst_p90']:.1f} °C.", fontsize=9, wrap=True)
    fig.text(0.08, 0.04, "Data: USGS Landsat Collection 2 Level 2, FAO GAUL 2025. "
             "Processed in Google Earth Engine. Map generated automatically.",
             fontsize=7, color="#616e7c")
    return fig, {"district": name, **stats}


def build_report():
    """Every district, one page each, one PDF. Returns the rows for the table."""
    rows, first = [], None
    with PdfPages(REPORT_PATH) as pdf:
        for name in DISTRICTS:
            fig, row = map_page(name)
            pdf.savefig(fig)
            if first is None:
                first = fig
            else:
                plt.close(fig)
            rows.append(row)
    import pandas as pd
    _state.update(first=first, rows=pd.DataFrame(rows))
    return first


_state = {}
REPORT_PATH = "images/real/ch28-district-report.pdf"


def first_page():
    return _state.get("first") or build_report()


def table():
    if "rows" not in _state:
        build_report()
    return _state["rows"].rename(columns={"lst_p10": "p10_C", "lst_p50": "median_C",
                                          "lst_p90": "p90_C"})


def products():
    return [
        {"kind": "figure", "name": "ch28-map-page", "figure": first_page,
         "caption": "Page 1 of the automated report: layout, locator inset, legend with "
                    "units, scale bar, north arrow, summary and data credit, all from code. "
                    "[Download the full PDF report](images/real/ch28-district-report.pdf)."},
        {"kind": "table", "name": "ch28-report-table", "data": table,
         "columns": ["district", "p10_C", "median_C", "p90_C"], "floatfmt": ("", ".1f", ".1f", ".1f"),
         "caption": "The numbers printed on each page, for all three districts."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    build_report()
    print("wrote", REPORT_PATH)
