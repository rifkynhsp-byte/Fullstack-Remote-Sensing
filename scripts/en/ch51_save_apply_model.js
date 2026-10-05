//| title: A model you can hand to someone else
//| description: Train a Random Forest on satellite embeddings, save it two ways, prove the saved copy gives the same answers, and apply it ever further from home.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 51 | A model you can hand to someone else
 * ---------------------------------------------------------------------------
 *  1. train   Random Forest on 2021 satellite embeddings, WorldCover 2021 labels,
 *             near Bandung (5 classes: trees, grass, cropland, built, water)
 *  2. save    route A: Export.classifier.toAsset -> ee.Classifier.load
 *             route B: the trees as text (classifier.explain().trees) in a table
 *                      -> ee.Classifier.decisionTreeEnsemble
 *  3. check   the reloaded model must reproduce the original's answers
 *  4. apply   to four other places, each further from home
 *
 * The saved assets live in the book's Earth Engine project and are public, so
 * this script runs for anyone as is. STEP 5 shows how to save your own copies.
 */

// ---------------------------------------------------------------------------
// STEP 1. The saved training table, labels and embeddings
// ---------------------------------------------------------------------------
var FOLDER = 'projects/shaped-producer-482312-m0/assets/book';
var TRAIN = FOLDER + '/train_bandung_2021';     // the training table, saved once
var CLF_ASSET = FOLDER + '/lulc_rf_fromtable';  // route A
var TREES = FOLDER + '/lulc_rf_trees';          // route B
var EMB = ee.ImageCollection('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL');
var label = ee.Image('ESA/WorldCover/v200/2021').select('Map')
  .remap([10, 30, 40, 50, 80], [0, 1, 2, 3, 4], -1).rename('label');   // trees, grass, cropland, built, water
var HOME = ee.Geometry.Rectangle([107.45, -7.05, 107.80, -6.80], null, false);
var PLACES = {
  'Bandung (home, new points)': [107.45, -7.05, 107.80, -6.80],
  'Garut, West Java (60 km)': [107.75, -7.35, 108.05, -7.10],
  'Lampung, Sumatra (400 km)': [105.10, -5.50, 105.45, -5.20],
  'Pontianak, Kalimantan (800 km)': [109.25, -0.15, 109.60, 0.15],
  'Makassar, Sulawesi (1,300 km)': [119.40, -5.25, 119.75, -4.95]
};
function embeddings(region) { return EMB.filterDate('2021-01-01', '2022-01-01').filterBounds(region).mosaic(); }
function samples(region, n, seed) {
  return embeddings(region).addBands(label.updateMask(label.gte(0)))
    .stratifiedSample({numPoints: n, classBand: 'label', region: region, scale: 10, seed: seed, tileScale: 4});
}

// ---------------------------------------------------------------------------
// STEP 2. Train from the saved table, so every run uses the same samples
// ---------------------------------------------------------------------------
var bands = EMB.first().bandNames();
var rf = ee.Classifier.smileRandomForest({numberOfTrees: 100, seed: 1}).train(ee.FeatureCollection(TRAIN), 'label', bands);

// ---------------------------------------------------------------------------
// STEP 3. Reload both saved copies and check they agree with the original
// ---------------------------------------------------------------------------
var routeA = ee.Classifier.load(CLF_ASSET);
var routeB = ee.Classifier.decisionTreeEnsemble(ee.FeatureCollection(TREES).aggregate_array('tree'));
var homeTest = samples(HOME, 100, 99);
function agreement(c) { return homeTest.classify(c).errorMatrix('label', 'classification').accuracy(); }
print('Agreement with WorldCover on new Bandung points', ee.Dictionary({
  in_memory: agreement(rf), routeA_toAsset_then_load: agreement(routeA), routeB_trees_as_text: agreement(routeB)}));

// ---------------------------------------------------------------------------
// STEP 4. Apply the saved model further and further from home
// ---------------------------------------------------------------------------
Object.keys(PLACES).forEach(function (name) {
  var box = ee.Geometry.Rectangle(PLACES[name], null, false);
  var em = samples(box, 100, 99).classify(routeB).errorMatrix('label', 'classification');
  print(name, ee.Dictionary({agreement_with_WorldCover: em.accuracy(), kappa: em.kappa()}));
});
var makassar = ee.Geometry.Rectangle(PLACES['Makassar, Sulawesi (1,300 km)'], null, false);
Map.centerObject(makassar, 11);
Map.addLayer(embeddings(makassar).classify(routeB).clip(makassar),
             {min: 0, max: 4, palette: ['006400', 'ffff4c', 'f096ff', 'fa0000', '0064c8']},
             'Bandung model applied in Makassar (trees, grass, cropland, built, water)');

// ---------------------------------------------------------------------------
// STEP 5. Saving your own copies (run once, then reload as in STEP 3)
// ---------------------------------------------------------------------------
// Replace the folder with one in your own Cloud project, then run the Tasks.
// var MY = 'projects/YOUR-PROJECT/assets/book';
// Export.table.toAsset(samples(HOME, 200, 1), 'train', MY + '/train_bandung_2021');
// Export.classifier.toAsset(rf, 'clf', MY + '/lulc_rf_fromtable');
// var trees = ee.List(rf.explain().get('trees'));
// Export.table.toAsset(ee.FeatureCollection(trees.map(function (t) {
//   return ee.Feature(ee.Geometry.Point([0, 0]), {tree: t}); })), 'trees', MY + '/lulc_rf_trees');
