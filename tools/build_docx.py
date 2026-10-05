"""Build the Word (.docx) editions of the book, English and Indonesian.

    python3 tools/build_docx.py [--quarto PATH] [--lang en|id]

The web book stays the source of truth. For each language this script makes a
temporary copy of the Quarto project in build/word-<lang>/, adapts the copy for
print, and renders it to one .docx:

  * every chapter gets a short note after its title linking to the same
    chapter online, where the maps are interactive and the code runs
  * front matter: how to use this edition, abbreviations, list of figures and
    list of tables (the lists are filled in by tools/word/word.lua)
  * web-only blocks are removed (runnable cells, quizzes, web maps)
  * no code and no outputs: each listing, with its maps, charts and tables, and
    each live Python figure becomes a link to the online chapter and the script
  * styles come from tools/word/reference.docx (tools/word/make_reference_docx.py)

Output: docs/downloads/<slug>-<lang>.docx (and build/word-<lang>/_book/).
"""

import argparse
import re
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://rifkynhsp-byte.github.io/Fullstack-Remote-Sensing"
SHARED = ["references.bib", "booklib.py", "styles.css"]

TEXT = {
    "en": {
        "online": "Online edition of this chapter, with interactive maps and runnable code:",
        "code": "Code and results online:",
        "script": "Script:",
        "live": "Interactive figure online:",
        "front_title": "About this edition",
        "front": [
            "This is the reading edition of a book that lives online at {site}/en/. "
            "It carries the explanations, the reasoning and the discussion of every result. "
            "The code, and the maps, charts and tables it produces, live online, where they "
            "are complete and current: wherever the online book shows a script and its "
            "results, this edition gives a link to that page and to the script itself. "
            "The online edition also adds maps you can pan and zoom, charts you can change, "
            "Python you can run in the browser, and knowledge checks.",
            "Figures and tables are numbered through the whole book. The lists that follow "
            "give their captions, grouped by chapter.",
        ],
        "abbr": "Abbreviations",
        "lof": "List of Figures",
        "lot": "List of Tables",
    },
    "id": {
        "online": "Edisi daring bab ini, dengan peta interaktif dan kode yang bisa dijalankan:",
        "code": "Kode dan hasilnya secara daring:",
        "script": "Skrip:",
        "live": "Gambar interaktif secara daring:",
        "front_title": "Tentang edisi ini",
        "front": [
            "Ini adalah edisi baca dari buku yang tersedia daring di {site}/id/. "
            "Edisi ini memuat penjelasan, penalaran, dan pembahasan setiap hasil. Kode, "
            "beserta peta, grafik, dan tabel yang dihasilkannya, ada di edisi daring, lengkap "
            "dan mutakhir: di setiap tempat buku daring menampilkan skrip dan hasilnya, edisi "
            "ini memberi tautan ke halaman itu dan ke skripnya. Edisi daring juga menambahkan "
            "peta yang bisa digeser dan diperbesar, grafik yang bisa diubah, Python yang bisa "
            "dijalankan di peramban, dan uji pemahaman.",
            "Gambar dan tabel diberi nomor berurutan di seluruh buku. Daftar berikut memuat "
            "keterangannya, dikelompokkan per bab.",
        ],
        "abbr": "Singkatan",
        "lof": "Daftar Gambar",
        "lot": "Daftar Tabel",
    },
}

