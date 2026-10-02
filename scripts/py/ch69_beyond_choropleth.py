#| title: Maps that answer questions, beyond the choropleth (Python)
#| description: Indonesia's provinces with population (WorldPop) and night lights (VIIRS) from Earth Engine, drawn six ways - totals against rates, three classification schemes, a bivariate choropleth, proportional symbols with a Dorling cartogram, a dot-density map - and Riau's land-cover change 2004-2024 (MODIS) as a Sankey diagram.

"""
CHAPTER 69 | Maps that answer questions

A choropleth (areas shaded by value) is the default map, and often the wrong
one. The same province data drawn six ways:

  1  totals vs rates         a big province is not a dense one
  2  classification          equal interval, quantile and natural breaks
                             tell three different stories
  3  bivariate choropleth    two variables in one map: crowded and lit?
  4  symbols and cartogram   size for counts, not colour
  5  dot density             where people actually are inside provinces
  6  Sankey                  where Riau's forest went, 2004 to 2024

Data (Earth Engine): FAO GAUL 2025 provinces, WorldPop 2020 population,
VIIRS 2024 annual night lights, MODIS MCD12Q1 land cover. Saved to MAP_DATA
so the R twin reads the same files.

Environment: pip install geopandas mapclassify matplotlib rasterio requests earthengine-api
"""

import json
import os
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

DATA = Path(os.environ.get("MAP_DATA", "data/maps_indonesia")); DATA.mkdir(parents=True, exist_ok=True)

SNAPSHOT = "https://github.com/rifkynhsp-byte/Fullstack-Remote-Sensing/releases/download/data-v1/ch69_maps_indonesia_inputs.zip"


def snapshot():
    """The exact inputs used for the book (frozen 2 October 2026), downloaded once if they are not here.
    Rebuild them from the live sources instead with the data-building step described in the chapter."""
    if not (DATA / "provinces.gpkg").exists():
        import io, zipfile, requests
        DATA.mkdir(parents=True, exist_ok=True)
        zipfile.ZipFile(io.BytesIO(requests.get(SNAPSHOT, timeout=600).content)).extractall(DATA)


snapshot()
EQ = "EPSG:6933"                    # equal-area projection for densities and areas
IGBP = {1: "Evergreen needleleaf forest", 2: "Evergreen broadleaf forest", 3: "Deciduous needleleaf forest",
        4: "Deciduous broadleaf forest", 5: "Mixed forest", 6: "Closed shrubland", 7: "Open shrubland",
        8: "Woody savanna", 9: "Savanna", 10: "Grassland", 11: "Permanent wetland", 12: "Cropland",
        13: "Urban", 14: "Cropland/natural mosaic", 15: "Snow and ice", 16: "Barren", 17: "Water"}
SIMPLE = {2: "Forest", 1: "Forest", 3: "Forest", 4: "Forest", 5: "Forest", 8: "Savanna & shrub", 9: "Savanna & shrub",
          6: "Savanna & shrub", 7: "Savanna & shrub", 10: "Grassland", 11: "Wetland", 12: "Cropland",
          14: "Cropland", 13: "Urban", 16: "Other", 15: "Other", 17: "Water"}


def ee_init():
    import ee
    key = os.environ.get("BOOK_EE_KEY")
    if key:
        info = json.load(open(os.path.expanduser(key)))
        ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], os.path.expanduser(key)), project=info.get("project_id"))
    else:
        ee.Initialize(project=os.environ.get("BOOK_EE_PROJECT"))
    return ee


