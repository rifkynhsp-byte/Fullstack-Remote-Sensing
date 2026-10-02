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
# °C, the same for every page. It must cover the hottest district too: the first version used
# 22-42 and Kota Bekasi (90th percentile 44 °C) saturated into one flat red.
VMIN, VMAX = 22, 46

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


def graticule(ax):
    """Grid lines at round degrees, labelled 107.60°E / 6.90°S on the frame."""
    from matplotlib.ticker import FuncFormatter, MaxNLocator

    def deg(v, axis):
        hemi = ("E" if v >= 0 else "W") if axis == "x" else ("N" if v >= 0 else "S")
        return f"{abs(v):.2f}°{hemi}"
    ax.xaxis.set_major_locator(MaxNLocator(5))
    ax.yaxis.set_major_locator(MaxNLocator(5))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: deg(v, "x")))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: deg(v, "y")))
    ax.grid(True, color="#333333", lw=0.3, alpha=0.6, ls="--")
    ax.tick_params(labelsize=7)


def north_arrow(ax, x=0.93, y=0.84, size=0.09):
    """Half black, half white arrow with N above: readable on any background."""
    from matplotlib.patches import Polygon
    t, w = ax.transAxes, size * 0.35
    ax.add_patch(Polygon([[x, y + size], [x - w, y], [x, y + size * 0.25]],
                         transform=t, fc="black", ec="black", lw=0.8, zorder=20))
    ax.add_patch(Polygon([[x, y + size], [x + w, y], [x, y + size * 0.25]],
                         transform=t, fc="white", ec="black", lw=0.8, zorder=20))
    ax.text(x, y + size + 0.015, "N", transform=t, ha="center", fontsize=11,
            fontweight="bold", zorder=20)


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
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    graticule(ax)
    scale_bar(ax, x0, x1, y0, y1)
    north_arrow(ax, x=0.06, y=0.80)          # top left, clear of the inset

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


# PART 4. Colour, ranges and projection: three ways a correct map misleads -----------------------
def lst_array(name, scale=150):
    """The district's LST as a numpy array (NaN outside), for the colour experiments."""
    region = gaul.filter(ee.Filter.eq("GAUL2_NAME", name)).geometry()
    img = landsat_lst(region).unmask(-999).reproject("EPSG:32748", None, scale)
    a = np.array(img.sampleRectangle(region.bounds(), defaultValue=-999).get("lst").getInfo(), float)
    a[a < -100] = np.nan
    xs, ys = zip(*region.bounds().coordinates().getInfo()[0])
    return a, (min(xs), max(xs), min(ys), max(ys))          # array and its lon/lat extent, for the graticule


def lightness(cmap, n=256):
    """CIELAB lightness L* along a colour map: what the map looks like in greyscale or to the eye's brightness channel."""
    from skimage.color import rgb2lab
    rgb = plt.get_cmap(cmap)(np.linspace(0, 1, n))[:, :3] if isinstance(cmap, str) else cmap(np.linspace(0, 1, n))[:, :3]
    return rgb2lab(rgb[None, :, :])[0, :, 0]


