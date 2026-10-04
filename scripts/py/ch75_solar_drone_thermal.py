#| title: Solar plant inspection from a thermal drone (Python)
#| description: Every PV module in 2,500 radiometric infrared frames from a drone flight over a real PV plant is segmented, compared with its neighbours in the same frame, and flagged when it runs hot as a whole (a substring or module fault) or has a hot spot (a cell or junction-box fault); the flagged frames are mapped from the drone's GPS.

"""
CHAPTER 75 | Which modules run hot?

Data: the example flight of PV Hawk (Bommes et al.), a DJI Matrice 210 with a Zenmuse XT2 thermal camera
(640 x 512) over the first twelve rows of a large PV plant in Germany, 11 October 2021. Released with the
MIT-licensed PV Hawk repository (github.com/LukasBommes/PV-Hawk, release v1.0.0). 2,541 16-bit radiometric
frames and the drone GPS of every frame.

The values are raw camera intensities, not degrees (PV Hawk itself only normalises them), so everything here
is RELATIVE: a module is compared with the other modules in the same frame, seen at the same moment, under the
same sun, wind and angle. That is also how thermographic inspection reads a plant: by temperature
difference, not absolute temperature.

    1. modules    bright panel area (Otsu threshold), split into modules at the dark gaps between them
    2. module     median and 99th percentile of each module's pixels
    3. anomaly    whole-module: median above the frame's module median by > K robust SDs (MAD)
                  hot spot:     99th percentile above the module's own median by > H counts
    4. map        flagged frames placed at the drone's GPS position (frame accuracy, ~10 m; module-level
                  georeferencing needs PV Hawk's structure-from-motion step)
"""

import json
import os
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

URL = "https://github.com/LukasBommes/PV-Hawk/releases/download/v1.0.0/example_data_double_row.zip"
CACHE = Path(os.environ.get("PVHAWK_CACHE", Path.home() / ".cache" / "pvhawk"))
STEP = 5                 # analyse every 5th frame: consecutive frames overlap by ~95 %
K_MODULE = 4.0           # whole-module anomaly: robust z above the frame's modules
H_SPOT = 100             # hot spot: 99th percentile minus module median, in counts (chosen in sensitivity_frame)
Z_MIN = -1.0             # a module view cooler than this (robust z) is not a sunlit module
_c = {}


def data():
    """Download once (828 MB) and unzip the frames and GPS."""
    root = CACHE / "splitted"
    if not (root / "gps" / "gps.json").exists():
        CACHE.mkdir(parents=True, exist_ok=True); z = CACHE / "double_row.zip"
        if not z.exists():
            import urllib.request; urllib.request.urlretrieve(URL, z)
        zipfile.ZipFile(z).extractall(CACHE)
    frames = sorted((root / "radiometric").glob("frame_*.tiff"))
    gps = np.array(json.load(open(root / "gps" / "gps.json")))
    return frames, gps


def read(f):
    from PIL import Image
    return np.array(Image.open(f)).astype(float)


