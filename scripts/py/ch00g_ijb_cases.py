#| title: IJB step by step: every module and four events, from the app's own engine (Python)
#| description: Renders the results the IJB app itself produced for one landscape run through every module (Kota Besi, Kotawaringin Timur: composite, 10-class model vs Dynamic World, GEDI canopy height and its scatter chart, height per desa, plantation age, disturbance year, K-Means) and for four real cases (the 2024 Demak flood, the 2023 Ogan Komering Ilir fires on peat, landslide susceptibility across West Java, and land change around the new capital), from the saved Earth Engine objects of each run.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
PRINCIPLES P6 | IJB step by step

Every number and map in this chapter was produced by the IJB app's own code
(users/rifkynauvalhsp/IndrajaBuana), not by a re-implementation. The app's
modules were run headless with tools/ijb_headless/harness.js: the Code Editor
interface is replaced by recording stubs, the inputs are typed in exactly as a
user would type them, and the module's own button is pressed. Each run saves
the metric cards and the Earth Engine objects behind every map layer to
data/p7_ijb/<case>.json. This script draws those layers; Earth Engine computes
them again from the saved recipe, so the maps are the app's results, not
pictures of them.

To repeat a run: clone the app repository, set IJB_SRC to the clone, and run
  node tools/ijb_headless/harness.js <job.json>
with a job file like the ones listed in CASES below.
"""

import json
import os
from pathlib import Path

import ee
import pandas as pd

ROOT = Path(__file__).resolve().parents[2] if "__file__" in globals() else Path(".")
DIR = ROOT / "data" / "p7_ijb"

# What was typed into the app for each case (the job files of the harness)
CASES = {
    "banjir_demak_2024": dict(module="Banjir", aoi="Kabupaten Demak", inputs="before 1-29 Feb 2024, after 14-24 Mar 2024; "
                              "descending orbit; DEM FABDEM; HAND limit 15 m (all defaults except the dates)"),
    "api_oki_2023": dict(module="Api", aoi="Kabupaten Ogan Komering Ilir", inputs="before 1 Jun-31 Jul 2023, after 15 Oct-30 Nov 2023"),
    "rawan_jabar_2024": dict(module="Rawan", aoi="Provinsi Jawa Barat", inputs="hazard Longsor, year 2024, DEM SRTM, 120 trees; "
                             "trained automatically from the NASA landslide catalogue"),
    "ubah_ppu_2019_2024": dict(module="Ubah", aoi="Kabupaten Penajam Paser Utara", inputs="index difference, NDVI, 2019 against 2024, threshold 0.2"),
}
EN = {"hektar tergenang": "flooded area (ha)", "jiwa terpapar": "people exposed", "bangunan": "buildings hit",
      "cocok riwayat": "overlap with past floods", "hektar terbakar": "burned area (ha)", "titik panas": "FIRMS hotspots",
      "hektar gambut": "burned area on peat (ha)", "tebal gambut rerata": "mean peat depth under the burn",
      "akurasi validasi": "validation accuracy", "kappa": "kappa", "hektar rawan tinggi": "high-susceptibility area (ha)",
      "jiwa di zona rawan": "people in susceptible zones", "hektar bertambah": "greener (ha)", "hektar berkurang": "browner (ha)"}


def load(case):
    return json.loads((DIR / f"{case}.json").read_text())


def layer(case, name):
    d = load(case)
    l = next(x for x in d["layers"] if x["name"] == name)
    return ee.deserializer.fromJSON(l["image"]), l["vis"], ee.deserializer.fromJSON(d["aoi"])


def metrics_table():
    rows = []
    for case, info in CASES.items():
        for m in load(case)["metrics"]:
            rows.append({"case": f'{info["module"]}: {info["aoi"]}', "card in the app": m["name"],
                         "in English": EN.get(m["name"], m["name"]), "value shown": m["value"]})
    return pd.DataFrame(rows)


def inputs_table():
    return pd.DataFrame([{"module": v["module"], "area": v["aoi"], "what was entered": v["inputs"]} for v in CASES.values()])


def vis(img, v):
    v = dict(v)
    if "palette" in v:
        v["palette"] = [c.lstrip("#") for c in v["palette"]]
    return img.visualize(**v)


def flood_map():
    s1, v1, aoi = layer("banjir_demak_2024", "Sentinel-1 sesudah")
    fl, v2, _ = layer("banjir_demak_2024", "Genangan banjir")
    return vis(s1, {"min": -25, "max": 0}).blend(vis(fl, {"palette": ["#1f78ff"]})), aoi


def fire_map():
    sw, _, aoi = layer("api_oki_2023", "Sentinel-2 SWIR sesudah")
    sev, v, _ = layer("api_oki_2023", "Keparahan bakar")
    peat, _, _ = layer("api_oki_2023", "Gambut terbakar")
    edge = peat.unmask(0).gt(0).focalMax(1).subtract(peat.unmask(0).gt(0)).selfMask()
    return vis(sw.select(0), {"min": 0, "max": 0.4}).blend(vis(sev, v)).blend(edge.visualize(palette=["000000"])), aoi


def demak_units():
    """The app's own exposure table for Demak, summarised per kecamatan (BPS boundaries)."""
    c = next(c for c in load("banjir_demak_2024")["charts"] if c["table"])
    return ee.FeatureCollection(ee.deserializer.fromJSON(c["table"]))


