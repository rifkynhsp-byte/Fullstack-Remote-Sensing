#| title: IJB at a glance (Python)
#| description: Drawings of the IJB application for the click-by-click guide: the screen, and for every module the card before you press its button and what appears after. No code is needed to use the app; this script only draws the guide figures.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
PRINCIPLES P6 | A map of the app, drawn for the guide.

IJB is used by clicking, not by coding. The screens below copy the app's real
labels (the app is in Bahasa Indonesia), its card layout, default values and
result cards. Buttons to press are outlined in red and numbered in order.
The map on each "after" screen is a real result made in this book with the
same method, not a screenshot of the app.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch

IMAGES = Path(__file__).resolve().parents[2] / "images" / "real"
MODULES = ["Data", "Citra", "Model", "Tutupan", "Deret",
           "Ubah", "Banjir", "Api", "Rawan", "Toolbox"]
TEAL, INK, GREY, LINE, FILL = "#0f8b78", "#1f2933", "#7b8794", "#cbd2d9", "#f1f3f5"
RED = "#d62728"


def box(ax, x, y, w, h, text="", fc="#ffffff", ec=LINE, fs=8, weight="normal",
        color=INK, ha="center", lw=1):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.06",
                                fc=fc, ec=ec, lw=lw))
    if text:
        tx = x + 0.15 if ha == "left" else x + w / 2
        ax.text(tx, y + h / 2, text, fontsize=fs, va="center", ha=ha, weight=weight,
                color=color)


def badge(ax, x, y, n):
    ax.add_patch(plt.Circle((x, y), 0.24, color=RED, zorder=30))
    ax.text(x, y, str(n), color="white", fontsize=8, weight="bold", ha="center",
            va="center", zorder=31)


def outline(ax, x, y, w, h):
    ax.add_patch(FancyBboxPatch((x - 0.06, y - 0.06), w + 0.12, h + 0.12,
                                boxstyle="round,pad=0.01,rounding_size=0.08", fc="none",
                                ec=RED, lw=2.2, zorder=25))


