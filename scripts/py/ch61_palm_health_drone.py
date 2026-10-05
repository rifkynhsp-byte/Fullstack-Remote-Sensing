#| title: Oil palm crown health from a drone orthophoto (Python)
#| description: Every palm counted in the drone chapter gets a greenness and a crown-fullness score from the RGB orthophoto; the crowns are grouped into healthy, moderate and poor with k-means, mapped, and shown as a gallery so the classes can be checked by eye.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 61 | Which palms look unwell?

Same drone orthophoto as the palm-counting chapter (OpenAerialMap, smallholder
oil palm near Banjarbaru, South Kalimantan, CC BY 4.0), same crown centres.
For a circle of 3.5 m around every crown centre:

    GLI       green leaf index (2G - R - B) / (2G + R + B): how green
    VARI      (G - R) / (G + R - B): greenness, less sensitive to haze
    fullness  share of the circle that is green canopy (ExG > 0.05):
              a thin, open or damaged crown fills less of its circle

k-means (3 groups) on the standardised scores, groups ordered by GLI into
healthy / moderate / poor. RGB colour is a symptom, not a diagnosis: yellowing
can be nutrient deficiency, drought, Ganoderma, pests or old fronds. A drone
with red-edge and near-infrared bands, and a field check, come next.

    pip install rasterio scikit-image scikit-learn scipy matplotlib pandas
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ch27_palm_counting as base  # noqa: E402  (load, count_palms)

RADIUS_M = 4.0          # about the radius of a mature crown (crowns ~8 m across)
GRID_MIN, GRID_MAX, GRID_N = 7.0, 11.0, 3   # a palm has >= 3 neighbours at 7-11 m
CLASS_NAMES = ["healthy", "moderate", "poor"]
CLASS_COLS = ["#1a9850", "#fee08b", "#d73027"]
NOT_PALM, NOT_PALM_COL = "not a palm (excluded)", "#3182bd"
_c = {}


def crowns():
    if "df" in _c:
        return _c["df"]
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    rgb, res = base.load()
    peaks = base.count_palms()
    r, g, b = rgb
    s = np.maximum(r + g + b, 1)
    gli = (2 * g - r - b) / np.maximum(2 * g + r + b, 1)
    vari = (g - r) / np.where(np.abs(g + r - b) < 1, 1, g + r - b)
    exg = (2 * g - r - b) / s
    rad = int(round(RADIUS_M / res))
    yy, xx = np.mgrid[-rad:rad + 1, -rad:rad + 1]
    disk = (yy ** 2 + xx ** 2) <= rad ** 2
    rows = []
    H, W = gli.shape
    for i, (y, x) in enumerate(peaks):
        if y - rad < 0 or x - rad < 0 or y + rad >= H or x + rad >= W:
            continue
        win = np.s_[y - rad:y + rad + 1, x - rad:x + rad + 1]
        if (rgb[:, win[0], win[1]].sum(0)[disk] == 0).any():
            continue                                    # touches the no-data frame
        green = exg[win][disk] > 0.05
        rows.append({"row": y, "col": x, "gli": gli[win][disk][green].mean() if green.any() else 0,
                     "vari": np.clip(vari[win][disk][green], -1, 1).mean() if green.any() else 0,
                     "fullness": green.mean()})
    df = pd.DataFrame(rows)
    # Step 0: is it a palm? Planted palms stand on a grid, so a real palm has
    # several neighbours at the planting distance; a bush or a tree does not.
    from scipy.spatial import cKDTree
    xy = df[["row", "col"]].values * res
    tree = cKDTree(xy)
    near = [sum(GRID_MIN <= np.hypot(*(xy[j] - xy[i])) <= GRID_MAX for j in nb if j != i)
            for i, nb in enumerate(tree.query_ball_point(xy, GRID_MAX))]
    df["grid_neighbours"] = near
    df["class"] = NOT_PALM
    palms = df.grid_neighbours >= GRID_N
    z = StandardScaler().fit_transform(df.loc[palms, ["gli", "vari", "fullness"]])
    km = KMeans(3, n_init=20, random_state=0).fit(z)
    gli_by_k = pd.Series(df.loc[palms, "gli"].values).groupby(km.labels_).mean()
    rank = {int(k): r for r, k in enumerate(gli_by_k.sort_values(ascending=False).index)}
    df.loc[palms, "class"] = [CLASS_NAMES[rank[int(k)]] for k in km.labels_]
    _c["df"] = df
    return df


