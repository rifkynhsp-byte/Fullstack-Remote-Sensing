#| title: An urban planning toolkit: green space, park access, heat and flood exposure in Surabaya (Python)
#| description: Puts Surabaya on an H3 hexagon grid and answers four planning questions with open data - does the city meet the 30 % green open space rule, how many residents can walk to a park, where should greening go first (a composite index with a weight-sensitivity test), and how much new building since 2016 sits on flood-prone low ground - with regression and Moran's I along the way.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 73 | An urban planning toolkit: Surabaya on a hexagon grid

A planning office does not need a land cover map. It needs answers per
neighbourhood: is there enough green, can people walk to a park, where is it
hottest, and is the city building where it floods. This script puts Kota
Surabaya on a grid of H3 hexagons (resolution 8, about 0.74 km2 each), fills
every hexagon with open data, and answers those questions.

Data: ESA WorldCover 2021 (10 m), GHSL population 2020 (100 m), Landsat 8 and 9
land surface temperature (dry seasons 2023-2024), MERIT Hydro elevation
(90 m), Google Open Buildings 2.5D Temporal (2016,
2023), OpenStreetMap parks, FAO GAUL 2025. The hexagon table is saved to
data/ch73_surabaya_hex.csv and the parks to data/ch73_surabaya_parks.geojson,
so the analysis (and the R twin) runs without Earth Engine or Overpass.

