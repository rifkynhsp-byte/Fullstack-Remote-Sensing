#| title: Counting oil palms without deep learning (Python)
#| description: Excess-green index, a Gaussian blur and local maxima on a drone orthophoto of smallholder oil palm in South Kalimantan.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 27 | One point per crown, from a drone orthophoto.

The author's GEE method (sawitML, GEE101 PalmOil_Detection): blur a
vegetation index, find the crown centres, count them. No neural network:
mature oil palm is planted on a regular grid and each crown is a bright,
round, well separated blob, which is exactly what a local-maximum filter
finds.

Image: OpenAerialMap, "53672_33413kebun_sawit_bangkal_baru", 3.7 cm drone
orthophoto near Banjarbaru, South Kalimantan, CC BY 4.0. Read straight from
the cloud-optimised GeoTIFF at 0.3 m, the resolution the original method used.

    pip install rasterio scikit-image scipy matplotlib pandas
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.feature import peak_local_max

# OpenAerialMap orthophoto (CC BY 4.0), originally at oin-hotosm-temp.s3.us-east-1.amazonaws.com/
# 6a13018bb96dbc8d970d888e/0/6a13018bb96dbc8d970d888f.tif. That bucket is temporary, so the book
# keeps an identical copy with its data snapshots; it is read in place, by HTTP range requests.
URL = "https://github.com/rifkynhsp-byte/Fullstack-Remote-Sensing/releases/download/data-v1/ch27_ch61_drone_orthophoto.tif"
OVERVIEW = 8          # 3.7 cm x 8 = 0.30 m
MIN_SPACING_M = 5.5   # two crowns closer than this are one palm
SIGMA_M = 0.9         # blur about a third of a crown radius

_cache = {}


def load():
    """RGB at 0.3 m, straight from the cloud; no download of the full 1 GB."""
    if "rgb" not in _cache:
        with rasterio.open("/vsicurl/" + URL) as src:
            h, w = src.height // OVERVIEW, src.width // OVERVIEW
            rgb = src.read(out_shape=(3, h, w), resampling=Resampling.average).astype(float)
            res = src.res[0] * OVERVIEW
        _cache.update(rgb=rgb, res=res)
    return _cache["rgb"], _cache["res"]


def count_palms():
    """Excess green, blur, local maxima: one point per crown."""
    if "peaks" in _cache:
        return _cache["peaks"]
    rgb, res = load()
    r, g, b = rgb
    exg = (2 * g - r - b) / np.maximum(r + g + b, 1)          # excess green index
    smooth = ndi.gaussian_filter(exg, SIGMA_M / res)
    valid = (rgb.sum(0) > 0).astype(int)                      # skip the no-data frame
    peaks = peak_local_max(smooth, min_distance=int(MIN_SPACING_M / res),
                           threshold_abs=0.04, labels=valid)
    _cache["peaks"] = peaks
    return peaks


def spacing_frame():
    """Distance from every counted palm to its nearest neighbour, in metres."""
    peaks = count_palms()
    _, res = load()
    d, _ = cKDTree(peaks * res).query(peaks * res, k=2)
    return pd.DataFrame({"nearest_m": d[:, 1]})


def density_frame():
    """Palms per hectare in a 50 m grid, which is what an estate manager asks for."""
    rgb, res = load()
    peaks = count_palms()
    cell = int(50 / res)
    rows, cols = rgb.shape[1] // cell, rgb.shape[2] // cell
    grid = np.zeros((rows, cols))
    for y, x in peaks:
        if y // cell < rows and x // cell < cols:
            grid[y // cell, x // cell] += 1
    return grid * 4          # 50 m cell = 0.25 ha


def lonlat_extent():
    """The orthophoto's extent in degrees, for a graticule on the image maps."""
    if "ext" not in _cache:
        from rasterio.warp import transform_bounds
        with rasterio.open("/vsicurl/" + URL) as src:
            w, s_, e, n = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        _cache["ext"] = [w, e, s_, n]
    return _cache["ext"]


def graticule(ax):
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    ax.xaxis.set_major_locator(MaxNLocator(3)); ax.yaxis.set_major_locator(MaxNLocator(3))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{abs(v):.3f}°E"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{abs(v):.3f}°S"))
    ax.grid(True, color="#ffffff", lw=0.4, ls="--", alpha=0.7); ax.tick_params(labelsize=7)


