#| title: Transit service and access in Jakarta from GTFS (Python)
#| description: Reads the public TransJakarta GTFS feed, turns its frequency-based timetable into buses per hour per route and per stop, and combines it with WorldPop to model what share of Jakarta's residents live within a walk of frequent service.

"""
CHAPTER 67 | What a timetable says about a city

A GTFS feed is a timetable written for computers. Read the right way, it
describes the city's transport network: where service runs, how often, how
unequally it is spread, and who can reach it.

  1  network map            where does service run, and how much?
  2  stop intensity + Lorenz how unequally is service spread over stops?
  3  headway by service type how long is the wait on each kind of route?
  4  weekday vs Sunday      which services are cut at the weekend?
  5  access curve           what share of residents live within 500 m of a
                            stop with a bus at least every h minutes?

Data: TransJakarta GTFS (public, no key); WorldPop 2020 100 m population and
FAO GAUL 2015 city boundaries (Earth Engine). By default the feed and layers as
they were on 2 October 2026 are downloaded, so results match the book; set
TRANSIT_LIVE=1 to use today's feed. The Earth Engine layers are
saved to TRANSIT_DATA so the R twin reads the same files.

Environment: pip install pandas geopandas matplotlib scipy rasterio requests earthengine-api
"""

import io
import json
import os
import zipfile
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from shapely.geometry import LineString

FEED = "https://gtfs.transjakarta.co.id/files/file_gtfs.zip"
DATA = Path(os.environ.get("TRANSIT_DATA", "data/transit_jakarta")); DATA.mkdir(parents=True, exist_ok=True)

SNAPSHOT = "https://github.com/rifkynhsp-byte/Fullstack-Remote-Sensing/releases/download/data-v1/ch67_transit_jakarta_inputs.zip"


def snapshot():
    """The exact inputs used for the book (frozen 2 October 2026), downloaded once if they are not here.
    Rebuild them from the live sources instead with the data-building step described in the chapter."""
    if not (DATA / "transjakarta_gtfs.zip").exists():
        import io, zipfile, requests
        DATA.mkdir(parents=True, exist_ok=True)
        zipfile.ZipFile(io.BytesIO(requests.get(SNAPSHOT, timeout=600).content)).extractall(DATA)


if not os.environ.get("TRANSIT_LIVE"):        # TRANSIT_LIVE=1 uses today's feed and Earth Engine instead
    snapshot()
CRS = "EPSG:32748"                      # UTM 48S, metres
HOUR = 8 * 3600                         # the weekday morning hour we describe (08:00)
WALK = 500                              # walking distance to a stop (m)
TYPES = ["BRT", "Angkutan Umum Integrasi", "Mikrotrans", "Transjabodetabek", "Royaltrans", "Rusun", "Bus Wisata"]
COLOURS = dict(zip(TYPES, ["#c51b7d", "#2166ac", "#1b9e77", "#e08214", "#7570b3", "#999999", "#d6604d"]))
_cache = {}


# PART 1. The feed ------------------------------------------------------------------
def gtfs():
    if "gtfs" in _cache:
        return _cache["gtfs"]
    f = DATA / "transjakarta_gtfs.zip"
    if not f.exists():
        f.write_bytes(requests.get(FEED, timeout=300).content)
    z = zipfile.ZipFile(f)
    read = lambda n: pd.read_csv(z.open(n), dtype=str)
    g = {n[:-4]: read(n) for n in ["routes.txt", "trips.txt", "frequencies.txt", "stops.txt",
                                     "stop_times.txt", "calendar.txt", "shapes.txt"]}
    _cache["gtfs"] = g
    return g


def secs(t):
    h, m, s = (int(x) for x in t.split(":")); return h * 3600 + m * 60 + s


def buses_per_hour(day="monday", at=HOUR):
    """Buses per hour of every trip pattern running on `day` at time `at`.
    This feed is frequency based: each trip is a template repeated every
    headway_secs between start_time and end_time."""
    g = gtfs()
    services = set(g["calendar"].loc[g["calendar"][day] == "1", "service_id"])
    f = g["frequencies"].copy()
    f["start"], f["end"] = f.start_time.map(secs), f.end_time.map(secs)
    f = f[(f.start <= at) & (f.end > at)]
    f["bph"] = 3600 / f.headway_secs.astype(float)
    t = g["trips"][g["trips"].service_id.isin(services)][["trip_id", "route_id", "shape_id"]]
    out = f.merge(t, on="trip_id").merge(g["routes"][["route_id", "route_short_name", "route_long_name", "route_desc"]],
                                        on="route_id")
    return out[["trip_id", "route_id", "shape_id", "route_short_name", "route_long_name", "route_desc", "headway_secs", "bph"]]


