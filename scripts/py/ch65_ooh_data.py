#| title: Building the open inputs for the Sydney OOH study (Python)
#| description: Downloads and derives every input of Chapter 65 from open sources - City of Sydney walking counts, employment survey, bus shelters and banners; OpenStreetMap points of interest, roads, stops and bus routes; GHSL building surface and volume, VIIRS night lights and WorldPop age structure from Earth Engine; ABS Census income - into one folder.

"""
CHAPTER 65 | The inputs, rebuilt from open data

Writes OOH_DATA (default data/ooh_sydney):
  candidates.gpkg   a point every 100 m along the streets (where footfall is predicted)
  counts.gpkg       walking count sites with the mean weekday count of the three
                    post-COVID surveys (autumn 2022, spring 2022, autumn 2023)
  employment.gpkg   2022 floor space and employment survey blocks
  areas.gpkg        ABS SA2 areas: median household income (Census 2021) and
                    WorldPop 2020 population by age band
  shelters.gpkg, banners.gpkg, routes.gpkg   the advertising inventory
  surfaces/*.tif    20 m density surfaces on GDA2020 / MGA zone 56

Environment: pip install osmnx geopandas rasterio scipy earthengine-api requests
Earth Engine: a service-account key in BOOK_EE_KEY, or `earthengine authenticate`.
"""

import io
import json
import os
from pathlib import Path

import ee
import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
import rasterio
import requests
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.ndimage import convolve

OUT = Path(os.environ.get("OOH_DATA", "data/ooh_sydney")); (OUT / "surfaces").mkdir(parents=True, exist_ok=True)
PLACE = "City of Sydney, New South Wales, Australia"
CRS = "EPSG:7856"          # GDA2020 / MGA zone 56: metres
CELL = 20                  # surface resolution (m)
KERNEL = 250               # heat-map radius (m), quartic kernel as in QGIS
COS = "https://services1.arcgis.com/cNVyNtjGVZybOQWZ/arcgis/rest/services"


def arcgis(service, where="1=1"):
    """All features of a City of Sydney feature service, paged."""
    frames, offset = [], 0
    while True:
        r = requests.get(f"{COS}/{service}/FeatureServer/0/query", timeout=120, params=dict(
            where=where, outFields="*", outSR=4326, f="geojson", resultOffset=offset, resultRecordCount=2000))
        g = gpd.read_file(io.StringIO(r.text))
        frames.append(g); offset += len(g)
        if len(g) < 2000:
            break
    return pd.concat(frames, ignore_index=True).set_crs(4326, allow_override=True)


