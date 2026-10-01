#| title: Oil palm crown health from a drone orthophoto (Python)
#| description: Every palm counted in the drone chapter gets a greenness and a crown-fullness score from the RGB orthophoto; the crowns are grouped into healthy, moderate and poor with k-means, mapped, and shown as a gallery so the classes can be checked by eye.

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
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.imshow(img)
    for n, c in zip(CLASS_NAMES + [NOT_PALM], CLASS_COLS + [NOT_PALM_COL]):
        s = d[d["class"] == n]
        ax.scatter(s.col, s.row, s=7, color=c, edgecolor="black", linewidth=0.2, label=n)
    ax.set_axis_off()
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
    ]


if __name__ == "__main__":
    print(summary_table())