# PART 1. Data from Earth Engine, saved once ------------------------------------------------
def provinces():
    f = DATA / "provinces.gpkg"
    if not f.exists():
        ee = ee_init()
        prov = ee.FeatureCollection("FAO/GAUL/2025/level1").filter(ee.Filter.eq("ISO3_CODE", "IDN"))
        pop = (ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "IDN"))
               .filter(ee.Filter.eq("year", 2020)).mosaic().rename("population"))
        light = (ee.ImageCollection("NOAA/VIIRS/DNB/ANNUAL_V22").filterDate("2024-01-01", "2025-01-01").first()
                 .select("average").max(0).multiply(ee.Image.pixelArea()).divide(1e6).rename("light"))   # nW/cm2/sr x km2
        stats = pop.reduceRegions(prov, ee.Reducer.sum().setOutputs(["population"]), 100)
        stats = light.reduceRegions(stats, ee.Reducer.sum().setOutputs(["light"]), 500)
        feats = stats.map(lambda p: p.setGeometry(p.geometry().simplify(2000))).getInfo()["features"]
        g = gpd.GeoDataFrame.from_features(feats, crs=4326)[["GAUL1_NAME", "population", "light", "geometry"]]
        g = g.rename(columns={"GAUL1_NAME": "province"})
        g["area_km2"] = g.to_crs(EQ).area / 1e6
        g.to_file(f)
    g = gpd.read_file(f)
    # simplification can leave stray lines inside GeometryCollections: keep the polygons
    from shapely.geometry import MultiPolygon
    polys = lambda geom: MultiPolygon([q for p in getattr(geom, "geoms", [geom]) if p.geom_type in ("Polygon", "MultiPolygon")
                                       for q in getattr(p, "geoms", [p])])
    g["geometry"] = g.geometry.apply(polys)
    g["density"] = g.population / g.area_km2                         # people per km2
    g["light_per_1000"] = 1000 * g.light / g.population               # light per 1,000 residents
    return g


def population_grid():
    """GPW v4.11 population counts aggregated to 0.05 degree cells, for the dot-density map."""
    f = DATA / "worldpop_5km.tif"
    if not f.exists():
        ee = ee_init()
        # Summing 100 m WorldPop over all of Indonesia exceeds Earth Engine's interactive memory, so the
        # dot map uses GPW v4.11 population counts (about 1 km, CIESIN), aggregated to 0.05 degrees.
        pop = ee.ImageCollection("CIESIN/GPWv411/GPW_Population_Count").filterDate("2020-01-01", "2021-01-01").first()
        grid = [0.05, 0, 94.5, 0, -0.05, 6.5]                         # 0.05 degree cells (about 5.5 km)
        pop5 = pop.reduceResolution(ee.Reducer.sum().unweighted(), maxPixels=1024).reproject("EPSG:4326", grid)
        url = pop5.getDownloadURL(dict(region=ee.Geometry.Rectangle([94.5, -11.5, 141.5, 6.5]), crs="EPSG:4326",
                                       crsTransform=grid, dimensions="940x360", format="GEO_TIFF"))
        r = requests.get(url, timeout=900); r.raise_for_status()
        f.write_bytes(r.content)
    return f


