#| title: Platforms and orbits (Python)
#| description: Orbit period from altitude, a simulated sun-synchronous ground track, real Landsat scene footprints over Java, and real overpass times that prove what "sun-synchronous" means.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
PRINCIPLES P2 | Where the sensor is, and when it passes.

    Kepler:  period T = 2π √(a³ / GM)      a = Earth radius + altitude
    LEO      a few hundred to about 1,000 km, about 100 minutes per orbit
    GEO      35,786 km above the equator, one orbit per sidereal day

The ground track is simulated from a circular orbit plus the Earth's rotation.
Footprints and overpass times come from the Landsat 8/9 and Sentinel-1
archives in Earth Engine.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

GM, R = 3.986004418e14, 6378137.0
SIDEREAL = 86164.1


def period_min(h_km):
    a = R + np.asarray(h_km) * 1e3
    return 2 * np.pi * np.sqrt(a ** 3 / GM) / 60


# ---------------------------------------------------------------------------
# 1. Altitude and period
# ---------------------------------------------------------------------------
def orbits_figure():
    h = np.logspace(np.log10(200), np.log10(40000), 200)
    fig, ax = plt.subplots(figsize=(8.5, 4))
    ax.loglog(h, period_min(h) / 60, color="#1f2933", lw=1.5)
    pts = [("ISS", 420), ("Landsat 8/9", 705), ("Sentinel-2", 786), ("SPOT", 832),
           ("Landsat 1-3", 917), ("GPS (MEO)", 20200), ("Geostationary (Himawari)", 35786)]
    for name, alt in pts:
        p = period_min(alt) / 60
        ax.plot(alt, p, "o", color="#c0392b", ms=5)
        ax.annotate(f"{name}\n{alt:,} km, {p * 60:.0f} min" if p < 2 else
                    f"{name}\n{alt:,} km, {p:.1f} h", (alt, p), xytext=(6, -4),
                    textcoords="offset points", fontsize=7.5, va="top")
    ax.axhline(SIDEREAL / 3600, color="#6b7680", ls=":", lw=1)
    ax.text(250, SIDEREAL / 3600 * 1.08, "one sidereal day (23.93 h)", fontsize=7.5,
            color="#6b7680")
    ax.axvspan(200, 2000, color="#2a78d6", alpha=0.08)
    ax.text(230, 0.95, "low Earth orbit", fontsize=8, color="#2a78d6")
    ax.set_xlabel("Altitude (km, log scale)")
    ax.set_ylabel("Orbital period (hours, log scale)")
    ax.set_title("Higher orbit, longer period: every Earth observation satellite obeys "
                 "Kepler", loc="left", fontsize=10)
    ax.text(0.99, -0.16, "Computed: T = 2π √(a³/GM), circular orbits",
            transform=ax.transAxes, ha="right", fontsize=7, color="#6b7680")
    return fig


def orbit_table():
    rows = []
    for name, alt in [("Landsat 8/9", 705), ("Sentinel-2", 786), ("SPOT", 832),
                      ("Landsat 1-3", 917), ("Geostationary", 35786)]:
        a = R + alt * 1e3
        v = np.sqrt(GM / a)
        rows.append({"platform": name, "altitude_km": alt, "period_min": period_min(alt),
                     "orbits_per_day": 86400 / (period_min(alt) * 60),
                     "speed_km_s": v / 1e3,
                     # speed of the point below, ignoring the Earth's own rotation
                     "ground_speed_km_s": v * R / a / 1e3 if alt < 2000 else np.nan})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2. A sun-synchronous ground track, simulated
# ---------------------------------------------------------------------------
def ground_track(h_km=705, inc_deg=98.2, hours=24, step_s=20):
    t = np.arange(0, hours * 3600, step_s)
    n = 2 * np.pi / (period_min(h_km) * 60)
    u = n * t                                         # angle along the orbit
    i = np.radians(inc_deg)
    lat = np.degrees(np.arcsin(np.sin(i) * np.sin(u)))
    lon_inertial = np.degrees(np.arctan2(np.cos(i) * np.sin(u), np.cos(u)))
    lon = (lon_inertial - 360 * t / SIDEREAL + 180) % 360 - 180
    asc = np.cos(u) > 0                               # latitude increasing
    return lon, lat, asc


def ground_track_figure():
    lon, lat, asc = ground_track()
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for mask, col, lab in [(~asc, "#c0392b", "descending (north to south)"),
                           (asc, "#2a78d6", "ascending (south to north)")]:
        lo, la = np.where(mask, lon, np.nan), np.where(mask, lat, np.nan)
        br = np.abs(np.diff(lo, prepend=lo[0])) > 180              # break at the dateline
        lo[br] = np.nan
        ax.plot(lo, la, color=col, lw=0.9, label=lab)
    top = lat.max()
    for y in (top, -top):
        ax.axhline(y, color="#6b7680", ls=":", lw=0.8)
    ax.text(-178, top + 1.5, f"highest latitude reached {top:.1f}° (never the pole)",
            fontsize=7.5, color="#6b7680")
    ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
    ax.set_xticks(range(-180, 181, 60)); ax.set_yticks(range(-90, 91, 30))
    ax.grid(color="#e1e5ea", lw=0.6)
    ax.set_xlabel("Longitude (°)"); ax.set_ylabel("Latitude (°)")
    ax.set_title(f"One day of a 705 km, 98.2° orbit: {86400 / (period_min(705) * 60):.1f} "
                 "orbits, each shifted west by the Earth's rotation", loc="left", fontsize=10)
    ax.legend(frameon=True, framealpha=0.95, fontsize=8, loc="center left")
    ax.text(0.99, -0.14, "Simulated: circular orbit, rotating Earth, no J2 precession "
            "within the day", transform=ax.transAxes, ha="right", fontsize=7,
            color="#6b7680")
    return fig