def figure_crowns():
    """The orthophoto with every counted crown, and a zoom on one corner."""
    rgb, res = load()
    peaks = count_palms()
    img = np.clip(np.moveaxis(rgb, 0, -1) / 255, 0, 1)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.6), gridspec_kw={"width_ratios": [1.2, 1]})
    w, e, s_, n = lonlat_extent()
    h, wd = img.shape[:2]
    lon = w + (peaks[:, 1] + 0.5) / wd * (e - w)
    lat = n - (peaks[:, 0] + 0.5) / h * (n - s_)
    axes[0].imshow(img, extent=[w, e, s_, n])
    axes[0].plot(lon, lat, ".", color="#ff2d55", ms=1.6)
    axes[0].set_title(f"{len(peaks):,} crowns counted", loc="left", fontsize=10)
    zy, zx, zs = int(0.55 * img.shape[0]), int(0.05 * img.shape[1]), int(120 / res)
    dx, dy = (e - w) / wd, (n - s_) / h
    axes[0].add_patch(plt.Rectangle((w + zx * dx, n - (zy + zs) * dy), zs * dx, zs * dy, fill=False, ec="yellow", lw=1.5))
    graticule(axes[0])
    axes[1].imshow(img[zy:zy + zs, zx:zx + zs])
    sel = ((peaks[:, 0] >= zy) & (peaks[:, 0] < zy + zs) &
           (peaks[:, 1] >= zx) & (peaks[:, 1] < zx + zs))
    axes[1].plot(peaks[sel, 1] - zx, peaks[sel, 0] - zy, "o", mfc="none", mec="#ff2d55",
                 ms=9, mew=1.2)
    axes[1].set_title("Zoom, 120 m across", loc="left", fontsize=10)
    axes[1].set_axis_off()            # a 120 m zoom; its position is the yellow box on the left map
    fig.text(0.01, 0.01, "Imagery: OpenAerialMap contributors, CC BY 4.0", fontsize=7,
             color="#616e7c")
    fig.tight_layout()
    return fig


def figure_density():
    """Palms per hectare, 50 m cells."""
    grid = density_frame()
    fig, ax = plt.subplots(figsize=(6, 5.2))
    w, e, s_, n = lonlat_extent()
    rgb, res = load()
    cell = int(50 / res)
    ext = [w, w + grid.shape[1] * cell / rgb.shape[2] * (e - w), n - grid.shape[0] * cell / rgb.shape[1] * (n - s_), n]
    im = ax.imshow(np.ma.masked_equal(grid, 0), cmap="YlGn", vmin=0, vmax=180, extent=ext)
    fig.colorbar(im, ax=ax, label="Palms per hectare (50 m cells)", shrink=0.8)
    ax.set_title("Planting density", loc="left", fontsize=10)
    graticule(ax); ax.grid(True, color="#333333", lw=0.3, ls="--")
    return fig


def plot_spacing(df):
    """Nearest-neighbour distance. A planted grid shows one sharp peak."""
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    ax.hist(df["nearest_m"].clip(0, 16), bins=np.arange(4, 16.5, 0.5), color="#1b7837")
    ax.axvline(9, color="#b2182b", ls="--", lw=1)
    ax.text(9.1, ax.get_ylim()[1] * 0.9, "9 m, a common planting distance", fontsize=7,
            color="#b2182b")
    ax.set_xlabel("Distance to the nearest counted palm (m)")
    ax.set_ylabel("Palms")
    ax.set_title("Does the count look like a plantation?", loc="left")
    return fig


def summary_frame():
    peaks = count_palms()
    rgb, res = load()
    sp = spacing_frame()["nearest_m"]
    grid = density_frame()
    area_ha = (rgb.sum(0) > 0).sum() * res * res / 1e4
    return pd.DataFrame([{
        "palms_counted": len(peaks), "image_area_ha": area_ha,
        "median_spacing_m": sp.median(),
        "share_spacing_7_to_11_m": ((sp >= 7) & (sp <= 11)).mean(),
        "median_density_per_ha_in_planted_cells": np.median(grid[grid > 60]),
    }])


