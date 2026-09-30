#| title: Energy, waves and the atmosphere (Python)
#| description: Planck curves for the Sun and the Earth, the numbers behind wavelength, frequency and photon energy, and the atmosphere measured directly by comparing top-of-atmosphere and surface reflectance from the same Sentinel-2 scene.

"""
PRINCIPLES P1 | Every remote sensing measurement starts as electromagnetic
energy. Three things decide what a sensor can see:

    where the energy comes from     the Sun (about 6,000 K) or the Earth (about 300 K)
    what the atmosphere lets through  windows and absorption bands
    what the surface does with it     reflect, absorb, transmit, emit

The figures here are computed from physics (Planck's law), and the atmosphere
is measured from a real scene: Sentinel-2 Level-1C (top of atmosphere) and
Level-2A (surface) for the same overpass.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

H, C, K = 6.62607015e-34, 2.99792458e8, 1.380649e-23      # Planck, light speed, Boltzmann
WIEN = 2897.771955                                        # µm·K


def planck(wl_um, t):
    """Spectral radiance, W m-2 sr-1 µm-1."""
    wl = wl_um * 1e-6
    return 2 * H * C ** 2 / wl ** 5 / (np.exp(H * C / (wl * K * t)) - 1) * 1e-6


# ---------------------------------------------------------------------------
# 1. Two blackbodies: why optical sensors see reflected sunlight and thermal
#    sensors see the Earth's own glow
# ---------------------------------------------------------------------------
def planck_figure():
    wl = np.logspace(-1, 2, 600)                                   # 0.1 to 100 µm
    sun = planck(wl, 5800) * (6.957e8 / 1.496e11) ** 2 * np.pi    # at the top of the atmosphere
    earth = planck(wl, 300) * np.pi                               # leaving the surface
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.loglog(wl, sun, color="#e69f00", lw=2.2, label="Sunlight arriving at Earth (Sun ≈ 5,800 K)")
    ax.loglog(wl, earth, color="#c0392b", lw=2.2, label="Earth's own emission (≈ 300 K)")
    for t, col in [(5800, "#e69f00"), (300, "#c0392b")]:
        pk = WIEN / t
        ax.axvline(pk, color=col, ls=":", lw=1)
        ax.text(pk * 1.05, 5e-2, f"peak {pk:.2f} µm", color=col, fontsize=8, rotation=90,
                va="bottom")
    bands = [("blue–red", 0.45, 0.68, "#9ecae1"), ("NIR", 0.85, 0.88, "#a1d99b"),
             ("SWIR", 1.57, 2.29, "#fdd0a2"), ("thermal", 10.6, 12.5, "#fcbba1")]
    for name, lo, hi, col in bands:
        ax.axvspan(lo, hi, color=col, alpha=0.6, lw=0)
        ax.text(np.sqrt(lo * hi), 3e3, name, ha="center", fontsize=8)
    ax.set_ylim(1e-3, 1e4)
    ax.set_xlabel("Wavelength (µm, log scale)")
    ax.set_ylabel("Spectral irradiance (W m⁻² µm⁻¹)")
    ax.set_title("The curves cross near 4 to 5 µm: below it the Sun dominates, above it "
                 "the Earth does", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    ax.text(0.99, -0.16, "Computed from Planck's law. Shaded: Landsat 8/9 band regions.",
            transform=ax.transAxes, ha="right", fontsize=7, color="#6b7680")
    return fig


def spectrum_table():
    rows = [("Blue (Landsat 8 band 2)", 0.48e-6), ("Red (band 4)", 0.655e-6),
            ("Near infrared (band 5)", 0.865e-6), ("Shortwave infrared (band 6)", 1.61e-6),
            ("Thermal infrared (band 10)", 10.9e-6), ("X-band radar (TerraSAR-X)", 0.031),
            ("C-band radar (Sentinel-1)", 0.0555), ("L-band radar (ALOS-2)", 0.236)]
    out = []
    for name, wl in rows:
        f = C / wl
        out.append({"region": name, "wavelength": (f"{wl * 1e6:.3g} µm" if wl < 1e-3
                                                   else f"{wl * 100:.3g} cm"),
                    "frequency_GHz": f / 1e9, "photon_energy_eV": H * f / 1.602176634e-19})
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# 2. The atmosphere, measured: the same Sentinel-2 overpass before and after
#    atmospheric correction
# ---------------------------------------------------------------------------
site = ee.Geometry.Rectangle([106.81, -6.30, 107.05, -6.05], None, False)     # Jakarta

# One clear overpass, and one tile (48MYU) so the whole box is in the scene.
sr = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(site)
      .filterDate("2023-05-01", "2024-11-01")
      .filter(ee.Filter.eq("MGRS_TILE", "48MYU"))
      .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 5))
      .sort("CLOUDY_PIXEL_PERCENTAGE").first())
toa = ee.Image(ee.ImageCollection("COPERNICUS/S2_HARMONIZED")
               .filter(ee.Filter.eq("system:index", sr.get("system:index"))).first())

BANDS = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]
CENTRE = [0.443, 0.490, 0.560, 0.665, 0.705, 0.740, 0.783, 0.842, 0.865, 1.610, 2.190]
TRUE = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 2500, "gamma": 1.1}


def band_means():
    a = toa.select(BANDS).reduceRegion(ee.Reducer.mean(), site, 60, maxPixels=1e9)
    b = sr.select(BANDS).reduceRegion(ee.Reducer.mean(), site, 60, maxPixels=1e9)
    a, b = a.getInfo(), b.getInfo()
    return pd.DataFrame({"band": BANDS, "centre_um": CENTRE,
                         "toa": [a[x] / 1e4 for x in BANDS],
                         "surface": [b[x] / 1e4 for x in BANDS]})


def plot_atmosphere(df):
    d = df.assign(added=df["toa"] - df["surface"])
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.8))
    a.plot(d.centre_um, d.toa, "o-", color="#6b7680", label="top of atmosphere (L1C)")
    a.plot(d.centre_um, d.surface, "o-", color="#1b7837", label="surface (L2A)")
    a.set_xlabel("Band centre (µm)"); a.set_ylabel("Mean reflectance")
    a.set_title("Same pixels, same minute, two answers", loc="left", fontsize=10)
    a.legend(frameon=False, fontsize=8)
    vis = d[d.centre_um < 0.9]
    b.bar(vis.band, vis.added, color="#2a78d6")
    ref = vis.added.iloc[0] * (vis.centre_um.iloc[0] / vis.centre_um) ** 4
    b.plot(vis.band, ref, color="#c0392b", lw=1.5, label="λ⁻⁴ (pure Rayleigh), scaled to B1")
    b.set_ylabel("TOA minus surface")
    b.set_title("The atmosphere adds most in the blue", loc="left", fontsize=10)
    b.legend(frameon=False, fontsize=8)
    b.tick_params(axis="x", labelsize=7)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 3. Emitted, not reflected: radiant temperature depends on emissivity
# ---------------------------------------------------------------------------
def emissivity_figure():
    eps = np.linspace(0.90, 1.0, 50)
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for tk, col in [(300, "#2a78d6"), (320, "#c0392b")]:
        ax.plot(eps, eps ** 0.25 * tk - 273.15, color=col, lw=2,
                label=f"true (kinetic) temperature {tk - 273.15:.0f} °C")
    ax.set_xlabel("Emissivity ε")
    ax.set_ylabel("Radiant temperature a sensor sees (°C)")
    ax.set_title("Same true temperature, lower emissivity, cooler-looking surface",
                 loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    ax.text(0.99, -0.22, "T_radiant = ε^¼ × T_kinetic (Stefan–Boltzmann)",
            transform=ax.transAxes, ha="right", fontsize=7, color="#6b7680")
    return fig


# ---------------------------------------------------------------------------
# 4. A schematic: how a surface returns light, and the paths to the sensor
# ---------------------------------------------------------------------------
def paths_figure():
    from matplotlib.patches import FancyArrowPatch, Rectangle
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8))

    def arrow(ax, a, b, col="#e69f00", lw=1.8, ls="-"):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, color=col,
                                     lw=lw, ls=ls))

    for ax in axes:
        ax.set_xlim(0, 10); ax.set_ylim(0, 8); ax.set_axis_off(); ax.set_aspect("equal")
    # (a) specular
    a = axes[0]
    a.add_patch(Rectangle((0.5, 0.6), 9, 0.5, color="#4a90c2"))
    arrow(a, (1.5, 6.5), (5, 1.1)); arrow(a, (5, 1.1), (8.5, 6.5), col="#c0392b")
    a.plot([5, 5], [1.1, 6.8], color="#6b7680", ls=":", lw=1)
    a.text(5, 7.2, "angle in = angle out", ha="center", fontsize=8)
    a.set_title("(a) Specular: calm water, a mirror", loc="left", fontsize=9)
    # (b) diffuse
    b = axes[1]
    xs = np.linspace(0.5, 9.5, 40)
    b.fill_between(xs, 0.6, 1.1 + 0.25 * np.sin(xs * 5), color="#8c6d46")
    arrow(b, (1.5, 6.5), (5, 1.2))
    for ang in np.radians([25, 50, 75, 90, 105, 130, 155]):
        arrow(b, (5, 1.3), (5 + 3.2 * np.cos(ang), 1.3 + 3.2 * np.sin(ang)), col="#c0392b",
              lw=1.2)
    b.set_title("(b) Diffuse: rough soil, a canopy", loc="left", fontsize=9)
    # (c) the paths that reach a sensor
    c = axes[2]
    c.add_patch(Rectangle((0.3, 0.6), 4.5, 0.5, color="#1b7837"))
    c.add_patch(Rectangle((4.8, 0.6), 4.9, 0.5, color="#8c6d46"))
    c.add_patch(Rectangle((7.8, 6.8), 1.2, 0.7, color="#34495e"))
    c.text(8.4, 7.7, "sensor", ha="center", fontsize=8)
    arrow(c, (0.6, 7.6), (2.6, 1.2)); arrow(c, (2.6, 1.2), (8.1, 6.8), col="#c0392b")
    c.text(3.2, 2.4, "1", fontsize=9, weight="bold", color="#c0392b")
    arrow(c, (3.2, 7.8), (4.6, 5.6)); arrow(c, (4.6, 5.6), (7.8, 7.0), col="#2a78d6", ls="--")
    c.text(4.2, 5.2, "2", fontsize=9, weight="bold", color="#2a78d6")
    arrow(c, (6.0, 1.2), (8.6, 6.8), col="#8e44ad", ls="-.")
    c.text(7.3, 3.2, "3", fontsize=9, weight="bold", color="#8e44ad")
    c.set_title("(c) What the sensor adds up", loc="left", fontsize=9)
    c.text(0.3, -0.5, "1 light from the pixel   2 path radiance (scattered by air)\n"
                      "3 light from neighbouring pixels (adjacency)", fontsize=7.5,
           va="top")
    fig.tight_layout()
    return fig


def products():
    return [
        {"kind": "figure", "name": "p1-planck", "figure": planck_figure,
         "caption": "Sunlight reaching the Earth and the Earth's own emission, both from "
                    "Planck's law. Optical bands (blue to SWIR) sit where reflected sunlight "
                    "is strong; the thermal band sits where the Earth's own glow is strong."},
        {"kind": "figure", "name": "p1-paths", "figure": paths_figure,
         "caption": "Specular and diffuse reflection, and the three kinds of light a "
                    "sensor adds together. Atmospheric correction tries to remove 2 and 3 "
                    "and keep 1."},
        {"kind": "table", "name": "p1-spectrum", "data": spectrum_table,
         "floatfmt": ("", "", ",.1f", ".3g"),
         "caption": "Wavelength, frequency and photon energy are three names for one "
                    "property (c = λf, E = hf). Radar photons carry about a hundred-"
                    "thousandth of the energy of blue light."},
        {"kind": "map", "name": "p1-toa", "image": toa.clip(site), "region": site, "vis": TRUE,
         "title": "Top of atmosphere (Level-1C)", "source": "Sentinel-2 L1C. GEE.",
         "caption": "Jakarta as the sensor recorded it, through the atmosphere."},
        {"kind": "map", "name": "p1-sr", "image": sr.clip(site), "region": site, "vis": TRUE,
         "title": "Surface reflectance (Level-2A)", "source": "Sentinel-2 L2A. GEE.",
         "caption": "The same overpass after atmospheric correction, same colour stretch. "
                    "The haze and the blue cast are gone."},
        {"kind": "chart", "name": "p1-atmosphere", "data": band_means, "plot": plot_atmosphere,
         "caption": "Mean reflectance over the scene before and after correction (left) "
                    "and top-of-atmosphere minus surface in each band (right). In the "
                    "blue the atmosphere adds light scattered into the sensor, falling "
                    "off with wavelength as Rayleigh scattering predicts. From the red "
                    "edge on the sign flips: there the atmosphere mostly removes light "
                    "(absorption and scattering out of the beam), so correction raises "
                    "the values."},
        {"kind": "figure", "name": "p1-emissivity", "figure": emissivity_figure,
         "caption": "A thermal sensor measures radiance, not temperature. Two surfaces at "
                    "the same true temperature look different if their emissivity differs."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(band_means())
