#| title: How sensors scan (Python)
#| description: Whisk broom, push broom and frame cameras drawn side by side; IFOV, swath and dwell time computed for real sensors; SPOT's off-nadir pointing; and Landsat 7's failed scan line corrector seen in a real image.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
PRINCIPLES P3 | Turning a moving satellite into a two-dimensional image.

    along track   the platform moves forward: one new line after another
    across track  something must build each line:
                  a swinging mirror (whisk broom, object-plane scanning), or
                  a row of detectors (push broom, image-plane scanning)

    ground pixel (GSD)  ≈ H × β        β = angular IFOV in radians
    swath               = 2 H tan(FOV / 2)
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, Polygon, Rectangle

GROUND_SPEED = 6.75e3          # m/s at 705 km (Chapter P2)


# ---------------------------------------------------------------------------
# 1. Three ways to build an image, drawn
# ---------------------------------------------------------------------------
def _arrow(ax, a, b, col="#1f2933", lw=1.4, ms=10):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=ms, color=col, lw=lw))


def scanning_figure():
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.6))
    for ax in axes:
        ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.set_aspect("equal"); ax.set_axis_off()

    # (a) whisk broom: one detector, a swinging mirror, a zig-zag on the ground
    a = axes[0]
    a.add_patch(Rectangle((4.3, 8.4), 1.4, 0.8, color="#34495e"))
    a.text(5, 9.5, "scan mirror swings", ha="center", fontsize=8)
    a.add_patch(Polygon([[0.5, 0.5], [9.5, 0.5], [9.5, 5.2], [0.5, 5.2]], color="#eef2e6"))
    ys = np.linspace(1.0, 4.6, 7)
    for k, y in enumerate(ys):
        xs = np.linspace(1.0, 9.0, 9)
        a.plot(xs, np.full_like(xs, y), "o", ms=3.5, color="#1b7837")
        if k < len(ys) - 1:
            a.plot([9.0, 1.0], [y, ys[k + 1]], color="#c0392b", lw=0.6, ls=":")
    a.plot([5, 1.0], [8.4, 4.6], color="#c0392b", lw=1)
    a.plot([5, 9.0], [8.4, 4.6], color="#c0392b", lw=1)
    _arrow(a, (1.6, 5.6), (8.4, 5.6), col="#c0392b")
    a.text(5, 5.85, "across track: pixel by pixel", ha="center", fontsize=8, color="#c0392b")
    _arrow(a, (0.3, 1.2), (0.3, 4.6))
    a.text(0.05, 2.9, "flight", rotation=90, va="center", fontsize=8)
    a.set_title("(a) Whisk broom (line scanning)\nLandsat 1-7, MODIS", loc="left", fontsize=9)

    # (b) push broom: a row of detectors, a whole line at once
    b = axes[1]
    b.add_patch(Rectangle((2.2, 8.5), 5.6, 0.45, color="#34495e"))
    for x in np.linspace(2.35, 7.65, 16):
        b.add_patch(Rectangle((x - 0.08, 8.55), 0.16, 0.35, color="#f1c40f"))
    b.text(5, 9.4, "linear array: thousands of detectors", ha="center", fontsize=8)
    b.add_patch(Polygon([[0.5, 0.5], [9.5, 0.5], [9.5, 5.2], [0.5, 5.2]], color="#eef2e6"))
    b.plot([2.2, 1.0], [8.5, 4.6], color="#2a78d6", lw=1)
    b.plot([7.8, 9.0], [8.5, 4.6], color="#2a78d6", lw=1)
    for y in np.linspace(1.0, 4.6, 7):
        b.plot([1.0, 9.0], [y, y], color="#2a78d6", lw=2.2 if y > 4.5 else 0.8)
    b.text(5, 5.85, "the whole line in one go", ha="center", fontsize=8, color="#2a78d6")
    _arrow(b, (0.3, 1.2), (0.3, 4.6))
    b.text(0.05, 2.9, "flight", rotation=90, va="center", fontsize=8)
    b.set_title("(b) Push broom (array scanning)\nSPOT, Landsat 8-9, Sentinel-2", loc="left",
                fontsize=9)

    # (c) frame camera: a 2-D array, a whole frame at once
    c = axes[2]
    c.add_patch(Rectangle((3.6, 7.9), 2.8, 1.5, color="#34495e"))
    for x in np.linspace(3.8, 6.2, 7):
        for y in np.linspace(8.05, 9.25, 4):
            c.add_patch(Rectangle((x - 0.1, y - 0.1), 0.2, 0.2, color="#f1c40f"))
    c.text(5, 9.65, "area array (like a phone camera)", ha="center", fontsize=8)
    c.add_patch(Polygon([[0.5, 0.5], [9.5, 0.5], [9.5, 5.2], [0.5, 5.2]], color="#eef2e6"))
    c.add_patch(Rectangle((1.5, 1.0), 7, 3.6, fill=False, ec="#8e44ad", lw=2))
    for x, y in [(3.6, 7.9), (6.4, 7.9)]:
        c.plot([x, 1.5 if x < 5 else 8.5], [y, 4.6], color="#8e44ad", lw=1)
    c.text(5, 5.85, "a whole frame per exposure", ha="center", fontsize=8, color="#8e44ad")
    c.set_title("(c) Frame camera\ndrones, aerial survey, small satellites", loc="left",
                fontsize=9)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 2. IFOV, swath and dwell time for real sensors