def kecamatan_table():
    rows = [f["properties"] for f in demak_units().getInfo()["features"]]
    d = pd.DataFrame(rows).rename(columns={"wilayah": "kecamatan", "luas_ha": "flooded_ha",
                                           "jiwa_terpapar": "people_exposed", "terbangun_m2": "built_up_m2"})
    d = d[d.flooded_ha > 0].sort_values("people_exposed", ascending=False)
    return d[["kecamatan", "flooded_ha", "people_exposed", "built_up_m2"]].head(12).reset_index(drop=True)


def kecamatan_map():
    # The app's table keeps names, not shapes; join it back to the same public BPS polygons by name.
    bps = ee.FeatureCollection("projects/shaped-producer-482312-m0/assets/ijb/idn_kecamatan_bps") \
        .filter(ee.Filter.eq("kab", "Demak"))
    joined = ee.Join.saveFirst("t").apply(bps, demak_units(), ee.Filter.equals(leftField="nama", rightField="wilayah"))
    units = ee.FeatureCollection(joined).map(lambda f: f.set("luas_ha", ee.Feature(f.get("t")).get("luas_ha")))
    fill = units.filter(ee.Filter.gt("luas_ha", 0)).reduceToImage(["luas_ha"], ee.Reducer.first())
    edge = ee.Image().byte().paint(bps, 1, 1)
    cls = fill.gt(0).add(fill.gte(100)).add(fill.gte(300)).add(fill.gte(600))      # 1..4
    img = cls.visualize(min=1, max=4, palette=["fec44f", "fe9929", "d95f0e", "993404"]) \
        .blend(edge.visualize(palette=["555555"]))
    return img, bps.geometry().bounds()


# ---------------------------------------------------------------------------
# One landscape, every module: Kota Besi (Kotawaringin Timur), reporting level Desa.
# Saved by the same harness to data/p6_ijb/<run>.json.
# ---------------------------------------------------------------------------
P6 = ROOT / "data" / "p6_ijb"
LULC = [("Perkebunan", "plantation", "f0e68c"), ("Hutan", "forest", "006400"), ("Pertanian", "agriculture", "ffd700"),
        ("Lahan Terbuka", "open land", "d2b48c"), ("Air", "water", "0000ff"), ("Mangrove", "mangrove", "2e8b57"),
        ("Sawah", "rice field", "00ffff"), ("Kelapa Sawit", "oil palm", "ffa500"), ("Sagu", "sago", "9acd32"),
        ("Karet", "rubber", "228b22")]
DWN = [("Air", "water"), ("Pohon", "trees"), ("Rumput", "grass"), ("Vegetasi tergenang", "flooded vegetation"),
       ("Tanaman", "crops"), ("Semak", "shrub and scrub"), ("Terbangun", "built"), ("Terbuka", "bare"), ("Salju", "snow and ice")]
