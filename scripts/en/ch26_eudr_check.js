//| title: An EUDR screening for a grid of supplier plots
//| description: Forest at the 31 December 2020 cut-off, loss since 2021, and a status per plot, in a Jambi frontier landscape.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 26 | Forestry, plantations and deforestation-free supply chains
 * ---------------------------------------------------------------------------
 * The EU Deforestation Regulation asks one question of every plot that
 * supplies rubber, palm oil, cocoa, coffee, soy, cattle or wood to the EU:
 * was there deforestation on it after 31 December 2020? This is the
 * screening logic of the author's traceability engine, on public data:
 *   forest at the cut-off   JRC Global Forest Cover 2020 (the EU's own map)
 *   loss after the cut-off  Hansen Global Forest Change, loss years 2021+
 * Real supplier plots are client data; a 1 km grid stands in for them here.
 */

var area = ee.Geometry.Rectangle([102.9, -1.9, 103.2, -1.6]);   // Jambi

var forest2020 = ee.Image('JRC/GFC2020/V4').select('Map').eq(1).unmask(0).rename('forest2020');
var hansen = ee.Image('UMD/hansen/global_forest_change_2024_v1_12');
// Deforestation under the EUDR is loss of forest that existed at the cut-off:
// count loss only on pixels the 2020 map calls forest.
var lossAfterCutoff = hansen.select('lossyear').gte(21).unmask(0).and(forest2020)
  .rename('loss_after_2020');

// Stand-in supplier plots: a 1 km grid over the area.
var plots = area.coveringGrid(ee.Projection('EPSG:32748').atScale(1000))
  .map(function (cell) { return cell.set('plot_id', cell.id()); });

// Hectares of each layer inside every plot, in one reduceRegions call.
var ha = forest2020.addBands(lossAfterCutoff).multiply(ee.Image.pixelArea()).divide(1e4);
var screened = ha.reduceRegions({collection: plots, reducer: ee.Reducer.sum(), scale: 30,
                                 tileScale: 4})
  .map(function (p) {
    var forest = ee.Number(p.get('forest2020'));
    var loss = ee.Number(p.get('loss_after_2020'));
    var status = ee.Algorithms.If(loss.gt(0.5), 'deforestation after cut-off',
                 ee.Algorithms.If(forest.gt(10), 'forest standing: check degradation',
                 'no forest at cut-off'));
    return p.set({forest2020_ha: forest, loss_after_2020_ha: loss, status: status});
  });
print('Plots by status', screened.aggregate_histogram('status'));

// Loss per year in ONE request: pixel area summed, grouped by loss year.
// Twenty-four separate reduceRegion calls hit "Too many concurrent aggregations".
var grouped = ee.Image.pixelArea().divide(1e4).addBands(hansen.select('lossyear'))
  .reduceRegion({reducer: ee.Reducer.sum().group({groupField: 1, groupName: 'code'}),
                 geometry: area, scale: 30, maxPixels: 1e10});
var lossByYear = ee.FeatureCollection(ee.List(grouped.get('groups')).map(function (g) {
  g = ee.Dictionary(g);
  return ee.Feature(null, {year: ee.Number(g.get('code')).add(2000), loss_ha: g.get('sum')});
})).filter(ee.Filter.gt('year', 2000));
print(ui.Chart.feature.byFeature(lossByYear, 'year', ['loss_ha']).setChartType('ColumnChart')
  .setOptions({title: 'Tree cover loss per year (Hansen)', hAxis: {format: '####'}}));

var palette = {'deforestation after cut-off': '#d7191c',
               'forest standing: check degradation': '#1a9641',
               'no forest at cut-off': '#d9d9d9'};
Map.centerObject(area, 11);
Map.addLayer(forest2020.selfMask(), {palette: ['#1a9641']}, 'Forest 2020 (JRC)', false);
Map.addLayer(lossAfterCutoff.selfMask(), {palette: ['#d7191c']}, 'Loss 2021-2024 (Hansen)');
Map.addLayer(screened.filter(ee.Filter.eq('status', 'deforestation after cut-off')),
  {color: '#d7191c'}, 'Plots failing the screen');

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Replace the 0.5 ha tolerance with 0. How many plots change status, and
//    is that loss real or edge noise?
// 2. Swap Hansen for JRC TMF deforestation (projects/JRC/TMF). Which plots
//    change, and which dataset would you defend to an auditor?