# ---------------------------------------------------------------------------
def geometry_table():
    rows = [
        # name, altitude km, IFOV µrad (or None), GSD m, swath km
        ("Landsat 1-3 MSS", 917, 86, None, 185),
        ("Landsat 5 TM", 705, 42.5, None, 185),
        ("SPOT 1-4 HRV multispectral", 832, None, 20, 60),
        ("SPOT 1-4 HRV panchromatic", 832, None, 10, 60),
        ("Landsat 8 OLI multispectral", 705, None, 30, 185),
        ("Sentinel-2 MSI (10 m bands)", 786, None, 10, 290),
    ]
    out = []
    for name, h, ifov, gsd, swath in rows:
        gsd = h * 1e3 * ifov * 1e-6 if ifov else gsd
        fov = 2 * np.degrees(np.arctan(swath / 2 / h))
        out.append({"sensor": name, "altitude_km": h, "gsd_m": gsd, "swath_km": swath,
                    "fov_deg": fov, "pixels_per_line": swath * 1e3 / gsd})
    return pd.DataFrame(out)


def dwell_table():
    line_time = 30 / GROUND_SPEED                      # time to advance one 30 m line
    px = 185e3 / 30                                    # pixels across a 185 km swath
    return pd.DataFrame([
        {"design": "push broom: one detector per pixel (OLI)", "dwell_time_us":
         line_time * 1e6},
        {"design": "whisk broom, one detector sweeping one line",
         "dwell_time_us": line_time / px * 1e6},
        {"design": "whisk broom, 16 detectors, 16 lines per sweep (TM-like)",
         "dwell_time_us": 16 * line_time / px * 1e6},
    ])


# ---------------------------------------------------------------------------
# 3. Pointing off nadir (SPOT): reach and pixel growth
# ---------------------------------------------------------------------------
def offnadir_geometry(tilt_deg, h=832e3, r=6371e3):
    """Spherical Earth: ground distance from the track, and pixel growth across track."""
    t = np.radians(tilt_deg)
    inc = np.arcsin((r + h) / r * np.sin(t))            # incidence angle at the ground
    gamma = inc - t                                     # angle at the Earth's centre
    slant = np.where(t > 0, r * np.sin(gamma) / np.where(t > 0, np.sin(t), 1), h)
    return r * gamma / 1e3, slant / h / np.cos(inc)


def offnadir_figure():
    ang = np.linspace(0, 30, 61)
    reach, grow = offnadir_geometry(ang)
    r27 = float(offnadir_geometry(np.array([27.0]))[0][0])
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.6))
    a.plot(ang, reach, color="#2a78d6", lw=2)
    a.axvline(27, color="#c0392b", ls="--", lw=1)
    a.text(27.4, 50, f"±27°: {r27:.0f} km each side", color="#c0392b",
           fontsize=8, rotation=90, va="bottom")
    a.set_xlabel("Tilt from nadir (°)"); a.set_ylabel("Distance from ground track (km)")
    a.set_title("How far to the side SPOT can look", loc="left", fontsize=10)
    b.plot(ang, grow, color="#8e44ad", lw=2)
    b.axvline(27, color="#c0392b", ls="--", lw=1)
    b.set_xlabel("Tilt from nadir (°)"); b.set_ylabel("Across-track pixel size ÷ nadir size")
    b.set_title("The price: pixels grow with tilt", loc="left", fontsize=10)
    b.text(0.99, -0.2, "Spherical Earth, 832 km orbit", transform=b.transAxes, ha="right",
           fontsize=7, color="#6b7680")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 4. A whisk broom that lost its corrector: Landsat 7 after May 2003
