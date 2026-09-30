//| title: Mangrove biomass from 45 field plots
//| description: Three regression models for above ground biomass, each tested by leaving one plot out.

/**
 * CHAPTER 20 | From a class to a quantity
 * ---------------------------------------------------------------------------
 * 45 field plots in West Papua, measured by CIFOR, each with above ground
 * biomass (AGB, Mg/ha): fish ponds, forest regrowing for 5 to 25 years, and
 * undisturbed mangrove. Three models try to predict AGB from space:
 *   1. a straight line on canopy height,
 *   2. a random forest on optical, radar, height and terrain,
 *   3. a random forest on AlphaEarth embeddings.
 * With 45 points there is no room for a 70/30 split, so every model is
 * scored by leave-one-out: train on 44, predict the one left out, repeat.
 *
 * Caveat, stated up front: the plot table does not carry survey dates. The
 * predictors are from 2020. Any change between survey and 2020 is error the
 * models cannot see.
 */

var plots = ee.FeatureCollection('projects/ee-rifkynauvalhsp2/assets/Mangrove_CIFOR_WestPapua_pivot')
  .map(function (f) { return f.set('AGB', f.get('AGB (Mg/ha)')); });
var region = plots.geometry().bounds().buffer(5000);

// ---------------------------------------------------------------------------
// STEP 1. Predictors, all 2020
// ---------------------------------------------------------------------------
var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(region).filterDate('2020-01-01', '2021-01-01')
  .map(function (i) {
    var scl = i.select('SCL');
    return i.updateMask(scl.neq(3).and(scl.neq(8)).and(scl.neq(9)).and(scl.neq(10)))
            .divide(10000);
  }).median();
var s1 = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(region)
  .filterDate('2020-01-01', '2021-01-01')
  .filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
  .select(['VV', 'VH']).median();
var aw3d = ee.ImageCollection('JAXA/ALOS/AW3D30/V4_1');
var stack = s2.normalizedDifference(['B8', 'B4']).rename('NDVI')
  .addBands(s2.normalizedDifference(['B8', 'B11']).rename('NDMI'))
  .addBands(s1)
  .addBands(ee.Image('users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1').rename('canopy_height'))
  .addBands(aw3d.select('DSM').filterBounds(region).mosaic().rename('elevation'))
  .float();
var embeddings = ee.ImageCollection('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL')
  .filterBounds(region).filterDate('2020-01-01', '2021-01-01').mosaic();

// Mean of a 20 m buffer around each plot centre, to soften geolocation error.
var table = stack.addBands(embeddings).reduceRegions({
  collection: plots.map(function (f) { return f.buffer(20); }),
  reducer: ee.Reducer.mean(), scale: 10, tileScale: 4
}).filter(ee.Filter.notNull(['canopy_height', 'NDVI', 'VH', 'A00']));
var indexed = ee.FeatureCollection(table.toList(100).map(function (f) {
  return ee.Feature(f).set('idx', table.toList(100).indexOf(f));
}));
print('Plots with every predictor:', indexed.size());

// ---------------------------------------------------------------------------
// STEP 2. Leave one out, three models
// ---------------------------------------------------------------------------
var STACK_BANDS = ['NDVI', 'NDMI', 'VV', 'VH', 'canopy_height', 'elevation'];
var EMB_BANDS = embeddings.bandNames();

var loo = indexed.map(function (held) {
  var others = indexed.filter(ee.Filter.neq('idx', held.get('idx')));
  // 1. Straight line on canopy height
  var fit = others.reduceColumns(ee.Reducer.linearFit(), ['canopy_height', 'AGB']);
  var lineal = ee.Number(fit.get('offset')).add(
    ee.Number(fit.get('scale')).multiply(held.get('canopy_height')));
  // 2 and 3. Random forests in regression mode
  var rf = function (bands) {
    return ee.Classifier.smileRandomForest({numberOfTrees: 200, seed: 7})
      .setOutputMode('REGRESSION').train(others, 'AGB', bands);
  };
  var one = ee.FeatureCollection([held]);
  return held.set({
    pred_linear: lineal,
    pred_rf_stack: one.classify(rf(STACK_BANDS), 'p').first().get('p'),
    pred_rf_embed: one.classify(rf(EMB_BANDS), 'p').first().get('p')
  });
});

var scoreOf = function (column) {
  var err = loo.map(function (f) {
    return f.set('e', ee.Number(f.get(column)).subtract(f.get('AGB')));
  });
  var rmse = ee.Number(err.aggregate_array('e').map(function (e) {
    return ee.Number(e).pow(2); }).reduce(ee.Reducer.mean())).sqrt();
  var r = ee.Number(loo.reduceColumns(ee.Reducer.pearsonsCorrelation(),
                                      [column, 'AGB']).get('correlation'));
  return ee.Feature(null, {model: column, rmse: rmse, r2: r.pow(2),
                           bias: err.aggregate_mean('e')});
};
print('Leave-one-out scores', ee.FeatureCollection(
  [scoreOf('pred_linear'), scoreOf('pred_rf_stack'), scoreOf('pred_rf_embed')]));

// ---------------------------------------------------------------------------
// STEP 3. A map from the stack model trained on all plots, mangrove only
// ---------------------------------------------------------------------------
var gmw = ee.FeatureCollection('projects/sat-io/open-datasets/GMW/extent/gmw_v3_2020_vec')
  .filterBounds(region);
var agb = stack.classify(ee.Classifier.smileRandomForest({numberOfTrees: 200, seed: 7})
    .setOutputMode('REGRESSION').train(indexed, 'AGB', STACK_BANDS))
  .updateMask(ee.Image(0).paint(gmw, 1)).rename('AGB');
Map.centerObject(plots, 9);
Map.addLayer(agb, {min: 0, max: 200, palette: ['#ffffcc', '#78c679', '#006837']},
  'AGB, Mg/ha (mangrove only)');
Map.addLayer(plots, {color: 'red'}, 'CIFOR plots');

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Which plots does every model get wrong? Look them up in the table:
//    what category are they, and what would a satellite see there?
// 2. Replace the 20 m buffer with a 50 m one. Does leave-one-out RMSE move?