Environment: pip install earthengine-api h3 geopandas shapely pyproj pandas numpy matplotlib statsmodels requests
"""

import json
import os
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely.geometry import Polygon, shape

ROOT = Path(__file__).resolve().parents[2] if "__file__" in globals() else Path(".")
DATA = Path(os.environ.get("PLAN_DATA", ROOT / "data"))
HEX_CSV, PARKS = DATA / "ch73_surabaya_hex.csv", DATA / "ch73_surabaya_parks.geojson"
RES = 8                      # H3 resolution 8: hexagons of about 0.74 km2, a neighbourhood
UTM = 32749                  # UTM 49S, metres
WALK = 400                   # metres: about five minutes on foot, a common park-access standard
MIN_PARK_HA = 0.5            # pocket parks smaller than this rarely serve a neighbourhood
LOW_M = 3                    # metres above sea level: the lowest quarter of the city
RTH_TARGET = 30              # % green open space required by Law 26/2007 (20 % public + 10 % private)


def city():
    import ee
    return ee.FeatureCollection("FAO/GAUL/2025/level2").filter(ee.Filter.eq("GAUL2_NAME", "Kota Surabaya"))


# PART 1. The grid -----------------------------------------------------------------------------
def hex_grid(boundary):
    """Every H3 cell whose centre lies inside the city, as polygons."""
    import h3
    cells = set()
    geoms = boundary.geoms if boundary.geom_type == "MultiPolygon" else [boundary]
    for g in geoms:
        cells |= set(h3.geo_to_cells(g.__geo_interface__, RES))
    rows = [{"h3": c, "geometry": Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(c)])} for c in sorted(cells)]
    return gpd.GeoDataFrame(rows, crs=4326)


# PART 2. Parks from OpenStreetMap --------------------------------------------------------------
def parks():
    """Public parks (leisure=park) of at least MIN_PARK_HA, from Overpass, saved once."""
    if PARKS.exists():
        return gpd.read_file(PARKS)
    import requests
    from shapely.ops import unary_union
    q = """[out:json][timeout:180];
    area["name"="Surabaya"]["admin_level"="5"]->.a;
    (way["leisure"="park"](area.a); relation["leisure"="park"](area.a););
    out geom;"""
    els = requests.post("https://overpass-api.de/api/interpreter", data={"data": q}, timeout=300,
                        headers={"User-Agent": "fullstack-remote-sensing-book"}).json()["elements"]
    polys = []
    for e in els:
        try:
            if e["type"] == "way" and len(e.get("geometry", [])) >= 4:
                polys.append({"name": e.get("tags", {}).get("name", ""), "geometry": Polygon([(p["lon"], p["lat"]) for p in e["geometry"]])})
            elif e["type"] == "relation":
                rings = [Polygon([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in e.get("members", [])
                         if m.get("role") == "outer" and len(m.get("geometry", [])) >= 4]
                if rings:
                    polys.append({"name": e.get("tags", {}).get("name", ""), "geometry": unary_union(rings)})
        except ValueError:
            continue
    g = gpd.GeoDataFrame(polys, crs=4326)
    g = g[g.geometry.is_valid]
    g["ha"] = g.to_crs(UTM).area / 1e4
    g = g[g.ha >= MIN_PARK_HA].reset_index(drop=True)
    DATA.mkdir(parents=True, exist_ok=True)
    g.to_file(PARKS, driver="GeoJSON")
    return g


# PART 3. Fill every hexagon from Earth Engine ---------------------------------------------------
def lst_image(geom):
    import ee
    def st(img):
        qa = img.select("QA_PIXEL")
        clear = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        return img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15).updateMask(clear)
    return (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
            .filterBounds(geom).filterDate("2023-06-01", "2024-10-31").filter(ee.Filter.calendarRange(6, 10, "month"))
            .map(st).median().rename("lst_c"))


def hexagons():
    """One row per hexagon: green, built, people, heat, low ground, new buildings and park access."""
    if HEX_CSV.exists():
        df = pd.read_csv(HEX_CSV)
        import h3
        return gpd.GeoDataFrame(df, geometry=[Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(c)]) for c in df.h3], crs=4326)
    import ee
    boundary = shape(city().geometry().getInfo())
    grid = hex_grid(boundary)
    geom = city().geometry()
    wc = ee.Image(ee.ImageCollection("ESA/WorldCover/v200").first()).select("Map")
    green = wc.eq(10).Or(wc.eq(20)).Or(wc.eq(30))            # tree cover, shrubland, grassland
    pop = ee.Image("JRC/GHSL/P2023A/GHS_POP/2020").select("population_count").max(0)
    elv = ee.Image("MERIT/Hydro/v1_0_1").select("elv")       # bias-corrected terrain, buildings and trees removed
    ob = lambda y: (ee.ImageCollection("GOOGLE/Research/open-buildings-temporal/v1").filterBounds(geom)
                    .filter(ee.Filter.calendarRange(y, y, "year")).mosaic().select("building_presence").gt(0.5))
    # Surabaya is a delta: HAND is under 5 m almost everywhere, so it cannot rank places.
    # Height above sea level can: land below 3 m is exposed to tidal flooding (rob) and river backwater.
    low = elv.lt(LOW_M)
    new_bldg = ob(2023).And(ob(2016).Not())
    # Park access: distance from every 100 m population cell to the nearest park edge.
    pk = parks()
    park_fc = ee.FeatureCollection([ee.Feature(ee.Geometry(g.__geo_interface__)) for g in pk.geometry])
    near_park = park_fc.distance(2000).lte(WALK).unmask(0)
    means = ee.Image.cat([
        green.rename("green_pct").multiply(100), wc.eq(10).rename("tree_pct").multiply(100),
        wc.eq(50).rename("built_pct").multiply(100), lst_image(geom), low.rename("low_pct").multiply(100),
        ob(2016).rename("bldg2016_pct").multiply(100), ob(2023).rename("bldg2023_pct").multiply(100)])
    sums = ee.Image.cat([pop.rename("people"), pop.multiply(near_park).rename("people_near_park"),
                         new_bldg.And(low).multiply(ee.Image.pixelArea()).rename("new_bldg_low_m2"),
                         new_bldg.multiply(ee.Image.pixelArea()).rename("new_bldg_m2")])
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(g.__geo_interface__), {"h3": h}) for h, g in zip(grid.h3, grid.geometry)])
    rows = []
    for i in range(0, len(grid), 150):                        # chunks keep each request within limits
        part = ee.FeatureCollection(fc.toList(150, i))
        a = means.reduceRegions(part, ee.Reducer.mean(), 10, tileScale=4).getInfo()["features"]
        b = sums.reduceRegions(part, ee.Reducer.sum(), 10, tileScale=4).getInfo()["features"]
        for x, y in zip(a, b):
            rows.append({**x["properties"], **{k: v for k, v in y["properties"].items() if k != "h3"}})
    df = pd.DataFrame(rows)
    # pop is per 100 m cell; summed at 10 m every cell is counted 100 times
    for c in ["people", "people_near_park"]:
        df[c] = df[c] / 100
    df["area_ha"] = grid.set_index("h3").to_crs(UTM).area.reindex(df.h3).values / 1e4
    import h3
    df["lat"], df["lon"] = zip(*[h3.cell_to_latlng(c) for c in df.h3])     # cell centres, for the R twin
    df.to_csv(HEX_CSV, index=False, float_format="%.5g")
    return hexagons()


def prepared():
    g = hexagons().copy()
    g["people_ha"] = g.people / g.area_ha
    g["park_access_pct"] = np.where(g.people > 0, 100 * g.people_near_park / g.people.clip(lower=1e-9), np.nan)
    return g


# PART 4. Question 1: does Surabaya meet the 30 % green rule? ----------------------------------------
def green_table():
    g = prepared()
    w = g.area_ha
    return pd.DataFrame([
        {"measure": "green cover, whole city (%)", "value": np.average(g.green_pct, weights=w)},
        {"measure": "tree cover, whole city (%)", "value": np.average(g.tree_pct, weights=w)},
        {"measure": f"hexagons meeting the {RTH_TARGET} % target", "value": int((g.green_pct >= RTH_TARGET).sum())},
        {"measure": "hexagons below 10 % green", "value": int((g.green_pct < 10).sum())},
        {"measure": "residents in hexagons below 10 % green (%)", "value": 100 * g.people[g.green_pct < 10].sum() / g.people.sum()},
        {"measure": f"residents within {WALK} m of a park ≥ {MIN_PARK_HA} ha (%)", "value": 100 * g.people_near_park.sum() / g.people.sum()},
        {"measure": "number of hexagons", "value": len(g)},
    ])


# PART 5. Question 2: does green cool, and is the effect local? Regression and Moran's I ----------------
def neighbours(cells):
    import h3
    idx = {c: i for i, c in enumerate(cells)}
    return [[idx[n] for n in h3.grid_ring(c, 1) if n in idx] for c in cells]


def morans_i(x, nb):
    """Moran's I with row-standardised contiguity weights, and a 999-permutation p-value."""
    x = np.asarray(x, float); z = x - x.mean()
    def stat(v):
        lag = np.array([v[n].mean() if n else 0 for n in nb])
        return (v * lag).sum() / (v ** 2).sum()
    obs = stat(z)
    rng = np.random.default_rng(0)
    perm = np.array([stat(rng.permutation(z)) for _ in range(999)])
    return obs, (1 + (perm >= obs).sum()) / 1000


