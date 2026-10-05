"""Show a chapter's products inside Colab or Jupyter, with the same cartography the book uses.

Every chapter script ends with `products()`: a list of maps, charts, tables, figures and animations. In the book
they are rendered to files at build time by `tools/real_outputs.py`; here the same functions draw them straight into
the notebook, and every map is also opened as an interactive geemap layer you can pan and inspect.

    from colab_render import show_all
    show_all(products())                 # everything
    show_all(products(), only=["ch24-flood-map"])
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
from IPython.display import HTML, Image, Markdown, display

import real_outputs as R

OUT = Path(tempfile.mkdtemp(prefix="book_"))
R.IMG_DIR = OUT                                   # the renderer writes here instead of the book's images/


def _interactive(p: dict):
    try:
        import geemap
    except ImportError:                           # geemap is optional; the static map is already shown
        return
    m = geemap.Map(height="420px")
    m.addLayer(p["image"], p.get("vis", {}), p.get("title", p["name"]))
    m.centerObject(p["region"])
    display(m)


def show_all(items: list[dict], only: list[str] | None = None, interactive: bool = True) -> None:
    for p in items:
        name, kind = p["name"], p["kind"]
        if only and name not in only:
            continue
        display(Markdown(f"#### {name}\n{p.get('caption', '')}"))
        try:
            if kind == "map":
                out = OUT / f"{name}.jpg"; R.render_map(p, out); display(Image(filename=str(out)))
                if interactive:
                    _interactive(p)
            elif kind == "chart":
                df = R.to_frame(p["data"]); fig = p["plot"](df); display(fig); plt.close(fig)
            elif kind == "figure":
                fig = p["figure"](); display(fig); plt.close(fig)
            elif kind == "animation":
                out = OUT / f"{name}.gif"; R.render_animation(p, out); display(Image(filename=str(out)))
            elif kind == "table":
                df = R.to_frame(p["data"])
                if "transform" in p:
                    df = p["transform"](df)
                if "columns" in p:
                    df = df[list(p["columns"])]
                display(df)
            elif kind == "html":
                out = OUT / f"{name}.html"; p["build"](str(out)); display(HTML(out.read_text()))
        except Exception as err:                  # one failed product must not stop the rest
            display(Markdown(f"**{name} failed:** `{str(err)[:300]}`"))
