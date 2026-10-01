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


# ---- Click guides: one screen per module, the buttons to press outlined in red
# and numbered in the order you press them.
RED = "#d62728"

CARDS = {
    # module: (card title, [(field label, click number or None)], run button label, run number,
    #          area click number, unit click number, map note)
    "Data": ("Data · catalogue", [("Group ▾   e.g. Rainfall", 2), ("Layer ▾   e.g. CHIRPS daily", 3),
                                  ("Date range   2023-01-01 → 2023-12-31", 4)],
             "Tampilkan lapisan", 5, 1, None, "layer + its mean over your area"),
    "Citra": ("Citra · clean Sentinel-2 image", [("Dates   2024-06-01 → 2024-09-30", 2),
                                                  ("Method ▾   Cloud Score Plus", 3),
                                                  ("Bands ▾   natural colour / NIR / SWIR", 4),
                                                  ("Index ▾   NDVI (optional)", None)],
              "Tampilkan", 5, 1, None, "cloud-free composite, image count"),
    "Tutupan": ("Tutupan · your own land cover", [("Source ▾   Sentinel-2 composite", 2),
                                                  ("Tambah class  ·  Tandai → click map", 3),
                                                  ("Algorithm ▾   Random Forest", 4),
                                                  ("Min. mapping unit ━●━", None)],
                "Latih dan klasifikasi", 5, 1, None, "map, accuracy, kappa, area per class"),
    "Model": ("Model · ready-made models", [("Mode ▾   10-class / Dynamic World / height", 2),
                                           ("Embedding year ▾   2024", 3)],
              "Jalankan", 4, 1, None, "land cover or canopy height, no samples"),
    "Deret": ("Deret · time series", [("Mode ▾   harmonic / LandTrendr / age / CCDC", 2),
                                      ("Years   2016 → 2024", 3),
                                      ("Change threshold ━●━", None)],
              "Jalankan analisis", 4, 1, None, "year of change, age, seasonal amplitude"),
    "Ubah": ("Ubah · change between two dates", [("Method ▾   Dynamic World transitions", 2),
                                                 ("Period A   2018", 3), ("Period B   2024", 3)],
             "Jalankan analisis", 4, 1, None, "hectares gained and lost"),
    "Banjir": ("Banjir · flood", [("Before period   a month before", 4),
                                  ("After period    days after the event", 4),
                                  ("Orbit ▾  ·  DEM ▾  ·  HAND ━●━ 15 m", 5)],
               "Jalankan analisis", 6, 1, 2, "flooded ha, people, buildings per unit"),
    "Api": ("Api · fire", [("Before period   June–July", 3), ("After period    Oct–Nov", 3)],
            "Jalankan analisis", 4, 1, None, "dNBR severity, hotspots, burned peat"),
    "Rawan": ("Rawan · hazard susceptibility", [("Hazard ▾   landslide", 2),
                                                ("Tandai RAWAN → click hazardous places", 3),
                                                ("Tandai AMAN → click safe places", 3),
                                                ("Trees ━●━ 120", None)],
              "Latih dari titik manual", 4, 1, None, "susceptibility, accuracy, people exposed"),
}


def badge(ax, x, y, n):
    ax.add_patch(plt.Circle((x, y), 0.26, color=RED, zorder=30))
    ax.text(x, y, str(n), color="white", fontsize=8, weight="bold", ha="center",
            va="center", zorder=31)


def outline(ax, x, y, w, h):
    ax.add_patch(FancyBboxPatch((x - 0.05, y - 0.05), w + 0.1, h + 0.1,
                                boxstyle="round,pad=0.02,rounding_size=0.1", fc="none",
                                ec=RED, lw=2.2, zorder=25))


