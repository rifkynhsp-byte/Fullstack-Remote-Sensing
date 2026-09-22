"""
booklib.py
==========

The shared Python library behind the executed chunks in the chapters.

Why this file exists
--------------------
The book renders Python at build time, in two languages, so the same
computation appears twice: once in ``en/`` and once in ``id/``. Without a
shared library, every chunk would carry its own copy of the palette, the
reflectance table and the plotting defaults, and the English and Indonesian
editions would drift apart one commit at a time until they disagreed about a
number.

So the chapters hold the teaching and the call; this file holds the data and
the machinery. A chunk in a chapter should be short enough to read in one
pass, because a reader is meant to read it, not scroll past it.

What it deliberately does not do
--------------------------------
It never contacts Earth Engine, or any network at render time. Every number
below is either published, synthetic, or computed. A chapter that needed
credentials to render would be a chapter only its author could build, and the
first person to fork this book would find it broken.

The reflectance values are the same ones the interactive widget in
``interactive/spectral-explorer.qmd`` uses. When one changes, change both:
a reader who gets different answers from the chart and the code stops
trusting either.

Copied into ``en/`` and ``id/`` by ``tools/build_site.sh``. Edit this copy,
at the repository root, never the ones inside the language projects.
"""

from __future__ import annotations

import math

import numpy as np

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
# The same teal and amber the book's CSS uses. Figures that pick their own
# colours read as imported from somewhere else, which is exactly what a
# reader should not be wondering about.

TEAL = "#0f6b57"
BRIGHT = "#14a37f"
AMBER = "#c8792b"
RED = "#a4372a"
INK = "#1b1f23"
MUTED = "#8b97a3"
RULE = "#e4e0d8"
SAND = "#faf8f4"

# A categorical order chosen so neighbouring series stay distinguishable in
# greyscale as well as in colour, because some readers will print this.
SERIES = [BRIGHT, AMBER, "#3c6e9c", RED, "#7a6ea8", "#5c6773"]


# ---------------------------------------------------------------------------
# Sentinel-2 bands and representative surface reflectance
# ---------------------------------------------------------------------------

#: Band centre wavelengths in nanometres.
BANDS: dict[str, int] = {
    "B2": 490, "B3": 560, "B4": 665, "B5": 705,
    "B6": 740, "B8": 842, "B11": 1610, "B12": 2190,
}

BAND_ROLE: dict[str, str] = {
    "B2": "Blue", "B3": "Green", "B4": "Red", "B5": "Red edge 1",
    "B6": "Red edge 2", "B8": "NIR", "B11": "SWIR 1", "B12": "SWIR 2",
}

#: Representative Sentinel-2 surface reflectance per land cover class.
#: Typical published values, not a measurement of one location. Good enough to
#: reason with, and the chapters say so wherever a figure uses them.
SPECTRA: dict[str, dict[str, float]] = {
    "Healthy mangrove":   {"B2": .030, "B3": .055, "B4": .030, "B5": .075, "B6": .240, "B8": .310, "B11": .115, "B12": .050},
    "Other dense forest": {"B2": .028, "B3": .052, "B4": .029, "B5": .072, "B6": .245, "B8": .330, "B11": .135, "B12": .060},
    "Oil palm":           {"B2": .032, "B3": .060, "B4": .035, "B5": .080, "B6": .250, "B8": .345, "B11": .155, "B12": .070},
    "Open water":         {"B2": .045, "B3": .040, "B4": .025, "B5": .018, "B6": .012, "B8": .008, "B11": .004, "B12": .003},
    "Turbid water":       {"B2": .075, "B3": .090, "B4": .080, "B5": .060, "B6": .040, "B8": .028, "B11": .010, "B12": .006},
    "Tidal mudflat":      {"B2": .070, "B3": .100, "B4": .130, "B5": .150, "B6": .170, "B8": .195, "B11": .230, "B12": .190},
    "Bare soil":          {"B2": .090, "B3": .130, "B4": .180, "B5": .210, "B6": .235, "B8": .265, "B11": .330, "B12": .290},
    "Built up":           {"B2": .130, "B3": .150, "B4": .170, "B5": .180, "B6": .190, "B8": .205, "B11": .240, "B12": .220},
}