def stop_service(day="monday"):
    """Buses per hour at every stop: the sum over the trip patterns that call there."""
    g = gtfs(); b = buses_per_hour(day)
    calls = g["stop_times"][["trip_id", "stop_id"]].drop_duplicates().merge(b[["trip_id", "bph", "route_desc"]], on="trip_id")
    s = calls.groupby("stop_id").agg(bph=("bph", "sum"), n_patterns=("trip_id", "nunique")).reset_index()
    stops = g["stops"][["stop_id", "stop_name", "stop_lat", "stop_lon"]].merge(s, on="stop_id")
    gdf = gpd.GeoDataFrame(stops, geometry=gpd.points_from_xy(stops.stop_lon.astype(float), stops.stop_lat.astype(float)),
                           crs=4326).to_crs(CRS)
    gdf["headway_min"] = 60 / gdf.bph            # the combined wait if any bus will do
    return gdf


# PART 2. Earth Engine layers, saved for both languages ---------------------------------------
def ee_layers():
    """WorldPop 2020 for the Jakarta bounding box and the GAUL city boundaries."""
    pop_f, kota_f = DATA / "worldpop_jakarta.tif", DATA / "kota.gpkg"
    if not (pop_f.exists() and kota_f.exists()):
        import ee
        kota = ee.FeatureCollection("FAO/GAUL/2015/level2").filter(ee.Filter.eq("ADM1_NAME", "Dki Jakarta"))
        k = gpd.GeoDataFrame.from_features(kota.getInfo()["features"], crs=4326)
        k = k[~k.ADM2_NAME.str.contains("Seribu", case=False)]          # the islands have no bus network
        k[["ADM2_NAME", "geometry"]].rename(columns={"ADM2_NAME": "kota"}).to_file(kota_f)
        region = ee.Geometry.Rectangle(list(k.total_bounds))
        pop = (ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "IDN"))
               .filter(ee.Filter.eq("year", 2020)).first())
        url = pop.getDownloadURL(dict(region=region, scale=100, crs="EPSG:4326", format="GEO_TIFF"))
        pop_f.write_bytes(requests.get(url, timeout=600).content)
    return pop_f, kota_f


def population_points():
    """Every populated 100 m cell inside the five mainland cities, as a point with its people."""
    if "pop" in _cache:
        return _cache["pop"]
    import rasterio
    pop_f, kota_f = ee_layers()
    with rasterio.open(pop_f) as src:
        a = src.read(1); tr = src.transform
    rows, cols = np.nonzero(a > 0)
    xs, ys = rasterio.transform.xy(tr, rows, cols)
    p = gpd.GeoDataFrame({"people": a[rows, cols]}, geometry=gpd.points_from_xy(xs, ys), crs=4326)
    kota = gpd.read_file(kota_f)
    p = gpd.sjoin(p, kota, predicate="within").drop(columns="index_right").to_crs(CRS)
    _cache["pop"] = p
    return p