# ---------------------------------------------------------------------------
# 3. Real footprints: one day of Landsat 8 scenes over Java
# ---------------------------------------------------------------------------
java = ee.Geometry.Rectangle([104.5, -9.5, 116.5, -4.5], None, False)
day = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterBounds(java)
       .filterDate("2024-08-01", "2024-08-31"))
one_path = day.filter(ee.Filter.eq("WRS_PATH", 120))
frames = ee.FeatureCollection(one_path.map(lambda im: ee.Feature(im.geometry())))
land = ee.Image("MODIS/061/MCD12Q1/2022_01_01").select("LC_Type1").neq(17)
footprint_map = (land.visualize(palette=["dbe9f6", "e8e3d3"])
                 .blend(ee.Image().byte().paint(frames, 1, 2).visualize(palette=["c0392b"])))


# ---------------------------------------------------------------------------
# 4. Real overpass times: sun-synchronous means the same local time
# ---------------------------------------------------------------------------
bandung = ee.Geometry.Point(107.61, -6.91)


def overpass_frame():
    def times(col, sensor):
        fc = col.filterBounds(bandung).filterDate("2023-01-01", "2024-01-01")
        return pd.DataFrame({"t": fc.aggregate_array("system:time_start").getInfo(),
                             "sensor": sensor})
    s1 = ee.ImageCollection("COPERNICUS/S1_GRD").filter(ee.Filter.eq("instrumentMode", "IW"))
    df = pd.concat([
        times(ee.ImageCollection("LANDSAT/LC08/C02/T1_L2"), "Landsat 8"),
        times(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"), "Landsat 9"),
        times(ee.ImageCollection("COPERNICUS/S2_HARMONIZED"), "Sentinel-2"),
        times(s1.filter(ee.Filter.eq("orbitProperties_pass", "ASCENDING")),
              "Sentinel-1 ascending"),
        times(s1.filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING")),
              "Sentinel-1 descending")])
    utc = pd.to_datetime(df["t"], unit="ms")
    df["date"] = utc.dt.normalize()
    solar = utc + pd.to_timedelta(107.61 / 15, unit="h")                # mean solar time
    df["local_solar_hour"] = solar.dt.hour + solar.dt.minute / 60
    return df.drop(columns="t")


def plot_overpass(df):
    cols = {"Landsat 8": "#c0392b", "Landsat 9": "#e67e22", "Sentinel-2": "#1b7837",
            "Sentinel-1 ascending": "#2a78d6", "Sentinel-1 descending": "#8e44ad"}
    fig, ax = plt.subplots(figsize=(9, 3.8))
    for s, d in df.groupby("sensor"):
        ax.scatter(d["date"], d["local_solar_hour"], s=12, color=cols[s], label=s)
    ax.set_ylim(0, 24); ax.set_yticks(range(0, 25, 3))
    ax.set_ylabel("Local solar time of pass (h)")
    ax.set_title("Every pass over Bandung in 2023: each satellite comes back at the same "
                 "local time", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=7.5, ncol=3, loc="upper center")
    return fig


def overpass_table(df):
    g = df.groupby("sensor")["local_solar_hour"]
    out = pd.DataFrame({"passes_2023": g.size(), "mean_local_time_h": g.mean(),
                        "spread_minutes": (g.max() - g.min()) * 60}).reset_index()
    return out


def products():
    return [
        {"kind": "figure", "name": "p2-orbits", "figure": orbits_figure,
         "caption": "Orbital period against altitude for circular orbits. Earth observation "
                    "satellites cluster in low Earth orbit (about 100 minutes per orbit); "
                    "weather satellites such as Himawari sit in geostationary orbit."},
        {"kind": "table", "name": "p2-orbit-table", "data": orbit_table,
         "floatfmt": ("", ",.0f", ".1f", ".2f", ".2f", ".2f"),
         "caption": "The same numbers for five platforms. Ground speed is how fast the "
                    "point below a low-orbit satellite sweeps across the ground. For a "
                    "geostationary satellite that point does not move at all."},
        {"kind": "figure", "name": "p2-groundtrack", "figure": ground_track_figure,
         "caption": "Ground track of a Landsat-like orbit over one day. Descending passes "
                    "(red) run north to south, ascending (blue) south to north. The track "
                    "never reaches the poles: this is a near-polar orbit."},
        {"kind": "map", "name": "p2-footprints", "image": footprint_map, "region": java,
         "vis": {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255},
         "title": "Landsat 8 scenes, WRS-2 path 120, August 2024",
         "source": "Landsat 8 Collection 2 footprints; MODIS land mask. GEE.",
         "caption": "Real scene footprints along one path across Java. Each scene is a "
                    "tilted parallelogram, not a north-up rectangle: the orbit is inclined "
                    "about 8° from north-south, and the Earth turns under the satellite "
                    "while each scene is recorded."},
        {"kind": "chart", "name": "p2-overpass", "data": overpass_frame, "plot": plot_overpass,
         "caption": "The time of day of every 2023 acquisition covering Bandung, from the "
                    "archive metadata. Optical satellites pass mid-morning; Sentinel-1 "
                    "passes near dawn and dusk."},
        {"kind": "table", "name": "p2-overpass-table", "data": overpass_frame,
         "transform": overpass_table, "floatfmt": ("", ".0f", ".2f", ".0f"),
         "caption": "Mean local solar time of each satellite's passes over Bandung, and "
                    "the spread across the whole year."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(overpass_table(overpass_frame()))