def transitions():
    """Area (km2) of every MODIS land-cover transition in Riau, 2004 to 2024."""
    f = DATA / "riau_landcover_2004_2024.csv"
    if not f.exists():
        ee = ee_init()
        riau = (ee.FeatureCollection("FAO/GAUL/2025/level1").filter(ee.Filter.eq("ISO3_CODE", "IDN"))
                .filter(ee.Filter.eq("GAUL1_NAME", "Riau")).geometry())
        lc = ee.ImageCollection("MODIS/061/MCD12Q1").select("LC_Type1")
        a = lc.filter(ee.Filter.calendarRange(2004, 2004, "year")).first()
        b = lc.filter(ee.Filter.calendarRange(2024, 2024, "year")).first()
        code = a.multiply(100).add(b).rename("code")
        res = (ee.Image.pixelArea().divide(1e6).addBands(code)
               .reduceRegion(ee.Reducer.sum().group(1, "code"), riau, 463.3, maxPixels=1e10).getInfo())
        rows = [{"from": IGBP[int(g["code"]) // 100], "to": IGBP[int(g["code"]) % 100], "km2": g["sum"]}
                for g in res["groups"]]
        pd.DataFrame(rows).to_csv(f, index=False)
    return pd.read_csv(f)


# PART 2. Map helpers: titles and a labelled graticule ----------------------------------------
def insight(fig, title, subtitle, top=0.86):
    fig.suptitle(title, x=0.01, y=0.985, ha="left", fontsize=10, fontweight="bold")
    fig.text(0.01, 0.985 - 0.32 / fig.get_figheight(), subtitle, fontsize=8, color="#444444", va="top")
    fig.subplots_adjust(top=top)


def graticule(ax, step=5):
    """Lon/lat lines every `step` degrees, labelled on the frame (maps here are in degrees)."""
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    xs = np.arange(np.ceil(x0 / step) * step, x1, step); ys = np.arange(np.ceil(y0 / step) * step, y1, step)
    ax.set_xticks(xs, [f"{abs(v):g}°{'E' if v >= 0 else 'W'}" for v in xs], fontsize=6.5)
    ax.set_yticks(ys, [f"{abs(v):g}°{'N' if v > 0 else 'S' if v < 0 else ''}" for v in ys], fontsize=6.5)
    ax.grid(color="#999999", lw=0.4, ls="--"); ax.set_axisbelow(True); ax.set_xlabel(""); ax.set_ylabel("")
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    for s in ax.spines.values():
        s.set_visible(True); s.set_color("#999999"); s.set_linewidth(0.6)


def base(ax, g):
    g.plot(ax=ax, color="#f2f2f2", edgecolor="#bbbbbb", lw=0.3)
    ax.set_xlim(94.5, 141.5); ax.set_ylim(-11.5, 6.5)


# PART 3. The maps --------------------------------------------------------------------------
def totals_rates_figure():
    g = provinces()
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.4))
    for ax, col, lab, cmap in [(axs[0], "population", "population (million)", "Blues"), (axs[1], "density", "people per km²", "Purples")]:
        v = g[col] / (1e6 if col == "population" else 1)
        g.assign(v=v).plot(ax=ax, column="v", cmap=cmap, scheme="Quantiles", k=5, edgecolor="white", lw=0.3,
                           legend=True, legend_kwds=dict(fontsize=6, title=lab, title_fontsize=7, loc="lower left", fmt="{:,.1f}"))
        ax.set_xlim(94.5, 141.5); ax.set_ylim(-11.5, 6.5); graticule(ax)
    axs[0].set_title("Total: how many people live there", loc="left", fontsize=9)
    axs[1].set_title("Rate: how crowded it is", loc="left", fontsize=9)
    drop = (g.population.rank(pct=True) - g.density.rank(pct=True))       # high on totals, low on density
    big = g.loc[drop.idxmax(), "province"]
    insight(fig, f"Insight 1: totals reward big provinces; on a rate map Java stands out and {big} fades",
            "Population per province (left) against people per km² (right), WorldPop 2020, both in quintiles. A choropleth "
            "of totals mostly maps area; shade by a rate.")
    return fig


def classification_table():
    import mapclassify as mc
    d = provinces().density.values
    rows = []
    for name, c in [("Equal interval", mc.EqualInterval(d, 5)), ("Quantile", mc.Quantiles(d, 5)),
                    ("Natural breaks", mc.FisherJenks(d, 5))]:
        rows.append({"scheme": name, **{f"class {i + 1}": n for i, n in enumerate(c.counts)},
                     "upper bounds": ", ".join(f"{b:,.0f}" for b in c.bins)})
    return pd.DataFrame(rows)


def classification_figure():
    g = provinces()
    fig, axs = plt.subplots(1, 3, figsize=(15, 3.9))
    for ax, s, t in zip(axs, ["EqualInterval", "Quantiles", "FisherJenks"], ["Equal interval", "Quantile", "Natural breaks (Fisher-Jenks)"]):
        g.plot(ax=ax, column="density", cmap="YlOrRd", scheme=s, k=5, edgecolor="white", lw=0.3, legend=True,
               legend_kwds=dict(fontsize=5.5, loc="lower left", fmt="{:,.0f}"))
        ax.set_xlim(94.5, 141.5); ax.set_ylim(-11.5, 6.5); graticule(ax, 10); ax.set_title(t, loc="left", fontsize=9)
    c = classification_table().set_index("scheme")
    insight(fig, f"Insight 2: the same densities, three maps: equal intervals put {int(c.loc['Equal interval', 'class 1'])} "
                 f"of {len(g)} provinces in the lowest class",
            "People per km² by province, five classes each. Equal intervals split the range, quantiles split the provinces "
            "evenly, natural breaks follow gaps in the data. Choose the scheme for the question, and say which you chose.",
            top=0.8)
    return fig