def click_figure(module):
    title, fields, run, run_n, area_n, unit_n, note = CARDS[module]
    fig, ax = plt.subplots(figsize=(11, 5.6))
    ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.set_axis_off()
    box(ax, 0.2, 0.2, 6.6, 8.6, fc="#f7f8fa")
    # step 1: area
    ax.text(0.45, 8.3, "STEP 1 · Area of interest", fontsize=8, weight="bold", color="#2a78d6")
    for i, t in enumerate(["Draw", "Admin", "Paste", "Asset"]):
        box(ax, 0.45 + i * 1.55, 7.45, 1.4, 0.55, t, fc="#eef4fb", fs=7, ha="center")
    outline(ax, 0.45 + 1.55, 7.45, 1.4, 0.55); badge(ax, 0.45 + 1.55, 8.0, area_n)
    # step 2: reporting unit
    ax.text(0.45, 7.0, "STEP 2 · Reporting unit", fontsize=8, weight="bold", color="#2a78d6")
    box(ax, 0.45, 6.25, 6.1, 0.5, "Province · Regency · Subdistrict · Village ▾", fc="#eef4fb", fs=7)
    if unit_n:
        outline(ax, 0.45, 6.25, 6.1, 0.5); badge(ax, 6.55, 6.75, unit_n)
    # step 3: modules
    ax.text(0.45, 5.8, "STEP 3 · Module", fontsize=8, weight="bold", color="#2a78d6")
    mod_n = 2 if unit_n is None else 3
    for i, m in enumerate(MODULES):
        r, c = divmod(i, 5)
        x, y = 0.45 + c * 1.24, 5.0 - r * 0.62
        on = m == module
        box(ax, x, y, 1.14, 0.48, m, fc="#1b7837" if on else "#ffffff",
            color="#ffffff" if on else "#1f2933", fs=7, ha="center")
        if on:
            outline(ax, x, y, 1.14, 0.48); badge(ax, x + 1.14, y + 0.48, mod_n)
    # module card
    # Fields carrying the same group number are one step (e.g. both date periods).
    box(ax, 0.45, 0.4, 6.1, 3.85, fc="#ffffff")
    ax.text(0.65, 3.9, title, fontsize=8.5, weight="bold")
    step, group = mod_n, None
    for k, (label, n) in enumerate(fields):
        y = 3.2 - k * 0.6
        box(ax, 0.65, y, 5.7, 0.45, label, fc="#eef4fb", fs=6.8)
        if n is not None:
            if n != group:
                step, group = step + 1, n
            outline(ax, 0.65, y, 5.7, 0.45); badge(ax, 6.35, y + 0.45, step)
    box(ax, 0.65, 0.6, 2.9, 0.5, run, fc="#2a78d6", color="#ffffff", fs=7.5, ha="center")
    outline(ax, 0.65, 0.6, 2.9, 0.5); badge(ax, 3.55, 1.1, step + 1)
    # map pane
    box(ax, 7.1, 0.2, 8.7, 8.6, fc="#dfe9e1")
    ax.add_patch(plt.Polygon([[8.6, 2.0], [12.2, 1.6], [14.6, 4.2], [13.2, 7.4], [9.4, 6.8]],
                             fc="#c7e1cc", ec="#2a78d6", lw=1.5, ls="--"))
    ax.text(11.6, 4.5, "your area", ha="center", fontsize=8, color="#2a78d6")
    box(ax, 12.7, 7.3, 2.9, 1.3, "Legend", fc="#ffffff", fs=7.5, ha="center")
    box(ax, 7.4, 0.45, 8.1, 0.55, "Result → " + note, fc="#ffffff", fs=7.5)
    ax.text(0.2, 8.95, f"IJB · {module}: press the red buttons in the order of the numbers",
            fontsize=10, weight="bold", va="bottom")
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
    ] + [{"kind": "figure", "name": f"p6-click-{m.lower()}", "figure": (lambda m=m: click_figure(m)),
          "caption": f"IJB {m}: the buttons to press, in order."} for m in CARDS]


if __name__ == "__main__":
    print(guide_table())