def graticule(ax, crs, n=4):
    """Latitude/longitude lines and edge labels on a map drawn in projected
    coordinates (metres), so every map can be located on the globe."""
    from pyproj import Transformer
    to_ll = Transformer.from_crs(crs, 4326, always_xy=True); to_xy = Transformer.from_crs(4326, crs, always_xy=True)
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    lon, lat = to_ll.transform([x0, x1, x0, x1], [y0, y0, y1, y1])
    span = max(max(lon) - min(lon), max(lat) - min(lat))
    step = next(s for s in (0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5) if span / s <= n + 1)
    fmt = lambda v, pos, neg: f"{abs(v):.{max(0, -int(np.floor(np.log10(step))))}f}°{pos if v >= 0 else neg}"
    for lo in np.arange(np.ceil(min(lon) / step) * step, max(lon), step):
        xs, ys = to_xy.transform(np.full(50, lo), np.linspace(min(lat) - step, max(lat) + step, 50))
        ax.plot(xs, ys, color="#888888", lw=0.4, ls="--", zorder=0.5)
        bx, _ = to_xy.transform(lo, min(lat))
        ax.text(bx, y0, fmt(lo, "E", "W"), ha="center", va="top", fontsize=7, color="#555555")
    for la in np.arange(np.ceil(min(lat) / step) * step, max(lat), step):
        xs, ys = to_xy.transform(np.linspace(min(lon) - step, max(lon) + step, 50), np.full(50, la))
        ax.plot(xs, ys, color="#888888", lw=0.4, ls="--", zorder=0.5)
        _, by = to_xy.transform(min(lon), la)
        ax.text(x0, by, fmt(la, "N", "S") + " ", ha="right", va="center", fontsize=7, color="#555555")
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_xlabel(""); ax.set_ylabel("")
    for s in ax.spines.values():
        s.set_visible(True); s.set_color("#999999"); s.set_linewidth(0.6)


# PART 3. The charts ------------------------------------------------------------------------
def insight(fig, title, subtitle, top=0.84):
    fig.suptitle(title, x=0.01, y=0.985, ha="left", fontsize=10, fontweight="bold")
    fig.text(0.01, 0.925, subtitle, fontsize=8, color="#444444")
    fig.subplots_adjust(top=top)


def network_figure():
    g = gtfs(); b = buses_per_hour()
    sh = g["shapes"].assign(lat=lambda d: d.shape_pt_lat.astype(float), lon=lambda d: d.shape_pt_lon.astype(float),
                            seq=lambda d: d.shape_pt_sequence.astype(int)).sort_values(["shape_id", "seq"])
    lines = sh.groupby("shape_id").apply(lambda d: LineString(zip(d.lon, d.lat)) if len(d) > 1 else None).dropna()
    net = gpd.GeoDataFrame(b.merge(lines.rename("geometry").reset_index(), on="shape_id"), crs=4326).to_crs(CRS)
    kota = gpd.read_file(ee_layers()[1]).to_crs(CRS)
    fig, ax = plt.subplots(figsize=(9, 8.4))
    kota.boundary.plot(ax=ax, color="#bbbbbb", lw=0.6)
    for t in reversed(TYPES):                                   # BRT drawn last, on top
        s = net[net.route_desc == t]
        if len(s):
            s.plot(ax=ax, color=COLOURS[t], linewidth=0.4 + s.bph.clip(upper=30) / 6, alpha=0.8, label=t)
    ax.legend(fontsize=7, loc="lower left", title="service type (width = buses/hour)", title_fontsize=7)
    ax.set_xlim(*kota.total_bounds[[0, 2]]); ax.set_ylim(*kota.total_bounds[[1, 3]]); graticule(ax, CRS)
    insight(fig, "Insight 1: BRT corridors form the spine; Mikrotrans feeders reach almost every street between them",
            "TransJakarta trip patterns running at 08:00 on a weekday, coloured by service type; line width is buses per hour "
            "on that pattern, so corridors shared by many patterns draw thick.", top=0.9)
    return fig


def stop_table():
    s = stop_service()
    return s.sort_values("bph", ascending=False).head(10)[["stop_name", "bph", "n_patterns", "headway_min"]].reset_index(drop=True)