def modules(a, min_px=1500):
    """Rectangles of single modules: Otsu on the frame, then split each bright column at the dark gaps."""
    from skimage.filters import threshold_otsu
    from scipy import ndimage as ndi
    from scipy.signal import find_peaks
    bright = a > threshold_otsu(a)
    bright = ndi.binary_opening(bright, iterations=2)
    lab, n = ndi.label(bright); out = []
    for k, sl in enumerate(ndi.find_objects(lab), start=1):
        m = lab[sl] == k
        if m.sum() < 4 * min_px: continue
        comp = []
        sub = np.where(m, a[sl], np.nan)
        # split across: the panel row is two modules wide, divided by a dark vertical gap
        colp = np.nanmedian(sub, axis=0); cuts_c = [0]
        pk, _ = find_peaks(-np.nan_to_num(colp, nan=np.nanmin(colp)), distance=max(10, sub.shape[1] // 3), prominence=15)
        cuts_c += [p for p in pk if 0.25 * sub.shape[1] < p < 0.75 * sub.shape[1]][:1] + [sub.shape[1]]
        # split along: modules end at dark horizontal gaps (module frames). The rows are slightly slanted, so each
        # half of the panel row is cut on its own profile.
        for c0, c1 in zip(cuts_c[:-1], cuts_c[1:]):
            half = sub[:, c0:c1]
            rowp = np.nanpercentile(half, 30, axis=1); rowp = np.nan_to_num(rowp, nan=np.nanmin(rowp))
            rowp = rowp - ndi.uniform_filter1d(rowp, 61)             # remove the slow brightness trend
            pr, _ = find_peaks(-rowp, distance=35, prominence=6)
            cuts_r = [0] + list(pr) + [sub.shape[0]]
            for r0, r1 in zip(cuts_r[:-1], cuts_r[1:]):
                cell = sub[r0 + 3:r1 - 3, c0 + 3:c1 - 3]; v = cell[np.isfinite(cell)]
                if v.size < min_px or not (35 <= r1 - r0 <= 80) or not (55 <= c1 - c0 <= 130): continue   # module shape
                comp.append(dict(r0=sl[0].start + r0, r1=sl[0].start + r1, c0=sl[1].start + c0, c1=sl[1].start + c1,
                                med=float(np.median(v)), p99=float(np.percentile(v, 99)), n=int(v.size), row=k))
        # a module belongs to a panel row: an isolated warm blob of module size (a car, a roof) is not a module
        if len(comp) >= 4:
            out += comp
    return pd.DataFrame(out)


def scan():
    if "scan" in _c: return _c["scan"]
    frames, gps = data(); rows = []
    for i in range(0, len(frames), STEP):
        m = modules(read(frames[i]))
        if len(m) < 4: continue
        med = m.med.median(); mad = 1.4826 * np.median(np.abs(m.med - med)) + 1e-6
        m["z"] = (m.med - med) / mad; m["spot"] = m.p99 - m.med
        m["frame"] = i; m["lon"], m["lat"] = gps[min(i, len(gps) - 1)]
        rows.append(m)
    d = pd.concat(rows, ignore_index=True)
    d["hot_module"] = d.z > K_MODULE; d["hot_spot"] = d.spot > H_SPOT
    _c["scan"] = d
    return d


def events(d, thr=H_SPOT, gap=3 * STEP):
    """One physical defect is seen in many overlapping frames: chain flagged sightings whose frames are within
    `gap` of each other into one event; keep the strongest sighting and the drone position."""
    # a real module in sunlight is not cooler than its neighbours: views with z < -1 are ground or shadow that
    # slipped through the segmentation (rough texture gives them a high "spot" value)
    f = d[(d.spot > thr) & (d.z > Z_MIN)].sort_values("frame")
    if f.empty: return pd.DataFrame(columns=["event", "frame", "spot", "z", "lon", "lat", "sightings"])
    ev = (f.frame.diff() > gap).cumsum().values
    f = f.assign(event=ev)
    best = f.loc[f.groupby("event").spot.idxmax()].copy()
    best["sightings"] = f.groupby("event").size().values
    return best.reset_index(drop=True)


def sensitivity_frame():
    d = scan(); rows = []
    for thr in (60, 80, 100, 150, 200, 250, 300):
        e = events(d, thr)
        rows.append({"hot-spot threshold (counts above module median)": thr, "module views flagged": int(((d.spot > thr) & (d.z > Z_MIN)).sum()),
                     "share of views": ((d.spot > thr) & (d.z > Z_MIN)).mean(), "defects (events)": len(e),
                     "single-frame events": int((e.sightings == 1).sum()) if len(e) else 0})
    return pd.DataFrame(rows)


def plot_spot_hist(d0):
    d = scan()
    fig, ax = plt.subplots(figsize=(7, 3.3))
    ax.hist(d.spot.clip(upper=400), bins=np.arange(0, 405, 5), color="#9aa5b1")
    ax.set_yscale("log"); ax.axvline(H_SPOT, color="#c0392b", lw=1.5)
    ax.text(H_SPOT + 5, ax.get_ylim()[1] * 0.3, f" threshold {H_SPOT}", color="#c0392b", fontsize=8)
    ax.set_xlabel("hot-spot strength: module 99th percentile minus module median (camera counts)")
    ax.set_ylabel("module views (log)"); ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Healthy modules form one hump; defects sit far out in the tail", loc="left", fontsize=10)
    fig.tight_layout()
    return fig


def figure_events():
    d = scan(); e = events(d); frames, _ = data()
    n = len(e); cols = min(n, 5); rows = int(np.ceil(n / cols)) if n else 1
    fig, axes = plt.subplots(rows, cols, figsize=(2.6 * cols, 2.4 * rows), squeeze=False)
    for ax in axes.ravel(): ax.set_axis_off()
    for k, (_, r) in enumerate(e.iterrows()):
        a = read(frames[int(r.frame)]); y0, y1, x0, x1 = max(0, int(r.r0) - 30), int(r.r1) + 30, max(0, int(r.c0) - 30), int(r.c1) + 30
        ax = axes.ravel()[k]; ax.imshow(a[y0:y1, x0:x1], cmap="inferno", vmin=np.percentile(a, 5), vmax=np.percentile(a, 99.95))
        ax.add_patch(plt.Rectangle((r.c0 - x0, r.r0 - y0), r.c1 - r.c0, r.r1 - r.r0, fill=False, ec="cyan", lw=1))
        ax.set_title(f"defect {k + 1}: +{r.spot:.0f} counts\nseen in {int(r.sightings)} frames", fontsize=7.5)
    fig.suptitle("Every hot-spot defect found (strongest sighting, module outlined)", x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    return fig


def figure_map():
    d = scan(); e = events(d); _, gps = data()
    lon, lat = gps[:, 0], gps[:, 1]; kx = 111320 * np.cos(np.radians(lat.mean()))
    fig, ax = plt.subplots(figsize=(7.4, 5.2))
    ax.plot(lon, lat, color="#9aa5b1", lw=1, label="drone track (one GPS fix per frame)")
    ax.scatter(e.lon, e.lat, s=90, color="#c0392b", edgecolor="black", zorder=3, label=f"hot-spot defects ({len(e)})")
    for k, (_, r) in enumerate(e.iterrows()):
        ax.annotate(str(k + 1), (r.lon, r.lat), xytext=(5, 4), textcoords="offset points", fontsize=8)
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    ax.xaxis.set_major_locator(MaxNLocator(4)); ax.yaxis.set_major_locator(MaxNLocator(4))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.4f}°E")); ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.4f}°N"))
    ax.grid(True, ls="--", lw=0.4, color="#cccccc"); ax.set_aspect(1 / np.cos(np.radians(lat.mean())))
    x0 = lon.min() + 0.05 * np.ptp(lon); y0 = lat.min() + 0.04 * np.ptp(lat)
    ax.plot([x0, x0 + 20 / kx], [y0, y0], color="black", lw=3); ax.text(x0, y0 + 0.03 * np.ptp(lat), "20 m", fontsize=8)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, frameon=False)
    ax.set_title("Where to send the technician: defects at the drone position (frame accuracy, about 10 m)", loc="left", fontsize=9.5)
    fig.tight_layout()
    return fig


def products():
    return [
        {"kind": "chart", "name": "ch75-spot-hist", "data": lambda: scan()[["spot"]].head(5), "plot": plot_spot_hist, "live": False,
         "caption": "Hot-spot strength of every module view (16,000 views of modules in 447 frames), log scale."},
        {"kind": "table", "name": "ch75-threshold", "data": sensitivity_frame, "floatfmt": (",.0f", ",.0f", ".2%", ",.0f", ",.0f"),
         "caption": "How many defects each threshold finds. Repeated sightings of one module in overlapping frames are one event."},
        {"kind": "figure", "name": "ch75-events", "figure": figure_events,
         "caption": "Each defect at its strongest sighting, in raw radiometric counts (PV Hawk example flight, MIT licence)."},
        {"kind": "figure", "name": "ch75-map", "figure": figure_map,
         "caption": "The flight track and the defects, placed at the drone's GPS position."},
    ]
