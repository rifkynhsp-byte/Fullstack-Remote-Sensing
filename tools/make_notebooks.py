"""Build one Colab notebook per chapter script: notebooks/<script>.ipynb (2026-10-05).

Each notebook: a header with links (book chapter EN/ID, Code Editor), one setup cell (packages, the book repository
for its data and helpers, Earth Engine sign-in with the reader's own Cloud project), the script itself split at its
STEP banners with the banner text as a heading, and a last cell that draws the chapter's products the way the book
does. The script's `if __name__ == "__main__":` block is left out: it is the author's command-line entry point.

    python tools/make_notebooks.py            # all scripts
    python tools/make_notebooks.py ch24_flood_aceh
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY, NB = ROOT / "scripts" / "py", ROOT / "notebooks"
GH = "rifkynhsp-byte/Fullstack-Remote-Sensing"
SITE = "https://rifkynhsp-byte.github.io/Fullstack-Remote-Sensing"
GEE_REPO = "users/rifkynauvalhsp/Fullstack-Remote-Sensing"
BANNER = re.compile(r"^# -{20,}\n# (STEP [^\n]*|[A-Z][^\n]*)\n# -{20,}\n", re.M)
# packages Colab does not ship, by import name -> pip name
EXTRA = {"geemap": "geemap", "laspy": "laspy[lazrs]", "rasterio": "rasterio", "tabulate": "tabulate",
         "rioxarray": "rioxarray", "pyproj": "pyproj", "contextily": "contextily", "lightgbm": "lightgbm",
         "osmnx": "osmnx", "mapclassify": "mapclassify", "statsmodels": "statsmodels", "plotly": "plotly",
         "openpyxl": "openpyxl"}


def chapter_of(stem: str) -> tuple[str, str] | None:
    """(qmd file name, title) of the chapter that includes this script."""
    for qmd in sorted((ROOT / "en").glob("*.qmd")):
        if stem in qmd.read_text(encoding="utf-8"):
            first = qmd.read_text(encoding="utf-8").split("\n", 1)[0]
            return qmd.name, re.sub(r"\s*\{.*\}\s*$", "", first.lstrip("# ")).strip()
    return None


def cells_from(src: str) -> list[tuple[str, str]]:
    src = re.sub(r"^#\|[^\n]*\n", "", src, flags=re.M)                       # Quarto listing options
    src = re.split(r"\nif __name__ == [\"']__main__[\"']:", src)[0].rstrip() + "\n"
    out = []
    try:                                                                        # module docstring -> markdown
        doc = ast.get_docstring(ast.parse(src))
    except SyntaxError:
        doc = None
    if doc:
        src = re.sub(r'^\s*(""".*?"""|\'\'\'.*?\'\'\')\s*\n', "", src, count=1, flags=re.S)
        out.append(("markdown", doc))
    parts = BANNER.split(src)
    if parts[0].strip():
        out += [("code", c) for c in by_function(parts[0])]
    for head, body in zip(parts[1::2], parts[2::2]):
        out.append(("markdown", f"### {head.strip().capitalize() if head.isupper() else head.strip()}"))
        out += [("code", c) for c in by_function(body)]
    return out


def by_function(chunk: str) -> list[str]:
    """Split a chunk before every top-level def/class, keeping the comment lines just above it with it."""
    lines, cells, cur = chunk.strip("\n").split("\n"), [], []
    for ln in lines:
        if re.match(r"(def|class|@)\s*\w", ln) and not (cur and cur[-1].startswith("@")):
            keep = []
            while cur and (cur[-1].startswith("#") or not cur[-1].strip()):
                keep.insert(0, cur.pop())
            if "\n".join(cur).strip():
                cells.append("\n".join(cur).strip())
            cur = keep
        cur.append(ln)
    if "\n".join(cur).strip():
        cells.append("\n".join(cur).strip())
    return cells


def notebook(stem: str) -> dict:
    src = (PY / f"{stem}.py").read_text(encoding="utf-8")
    title = (re.search(r"^#\| title: (.*)$", src, re.M) or [None, stem])[1]
    chap = chapter_of(stem)
    imports = set(re.findall(r"^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", src, re.M))
    pip = sorted({"earthengine-api", "geemap", "tabulate"} | {EXTRA[i] for i in imports if i in EXTRA} | ({"openpyxl"} if "read_excel" in src else set()))
    uses_ee = "ee." in src
    js = (ROOT / "scripts" / "en" / f"{stem}.js").exists()
    links = []
    if chap:
        page = chap[0].replace(".qmd", ".html")
        links += [f"[Chapter: {chap[1]}]({SITE}/en/{page})", f"[Bab (Bahasa Indonesia)]({SITE}/id/{page})"]
    if js:
        links.append(f"[Open the JavaScript in the Code Editor](https://code.earthengine.google.com/?scriptPath={GEE_REPO}:{stem})")
    header = (f"# {title}\n\n**Fullstack Remote Sensing** by Rifky Nauval Hendrawan · {' · '.join(links)}\n\n"
              "Run the cells from top to bottom. The first cell installs what Colab lacks, fetches the book's data "
              "and helpers, and signs you in to Earth Engine with your own Google Cloud project "
              "([how to get one](https://developers.google.com/earth-engine/guides/access)).\n\n"
              "*Jalankan sel dari atas ke bawah. Sel pertama memasang paket, mengambil data buku, dan masuk ke Earth Engine "
              "dengan proyek Google Cloud Anda sendiri.*")
    setup = [f"# @title Setup: packages, book data, Earth Engine sign-in",
             f"!pip -q install {' '.join(pip)}",
             f"!test -d /content/book || git clone -q --depth 1 --filter=blob:none --sparse https://github.com/{GH}.git /content/book",
             "!git -C /content/book sparse-checkout set tools scripts data   # only what the code needs, not the website",
             "import sys, os; sys.path[:0] = ['/content/book/tools', '/content/book/scripts/py']; os.chdir('/content/book')",
             f"__file__ = '/content/book/scripts/py/{stem}.py'   # the script finds the book's data relative to itself"]
    if uses_ee:
        setup += ['PROJECT = "your-cloud-project"  # @param {type:"string"}',
                  "import ee",
                  "ee.Authenticate()",
                  "ee.Initialize(project=PROJECT)",
                  "_init = ee.Initialize; ee.Initialize = lambda *a, **k: None   # the script must not sign in again"]
    cells = [("markdown", header), ("code", "\n".join(setup))] + cells_from(src)
    cells += [("markdown", "### The chapter's maps, charts and tables\nThe same products the book shows, drawn here. "
                           "Maps also open as an interactive layer."),
              ("code", "from colab_render import show_all\nshow_all(products())")]
    nb_cells = []
    for kind, text in cells:
        c = {"cell_type": kind, "metadata": {}, "source": text.splitlines(keepends=True)}
        if kind == "code":
            c.update(execution_count=None, outputs=[])
        nb_cells.append(c)
    return {"cells": nb_cells, "nbformat": 4, "nbformat_minor": 5,
            "metadata": {"colab": {"name": f"{stem}.ipynb", "provenance": []},
                         "kernelspec": {"name": "python3", "display_name": "Python 3"}, "language_info": {"name": "python"}}}


def main(argv: list[str]) -> int:
    NB.mkdir(exist_ok=True)
    stems = argv or sorted(p.stem for p in PY.glob("ch*.py"))
    for stem in stems:
        (NB / f"{stem}.ipynb").write_text(json.dumps(notebook(stem), indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(stems)} notebooks -> {NB}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