def summary_table():
    df = crowns()
    g = df.groupby("class")
    out = pd.DataFrame({"palms": g.size(), "share": g.size() / len(df),
                        "gli_mean": g.gli.mean(), "vari_mean": g.vari.mean(),
                        "fullness_mean": g.fullness.mean()}).reindex(CLASS_NAMES + [NOT_PALM]).reset_index()
    return out


def plot_scores(df):
    d = crowns()
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    for n, c in zip(CLASS_NAMES, CLASS_COLS):            # palms only
        s = d[d["class"] == n]
        ax.scatter(s.fullness, s.gli, s=6, color=c, label=f"{n} ({len(s)})", alpha=0.7)
    ax.set_xlabel("Crown fullness (share of the 3.5 m circle that is green)")
    ax.set_ylabel("Green leaf index (GLI)")
    ax.set_title("Two scores per crown, three groups", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    return fig


def figure_map():
    d = crowns()
    rgb, res = base.load()
    img = np.clip(np.transpose(rgb, (1, 2, 0)) / np.percentile(rgb[rgb > 0], 99), 0, 1)
    H, W = rgb.shape[1:]
    w, e, s_, n_ = base.lonlat_extent()
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.imshow(img, extent=[w, e, s_, n_])
    for n, c in zip(CLASS_NAMES + [NOT_PALM], CLASS_COLS + [NOT_PALM_COL]):
        s = d[d["class"] == n]
        ax.scatter(w + (s.col + 0.5) / W * (e - w), n_ - (s.row + 0.5) / H * (n_ - s_), s=7, color=c,
                   edgecolor="black", linewidth=0.2, label=n)
    base.graticule(ax)
    ax.set_aspect(1 / np.cos(np.radians((s_ + n_) / 2)))
    ax.legend(frameon=True, fontsize=8, loc="lower right", markerscale=2)
    ax.set_title("Crown health from RGB greenness and fullness", loc="left", fontsize=10)
    return fig


def figure_gallery():
    """Six random crowns from each group, at full drone resolution, for a check by eye."""
    d = crowns()
    rgb, res = base.load()
    rad = int(round(RADIUS_M / res)) + 3
    norm = np.percentile(rgb[rgb > 0], 99)
    fig, axes = plt.subplots(4, 6, figsize=(9, 6.4))
    rng = np.random.default_rng(1)
    names, cols = CLASS_NAMES + [NOT_PALM], CLASS_COLS + [NOT_PALM_COL]
    for i, n in enumerate(names):
        s = d[d["class"] == n]
        pick = s.iloc[rng.choice(len(s), size=min(6, len(s)), replace=False)]
        for j, ax in enumerate(axes[i]):
            ax.set_axis_off()
            if j >= len(pick):
                continue
            y, x = int(pick.row.iloc[j]), int(pick.col.iloc[j])
            chip = rgb[:, y - rad:y + rad + 1, x - rad:x + rad + 1]
            ax.imshow(np.clip(np.transpose(chip, (1, 2, 0)) / norm, 0, 1))
        axes[i, 0].text(-0.15, 0.5, n.replace(" (", "\n("), transform=axes[i, 0].transAxes,
                        ha="right", va="center", fontsize=9, color=cols[i], weight="bold")
    fig.suptitle("Random crowns from each group (0.3 m pixels)", x=0.02, ha="left", fontsize=10)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Fresh fruit bunches (FFB): a map, not only a total
# ---------------------------------------------------------------------------
# Every number below is an assumption you can change, and the chapter tests them:
PEAK_T_HA = 34.5           # potential FFB at prime age, t/ha/yr (PPKS standard; Chapter 60)
ACHIEVE = 0.42             # actual / attainable, Indonesian smallholders (Chapter 60)
SPACING_M = 8.7            # measured planting distance in this block (Chapter 27)
PALMS_HA = 10000 / (SPACING_M ** 2 * np.sqrt(3) / 2)       # triangular planting: about 153 palms/ha
KG_PALM = PEAK_T_HA * ACHIEVE * 1000 / PALMS_HA           # about 95 kg per palm per year
SCENARIOS = {"no health effect": {"healthy": 1.0, "moderate": 1.0, "poor": 1.0},
             "mild (base)": {"healthy": 1.0, "moderate": 0.9, "poor": 0.6},
             "strong": {"healthy": 1.0, "moderate": 0.75, "poor": 0.3}}
BASE_SCEN = "mild (base)"
CELL_M = 30.0              # the map unit: 30 m cells, 0.09 ha, about 14 palm positions


def ffb_palms(scenario=BASE_SCEN):
    d = crowns()
    d = d[d["class"].isin(CLASS_NAMES)].copy()
    d["ffb_kg"] = KG_PALM * d["class"].map(SCENARIOS[scenario])
    return d


def ffb_grid(scenario=BASE_SCEN):
    """FFB per hectare in 30 m cells: the sum of the palms in each cell over its area.
    Gaps (dead, missing or unplanted positions) lower a cell, which a satellite pixel cannot show."""
    rgb, res = base.load()
    H, W = rgb.shape[1:]
    n = int(round(CELL_M / res))
    d = ffb_palms(scenario)
    valid = rgb.sum(0) > 0
    rows, cols = H // n, W // n
    grid = np.full((rows, cols), np.nan)
    sums = np.zeros((rows, cols)); counts = np.zeros((rows, cols))
    idx = (np.minimum(d.row.values // n, rows - 1), np.minimum(d.col.values // n, cols - 1))
    np.add.at(sums, idx, d.ffb_kg.values); np.add.at(counts, idx, 1)
    # Planted area: a cell whose 3 x 3 neighbourhood (about 124 palm positions) holds at least
    # 20 palms. Gaps inside the plantation stay in (as low values); forest and bush around it,
    # with a stray detection here and there, drop out.
    from scipy.ndimage import uniform_filter
    planted = uniform_filter(counts, size=3, mode="constant") * 9 >= 20
    for i in range(rows):
        for j in range(cols):
            if planted[i, j] and valid[i * n:(i + 1) * n, j * n:(j + 1) * n].mean() > 0.95:
                grid[i, j] = sums[i, j] / 1000 / (CELL_M ** 2 / 1e4)       # t/ha/yr
    return grid


def figure_ffb_map():
    d = ffb_palms()
    rgb, res = base.load()
    H, W = rgb.shape[1:]
    w, e, s, n = base.lonlat_extent()
    lon = w + (d.col.values + 0.5) / W * (e - w)
    lat = n - (d.row.values + 0.5) / H * (n - s)
    img = np.clip(np.transpose(rgb, (1, 2, 0)) / np.percentile(rgb[rgb > 0], 99), 0, 1)
    grid = ffb_grid()
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.4))
    axes[0].imshow(img, extent=[w, e, s, n])
    mult = SCENARIOS[BASE_SCEN]
    for n_, c in zip(CLASS_NAMES, CLASS_COLS):
        k = (d["class"] == n_).values
        axes[0].scatter(lon[k], lat[k], s=9, color=c, edgecolor="black", linewidth=0.25,
                        label=f"{n_}: {KG_PALM * mult[n_]:.0f} kg/yr ({k.sum()} palms)")
    axes[0].legend(fontsize=7, loc="upper right", framealpha=0.9, title="FFB per palm", title_fontsize=7)
    axes[0].set_title("Per palm: expected fruit, by crown health", loc="left", fontsize=10)
    axes[1].imshow(img, extent=[w, e, s, n], alpha=0.35)
    im = axes[1].imshow(np.ma.masked_invalid(grid), extent=[w, e, s, n], cmap="YlGn", vmin=0, vmax=18,
                        interpolation="nearest", alpha=0.9)
    fig.colorbar(im, ax=axes[1], shrink=0.7, label="FFB (t/ha/yr), 30 m cells")
    axes[1].set_title("Per 30 m cell: gaps and weak palms show as low yield", loc="left", fontsize=10)
    for ax in axes:
        base.graticule(ax)
        ax.set_aspect(1 / np.cos(np.radians((s + n) / 2)))
    fig.text(0.01, 0.01, "Modelled, not measured: 34.5 t/ha potential x 0.42 achievement, "
             f"{PALMS_HA:.0f} palms/ha, health multipliers {SCENARIOS[BASE_SCEN]}. Drone: OpenAerialMap, CC BY 4.0.",
             fontsize=7, color="#555555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def ffb_table():
    rows = []
    area_ha = (~np.isnan(ffb_grid())).sum() * CELL_M ** 2 / 1e4          # planted cells only
    for name in SCENARIOS:
        d = ffb_palms(name); g = ffb_grid(name)
        v = g[~np.isnan(g)]
        rows.append({"scenario (health multipliers)": name, "palms": len(d), "total_t_yr": d.ffb_kg.sum() / 1000,
                     "planted_ha": area_ha, "t_ha_yr_planted": v.mean(),
                     "cells_p10": np.percentile(v, 10), "cells_p90": np.percentile(v, 90),
                     "cells_below_8_t_ha": (v < 8).mean()})
    d = crowns()
    rows.append({"scenario (health multipliers)": "upper bound: all 2,585 detections as healthy palms",
                 "palms": len(d), "total_t_yr": len(d) * KG_PALM / 1000,
                 "planted_ha": np.nan, "t_ha_yr_planted": np.nan,
                 "cells_p10": np.nan, "cells_p90": np.nan, "cells_below_8_t_ha": np.nan})
    return pd.DataFrame(rows)


def ffb_cells_frame():
    v = ffb_grid()
    return pd.DataFrame({"t_ha_yr": v[~np.isnan(v)]})


def plot_ffb_cells(d):
    fig, ax = plt.subplots(figsize=(6.6, 3.2))
    ax.hist(d.t_ha_yr, bins=np.arange(0, 26, 1), color="#78a65a", edgecolor="white")
    ax.axvline(PEAK_T_HA * ACHIEVE, color="#c0392b", lw=1.2)
    ax.text(PEAK_T_HA * ACHIEVE, ax.get_ylim()[1] * 0.92, f" a full, healthy cell: {PEAK_T_HA * ACHIEVE:.1f} t/ha",
            fontsize=8, color="#c0392b")
    ax.set_xlabel("modelled FFB per 30 m cell (t/ha/yr)"); ax.set_ylabel("cells")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("One block, a wide spread: the total hides where the fruit is lost", loc="left", fontsize=10)
    fig.tight_layout()
    return fig



# ---------------------------------------------------------------------------
# Land cover from the drone: objects, not pixels
# ---------------------------------------------------------------------------
# Names follow what the classes turned out to contain on the visual check (figure_lc_check), not the seed rules
# intentions: smooth green canopy is mostly shrub and regrowth (RGB cannot separate grass from dense shrub at
# 0.3 m), and the pale smooth class holds dry grass as well as bare soil and tracks.
LC = [("oil palm", "#e69f00"), ("trees and bush (rough canopy)", "#1b7837"), ("shrub and regrowth (smooth canopy)", "#a6dba0"),
      ("bare soil, tracks and dry grass", "#bf812d"), ("shadow and water", "#2c3e50")]
# Visual check of the 40 random objects in figure_lc_check (seed 3), read by eye at full resolution:
LC_CHECK = [("oil palm", 8, 8), ("trees and bush (rough canopy)", 7, 8), ("shrub and regrowth (smooth canopy)", 6, 8),
            ("bare soil, tracks and dry grass", 6, 8), ("shadow and water", 8, 8)]


def lc_check_table():
    d = pd.DataFrame(LC_CHECK, columns=["class", "correct", "checked"])
    return pd.concat([d, pd.DataFrame([{"class": "all", "correct": d.correct.sum(), "checked": d.checked.sum()}])]).assign(
        share=lambda x: x.correct / x.checked)


def drone_landcover():
    """SLIC superpixels (about one palm crown each), colour and texture per object, seed labels from simple
    rules plus the planting grid of the counting chapter, then a Random Forest for every object.
    Seeds are rules, not truth: the result is checked by eye on a random sample (figure_lc_check)."""
    if "lc" in _c:
        return _c["lc"]
    from skimage.segmentation import slic
    from sklearn.ensemble import RandomForestClassifier
    from scipy import ndimage as ndi
    rgb, res = base.load()
    img = np.transpose(rgb, (1, 2, 0)); valid = img.sum(2) > 0
    norm = img / np.percentile(img[valid], 99)
    seg = slic(np.clip(norm, 0, 1), n_segments=8000, compactness=10, start_label=1, mask=valid)
    r, g, b = [norm[..., i] for i in range(3)]; s = np.maximum(r + g + b, 1e-6)
    exg = (2 * g - r - b) / s; bright = (r + g + b) / 3
    tex = ndi.generic_filter(bright, np.std, size=5)                      # local roughness: crowns are rough, grass smooth
    labels = np.arange(1, seg.max() + 1)
    m = lambda a: ndi.mean(a, seg, labels)
    F = pd.DataFrame({"r": m(r), "g": m(g), "b": m(b), "exg": m(exg), "bright": m(bright), "tex": m(tex),
                      "tex_sd": ndi.standard_deviation(bright, seg, labels)})
    # planting-grid proximity: share of the object's pixels within 3.5 m of a crown that passed the grid test
    d = crowns(); pal = d[d["class"].isin(CLASS_NAMES)]
    mask = np.zeros(valid.shape, bool); mask[pal.row.values.astype(int), pal.col.values.astype(int)] = True
    near = ndi.distance_transform_edt(~mask) * res < 3.5
    F["grid"] = m(near.astype(float))
    seed = np.full(len(F), -1)
    green = F.exg > F.exg.quantile(0.45)
    seed[(F.bright < F.bright.quantile(0.08))] = 4                                     # shadow, water
    smooth = F.tex < F.tex.median()
    seed[(F.exg < F.exg.quantile(0.15)) & (F.bright > F.bright.quantile(0.5)) & smooth & (F.grid < 0.3)] = 3   # bare soil, roads: pale AND smooth
    seed[green & (F.tex < F.tex.quantile(0.25)) & (F.bright > F.bright.quantile(0.6)) & (F.grid < 0.05)] = 2 # grass: smooth AND light green
    seed[green & (F.tex > F.tex.quantile(0.6)) & (F.grid < 0.05)] = 1                  # rough green off-grid: trees, bush
    seed[green & (F.grid > 0.6)] = 0                                                   # green on the planting grid: palm
    rf = RandomForestClassifier(200, random_state=0, min_samples_leaf=3).fit(F[seed >= 0], seed[seed >= 0])
    cls = rf.predict(F)
    cls[(F.grid.values > 0.6) & (F.exg.values > F.exg.quantile(0.2))] = 0     # on the planting grid and not bare: palm
    lc = np.full(seg.shape, -1); lc[seg > 0] = cls[seg[seg > 0] - 1]
    _c["lc"] = (lc, seg, F.assign(cls=cls, seed=seed), res)
    return _c["lc"]


def figure_lc_map():
    from matplotlib.colors import ListedColormap
    lc, seg, F, res = drone_landcover()
    rgb, _ = base.load(); w, e, s, n = base.lonlat_extent()
    img = np.clip(np.transpose(rgb, (1, 2, 0)) / np.percentile(rgb[rgb > 0], 99), 0, 1)
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    axes[0].imshow(img, extent=[w, e, s, n]); axes[0].set_title("Drone orthophoto (0.3 m)", loc="left", fontsize=10)
    axes[1].imshow(np.ma.masked_less(lc, 0), extent=[w, e, s, n], cmap=ListedColormap([c for _, c in LC]), vmin=-0.5, vmax=4.5, interpolation="nearest")
    axes[1].set_title("Land cover from the drone, by object", loc="left", fontsize=10)
    from matplotlib.patches import Patch
    axes[1].legend(handles=[Patch(color=c, label=l) for l, c in LC], loc="lower right", fontsize=7.5, framealpha=0.9)
    for ax in axes:
        base.graticule(ax); ax.set_aspect(1 / np.cos(np.radians((s + n) / 2)))
    fig.tight_layout()
    return fig


def lc_area_table():
    lc, seg, F, res = drone_landcover()
    px = np.array([(lc == k).sum() for k in range(len(LC))]) * res ** 2 / 1e4
    return pd.DataFrame({"class": [l for l, _ in LC], "area_ha": px, "share": px / px.sum()})


def lc_sample(n_per=8, seed=3):
    lc, seg, F, res = drone_landcover()
    rng = np.random.default_rng(seed); out = []
    for k in range(len(LC)):
        ids = np.where(F.cls.values == k)[0]
        for i in rng.choice(ids, size=min(n_per, len(ids)), replace=False):
            out.append((k, i + 1))
    return out


def figure_lc_check():
    """Eight random objects per predicted class, at full resolution, outlined: the honest check of the map."""
    lc, seg, F, res = drone_landcover(); rgb, _ = base.load()
    img = np.clip(np.transpose(rgb, (1, 2, 0)) / np.percentile(rgb[rgb > 0], 99), 0, 1)
    smp = lc_sample(); fig, axes = plt.subplots(len(LC), 8, figsize=(10, 6.6))
    for ax in axes.ravel(): ax.set_axis_off()
    from skimage.segmentation import find_boundaries
    for j, (k, sid) in enumerate(smp):
        rr, cc = np.where(seg == sid); y, x = int(rr.mean()), int(cc.mean()); h = 22
        y0, y1, x0, x1 = max(0, y - h), y + h, max(0, x - h), x + h
        chip = img[y0:y1, x0:x1].copy(); bd = find_boundaries(seg[y0:y1, x0:x1] == sid); chip[bd] = [1, 0, 0]
        ax = axes[k, j % 8]; ax.imshow(chip); ax.set_title(f"{sid}", fontsize=6)
        if j % 8 == 0: ax.text(-0.15, 0.5, LC[k][0], transform=ax.transAxes, ha="right", va="center", fontsize=8, color=LC[k][1], weight="bold")
    fig.suptitle("Random objects from each predicted class (red outline, 13 x 13 m chips): if the rows look alike inside and different between, the map is right", x=0.01, ha="left", fontsize=9)
    fig.tight_layout()
    return fig


def products():
    return [
        {"kind": "figure", "name": "ch61-map", "figure": figure_map,
         "caption": "Every counted palm coloured by its health group, over the drone "
                    "orthophoto (OpenAerialMap, CC BY 4.0)."},
        {"kind": "chart", "name": "ch61-scores", "data": lambda: crowns()[["gli", "vari",
                                                                          "fullness", "class"]],
         "plot": plot_scores,
         "caption": "Greenness against crown fullness for every palm, coloured by group."},
        {"kind": "table", "name": "ch61-summary", "data": summary_table,
         "floatfmt": ("", ",.0f", ".0%", ".3f", ".3f", ".2f"),
         "caption": "Palms per group and the mean scores of each group."},
        {"kind": "figure", "name": "ch61-gallery", "figure": figure_gallery,
         "caption": "Six random crowns from each group. If the groups are right, the rows "
                    "should look different to your eye."},
        {"kind": "figure", "name": "ch61-ffb-map", "figure": figure_ffb_map,
         "caption": "Modelled fresh fruit bunches from the drone: per palm (left) and per 30 m cell (right). "
                    "Only crowns that pass the planting-grid test are counted."},
        {"kind": "chart", "name": "ch61-ffb-cells", "data": ffb_cells_frame, "plot": plot_ffb_cells, "live": False,
         "caption": "Distribution of modelled FFB across the 30 m cells of the block."},
        {"kind": "figure", "name": "ch61-lc-map", "figure": figure_lc_map,
         "caption": "Land cover classified from the drone orthophoto, object by object (OpenAerialMap, CC BY 4.0)."},
        {"kind": "table", "name": "ch61-lc-area", "data": lc_area_table, "floatfmt": ("", ".2f", ".0%"),
         "caption": "Area of each class in the orthophoto."},
        {"kind": "figure", "name": "ch61-lc-check", "figure": figure_lc_check,
         "caption": "The check: random objects of each predicted class at full resolution."},
        {"kind": "table", "name": "ch61-lc-check-table", "data": lc_check_table, "floatfmt": ("", ".0f", ".0f", ".0%"),
         "caption": "Visual check of the random objects above, read by eye (8 per class). A small sample: it says the map "
                    "is usable for palm vs non-palm, and that the shrub and dry-grass classes are approximate."},
        {"kind": "table", "name": "ch61-ffb", "data": ffb_table,
         "floatfmt": ("", ",.0f", ",.0f", ".1f", ".1f", ".1f", ".1f", ".0%"),
         "caption": "Block totals and the spread between cells under three assumptions about how much crown "
                    "health costs in fruit, plus the upper bound if every detection were a healthy palm."},
    ]


if __name__ == "__main__":
    print(summary_table())