# Abbreviations used in the book: (abbreviation, English, Indonesian).
ABBR = [
    ("AGB", "aboveground biomass", "biomassa atas permukaan"),
    ("AMDAL", "environmental impact assessment (Indonesia)", "analisis mengenai dampak lingkungan"),
    ("AOI", "area of interest", "wilayah kajian"),
    ("BPS", "Statistics Indonesia", "Badan Pusat Statistik"),
    ("CART", "classification and regression tree", "pohon klasifikasi dan regresi"),
    ("CHIRPS", "Climate Hazards Group InfraRed Precipitation with Station data", "data curah hujan CHIRPS"),
    ("CHM", "canopy height model", "model tinggi kanopi"),
    ("CSF", "cloth simulation filter", "penyaring simulasi kain"),
    ("DBH", "diameter at breast height", "diameter setinggi dada"),
    ("DEM", "digital elevation model", "model elevasi digital"),
    ("DTM", "digital terrain model", "model medan digital"),
    ("DW", "Dynamic World", "Dynamic World"),
    ("EE / GEE", "Google Earth Engine", "Google Earth Engine"),
    ("ERA5", "fifth-generation ECMWF reanalysis", "reanalisis ECMWF generasi kelima"),
    ("EUDR", "EU Deforestation Regulation", "Regulasi Deforestasi Uni Eropa"),
    ("FFB", "fresh fruit bunches (oil palm)", "tandan buah segar (TBS)"),
    ("FOLU", "forestry and other land use", "kehutanan dan penggunaan lahan lainnya"),
    ("GEDI", "Global Ecosystem Dynamics Investigation (lidar)", "lidar GEDI"),
    ("GHI", "global horizontal irradiance", "iradiasi horizontal global"),
    ("GLCM", "grey-level co-occurrence matrix", "matriks ko-okurensi tingkat keabuan"),
    ("GMW", "Global Mangrove Watch", "Global Mangrove Watch"),
    ("GRACE", "Gravity Recovery and Climate Experiment", "misi gravitasi GRACE"),
    ("HAND", "height above nearest drainage", "tinggi di atas drainase terdekat"),
    ("IPCC", "Intergovernmental Panel on Climate Change", "Panel Antarpemerintah tentang Perubahan Iklim"),
    ("JRC", "Joint Research Centre (EU)", "Joint Research Centre (UE)"),
    ("LiDAR", "light detection and ranging", "deteksi dan pengukuran jarak dengan cahaya"),
    ("LST", "land surface temperature", "suhu permukaan lahan"),
    ("MRV", "monitoring, reporting and verification", "pemantauan, pelaporan, dan verifikasi"),
    ("NBR", "normalised burn ratio", "normalised burn ratio"),
    ("NDMI", "normalised difference moisture index", "indeks kelembapan ternormalisasi"),
    ("NDVI", "normalised difference vegetation index", "indeks vegetasi ternormalisasi"),
    ("NDWI", "normalised difference water index", "indeks air ternormalisasi"),
    ("NIR", "near infrared", "inframerah dekat"),
    ("OBIA", "object-based image analysis", "analisis citra berbasis objek"),
    ("OSM", "OpenStreetMap", "OpenStreetMap"),
    ("PETI", "unlicensed mining", "penambangan tanpa izin"),
    ("PLN", "Indonesian state electricity company", "Perusahaan Listrik Negara"),
    ("PMF", "progressive morphological filter", "penyaring morfologi progresif"),
    ("PNBP", "non-tax state revenue", "penerimaan negara bukan pajak"),
    ("PR", "performance ratio (solar)", "rasio kinerja (surya)"),
    ("PV", "photovoltaic", "fotovoltaik"),
    ("RF", "random forest", "random forest"),
    ("REDD+", "reducing emissions from deforestation and forest degradation", "pengurangan emisi dari deforestasi dan degradasi hutan"),
    ("RTRW", "spatial plan (Indonesia)", "rencana tata ruang wilayah"),
    ("SAR", "synthetic aperture radar", "radar apertur sintetis"),
    ("SCC", "social cost of carbon", "biaya sosial karbon"),
    ("SHAP", "Shapley additive explanations", "Shapley additive explanations"),
    ("SVM", "support vector machine", "support vector machine"),
    ("SWIR", "shortwave infrared", "inframerah gelombang pendek"),
    ("UTM", "Universal Transverse Mercator", "Universal Transverse Mercator"),
    ("WDPA", "World Database on Protected Areas", "Basis Data Kawasan Lindung Dunia"),
]


def front_matter(lang):
    t = TEXT[lang]
    lines = [f"# {t['front_title']} {{.unnumbered}}", ""]
    lines += [p.format(site=SITE) + "\n" for p in t["front"]]
    lines += [f"## {t['abbr']} {{.unnumbered}}", "",
              "| | |", "|---|---|"]
    lines += [f"| **{a}** | {en if lang == 'en' else idn} |" for a, en, idn in ABBR]
    lines += ["", f"## {t['lof']} {{.unnumbered}}", "", "::: {#list-of-figures}", ":::", "",
              f"## {t['lot']} {{.unnumbered}}", "", "::: {#list-of-tables}", ":::", ""]
    return "\n".join(lines)


def chapter_files(chapters):
    for c in chapters:
        if isinstance(c, str):
            yield c
        elif isinstance(c, dict):
            yield from chapter_files(c.get("chapters", []))


def add_online_link(path, lang):
    text = path.read_text(encoding="utf-8")
    url = f"{SITE}/{lang}/{path.stem}.html"
    note = f"\n*{TEXT[lang]['online']}* <{url}>\n"
    # after the first level-1 heading (and its attribute block)
    m = re.search(r"^# .*$", text, flags=re.M)
    if not m:
        return
    path.write_text(text[:m.end()] + "\n" + note + text[m.end():], encoding="utf-8")