#: Indonesian labels, so the Indonesian edition's figures are in Indonesian
#: without the chunk carrying a translation table of its own.
SPECTRA_ID: dict[str, str] = {
    "Healthy mangrove": "Mangrove sehat",
    "Other dense forest": "Hutan lebat lain",
    "Oil palm": "Kelapa sawit",
    "Open water": "Air terbuka",
    "Turbid water": "Air keruh",
    "Tidal mudflat": "Lumpur pasut",
    "Bare soil": "Tanah terbuka",
    "Built up": "Terbangun",
}


def label(name: str, lang: str = "en") -> str:
    """Class name in the requested language, falling back to the key."""
    return SPECTRA_ID.get(name, name) if lang == "id" else name


def reflectance(name: str) -> np.ndarray:
    """Reflectance of one class as an array ordered like :data:`BANDS`."""
    r = SPECTRA[name]
    return np.array([r[b] for b in BANDS])


# ---------------------------------------------------------------------------
# Spectral indices
# ---------------------------------------------------------------------------

def nd(a, b):
    """Normalised difference. The shape almost every index in the book takes.

    Returns a value in [-1, 1] for non-negative inputs, which is the whole
    reason the form is used: it is comparable between scenes and sensors in a
    way a raw band ratio is not.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    return (a - b) / (a + b)


#: Index definitions, each a function of a reflectance dict.
#: Keeping the formula next to the name means a chapter can print the table
#: rather than restate it in prose that can fall out of date.
INDICES: dict[str, dict] = {
    "NDVI":  {"formula": "(NIR - Red) / (NIR + Red)",
              "f": lambda r: nd(r["B8"], r["B4"])},
    "NDWI":  {"formula": "(Green - NIR) / (Green + NIR)",
              "f": lambda r: nd(r["B3"], r["B8"])},
    "MNDWI": {"formula": "(Green - SWIR1) / (Green + SWIR1)",
              "f": lambda r: nd(r["B3"], r["B11"])},
    "NDMI":  {"formula": "(NIR - SWIR1) / (NIR + SWIR1)",
              "f": lambda r: nd(r["B8"], r["B11"])},
    "CMRI":  {"formula": "NDVI - NDWI",
              "f": lambda r: nd(r["B8"], r["B4"]) - nd(r["B3"], r["B8"])},
    "MVI":   {"formula": "(NIR - Green) / (SWIR1 - Green)",
              "f": lambda r: (r["B8"] - r["B3"]) / max(r["B11"] - r["B3"], 1e-3)},
}


def index_value(name: str, class_name: str) -> float:
    """One index over one class."""
    return float(INDICES[name]["f"](SPECTRA[class_name]))


def separability(name: str, a: str, b: str) -> float:
    """How far apart an index puts two classes.

    The crude measure on purpose: the absolute gap between the two index
    values. A reader with training data should compute a Jeffries-Matusita
    distance instead, and Chapter 15 says so. What this is for is deciding
    whether an index is worth putting in a stack at all, and for that, "these
    two land on top of each other" is the entire finding.
    """
    return abs(index_value(name, a) - index_value(name, b))


# ---------------------------------------------------------------------------
# Accuracy
# ---------------------------------------------------------------------------

def confusion_stats(matrix) -> dict:
    """Overall accuracy, kappa, and per class producer's and user's accuracy.

    ``matrix[i][j]`` is the count of reference class ``i`` predicted as class
    ``j``. Rows are truth, columns are the map. Getting that convention
    backwards silently swaps producer's and user's accuracy, which is why the
    chapters print both and name them.

    Note what this returns and what it does not. These are sample based
    accuracies for the pixels in the matrix. They are not area estimates, and
    using them as such over an unbalanced landscape is the error Chapter 17
    spends its length on.
    """
    m = np.asarray(matrix, dtype=float)
    if m.ndim != 2 or m.shape[0] != m.shape[1]:
        raise ValueError("a confusion matrix must be square")

    total = m.sum()
    if total == 0:
        raise ValueError("an empty confusion matrix has no accuracy")

    correct = np.trace(m)
    oa = correct / total

    row = m.sum(axis=1)        # reference totals
    col = m.sum(axis=0)        # map totals
    expected = float((row * col).sum()) / (total * total)
    kappa = (oa - expected) / (1 - expected) if expected != 1 else float("nan")

    with np.errstate(divide="ignore", invalid="ignore"):
        producers = np.where(row > 0, np.diag(m) / row, np.nan)
        users = np.where(col > 0, np.diag(m) / col, np.nan)
        f1 = np.where(
            (producers + users) > 0,
            2 * producers * users / (producers + users),
            np.nan,
        )

    return {
        "overall_accuracy": float(oa),
        "kappa": float(kappa),
        "producers_accuracy": producers,
        "users_accuracy": users,
        "f1": f1,
        "n": int(total),
    }


def sample_size(target_se: float, expected_accuracies, weights) -> int:
    """Olofsson's sample size for a target standard error of overall accuracy.

    ``n = (sum(W_i * S_i) / SE)^2`` with ``S_i = sqrt(U_i (1 - U_i))``.

    The reason this belongs in a book rather than in a footnote: the intuition
    that a rare class needs proportionally fewer points is exactly wrong. A
    class covering two percent of a landscape drives the variance of its own
    user's accuracy, and proportional allocation gives it almost no points to
    do that with.
    """
    u = np.asarray(expected_accuracies, dtype=float)
    w = np.asarray(weights, dtype=float)
    if u.shape != w.shape:
        raise ValueError("one expected accuracy per class weight")
    if not math.isclose(float(w.sum()), 1.0, abs_tol=1e-6):
        raise ValueError(f"class weights must sum to 1, got {w.sum():.4f}")

    s = np.sqrt(u * (1 - u))
    return int(math.ceil((float((w * s).sum()) / target_se) ** 2))


# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------

def clear_probability(cloud_fraction: float, n_scenes: int) -> float:
    """Probability that at least one of ``n_scenes`` sees a pixel clear.

    ``1 - p^n``, the independence assumption stated out loud so a reader can
    see where it fails: cloud is seasonal and spatially organised, so in a
    monsoon month the real answer is worse than this, sometimes much worse.
    Chapter 9 uses the gap between the two as the argument for composites.
    """
    if not 0 <= cloud_fraction <= 1:
        raise ValueError("cloud fraction is a probability")
    return float(1 - cloud_fraction ** max(int(n_scenes), 0))


# ---------------------------------------------------------------------------
# Time series
# ---------------------------------------------------------------------------

def synthetic_ndvi(n_years=4, per_year=24, seed=7, trend=-0.02,
                   disturbance_at=None, disturbance_size=-0.28):
    """A synthetic NDVI series with season, trend, noise and gaps.

    Synthetic on purpose. A real series would make the chapter's point about
    harmonic fitting no better, and would tie the render to a download that
    can fail, an account that can expire and a scene that can be reprocessed.

    Returns ``(t, ndvi)`` where ``t`` is in years from the start, gaps already
    removed, the way a cloud screened optical series actually arrives.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(0, n_years * per_year) / per_year

    seasonal = 0.12 * np.sin(2 * np.pi * t - 0.7)
    base = 0.74 + trend * t + seasonal
    if disturbance_at is not None:
        base = base + np.where(t >= disturbance_at, disturbance_size, 0.0)

    ndvi = np.clip(base + rng.normal(0, 0.025, t.size), -1, 1)

    # Cloud. Roughly a third of observations lost, clustered rather than
    # uniform, because that is how a wet season behaves.
    wet = 0.45 + 0.35 * (np.sin(2 * np.pi * t + 1.2) > 0)
    keep = rng.random(t.size) > (1 - wet) * 0.9
    return t[keep], ndvi[keep]


