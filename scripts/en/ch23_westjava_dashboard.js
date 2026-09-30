//| title: A district dashboard for West Java
//| description: Four indicators per district, a map and a chart in one Code Editor app, plus the export that feeds a Python dashboard.

/**
 * CHAPTER 23 | From analysis to something a district office can use
 * ---------------------------------------------------------------------------
 * The GEE101 course ends with exports and small apps (GEE_UI repository).
 * This listing puts the two together: compute four indicators for every
 * district in West Java, show them in a click-to-explore app, and export the
 * same table so a Python dashboard (the other tab) can be built from it.
 *
 *   NDVI     MODIS 16-day, 2024 mean
 *   LST      MODIS 8-day daytime land surface temperature, 2024 mean (°C)
 *   built    share of the district that Dynamic World calls built, 2024
 *   people   WorldPop 2020 population
 */

var districts = ee.FeatureCollection('FAO/GAUL/2025/level2')
  .filter(ee.Filter.eq('GAUL1_NAME', 'Jawa Barat'));
var YEAR = '2024';

var ndvi = ee.ImageCollection('MODIS/061/MOD13A2').filterDate(YEAR + '-01-01', '2025-01-01')
  .select('NDVI').mean().multiply(0.0001).rename('ndvi');
var lst = ee.ImageCollection('MODIS/061/MOD11A2').filterDate(YEAR + '-01-01', '2025-01-01')
  .select('LST_Day_1km').mean().multiply(0.02).subtract(273.15).rename('lst_c');
var built = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(districts)
  .filterDate(YEAR + '-01-01', '2025-01-01').select('built').mean().gt(0.5).rename('built');
var people = ee.ImageCollection('WorldPop/GP/100m/pop').filter(ee.Filter.eq('country', 'IDN'))
  .filter(ee.Filter.eq('year', 2020)).mosaic().rename('people');

// Means for the indicators, a sum for people: one reduceRegions each.
var means = ndvi.addBands(lst).addBands(built).reduceRegions({
  collection: districts, reducer: ee.Reducer.mean(), scale: 1000, tileScale: 4});
var table = people.reduceRegions({collection: means, reducer: ee.Reducer.sum().setOutputs(['people']),
                                  scale: 100, tileScale: 8})
  .map(function (f) {
    return f.set({district: f.get('GAUL2_NAME'),
                  built_pct: ee.Number(f.get('built')).multiply(100)});
  }).select(['district', 'ndvi', 'lst_c', 'built_pct', 'people']);

// ---------------------------------------------------------------------------
// The app: pick an indicator, click a district
// ---------------------------------------------------------------------------
var panel = ui.Panel({style: {width: '340px'}});
var info = ui.Label('Click a district.');
var select = ui.Select({
  items: ['ndvi', 'lst_c', 'built_pct'], value: 'lst_c',
  onChange: function (v) { draw(v); }
});
panel.add(ui.Label('West Java at a glance, ' + YEAR, {fontWeight: 'bold', fontSize: '16px'}))
     .add(select).add(info);
ui.root.insert(0, panel);

var ramps = {ndvi: ['#f7fcb9', '#31a354'], lst_c: ['#ffffcc', '#bd0026'],
             built_pct: ['#f0f0f0', '#636363']};
var draw = function (field) {
  var img = table.reduceToImage([field], ee.Reducer.first());
  var stats = table.aggregate_stats(field);
  stats.evaluate(function (s) {
    Map.layers().reset();
    Map.addLayer(img, {min: s.min, max: s.max, palette: ramps[field]}, field);
    Map.addLayer(ee.Image().byte().paint(districts, 1, 1), {palette: ['black']}, 'districts');
  });
};
Map.centerObject(districts, 8);
draw('lst_c');

Map.onClick(function (coords) {
  var hit = table.filterBounds(ee.Geometry.Point([coords.lon, coords.lat])).first();
  hit.evaluate(function (f) {
    if (!f) { info.setValue('No district here.'); return; }
    var p = f.properties;
    info.setValue(p.district + ': NDVI ' + p.ndvi.toFixed(2) + ', LST ' +
      p.lst_c.toFixed(1) + ' °C, built ' + p.built_pct.toFixed(1) + ' %, people ' +
      Math.round(p.people).toLocaleString());
  });
});

// The same table leaves Earth Engine as CSV for the Python dashboard.
Export.table.toDrive({collection: table, description: 'westjava_districts_' + YEAR,
                      fileFormat: 'CSV'});

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Publish the app (Apps > New App) with access limited to your account.
// 2. Add a fourth option, people per km². What does it change on the map?
