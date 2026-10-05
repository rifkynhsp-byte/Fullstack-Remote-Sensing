//| title: Many models, one map, and the validation that tells the truth
//| description: Ten plantation-landscape classes in Riau from satellite embeddings and terrain: three Earth Engine classifiers, a majority vote, and where the models agree.

/**
 * CHAPTER 59 | Many models, one map, and the validation that tells the truth
 * ---------------------------------------------------------------------------
 * Labels: the author's reference points, 10 classes, made for 2023 imagery:
 * plantation, forest, agriculture, open land, water, mangrove, paddy, oil palm,
 * sago and rubber. Classes a global map does not have.
 *   features  Google Satellite Embedding 2023 (64 bands) + elevation and slope
 *   map       an Earth Engine ensemble (RF + CART + minimum distance, majority
 *             vote) and the number of models that agree in every pixel
 * The scikit-learn comparison (gradient boosting, SVM, kNN, logistic,
 * stacking) and the spatial-block validation are in the Python notebook:
 * there, random splits flatter every model and spatial blocks tell the truth.
 */

// ---------------------------------------------------------------------------
// STEP 1. Reference points and features
// ---------------------------------------------------------------------------
var points = ee.FeatureCollection('projects/ee-rifkynauvalhsp2/assets/export_training_data_lccagri');
var PALETTE = ['8c6d31', '1a9850', 'fee08b', 'd8b365', '2c7fb8', '00a884', 'a6d96a', 'e6550d', '7b3294', 'c51b7d'];
var mapAoi = ee.Geometry.Rectangle([102.65, 0.80, 103.05, 1.05], null, false);
var emb = ee.ImageCollection('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL').filterDate('2023-01-01', '2024-01-01')
  .filterBounds(points.geometry().bounds()).mosaic();
var dem = ee.ImageCollection('COPERNICUS/DEM/GLO30').select('DEM').mosaic()
  .setDefaultProjection(ee.Projection('EPSG:4326').atScale(30));
var stack = emb.addBands(dem.rename('elevation')).addBands(ee.Terrain.slope(dem).rename('slope'));
var bands = stack.bandNames();
print('Reference points per class (1 plantation ... 10 rubber)', points.aggregate_histogram('landcover'));

// ---------------------------------------------------------------------------
// STEP 2. What a global map calls each of the author's classes
// ---------------------------------------------------------------------------
var wc = ee.ImageCollection('ESA/WorldCover/v200').first().rename('worldcover');
var withWc = wc.sampleRegions({collection: points, properties: ['landcover'], scale: 10, tileScale: 8});
print('WorldCover class counts within each author class (10 trees, 40 cropland, 90 wetland, 95 mangroves ...)',
      withWc.reduceColumns(ee.Reducer.frequencyHistogram().group(1, 'landcover'), ['worldcover', 'landcover']));

// ---------------------------------------------------------------------------
// STEP 3. A random split, three classifiers, and their honest-looking scores
// ---------------------------------------------------------------------------
var samples = stack.sampleRegions({collection: points, properties: ['landcover'], scale: 10, tileScale: 8})
  .randomColumn('r', 1);
var train = samples.filter(ee.Filter.lt('r', 0.7)), test = samples.filter(ee.Filter.gte('r', 0.7));
var models = {
  'random forest': ee.Classifier.smileRandomForest({numberOfTrees: 100, seed: 1}),
  'CART': ee.Classifier.smileCart(),
  'minimum distance (Mahalanobis)': ee.Classifier.minimumDistance('mahalanobis')   // scale-aware: elevation is in metres
};
Object.keys(models).forEach(function (k) {
  var m = models[k].train(train, 'landcover', bands);
  print(k + ': random 70/30 split accuracy (optimistic; see the notebook for spatial blocks)',
        test.classify(m).errorMatrix('landcover', 'classification').accuracy());
});

// ---------------------------------------------------------------------------
// STEP 4. The ensemble map and where the models agree
// ---------------------------------------------------------------------------
var votes = ee.ImageCollection(Object.keys(models).map(function (k) {
  return stack.clip(mapAoi).classify(models[k].train(samples, 'landcover', bands));
}));
var ensMap = votes.mode().rename('class');
var agreement = votes.map(function (i) { return i.eq(ensMap); }).sum().rename('agree');
Map.centerObject(mapAoi, 11);
Map.addLayer(ensMap, {min: 1, max: 10, palette: PALETTE}, 'Ensemble (majority of 3 models)');
Map.addLayer(agreement, {min: 1, max: 3, palette: ['d73027', 'fee08b', '1a9850']}, 'Models agreeing (1-3)', false);
Map.addLayer(points, {color: '000000'}, 'Reference points', false);