def harmonic_design(t, order=2):
    """Design matrix for a harmonic regression: intercept, trend, sin/cos pairs."""
    t = np.asarray(t, dtype=float)
    cols = [np.ones_like(t), t]
    for k in range(1, order + 1):
        cols.append(np.sin(2 * np.pi * k * t))
        cols.append(np.cos(2 * np.pi * k * t))
    return np.column_stack(cols)


def harmonic_fit(t, y, order=2):
    """Least squares harmonic fit. Returns ``(coefficients, predict)``.

    This is the model Earth Engine's ``linearRegression`` reducer fits over an
    image collection, written small enough to read. Understanding it here is
    what makes the server side version legible later.
    """
    X = harmonic_design(t, order)
    coef, *_ = np.linalg.lstsq(X, np.asarray(y, dtype=float), rcond=None)

    def predict(tt):
        return harmonic_design(tt, order) @ coef

    return coef, predict


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def mpl_style():
    """Apply the book's matplotlib defaults. Call once per chunk that plots."""
    import matplotlib as mpl

    mpl.rcParams.update({
        "figure.dpi": 130,
        "savefig.dpi": 130,
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
        "axes.labelsize": 9,
        "axes.edgecolor": "#c9c4bb",
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": "#ececec",
        "grid.linewidth": 0.8,
        "legend.frameon": False,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.labelcolor": "#5c6773",
        "axes.prop_cycle": __import__("cycler").cycler(color=SERIES),
        "figure.facecolor": "white",
        "savefig.bbox": "tight",
    })


