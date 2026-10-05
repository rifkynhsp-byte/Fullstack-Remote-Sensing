//| title: Thesis starters 8, 10, 11 and 12: canopy height, landslide transfer, footprints and radar
//| description: The Earth Engine parts of starters 8, 10, 11 and 12: two canopy height maps compared, a landslide model trained west and tested east, two building-footprint datasets, and radar inside and outside the Iburi landslides.

/**
 * CHAPTER 36 | Starters 7 to 12, the Earth Engine parts
 * ---------------------------------------------------------------------------
 *   T8   stretching LiDAR plots    ETH minus GLAD canopy height, Jambi
 *   T10  landslide transfer        Iburi: train west, test east, against a random split
 *   T11  missing footprints        Microsoft vs Google Open Buildings in seven towns
 *   T12  radar before a landslide  Sentinel-1 VV inside and outside Iburi landslides, 2018
 * T7 (stems under canopy) works on a point cloud and T9 (placing LiDAR plots)
 * on k-means in feature space; both are in the Python notebook.
 */

// ---------------------------------------------------------------------------
// T8. Two global canopy height maps disagree: by how much, and where?
// ---------------------------------------------------------------------------
var jambi = ee.Geometry.Rectangle([102.45, -2.15, 102.90, -1.75], null, false);
var eth = ee.Image('users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1').rename('eth');
var glad = ee.ImageCollection('users/potapovpeter/GEDI_V27').mosaic().rename('glad');
var diff = eth.subtract(glad).rename('diff').clip(jambi);
var pairs = eth.addBands(glad).sample({region: jambi, scale: 30, numPixels: 4000, seed: 2, tileScale: 4})
  .filter(ee.Filter.gt('glad', 0));
print(ui.Chart.feature.byFeature(pairs, 'glad', 'eth').setChartType('ScatterChart')
  .setOptions({title: 'T8: ETH against GLAD canopy height, Jambi (m)', hAxis: {title: 'GLAD (m)'},
               vAxis: {title: 'ETH (m)'}, pointSize: 1, colors: ['#2a78d6']}));
Map.centerObject(jambi, 11);
Map.addLayer(diff, {min: -15, max: 15, palette: ['2166ac', 'f7f7f7', 'b2182b']}, 'T8: ETH minus GLAD canopy height (m)');

// ---------------------------------------------------------------------------
// T10. Landslide mapping: does a model trained in the west work in the east?
// ---------------------------------------------------------------------------
var win = ee.Geometry.Rectangle([141.93, 42.70, 142.05, 42.80]);
var inventory = ee.FeatureCollection('users/rifkynauvalhsp/IburiLandslideInventory/trainingset');
function s2(start, end) {
  return ee.ImageCollection('COPERNICUS/S2_HARMONIZED').filterBounds(win).filterDate(start, end)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    .map(function (s) {
      s = s.updateMask(s.select('QA60').eq(0)).divide(10000);
      return s.addBands([s.normalizedDifference(['B8', 'B4']).rename('ndvi'), s.normalizedDifference(['B3', 'B4']).rename('grvi')]);
    }).median();
}
var pre = s2('2017-09-01', '2017-10-31'), post = s2('2018-09-07', '2018-10-31');
var dem = ee.ImageCollection('JAXA/ALOS/AW3D30/V4_1').filterBounds(win).select('DSM').mosaic()
  .setDefaultProjection('EPSG:4326', null, 30);
var feat = post.select(['ndvi', 'grvi']).subtract(pre.select(['ndvi', 'grvi'])).rename(['dNDVI', 'dGRVI'])
  .addBands(ee.Terrain.slope(dem).rename('slope')).addBands(ee.Image.pixelLonLat().select('longitude'));
var truth = ee.Image(0).paint(inventory, 1).rename('truth').clip(win);
var pts = feat.addBands(truth).stratifiedSample({numPoints: 1000, classBand: 'truth', region: win, scale: 10, seed: 3, tileScale: 4})
  .randomColumn('r', 0);
var mid = ee.Number(pts.reduceColumns(ee.Reducer.median(), ['longitude']).get('median'));
function f1(train, test) {
  var m = ee.Classifier.smileRandomForest({numberOfTrees: 200, seed: 0}).train(train, 'truth', ['dNDVI', 'dGRVI', 'slope']);
  var cm = test.classify(m).errorMatrix('truth', 'classification');
  return ee.Number(ee.Array(cm.fscore()).get([1]));            // F1 of the landslide class
}
print('T10: landslide F1', ee.Dictionary({
  random_half_vs_other_half: f1(pts.filter(ee.Filter.lt('r', 0.5)), pts.filter(ee.Filter.gte('r', 0.5))),
  west_half_vs_east_half: f1(pts.filter(ee.Filter.lt('longitude', mid)), pts.filter(ee.Filter.gte('longitude', mid)))}));

// ---------------------------------------------------------------------------
// T11. Missing footprints: Microsoft against Google Open Buildings
// ---------------------------------------------------------------------------
var TOWNS = {'Bandung': [107.61, -6.91], 'Garut': [107.90, -7.21], 'Surabaya': [112.75, -7.26],
             'Sleman': [110.36, -7.72], 'Selong, Lombok': [116.53, -8.65], 'Kuala Simpang, Aceh': [98.06, 4.28],
             'Jayapura': [140.70, -2.55]};
var msParts = ee.FeatureCollection([1, 2, 3, 4, 5, 6, 7].map(function (i) {
  return ee.FeatureCollection('projects/sat-io/open-datasets/MSBuildings/Indonesia/indonesia_' + i);
})).flatten();
Object.keys(TOWNS).forEach(function (town) {
  var c = TOWNS[town];
  var box = ee.Geometry.Rectangle([c[0] - 0.0135, c[1] - 0.0135, c[0] + 0.0135, c[1] + 0.0135]);   // about 3 x 3 km
  var ms = msParts.filterBounds(box).size();
  var gob = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons').filterBounds(box)
    .filter(ee.Filter.gte('confidence', 0.75)).size();
  print('T11: ' + town, ee.Dictionary({microsoft: ms, google_v3_conf75: gob, ratio_google_to_ms: gob.divide(ms)}));
});

// ---------------------------------------------------------------------------
// T12. Radar before and after the 6 September 2018 landslides
// ---------------------------------------------------------------------------
var s1 = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(win).filterDate('2018-01-01', '2018-12-31')
  .filter(ee.Filter.eq('instrumentMode', 'IW')).select('VV');
var slid = truth.eq(1);
var series = s1.map(function (img) {
  var g = img.updateMask(slid).reduceRegion({reducer: ee.Reducer.mean(), geometry: win, scale: 20, maxPixels: 1e9, tileScale: 4});
  var o = img.updateMask(slid.not()).reduceRegion({reducer: ee.Reducer.mean(), geometry: win, scale: 20, maxPixels: 1e9, tileScale: 4});
  return ee.Feature(null, {'system:time_start': img.date().millis(), inside_landslides: g.get('VV'), outside: o.get('VV')});
});
print(ui.Chart.feature.byFeature(series, 'system:time_start', ['inside_landslides', 'outside'])
  .setOptions({title: 'T12: Sentinel-1 VV inside and outside the Iburi landslides, 2018 (dB)',
               colors: ['#b8433a', '#7b8794'], pointSize: 3, lineWidth: 0}));
Map.addLayer(inventory, {color: 'b8433a'}, 'T10/T12: Iburi landslide inventory', false);