DWP = ["419bdf", "397d49", "88b053", "7a87c6", "e49635", "dfc35a", "c4281b", "a59b8f", "b39fe1"]
P6_RUNS = {
    "citra_kotabesi": ("Citra", "Sentinel-2 composite, 1 Jun-31 Oct 2024, Cloud Score+ (default), natural colour"),
    "model10_kotabesi": ("Model", "Model 10 kelas milik sendiri, year 2024, minimum mapping unit 10 px"),
    "dw_kotabesi": ("Model", "Dynamic World, year 2024"),
    "tinggi_kotabesi": ("Model, then Toolbox", "Tinggi tajuk dari GEDI: GEDI 2019-04-01 to 2023-12-31, embeddings 2024, 150 trees; "
                                               "then Toolbox: Statistik zonal, Rerata, 30 m, per desa"),
    "umur_kotabesi": ("Deret", "Umur tegakan atau tanaman, 1990-2024, magnitude 0.2"),
    "gangguan_kotabesi": ("Deret", "Titik patah LandTrendr, 2000-2024, magnitude 0.2"),
    "tutupan_kotabesi": ("Tutupan", "K-Means, 6 clusters, Sentinel-2 composite 2024 (no training points needed)"),
}


def p6(run):
    return json.loads((P6 / f"{run}.json").read_text())


def p6_layer(run, name):
    d = p6(run); l = next(x for x in d["layers"] if x["name"] == name)
    return ee.deserializer.fromJSON(l["image"]), l["vis"], ee.deserializer.fromJSON(d["aoi"])


def p6_chart_table(run, i):
    return ee.FeatureCollection(ee.deserializer.fromJSON([c for c in p6(run)["charts"] if c["table"]][i]["table"]))


def p6_inputs_table():
    rows = []
    for run, (mod, inp) in P6_RUNS.items():
        cards = "; ".join(f'{m["name"]}: {m["value"]}' for m in p6(run)["metrics"] if m["value"] not in ("…", "n/a"))
        rows.append({"module": mod, "what was entered (Kota Besi, reporting level Desa)": inp, "cards the app showed": cards})
    return pd.DataFrame(rows)


def class_area(img, aoi, names, scale=30):
    g = (ee.Image.pixelArea().divide(1e4).addBands(img.rename("c"))
         .reduceRegion(ee.Reducer.sum().group(1, "c"), aoi, scale, maxPixels=1e10, tileScale=8).get("groups").getInfo())
    d = pd.DataFrame([{"class": names[int(r["c"])], "area_ha": r["sum"]} for r in g])
    d["share"] = d.area_ha / d.area_ha.sum()
    return d.sort_values("area_ha", ascending=False).reset_index(drop=True)


def model10_area():
    img, _, aoi = p6_layer("model10_kotabesi", "Tutupan lahan, model 10 kelas")
    d = class_area(img, aoi, [f"{e} ({i})" for i, e, _ in LULC])
    return d


def dw_vs_model10():
    """Where Dynamic World says 'trees', what does the author's model say?"""
    m10, _, aoi = p6_layer("model10_kotabesi", "Tutupan lahan, model 10 kelas")
    dw, _, _ = p6_layer("dw_kotabesi", "Dynamic World")
    d = class_area(m10.updateMask(dw.eq(1)), aoi, [f"{e} ({i})" for i, e, _ in LULC])
    return d.rename(columns={"class": "10-class model, inside Dynamic World 'trees'"})


def height_scatter():
    fc = p6_chart_table("tinggi_kotabesi", 0)
    return pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]])[["rh98", "prediksi"]]


