//| title: Land cover in 2030 and 2035, predicted with machine learning
//| description: A random forest learns how Bandung Raya's land cover changed over five years, is tested by predicting 2025 from 2020, and is then run forward to 2030 and 2035.

/**
 * CHAPTER 76 | Land cover in 2030 and 2035, predicted with machine learning
 * ---------------------------------------------------------------------------
 * Classic land-change models (Markov chains, CA-Markov) count how often each
 * class turned into each other class and spread that rate over a suitability
 * map. Here a random forest learns where and into what, pixel by pixel; the
 * past rate of change sets how much.
 *   labels    Dynamic World V1, annual mode, 6 classes: water, trees, grass and
 *             shrub, crops, built, bare
 *   features  at year t: the pixel's class, the share of built, crops and trees
 *             within 500 m and 1.5 km, distance to built land, slope, elevation,
 *             distance to the city centre, population (GHSL 2020)
 *   train     features in 2017 -> class in 2022
 *   how much  the share of the area that changed in the last observed five years
 *   test      2020 -> predicted 2025, against the observed 2025 map and against
 *             "nothing changes"
 *   forecast  2025 -> 2030, then the predicted 2030 -> 2035
 * Read the forecast as "if the next five years behave like the last ones".
 */

// ---------------------------------------------------------------------------
// STEP 1. Area, classes and label maps
// ---------------------------------------------------------------------------
var AOI = ee.Geometry.Rectangle([107.40, -7.10, 107.80, -6.80], null, false);   // Bandung Raya
var CENTRE = ee.Geometry.Point([107.6098, -6.9218]);                          // Alun-alun Bandung
var NAMES = ['water', 'trees', 'grass and shrub', 'crops', 'built', 'bare'];
var PALETTE = ['419bdf', '397d49', 'a8c88e', 'e4c372', 'c4281b', 'a59b8f'];
var SCALE = 60;                         // a regional forecast: 60 m cells keep the 2035 step within limits
var PROJ = ee.Projection('EPSG:32748').atScale(SCALE);
// Dynamic World 0 water, 1 trees, 2 grass, 3 flooded vegetation, 4 crops, 5 shrub, 6 built, 7 bare
function landcover(year) {
  var d = ee.Date.fromYMD(year, 1, 1);
  return ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(AOI).filterDate(d, d.advance(1, 'year'))
    .select('label').mode().remap([0, 1, 2, 3, 4, 5, 6, 7], [0, 1, 2, 2, 3, 2, 4, 5]).rename('lc').clip(AOI);
}
var lc17 = landcover(2017), lc20 = landcover(2020), lc22 = landcover(2022), lc25 = landcover(2025);

// ---------------------------------------------------------------------------
// STEP 2. Features, recomputable from any class map
// ---------------------------------------------------------------------------
var dem = ee.ImageCollection('COPERNICUS/DEM/GLO30_2024_1').select('DEM').mosaic()
  .setDefaultProjection(ee.Projection('EPSG:4326').atScale(30));
var STATIC = ee.Image.cat([dem.rename('elev_m'), ee.Terrain.slope(dem).rename('slope_deg'),
  ee.FeatureCollection([ee.Feature(CENTRE)]).distance(60000).divide(1000).rename('km_to_centre'),
  ee.Image('JRC/GHSL/P2023A/GHS_POP/2020').select('population_count').max(0).add(1).log().rename('people_log')]);
function features(lc) {
  lc = ee.Image(lc).reproject(PROJ);
  var onehot = ee.Image.cat(NAMES.map(function (n, k) { return lc.eq(k).rename('is_' + k); }));
  function share(k, m) { return lc.eq(k).focalMean(m, 'circle', 'meters').rename('share' + k + '_' + m); }
  var distBuilt = lc.eq(4).selfMask().fastDistanceTransform(256, 'pixels', 'squared_euclidean').sqrt()
    .multiply(SCALE / 1000).unmask(256 * SCALE / 1000).rename('km_to_built');
  return ee.Image.cat([onehot, share(4, 500), share(4, 1500), share(3, 500), share(1, 500), distBuilt, STATIC])
    .toFloat().clip(AOI);
}
var BANDS = features(lc17).bandNames();

// ---------------------------------------------------------------------------
// STEP 3. Train: 2017 features, the class five years later
// ---------------------------------------------------------------------------
// Change is rare, so half the points come from pixels that changed 2017-2022;
// otherwise the forest learns that nothing ever changes.
var changed = lc17.neq(lc22).rename('changed').toInt();
var train = features(lc17).addBands(lc22.rename('next')).addBands(changed)
  .stratifiedSample({numPoints: 0, classBand: 'changed', region: AOI, scale: SCALE, seed: 7,
                     classValues: [0, 1], classPoints: [4000, 4000], tileScale: 8});
