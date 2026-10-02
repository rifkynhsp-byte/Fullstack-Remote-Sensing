#| title: IJB at work: four case studies from the app's own engine (Python)
#| description: Renders the results the IJB app itself produced for four real cases (the 2024 Demak flood, the 2023 Ogan Komering Ilir fires on peat, landslide susceptibility across West Java, and land change around the new capital), from the saved Earth Engine objects of each run.

"""
PRINCIPLES P7 | IJB at work

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


def products():
    fm, fa = flood_map()
    fi, fia = fire_map()
    ch, chv, cha = layer("ubah_ppu_2019_2024", "Selisih NDVI")
    rw, rwv, rwa = layer("rawan_jabar_2024", "Indeks kerawanan Longsor")
    rgb = {"bands": ["vis-red", "vis-green", "vis-blue"], "min": 0, "max": 255}
    pal = lambda v: [c.lstrip("#") for c in v["palette"]]
    return [
        {"kind": "table", "name": "p7-inputs", "data": inputs_table, "caption": "What was entered in the app for each case."},
        {"kind": "table", "name": "p7-metrics", "data": metrics_table,
         "caption": "The metric cards exactly as the app displayed them (Indonesian number format: a point separates thousands)."},
        {"kind": "map", "name": "p7-banjir-demak", "image": fm, "region": fa, "vis": rgb,
         "classes": [("flooded, 14-24 March 2024", "#1f78ff")], "title": "Banjir: Demak, March 2024",
         "source": "IJB Banjir module (Sentinel-1, Otsu, FABDEM slope, JRC water, HAND). GEE.",
         "caption": "The app's flood layer over the post-event Sentinel-1 image."},
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
    ]


if __name__ == "__main__":
    k = os.path.expanduser(os.environ.get("BOOK_EE_KEY", "~/.config/fullstack-rs/ee-key.json")); info = json.load(open(k))
    ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], k), project=info.get("project_id"))
    print(metrics_table())