_PLOTLY_LAYOUT = dict(
    template="simple_white",
    font=dict(family="Source Sans 3, system-ui, sans-serif", size=12, color=INK),
    margin=dict(l=56, r=16, t=34, b=48),
    colorway=SERIES,
    hoverlabel=dict(font_size=12, font_family="Source Sans 3, system-ui, sans-serif"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
)


def show(fig, height=380):
    """Display a Plotly figure in the page as a hoverable chart.

    It displays rather than returns, deliberately. A returned value is only
    rendered when it is the cell's last expression, so a chunk that plotted
    and then printed a number silently lost its chart. That happened once,
    in Chapter 21, and it is not a mistake worth leaving available.

    Quarto's own Plotly path loads a 2019 build of plotly.js through RequireJS.
    Going through ``to_html`` instead pins a current build from the CDN, drops
    the RequireJS shim, and lets the chart be configured properly: no
    editing toolbar, no screenshot button, responsive width.

    ``include_plotlyjs="cdn"`` emits a script tag per figure. The browser
    fetches the library once and serves the rest from cache, and plotly.js is
    written to tolerate being requested twice.
    """
    from IPython.display import HTML, display

    fig.update_layout(height=height, **_PLOTLY_LAYOUT)
    html = fig.to_html(
        include_plotlyjs="cdn",
        full_html=False,
        default_width="100%",
        default_height=f"{height}px",
        config={
            "displaylogo": False,
            "responsive": True,
            "modeBarButtonsToRemove": ["select2d", "lasso2d", "toImage", "autoScale2d"],
        },
    )
    display(HTML(html))


def table(df, caption=None):
    """Display a DataFrame as the book's own table rather than pandas' default.

    pandas' HTML carries its own borders and fonts and looks like output from
    another document. This hands Quarto a plain table it can style with the
    book's CSS.

    Displays rather than returns, for the reason given in :func:`show`.
    """
    from IPython.display import HTML, display

    html = df.to_html(index=False, border=0, escape=False,
                      classes="book-table", float_format=lambda v: f"{v:,.3f}")
    if caption:
        html = f'<div class="book-table-wrap">{html}' \
               f'<p class="book-table-note">{caption}</p></div>'
    display(HTML(html))
