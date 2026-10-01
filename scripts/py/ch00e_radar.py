#| title: Radar basics (Python)
#| description: Side-looking geometry, range and azimuth resolution, foreshortening, layover and shadow computed from a hill profile, Sentinel-1 ascending and descending over Rinjani, speckle, and backscatter by land cover.

"""
PRINCIPLES P5 | Imaging radar, from the geometry up.

    range (across track)    slant-range resolution  = c τ / 2   (pulse length τ)
                            ground-range resolution = slant / sin θ   (θ incidence)
    azimuth (along track)   real aperture           = λ R / L   (antenna length L)
                            synthetic aperture      ≈ L / 2

Distortions come from one fact: radar places every echo by its distance
from the antenna, not by its position on the map.
"""

import io

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from matplotlib.patches import FancyArrowPatch, Polygon
from PIL import Image

C = 2.99792458e8


# ---------------------------------------------------------------------------
# 1. Side-looking geometry, drawn
# ---------------------------------------------------------------------------
def geometry_figure():
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.set_xlim(-1, 11); ax.set_ylim(-1.2, 7.4); ax.set_aspect("equal"); ax.set_axis_off()
    ax.fill_between([-1, 11], -1.2, 0, color="#eef2e6")
    s = (0.5, 6.4)
    ax.plot(*s, "s", color="#34495e", ms=12)
    ax.text(s[0] - 0.2, s[1] + 0.45, "radar, flying into the page", fontsize=8)
    ax.plot([0.5, 0.5], [6.2, 0], color="#6b7680", ls=":", lw=1)
    ax.text(0.6, 0.15, "nadir", fontsize=8, color="#6b7680")
    near, far = 3.2, 9.6
    beam = Polygon([s, (near, 0), (far, 0)], color="#2a78d6", alpha=0.12)
    ax.add_patch(beam)
    for x, lab in [(near, "near range"), (far, "far range")]:
        ax.plot([s[0], x], [s[1], 0], color="#2a78d6", lw=1)
        ax.text(x, -0.45, lab, ha="center", fontsize=8)
    mid = (near + far) / 2
    ax.plot([s[0], mid], [s[1], 0], color="#c0392b", lw=1.6)
    ax.text(3.6, 3.6, "slant range", color="#c0392b", fontsize=9, rotation=-33)
    ax.add_patch(FancyArrowPatch((near, -0.85), (far, -0.85), arrowstyle="<|-|>",
                                 mutation_scale=10, color="#1f2933"))
    ax.text(mid, -1.1, "swath (ground range)", ha="center", fontsize=8)
    # angles
    th = np.degrees(np.arctan((mid - s[0]) / s[1]))
    arc = np.radians(np.linspace(-90, -90 + th, 30))
    ax.plot(s[0] + 1.2 * np.cos(arc), s[1] + 1.2 * np.sin(arc), color="#8e44ad")
    ax.text(0.3, 4.9, "look\nangle", fontsize=8, color="#8e44ad", ha="right")
    arc2 = np.radians(np.linspace(90, 90 + th, 30))
    ax.plot(mid + 1.0 * np.cos(arc2), 1.0 * np.sin(arc2), color="#e67e22")
    ax.plot([mid, mid], [0, 1.4], color="#e67e22", ls=":", lw=1)
    ax.text(mid - 1.5, 1.25, "incidence\nangle", fontsize=8, color="#e67e22")
    arc3 = np.radians(np.linspace(-th - 90 + 90, 0, 30)) - np.pi
    ax.plot(s[0] + 1.6 * np.cos(np.radians(np.linspace(-(90 - th), 0, 30))),
            s[1] + 1.6 * np.sin(np.radians(np.linspace(-(90 - th), 0, 30))), color="#1b7837")
    ax.plot([s[0], s[0] + 2.2], [s[1], s[1]], color="#1b7837", ls=":", lw=1)
    ax.text(2.25, 6.05, "depression angle", fontsize=8, color="#1b7837")
    ax.set_title("Side-looking radar: range is across track, azimuth is along track",
                 loc="left", fontsize=10)
    return fig