def plot_scatter(d):
    import matplotlib.pyplot as plt
    import numpy as np
    r = np.corrcoef(d.rh98, d.prediksi)[0, 1]; rmse = float(np.sqrt(((d.prediksi - d.rh98) ** 2).mean()))
    fig, ax = plt.subplots(figsize=(5.4, 5))
    ax.scatter(d.rh98, d.prediksi, s=10, color="#31a354", alpha=0.6, edgecolor="none")
    ax.plot([0, 40], [0, 40], color="#1f2933", lw=1, ls="--", label="1:1 line (perfect prediction)")
    b = np.polyfit(d.rh98, d.prediksi, 1); xs = np.array([0, 40])
    ax.plot(xs, np.polyval(b, xs), color="#c0392b", lw=1.5, label=f"fitted line (slope {b[0]:.2f})")
    ax.set_xlim(0, 40); ax.set_ylim(0, 40); ax.set_aspect(1)
    ax.set_xlabel("GEDI rh98 measured by the laser (m)"); ax.set_ylabel("height the app predicted (m)")
    ax.set_title(f"Test shots: r = {r:.2f}, RMSE = {rmse:.1f} m, n = {len(d)}", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="upper left"); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def desa_height():
    fc = p6_chart_table("tinggi_kotabesi", 1)
    d = pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]]).rename(columns={"wilayah": "desa", "nilai": "mean_height_m"})
    return d.dropna().sort_values("mean_height_m", ascending=False).reset_index(drop=True)


def plot_desa(d):
    import matplotlib.pyplot as plt
    d = d.sort_values("mean_height_m")
    fig, ax = plt.subplots(figsize=(6.6, 0.22 * len(d) + 1))
    ax.barh(d.desa, d.mean_height_m, color="#31a354")
    ax.set_xlabel("mean modelled canopy height (m)"); ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Toolbox, Statistik zonal: canopy height per desa", loc="left", fontsize=10)
    fig.tight_layout()
    return fig


def year_area(run, name, band):
    img, _, aoi = p6_layer(run, name)
    h = img.rename("y").reduceRegion(ee.Reducer.frequencyHistogram(), aoi, 30, maxPixels=1e10, tileScale=8).get("y").getInfo()
    return pd.DataFrame(sorted((int(float(k)), v * 900 / 1e4) for k, v in h.items()), columns=[band, "area_ha"])


def plot_years(d, title, color):
    import matplotlib.pyplot as plt
    col = d.columns[0]
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.bar(d[col], d.area_ha, color=color)
    ax.set_ylabel("area (ha)"); ax.set_xlabel(col.replace("_", " ")); ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(title, loc="left", fontsize=10)
    fig.tight_layout()
    return fig


