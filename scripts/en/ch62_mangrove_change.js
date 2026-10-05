//| title: Is the mangrove growing or degrading?
//| description: One model on satellite embeddings for every year at Segara Anakan, gain and loss since 2017, the canopy trend inside stable mangrove, and what replaced the losses.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 62 | Is the mangrove growing or degrading?
 * ---------------------------------------------------------------------------
 * The same approach as the author's interactive mangrove explorer, at a
 * public site: one model, every year, compared with a fixed baseline.
 *   1. labels     GMW v3 2020: mangrove inside the polygons; non-mangrove more
 *                 than 100 m outside them (a buffer keeps edge errors out)
 *   2. model      random forest on the 2020 Satellite Embedding (64 bands)
 *   3. years      the same model on every embedding year 2017-2024
 *   4. change     gain = not mangrove in 2017, mangrove in 2024; loss = the reverse
 *   5. condition  inside mangrove in BOTH years: Sen's slope of annual median
 *                 NDMI (Sentinel-2, 2019-2024). Area changes say nothing about this.
 *   6. after      Dynamic World 2024 label of the lost mangrove
 */

// ---------------------------------------------------------------------------
// STEP 1. Segara Anakan and labels from Global Mangrove Watch
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Rectangle([108.76, -7.76, 109.06, -7.62], null, false);
var SLOPE = 0.005;     // NDMI per year; beyond this the trend counts as real change
var gmw = ee.FeatureCollection('projects/sat-io/open-datasets/GMW/extent/gmw_v3_2020_vec').filterBounds(aoi);
var gmwImg = ee.Image(0).paint(gmw, 1).clip(aoi);
var outside = gmwImg.not().and(gmwImg.focalMax(100, 'circle', 'meters').not());
var lab = ee.Image(-1).where(gmwImg.eq(1), 1).where(outside, 0);
var labels = lab.rename('mangrove').updateMask(lab.gte(0)).clip(aoi);

// ---------------------------------------------------------------------------
// STEP 2. One model, trained on 2020
// ---------------------------------------------------------------------------
function emb(year) {
  var d = ee.Date.fromYMD(year, 1, 1);
  return ee.ImageCollection('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL').filterDate(d, d.advance(1, 'year'))
    .filterBounds(aoi).mosaic().clip(aoi);
}
var bands = emb(2020).bandNames();
var pts = labels.stratifiedSample({numPoints: 600, classBand: 'mangrove', region: aoi, scale: 10, seed: 3,
                                   geometries: true, tileScale: 8});
var samples = emb(2020).sampleRegions({collection: pts, properties: ['mangrove'], scale: 10, tileScale: 8}).randomColumn('r', 2);
var train = samples.filter(ee.Filter.lt('r', 0.7)), test = samples.filter(ee.Filter.gte('r', 0.7));
var model = ee.Classifier.smileRandomForest({numberOfTrees: 150, seed: 1}).train(train, 'mangrove', bands);
print('Hold-out accuracy, 2020', test.classify(model).errorMatrix('mangrove', 'classification').accuracy());
function mangrove(year) { return emb(year).classify(model).eq(1).rename('m'); }

// ---------------------------------------------------------------------------
// STEP 3. Mangrove area every year
// ---------------------------------------------------------------------------
var area = ee.Image.pixelArea().divide(1e4);
var perYear = ee.FeatureCollection(ee.List.sequence(2017, 2024).map(function (y) {
  return ee.Feature(null, {year: y, mangrove_ha: area.updateMask(mangrove(y)).reduceRegion({reducer: ee.Reducer.sum(),
    geometry: aoi, scale: 10, maxPixels: 1e10, tileScale: 8}).values().get(0)});
}));
print(ui.Chart.feature.byFeature(perYear, 'year', 'mangrove_ha').setChartType('ColumnChart')
  .setOptions({title: 'Mangrove area at Segara Anakan, same model every year (ha)', colors: ['#1a9641']}));

// ---------------------------------------------------------------------------
// STEP 4. Gain, loss, and the condition of what stayed
// ---------------------------------------------------------------------------
function s2Year(y) {
  var d = ee.Date.fromYMD(y, 1, 1);
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(aoi).filterDate(d, d.advance(1, 'year'))
    .linkCollection(ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'), ['cs'])
    .map(function (i) { return i.updateMask(i.select('cs').gte(0.6)); }).median().divide(10000);
}
var trendCol = ee.ImageCollection(ee.List.sequence(2019, 2024).map(function (y) {
  return ee.Image.constant(y).float().rename('t').addBands(s2Year(y).normalizedDifference(['B8', 'B11']).rename('ndmi'));
}));
var slope = trendCol.select(['t', 'ndmi']).reduce(ee.Reducer.sensSlope()).select('slope');
var m17 = mangrove(2017), m24 = mangrove(2024), stable = m17.and(m24);
// 1 gain, 2 loss, 3 stable but degrading, 4 stable no clear trend, 5 stable improving
var change = ee.Image(0).where(m17.not().and(m24), 1).where(m17.and(m24.not()), 2)
  .where(stable.and(slope.lt(-SLOPE)), 3).where(stable.and(slope.abs().lte(SLOPE)), 4)
  .where(stable.and(slope.gt(SLOPE)), 5).selfMask().rename('change').clip(aoi);
print('Hectares: 1 gain, 2 loss, 3 stable degrading, 4 stable no trend, 5 stable improving',
      area.addBands(change).reduceRegion({reducer: ee.Reducer.sum().group(1, 'change'), geometry: aoi, scale: 10,
                                          maxPixels: 1e10, tileScale: 8}).get('groups'));

// ---------------------------------------------------------------------------
// STEP 5. What replaced the lost mangrove (Dynamic World 2024)
// ---------------------------------------------------------------------------
var dw = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(aoi).filterDate('2024-01-01', '2025-01-01').select('label').mode();
print('Lost mangrove by its 2024 label (0 water, 1 trees, 2 grass, 3 flooded vegetation, 4 crops, 5 shrub, 6 built, 7 bare)',
      area.updateMask(change.eq(2)).addBands(dw.rename('dw')).reduceRegion({reducer: ee.Reducer.sum().group(1, 'dw'),
        geometry: aoi, scale: 10, maxPixels: 1e10, tileScale: 8}).get('groups'));

// ---------------------------------------------------------------------------
// STEP 6. The map
// ---------------------------------------------------------------------------
Map.centerObject(aoi, 12);
Map.addLayer(change, {min: 1, max: 5, palette: ['00ff7f', 'd7191c', 'fdae61', '1a9641', '2b83ba']},
             'Gain, loss, degrading, stable, improving');
Map.addLayer(ee.Image().byte().paint(gmw, 1, 1), {palette: ['000000']}, 'GMW 2020 outline', false);