_reg = {}


def regression():
    """Two models, to show a trap: the sign of 'green' depends on what it is compared with."""
    if _reg:
        return _reg
    import statsmodels.formula.api as smf
    g = prepared().dropna(subset=["lst_c"])
    g = g[g.people > 0].reset_index(drop=True)
    g["log_people_ha"] = np.log1p(g.people_ha)
    m1 = smf.ols("lst_c ~ green_pct", data=g).fit()
    m = smf.ols("lst_c ~ green_pct + built_pct + log_people_ha", data=g).fit()
    nb = neighbours(list(g.h3))
    _reg.update(g=g, m1=m1, m=m, moran_lst=morans_i(g.lst_c, nb), moran_resid=morans_i(m.resid, nb), nb=nb)
    return _reg


def regression_table():
    r = regression()
    rows = []
    for name, m in [("A: green only", r["m1"]), ("B: green + built + people", r["m"])]:
        ci = m.conf_int()
        rows += [{"model": name, "term": k, "coefficient": m.params[k], "95% CI low": ci.loc[k, 0],
                  "95% CI high": ci.loc[k, 1], "p": m.pvalues[k]} for k in m.params.index]
        rows.append({"model": name, "term": "R²", "coefficient": m.rsquared})
    rows += [{"model": "", "term": "Moran's I of LST", "coefficient": r["moran_lst"][0], "p": r["moran_lst"][1]},
             {"model": "B", "term": "Moran's I of residuals", "coefficient": r["moran_resid"][0], "p": r["moran_resid"][1]}]
    return pd.DataFrame(rows)


# PART 6. Question 3: where should greening go first? A composite index, and how robust it is -----------
CRITERIA = {"lst_c": +1, "people_ha": +1, "green_pct": -1, "park_access_pct": -1}   # +1: more is more urgent


def priority(weights=None):
    g = prepared().dropna(subset=["lst_c"])
    g = g[g.people >= 500].copy()                    # neighbourhoods with residents to serve
    w = weights or {k: 0.25 for k in CRITERIA}
    z = lambda s: (s - s.mean()) / s.std()
    g["score"] = sum(w[k] * d * z(g[k].fillna(g[k].median())) for k, d in CRITERIA.items())
    return g.sort_values("score", ascending=False)