def p6_products():
    rgb = {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255}
    ci, civ, aoi = p6_layer("citra_kotabesi", "Warna alami · Cloud Score Plus (terbaik)")
    m10, _, _ = p6_layer("model10_kotabesi", "Tutupan lahan, model 10 kelas")
    dw, _, _ = p6_layer("dw_kotabesi", "Dynamic World")
    chm, chv, _ = p6_layer("tinggi_kotabesi", "Tinggi tajuk, meter")
    age, agv, _ = p6_layer("umur_kotabesi", "Umur, tahun")
    yod, ydv, _ = p6_layer("gangguan_kotabesi", "Tahun gangguan")
    km, _, _ = p6_layer("tutupan_kotabesi", "K-Means 6 klaster")
    # LandTrendr and K-Means over 600 km2 are too heavy for an on-the-fly thumbnail, so the app's results
    # were exported once (same images, 30 m) to public assets; the recipe above stays as the fallback.
    A = "projects/shaped-producer-482312-m0/assets/fullstack_rs/ijb_kotabesi/"
    def asset_or(name, img):
        try:
            ee.data.getAsset(A + name); return ee.Image(A + name)
        except ee.EEException:
            return img
    age = asset_or("umur", age); yod = asset_or("tahun_gangguan", yod); km = asset_or("kmeans", km.select("kelas")).rename("kelas")
    outline = ee.Image().byte().paint(ee.FeatureCollection([ee.Feature(aoi)]), 1, 2).visualize(palette=["000000"])
    pal = lambda v: [c.lstrip("#") for c in v["palette"]]
    src = "IJB app (users/rifkynauvalhsp/IndrajaBuana), run headless with the app's own code. GEE."
    return [
        {"kind": "table", "name": "p6-runs", "data": p6_inputs_table,
         "caption": "Every run in the walk-through: what was entered, and the result cards exactly as the app showed them."},
        {"kind": "map", "name": "p6-citra", "image": ci.visualize(**{k: v for k, v in civ.items() if k in ("min", "max", "gamma")}).blend(outline).clip(aoi.buffer(500)),
         "region": aoi, "vis": rgb, "title": "Citra: Kota Besi, dry season 2024", "source": src,
         "caption": "Step 1 of the walk-through: a clean Sentinel-2 composite of the kecamatan, from 62 scenes."},
        {"kind": "map", "name": "p6-model10", "image": m10.visualize(min=0, max=9, palette=[c for _, _, c in LULC]).clip(aoi), "region": aoi, "vis": rgb,
         "classes": [(f"{e}", "#" + c) for _, e, c in LULC], "title": "Model: the author's 10-class model, 2024", "source": src,
         "caption": "The author's own model, called from its asset: oil palm, rubber, sago, forest and plantations are separate classes."},
        {"kind": "table", "name": "p6-model10-area", "data": model10_area, "floatfmt": ("", ",.0f", ".0%"),
         "caption": "Area per class in Kota Besi from the 10-class model (the app's pie chart, as a table)."},
        {"kind": "map", "name": "p6-dw", "image": dw.visualize(min=0, max=8, palette=DWP).clip(aoi), "region": aoi, "vis": rgb,
         "classes": [(e, "#" + c) for (_, e), c in zip(DWN[:8], DWP[:8])], "title": "Model: Dynamic World, 2024", "source": src,
         "caption": "The global model on the same area: almost everything is 'trees'."},
        {"kind": "table", "name": "p6-dw-vs-model10", "data": dw_vs_model10, "floatfmt": ("", ",.0f", ".0%"),
         "caption": "What Dynamic World calls 'trees', split by the 10-class model. A global model sees canopy; a local model sees the crop."},
        {"kind": "map", "name": "p6-chm", "image": chm.visualize(min=0, max=35, palette=pal(chv)).clip(aoi), "region": aoi, "vis": rgb,
         "legend": "Canopy height (m), 0 to 35", "title": "Model: canopy height trained on GEDI", "source": src,
         "caption": "GEDI measures height only along its laser tracks; the app learns height from the embeddings and fills the whole area at 10 m."},
        {"kind": "chart", "name": "p6-scatter", "data": height_scatter, "plot": plot_scatter, "live": False,
         "caption": "The scatter chart the app now draws under the height map: each dot is one GEDI test shot the model never saw."},
        {"kind": "chart", "name": "p6-desa", "data": desa_height, "plot": plot_desa, "live": False,
         "caption": "Chained in the Toolbox: the height map summarised per desa with Statistik zonal."},
        {"kind": "map", "name": "p6-age", "image": age.visualize(min=0, max=25, palette=pal(agv)).clip(aoi), "region": aoi, "vis": rgb,
         "legend": "Age (years), 0 to 25", "title": "Deret: stand and plantation age", "source": src,
         "caption": "Age from the start of the largest LandTrendr growth segment in the annual NBR series."},
        {"kind": "chart", "name": "p6-age-years", "data": lambda: year_area("umur_kotabesi", "Tahun tanam", "planting_year"),
         "plot": lambda d: plot_years(d, "Area by planting (regrowth) year", "#1a9850"), "live": False,
         "caption": "The same result as a distribution: when were today's stands established?"},
        {"kind": "map", "name": "p6-disturb", "image": yod.visualize(min=2000, max=2024, palette=pal(ydv)).clip(aoi), "region": aoi, "vis": rgb,
         "legend": "Year of disturbance, 2000 to 2024", "title": "Deret: year of the largest disturbance (LandTrendr)", "source": src,
         "caption": "Clearing, fire or replanting: the year the NBR series dropped most."},
        {"kind": "chart", "name": "p6-disturb-years", "data": lambda: year_area("gangguan_kotabesi", "Tahun gangguan", "disturbance_year"),
         "plot": lambda d: plot_years(d, "Disturbed area per year", "#31688e"), "live": False,
         "caption": "The app's chart under the map: hectares disturbed in each year."},
        {"kind": "map", "name": "p6-kmeans", "image": km.select("kelas").randomVisualizer().select(["viz-red", "viz-green", "viz-blue"], ["vis-red", "vis-green", "vis-blue"]).clip(aoi), "region": aoi, "vis": rgb,
         "title": "Tutupan: six K-Means clusters, no samples", "source": src,
         "caption": "Unsupervised clusters: the app groups similar pixels; you name the groups (or train a Random Forest with your own points)."},
    ]


