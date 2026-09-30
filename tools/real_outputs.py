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
        cmap = LinearSegmentedColormap.from_list(
            "p", ["#" + c.lstrip("#") for c in vis["palette"]])
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
    items = []
    for p in module.products():
        name, kind = p["name"], p["kind"]
        entry = {"name": name, "kind": kind, "caption": p.get("caption", "")}
        try:
            if kind == "map":
                render_map(p, IMG_DIR / f"{name}.jpg")     # JPEG keeps pages light
                entry["image"] = f"images/real/{name}.jpg"
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