# Each module card as it appears in the app: section label, title, description,
# fields (label, kind, value, click group) and the button. Values are the app's
# defaults or a typical setting. Kinds: select, date, slider, button.
CARDS = {
    "Data": ("KATALOG", "Penjelajah Data", "Seluruh dataset yang terpasang. Tampilkan di AOI, unduh statistik per wilayah.",
             [("Kelompok", "select", "Curah hujan", 1),
              ("Lapisan", "select", "CHIRPS harian, akumulasi periode", 2),
              ("Rentang tanggal untuk lapisan deret waktu", "date", ("2023-01-01", "2023-12-31"), 3)],
             "Tampilkan lapisan", ["rerata di AOI", "jenis"]),
    "Citra": ("CITRA", "Komposit Sentinel-2", "Lima cara menyusun citra terbaik dari seluruh rentang tanggal.",
              [("Metode komposit", "select", "Cloud Score Plus (terbaik)", 1),
               ("Rentang tanggal", "date", ("2025-01-01", "2025-12-31"), 2),
               ("Batas awan per scene, persen", "slider", "60", None),
               ("Ambang Cloud Score Plus", "slider", "0.60", None),
               ("Kombinasi band", "select", "Warna alami", 3),
               ("Indeks", "select", "(tanpa indeks)", None)],
              "Susun komposit", ["citra tersedia", "piksel bersih"]),
    "Model": ("MODEL", "Klasifikasi dan Tinggi Tajuk", "Model 10 kelas dipanggil langsung dari aset; tinggi tajuk dilatih dari GEDI.",
              [("Mode", "select", "Tinggi tajuk dari GEDI", 1),
               ("Tahun embedding", "select", "2024", 2),
               ("Unit pemetaan minimum, piksel", "slider", "10", None),
               ("Rentang tembakan GEDI", "date", ("2019-04-01", "2023-12-31"), None),
               ("Jumlah pohon regresi", "slider", "150", None)],
              "Jalankan model", ["kelas dominan", "luas kelas dominan", "korelasi GEDI", "tinggi rerata"]),
    "Tutupan": ("ANALISIS", "Klasifikasi Tutupan Lahan", "Tentukan kelas sendiri, tandai contoh, latih, baca akurasi dan luas.",
                [("Sumber data", "select", "Sentinel-2 komposit", 1),
                 ("Algoritma", "select", "Random Forest", 2),
                 ("Unit pemetaan minimum, piksel", "slider", "0", None),
                 ("Kelas  ·  nama kelas", "button", "Tambah", 3),
                 ("hutan  ·  sawah  ·  permukiman  ·  air", "button", "Tandai → klik peta", 4)],
                "Latih dan klasifikasi", ["akurasi keseluruhan", "kappa"]),
    "Deret": ("DERET WAKTU", "Harmonik dan Titik Patah", "Harmonik memisahkan musim dari tren; LandTrendr memberi tahun gangguan dan umur.",
              [("Mode", "select", "Umur tegakan atau tanaman", 1),
               ("Rentang tahun", "date", ("1990", "2023"), 2),
               ("Jumlah harmonik", "slider", "2", None),
               ("Ambang magnitudo perubahan", "slider", "0.20", None)],
              "Jalankan analisis", ["tahun gangguan dominan", "luas terganggu", "umur rerata", "amplitudo musiman"]),
    "Ubah": ("ANALISIS", "Deteksi Perubahan", "Empat metode. Untuk waktu kejadian yang presisi, gunakan modul Deret.",
             [("Metode", "select", "Selisih indeks", 1),
              ("Indeks", "select", "NDVI", None),
              ("Periode pertama", "date", ("2019-01-01", "2019-12-31"), 2),
              ("Periode kedua", "date", ("2024-01-01", "2024-12-31"), 2),
              ("Ambang batas perubahan", "slider", "0.20", None)],
             "Jalankan deteksi", ["hektar bertambah", "hektar berkurang"]),
    "Banjir": ("KEBENCANAAN", "Pemetaan Banjir", "Perubahan hamburan balik Sentinel-1 dengan ambang Otsu, disaring lereng, air permanen, dan HAND.",
               [("Periode sebelum kejadian", "date", ("2025-09-01", "2025-10-31"), 1),
                ("Periode saat atau sesudah", "date", ("2025-11-26", "2025-11-30"), 1),
                ("Arah orbit", "select", "DESCENDING", 2),
                ("Model elevasi", "select", "FABDEM", None),
                ("Batas HAND, meter di atas drainase", "slider", "15", 3)],
               "Jalankan analisis", ["hektar tergenang", "jiwa terpapar", "bangunan", "cocok riwayat"]),
    "Api": ("KEBENCANAAN", "Kebakaran Hutan dan Lahan", "Selisih NBR dikelaskan menjadi empat tingkat, ditumpangkan dengan sebaran dan ketebalan gambut.",
            [("Periode sebelum", "date", ("2015-06-01", "2015-07-31"), 1),
             ("Periode sesudah", "date", ("2015-10-01", "2015-11-30"), 1)],
            "Jalankan analisis", ["hektar terbakar", "titik panas", "hektar gambut", "tebal gambut rerata"]),
    "Rawan": ("KEBENCANAAN", "Kerawanan Berbasis Machine Learning", "Random forest di atas Satellite Embedding ditambah lereng, elevasi, TWI, HAND, hujan, tanah.",
              [("Jenis bahaya", "select", "Longsor", 1),
               ("Tahun embedding", "select", "2024", None),
               ("Model elevasi", "select", "SRTM", None),
               ("Jumlah pohon", "slider", "120", None),
               ("Titik latih manual", "button", "Tandai RAWAN → klik peta", 2),
               ("", "button", "Tandai AMAN → klik peta", 3)],
              "Latih dari titik manual", ["akurasi validasi", "kappa", "hektar rawan tinggi", "jiwa di zona rawan"]),
}
# The legend each module puts on the map, copied from the app's code:
# ("ramp", title, palette, min, max) or ("class", title, names, colours).
LEGEND = {
    "Data": ("ramp", "CHIRPS harian, akumulasi periode",
             ["#ffffff", "#c7e9b4", "#7fcdbb", "#41b6c4", "#2c7fb8", "#253494"], 0, 3000),
    "Citra": None,                                   # true colour: no legend
    "Model": ("ramp", "Tinggi tajuk, meter",
              ["#ffffcc", "#c2e699", "#78c679", "#31a354", "#006837"], 0, 35),
    "Tutupan": ("class", "Tutupan lahan", ["hutan", "sawah", "permukiman", "air"],
                ["#1a9850", "#fee08b", "#d73027", "#2c7fb8"]),
    "Deret": ("ramp", "Umur tegakan, tahun", ["#fee08b", "#a6d96a", "#1a9850", "#006837"], 0, 25),
    "Ubah": ("ramp", "Selisih NDVI", ["#c4281b", "#f5f5f5", "#397d49"], -0.5, 0.5),
    "Banjir": ("class", "Banjir", ["Area tergenang"], ["#0b2f6b"]),
    "Api": ("class", "Keparahan (dNBR)", ["Rendah", "Sedang rendah", "Sedang tinggi", "Tinggi"],
            ["#ffe066", "#ff9f1c", "#e63946", "#7d1128"]),
    "Rawan": ("ramp", "Indeks kerawanan", ["#1a9850", "#a6d96a", "#ffffbf", "#fdae61", "#d73027"], 0, 1),
}
TEXT = {
    "en": {"before": "1 · Set the card and press the button (red, in order)",
           "after": "2 · What appears after you press",
           "metrics": "Result cards: the numbers fill in here",
           "map": "Map: the result layer is added over your area, with this legend",
           "here": "the result layer appears here", "own": "(colours follow your own classes)",
           "screen": "The IJB screen (labels as in the app)"},
    "id": {"before": "1 · Isi kartu lalu tekan tombol (merah, sesuai urutan)",
           "after": "2 · Yang muncul setelah tombol ditekan",
           "metrics": "Kartu hasil: angka muncul di sini",
           "map": "Peta: lapisan hasil ditambahkan di atas wilayah Anda, dengan legenda ini",
           "here": "lapisan hasil tampil di sini", "own": "(warna mengikuti kelas Anda sendiri)",
           "screen": "Layar IJB (label sesuai aplikasi)"},
}


