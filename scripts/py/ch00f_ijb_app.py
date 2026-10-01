#| title: IJB at a glance (Python)
#| description: Drawings of the IJB application: its layout, the three steps every analysis follows, and which module answers which question. No Earth Engine code is needed to use the app; this script only draws the guide figures.

"""
PRINCIPLES P6 | A map of the app, drawn for the guide.

IJB is used by clicking, not by coding. These figures are drawn from the
app's actual structure: the side panel with its three steps, the ten module
buttons, and the map with its legend and status bar.
"""

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch

MODULES = ["Data", "Citra", "Model", "Tutupan", "Deret",
           "Ubah", "Banjir", "Api", "Rawan", "Toolbox"]


def box(ax, x, y, w, h, text="", fc="#ffffff", ec="#9aa5b1", fs=8, weight="normal",
        color="#1f2933", ha="left"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=fc, ec=ec, lw=1))
    if text:
        tx = x + 0.12 if ha == "left" else x + w / 2
        ax.text(tx, y + h / 2, text, fontsize=fs, va="center", ha=ha, weight=weight,
                color=color)


def layout_figure():
    fig, ax = plt.subplots(figsize=(11, 6.2))
    ax.set_xlim(0, 16); ax.set_ylim(0, 10); ax.set_axis_off()
    # side panel
    box(ax, 0.2, 0.2, 5.4, 9.6, fc="#f7f8fa")
    box(ax, 0.4, 8.6, 5.0, 1.0, "IJB  ·  disasters, land cover, time series",
        fc="#ffffff", fs=8, weight="bold")
    box(ax, 0.4, 6.7, 5.0, 1.7, fc="#ffffff")
    ax.text(0.55, 8.15, "STEP 1  ·  Area of interest", fontsize=8, weight="bold", color="#2a78d6")
    for i, t in enumerate(["Draw", "Admin", "Paste", "Asset"]):
        box(ax, 0.55 + i * 1.2, 7.0, 1.1, 0.6, t, fc="#eef4fb", fs=6.5, ha="center")
    box(ax, 0.4, 5.4, 5.0, 1.1, fc="#ffffff")
    ax.text(0.55, 6.2, "STEP 2  ·  Reporting unit", fontsize=8, weight="bold", color="#2a78d6")
    box(ax, 0.55, 5.55, 4.7, 0.45, "Province · Regency · Subdistrict · Village ▾",
        fc="#eef4fb", fs=6.5)
    box(ax, 0.4, 3.3, 5.0, 1.9, fc="#ffffff")
    ax.text(0.55, 4.9, "STEP 3  ·  Analysis modules", fontsize=8, weight="bold", color="#2a78d6")
    for i, m in enumerate(MODULES):
        r, c = divmod(i, 5)
        box(ax, 0.55 + c * 0.96, 4.15 - r * 0.6, 0.9, 0.45, m,
            fc="#1b7837" if m == "Banjir" else "#ffffff",
            color="#ffffff" if m == "Banjir" else "#1f2933", fs=6.5, ha="center")
    box(ax, 0.4, 0.4, 5.0, 2.7, fc="#ffffff")
    ax.text(0.55, 2.8, "Module card (here: Banjir / flood)", fontsize=8, weight="bold")
    for k, t in enumerate(["Before period   2024-12-01 → 2024-12-31",
                           "After period    2025-01-01 → 2025-01-31",
                           "Orbit ▾  ·  DEM ▾  ·  HAND ━●━ 15 m"]):
        ax.text(0.6, 2.35 - k * 0.42, t, fontsize=6.8, family="monospace")
    box(ax, 0.6, 0.6, 2.0, 0.45, "Run analysis", fc="#2a78d6", color="#ffffff", fs=7,
        ha="center")
    ax.text(2.8, 0.83, "→ map layers, legend and numbers", fontsize=6.8, color="#6b7680")
    # map
    box(ax, 5.9, 0.2, 9.9, 9.6, fc="#dfe9e1")
    ax.text(10.85, 5.2, "MAP\n(satellite basemap, your area outlined,\nresult layers stacked on top)",
            ha="center", fontsize=9, color="#4b5563")
    box(ax, 12.6, 6.9, 3.0, 2.6, "Legend", fc="#ffffff", fs=8, ha="center")
    box(ax, 6.2, 0.5, 6.0, 0.6, "Status bar: what the app is doing now", fc="#ffffff", fs=7)
    ax.set_title("IJB: the side panel walks you through three steps; the map shows "
                 "every result", loc="left", fontsize=10)
    return fig


def chain_figure():
    fig, ax = plt.subplots(figsize=(11, 2.6))
    ax.set_xlim(0, 16); ax.set_ylim(0, 3); ax.set_axis_off()
    steps = ["Citra\nSentinel-2 composite", "Toolbox\nindex: (NIR−red)/(NIR+red)",
             "Toolbox\nOtsu threshold", "Toolbox\nsieve, small patches out",
             "Toolbox\nraster → vector", "Toolbox\nzonal statistics\nper village"]
    for i, t in enumerate(steps):
        box(ax, 0.2 + i * 2.65, 0.8, 2.3, 1.5, t, fc="#eef4fb" if i else "#ffffff", fs=7.5,
            ha="center")
        if i:
            ax.annotate("", (0.2 + i * 2.65, 1.55), (0.2 + i * 2.65 - 0.33, 1.55),
                        arrowprops={"arrowstyle": "-|>", "color": "#2a78d6"})
    ax.text(0.2, 0.35, "Each result becomes the active layer, so the next tool works on it: "
            "a whole workflow without one line of code.", fontsize=8, color="#4b5563")
    return fig


def guide_table():
    return pd.DataFrame([
        ("I need a basic layer (rainfall, buildings, peat, population...) for my area", "Data", "43 public datasets in 13 groups, statistics per reporting unit"),
        ("I need a clean satellite image without clouds", "Citra", "five ways to build a Sentinel-2 composite, band combinations and indices"),
        ("What is the land cover here, by my own classes?", "Tutupan", "mark examples, choose an algorithm, get a map with accuracy and areas"),
        ("I want a ready-made land-cover map or a canopy height map", "Model", "the author's 10-class model, Dynamic World, or canopy height trained on GEDI"),
        ("When did this place change, or how old is this plantation?", "Deret", "harmonics, LandTrendr, stand age, CCDC breakpoints"),
        ("What changed between two dates?", "Ubah", "index difference, Dynamic World transitions, double classification, trend"),
        ("Where did it flood, and who was affected?", "Banjir", "Sentinel-1 change with Otsu threshold, HAND, slope and permanent-water filters; people and buildings"),
        ("What burned, how badly, and on peat?", "Api", "dNBR in four severity classes, hotspots, burned peat and its thickness"),
        ("Where is landslide or flood risk highest?", "Rawan", "random forest on embeddings and terrain, from your points or the NASA landslide catalog"),
        ("I need to combine steps: threshold, clean up, vectorise, summarise", "Toolbox", "expression calculator, Otsu, raster ↔ vector, zonal statistics, SNIC, morphology"),
    ], columns=["question", "module", "what it does"])


def products():
    return [
        {"kind": "figure", "name": "p6-layout", "figure": layout_figure,
         "caption": "The IJB screen, drawn from the app's structure: area, reporting unit and "
                    "module on the left, the map on the right."},
        {"kind": "table", "name": "p6-guide", "data": guide_table,
         "caption": "Which module to open for which question."},
        {"kind": "figure", "name": "p6-chain", "figure": chain_figure,
         "caption": "Chaining tools: every result becomes the active layer for the next one."},
    ]


if __name__ == "__main__":
    print(guide_table())