var model = ee.Classifier.smileRandomForest({numberOfTrees: 200, minLeafPopulation: 3, seed: 1})
  .setOutputMode('MULTIPROBABILITY').train(train, 'next', BANDS);

// ---------------------------------------------------------------------------
// STEP 4. Predict: where and into what from the model, how much from the past
// ---------------------------------------------------------------------------
function changeRate(a, b) {
  return ee.Number(a.neq(b).reduceRegion({reducer: ee.Reducer.mean(), geometry: AOI, scale: 120, maxPixels: 1e10, tileScale: 8}).values().get(0));
}
function predict(lcNow, rate) {
  lcNow = ee.Image(lcNow);
  var probs = features(lcNow).classify(model).arrayFlatten([NAMES.map(function (n, k) { return 'p' + k; })]);
  var onehot = ee.Image.cat(NAMES.map(function (n, k) { return lcNow.eq(k); }));
  var pChange = ee.Image(1).subtract(probs.multiply(onehot).reduce('sum'));
  var other = probs.multiply(ee.Image(1).subtract(onehot)).toArray().arrayArgmax().arrayGet([0]);   // most likely new class
  var cut = pChange.reduceRegion({reducer: ee.Reducer.percentile([ee.Number(1).subtract(rate).multiply(100)]),
                                  geometry: AOI, scale: 120, maxPixels: 1e10, tileScale: 8}).values().get(0);
  return lcNow.where(pChange.gt(ee.Number(cut)), other).rename('lc').toInt();
}

// ---------------------------------------------------------------------------
// STEP 5. The test before the forecast: 2025 from 2020
// ---------------------------------------------------------------------------
var pred25 = predict(lc20, changeRate(lc17, lc22));          // only what was known in 2022
var obsChange = lc20.neq(lc25);
function score(name, p) {
  var predChange = lc20.neq(p);
  var s = ee.Image.cat([p.eq(lc25).rename('agree'), obsChange.and(predChange).and(p.eq(lc25)).rename('hits'),
                        obsChange.and(predChange).and(p.neq(lc25)).rename('wrong'), obsChange.and(predChange.not()).rename('misses'),
                        obsChange.not().and(predChange).rename('false_alarms')])
    .reduceRegion({reducer: ee.Reducer.mean(), geometry: AOI, scale: 120, maxPixels: 1e10, tileScale: 8});
  var denom = ee.Number(s.get('hits')).add(s.get('wrong')).add(s.get('misses')).add(s.get('false_alarms'));
  print(name, s.set('figure_of_merit', ee.Number(s.get('hits')).divide(denom.max(1e-9))));
}
score('Random forest, 2020 -> 2025', pred25);
score('No change (the 2020 map as the 2025 forecast)', lc20);

// ---------------------------------------------------------------------------
// STEP 6. The forecast: 2030, and 2035 from the predicted 2030
// ---------------------------------------------------------------------------
var rate = changeRate(lc20, lc25);                            // the latest observed five years
var pred30 = predict(lc25, rate);
var pred35 = predict(pred30, rate);
var area = ee.Image.pixelArea().divide(1e4);
[[2017, lc17], [2020, lc20], [2025, lc25], [2030, pred30], [2035, pred35]].forEach(function (p) {
  print('Hectares per class ' + p[0] + (p[0] > 2025 ? ' (predicted)' : '') + ': 0 water, 1 trees, 2 grass/shrub, 3 crops, 4 built, 5 bare',
        area.addBands(p[1].rename('lc')).reduceRegion({reducer: ee.Reducer.sum().group(1, 'lc'), geometry: AOI, scale: 120,
                                                       maxPixels: 1e10, tileScale: 8}).get('groups'));
});

// ---------------------------------------------------------------------------
// STEP 7. Maps
// ---------------------------------------------------------------------------
var vis = {min: 0, max: 5, palette: PALETTE};
Map.centerObject(AOI, 11);
Map.addLayer(lc25, vis, 'Land cover 2025 (observed)');
Map.addLayer(pred30, vis, 'Land cover 2030 (predicted)', false);
Map.addLayer(pred35, vis, 'Land cover 2035 (predicted)', false);
Map.addLayer(ee.Image(0).where(lc25.eq(4), 1).where(pred30.eq(4).and(lc25.neq(4)), 2)
               .where(pred35.eq(4).and(pred30.neq(4)), 3).selfMask(),
             {min: 1, max: 3, palette: ['9e9e9e', 'fd8d3c', '800026']}, 'Built 2025, new by 2030, new by 2035');