def control(ax, x, y, w, kind, value):
    """One input as the app draws it; returns its height."""
    h = 0.5
    if kind == "select":
        box(ax, x, y, w, h, value, fc=FILL, fs=7, weight="bold")
        ax.text(x + w - 0.2, y + h / 2, "⇕", fontsize=8, ha="center", va="center", color=GREY)
    elif kind == "date":
        box(ax, x, y, w / 2 - 0.02, h, value[0], fs=7, ha="left")
        box(ax, x + w / 2 + 0.02, y, w / 2 - 0.02, h, value[1], fs=7, ha="left")
    elif kind == "slider":
        ax.plot([x + 0.1, x + w - 1.0], [y + h / 2] * 2, color=LINE, lw=1.5)
        ax.add_patch(plt.Rectangle((x + (w - 1.1) * 0.5, y + 0.1), 0.25, 0.3, fc="#ffffff",
                                   ec=GREY, lw=0.8))
        ax.text(x + w - 0.15, y + h / 2, value, fontsize=7, ha="right", va="center")
    else:                                   # button
        box(ax, x, y, w, h, value, fc=FILL, fs=7, weight="bold")
    return h


def sidebar(ax, module, step0, unit_click, compact=False):
    """Draw Langkah 1-3 and the module card; returns the next free y and click count."""
    y, W, x = 0.0, 7.0, 0.3
    n = 1
    # Langkah 1
    box(ax, 0.1, y - 1.75, W + 0.4, 1.75, fc="#ffffff")
    ax.text(x, y - 0.3, "LANGKAH 1", fontsize=7, color=TEAL, weight="bold")
    ax.text(x, y - 0.65, "Area of Interest", fontsize=9.5, weight="bold", color=INK)
    for i, t in enumerate(["Gambar", "Wilayah", "Tempel", "Aset"]):
        box(ax, x + i * 1.75, y - 1.55, 1.65, 0.5, t, fc=FILL, fs=7, weight="bold")
    outline(ax, x + 1.75, y - 1.55, 1.65, 0.5); badge(ax, x + 1.75, y - 1.05, n); n += 1
    y -= 1.95
    # Langkah 2
    box(ax, 0.1, y - 1.45, W + 0.4, 1.45, fc="#ffffff")
    ax.text(x, y - 0.3, "LANGKAH 2", fontsize=7, color=TEAL, weight="bold")
    ax.text(x, y - 0.65, "Satuan Pelaporan", fontsize=9.5, weight="bold", color=INK)
    box(ax, x, y - 1.3, W - 0.2, 0.5, unit_click or "Kabupaten", fc=FILL, fs=7, weight="bold")
    if unit_click:
        outline(ax, x, y - 1.3, W - 0.2, 0.5); badge(ax, x + W - 0.2, y - 0.8, n); n += 1
    y -= 1.65
    # Langkah 3
    box(ax, 0.1, y - 2.0, W + 0.4, 2.0, fc="#ffffff")
    ax.text(x, y - 0.3, "LANGKAH 3", fontsize=7, color=TEAL, weight="bold")
    ax.text(x, y - 0.65, "Modul Analisis", fontsize=9.5, weight="bold", color=INK)
    for i, m in enumerate(MODULES):
        r, c = divmod(i, 5)
        bx, by = x + c * 1.4, y - 1.3 - r * 0.62
        on = m == module
        box(ax, bx, by, 1.3, 0.5, m, fc=FILL, fs=7, weight="bold",
            ec=INK if on else LINE, lw=2.5 if on else 1)
        if on:
            outline(ax, bx, by, 1.3, 0.5); badge(ax, bx + 1.3, by + 0.5, n); n += 1
    y -= 2.2
    return y, n


