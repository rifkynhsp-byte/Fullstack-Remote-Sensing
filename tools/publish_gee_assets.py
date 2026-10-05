"""Publish the book's own input data as public Earth Engine assets.

For each local file: stage it in Cloud Storage, ingest it as an image (GeoTIFF)
or a table (vector file, converted to a zipped shapefile), wait for the
ingestion, then set "anyone can read". Readers can then use the data straight
from the Code Editor.

    python tools/publish_gee_assets.py ooh       # chapter 65 inputs
    python tools/publish_gee_assets.py parks     # chapter 73 parks
    python tools/publish_gee_assets.py jakartaflood   # chapter 39 training polygons

Credentials: the service-account key at $BOOK_EE_KEY
(~/.config/fullstack-rs/ee-key.json by default). Never commit a key.
"""

import json
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import ee
from google.cloud import storage

KEY = os.path.expanduser(os.environ.get("BOOK_EE_KEY", "~/.config/fullstack-rs/ee-key.json"))
BUCKET, PREFIX = "satellite-rhsp", "fullstack-rs/"
ROOT = "projects/shaped-producer-482312-m0/assets/fullstack_rs"


def connect():
    info = json.load(open(KEY))
    ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], KEY), project=info["project_id"])
    return storage.Client.from_service_account_json(KEY)


def ensure_folder(path):
    try:
        ee.data.getAsset(path)
    except ee.EEException:
        ee.data.createAsset({"type": "FOLDER"}, path)
    make_public(path)


def make_public(asset):
    acl = ee.data.getAssetAcl(asset)
    acl["all_users_can_read"] = True
    ee.data.setAssetAcl(asset, json.dumps(acl))


def stage(gcs, local, name):
    blob = gcs.bucket(BUCKET).blob(PREFIX + name)
    blob.upload_from_filename(str(local))
    return f"gs://{BUCKET}/{blob.name}"


def as_shapefile_zip(vector_path):
    """Any vector file -> zipped shapefile in WGS84 (the most reliable table ingestion format)."""
    import geopandas as gpd
    g = gpd.read_file(vector_path).to_crs(4326)
    g.columns = [c[:10] for c in g.columns]          # shapefile field names: 10 characters
    tmp = Path(tempfile.mkdtemp())
    shp = tmp / (Path(vector_path).stem + ".shp")
    g.to_file(shp)
    z = tmp / (Path(vector_path).stem + ".zip")
    with zipfile.ZipFile(z, "w") as zf:
        for f in tmp.glob(Path(vector_path).stem + ".*"):
            if f.suffix != ".zip":
                zf.write(f, f.name)
    return z


def ingest(gcs, local, asset_id, kind, properties=None):
    try:
        ee.data.getAsset(asset_id)
        print("exists, skipped:", asset_id)
        return None
    except ee.EEException:
        pass
    if kind == "image":
        uri = stage(gcs, local, Path(local).name)
        manifest = {"name": asset_id, "tilesets": [{"sources": [{"uris": [uri]}]}], "properties": properties or {}}
        op = ee.data.startIngestion(ee.data.newTaskId()[0], manifest)
    else:
        z = as_shapefile_zip(local)
        uri = stage(gcs, z, z.name)
        manifest = {"name": asset_id, "sources": [{"uris": [uri]}], "properties": properties or {}}
        op = ee.data.startTableIngestion(ee.data.newTaskId()[0], manifest)
    return op["name"], asset_id


def wait_and_publish(jobs):
    for op, asset_id in [j for j in jobs if j]:
        while True:
            st = ee.data.getOperation(op)["metadata"]["state"]
            if st in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break
            time.sleep(15)
        if st == "SUCCEEDED":
            make_public(asset_id)
        print(st, asset_id)


SETS = {
    "ooh": dict(folder="ooh_sydney", src=Path(os.environ.get("OOH_DATA", "data/ooh_sydney")),
                source="City of Sydney open data, OpenStreetMap, GHSL, VIIRS, WorldPop, ABS Census 2021; built by scripts/py/ch65_ooh_data.py"),
    "parks": dict(folder="surabaya", src=Path("data"), source="OpenStreetMap leisure=park >= 0.5 ha (ODbL)"),
    "jakartaflood": dict(folder="jakarta_flood", src=Path("data"),
                         source="Training polygons for the 1 Jan 2020 Jakarta flood, drawn for the book (chapter 39)"),
}


def main(which):
    gcs = connect()
    s = SETS[which]
    folder = f"{ROOT}/{s['folder']}"
    ensure_folder(ROOT)
    ensure_folder(folder)
    jobs = []
    if which == "ooh":
        for f in sorted(s["src"].glob("*.gpkg")):
            jobs.append(ingest(gcs, f, f"{folder}/{f.stem}", "table", {"source": s["source"]}))
        for f in sorted((s["src"] / "surfaces").glob("*.tif")):
            jobs.append(ingest(gcs, f, f"{folder}/surface_{f.stem}", "image", {"source": s["source"]}))
    elif which == "parks":
        jobs.append(ingest(gcs, s["src"] / "ch73_surabaya_parks.geojson", f"{folder}/parks_osm", "table", {"source": s["source"]}))
    elif which == "jakartaflood":
        jobs.append(ingest(gcs, s["src"] / "jakarta_flood2020_training.geojson", f"{folder}/jakarta_flood2020_training",
                           "table", {"source": s["source"]}))
    wait_and_publish(jobs)


if __name__ == "__main__":
    main(sys.argv[1])
