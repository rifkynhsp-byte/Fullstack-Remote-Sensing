// Runs IJB (users/rifkynauvalhsp/IndrajaBuana) module code headless: the app's own
// Earth Engine logic, with the Code Editor ui replaced by recording stubs.
// Usage: node harness.js <job.json>   (job: module, fn, aoiAsset/filter, inputs, level, out)
const fs = require("fs");
const path = require("path");
const ee = require("@google/earthengine");

const SRC = process.env.IJB_SRC || "/mnt/c/Users/Rifky/Documents/GEE/rifkynauvalhsp/IndrajaBuana";
const job = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const key = JSON.parse(fs.readFileSync(process.env.HOME + "/.config/fullstack-rs/ee-key.json", "utf8"));

// ---------------------------------------------------------------- ui stubs
const created = { textboxes: [], selects: [], sliders: [], buttons: [], labels: [], charts: [] };
const metrics = [];
function widget(kind, props) {
  const w = Object.assign({ kind, value: undefined, children: [] }, props || {});
  const style = { set() { return style; }, get() { return undefined; } };
  const base = {
    getValue() { return w.value; },
    setValue(v) { w.value = v; return proxy; },
    style() { return style; },
    add(c) { w.children.push(c); return proxy; },
    clear() { w.children = []; return proxy; },
    widgets() { return { reset() {}, add() {}, get() { return undefined; }, length() { return 0; }, forEach() {} }; },
    onClick(cb) { w.onClickCb = cb; return proxy; },
    onChange(cb) { w.onChangeCb = cb; return proxy; },
    getLabel() { return w.label; },
  };
  const proxy = new Proxy(base, {
    get(t, p) {
      if (p in t) return t[p];
      if (p === "_w") return w;
      return function () { return proxy; };            // any other widget method: chainable no-op
    },
  });
  return proxy;
}
function chainable(record) {
  const f = function () { return chainable(record); };
  return new Proxy(f, { get(t, p) { return function () { return chainable(record); }; }, apply() { return chainable(record); } });
}
const ui = {
  Label(text) { const l = widget("Label", { value: typeof text === "object" && text ? text.value : text }); created.labels.push(l); return l; },
  Textbox(ph, value) { const t = widget("Textbox", { value: typeof ph === "object" && ph ? ph.value : value }); created.textboxes.push(t); return t; },
  Select(o) { const s = widget("Select", { value: o && o.value, items: o && o.items }); created.selects.push(s); return s; },
  Slider(o) { const s = widget("Slider", { value: o && o.value }); created.sliders.push(s); return s; },
  Checkbox(o) { return widget("Checkbox", { value: o && (o.value || false) }); },
  Button(o, cb) { const b = widget("Button", typeof o === "object" ? { label: o.label, onClickCb: o.onClick } : { label: o, onClickCb: cb }); created.buttons.push(b); return b; },
  Panel(children) {
    const p = widget("Panel", { children: children || [] });
    // core.metric: Panel([value "—", Label(name)]) -> remember the pair
    if (Array.isArray(children) && children.length === 2 && children[0]._w && children[1]._w &&
        children[0]._w.kind === "Label" && children[1]._w.kind === "Label" && children[0]._w.value === "—") {
      metrics.push({ name: children[1]._w.value, label: children[0] });
    }
    return p;
  },
  Thumbnail() { return widget("Thumbnail"); },
  Map: function () { return widget("Map"); },
  Chart: new Proxy({}, { get(t, kind) {
    return new Proxy({}, { get(t2, fn) { return function () { created.charts.push({ kind, fn, args: Array.from(arguments) }); return chainable(); }; } });
  } }),
  util: { setTimeout(f) { setTimeout(f, 0); }, debounce(f) { return f; } },
  root: widget("root"),
  url: { get() {}, set() {} },
};
ui.Panel.Layout = { flow() {}, absolute() {} };
ui.Map.Layer = function () { return widget("Layer"); };
ui.Map.Linker = function () {};
ui.Map.DrawingTools = function () {};