def priority_table(n=10):
    g = priority()
    # Robustness: draw 1,000 random weight sets (Dirichlet), count how often each hexagon is in the top n.
    rng = np.random.default_rng(42)
    hits = pd.Series(0, index=g.h3)
    for w in rng.dirichlet(np.ones(len(CRITERIA)), 1000):
        top = priority(dict(zip(CRITERIA, w))).h3.head(n)
        hits[top] += 1
    g["in top 10 under random weights (%)"] = hits.reindex(g.h3).values / 10
    c = g.to_crs(UTM).geometry.centroid.to_crs(4326)
    g["lon"], g["lat"] = c.x.round(4), c.y.round(4)
    cols = ["h3", "lon", "lat", "lst_c", "people_ha", "green_pct", "park_access_pct", "score", "in top 10 under random weights (%)"]
    return g[cols].head(n).reset_index(drop=True)


# PART 7. Question 4: is the city building on low ground? ------------------------------------------------
def flood_table():
    g = prepared()
    land_low = np.average(g.low_pct, weights=g.area_ha)
    new_low = 100 * g.new_bldg_low_m2.sum() / g.new_bldg_m2.sum()
    return pd.DataFrame([
        {"measure": f"land below {LOW_M} m above sea level (%)", "value": land_low},
        {"measure": "new building cover 2016-2023 on that land (%)", "value": new_low},
        {"measure": "location quotient (new building share / land share)", "value": new_low / land_low},
        {"measure": "building cover 2016 (%)", "value": np.average(g.bldg2016_pct, weights=g.area_ha)},
        {"measure": "building cover 2023 (%)", "value": np.average(g.bldg2023_pct, weights=g.area_ha)},
    ])


# PART 8. Maps and charts -----------------------------------------------------------------------------
def graticule(ax, crs, n=4):
    """Latitude/longitude lines and edge labels on a map drawn in projected metres."""
    from pyproj import Transformer
    to_ll = Transformer.from_crs(crs, 4326, always_xy=True); to_xy = Transformer.from_crs(4326, crs, always_xy=True)
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    lon, lat = to_ll.transform([x0, x1, x0, x1], [y0, y0, y1, y1])
    span = max(max(lon) - min(lon), max(lat) - min(lat))
    step = next(s for s in (0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1) if span / s <= n + 1)
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


def hexmap(ax, g, col, cmap, title, vmin=None, vmax=None, label=""):
    g = g.to_crs(UTM)
    g.plot(col, ax=ax, cmap=cmap, vmin=vmin, vmax=vmax, edgecolor="white", linewidth=0.15,
           legend=True, legend_kwds={"shrink": 0.6, "label": label}, missing_kwds={"color": "#eeeeee"})
    ax.set_title(title, loc="left", fontsize=9)
    graticule(ax, UTM)