def module_card(ax, module, y, n):
    eyebrow, title, desc, fields, button, _ = CARDS[module]
    x, W = 0.3, 7.0
    top = y
    yy = y - 0.3
    ax.text(x, yy, eyebrow, fontsize=7, color=TEAL, weight="bold"); yy -= 0.38
    ax.text(x, yy, title, fontsize=9.5, weight="bold", color=INK); yy -= 0.4
    ax.text(x, yy, desc, fontsize=6.3, color="#3e4c59", wrap=True); yy -= 0.45
    groups = {}
    for label, kind, value, g in fields:
        if label:
            ax.text(x, yy, label, fontsize=6.6, color=GREY, va="top"); yy -= 0.3
        yy -= 0.5
        control(ax, x, yy, W - 0.2, kind, value)
        if g is not None:
            if g not in groups:
                groups[g] = n; n += 1
                badge(ax, x + W - 0.2, yy + 0.5, groups[g])
            outline(ax, x, yy, W - 0.2, 0.5)
        yy -= 0.3
    yy -= 0.55
    box(ax, x, yy, W - 0.2, 0.5, button, fc=FILL, ec=TEAL, fs=7.5, weight="bold")
    outline(ax, x, yy, W - 0.2, 0.5); badge(ax, x + W - 0.2, yy + 0.5, n)
    yy -= 0.2
    ax.add_patch(FancyBboxPatch((0.1, yy), W + 0.4, top - yy, boxstyle="round,pad=0.01",
                                fc="none", ec=LINE, lw=1, zorder=0))
    return yy