def main():
    global x0, y0, x1, y1, W, H, TRANSFORM, area
    # PART 1. Study area, counts, employment, inventory -----------------------------------
    area = ox.geocode_to_gdf(PLACE).to_crs(CRS)
    bounds = area.total_bounds; pad = 1500     # buffers reach 1 km beyond the boundary
    x0, y0, x1, y1 = bounds[0] - pad, bounds[1] - pad, bounds[2] + pad, bounds[3] + pad
    W, H = int((x1 - x0) / CELL), int((y1 - y0) / CELL)
    TRANSFORM = from_origin(x0, y1, CELL, CELL)

    sites = arcgis("WalkingCountSites").to_crs(CRS)
    surveys = arcgis("Walking_count_surveys", "Period='weekday'").drop(columns="geometry")
    recent = surveys[((surveys.Year == 2022) | ((surveys.Year == 2023) & (surveys.Month == "Autumn")))]
    target = recent.groupby("SiteID").TotalCount.agg(["mean", "count"]).rename(
        columns={"mean": "weekday_count", "count": "n_surveys"})
    counts = sites.merge(target, left_on="Site_ID", right_index=True, how="left")
    counts.to_file(OUT / "counts.gpkg")
    print(f"count sites {len(counts)}, with a recent weekday count {counts.weekday_count.notna().sum()}")

    emp = arcgis("FES2022_Block_Data").to_crs(CRS)
    emp["jobs_per_ha"] = emp.Total_Jobs / (emp.geometry.area / 1e4)
    emp["floor_ratio"] = emp.Internal_FloorArea / emp.geometry.area
    emp[["BLOCKNUM", "Total_Jobs", "Businesses", "jobs_per_ha", "floor_ratio", "geometry"]].to_file(OUT / "employment.gpkg")

    arcgis("Bus_shelters").to_crs(CRS).to_file(OUT / "shelters.gpkg")
    arcgis("Banner_poles_audit_1").to_crs(CRS).to_file(OUT / "banners.gpkg")

    # Bus routes are OSM relations, which osmnx does not return as lines: ask
    # Overpass for every bus-route relation in the area with its member ways.
    s_, w_, n_, e_ = area.to_crs(4326).total_bounds[[1, 0, 3, 2]]
    q = f'[out:json][timeout:180];relation["route"="bus"]({s_},{w_},{n_},{e_});out geom;'
    els = requests.post("https://overpass-api.de/api/interpreter", data={"data": q}, timeout=300,
                        headers={"User-Agent": "fullstack-remote-sensing-book"}).json()["elements"]
    from shapely.geometry import LineString, MultiLineString
    rows = []
    for el in els:
        lines = [LineString([(g["lon"], g["lat"]) for g in m["geometry"]]) for m in el.get("members", [])
                 if m.get("type") == "way" and len(m.get("geometry", [])) > 1]
        if lines:
            tags = el.get("tags", {})
            rows.append({"route": tags.get("ref") or tags.get("name"), "name": tags.get("name"),
                         "geometry": MultiLineString(lines)})
    routes = gpd.GeoDataFrame(rows, crs=4326).dropna(subset=["route"]).to_crs(CRS)
    routes = routes.dissolve("route", aggfunc="first").reset_index()
    routes["geometry"] = routes.intersection(area.geometry.iloc[0].buffer(500))    # the part inside the city
    routes = routes[~routes.is_empty]
    routes.to_file(OUT / "routes.gpkg")
    print(f"bus routes {len(routes)}")


    # PART 2. Density surfaces from OpenStreetMap ---------------------------------------------
    def osm_points(tags):
        g = ox.features_from_place(PLACE, tags=tags).to_crs(CRS)
        return g.geometry.representative_point()


    def heat(points=None, lines=None):
        """Quartic-kernel density on the 20 m grid: points per km2, or line km per km2."""
        grid = np.zeros((H, W))
        if points is not None:
            c = ((points.x - x0) / CELL).astype(int); r = ((y1 - points.y) / CELL).astype(int)
            ok = (c >= 0) & (c < W) & (r >= 0) & (r < H)
            np.add.at(grid, (r[ok], c[ok]), 1.0)
        if lines is not None:   # length of road in each cell, km
            seg = lines.explode(index_parts=False).segmentize(CELL / 2)
            pts = seg.get_coordinates()
            d = np.hypot(np.diff(pts.x), np.diff(pts.y)); same = pts.index[1:] == pts.index[:-1]
            mx, my = (pts.x.values[1:] + pts.x.values[:-1]) / 2, (pts.y.values[1:] + pts.y.values[:-1]) / 2
            c = ((mx - x0) / CELL).astype(int); r = ((y1 - my) / CELL).astype(int)
            ok = same & (c >= 0) & (c < W) & (r >= 0) & (r < H)
            np.add.at(grid, (r[ok], c[ok]), d[ok] / 1000)
        n = int(KERNEL / CELL); yy, xx = np.mgrid[-n:n + 1, -n:n + 1] * CELL
        k = np.clip(1 - (xx ** 2 + yy ** 2) / KERNEL ** 2, 0, None) ** 2
        k = k / k.sum() / (CELL * CELL / 1e6)       # per km2
        return convolve(grid, k, mode="constant").astype("float32")


    def write(name, arr):
        with rasterio.open(OUT / "surfaces" / f"{name}.tif", "w", driver="GTiff", height=H, width=W, count=1,
                           dtype="float32", crs=CRS, transform=TRANSFORM, nodata=-9999) as dst:
            dst.write(arr.astype("float32"), 1)


    write("poi", heat(osm_points({"amenity": True, "shop": True, "leisure": True, "tourism": True})))
    write("fastfood_poi", heat(osm_points({"amenity": ["fast_food", "food_court"]})))
    write("education_poi", heat(osm_points({"amenity": ["school", "university", "college", "kindergarten", "language_school"]})))
    write("financial_poi", heat(osm_points({"amenity": ["bank", "atm", "bureau_de_change"], "office": ["financial", "insurance"]})))
    write("bus_station", heat(osm_points({"highway": "bus_stop", "railway": "station", "public_transport": "station"})))
    roads = ox.features_from_place(PLACE, tags={"highway": ["primary", "secondary", "tertiary", "residential",
                                                            "pedestrian", "footway", "living_street", "unclassified"]})
    road_lines = roads[roads.geom_type.isin(["LineString", "MultiLineString"])].to_crs(CRS)
    write("road_density", heat(lines=road_lines.geometry))

    # Candidate locations: a point every 100 m along the street network inside the
    # city, rounded to a 50 m grid so parallel carriageways do not double up. These
    # are where footfall is predicted and what the advertising inventory is scored on.
    inside = road_lines.clip(area)
    pts = inside.geometry.explode(index_parts=False).apply(
        lambda g: [g.interpolate(d) for d in np.arange(0, g.length, 100)]).explode().dropna()
    cand = gpd.GeoDataFrame(geometry=gpd.GeoSeries(list(pts), crs=CRS))
    cand["k"] = list(zip((cand.geometry.x // 50).astype(int), (cand.geometry.y // 50).astype(int)))
    cand = cand.drop_duplicates("k").drop(columns="k").reset_index(drop=True)
    cand.to_file(OUT / "candidates.gpkg")
    print(f"candidate street locations {len(cand)}")
    write("jobs", rasterize(((g, v) for g, v in zip(emp.geometry, emp.jobs_per_ha.fillna(0))),
                            out_shape=(H, W), transform=TRANSFORM, fill=0, dtype="float32"))


    # PART 3. Earth Engine: buildings, night lights, population by age -----------------------------
    key = os.environ.get("BOOK_EE_KEY")
    if key:
        info = json.load(open(os.path.expanduser(key)))
        ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], os.path.expanduser(key)), project=info.get("project_id"))
    else:
        ee.Initialize(project=os.environ.get("BOOK_EE_PROJECT"))
    region = ee.Geometry.Rectangle([x0, y0, x1, y1], ee.Projection(CRS), False)


    def ee_surface(name, image):
        url = image.getDownloadURL(dict(region=region, crs=CRS, crsTransform=[CELL, 0, x0, 0, -CELL, y1],
                                        dimensions=f"{W}x{H}", format="GEO_TIFF"))
        with rasterio.open(io.BytesIO(requests.get(url, timeout=600).content)) as src:
            write(name, src.read(1))


    ghsl = "JRC/GHSL/P2023A/"
    ee_surface("building_surface", ee.Image(ghsl + "GHS_BUILT_S/2020").select("built_surface"))
    ee_surface("building_volume", ee.Image(ghsl + "GHS_BUILT_V/2020").select("built_volume_total"))
    viirs = ee.ImageCollection("NOAA/VIIRS/DNB/ANNUAL_V22").filterDate("2022-01-01", "2023-01-01").first()
    ee_surface("nighttime", viirs.select("average"))

    # SA2 areas: Census income from the ABS Data API, population by age from WorldPop.
    sa2 = gpd.read_file(requests.get("https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/SA2/MapServer/0/query",
                                     timeout=300, params=dict(where="1=1", outFields="sa2_code_2021,sa2_name_2021",
                                                              geometry=f"{x0},{y0},{x1},{y1}", inSR=7856,
                                                              geometryType="esriGeometryEnvelope", outSR=4326,
                                                              f="geojson")).text)
    g02 = pd.read_csv(io.StringIO(requests.get("https://data.api.abs.gov.au/rest/data/C21_G02_SA2/all",
                                               params={"format": "csv"}, timeout=300).text))
    inc = g02[(g02.MEDAVG == 4)].assign(REGION=lambda d: d.REGION.astype(str)).set_index("REGION").OBS_VALUE
    sa2["income_weekly"] = sa2.sa2_code_2021.astype(str).map(inc)
    pop = ee.ImageCollection("WorldPop/GP/100m/pop_age_sex").filter(ee.Filter.eq("country", "AUS")) \
        .filter(ee.Filter.eq("year", 2020)).first()
    bands = {"total_population": ["population"],
             "pop1545": [f"{s}_{a}" for s in "MF" for a in (15, 20, 25, 30, 35, 40)],
             "pop2035": [f"{s}_{a}" for s in "MF" for a in (20, 25, 30)],
             "pop4065": [f"{s}_{a}" for s in "MF" for a in (40, 45, 50, 55, 60)]}
    img = ee.Image.cat([pop.select(b).reduce(ee.Reducer.sum()).rename(k) for k, b in bands.items()])
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(g.__geo_interface__), {"i": i}) for i, g in enumerate(sa2.geometry)])
    res = img.reduceRegions(fc, ee.Reducer.sum(), 100).getInfo()["features"]
    vals = pd.DataFrame([f["properties"] for f in res]).set_index("i")
    sa2 = sa2.join(vals[list(bands)]).to_crs(CRS)
    sa2.to_file(OUT / "areas.gpkg")
    print("wrote", sorted(p.name for p in OUT.rglob("*") if p.is_file()))


if __name__ == "__main__":
    main()