def plot_maps(t):
    g = prepared()
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
    hexmap(axes[0, 0], g, "green_pct", "Greens", "1. Green cover (%)", 0, 60, "%")
    hexmap(axes[0, 1], g, "park_access_pct", "Blues", f"2. Residents within {WALK} m of a park (%)", 0, 100, "%")
    hexmap(axes[1, 0], g, "lst_c", "inferno", "3. Dry-season land surface temperature (°C)", None, None, "°C")
    hexmap(axes[1, 1], g.assign(pd_=np.log10(g.people_ha.clip(lower=1))), "pd_", "viridis", "4. People per hectare (log10)", 0, 2.7, "log10")
    pk = parks().to_crs(UTM)
    pk.boundary.plot(ax=axes[0, 1], color="#08306b", linewidth=0.5)
    gt = green_table().set_index("measure").value
    fig.suptitle(f"Surabaya is {gt.iloc[0]:.0f} % green against a {RTH_TARGET} % target, and "
                 f"{gt.iloc[5]:.0f} % of residents live within a five-minute walk of a park",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


def plot_regression(t):
    r = regression(); g, m1, m = r["g"], r["m1"], r["m"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.4))
    sc = a1.scatter(g.green_pct, g.lst_c, c=g.built_pct, cmap="RdPu", s=12)
    xs = np.linspace(0, g.green_pct.max(), 50)
    a1.plot(xs, m1.params["Intercept"] + m1.params["green_pct"] * xs, color="#2166ac", lw=1.5,
            label=f"A, green only: {10 * m1.params['green_pct']:+.2f} °C per +10 %")
    a1.plot(xs, m.params["Intercept"] + m.params["green_pct"] * xs + m.params["built_pct"] * g.built_pct.mean()
            + m.params["log_people_ha"] * g.log_people_ha.mean(), color="k", lw=1.5, ls="--",
            label=f"B, built-up held fixed: {10 * m.params['green_pct']:+.2f} °C per +10 %")
    a1.legend(frameon=False, fontsize=8, loc="lower left")
    fig.colorbar(sc, ax=a1, label="built-up (%)", shrink=0.8)
    a1.set_xlabel("green cover (%)"); a1.set_ylabel("land surface temperature (°C)")
    a1.set_title("The sign of 'green' depends on what it replaces", loc="left", fontsize=9)
    a1.spines[["top", "right"]].set_visible(False)
    gg = g.assign(resid=m.resid.values).to_crs(UTM)
    lim = np.nanpercentile(np.abs(gg.resid), 98)
    gg.plot("resid", ax=a2, cmap="RdBu_r", vmin=-lim, vmax=lim, edgecolor="white", linewidth=0.15, legend=True,
            legend_kwds={"shrink": 0.6, "label": "°C"})
    graticule(a2, UTM)
    I, p = r["moran_resid"]
    a2.set_title(f"Model B residuals cluster in space: Moran's I = {I:.2f} (p = {p:.3f})", loc="left", fontsize=9)
    fig.suptitle("Built-up land explains the heat; green's effect flips sign once built-up is held fixed",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


def plot_priority(t):
    g = priority()
    top = priority_table()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.8), gridspec_kw={"width_ratios": [1.2, 1]})
    gg = g.to_crs(UTM)
    prepared().to_crs(UTM).plot(ax=a1, color="#eeeeee", edgecolor="white", linewidth=0.15)
    gg.plot("score", ax=a1, cmap="YlOrRd", edgecolor="white", linewidth=0.15, legend=True, legend_kwds={"shrink": 0.6, "label": "priority score"})
    gg[gg.h3.isin(top.h3)].boundary.plot(ax=a1, color="k", linewidth=1.2)
    graticule(a1, UTM)
    a1.set_title("Greening priority (equal weights); top 10 outlined", loc="left", fontsize=9)
    tt = top.iloc[::-1]
    a2.barh(range(len(tt)), tt["in top 10 under random weights (%)"], color="#d94801")
    a2.set_yticks(range(len(tt))); a2.set_yticklabels([f"#{len(tt) - i}  {lo:.3f}°E {abs(la):.3f}°S" for i, (lo, la) in enumerate(zip(tt.lon, tt.lat))], fontsize=7.5)
    a2.set_xlabel("share of 1,000 random weightings that keep it in the top 10 (%)"); a2.set_xlim(0, 100)
    a2.spines[["top", "right"]].set_visible(False)
    a2.set_title("How robust is each choice to the weights?", loc="left", fontsize=9)
    robust = int((top["in top 10 under random weights (%)"] >= 50).sum())
    fig.suptitle(f"{robust} of the top 10 stay in the top 10 under at least half of all random weightings",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


def products():
    return [
        {"kind": "table", "name": "ch73-green", "data": green_table, "floatfmt": ("", ".1f"),
         "caption": "Green cover, tree cover and park access in Kota Surabaya, on H3 resolution-8 hexagons."},
        {"kind": "chart", "name": "ch73-maps", "data": green_table, "plot": plot_maps, "live": False,
         "caption": "Four layers a planner reads together. Park outlines from OpenStreetMap on map 2."},
        {"kind": "table", "name": "ch73-regression", "data": regression_table, "floatfmt": ("", "", ".3f", ".3f", ".3f", ".2g"),
         "caption": "Ordinary least squares of land surface temperature per hexagon, and Moran's I before and after."},
        {"kind": "chart", "name": "ch73-regression-chart", "data": regression_table, "plot": plot_regression, "live": False,
         "caption": "Left: the partial effect of green cover. Right: where the model is too cool (red) or too warm (blue)."},
        {"kind": "table", "name": "ch73-priority", "data": priority_table,
         "floatfmt": ("", ".3f", ".3f", ".1f", ".0f", ".1f", ".0f", ".2f", ".0f"),
         "caption": "The ten hexagons where greening helps most: hot, crowded, bare and far from a park."},
        {"kind": "chart", "name": "ch73-priority-chart", "data": priority_table, "plot": plot_priority, "live": False,
         "caption": "The composite index, and a weight-sensitivity test."},
        {"kind": "table", "name": "ch73-flood", "data": flood_table, "floatfmt": ("", ".2f"),
         "caption": f"Building on low ground: new building cover 2016-2023 on land below {LOW_M} m above sea level."},
    ]


if __name__ == "__main__":
    import ee
    k = os.path.expanduser(os.environ.get("BOOK_EE_KEY", "~/.config/fullstack-rs/ee-key.json")); info = json.load(open(k))
    ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], k), project=info.get("project_id"))
    pd.set_option("display.width", 200)
    print(len(parks()), "parks"); print(green_table()); print(regression_table().round(3)); print(priority_table()); print(flood_table())