# ---------------------------------------------------------------------------
# From drone to satellite: does a 10 m palm map see the same block?
# ---------------------------------------------------------------------------
PALMS_PER_HA = 10000 / (9 * 9 * np.sin(np.radians(60)))      # 9 m triangular planting: about 143 palms/ha


def cells_frame():
    """Drone palms/ha and the Forest Data Partnership oil palm probability in every 50 m cell."""
    if "cells" in _cache:
        return _cache["cells"]
    import ee
    grid = density_frame()
    with rasterio.open("/vsicurl/" + URL) as src:
        left, top = src.bounds.left, src.bounds.top
    _, res = load()
    cell_m = int(50 / res) * res                                # the exact cell size used by density_frame
    feats = []
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            x0, y1 = left + j * cell_m, top - i * cell_m
            g = ee.Geometry.Rectangle([x0, y1 - cell_m, x0 + cell_m, y1], "EPSG:3857", False)
            feats.append(ee.Feature(g, {"row": i, "col": j, "drone_per_ha": float(grid[i, j])}))
    fdp = lambda y: (ee.ImageCollection("projects/forestdatapartnership/assets/palm/model_2026a")
                     .filterDate(f"{y}-01-01", f"{y + 1}-01-01").mosaic().select("probability").rename(f"p{y}"))
    img = fdp(2020).addBands(fdp(2024))
    out = img.reduceRegions(ee.FeatureCollection(feats), ee.Reducer.mean(), 10).getInfo()["features"]
    d = pd.DataFrame([f["properties"] for f in out])
    _cache["cells"] = d
    return d


def crosscheck_table():
    d = cells_frame()
    from scipy import stats
    planted = d.drone_per_ha > 60                              # the drone's own "planted" rule, as in the summary
    sat = d.p2024 > 0.5
    rows = [
        ("50 m cells in the image", len(d)),
        ("cells the drone calls planted (> 60 palms/ha)", int(planted.sum())),
        ("cells the satellite calls oil palm (p > 0.5, 2024)", int(sat.sum())),
        ("both agree: planted", int((planted & sat).sum())),
        ("both agree: not planted", int((~planted & ~sat).sum())),
        ("Spearman r, drone palms/ha vs satellite probability", stats.spearmanr(d.drone_per_ha, d.p2024)[0]),
        ("satellite palm area (ha)", sat.sum() * 0.25),
        (f"palms expected at {PALMS_PER_HA:.0f}/ha on that area", sat.sum() * 0.25 * PALMS_PER_HA),
        ("drone count: all detections", len(count_palms())),
        ("drone count: inside satellite palm cells", int(d.loc[sat, "drone_per_ha"].sum() * 0.25)),
    ]
    out = pd.DataFrame(rows, columns=["measure", "value"])
    out["shown"] = [f"{v:.2f}" if isinstance(v, float) and v < 1 else f"{v:,.0f}" for v in out.value]
    return out


