#!/usr/bin/env python3
"""
real_outputs.py
===============

Runs every Python twin in scripts/py/ against live Earth Engine and writes the
real maps, charts and tables that sit under each code listing in the book.

Every JavaScript listing in scripts/en/ has a Python twin with the same name in
scripts/py/. Both do the same analysis. The twin also defines `products()`,
which returns what the chapter shows. This script renders those products:

    map    -> images/real/<name>.png   (thumbnail from Earth Engine, drawn with
                                        lon/lat axes, a colour bar and a scale)
    chart  -> images/real/<name>.png   (the twin's own matplotlib function)
    table  -> a Markdown table in the manifest

and writes outputs/<script>.json, which tools/build_snippets.py turns into the
"Output" block under the listing, plus a small runnable Python cell that holds
the chart's real data so a reader can change the plot in the browser.

Credentials
-----------
Nothing secret lives in this repository. Point BOOK_EE_KEY at a service account
JSON key file, or leave it unset to use your own `earthengine authenticate`
login with BOOK_EE_PROJECT set to your Cloud project.

    BOOK_EE_KEY=~/.config/book/key.json python3 tools/real_outputs.py
    python3 tools/real_outputs.py ch09_annual_composite     # just one script
"""

from __future__ import annotations

import importlib.util
import inspect
import io
import json
import math
import os
import sys
import textwrap
from pathlib import Path

import ee
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
import pandas as pd                                  # noqa: E402
import requests                                      # noqa: E402
from PIL import Image                                # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PY_DIR = ROOT / "scripts" / "py"
IMG_DIR = ROOT / "images" / "real"
OUT_DIR = ROOT / "outputs"

MAP_WIDTH = 1400          # pixels requested from Earth Engine
LIVE_MAX_ROWS = 400       # rows embedded in a runnable cell, to keep pages light

INK = "#1f2933"
plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 150, "font.size": 9,
    "axes.edgecolor": "#9aa5b1", "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK, "ytick.color": INK, "axes.spines.top": False,
    "axes.spines.right": False,
})


# ---------------------------------------------------------------------------
# Earth Engine
# ---------------------------------------------------------------------------
def initialise() -> None:
    key = os.environ.get("BOOK_EE_KEY")
    if key:
        key = os.path.expanduser(key)
        info = json.loads(Path(key).read_text())
        creds = ee.ServiceAccountCredentials(info["client_email"], key)
        ee.Initialize(creds, project=info["project_id"])
    else:
        ee.Initialize(project=os.environ.get("BOOK_EE_PROJECT"))


_FRAMES: dict[int, pd.DataFrame] = {}
WEB_LAYERS: list[dict] = []     # filled by render_map, one entry per map product


def to_frame(data) -> pd.DataFrame:
    """Turn whatever a twin returns (FeatureCollection, dict, list, frame) into a frame.

    Results are cached per object, so a heavy collection used by a chart and a
    table is computed on the server once.
    """
    if id(data) in _FRAMES:
        return _FRAMES[id(data)].copy()
    df = _to_frame(data)
    _FRAMES[id(data)] = df
    return df.copy()


def _to_frame(data) -> pd.DataFrame:
    if callable(data):                      # a twin that fetches in batches itself
        return data()
    if isinstance(data, pd.DataFrame):
        return data
    if isinstance(data, ee.FeatureCollection):
        info = data.getInfo()
        return pd.DataFrame([f["properties"] for f in info["features"]])
    if isinstance(data, (ee.Dictionary, ee.List, ee.ComputedObject)):
        data = data.getInfo()
    if isinstance(data, dict):
        return pd.DataFrame([data])
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def _bounds(region: ee.Geometry):
    coords = region.bounds().coordinates().getInfo()[0]
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return min(xs), max(xs), min(ys), max(ys)