def colour_figure():
    """Rainbow against perceptually uniform colour maps, on the same data."""
    ours = LinearSegmentedColormap.from_list("ours", ["#" + c for c in PALETTE])
    a, ext = lst_array("Kota Bandung")
    fig = plt.figure(figsize=(11, 7))
    ax = fig.add_subplot(2, 1, 1)
    for name, cm, col in [("jet (rainbow)", "jet", "#d62728"), ("viridis", "viridis", "#440154"),
                          ("cividis", "cividis", "#00204d"), ("this chapter's diverging palette", ours, "#f46d43")]:
        ax.plot(np.linspace(VMIN, VMAX, 256), lightness(cm), label=name, color=col, lw=2)
    ax.set_xlabel("data value mapped to the colour (°C)"); ax.set_ylabel("lightness L* (0 black, 100 white)")
    ax.legend(frameon=False, fontsize=8, ncol=4, loc="lower center")
    ax.set_title("Lightness along each colour map: a good sequential map climbs steadily; jet rises and falls",
                 loc="left", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    for i, (cm, title) in enumerate([("jet", "jet in colour"), ("viridis", "viridis in colour")]):
        for j, grey in enumerate([False, True]):
            axm = fig.add_subplot(2, 4, 5 + 2 * i + j)
            rgba = plt.get_cmap(cm)(plt.Normalize(VMIN, VMAX)(a))
            if grey:
                from skimage.color import rgb2lab
                lab = rgb2lab(np.nan_to_num(rgba[..., :3]))
                show = np.where(np.isnan(a), np.nan, lab[..., 0])
                axm.imshow(show, cmap="gray", vmin=0, vmax=100, extent=ext)
                axm.set_title(f"{cm} printed in grey", fontsize=8)
            else:
                rgba[np.isnan(a)] = (1, 1, 1, 0)
                axm.imshow(rgba, extent=ext)
                axm.set_title(title, fontsize=8)
            graticule(axm); axm.tick_params(labelsize=6)
    fig.suptitle(f"Kota Bandung LST, {VMIN}-{VMAX} °C: in grey, jet's hottest and coolest pixels look alike; viridis keeps its order",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


def range_trap_figure():
    """Two districts, drawn with their own colour ranges and with one shared range."""
    cmap = LinearSegmentedColormap.from_list("lst", ["#" + c for c in PALETTE])
    got = {n: lst_array(n, 200) for n in ["Kota Bekasi", "Garut"]}      # 200 m keeps Garut under the sample limit
    arrs = {n: v[0] for n, v in got.items()}
    fig, axes = plt.subplots(2, 2, figsize=(10, 8.5))
    for j, (n, a) in enumerate(arrs.items()):
        for i, (lo, hi, row) in enumerate([(np.nanpercentile(a, 2), np.nanpercentile(a, 98), "own range"),
                                           (VMIN, VMAX, "shared range")]):
            ax = axes[i, j]
            im = ax.imshow(a, cmap=cmap, vmin=lo, vmax=hi, extent=got[n][1])
            fig.colorbar(im, ax=ax, shrink=0.7, label="°C")
            ax.set_title(f"{n}, {row} ({lo:.0f}-{hi:.0f} °C); median {np.nanmedian(a):.1f} °C", fontsize=9)
            graticule(ax)
    med = {n: np.nanmedian(a) for n, a in arrs.items()}
    fig.suptitle(f"Top: each district red at its own hottest, so both look equally hot. Bottom: one range shows "
                 f"Bekasi's median is {med['Kota Bekasi'] - med['Garut']:.1f} °C hotter",
                 x=0.01, ha="left", fontweight="bold", fontsize=10)
    fig.tight_layout()
    return fig


def mercator_table():
    """Web Mercator, the projection of every web map, stretches lengths by 1/cos(latitude) and areas by its square."""
    import pandas as pd
    places = [("Banda Aceh", 5.55), ("Jakarta", -6.21), ("Kupang", -10.18), ("Sydney", -33.87),
              ("Hobart", -42.88), ("Oslo", 59.91)]
    rows = [{"place": n, "latitude": la, "length scale factor": 1 / math.cos(math.radians(la)),
             "area scale factor": 1 / math.cos(math.radians(la)) ** 2} for n, la in places]
    return pd.DataFrame(rows)


def products():
    return [
        {"kind": "figure", "name": "ch28-map-page", "figure": first_page,
         "caption": "Page 1 of the automated report: layout, locator inset, legend with "
                    "units, scale bar, north arrow, summary and data credit, all from code. "
                    "[Download the full PDF report](images/real/ch28-district-report.pdf)."},
        {"kind": "table", "name": "ch28-report-table", "data": table,
         "columns": ["district", "p10_C", "median_C", "p90_C"], "floatfmt": ("", ".1f", ".1f", ".1f"),
         "caption": "The numbers printed on each page, for all three districts."},
        {"kind": "figure", "name": "ch28-colour", "figure": colour_figure,
         "caption": "Lightness (CIELAB L*) along four colour maps, and the same LST map in colour and printed in grey."},
        {"kind": "figure", "name": "ch28-range-trap", "figure": range_trap_figure,
         "caption": "The same two districts with their own colour ranges (top) and one shared range (bottom)."},
        {"kind": "table", "name": "ch28-mercator", "data": mercator_table, "floatfmt": ("", ".2f", ".3f", ".3f"),
         "caption": "How much Web Mercator enlarges lengths and areas at six latitudes."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    build_report()
    print("wrote", REPORT_PATH)
