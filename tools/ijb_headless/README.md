# IJB headless runner

Runs modules of the IJB app (`users/rifkynauvalhsp/IndrajaBuana`) outside the Code Editor, so the
book can show results produced by the app's own code (chapter P6).

    npm install @google/earthengine
    IJB_SRC=/path/to/clone/of/IndrajaBuana node harness.js job.json

A job names the module and its function, the area, and the values to type, then presses the
module's button. Example (Banjir, Demak 2024):

    {"module": "disaster", "fn": "flood",
     "aoi": {"collection": "FAO/GAUL/2025/level2", "field": "GAUL2_NAME", "value": "Demak"},
     "level": "Kabupaten", "textboxes": ["2024-02-01", "2024-02-29", "2024-03-14", "2024-03-24"],
     "out": "banjir_demak_2024.json"}

The output holds the metric cards and the serialised Earth Engine object of every map layer;
`scripts/py/ch00g_ijb_cases.py` draws them. Authentication uses a service-account key at
`~/.config/fullstack-rs/ee-key.json` (never commit a key).