// ---------------------------------------------------------------- fake map and context
const layers = [];
const fakeMap = new Proxy({ addLayer(img, vis, name) { layers.push({ img, vis, name }); return widget("Layer"); },
  layers() { return { reset() {}, add() {}, forEach() {}, length() { return 0; } }; } },
  { get(t, p) { return p in t ? t[p] : function () { return widget("x"); }; } });
let status = "";
const K = {
  map: fakeMap,
  state: { aoi: null, reportLevel: job.level || "Kabupaten", lastResult: null, lastResultName: null, lastVector: null },
  clearResults() {}, setLegend() {}, setStatus(s) { status = s; if (s) console.error("[status]", s); }, onResult() {},
};

// ---------------------------------------------------------------- module loader (require "users/...:name")
const cache = {};
function req(id) {
  const name = id.split(":")[1];
  if (cache[name]) return cache[name];
  const exportsObj = {};
  cache[name] = exportsObj;
  const code = fs.readFileSync(path.join(SRC, name), "utf8");
  const fn = new Function("ee", "ui", "require", "exports", "print", "Map", "Export", "Chart", code);
  fn(ee, ui, req, exportsObj, (...a) => console.error("[print]", ...a.map(String)), fakeMap, {}, ui.Chart);
  return exportsObj;
}

// ---------------------------------------------------------------- pending evaluate() tracking
let pending = 0;
const origEval = ee.ComputedObject.prototype.evaluate;
ee.ComputedObject.prototype.evaluate = function (cb) {
  pending++;
  return origEval.call(this, function (v, e) {
    try { cb(v, e); } catch (err) { console.error("[callback error]", err.message); }
    pending--;
  });
};

function settle(done) {
  let quiet = 0;
  const t = setInterval(() => {
    quiet = pending === 0 ? quiet + 1 : 0;
    if (quiet >= 5) { clearInterval(t); done(); }
  }, 1000);
}

// ---------------------------------------------------------------- run
ee.data.authenticateViaPrivateKey(key, () => {
  ee.initialize(null, null, () => {
    const mod = req("users/rifkynauvalhsp/IndrajaBuana:" + job.module);
    mod.bind(K);
    K.state.aoi = ee.FeatureCollection(job.aoi.collection).filter(ee.Filter.eq(job.aoi.field, job.aoi.value)).geometry();
    mod[job.fn]();
    // inputs in creation order
    (job.textboxes || []).forEach((v, i) => { if (v !== null) created.textboxes[i].setValue(v); });
    (job.selects || []).forEach((v, i) => { if (v !== null) created.selects[i].setValue(v); });
    (job.sliders || []).forEach((v, i) => { if (v !== null) created.sliders[i].setValue(v); });
    const btn = created.buttons.find((b) => b._w.label === (job.button || "Jalankan analisis"));
    console.error("[run]", job.module, job.fn, "inputs:", created.textboxes.map((t) => t.getValue()), created.selects.map((s) => s.getValue()));
    btn._w.onClickCb();
    settle(() => {
      const out = {
        metrics: metrics.map((m) => ({ name: m.name, value: m.label.getValue() })),
        layers: layers.map((l) => ({ name: l.name, vis: l.vis, image: ee.Serializer.toJSON(l.img) })),
        charts: created.charts.map((c) => ({ kind: c.kind, fn: c.fn, table: c.args[0] && c.args[0].serialize ? ee.Serializer.toJSON(c.args[0]) : null, args: c.args.slice(1).map((a) => (typeof a === "object" ? null : a)) })),
        aoi: ee.Serializer.toJSON(K.state.aoi),
        hazard: K.state.lastHazard ? ee.Serializer.toJSON(K.state.lastHazard) : null,
        result: K.state.lastResult ? ee.Serializer.toJSON(K.state.lastResult) : null,
        errors: created.labels.filter((l) => l._w.value && /Gagal|Tidak ada|galat/i.test(String(l._w.value))).map((l) => l._w.value),
      };
      fs.writeFileSync(job.out, JSON.stringify(out));
      console.error("[done]", out.metrics, "layers:", out.layers.map((l) => l.name), "errors:", out.errors);
      process.exit(0);
    });
  }, (e) => { console.error("init failed", e); process.exit(1); }, null, key.project_id);
}, (e) => { console.error("auth failed", e); process.exit(1); });