def _scale_bar(ax, x0, x1, y0, y1):
    """A plain scale bar: 1-2-5 rounded length, about a fifth of the width."""
    mid_lat = math.radians((y0 + y1) / 2)
    km_per_deg = 111.32 * math.cos(mid_lat)
    width_km = (x1 - x0) * km_per_deg
    target = width_km / 5
    base = 10 ** math.floor(math.log10(target))
    length = max(m * base for m in (1, 2, 5) if m * base <= target)
    deg = length / km_per_deg
    px, py = x0 + (x1 - x0) * 0.05, y0 + (y1 - y0) * 0.06
    ax.plot([px, px + deg], [py, py], color="black", lw=4, solid_capstyle="butt")
    ax.plot([px, px + deg], [py, py], color="white", lw=2, solid_capstyle="butt")
    label = f"{length:g} km" if length >= 1 else f"{length * 1000:g} m"
    ax.text(px + deg / 2, py + (y1 - y0) * 0.025, label, ha="center", va="bottom",
            fontsize=8, color="black",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))


def render_map(p: dict, out: Path) -> None:
    region = p["region"]
    vis = dict(p["vis"])
    img, last_error = None, ""
    # Heavy maps (several classifiers, focal filters) can time out on Earth
    # Engine's side at full size. Step down the size before giving up.
    for width in (p.get("width", MAP_WIDTH), 900, 600):
        url = p["image"].visualize(**vis).getThumbURL(
            {"region": region, "dimensions": width, "format": "png"})
        reply = requests.get(url, timeout=600)
        if reply.headers.get("content-type", "").startswith("image/"):
            img = Image.open(io.BytesIO(reply.content))
            break
        last_error = reply.text[:200]
    if img is None:
        raise RuntimeError(f"Earth Engine returned no image: {last_error}")
    x0, x1, y0, y1 = _bounds(region)
    # Keep the bare image and its bounds for the chapter's interactive web map.
    raw_dir = IMG_DIR / "raw"
    raw_dir.mkdir(exist_ok=True)
    web = img.convert("RGBA")
    web.thumbnail((1000, 1000))
    # 256 colours with transparency keeps each overlay to a few hundred kB.
    web.quantize(colors=255, method=Image.Quantize.FASTOCTREE).save(
        raw_dir / f"{out.stem}.png", optimize=True)
    WEB_LAYERS.append({"name": out.stem, "title": p.get("title", out.stem),
                       "png": f"raw/{out.stem}.png", "bounds": [[y0, x0], [y1, x1]]})

    fig, ax = plt.subplots(figsize=(7.2, 7.2 * (y1 - y0) / (x1 - x0) + 0.9))
    ax.imshow(img, extent=[x0, x1, y0, y1], interpolation="nearest")
    ax.set_xlabel("Longitude (°)")
    ax.set_ylabel("Latitude (°)")
    ax.set_title(p.get("title", ""), loc="left", fontsize=10, fontweight="bold")
    ax.tick_params(labelsize=7)
    ax.ticklabel_format(useOffset=False, style="plain")
    _scale_bar(ax, x0, x1, y0, y1)
    ax.annotate("N", xy=(0.95, 0.93), xytext=(0.95, 0.83), xycoords="axes fraction",
                ha="center", fontsize=9, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color="black"))

    if "palette" in vis and "classes" not in p and "min" in vis:
        import re
        def colour(c):             # hex with or without '#', or a named colour
            c = c.lstrip("#")
            return "#" + c if re.fullmatch(r"[0-9a-fA-F]{6}", c) else c
        cmap = LinearSegmentedColormap.from_list("p", [colour(c) for c in vis["palette"]])
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vis["min"], vis["max"]))
        cb = fig.colorbar(sm, ax=ax, orientation="horizontal", fraction=0.04, pad=0.09)
        cb.set_label(p.get("legend", ", ".join(vis.get("bands", []))), fontsize=8)
    elif "classes" in p:          # categorical legend: [(label, colour), ...]
        from matplotlib.patches import Patch
        ax.legend(handles=[Patch(color=c, label=l) for l, c in p["classes"]],
                  loc="lower right", fontsize=7, framealpha=0.9)

    ax.text(0.99, 0.01, p.get("source", "Data: Google Earth Engine"),
            transform=ax.transAxes, ha="right", va="bottom", fontsize=6.5, color=INK,
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.75))
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", pil_kwargs={"quality": 85, "optimize": True})
    plt.close(fig)