def metric_cards(ax, labels, x, y, w, highlight=False):
    cw = (w - 0.1 * (len(labels) - 1)) / len(labels)
    for i, lab in enumerate(labels):
        bx = x + i * (cw + 0.1)
        box(ax, bx, y, cw, 1.0, fc="#effaf7", ec="#c6ece3")
        ax.plot([bx + 0.2, bx + 0.5], [y + 0.62] * 2, color=TEAL, lw=2.5)
        ax.text(bx + 0.2, y + 0.25, lab, fontsize=6.3, color="#3e4c59")
        if highlight:
            outline(ax, bx, y, cw, 1.0)


def click_figure(module, lang):
    t = TEXT[lang]
    fig = plt.figure(figsize=(12.5, 8.6))
    a = fig.add_axes([0.01, 0.01, 0.42, 0.93])
    b = fig.add_axes([0.45, 0.01, 0.54, 0.93])
    unit = "Desa" if module == "Banjir" else None
    y, n = sidebar(a, module, 1, unit)
    bottom = module_card(a, module, y, n)
    a.set_xlim(0, 7.6); a.set_ylim(bottom - 0.2, 0.15); a.set_aspect("equal"); a.set_axis_off()
    a.set_title(t["before"], loc="left", fontsize=10, weight="bold", color=RED)
    # after: result cards, then the map with the real output
    b.set_xlim(0, 10); b.set_ylim(0, 13); b.set_axis_off()
    b.set_title(t["after"], loc="left", fontsize=10, weight="bold", color=RED)
    b.text(0.1, 12.6, t["metrics"], fontsize=8, color=INK, weight="bold")
    metric_cards(b, CARDS[module][5], 0.1, 11.3, 9.8, highlight=True)
    b.text(0.1, 10.7, t["map"], fontsize=8, color=INK, weight="bold")
    box(b, 0.1, 0.1, 9.8, 10.3, fc="#dfe9e1")
    b.add_patch(plt.Polygon([[1.2, 1.4], [5.6, 0.9], [8.0, 4.0], [6.6, 8.0], [2.2, 7.4]],
                            fc="#c7e1cc", ec="#2a78d6", lw=1.5, ls="--", hatch="///"))
    b.text(4.6, 4.4, t["here"], ha="center", fontsize=9, color="#2a78d6", weight="bold",
           bbox={"fc": "white", "ec": "none", "alpha": 0.85})
    legend(b, LEGEND[module], t, 6.3, 8.3)
    return fig


def legend(ax, spec, t, x, y):
    """The app's legend panel, drawn at the top right of the map."""
    if spec is None:
        return
    box(ax, x, y - 0.1 - (0.45 * len(spec[2]) if spec[0] == "class" else 1.2), 3.4,
        (0.45 * len(spec[2]) if spec[0] == "class" else 1.2) + 1.0, fc="#ffffff")
    ax.text(x + 0.15, y + 0.6, spec[1], fontsize=7.5, weight="bold", color=INK)
    if spec[0] == "class":
        for i, (n, c) in enumerate(zip(spec[2], spec[3])):
            yy = y + 0.05 - i * 0.45
            ax.add_patch(plt.Rectangle((x + 0.15, yy - 0.15), 0.35, 0.3, fc=c, ec=GREY, lw=0.5))
            ax.text(x + 0.65, yy, n, fontsize=7, va="center")
        if spec[1] == "Tutupan lahan":
            ax.text(x + 0.15, y - 0.45 * len(spec[2]) + 0.05, t["own"], fontsize=6, color=GREY)
    else:
        pal, lo, hi = spec[2], spec[3], spec[4]
        n = 60
        for i in range(n):
            c = plt.matplotlib.colors.LinearSegmentedColormap.from_list("p", pal)(i / (n - 1))
            ax.add_patch(plt.Rectangle((x + 0.15 + i * 3.1 / n, y - 0.1), 3.1 / n, 0.4, fc=c,
                                       ec="none"))
        ax.text(x + 0.15, y - 0.45, f"{lo:g}", fontsize=7)
        ax.text(x + 3.25, y - 0.45, f"{hi:g}", fontsize=7, ha="right")