def stops_figure():
    s = stop_service().sort_values("bph")
    kota = gpd.read_file(ee_layers()[1]).to_crs(CRS)
    fig, axs = plt.subplots(1, 2, figsize=(12, 5.6), gridspec_kw=dict(width_ratios=[1.25, 1]))
    kota.boundary.plot(ax=axs[0], color="#bbbbbb", lw=0.6)
    sc = axs[0].scatter(s.geometry.x, s.geometry.y, c=np.log10(s.bph), s=3 + s.bph.clip(upper=60) / 3, cmap="viridis")
    cb = fig.colorbar(sc, ax=axs[0], shrink=0.6); cb.set_label("buses per hour (log scale)")
    cb.set_ticks(np.log10([1, 3, 10, 30, 100])); cb.set_ticklabels(["1", "3", "10", "30", "100"])
    axs[0].set_xlim(*kota.total_bounds[[0, 2]]); axs[0].set_ylim(*kota.total_bounds[[1, 3]]); graticule(axs[0], CRS)
    # Lorenz curve: stops ranked from least to most served
    v = np.sort(s.bph.values); cs = np.cumsum(v) / v.sum(); x = np.arange(1, len(v) + 1) / len(v)
    gini = 1 - 2 * getattr(np, "trapezoid", getattr(np, "trapz", None))(cs, x)
    top10 = 1 - np.interp(0.9, x, cs)
    axs[1].plot([0, 1], [0, 1], ":", color="#888"); axs[1].plot(x, cs, color="#2166ac", lw=2)
    axs[1].fill_between(x, cs, x, color="#2166ac", alpha=0.12)
    axs[1].set_xlabel("share of stops (least served first)"); axs[1].set_ylabel("share of all bus calls per hour")
    axs[1].text(0.05, 0.9, f"Gini {gini:.2f}\nbusiest 10 % of stops: {100 * top10:.0f} % of calls", fontsize=9)
    insight(fig, f"Insight 2: the busiest tenth of stops gets {100 * top10:.0f} % of all bus calls, almost three times its share",
            "Left: buses per hour at every stop, 08:00 on a weekday (all patterns calling there). Right: Lorenz curve of the "
            "same numbers; the further the curve sags below the diagonal, the less evenly service is spread.", top=0.86)
    return fig


def headway_table():
    b = buses_per_hour()
    b["headway_min"] = b.headway_secs.astype(float) / 60
    t = b.groupby("route_desc").headway_min.describe(percentiles=[0.25, 0.5, 0.75])[["count", "25%", "50%", "75%"]]
    return t.reindex([x for x in TYPES if x in t.index]).reset_index()


def headway_figure():
    b = buses_per_hour(); b["headway_min"] = b.headway_secs.astype(float) / 60
    types = [t for t in TYPES if t in set(b.route_desc)]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    data = [b[b.route_desc == t].headway_min for t in types]
    ax.boxplot(data, vert=False, widths=0.55, showfliers=False, patch_artist=True,
               boxprops=dict(facecolor="#f0f0f0", color="#666"), medianprops=dict(color="#000"))
    rng = np.random.default_rng(1)
    for i, (t, d) in enumerate(zip(types, data), 1):
        ax.scatter(d, i + rng.uniform(-0.18, 0.18, len(d)), s=10, color=COLOURS[t], alpha=0.7, zorder=3)
    ax.set_yticks(range(1, len(types) + 1), types)
    ax.set_xscale("log"); ax.set_xticks([2, 5, 10, 20, 30, 60], ["2", "5", "10", "20", "30", "60"])
    ax.xaxis.set_minor_formatter(plt.NullFormatter())
    ax.invert_yaxis(); ax.set_xlabel("scheduled headway on each trip pattern (minutes, log scale)")
    insight(fig, "Insight 3: per trip pattern, Mikrotrans is scheduled every 6 minutes and a BRT pattern every 20",
            "Headway of every trip pattern running at 08:00 on a weekday, by service type: each dot is one pattern, boxes hold "
            "the middle half (log axis). BRT corridors are frequent because many patterns share them, which this chart cannot show.")
    return fig


def weekday_sunday_table():
    w = buses_per_hour("monday").groupby("route_desc").bph.sum().rename("weekday")
    s = buses_per_hour("sunday").groupby("route_desc").bph.sum().rename("sunday")
    t = pd.concat([w, s], axis=1).fillna(0).reindex([x for x in TYPES if x in w.index or x in s.index])
    t["change_%"] = 100 * (t.sunday / t.weekday - 1)
    return t.reset_index().rename(columns={"index": "route_desc"})


def plot_slope(df):
    fig, ax = plt.subplots(figsize=(6.4, 5))
    for r in df.itertuples():
        c = COLOURS.get(r.route_desc, "#555")
        if r.sunday == 0:            # a log axis cannot show zero: mark it at the weekday point instead
            ax.plot(0, r.weekday, "o", color=c); ax.text(0.04, r.weekday, f"{r.route_desc}: no Sunday service",
                                                         va="center", fontsize=8, color=c)
            continue
        ax.plot([0, 1], [r.weekday, r.sunday], "-o", color=c, lw=2)
        ax.text(1.04, r.sunday, f"{r.route_desc} ({r._4:+.0f} %)", va="center", fontsize=8)
    ax.set_yscale("log"); ax.set_xticks([0, 1], ["weekday 08:00", "Sunday 08:00"]); ax.set_xlim(-0.1, 1.9)
    ax.yaxis.set_minor_formatter(plt.NullFormatter())
    ax.set_ylabel("buses per hour, whole network (log scale)")
    insight(fig, "Insight 4: Sunday morning keeps almost the whole weekday service; only Royaltrans stops",
            "Total buses per hour by service type at 08:00, weekday against Sunday.", top=0.86)
    return fig