def render_animation(p: dict, out: Path) -> None:
    """An animated GIF from a collection of already visualised RGB frames.

    Earth Engine renders the frames; each one then gets its label (usually
    the year) burnt into the corner, because a time-lapse without dates is
    a screensaver.
    """
    from PIL import ImageDraw, ImageSequence
    if "frames" in p:
        # One thumbnail per frame. Slower, but each request is small enough to
        # stay under Earth Engine's per-request memory limit, which a single
        # video request over several composites can exceed.
        raw = []
        for frame in p["frames"]:
            url = frame.getThumbURL({"region": p["region"], "dimensions": p.get("width", 520),
                                     "format": "png", "crs": "EPSG:3857"})
            reply = requests.get(url, timeout=600)
            if not reply.headers.get("content-type", "").startswith("image/"):
                raise RuntimeError(reply.text[:200])
            raw.append(Image.open(io.BytesIO(reply.content)))
    else:
        url = p["collection"].getVideoThumbURL({
            "region": p["region"], "dimensions": p.get("width", 720),
            "framesPerSecond": p.get("fps", 1), "crs": "EPSG:3857"})
        reply = requests.get(url, timeout=600)
        if not reply.headers.get("content-type", "").startswith("image/"):
            raise RuntimeError(reply.text[:200])
        raw = list(ImageSequence.Iterator(Image.open(io.BytesIO(reply.content))))
    labels = p.get("labels", [])
    frames = []
    for i, frame in enumerate(raw):
        f = frame.convert("RGB")
        if i < len(labels):
            d = ImageDraw.Draw(f)
            from PIL import ImageFont
            try:
                font = ImageFont.load_default(size=18)
            except TypeError:                      # Pillow < 10.1
                font = ImageFont.load_default()
            box = d.textbbox((14, 12), str(labels[i]), font=font)
            d.rectangle([box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4], fill=(255, 255, 255))
            d.text((14, 12), str(labels[i]), fill=(20, 20, 20), font=font)
        frames.append(f)
    # An adaptive 128 colour palette keeps a six frame GIF well under 1 MB.
    frames = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for f in frames]
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=int(1000 / p.get("fps", 1)), loop=0, optimize=True)


def render_chart(p: dict, out: Path) -> pd.DataFrame:
    df = to_frame(p["data"])
    fig = p["plot"](df)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return df


