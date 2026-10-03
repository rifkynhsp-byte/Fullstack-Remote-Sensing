# Book data published as public Earth Engine assets

Everything here is readable by anyone with an Earth Engine account, straight from the Code Editor.

| Asset | Chapters | Contents | Source and licence |
|---|---|---|---|
| `projects/shaped-producer-482312-m0/assets/fullstack_rs/drone_oilpalm_banjarbaru_30cm` | 27, 61 | RGB drone orthophoto of a smallholder oil palm block near Banjarbaru, bands R, G, B, resampled to 0.3 m | OpenAerialMap (HOT), CC BY 4.0 |
| `.../fullstack_rs/ooh_sydney/counts` | 65 | City of Sydney walking-count sites with the 2022-2023 weekday mean | City of Sydney open data, CC BY 4.0 |
| `.../fullstack_rs/ooh_sydney/employment` | 65 | Employment survey blocks | City of Sydney open data, CC BY 4.0 |
| `.../fullstack_rs/ooh_sydney/areas` | 65 | SA2 areas with income and population | ABS Census 2021, CC BY 4.0 |
| `.../fullstack_rs/ooh_sydney/shelters`, `banners`, `routes`, `candidates` | 65 | Bus shelters, city banners, bus routes, street candidate locations | City of Sydney open data; OpenStreetMap (ODbL) |
| `.../fullstack_rs/ooh_sydney/surface_*` (10 images) | 65 | 20 m density surfaces: building surface and volume, bus stations, POIs (all, education, fast food, financial), jobs, night lights, road density | GHSL, VIIRS, OpenStreetMap, City of Sydney |
| `.../fullstack_rs/surabaya/parks_osm` | 73 | Public parks of at least 0.5 ha in Kota Surabaya | OpenStreetMap (ODbL) |
| `.../book/train_bandung_2021`, `lulc_rf_fromtable`, `lulc_rf_trees` | 51 | Training table (embeddings + WorldCover label), the saved classifier (route A) and its trees as text (route B) | Satellite Embedding 2021; ESA WorldCover (CC BY 4.0) |

`...` stands for `projects/shaped-producer-482312-m0/assets`. Table field names are cut to 10 characters by the shapefile format used for ingestion.

Larger or non-raster inputs (the full 3.7 cm orthophoto, GTFS, OOH, map inputs) are also kept as offline snapshots on the GitHub release `data-v1`.