def prepare(lang, quarto, skip_mermaid=False):
    src = ROOT / lang
    dst = ROOT / "build" / f"word-{lang}"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("_book", "_freeze", ".quarto",
                                                            "images", "interactive"))
    for f in SHARED:
        if (ROOT / f).exists():
            shutil.copy(ROOT / f, dst / f)
    shutil.copytree(ROOT / "images", dst / "images",
                    ignore=shutil.ignore_patterns("*.html", "raw"))

    # Mermaid diagrams need a headless Chrome to become images. CI has one; a local
    # test without it can replace them with a pointer to the online edition.
    if skip_mermaid:
        note = ("*Diagram: see the online edition.*" if lang == "en"
                else "*Diagram: lihat edisi daring.*")
        for q in dst.glob("*.qmd"):
            t = q.read_text(encoding="utf-8")
            t2 = re.sub(r"^```\{mermaid\}.*?^```\s*$", note, t, flags=re.M | re.S)
            if t2 != t:
                q.write_text(t2, encoding="utf-8")

    # No code and no outputs in the reading edition: each listing (with its maps,
    # charts and tables) becomes a link to the online chapter and to the script.
    repo = "https://github.com/rifkynhsp-byte/Fullstack-Remote-Sensing/blob/main/scripts"
    for q in dst.glob("*.qmd"):
        t = q.read_text(encoding="utf-8")
        url = f"{SITE}/{lang}/{q.stem}.html"

        def link(m):
            stem = m.group(1)
            if (ROOT / "scripts" / "py" / f"{stem}.py").exists():
                script = f"{repo}/py/{stem}.py"
            elif (ROOT / "scripts" / lang / f"{stem}.js").exists():
                script = f"{repo}/{lang}/{stem}.js"
            else:
                script = f"{repo}/en/{stem}.js"
            return (f"*{TEXT[lang]['code']}* <{url}>  \n"
                    f"*{TEXT[lang]['script']}* <{script}>")
        # [ \t]* rather than \s*: the line break must survive, or a following
        # callout or heading would be swallowed into the link paragraph.
        t2 = re.sub(r"^\{\{< include _snippets/(\S+?)\.qmd >\}\}[ \t]*$",
                    lambda m: link(m) + "\n", t, flags=re.M)
        t2 = re.sub(r"^```\{python\}.*?^```[ \t]*$", f"*{TEXT[lang]['live']}* <{url}>\n", t2,
                    flags=re.M | re.S)
        if t2 != t:
            q.write_text(t2, encoding="utf-8")

    # Table attributes such as ": Caption {.striped}" are HTML styling; in Word
    # they would print as text.
    for q in dst.glob("*.qmd"):
        t = q.read_text(encoding="utf-8")
        t2 = re.sub(r"^(: .*?)\s*\{\.[^}]*\}\s*$", r"\1", t, flags=re.M)
        if t2 != t:
            q.write_text(t2, encoding="utf-8")

    # Interactive widgets (sliders, explorers) work only on the web.
    for q in dst.glob("*.qmd"):
        t = q.read_text(encoding="utf-8")
        t2 = re.sub(r"^\{\{< include \.\./interactive/.*?>\}\}\s*$", "", t, flags=re.M)
        if t2 != t:
            q.write_text(t2, encoding="utf-8")

    cfg = yaml.safe_load((dst / "_quarto.yml").read_text(encoding="utf-8"))
    book = cfg["book"]
    for name in chapter_files(book["chapters"]):
        p = dst / name
        if p.exists() and name not in ("index.qmd",):
            add_online_link(p, lang)
    (dst / "word-front.qmd").write_text(front_matter(lang), encoding="utf-8")
    book["chapters"] = ["index.qmd", "word-front.qmd"] + [
        c for c in book["chapters"] if c != "index.qmd"]
    for k in ("navbar", "sidebar", "repo-url", "repo-branch", "repo-subdir", "repo-actions",
              "search", "reader-mode", "page-navigation", "favicon", "page-footer"):
        book.pop(k, None)
    book.pop("downloads", None)
    cfg["project"] = {"type": "book", "output-dir": "_book"}
    cfg["execute"] = {"eval": False, "freeze": False}
    cfg["format"] = {"docx": {
        "reference-doc": str(ROOT / "tools" / "word" / "reference.docx"),
        "toc": True, "toc-depth": 2, "number-sections": True,
        "toc-title": "Contents" if lang == "en" else "Daftar Isi",
        "filters": [str(ROOT / "tools" / "word" / "word.lua")],
        "highlight-style": "github",
    }}
    for k in ("filters", "include-in-header", "include-after-body"):
        cfg.pop(k, None)
    (dst / "_quarto.yml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                                     encoding="utf-8")
    return dst


def render(dst, lang, quarto, pythonpath=None):
    import os
    env = dict(os.environ)
    if pythonpath:
        env["PYTHONPATH"] = pythonpath + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run([quarto, "render", str(dst), "--to", "docx"], check=True, env=env)
    out = list((dst / "_book").glob("*.docx"))
    if not out:
        raise SystemExit("no .docx produced")
    target = ROOT / "docs" / "downloads"
    target.mkdir(parents=True, exist_ok=True)
    final = target / f"flux-pixels-planet-{lang}.docx"
    shutil.copy(out[0], final)
    print(f"  -> {final.relative_to(ROOT)}  ({final.stat().st_size / 1e6:.1f} MB)")
    return final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarto", default="quarto")
    ap.add_argument("--lang", choices=["en", "id"], action="append")
    ap.add_argument("--skip-mermaid", action="store_true",
                    help="replace Mermaid diagrams with a note (local test without Chrome)")
    ap.add_argument("--pythonpath", default=None,
                    help="extra package folder for the executed cells (jupyter, plotly, kaleido)")
    a = ap.parse_args()
    subprocess.run(["python3", str(ROOT / "tools" / "build_snippets.py")], check=True)
    for lang in a.lang or ["en", "id"]:
        print(f"==> Word edition, {lang}")
        render(prepare(lang, a.quarto, a.skip_mermaid), lang, a.quarto, a.pythonpath)


if __name__ == "__main__":
    main()