def bivariate_figure():
    """3 x 3 bivariate choropleth: density (rows) against night light per 1,000 residents (columns)."""
    g = provinces().copy()
    g["d3"] = pd.qcut(g.density, 3, labels=False); g["l3"] = pd.qcut(g.light_per_1000, 3, labels=False)
    palette = [["#e8e8e8", "#ace4e4", "#5ac8c8"], ["#dfb0d6", "#a5add3", "#5698b9"], ["#be64ac", "#8c62aa", "#3b4994"]]
    g["colour"] = [palette[int(d)][int(l)] for d, l in zip(g.d3, g.l3)]
    fig = plt.figure(figsize=(12, 5.2)); ax = fig.add_axes([0.03, 0.08, 0.72, 0.74])
    g.plot(ax=ax, color=g.colour, edgecolor="white", lw=0.3)
    ax.set_xlim(94.5, 141.5); ax.set_ylim(-11.5, 6.5); graticule(ax)
    lg = fig.add_axes([0.79, 0.3, 0.16, 0.36])
    for d in range(3):
        for l in range(3):
            lg.add_patch(plt.Rectangle((l, d), 1, 1, color=palette[d][l]))
    lg.set_xlim(0, 3); lg.set_ylim(0, 3); lg.set_xticks([]); lg.set_yticks([])
    lg.set_xlabel("night light per resident →", fontsize=8); lg.set_ylabel("people per km² →", fontsize=8)
    for s in lg.spines.values(): s.set_visible(False)
    dim = (g.d3 == 2) & (g.l3 == 0); bright = (g.d3 == 0) & (g.l3 == 2)
    insight(fig, f"Insight 3: Java is crowded but dim per person (pink); the most light per resident is in "
                 f"{bright.sum()} sparsely settled provinces (green-blue)",
            "Two variables in one colour: people per km² (WorldPop 2020) and VIIRS 2024 night light per 1,000 residents, each in "
            f"terciles. {dim.sum()} provinces fall in the crowded-but-dim corner; light per resident is highest where few people "
            "live, so one mine, port or town lifts the ratio.", top=0.86)
    return fig


def dorling(g, scale, iters=300):
    """Dorling cartogram: one circle per province, area proportional to population,
    pushed apart until circles no longer overlap."""
    c = g.to_crs(EQ).geometry.centroid; xy = np.column_stack([c.x, c.y]).astype(float)
    r = scale * np.sqrt(g.population.values)
    for _ in range(iters):
        moved = False
        for i in range(len(xy)):
            for j in range(i + 1, len(xy)):
                d = xy[j] - xy[i]; dist = np.hypot(*d) + 1e-9; overlap = r[i] + r[j] - dist
                if overlap > 0:
                    push = d / dist * overlap / 2; xy[i] -= push; xy[j] += push; moved = True
        if not moved:
            break
    return xy, r


def symbols_figure():
    g = provinces()
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.6))
    base(axs[0], g)
    c = g.geometry.representative_point()
    axs[0].scatter(c.x, c.y, s=g.population / 1e5, color="#2166ac", alpha=0.55, edgecolor="white")
    for p in [1e6, 1e7, 4e7]:
        axs[0].scatter([], [], s=p / 1e5, color="#2166ac", alpha=0.55, label=f"{p / 1e6:,.0f} million")
    axs[0].legend(fontsize=6.5, loc="lower left", labelspacing=1.4, borderpad=1); graticule(axs[0])
    axs[0].set_title("Proportional symbols: circle area = population", loc="left", fontsize=9)
    xy, r = dorling(g, 2.5e5 / np.sqrt(g.population.max()))          # largest circle: 250 km radius
    gq = g.to_crs(EQ); gq.plot(ax=axs[1], color="#f2f2f2", edgecolor="#cccccc", lw=0.3)
    bx = gq.total_bounds; pad = 3e5
    axs[1].set_xlim(bx[0] - pad, bx[2] + pad); axs[1].set_ylim(bx[1] - pad, bx[3] + pad)
    for (x, y), rr, dens in zip(xy, r, g.density):
        axs[1].add_patch(plt.Circle((x, y), rr, color=plt.get_cmap("Purples")(min(1, np.log10(dens) / 4)), alpha=0.85))
    big = g.nlargest(3, "population")
    for i in big.index:
        axs[1].text(xy[i][0], xy[i][1], big.province[i].replace("Jawa ", "Jawa\n"), ha="center", va="center", fontsize=6)
    axs[1].set_aspect("equal"); axs[1].set_axis_off()
    axs[1].set_title("Dorling cartogram: circles sized by population, shaded by density", loc="left", fontsize=9)
    share = g.nlargest(6, "population").population.sum() / g.population.sum()
    insight(fig, f"Insight 4: drawn by people instead of land, Java dominates: the six most populous provinces hold "
                 f"{100 * share:.0f} % of Indonesians",
            "Left: a circle per province with area proportional to WorldPop 2020 population, on the map. Right: the same "
            "circles pushed apart so none overlap (equal-area projection).")
    return fig