def live_cell(df: pd.DataFrame, plot_fn) -> str:
    """Python a reader can run in the page: the real data plus the plot function."""
    small = df.head(LIVE_MAX_ROWS)
    csv = small.to_csv(index=False, float_format="%.5g")
    src = textwrap.dedent(inspect.getsource(plot_fn))
    name = plot_fn.__name__
    return (
        "import io\nimport pandas as pd\nimport matplotlib.pyplot as plt\n\n"
        f'DATA = """{csv}"""\n'
        "df = pd.read_csv(io.StringIO(DATA))\n\n"
        f"{src}\n"
        f"{name}(df)\nplt.show()\n"
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def web_map(stem: str, layers: list[dict], compare=None) -> str | None:
    """One interactive Leaflet map per chapter script.

    Every map product becomes a toggleable image overlay on a real basemap,
    with an opacity slider. If the script names a before/after pair, a swipe
    control is added. The overlays are the rendered PNGs themselves, so the
    page keeps working after Earth Engine tile links would have expired.
    """
    if not layers:
        return None
    import folium
    from folium import plugins
    south = min(l["bounds"][0][0] for l in layers)
    west = min(l["bounds"][0][1] for l in layers)
    north = max(l["bounds"][1][0] for l in layers)
    east = max(l["bounds"][1][1] for l in layers)
    m = folium.Map(tiles=None, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="Street map").add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Satellite basemap").add_to(m)
    overlays = {}
    for i, l in enumerate(layers):
        # folium would try to embed a relative path as a file; give it a URL
        # placeholder and point it back at the sibling PNG after saving.
        ov = folium.raster_layers.ImageOverlay(
            image="https://overlay.invalid/" + l["png"], bounds=l["bounds"], name=l["title"], opacity=0.85,
            show=(i == 0), interactive=False, zindex=10 + i)
        ov.add_to(m)
        overlays[l["name"]] = ov
    if compare and all(c in overlays for c in compare):
        plugins.SideBySideLayers(layer_left=overlays[compare[0]],
                                 layer_right=overlays[compare[1]]).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    plugins.Fullscreen().add_to(m)
    m.fit_bounds([[south, west], [north, east]])
    # Opacity slider for every overlay, in plain JavaScript.
    m.get_root().html.add_child(folium.Element(
        '<div style="position:absolute;bottom:18px;left:10px;z-index:9999;background:white;'
        'padding:4px 8px;border-radius:4px;font:12px sans-serif">Overlay opacity '
        '<input type="range" min="0" max="100" value="85" oninput="'
        'document.querySelectorAll(\'.leaflet-image-layer\').forEach(function(e){'
        'e.style.opacity=this.value/100}.bind(this))"></div>'))
    path = IMG_DIR / f"{stem}-webmap.html"
    m.save(str(path))
    path.write_text(path.read_text().replace("https://overlay.invalid/", ""))
    return f"images/real/{stem}-webmap.html"


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(path: Path) -> None:
    module = load(path)
    if not hasattr(module, "products"):
        print(f"  - {path.name}: no products(), skipped")
        return
    print(f"==> {path.name}")
    WEB_LAYERS.clear()
    items = []
    for p in module.products():
        name, kind = p["name"], p["kind"]
        entry = {"name": name, "kind": kind, "caption": p.get("caption", "")}
        try:
            if kind == "map":
                render_map(p, IMG_DIR / f"{name}.jpg")     # JPEG keeps pages light
                entry["image"] = f"images/real/{name}.jpg"
            elif kind == "html":               # an interactive page, e.g. plotly
                p["build"](str(IMG_DIR / f"{name}.html"))
                entry["html"] = f"images/real/{name}.html"
                entry["height"] = p.get("height", 520)
            elif kind == "figure":             # any matplotlib figure, no Earth Engine
                fig = p["figure"]()
                fig.savefig(IMG_DIR / f"{name}.png", bbox_inches="tight")
                plt.close(fig)
                entry["image"] = f"images/real/{name}.png"
            elif kind == "animation":
                render_animation(p, IMG_DIR / f"{name}.gif")
                entry["image"] = f"images/real/{name}.gif"
            elif kind == "chart":
                df = render_chart(p, IMG_DIR / f"{name}.png")
                entry["image"] = f"images/real/{name}.png"
                if p.get("live", True):
                    entry["live"] = live_cell(df, p["plot"])
            elif kind == "table":
                df = to_frame(p["data"])
                if "transform" in p:            # e.g. scores computed locally
                    df = p["transform"](df)
                if "columns" in p:
                    df = df[list(p["columns"])]
                entry["markdown"] = df.to_markdown(index=False, floatfmt=p.get("floatfmt", ".3g"))  # str or per-column tuple
            print(f"  + {kind:5s} {name}")
        except Exception as err:            # one failed product must not sink the rest
            entry["error"] = str(err)[:300]
            print(f"  ! {kind:5s} {name}: {entry['error']}")
        items.append(entry)
    try:
        html = web_map(path.stem, list(WEB_LAYERS), getattr(module, "COMPARE", None))
        if html:
            items.insert(0, {"name": f"{path.stem}-webmap", "kind": "html", "html": html,
                             "height": 480,
                             "caption": "Interactive: pan, zoom, switch layers and basemaps, "
                                        "change the overlay opacity."})
            print(f"  + web   {path.stem}-webmap")
    except Exception as err:
        print(f"  ! web map: {err}")
    (OUT_DIR / f"{path.stem}.json").write_text(json.dumps(items, indent=1, ensure_ascii=False))


def main(argv: list[str]) -> int:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(exist_ok=True)
    sys.path.insert(0, str(PY_DIR))
    initialise()
    wanted = set(argv[1:])
    for path in sorted(PY_DIR.glob("ch*.py")):
        if wanted and path.stem not in wanted:
            continue
        run(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