# ---------------------------------------------------------------------------
# 2. Resolution: range gets better far out; azimuth needs a synthetic aperture
# ---------------------------------------------------------------------------
def resolution_figure():
    bw = 56.5e6                                     # pulse bandwidth, Hz (a C-band example)
    slant = C / (2 * bw)
    inc = np.linspace(15, 50, 100)
    ground = slant / np.sin(np.radians(inc))
    R = np.linspace(500e3, 1200e3, 100)
    lam, L = 0.0555, 12.3                           # C-band, Sentinel-1 antenna length
    real = lam * R / L
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.7))
    a.plot(inc, ground, color="#2a78d6", lw=2, label="ground-range resolution")
    a.axhline(slant, color="#6b7680", ls="--", lw=1, label=f"slant-range resolution {slant:.1f} m")
    a.set_xlabel("Incidence angle (°)"); a.set_ylabel("Resolution (m)")
    a.set_title("Range: worse at near range, better at far range", loc="left", fontsize=10)
    a.legend(frameon=False, fontsize=8)
    b.semilogy(R / 1e3, real, color="#c0392b", lw=2, label="real aperture  λR/L")
    b.semilogy(R / 1e3, np.full_like(R, L / 2), color="#1b7837", lw=2,
               label=f"synthetic aperture  L/2 = {L / 2:.2f} m")
    b.set_xlabel("Distance to target, slant range (km)"); b.set_ylabel("Azimuth resolution (m)")
    b.set_title("Azimuth: the synthetic aperture removes the distance", loc="left",
                fontsize=10)
    b.legend(frameon=False, fontsize=8)
    b.text(0.99, -0.22, f"C-band λ = 5.55 cm, antenna L = 12.3 m, bandwidth 56.5 MHz",
           transform=b.transAxes, ha="right", fontsize=7, color="#6b7680")
    fig.tight_layout()
    return fig


def bands_table():
    rows = [("X", 0.031, "TerraSAR-X, COSMO-SkyMed, ICEYE"), ("C", 0.0555, "Sentinel-1, RADARSAT"),
            ("S", 0.094, "NISAR (S-band)"), ("L", 0.236, "ALOS-2 PALSAR-2, NISAR (L-band)"),
            ("P", 0.69, "BIOMASS")]
    return pd.DataFrame([{"band": b, "wavelength_cm": w * 100, "frequency_GHz": C / w / 1e9,
                          "example_missions": m} for b, w, m in rows])


# ---------------------------------------------------------------------------
# 3. Foreshortening, layover and shadow, computed from a hill profile
# ---------------------------------------------------------------------------
def distortion_figure(theta_deg=35.0):
    th = np.radians(theta_deg)
    # A ground profile, radar to the left: a gentle hill, then a steep one.
    x = np.array([0, 2, 4, 5, 7, 8.2, 8.9, 11, 13])
    z = np.array([0, 0, 1.0, 0, 0, 2.6, 0, 0, 0])
    labels = ["", "A", "B", "C", "D", "E", "F", "", ""]
    fx = np.linspace(0, 13, 1301)
    fz = np.interp(fx, x, z)
    # Slant-range position: distance along the look direction (plane wave from the left).
    r = fx * np.sin(th) - fz * np.cos(th)
    # A point is in shadow if some point nearer the radar rises above its ray.
    hidden = np.array([np.any(fz[:i] > fz[i] + (fx[i] - fx[:i]) / np.tan(th) + 1e-9)
                       for i in range(len(fx))])
    fig, (a, b) = plt.subplots(2, 1, figsize=(10, 5.2),
                               gridspec_kw={"height_ratios": [1.5, 1]})
    a.fill_between(fx, -0.4, fz, color="#d8cfb4")
    a.plot(fx, np.where(hidden, fz, np.nan), color="black", lw=4, label="in radar shadow")
    for xi, zi, lab in zip(x, z, labels):
        if lab:
            a.text(xi, zi + 0.2, lab, ha="center", fontsize=9, weight="bold")
    for x0 in np.arange(-3, 12, 1.2):
        a.annotate("", (x0 + 3.2 * np.sin(th), 3.6 - 3.2 * np.cos(th)), (x0, 3.6),
                   arrowprops={"arrowstyle": "->", "color": "#2a78d6", "lw": 0.7})
    a.set_xlim(-0.5, 13); a.set_ylim(-0.4, 3.9); a.set_aspect("equal"); a.set_axis_off()
    a.set_title(f"Ground profile, radar beam from the left at {theta_deg:.0f}° incidence",
                loc="left", fontsize=10)
    a.legend(frameon=False, fontsize=8, loc="upper right")
    # The same points as the radar sees them, ordered by slant range.
    rp = x * np.sin(th) - z * np.cos(th)
    b.axhline(0, color="#1f2933", lw=1)
    # Shadow in the image: the slant-range gap that no visible point fills.
    iE = int(np.argmin(np.abs(fx - x[5])))
    after = np.where(~hidden[iE + 1:])[0]
    if after.size:
        i_end = iE + 1 + after[0]
        r_end = r[i_end]
        r_lo = r[:i_end][~hidden[:i_end]].max()
        b.axvspan(r_lo, r_end, ymin=0.3, ymax=0.7, color="#1f2933", alpha=0.85)
        b.text((r_lo + r_end) / 2, -0.42, "shadow: no echo", ha="center", fontsize=8)
    for xi, rpi, lab in zip(x, rp, labels):
        if lab:
            k = int(np.argmin(np.abs(fx - xi)))
            if hidden[k]:
                continue                                   # a hidden point returns nothing
            b.plot(rpi, 0, "o", color="#c0392b", zorder=3)
            b.text(rpi, 0.18, lab, ha="center", fontsize=9, weight="bold")
    b.annotate("A-B squeezed", ((rp[1] + rp[2]) / 2, -0.05), xytext=((rp[1] + rp[2]) / 2, -0.45),
               ha="center", fontsize=8, arrowprops={"arrowstyle": "-", "lw": 0.6})
    b.annotate("E arrives before D", (rp[5], 0), xytext=(rp[5] - 1.6, 0.42), fontsize=8,
               arrowprops={"arrowstyle": "->", "lw": 0.6})
    b.set_ylim(-0.6, 0.6); b.set_yticks([])
    b.set_xlabel("Position in the radar image (slant range)")
    b.set_title("In the image: foreshortening (A-B), layover (E before D), shadow (behind E)",
                loc="left", fontsize=10)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 4. Real Sentinel-1: ascending and descending over Rinjani, Lombok