def dots_figure():
    import rasterio
    with rasterio.open(population_grid()) as src:
        a = src.read(1).astype(float); tr = src.transform
    a[~np.isfinite(a) | (a < 0)] = 0
    per_dot = 20_000
    rng = np.random.default_rng(1)
    n = rng.poisson(a / per_dot)                                      # dots per 5 km cell
    rows, cols = np.nonzero(n)
    reps = n[rows, cols]
    rr = np.repeat(rows, reps) + rng.random(reps.sum()); cc = np.repeat(cols, reps) + rng.random(reps.sum())
    xs = tr.c + cc * tr.a; ys = tr.f + rr * tr.e
    prov = provinces()
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(xs, ys), crs=4326)
    pts = gpd.sjoin(pts, prov[["geometry"]], predicate="within")          # keep Indonesia only (the grid covers neighbours)
    xs, ys = pts.geometry.x.values, pts.geometry.y.values
    fig, ax = plt.subplots(figsize=(13, 5))
    base(ax, prov)
    ax.scatter(xs, ys, s=0.12, color="#08306b", alpha=0.45, linewidths=0)
    graticule(ax)
    insight(fig, f"Insight 5: one dot per {per_dot:,} people shows what a choropleth hides: dense Java, coasts and "
                 "river valleys elsewhere",
            f"GPW v4.11 2020 population summed to 0.05° cells; each cell gets a random number of dots with mean population/{per_dot:,}, "
            "placed at random inside the cell. Inside every province, people cluster.", top=0.86)
    return fig


def sankey_table():
    t = transitions()
    t["from"] = t["from"].map({v: SIMPLE[k] for k, v in IGBP.items()}); t["to"] = t["to"].map({v: SIMPLE[k] for k, v in IGBP.items()})
    # classes that are small on both dates merge into one node, so labels do not pile up
    size = pd.concat([t.groupby("from").km2.sum(), t.groupby("to").km2.sum()], axis=1).max(axis=1)
    small = set(size[size < 0.05 * t.km2.sum()].index)
    for c in ("from", "to"):
        t[c] = t[c].where(~t[c].isin(small), "Other (wetland, crops, grass, urban, water)")
    return t.groupby(["from", "to"], as_index=False).km2.sum().sort_values("km2", ascending=False)


SANKEY_COLOURS = {"Forest": "#1b7837", "Wetland": "#35978f", "Savanna & shrub": "#b8e186", "Grassland": "#e6f5d0",
                  "Cropland": "#fdae61", "Urban": "#d73027", "Water": "#4575b4", "Other": "#999999",
                  "Other (wetland, crops, grass, urban, water)": "#bdbdbd"}


