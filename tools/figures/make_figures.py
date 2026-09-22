#!/usr/bin/env python3
"""
make_figures.py
===============

Generates the conceptual figures used throughout the book.

Scope, stated plainly
---------------------
These are DIAGRAMS, not satellite maps. Every one is computed from published
reference values or from a synthetic pattern built here, and none of them
contains real Sentinel-2 or Sentinel-1 pixels.

That distinction matters and the captions say so. Real maps of your own study
area come from running the Earth Engine scripts in scripts/ and exporting the
result; notebooks/produce_maps.ipynb does that in Python.

What each figure is for
-----------------------
    spectral-signatures   Chapter 2. The three curves the book asks readers to
                          draw from memory, with Sentinel-2 bands overlaid.
    ndvi-saturation       Chapter 12. Why NDVI stops responding over dense
                          canopy and EVI does not.
    speckle-filter        Chapter 10. What speckle is and what filtering costs.
    glcm-texture          Chapter 14. Plantation against natural forest, with
                          entropy computed rather than asserted.
    block-cv              Chapter 15. Random split against block split, and
                          where the leakage comes from.
    confusion-matrix      Chapter 17. Producer and user accuracy read off the
                          same table.

Run
---
    python3 tools/figures/make_figures.py

Writes PNG at 200 dpi into images/.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "images"
OUT.mkdir(exist_ok=True)

# Book palette, matching theme.scss so figures sit inside the design rather
# than beside it.
TEAL = "#0f6b57"
BRIGHT = "#14a37f"
AMBER = "#c8792b"
RED = "#a4372a"
INK = "#1b1f23"
MUTED = "#5c6773"
RULE = "#e4e0d8"
SAND = "#faf8f4"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})


def save(fig, name):
    path = OUT / f"{name}.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote images/{name}.png")


# ---------------------------------------------------------------------------
# 1. Spectral signatures
# ---------------------------------------------------------------------------
def spectral_signatures():
    """The three curves, from typical published reflectance values.

    These are representative shapes rather than a measurement of any
    particular surface. The point of the figure is the SHAPE: the red trough,
    the near infrared plateau, the water collapse. Exact values vary by
    species, season and sensor.
    """
    wl = np.linspace(400, 2400, 500)

    def curve(points):
        """Smooth interpolation through the reference points.

        Straight line interpolation between control points produces an
        angular curve that no leaf has ever produced. PCHIP preserves the
        shape without overshooting into negative reflectance, which a cubic
        spline would do at the water absorption troughs.
        """
        from scipy.interpolate import PchipInterpolator
        x, y = zip(*points)
        return PchipInterpolator(np.array(x), np.array(y))(wl)

    vegetation = curve([
        (400, 0.03), (450, 0.04), (550, 0.10), (620, 0.05), (670, 0.03),
        (700, 0.05), (720, 0.25), (760, 0.48), (900, 0.50), (1100, 0.48),
        (1250, 0.42), (1450, 0.16), (1650, 0.28), (1900, 0.06),
        (2200, 0.16), (2400, 0.10),
    ])
    water = curve([
        (400, 0.05), (480, 0.06), (550, 0.05), (620, 0.03), (700, 0.015),
        (800, 0.008), (1000, 0.004), (1400, 0.002), (2400, 0.002),
    ])
    soil = curve([
        (400, 0.07), (500, 0.11), (600, 0.16), (700, 0.20), (800, 0.24),
        (1000, 0.28), (1300, 0.33), (1450, 0.30), (1650, 0.36),
        (1900, 0.28), (2200, 0.34), (2400, 0.31),
    ])

    fig, ax = plt.subplots(figsize=(9, 4.6))

    # Sentinel-2 bands, centre wavelength and approximate width in nm.
    bands = [
        ("B2", 490, 65), ("B3", 560, 35), ("B4", 665, 30),
        ("B5", 705, 15), ("B6", 740, 15), ("B7", 783, 20),
        ("B8", 842, 115), ("B11", 1610, 90), ("B12", 2190, 180),
    ]
    for name, centre, width in bands:
        ax.add_patch(Rectangle((centre - width / 2, 0), width, 0.56,
                               color=TEAL, alpha=0.07, zorder=0))
        ax.text(centre, 0.575, name, ha="center", fontsize=6.5, color=MUTED)

    # The two water vapour absorption features. Note the deliberate gap in
    # Sentinel-2's band placement around them.
    for lo, hi in [(1340, 1460), (1790, 1960)]:
        ax.axvspan(lo, hi, color=MUTED, alpha=0.10, zorder=0)
    ax.text(1400, 0.50, "H₂O", ha="center", fontsize=7, color=MUTED)
    ax.text(1875, 0.50, "H₂O", ha="center", fontsize=7, color=MUTED)

    ax.plot(wl, vegetation, color=BRIGHT, lw=2.2, label="Healthy vegetation", zorder=3)
    ax.plot(wl, water, color="#1A5BAB", lw=2.2, label="Water", zorder=3)
    ax.plot(wl, soil, color=AMBER, lw=2.2, label="Bare soil", zorder=3)

    ax.annotate("red trough\n(chlorophyll absorbs)", xy=(670, 0.03),
                xytext=(560, 0.30), fontsize=7.5, color=INK, ha="center",
                arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.9))
    ax.annotate("NIR plateau\n(mesophyll scatters,\nnot chlorophyll)", xy=(870, 0.50),
                xytext=(1050, 0.56), fontsize=7.5, color=INK, ha="center",
                arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.9))
    ax.annotate("red edge", xy=(720, 0.25), xytext=(700, 0.42),
                fontsize=7.5, color=INK, ha="center",
                arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.9))

    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Reflectance")
    ax.set_xlim(400, 2400)
    ax.set_ylim(0, 0.62)
    ax.legend(frameon=False, loc="upper right", fontsize=8.5)
    ax.set_title("Spectral signatures and Sentinel-2 band placement",
                 fontsize=11, color=INK, pad=14, loc="left")
    save(fig, "spectral-signatures")


# ---------------------------------------------------------------------------
# 2. NDVI saturation
# ---------------------------------------------------------------------------
def ndvi_saturation():
    """Why NDVI cannot distinguish intact from degraded tropical forest.

    Reflectance is modelled with a simple Beer-Lambert style canopy: red is
    absorbed strongly so it saturates fast, NIR accumulates through multiple
    scattering. The resulting NDVI curve reproduces the well documented
    plateau above LAI of roughly 3.
    """
    lai = np.linspace(0, 8, 300)

    red = 0.04 + 0.26 * np.exp(-2.2 * lai)      # soil showing through, then absorbed
    nir = 0.50 - 0.28 * np.exp(-0.75 * lai)     # builds with scattering layers
    blue = 0.03 + 0.14 * np.exp(-2.4 * lai)

    ndvi = (nir - red) / (nir + red)
    evi = 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)

    fig, ax = plt.subplots(figsize=(8, 4.2))

    ax.axvspan(3, 8, color=RED, alpha=0.06, zorder=0)
    ax.text(5.5, 0.24, "saturated zone\ntropical forest lives here",
            ha="center", fontsize=8, color=RED)

    ax.plot(lai, ndvi, color=BRIGHT, lw=2.4, label="NDVI")
    ax.plot(lai, evi, color=AMBER, lw=2.4, label="EVI")

    ax.annotate("NDVI stops responding:\nintact and degraded forest\nreturn nearly the same value",
                xy=(5.0, ndvi[np.argmin(abs(lai - 5.0))]), xytext=(4.4, 0.55),
                fontsize=7.5, ha="center", color=INK,
                arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.9))

    ax.set_xlabel("Leaf area index")
    ax.set_ylabel("Index value")
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 1.0)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    ax.set_title("NDVI saturation, and why EVI keeps responding",
                 fontsize=11, color=INK, pad=14, loc="left")
    save(fig, "ndvi-saturation")


# ---------------------------------------------------------------------------
# 3. Speckle
# ---------------------------------------------------------------------------
def speckle_filter():
    """Speckle is multiplicative and inherent, and filtering costs edges.

    A clean scene of three backscatter classes is multiplied by Gamma
    distributed speckle with a realistic number of looks, then filtered two
    ways so the edge cost of the mean is visible next to the median.
    """
    from scipy.ndimage import median_filter, uniform_filter

    rng = np.random.default_rng(42)
    n = 200
    clean = np.full((n, n), 0.08)                  # calm water, dark
    clean[40:160, 40:160] = 0.35                   # forest canopy
    clean[70:130, 70:130] = 0.75                   # double bounce, flooded forest

    looks = 4
    speckle = rng.gamma(shape=looks, scale=1.0 / looks, size=(n, n))
    observed = clean * speckle

    med = median_filter(observed, size=5)
    mean = uniform_filter(observed, size=5)

    fig, axes = plt.subplots(1, 4, figsize=(12, 3.4))
    panels = [
        (clean, "Underlying scene\n(never observed)"),
        (observed, "As recorded\nspeckle is the physics"),
        (med, "Focal median 5×5\nedges survive"),
        (mean, "Focal mean 5×5\nedges smeared"),
    ]
    for ax, (data, title) in zip(axes, panels):
        ax.imshow(data, cmap="gray", vmin=0, vmax=0.9)
        ax.set_title(title, fontsize=8.5, color=INK, pad=8)
        ax.set_xticks([]); ax.set_yticks([])

    # Quantify the edge cost rather than asserting it.
    edge = slice(95, 105)
    sharp_med = np.abs(np.diff(med[edge, 60:80].mean(axis=0))).max()
    sharp_mean = np.abs(np.diff(mean[edge, 60:80].mean(axis=0))).max()
    fig.text(0.5, -0.04,
             f"Maximum edge gradient across the boundary: median {sharp_med:.3f}, "
             f"mean {sharp_mean:.3f}. The mean loses {100*(1-sharp_mean/sharp_med):.0f}% of the edge.",
             ha="center", fontsize=8, color=MUTED)
    save(fig, "speckle-filter")


# ---------------------------------------------------------------------------
# 4. GLCM texture
# ---------------------------------------------------------------------------
def glcm_texture():
    """Two canopies with the same mean brightness and different arrangement.

    The plantation is a regular grid of identical crowns; the natural stand
    has crowns of varying size at random positions. Mean reflectance is
    matched deliberately, so any separation comes from texture alone.
    """
    from skimage.feature import graycomatrix, graycoprops

    rng = np.random.default_rng(7)
    n = 128

    def crown(canvas, cy, cx, radius, brightness):
        yy, xx = np.ogrid[:canvas.shape[0], :canvas.shape[1]]
        d = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
        canvas += brightness * np.exp(-(d ** 2) / (2 * (radius / 1.6) ** 2))

    plantation = np.full((n, n), 0.10)
    for y in range(8, n, 11):
        for x in range(8, n, 11):
            crown(plantation, y, x, 5.0, 0.42)

    natural = np.full((n, n), 0.10)
    for _ in range(150):
        crown(natural,
              rng.uniform(0, n), rng.uniform(0, n),
              rng.uniform(2.5, 9.0), rng.uniform(0.25, 0.60))

    # Match the means so the comparison is honest: only arrangement differs.
    natural = natural * (plantation.mean() / natural.mean())

    def texture_stats(img):
        q = np.clip(img / 0.9, 0, 1)
        q = (q * 255).astype(np.uint8)
        glcm = graycomatrix(q, distances=[1], angles=[0, np.pi/2],
                            levels=256, symmetric=True, normed=True)
        contrast = graycoprops(glcm, "contrast").mean()
        p = glcm[:, :, 0, :].mean(axis=2)
        p = p[p > 0]
        entropy = -np.sum(p * np.log(p))
        asm = graycoprops(glcm, "ASM").mean()
        return contrast, entropy, asm

    c_p, e_p, a_p = texture_stats(plantation)
    c_n, e_n, a_n = texture_stats(natural)

    fig, axes = plt.subplots(1, 2, figsize=(9, 4.6))
    for ax, img, name, (c, e, a) in [
        (axes[0], plantation, "Planted monoculture", (c_p, e_p, a_p)),
        (axes[1], natural, "Natural stand", (c_n, e_n, a_n)),
    ]:
        ax.imshow(img, cmap="YlGn", vmin=0, vmax=0.62)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"{name}\nmean reflectance {img.mean():.3f}",
                     fontsize=9.5, color=INK, pad=8)
        ax.text(0.5, -0.11,
                f"contrast {c:.0f}    entropy {e:.2f}    ASM {a:.4f}",
                transform=ax.transAxes, ha="center", fontsize=8.5, color=TEAL)

    fig.suptitle("Identical mean brightness, different arrangement: "
                 "texture is what separates them",
                 fontsize=11, color=INK, y=1.02)
    save(fig, "glcm-texture")
    return (e_p, e_n)


# ---------------------------------------------------------------------------
# 5. Block cross validation
# ---------------------------------------------------------------------------
def block_cv():
    """Where spatial leakage comes from, drawn rather than described."""
    rng = np.random.default_rng(3)
    n_pts = 220
    pts = rng.uniform(0, 10, size=(n_pts, 2))

    random_fold = rng.integers(0, 2, n_pts)

    block = 2.5
    block_id = (pts[:, 0] // block).astype(int) + 4 * (pts[:, 1] // block).astype(int)
    block_fold = (block_id % 2)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8))

    for ax, folds, title in [
        (axes[0], random_fold, "Random split"),
        (axes[1], block_fold, "Spatial block split"),
    ]:
        train = pts[folds == 0]
        test = pts[folds == 1]
        ax.scatter(train[:, 0], train[:, 1], s=22, color=BRIGHT,
                   label="train", edgecolor="white", linewidth=0.4)
        ax.scatter(test[:, 0], test[:, 1], s=22, color=AMBER,
                   label="test", edgecolor="white", linewidth=0.4)
        ax.set_xlim(0, 10); ax.set_ylim(0, 10)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(title, fontsize=10.5, color=INK, pad=10)
        ax.legend(frameon=False, fontsize=8.5, loc="upper right")
        ax.set_aspect("equal")

    for g in np.arange(block, 10, block):
        axes[1].axvline(g, color=MUTED, lw=0.7, ls="--", alpha=0.6)
        axes[1].axhline(g, color=MUTED, lw=0.7, ls="--", alpha=0.6)

    # Quantify the leakage: nearest test point to each training point.
    def mean_nn(folds):
        tr = pts[folds == 0]; te = pts[folds == 1]
        d = np.sqrt(((tr[:, None, :] - te[None, :, :]) ** 2).sum(-1))
        return d.min(axis=1).mean()

    axes[0].text(0.5, -0.09,
                 f"mean distance to nearest test point: {mean_nn(random_fold):.2f} units",
                 transform=axes[0].transAxes, ha="center", fontsize=8.5, color=RED)
    axes[1].text(0.5, -0.09,
                 f"mean distance to nearest test point: {mean_nn(block_fold):.2f} units",
                 transform=axes[1].transAxes, ha="center", fontsize=8.5, color=TEAL)

    fig.suptitle("Random splitting puts each training point next to a test point",
                 fontsize=11, color=INK, y=1.0)
    save(fig, "block-cv")
    return mean_nn(random_fold), mean_nn(block_fold)


# ---------------------------------------------------------------------------
# 6. Confusion matrix
# ---------------------------------------------------------------------------
def confusion_matrix():
    """The same table read two ways: producer accuracy and user accuracy."""
    classes = ["Mangrove", "Other forest", "Water", "Bareland", "Urban"]
    m = np.array([
        [142,  23,   5,   4,   1],
        [ 18, 176,   2,   9,   3],
        [  3,   1, 148,   6,   0],
        [  5,   8,   7, 131,  12],
        [  1,   4,   0,  14, 119],
    ])

    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    ax.imshow(np.where(np.eye(5, dtype=bool), 1, 0.25), cmap="Greens",
              vmin=0, vmax=1.6)

    for i in range(5):
        for j in range(5):
            on_diag = i == j
            ax.text(j, i, str(m[i, j]), ha="center", va="center",
                    fontsize=10, color=INK if on_diag else MUTED,
                    fontweight="bold" if on_diag else "normal")

    producer = np.diag(m) / m.sum(axis=1)
    user = np.diag(m) / m.sum(axis=0)
    overall = np.trace(m) / m.sum()

    for i, p in enumerate(producer):
        ax.text(5.05, i, f"{p*100:.0f}%", va="center", fontsize=9, color=TEAL)
    for j, u in enumerate(user):
        ax.text(j, 5.05, f"{u*100:.0f}%", ha="center", fontsize=9, color=AMBER)

    ax.text(5.05, -0.85, "Producer\naccuracy", ha="left", va="center",
            fontsize=8.5, color=TEAL, fontweight="bold")
    ax.text(-0.75, 5.05, "User\naccuracy", ha="center", va="center",
            fontsize=8.5, color=AMBER, fontweight="bold")

    ax.set_xticks(range(5)); ax.set_yticks(range(5))
    ax.set_xticklabels(classes, rotation=30, ha="right", fontsize=8.5)
    ax.set_yticklabels(classes, fontsize=8.5)
    ax.set_xlabel("Predicted", fontsize=9.5)
    ax.set_ylabel("Actual", fontsize=9.5)
    ax.set_xlim(-0.5, 6.0); ax.set_ylim(5.7, -0.5)
    ax.set_title(f"Overall accuracy {overall*100:.1f}%, and why that number hides the problem",
                 fontsize=10.5, color=INK, pad=16, loc="left")

    fig.text(0.5, -0.02,
             "Mangrove and other forest confuse each other in both directions, "
             f"{m[0,1]} one way and {m[1,0]} the other.\n"
             "Every improvement worth making lives in that one class pair.",
             ha="center", fontsize=8.5, color=MUTED)
    save(fig, "confusion-matrix")
    return overall, producer[0], user[0]




# ---------------------------------------------------------------------------
# 7. The filter funnel
# ---------------------------------------------------------------------------
def filter_funnel():
    """How a global archive collapses to one usable scene.

    The counts are realistic for a single Sentinel-2 tile over a wet tropical
    coast across one year. They are illustrative of the shape rather than a
    query result, and the chapter says so.
    """
    steps = [
        ("Global archive\nCOPERNICUS/S2_SR_HARMONIZED", 4_500_000),
        ("filterBounds(aoi)", 146),
        ("filterDate(one year)", 73),
        ("CLOUDY_PIXEL_PERCENTAGE < 15", 6),
        ("sort() then first()", 1),
    ]
    labels = [s[0] for s in steps]
    counts = np.array([s[1] for s in steps], dtype=float)
    widths = np.log10(counts + 1) / np.log10(counts.max() + 1)

    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    colours = [TEAL, TEAL, BRIGHT, AMBER, RED]

    for i, (label, count, w, c) in enumerate(zip(labels, counts, widths, colours)):
        y = len(steps) - i - 1
        ax.add_patch(Rectangle((0.5 - w / 2, y - 0.32), w, 0.64,
                               facecolor=c, alpha=0.82, edgecolor="none"))
        ax.text(0.5, y, f"{int(count):,}".replace(",", " "),
                ha="center", va="center", fontsize=10.5,
                color="white", fontweight="bold")
        ax.text(1.06, y, label, ha="left", va="center", fontsize=8.8, color=INK)

    ax.set_xlim(0, 2.3)
    ax.set_ylim(-0.7, len(steps) - 0.3)
    ax.axis("off")
    ax.set_title("Each filter is lazy: nothing is fetched until something forces evaluation",
                 fontsize=10.5, color=INK, pad=12, loc="left")
    fig.text(0.05, -0.02,
             "Counts are representative for one tile over a wet tropical coast. "
             "The shape is the point, not the exact numbers.",
             fontsize=8, color=MUTED)
    save(fig, "filter-funnel")


# ---------------------------------------------------------------------------
# 8. Compositing
# ---------------------------------------------------------------------------
def compositing():
    """Why the median of masked observations beats hunting for a clear scene.

    Six synthetic acquisitions over the same ground, each with cloud in a
    different place. No single scene is usable. The median of what survives
    masking has no gaps, and the observation count map shows where confidence
    is lowest.
    """
    rng = np.random.default_rng(11)
    n = 90

    # Underlying scene: river, mangrove belt, upland, ponds.
    yy, xx = np.mgrid[0:n, 0:n]
    truth = np.full((n, n), 0.42)                      # upland vegetation
    truth[np.abs(yy - 45 - 8 * np.sin(xx / 12)) < 6] = 0.06   # river
    belt = np.abs(yy - 45 - 8 * np.sin(xx / 12))
    truth[(belt >= 6) & (belt < 14)] = 0.28            # mangrove
    truth[20:30, 60:75] = 0.10                         # aquaculture ponds

    scenes, masks = [], []
    for k in range(6):
        cloud = np.zeros((n, n), bool)
        for _ in range(rng.integers(2, 5)):
            cy, cx = rng.uniform(0, n, 2)
            r = rng.uniform(12, 26)
            cloud |= ((yy - cy) ** 2 + (xx - cx) ** 2) < r ** 2
        obs = truth + rng.normal(0, 0.015, (n, n))
        obs[cloud] = rng.uniform(0.75, 0.95, cloud.sum())   # bright cloud
        scenes.append(obs)
        masks.append(~cloud)

    stack = np.array([np.where(m, s, np.nan) for s, m in zip(scenes, masks)])
    median = np.nanmedian(stack, axis=0)
    count = np.sum(~np.isnan(stack), axis=0)

    fig = plt.figure(figsize=(12, 5.2))
    gs = fig.add_gridspec(2, 6, hspace=0.28, wspace=0.12)

    for k in range(6):
        ax = fig.add_subplot(gs[0, k])
        ax.imshow(scenes[k], cmap="YlGn_r", vmin=0, vmax=1)
        ax.set_xticks([]); ax.set_yticks([])
        pct = 100 * (1 - masks[k].mean())
        ax.set_title(f"scene {k+1}\n{pct:.0f}% cloud", fontsize=7.5, color=MUTED, pad=4)

    ax = fig.add_subplot(gs[1, 0:3])
    ax.imshow(median, cmap="YlGn_r", vmin=0, vmax=1)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title("Median of what survived masking: no gaps, no cloud",
                 fontsize=9.5, color=INK, pad=8)

    ax = fig.add_subplot(gs[1, 3:6])
    im = ax.imshow(count, cmap="magma", vmin=0, vmax=6)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"Clear observations per pixel: {count.min()} to {count.max()}",
                 fontsize=9.5, color=INK, pad=8)
    cbar = plt.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cbar.ax.tick_params(labelsize=7.5)

    fig.suptitle("No single scene is usable. Every pixel of the composite is, "
                 "and the count map says where to trust it least.",
                 fontsize=10.5, color=INK, y=1.0)
    save(fig, "compositing")
    return count.min(), count.max()


# ---------------------------------------------------------------------------
# 9. Radar scattering mechanisms
# ---------------------------------------------------------------------------
def radar_scattering():
    """Why flooded forest is bright and calm water is black."""
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.9))

    panels = [
        ("Surface scattering\ncalm water: very dark", "smooth"),
        ("Volume scattering\ncanopy: moderate, VH", "volume"),
        ("Double bounce\nflooded forest: very bright", "double"),
    ]

    for ax, (title, kind) in zip(axes, panels):
        ax.set_xlim(0, 10); ax.set_ylim(0, 7)
        ax.axis("off")
        ax.set_title(title, fontsize=9.5, color=INK, pad=10)

        # sensor
        ax.plot(1.2, 6.3, marker="s", ms=9, color=TEAL)
        ax.text(1.2, 6.75, "sensor", ha="center", fontsize=7.5, color=MUTED)

        # ground
        ax.plot([0.5, 9.5], [1.2, 1.2], color=MUTED, lw=1.4)

        arrow = dict(arrowstyle="->", lw=1.6)

        if kind == "smooth":
            ax.fill_between([0.5, 9.5], 0.6, 1.2, color="#1A5BAB", alpha=0.35)
            ax.annotate("", xy=(5.0, 1.2), xytext=(1.5, 6.1),
                        arrowprops=dict(color=AMBER, **arrow))
            ax.annotate("", xy=(8.7, 5.9), xytext=(5.0, 1.2),
                        arrowprops=dict(color=AMBER, **arrow))
            ax.text(7.6, 3.0, "reflected away\nfrom the sensor",
                    fontsize=7.8, color=RED, ha="center")

        elif kind == "volume":
            for cx in (4.0, 5.6, 7.2):
                ax.plot([cx, cx], [1.2, 2.6], color="#6b4a2f", lw=2.4)
                ax.add_patch(plt.Circle((cx, 3.4), 1.0, color=BRIGHT, alpha=0.30))
            ax.annotate("", xy=(5.4, 4.0), xytext=(1.5, 6.1),
                        arrowprops=dict(color=AMBER, **arrow))
            rng = np.random.default_rng(4)
            for _ in range(7):
                x0, y0 = rng.uniform(4.2, 7.0), rng.uniform(2.9, 4.0)
                x1, y1 = x0 + rng.uniform(-1, 1), y0 + rng.uniform(-0.6, 0.9)
                ax.plot([x0, x1], [y0, y1], color=AMBER, lw=0.9, alpha=0.8)
            ax.annotate("", xy=(2.2, 6.0), xytext=(5.0, 4.1),
                        arrowprops=dict(color=AMBER, **arrow))
            ax.text(8.2, 3.4, "depolarised\nby multiple\nscattering: VH",
                    fontsize=7.8, color=TEAL, ha="center")

        else:
            ax.fill_between([0.5, 9.5], 0.6, 1.2, color="#1A5BAB", alpha=0.35)
            for cx in (5.2, 6.8):
                ax.plot([cx, cx], [1.2, 4.2], color="#6b4a2f", lw=3.0)
                ax.add_patch(plt.Circle((cx, 4.7), 0.85, color=BRIGHT, alpha=0.30))
            ax.annotate("", xy=(4.0, 1.2), xytext=(1.5, 6.1),
                        arrowprops=dict(color=AMBER, **arrow))
            ax.annotate("", xy=(5.15, 2.4), xytext=(4.0, 1.2),
                        arrowprops=dict(color=AMBER, **arrow))
            ax.annotate("", xy=(1.6, 6.0), xytext=(5.15, 2.4),
                        arrowprops=dict(color=RED, lw=2.2, arrowstyle="->"))
            ax.text(8.0, 2.6, "returns along\nits incoming path:\nvery bright",
                    fontsize=7.8, color=RED, ha="center")

    fig.suptitle("What radar measures is arrangement, not composition",
                 fontsize=11, color=INK, y=1.04)
    save(fig, "radar-scattering")


# ---------------------------------------------------------------------------
# 10. Surface model against terrain model
# ---------------------------------------------------------------------------
def dsm_vs_dtm():
    """The canopy offset trap that excludes the tallest mangrove."""
    x = np.linspace(0, 100, 500)

    ground = np.where(x < 55, 1.0 + 0.02 * x, 1.0 + 0.02 * 55 + 0.9 * (x - 55))
    ground = np.clip(ground, 0, None)

    canopy = np.zeros_like(x)
    canopy += 25 * np.exp(-((x - 30) ** 2) / (2 * 13 ** 2))     # mature mangrove
    canopy += 6 * np.exp(-((x - 62) ** 2) / (2 * 6 ** 2))       # young regrowth
    canopy += 22 * np.exp(-((x - 85) ** 2) / (2 * 10 ** 2))     # upland forest
    surface = ground + canopy

    fig, ax = plt.subplots(figsize=(9.5, 4.4))

    ax.fill_between(x, 0, ground, color="#8a7a5e", alpha=0.55, label="Ground (DTM)")
    ax.fill_between(x, ground, surface, color=BRIGHT, alpha=0.35)
    ax.plot(x, surface, color=TEAL, lw=2.2, label="What the DEM records (DSM)")
    ax.plot(x, ground, color="#6b5a3e", lw=1.8, ls="--")

    ax.axhline(10, color=RED, lw=1.6, ls=":")
    ax.text(2, 11.2, "naive rule: elevation < 10 m", fontsize=8.5, color=RED)

    ax.annotate("mature mangrove\nDSM reports ~26 m\nEXCLUDED by the rule",
                xy=(30, 26), xytext=(20, 40), fontsize=8, ha="center", color=RED,
                arrowprops=dict(arrowstyle="->", color=RED, lw=1.1))
    ax.annotate("young regrowth\nDSM reports ~8 m\nkept",
                xy=(62, 8.5), xytext=(60, 33), fontsize=8, ha="center", color=TEAL,
                arrowprops=dict(arrowstyle="->", color=TEAL, lw=1.1))
    ax.annotate("upland forest\ncorrectly excluded",
                xy=(85, 49), xytext=(88, 20), fontsize=8, ha="center", color=MUTED,
                arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))

    ax.set_xlabel("Distance inland (arbitrary units)")
    ax.set_ylabel("Height above sea level (m)")
    ax.set_ylim(0, 56)
    ax.set_xlim(0, 100)
    ax.legend(frameon=False, loc="upper left", fontsize=8.5)
    ax.set_title("Every global DEM is a surface model, and the tallest mangrove pays for it",
                 fontsize=10.5, color=INK, pad=14, loc="left")
    save(fig, "dsm-vs-dtm")


# ---------------------------------------------------------------------------
# 11. Palette comparison
# ---------------------------------------------------------------------------
def palette_comparison():
    """Why rainbow misleads, shown rather than asserted.

    The same gradient rendered four ways. The lightness curve underneath is
    what decides readability: a good palette rises steadily, so equal steps
    in the data look equal to the eye and survive greyscale printing.
    Rainbow reverses direction repeatedly and does neither.
    """
    from matplotlib import colormaps
    from matplotlib.colors import to_rgb

    grad = np.linspace(0, 1, 512).reshape(1, -1)
    names = ["jet", "viridis", "magma", "YlGnBu"]
    labels = ["jet (rainbow)", "viridis", "magma", "YlGnBu"]

    fig, axes = plt.subplots(3, 4, figsize=(11, 4.6),
                             gridspec_kw={"height_ratios": [1, 1, 1.6],
                                          "hspace": 0.5})

    for j, (name, label) in enumerate(zip(names, labels)):
        cmap = colormaps[name]

        axes[0, j].imshow(grad, aspect="auto", cmap=cmap)
        axes[0, j].set_title(label, fontsize=9.5, color=INK, pad=6)
        axes[0, j].set_xticks([]); axes[0, j].set_yticks([])

        # Standard luminance weighting, which is what a greyscale printer and
        # a colour blind reader both effectively see.
        rgb = np.array([to_rgb(cmap(v)) for v in np.linspace(0, 1, 256)])
        light = 0.2126 * rgb[:, 0] + 0.7152 * rgb[:, 1] + 0.0722 * rgb[:, 2]

        axes[1, j].imshow(light.reshape(1, -1), aspect="auto", cmap="gray",
                          vmin=0, vmax=1)
        axes[1, j].set_xticks([]); axes[1, j].set_yticks([])
        if j == 0:
            axes[1, j].set_ylabel("in greyscale", fontsize=7.5, color=MUTED)

        axes[2, j].plot(np.linspace(0, 1, 256), light, color=TEAL, lw=1.8)
        axes[2, j].set_ylim(0, 1)
        axes[2, j].set_xticks([]); axes[2, j].set_yticks([0, 0.5, 1])
        axes[2, j].tick_params(labelsize=7)
        if j == 0:
            axes[2, j].set_ylabel("lightness", fontsize=7.5, color=MUTED)

        d = np.diff(light)
        reversals = int(np.sum(np.sign(d[:-1]) != np.sign(d[1:])))
        axes[2, j].text(0.5, 0.08, f"{reversals} direction changes",
                        transform=axes[2, j].transAxes, ha="center",
                        fontsize=7.5,
                        color=RED if reversals > 4 else TEAL)

    fig.suptitle("A palette is readable when its lightness rises steadily. "
                 "Rainbow reverses, so equal steps in the data look unequal.",
                 fontsize=10.5, color=INK, y=1.03)
    save(fig, "palette-comparison")


if __name__ == "__main__":
    print("Generating figures into images/")
    spectral_signatures()
    ndvi_saturation()
    speckle_filter()
    ent = glcm_texture()
    nn = block_cv()
    cm = confusion_matrix()
    filter_funnel()
    obs = compositing()
    radar_scattering()
    dsm_vs_dtm()
    palette_comparison()
    print("\nComputed values now quoted in the chapters:")
    print(f"  Clear observations per pixel in the composite: {obs[0]} to {obs[1]}")
    print(f"  GLCM entropy, plantation {ent[0]:.2f} vs natural {ent[1]:.2f}")
    print(f"  Mean distance to nearest test point: random {nn[0]:.2f}, block {nn[1]:.2f}")
    print(f"  Confusion matrix: overall {cm[0]*100:.1f}%, "
          f"mangrove producer {cm[1]*100:.1f}%, user {cm[2]*100:.1f}%")