# ---------------------------------------------------------------------------
area = ee.Geometry.Rectangle([107.35, -7.10, 107.95, -6.75], None, False)     # Bandung
L7_VIS = {"bands": ["SR_B3", "SR_B2", "SR_B1"], "min": 7000, "max": 16000}
L8_VIS = {"bands": ["SR_B4", "SR_B3", "SR_B2"], "min": 7000, "max": 16000}


def first_clear(col):
    return ee.Image(col.filterBounds(area).filter(ee.Filter.lt("CLOUD_COVER", 30))
                    .sort("CLOUD_COVER").first())


l7_on = first_clear(ee.ImageCollection("LANDSAT/LE07/C02/T1_L2")
                    .filterDate("2000-01-01", "2003-05-01"))
# Same path and row as the "before" image, so the two cover the same ground.
l7_off = first_clear(ee.ImageCollection("LANDSAT/LE07/C02/T1_L2")
                     .filterDate("2015-01-01", "2016-12-31")
                     .filter(ee.Filter.eq("WRS_PATH", l7_on.get("WRS_PATH")))
                     .filter(ee.Filter.eq("WRS_ROW", l7_on.get("WRS_ROW"))))
common = area.intersection(l7_on.geometry(), 30).intersection(l7_off.geometry(), 30)


def gap_table():
    rows = []
    for name, img in [("Landsat 7, before May 2003 (SLC on)", l7_on),
                      ("Landsat 7, 2015-2016 (SLC off)", l7_off)]:
        valid = img.select("SR_B1").mask().gt(0)
        r = valid.unmask(0).reduceRegion(ee.Reducer.mean(), common, 30,
                                         maxPixels=1e9).getInfo()
        rows.append({"image": name, "date": img.date().format("YYYY-MM-dd").getInfo(),
                     "valid_share": list(r.values())[0]})
    return pd.DataFrame(rows)


def products():
    return [
        {"kind": "figure", "name": "p3-scanning", "figure": scanning_figure,
         "caption": "Three ways to build an image. A whisk broom sweeps one pixel at a time "
                    "across track with a mirror; a push broom records a whole line with a row "
                    "of detectors; a frame camera records a whole area. In every case the "
                    "platform's forward motion supplies the along-track direction."},
        {"kind": "table", "name": "p3-geometry", "data": geometry_table,
         "floatfmt": ("", ",.0f", ".0f", ",.0f", ".1f", ",.0f"),
         "caption": "Ground pixel size (GSD = altitude × IFOV), swath and field of view for "
                    "six sensors. SPOT's 4.1° field of view from 832 km gives its 60 km "
                    "swath; Landsat needs about 15° for 185 km."},
        {"kind": "table", "name": "p3-dwell", "data": dwell_table,
         "floatfmt": ("", ",.1f"),
         "caption": "How long each detector looks at one 30 m pixel. The push broom has "
                    "thousands of times longer to collect light, which is why it can have "
                    "better signal-to-noise with smaller optics."},
        {"kind": "figure", "name": "p3-offnadir", "figure": offnadir_figure,
         "caption": "Tilting the camera lets SPOT image a target up to about 430 km either "
                    "side of its track, so it can revisit a place every few days instead "
                    "of every 26. The cost is larger, distorted pixels."},
        {"kind": "map", "name": "p3-slc-on", "image": l7_on.clip(area), "region": area,
         "vis": L7_VIS, "title": "Landsat 7 ETM+, scan line corrector working",
         "source": "Landsat 7 Collection 2 L2. GEE.",
         "caption": "Bandung before May 2003. The whisk broom and its scan line corrector "
                    "together fill every line."},
        {"kind": "map", "name": "p3-slc-off", "image": l7_off.clip(area), "region": area,
         "vis": L7_VIS, "title": "Landsat 7 ETM+, scan line corrector failed",
         "source": "Landsat 7 Collection 2 L2. GEE.",
         "caption": "The same area after the corrector failed on 31 May 2003. Without it, "
                    "each mirror sweep traces a zig-zag, leaving wedge-shaped gaps that "
                    "widen away from the centre of the scene."},
        {"kind": "table", "name": "p3-gaps", "data": gap_table, "floatfmt": ("", "", ".0%"),
         "caption": "Share of pixels with data where both scenes (same path and row) cover "
                    "the box, before and after the failure. Clouds are not removed, so "
                    "only the scan gaps differ."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(gap_table())