def layout_figure(lang):
    fig = plt.figure(figsize=(12.5, 6.4))
    a = fig.add_axes([0.01, 0.01, 0.40, 0.92])
    b = fig.add_axes([0.43, 0.01, 0.56, 0.92])
    y, n = sidebar(a, "Data", 1, None)
    a.set_xlim(0, 7.6); a.set_ylim(y - 0.2, 0.15); a.set_aspect("equal"); a.set_axis_off()
    b.set_xlim(0, 10); b.set_ylim(0, 10); b.set_axis_off()
    box(b, 0.1, 0.1, 9.8, 9.8, fc="#dfe9e1")
    b.add_patch(plt.Polygon([[2, 2], [6, 1.6], [8.4, 4.4], [7, 7.6], [3, 7.0]],
                            fc="#c7e1cc", ec="#2a78d6", lw=1.5, ls="--"))
    b.text(5.2, 4.6, "AOI", ha="center", fontsize=9, color="#2a78d6")
    box(b, 7.0, 8.0, 2.6, 1.5, "Legenda", fs=8)
    box(b, 0.4, 0.4, 6.4, 0.6, "Lapisan aktif: belum ada", fs=7.5, ha="left")
    fig.suptitle(TEXT[lang]["screen"], x=0.01, ha="left", fontsize=10, weight="bold")
    return fig


def chain_figure(lang):
    steps = {"en": ["Citra\nSentinel-2 composite", "Kalkulator ekspresi\n(NIR−red)/(NIR+red)",
                    "Ambang batas Otsu\nautomatic threshold", "Morfologi + sieve\nsmall patches out",
                    "Raster ke vektor\npolygons", "Statistik zonal\nper village"],
             "id": ["Citra\nkomposit Sentinel-2", "Kalkulator ekspresi\n(NIR−merah)/(NIR+merah)",
                    "Ambang batas Otsu\nambang otomatis", "Morfologi + sieve\nbuang petak kecil",
                    "Raster ke vektor\npoligon", "Statistik zonal\nper desa"]}[lang]
    note = {"en": "Toolbox › Operasi › Jalankan operasi. Each result becomes the active layer "
                  "(Lapisan aktif), so the next tool works on it: a whole workflow without code.",
            "id": "Toolbox › Operasi › Jalankan operasi. Setiap hasil menjadi lapisan aktif, "
                  "jadi alat berikutnya bekerja di atasnya: satu alur kerja utuh tanpa kode."}[lang]
    fig, ax = plt.subplots(figsize=(11, 2.6))
    ax.set_xlim(0, 16); ax.set_ylim(0, 3); ax.set_axis_off()
    for i, t in enumerate(steps):
        box(ax, 0.2 + i * 2.65, 0.8, 2.3, 1.5, t, fc="#effaf7" if i else "#ffffff", fs=7.2)
        if i:
            ax.annotate("", (0.2 + i * 2.65, 1.55), (0.2 + i * 2.65 - 0.33, 1.55),
                        arrowprops={"arrowstyle": "-|>", "color": TEAL})
    ax.text(0.2, 0.35, note, fontsize=8, color="#3e4c59")
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
    out = [{"kind": "table", "name": "p6-guide", "data": guide_table,
            "caption": "Which module to open for which question."}]
    for lang in ("en", "id"):
        out += [{"kind": "figure", "name": f"p6-layout-{lang}", "figure": (lambda l=lang: layout_figure(l)),
                 "caption": "The IJB screen."},
                {"kind": "figure", "name": f"p6-chain-{lang}", "figure": (lambda l=lang: chain_figure(l)),
                 "caption": "Chaining Toolbox operations."}]
        out += [{"kind": "figure", "name": f"p6-click-{m.lower()}-{lang}",
                 "figure": (lambda m=m, l=lang: click_figure(m, l)),
                 "caption": f"IJB {m}: before and after pressing the button."} for m in CARDS]
    return out


if __name__ == "__main__":
    print(guide_table())