# PART 4. A model of access ----------------------------------------------------------------
THRESHOLDS = [3, 5, 10, 15, 20, 30, 60]


def access_table():
    """Share of residents within WALK m of a stop whose combined headway is <= h minutes."""
    from scipy.spatial import cKDTree
    p = population_points(); s = stop_service()
    xy = np.column_stack([p.geometry.x, p.geometry.y])
    rows = []
    for h in THRESHOLDS:
        f = s[s.headway_min <= h]
        d, _ = cKDTree(np.column_stack([f.geometry.x, f.geometry.y])).query(xy, distance_upper_bound=WALK)
        near = np.isfinite(d)
        for k, grp in p.assign(near=near).groupby("kota"):
            rows.append({"kota": k, "headway_max_min": h, "share_%": 100 * grp.people[grp.near].sum() / grp.people.sum()})
        rows.append({"kota": "DKI Jakarta (5 cities)", "headway_max_min": h, "share_%": 100 * p.people[near].sum() / p.people.sum()})
    return pd.DataFrame(rows)


def plot_access(df):
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for k, g in df.groupby("kota"):
        whole = k.startswith("DKI")
        ax.plot(g.headway_max_min, g["share_%"], "-o", lw=3 if whole else 1.3, ms=4,
                color="#000" if whole else None, label=k, zorder=3 if whole else 2)
    ax.set_xscale("log"); ax.set_xticks(THRESHOLDS, [str(t) for t in THRESHOLDS])
    ax.xaxis.set_minor_formatter(plt.NullFormatter())
    ax.set_xlabel("a bus at least every ... minutes (combined headway at the stop)")
    ax.set_ylabel(f"residents within {WALK} m of such a stop (%)"); ax.set_ylim(0, 100); ax.grid(alpha=0.3)
    ax.legend(fontsize=7, loc="lower right")
    insight(fig, "Insight 5: nine in ten residents live within 500 m of a stop served at least every 10 minutes",
            f"Share of each city's WorldPop 2020 residents within {WALK} m (straight line) of a TransJakarta stop, by the "
            "most frequent combined service required at that stop; weekday 08:00.")
    return fig


def products():
    return [
        {"kind": "figure", "name": "ch67-network", "figure": network_figure,
         "caption": "Insight 1. The TransJakarta network at 08:00 on a weekday."},
        {"kind": "figure", "name": "ch67-stops", "figure": stops_figure,
         "caption": "Insight 2. Buses per hour at every stop, and how unequally they are spread."},
        {"kind": "table", "name": "ch67-top-stops", "data": stop_table, "floatfmt": ("", ".0f", ".0f", ".2f"),
         "caption": "The ten busiest stops: buses per hour, trip patterns calling, and the combined headway."},
        {"kind": "figure", "name": "ch67-headways", "figure": headway_figure,
         "caption": "Insight 3. Scheduled headways by service type."},
        {"kind": "table", "name": "ch67-headway-table", "data": headway_table, "floatfmt": ("", ".0f", ".1f", ".1f", ".1f"),
         "caption": "Headway quartiles (minutes) by service type, weekday 08:00."},
        {"kind": "chart", "name": "ch67-weekend", "data": weekday_sunday_table, "plot": plot_slope,
         "caption": "Insight 4. Weekday against Sunday service by type."},
        {"kind": "chart", "name": "ch67-access", "data": access_table, "plot": plot_access,
         "caption": "Insight 5. Share of residents within walking distance of frequent service."},
    ]


if __name__ == "__main__":
    print(stop_table()); print(headway_table()); print(weekday_sunday_table())
    print(access_table().pivot(index="kota", columns="headway_max_min", values="share_%").round(1))