def plot_crosscheck(t):
    d = cells_frame()
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(11, 3.8))
    shape = (d.row.max() + 1, d.col.max() + 1)
    m1 = np.full(shape, np.nan); m2 = np.full(shape, np.nan)
    m1[d.row, d.col] = d.drone_per_ha; m2[d.row, d.col] = d.p2024
    from rasterio.warp import transform_bounds
    with rasterio.open("/vsicurl/" + URL) as src:
        w, so, e, n = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
    _, res = load()
    cell_deg = (e - w) * (int(50 / res) * res) / ((src.bounds.right - src.bounds.left))
    ext = [w, w + shape[1] * cell_deg, n - shape[0] * cell_deg, n]          # the 50 m grid's own extent
    im1 = a1.imshow(m1, cmap="YlGn", vmin=0, vmax=200, extent=ext); fig.colorbar(im1, ax=a1, shrink=0.75, label="palms/ha")
    a1.set_title("Drone: palms per hectare", loc="left", fontsize=9)
    im2 = a2.imshow(m2, cmap="YlOrBr", vmin=0, vmax=1, extent=ext); fig.colorbar(im2, ax=a2, shrink=0.75, label="probability")
    a2.set_title("Satellite: oil palm probability 2024", loc="left", fontsize=9)
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    for a in (a1, a2):                                                       # graticule: every map gets coordinates
        a.xaxis.set_major_locator(MaxNLocator(3)); a.yaxis.set_major_locator(MaxNLocator(3))
        a.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{abs(v):.3f}°E"))
        a.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{abs(v):.3f}°S"))
        a.grid(True, color="#333333", lw=0.3, ls="--", alpha=0.6); a.tick_params(labelsize=7)
    a3.scatter(d.p2024, d.drone_per_ha, s=14, color="#2a78d6", alpha=0.7)
    a3.axhline(60, color="grey", ls=":"); a3.axvline(0.5, color="grey", ls=":")
    a3.set_xlabel("satellite probability"); a3.set_ylabel("drone palms/ha")
    a3.spines[["top", "right"]].set_visible(False)
    tt = t.set_index("measure").value
    a3.set_title(f"Spearman r = {tt.iloc[5]:.2f}", loc="left", fontsize=9)
    agree = (tt.iloc[3] + tt.iloc[4]) / tt.iloc[0]
    fig.suptitle(f"Drone and 10 m satellite map agree on {agree:.0%} of the 50 m cells", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Sensitivity: which settings count palms, and which count other trees too?
# ---------------------------------------------------------------------------
def smooth_exg():
    if "smooth" not in _cache:
        rgb, res = load()
        r, g, b = rgb
        exg = (2 * g - r - b) / np.maximum(r + g + b, 1)
        _cache["smooth"] = ndi.gaussian_filter(exg, SIGMA_M / res)
        _cache["valid"] = (rgb.sum(0) > 0).astype(int)
    return _cache["smooth"], _cache["valid"]


def detect(threshold, spacing_m):
    sm, valid = smooth_exg()
    _, res = load()
    return peak_local_max(sm, min_distance=int(spacing_m / res), threshold_abs=threshold, labels=valid)


def on_grid(peaks):
    """True for detections with at least 3 neighbours 7-11 m away, as on a planting grid."""
    _, res = load()
    xy = peaks * res
    tree = cKDTree(xy)
    n_in = np.array([len(tree.query_ball_point(p, 11)) for p in xy])
    n_close = np.array([len(tree.query_ball_point(p, 7)) for p in xy])
    return (n_in - n_close) >= 3


THRESHOLDS = (0.04, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55)     # 0.04 is the default above; crown peaks start near 0.30
SPACINGS = (4.0, 5.0, 5.5, 6.0, 7.0)


def sensitivity_frame():
    """Every combination of greenness threshold and minimum spacing, scored with two independent proxies.

    No field count exists, so 'truth' is replaced by what two other sources agree on:
      * not palm: detections in 50 m cells the satellite palm model scores below 0.2
        (the drone confirms most of these cells are unplanted);
      * palm-like: detections in cells the satellite scores above 0.5 that also
        sit on a planting grid (>= 3 neighbours 7-11 m away).
    """
    if "sens" in _cache:
        return _cache["sens"]
    d = cells_frame()
    _, res = load()
    cell = int(50 / res)
    p = np.full((d.row.max() + 1, d.col.max() + 1), np.nan)
    p[d.row, d.col] = d.p2024
    rows = []
    for sp in SPACINGS:
        for th in THRESHOLDS:
            pk = detect(th, sp)
            r, c = pk[:, 0] // cell, pk[:, 1] // cell
            ok = (r < p.shape[0]) & (c < p.shape[1])
            prob = np.full(len(pk), np.nan); prob[ok] = p[r[ok], c[ok]]
            grid = on_grid(pk)
            near, _ = cKDTree(pk * res).query(pk * res, k=2)
            palm_like = int(((prob > 0.5) & grid).sum())
            not_palm = int((prob < 0.2).sum())
            rows.append({"min spacing (m)": sp, "ExG threshold": th, "detections": len(pk),
                         "palm-like": palm_like, "in non-palm cells": not_palm,
                         "share palm-like": palm_like / max(len(pk), 1),
                         "pairs closer than 6 m (%)": 100 * (near[:, 1] < 6).mean()})
    _cache["sens"] = pd.DataFrame(rows)
    return _cache["sens"]


def plot_sensitivity(t):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    cols = {4.0: "#d95f02", 5.0: "#e6ab02", 5.5: "#1b7837", 6.0: "#1f78b4", 7.0: "#7570b3"}
    for sp, g in t.groupby("min spacing (m)"):
        a1.plot(g["in non-palm cells"], g["palm-like"], marker="o", color=cols[sp], label=f"min spacing {sp:g} m")
        for _, r in g.iterrows():
            a1.annotate(f'{r["ExG threshold"]:g}', (r["in non-palm cells"], r["palm-like"]), fontsize=6.5,
                        xytext=(3, 2), textcoords="offset points", color=cols[sp])
        a2.plot(g["ExG threshold"], g["share palm-like"] * 100, marker="o", color=cols[sp], label=f"{sp:g} m")
    a1.set_xlabel("detections in cells with no palms (other trees, bushes)"); a1.set_ylabel("palm-like detections")
    a1.legend(frameon=False, fontsize=8); a1.set_title("Every point is one setting; labels are the ExG threshold", loc="left", fontsize=9)
    a2.set_xlabel("ExG threshold"); a2.set_ylabel("detections that are palm-like (%)")
    a2.set_title("Raise the threshold and the share of palms FALLS: the greenest crowns are not palms", loc="left", fontsize=9)
    for a in (a1, a2):
        a.spines[["top", "right"]].set_visible(False)
    best = t.loc[(t["palm-like"] - t["in non-palm cells"]).idxmax()]
    fig.suptitle(f"Best trade-off: spacing {best['min spacing (m)']:g} m, threshold {best['ExG threshold']:g} "
                 f"({int(best['palm-like']):,} palm-like, {int(best['in non-palm cells']):,} in non-palm cells)",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


def products():
    return [
        {"kind": "figure", "name": "ch27-palm-crowns", "figure": figure_crowns,
         "caption": "Every red dot is a crown centre found by the local-maximum filter. "
                    "Inside planted blocks it is one dot per palm; outside them, dots "
                    "fall on ordinary trees, so count inside a plantation boundary."},
        {"kind": "figure", "name": "ch27-palm-density", "figure": figure_density,
         "caption": "Counts turned into palms per hectare on a 50 m grid: the gaps, "
                    "young blocks and edges an estate manager needs to see."},
        {"kind": "chart", "name": "ch27-palm-spacing", "data": spacing_frame,
         "plot": plot_spacing,
         "caption": "Nearest-neighbour distance between counted palms. A clean peak "
                    "near the planting distance is a quick sanity check on the count; "
                    "a long tail below 6 m means double counts."},
        {"kind": "table", "name": "ch27-palm-summary", "data": summary_frame,
         "floatfmt": (".0f", ".1f", ".1f", ".2f", ".0f"),
         "caption": "The count in numbers. Without field counts this is not an "
                    "accuracy; the spacing check is the evidence available."},
        {"kind": "table", "name": "ch27-sensitivity", "data": sensitivity_frame,
         "floatfmt": (".1f", ".2f", ",.0f", ",.0f", ",.0f", ".2f", ".0f"),
         "caption": "Eighteen settings of the same method, scored against two independent proxies for truth."},
        {"kind": "chart", "name": "ch27-sensitivity-chart", "data": sensitivity_frame, "plot": plot_sensitivity, "live": False,
         "caption": "The trade-off between finding palms and counting other trees, for every setting."},
        {"kind": "table", "name": "ch27-crosscheck", "data": crosscheck_table, "columns": ["measure", "shown"],
         "caption": "The drone count against the Forest Data Partnership oil palm model (Sentinel-based, 10 m), cell by cell."},
        {"kind": "chart", "name": "ch27-crosscheck-chart", "data": crosscheck_table, "plot": plot_crosscheck, "live": False,
         "caption": "Left and centre: the same 50 m grid seen by the drone and by the satellite model. Right: every cell, one against the other."},
    ]


if __name__ == "__main__":
    print(summary_frame())