# ---------------------------------------------------------------------------
rinjani = ee.Geometry.Rectangle([116.25, -8.55, 116.65, -8.25], None, False)
s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(rinjani)
      .filterDate("2023-01-01", "2024-01-01")
      .filter(ee.Filter.eq("instrumentMode", "IW"))
      .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")))
asc = s1.filter(ee.Filter.eq("orbitProperties_pass", "ASCENDING")).select("VV").mean()
desc = s1.filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING")).select("VV").mean()
VV = {"min": -18, "max": 2}


# ---------------------------------------------------------------------------
# 5. Speckle: one date against the mean of many dates
# ---------------------------------------------------------------------------
karawang = ee.Geometry.Rectangle([107.28, -6.33, 107.38, -6.26], None, False)
s1k = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(karawang)
       .filterDate("2023-06-01", "2023-10-01").filter(ee.Filter.eq("instrumentMode", "IW"))
       .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING")).select("VV"))


def speckle_figure():
    one = ee.Image(s1k.first())
    lin = s1k.map(lambda i: ee.Image(10).pow(i.divide(10)))
    many = lin.mean().log10().multiply(10)
    filt = one.focalMedian(1.5, "square", "pixels")
    n = s1k.size().getInfo()
    panels = [("One date", one), ("One date, 3 × 3 median filter", filt),
              (f"Mean of {n} dates (linear power)", many)]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.9))
    for ax, (t, img) in zip(axes, panels):
        url = img.visualize(min=-20, max=0).getThumbURL(
            {"region": karawang, "dimensions": 520, "format": "png"})
        ax.imshow(np.array(Image.open(io.BytesIO(requests.get(url, timeout=300).content))
                           .convert("RGB")))
        ax.set_title(t, loc="left", fontsize=9); ax.set_axis_off()
    fig.suptitle("Sentinel-1 VV over rice fields and villages near Karawang, 2023 dry season",
                 x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 6. What scatters how: backscatter by land cover
# ---------------------------------------------------------------------------
jkt = ee.Geometry.Rectangle([107.20, -6.65, 107.50, -6.35], None, False)   # Jatiluhur, Purwakarta
s1j = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(jkt)
       .filterDate("2023-06-01", "2023-10-01").filter(ee.Filter.eq("instrumentMode", "IW"))
       .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")))
db_mean = (s1j.select(["VV", "VH"]).map(lambda i: ee.Image(10).pow(i.divide(10))).mean()
           .log10().multiply(10))
dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(jkt)
      .filterDate("2023-06-01", "2023-10-01").select("label").mode())
NAMES = {0: "water", 1: "trees", 4: "crops", 6: "built"}
samples = (db_mean.addBands(dw.rename("cls"))
           .updateMask(dw.remap([0, 1, 4, 6], [1, 1, 1, 1], 0))
           .stratifiedSample(numPoints=400, classBand="cls", region=jkt, scale=20, seed=3,
                             dropNulls=True, tileScale=4))


