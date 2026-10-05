"""Execute the generated notebooks locally (2026-10-05): the Colab setup cell is swapped for a local one (same
sys.path and __file__, Earth Engine via the book's service account); every other cell runs unchanged in a real
Jupyter kernel. Writes notebooks/_test/<stem>.log; prints PASS/FAIL per notebook."""
import json, os, sys, copy, time
from pathlib import Path
import nbformat
from nbclient import NotebookClient
ROOT = Path(__file__).resolve().parent.parent; OUT = ROOT / "notebooks" / "_test"; OUT.mkdir(exist_ok=True)
for stem in sys.argv[1:]:
    nb = nbformat.read(ROOT / "notebooks" / f"{stem}.ipynb", as_version=4)
    setup = nb.cells[1].source
    local = [f"import sys, os, matplotlib; matplotlib.use('Agg'); sys.path[:0] = ['{ROOT}/tools', '{ROOT}/scripts/py']; os.chdir('{ROOT}')",
             f"__file__ = '{ROOT}/scripts/py/{stem}.py'"]
    if "ee.Authenticate" in setup:
        local += ["import ee, json; k = os.path.expanduser('~/.config/fullstack-rs/ee-key.json'); info = json.load(open(k))",
                  "ee.Initialize(ee.ServiceAccountCredentials(info['client_email'], k), project=info['project_id'])",
                  "ee.Initialize = lambda *a, **kw: None"]
    nb.cells[1].source = "\n".join(local)
    t = time.time(); ok = True
    try:
        NotebookClient(nb, timeout=1800, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}).execute()
    except Exception as e:
        ok = False; err = str(e)[-600:]
    fails = [o.get("data", {}).get("text/markdown", "") for c in nb.cells if c.cell_type == "code" for o in c.get("outputs", [])
             if "failed:**" in o.get("data", {}).get("text/markdown", "")]
    (OUT / f"{stem}.log").write_text((err if not ok else "") + "\n".join(fails))
    print(f"{'PASS' if ok and not fails else 'FAIL'} {stem} ({time.time()-t:.0f}s){'' if ok else ' error: ' + err[-200:]}{' product failures: ' + str(len(fails)) if fails else ''}", flush=True)