def plot_sankey(df):
    """Two-column Sankey: each ribbon is a transition, its width the area."""
    from matplotlib.path import Path as MPath
    from matplotlib.patches import PathPatch
    order = [k for k in SANKEY_COLOURS if k in set(df["from"]) | set(df["to"])]
    left = df.groupby("from").km2.sum().reindex(order).fillna(0); right = df.groupby("to").km2.sum().reindex(order).fillna(0)
    total = left.sum(); gap = 0.02 * total
    def stack(s):
        y, pos = 0.0, {}
        for k, v in s.items():
            pos[k] = y; y += v + (gap if v > 0 else 0)
        return pos
    yl, yr = stack(left), stack(right)
    fig, ax = plt.subplots(figsize=(9.5, 6.2))
    ax.set_position([0.08, 0.04, 0.84, 0.78])
    offl, offr = dict(yl), dict(yr)
    for r in df.sort_values(["from", "to"], key=lambda s: s.map({k: i for i, k in enumerate(order)})).itertuples():
        y0, y1 = offl[r._1], offr[r.to]; h = r.km2
        verts = [(0.1, y0), (0.5, y0), (0.5, y1), (0.9, y1), (0.9, y1 + h), (0.5, y1 + h), (0.5, y0 + h), (0.1, y0 + h), (0.1, y0)]
        codes = [MPath.MOVETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4, MPath.LINETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4, MPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MPath(verts, codes), color=SANKEY_COLOURS[r._1], alpha=0.45, lw=0))
        offl[r._1] += h; offr[r.to] += h
    for side, s, pos, x in [("l", left, yl, 0.1), ("r", right, yr, 0.9)]:
        for k, v in s.items():
            if v <= 0: continue
            ax.add_patch(plt.Rectangle((x - 0.02 if side == "l" else x, pos[k]), 0.02, v, color=SANKEY_COLOURS[k]))
            ax.text(x - 0.03 if side == "l" else x + 0.03, pos[k] + v / 2, f"{k}\n{v:,.0f} km²", ha="right" if side == "l" else "left",
                    va="center", fontsize=7.5)
    ax.text(0.1, -0.04 * total, "2004", ha="center", fontsize=9, fontweight="bold"); ax.text(0.9, -0.04 * total, "2024", ha="center", fontsize=9, fontweight="bold")
    ax.set_xlim(-0.25, 1.25); ax.set_ylim(-0.07 * total, total + gap * len(order)); ax.invert_yaxis(); ax.set_axis_off()
    f2s = df[(df["from"] == "Forest") & (df.to == "Savanna & shrub")].km2.sum()
    s2f = df[(df["from"] == "Savanna & shrub") & (df.to == "Forest")].km2.sum()
    lost = left.get("Forest", 0) - right.get("Forest", 0)
    insight(fig, f"Insight 6: Riau's mapped forest shrank by {lost:,.0f} km² net; the big flows run both ways between forest "
                 f"and savanna & shrub ({f2s:,.0f} and {s2f:,.0f} km²)",
            "MODIS MCD12Q1 land cover (IGBP classes grouped), 2004 on the left, 2024 on the right; ribbon width is area. "
            "At 500 m, MODIS confuses plantations, regrowth and forest, so read the two-way flows as uncertainty, not as change.",
            top=0.86)
    return fig


def products():
    return [
        {"kind": "figure", "name": "ch69-totals-rates", "figure": totals_rates_figure,
         "caption": "Insight 1. Totals against rates."},
        {"kind": "figure", "name": "ch69-classification", "figure": classification_figure,
         "caption": "Insight 2. Three classification schemes for the same data."},
        {"kind": "table", "name": "ch69-classes", "data": classification_table,
         "caption": "Provinces per class under each scheme, and the class upper bounds (people per km²)."},
        {"kind": "figure", "name": "ch69-bivariate", "figure": bivariate_figure,
         "caption": "Insight 3. Bivariate choropleth: density against night light per resident."},
        {"kind": "figure", "name": "ch69-symbols", "figure": symbols_figure,
         "caption": "Insight 4. Proportional symbols and a Dorling cartogram."},
        {"kind": "figure", "name": "ch69-dots", "figure": dots_figure,
         "caption": "Insight 5. Dot-density map of population."},
        {"kind": "chart", "name": "ch69-sankey", "data": sankey_table, "plot": plot_sankey,
         "caption": "Insight 6. Riau land-cover change 2004-2024 as a Sankey diagram."},
    ]


if __name__ == "__main__":
    g = provinces(); print(len(g), g[["province", "population", "density", "light_per_1000"]].sort_values("density").tail(5))
    print(classification_table()); print(sankey_table().head(12))