def plot_backscatter(df):
    df = df.assign(cover=df["cls"].astype(int).map(NAMES))
    order = ["water", "crops", "trees", "built"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for ax, pol in zip(axes, ["VV", "VH"]):
        ax.boxplot([df.loc[df.cover == c, pol] for c in order], vert=False, tick_labels=order,
                   showfliers=False, widths=0.55, medianprops={"color": "#c0392b", "lw": 2})
        ax.set_xlabel(f"{pol} backscatter (dB)")
        ax.set_title(f"{pol}", loc="left", fontsize=10)
    fig.suptitle("Calm water is darkest; buildings (double bounce) are brightest in VV; "
                 "in VH, trees catch up with buildings (volume scattering)", x=0.01,
                 ha="left", fontsize=10)
    fig.tight_layout()
    return fig


def backscatter_table(df):
    df = df.assign(cover=df["cls"].astype(int).map(NAMES))
    g = df.groupby("cover")
    out = pd.DataFrame({"samples": g.size(), "VV_median_dB": g["VV"].median(),
                        "VH_median_dB": g["VH"].median()})
    out["VV_minus_VH_dB"] = out["VV_median_dB"] - out["VH_median_dB"]
    return out.reindex(["water", "crops", "trees", "built"]).reset_index()


def products():
    return [
        {"kind": "figure", "name": "p5-geometry", "figure": geometry_figure,
         "caption": "Imaging radar looks to one side. Near range is closest to the ground "
                    "track, far range farthest. The look angle is measured at the radar from "
                    "the vertical; the incidence angle at the ground from the vertical "
                    "(equal on flat ground if the Earth's curvature is ignored); the "
                    "depression angle at the radar from the horizontal."},
        {"kind": "table", "name": "p5-bands", "data": bands_table,
         "floatfmt": ("", ".1f", ".2f", ""),
         "caption": "Radar bands still carry the letter codes of wartime secrecy. Longer "
                    "wavelengths penetrate deeper into canopy, soil and dry snow."},
        {"kind": "figure", "name": "p5-resolution", "figure": resolution_figure,
         "caption": "Left: ground-range resolution is the slant-range resolution divided by "
                    "the sine of the incidence angle, so it is coarser at near range. "
                    "Right: a real antenna's azimuth resolution grows with distance "
                    "(kilometres from orbit); a synthetic aperture makes it about half the "
                    "antenna length, independent of distance."},
        {"kind": "figure", "name": "p5-distortions", "figure": distortion_figure,
         "caption": "Computed from the hill profile. Points are placed in the image by their "
                    "distance from the radar. The gentle slope A-B is squeezed "
                    "(foreshortening); the top E of the steep hill arrives before its foot D "
                    "(layover); the back slope beyond E, including F, hides behind the "
                    "summit and leaves a gap in the image (shadow)."},
        {"kind": "map", "name": "p5-ascending", "image": asc.clip(rinjani), "region": rinjani,
         "vis": VV, "legend": "VV backscatter, mean of 2023 (dB)",
         "title": "Rinjani, Sentinel-1 ascending", "source": "Sentinel-1 GRD. GEE.",
         "caption": "Ascending passes fly north and look east (right-looking). Slopes facing "
                    "west, towards the radar, are bright and squeezed; slopes facing away "
                    "are dark."},
        {"kind": "map", "name": "p5-descending", "image": desc.clip(rinjani),
         "region": rinjani, "vis": VV, "legend": "VV backscatter, mean of 2023 (dB)",
         "title": "Rinjani, Sentinel-1 descending", "source": "Sentinel-1 GRD. GEE.",
         "caption": "Descending passes fly south and look west. The bright and dark sides of "
                    "the volcano swap. Using both passes fills in what one pass hides."},
        {"kind": "figure", "name": "p5-speckle", "figure": speckle_figure,
         "caption": "Speckle: the grainy pattern of a single radar image. A spatial filter "
                    "smooths it at the cost of detail; averaging many dates (in linear power, "
                    "then back to dB) reduces it while keeping edges."},
        {"kind": "chart", "name": "p5-backscatter", "data": samples, "plot": plot_backscatter,
         "caption": "Backscatter of 400 random pixels per class (Dynamic World 2023), "
                    "Jatiluhur reservoir and Purwakarta, dry-season mean."},
        {"kind": "table", "name": "p5-backscatter-table", "data": samples,
         "transform": backscatter_table, "floatfmt": ("", ".0f", ".1f", ".1f", ".1f"),
         "caption": "Median backscatter by class. Among land covers the VV minus VH gap is "
                    "smallest for trees, because volume scattering in the canopy "
                    "depolarises the signal. Water's small gap is not physics: its VH is "
                    "at the sensor's noise floor (about -22 to -25 dB)."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(samples.size().getInfo())