def products():
    fm, fa = flood_map()
    fi, fia = fire_map()
    ch, chv, cha = layer("ubah_ppu_2019_2024", "Selisih NDVI")
    rw, rwv, rwa = layer("rawan_jabar_2024", "Indeks kerawanan Longsor")
    rgb = {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255}
    km, kma = kecamatan_map()
    pal = lambda v: [c.lstrip("#") for c in v["palette"]]
    return [
        {"kind": "table", "name": "p7-inputs", "data": inputs_table, "caption": "What was entered in the app for each case."},
        {"kind": "table", "name": "p7-metrics", "data": metrics_table,
         "caption": "The metric cards exactly as the app displayed them (Indonesian number format: a point separates thousands)."},
        {"kind": "map", "name": "p7-banjir-demak", "image": fm, "region": fa, "vis": rgb,
         "classes": [("flooded, 14-24 March 2024", "#1f78ff")], "title": "Banjir: Demak, March 2024",
         "source": "IJB Banjir module (Sentinel-1, Otsu, FABDEM slope, JRC water, HAND). GEE.",
         "caption": "The app's flood layer over the post-event Sentinel-1 image."},
        {"kind": "map", "name": "p7-banjir-kecamatan", "image": km, "region": kma, "vis": rgb,
         "classes": [("under 100 ha", "#fec44f"), ("100-300 ha", "#fe9929"), ("300-600 ha", "#d95f0e"),
                     ("600 ha or more", "#993404")], "title": "Banjir: Demak, flooded area per kecamatan",
         "source": "IJB Banjir module, reporting level Kecamatan (BPS boundaries via OCHA COD-AB). GEE.",
         "caption": "The same flood, summarised the way a BPBD office reports it: per kecamatan."},
        {"kind": "table", "name": "p7-banjir-kecamatan-table", "data": kecamatan_table,
         "floatfmt": ("", ",.0f", ",.0f", ",.0f"),
         "caption": "The app's exposure table for Demak at the Kecamatan level, as downloaded from the app (top 12 by people exposed)."},
        {"kind": "map", "name": "p7-api-oki", "image": fi, "region": fia, "vis": rgb,
         "classes": [("low", "#ffe066"), ("moderate", "#ff9f1c"), ("high", "#e63946"), ("very high", "#7d1128"),
                     ("edge of burned peat", "#000000")],
         "title": "Api: Ogan Komering Ilir, 2023 fire season", "source": "IJB Api module (Sentinel-2 dNBR, FIRMS, peat maps). GEE.",
         "caption": "Burn severity classes from the app, with the outline of burned peat."},
        {"kind": "map", "name": "p7-ubah-ppu", "image": ch, "region": cha,
         "vis": {"min": chv["min"], "max": chv["max"], "palette": pal(chv)}, "title": "Ubah: NDVI 2024 minus 2019, Penajam Paser Utara",
         "source": "IJB Ubah module (Sentinel-2, Cloud Score+ composites). GEE.",
         "caption": "Red: less green in 2024 than in 2019; green: greener. The new capital's core lies in the north of the regency."},
        {"kind": "map", "name": "p7-rawan-jabar", "image": rw, "region": rwa,
         "vis": {"min": 0, "max": 1, "palette": pal(rwv)}, "title": "Rawan: landslide susceptibility, West Java 2024",
         "source": "IJB Rawan module (random forest on embeddings, terrain, rain, soil; NASA landslide catalogue). GEE.",
         "caption": "Modelled probability of landslide-like terrain, from the app's automatic training."},
    ] + p6_products()


if __name__ == "__main__":
    k = os.path.expanduser(os.environ.get("BOOK_EE_KEY", "~/.config/fullstack-rs/ee-key.json")); info = json.load(open(k))
    ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], k), project=info.get("project_id"))
    print(metrics_table())
