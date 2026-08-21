//| title: Ensemble land cover classification
//| description: Split, sample, tune, train three classifiers, vote, and clean up.

/**
 * CHAPTER 16 | Ensemble supervised classification
 * ---------------------------------------------------------------------------
 * Goal
 *   Turn the feature stack from Chapter 10 and the training points from
 *   Chapter 15 into a five class land cover map, using three different
 *   classifiers and a majority vote between them.
 *
 * Class schema
 *   0 Mangrove   1 Other forest   2 Water   3 Bareland or agriculture
 *   4 Urban
 *
 * Asset dependencies
 *   var aoi = ...                                 study area geometry
 *   var trainingDataGeometries = ...              labelled points, Chapter 15
 *   var image2023 = getAnalysisReadyData(2023)    feature stack, Chapter 10
 *
 * Run order
 *   This script assumes Chapters 10 and 15 have already run in the same
 *   editor session, or that their outputs have been exported to assets and
 *   imported here. Exporting the stack to an asset first is strongly
 *   recommended: it turns a computation that reruns on every pan and zoom
 *   into one that ran once.
 */

var lulcPalette = [
  '#075e11',  // 0 mangrove
  '#358221',  // 1 other forest
  '#1A5BAB',  // 2 water
  '#FFDB5C',  // 3 bareland or agriculture
  '#ED022A'   // 4 urban
];

// ===========================================================================
// PART 1. Split before you sample
// ===========================================================================
// The order of these two operations is not cosmetic and getting it wrong is
// the most common silent error in remote sensing machine learning.
//
// randomColumn() attaches a reproducible pseudo random number between 0 and 1
// to each training feature. Filtering on it splits the POINTS into training
// and validation sets. Only then does each set get used to sample the image.
//
// If you sample first and split afterwards, pixels drawn from inside the same
// training polygon end up on both sides of the split. They are spatially
// autocorrelated and nearly identical, so the model is being validated
// against data it has effectively already seen. Accuracy comes back four to
// eight points too high, consistently, and nothing in the output looks wrong.
var withRandom = trainingDataGeometries.randomColumn('random', 42);

var SPLIT = 0.7;
var trainingSet   = withRandom.filter(ee.Filter.lt('random', SPLIT));
var validationSet = withRandom.filter(ee.Filter.gte('random', SPLIT));

print('Training points:', trainingSet.size());
print('Validation points:', validationSet.size());

var bands = image2023.bandNames();

// sampleRegions extracts every band value at every point and returns a table.
// tileScale is the memory escape hatch: it splits the computation into
// smaller tiles at some cost in speed. If this line throws "user memory limit
// exceeded", raise it to 8 or 16 before changing anything else.
var trainingSamples = image2023.sampleRegions({
  collection: trainingSet,
  properties: ['landcover'],
  scale: 10,
  tileScale: 4
});

var validationSamples = image2023.sampleRegions({
  collection: validationSet,
  properties: ['landcover'],
  scale: 10,
  tileScale: 4
});

// A point that falls on a masked pixel produces a feature with no band
// values, which silently corrupts training. Check the count survived.
print('Usable training samples:', trainingSamples.size());

// ===========================================================================
// PART 2. Tune the forest
// ===========================================================================
// Random Forest has few parameters that matter, and the number of trees is
// the main one. Too few and the ensemble is unstable; beyond a certain point
// accuracy plateaus and you are only paying for computation.
//
// This sweep trains a forest at each size and scores it against the held out
// validation set. Note the order inside the loop: classify the validation
// FEATURES, then build the error matrix from them. Calling errorMatrix on the
// training samples instead reports resubstitution accuracy, which is close to
// meaningless and always flattering.
var numTreesList = ee.List.sequence(10, 150, 20);

var accuracies = numTreesList.map(function (numTrees) {
  var classifier = ee.Classifier.smileRandomForest(numTrees).train({
    features: trainingSamples,
    classProperty: 'landcover',
    inputProperties: bands
  });
  var validated = validationSamples.classify(classifier);
  return validated.errorMatrix('landcover', 'classification').accuracy();
});

var maxAccuracy = accuracies.reduce(ee.Reducer.max());
var bestNumTrees = numTreesList.get(accuracies.indexOf(maxAccuracy));

print('Tuning curve:', ui.Chart.array.values(accuracies, 0, numTreesList)
  .setOptions({
    title: 'Random Forest tuning',
    hAxis: {title: 'Number of trees'},
    vAxis: {title: 'Validation accuracy'},
    legend: {position: 'none'}
  }));
print('Best number of trees:', bestNumTrees);

// Read the curve, do not just take the maximum. If accuracy is flat from 50
// trees onward, the "best" value is noise and 50 is the honest choice: fewer
// trees, same accuracy, faster to run and faster to export.

// ===========================================================================
// PART 3. Which bands are actually working
// ===========================================================================
// classifier.explain() returns the internal structure of a trained model,
// including per band importance. This is the diagnostic that tells you
// whether the expensive radar and texture bands from Chapter 10 are earning
// their place, or whether NDVI is doing all the work on its own.
var explainer = ee.Classifier.smileRandomForest(100)
  .train(trainingSamples, 'landcover', bands);

var importance = ee.Feature(null, ee.Dictionary(explainer.explain()).get('importance'));

print(ui.Chart.feature.byProperty(importance)
  .setChartType('ColumnChart')
  .setOptions({
    title: 'Feature contribution to the model',
    hAxis: {title: 'Predictor'},
    vAxis: {title: 'Importance'},
    legend: {position: 'none'}
  }));

// What to do with this chart:
//   A band near zero is dead weight. Drop it and retrain; if accuracy holds,
//   the model just got cheaper and more stable.
//   A band that dominates everything else deserves suspicion rather than
//   satisfaction. Ask whether it could be a disguised copy of the label.
//   Chapter 22 works through a real case where exactly that happened.

// ===========================================================================
// PART 4. Three classifiers, three sets of blind spots
// ===========================================================================
// Random Forest: bagging. Many trees on bootstrap samples, each seeing a
// random band subset, majority vote. Robust, resists overfitting, handles
// mixed scales without normalisation. Cannot predict outside its training
// range, which matters for regression far more than classification.
var rf = ee.Classifier.smileRandomForest(bestNumTrees).train({
  features: trainingSamples,
  classProperty: 'landcover',
  inputProperties: bands
});

// Support vector machine with a radial basis kernel. Finds a boundary in a
// transformed space, so it can separate classes no straight line divides.
// It is distance based, which means unscaled bands wreck it: this is exactly
// why the PALSAR conversion in Chapter 10 mattered. gamma controls how local
// the boundary is and cost controls tolerance of misclassified training
// points. Both need tuning for a real deployment; these are starting values.
var svm = ee.Classifier.libsvm({
  kernelType: 'RBF',
  gamma: 0.5,
  cost: 10
}).train({
  features: trainingSamples,
  classProperty: 'landcover',
  inputProperties: bands
});

// Gradient tree boost: sequential error correction, each tree fitting what
// the previous ones got wrong. Often the most accurate of the three on
// tabular data, and the most willing to overfit if training data is noisy.
var gtb = ee.Classifier.smileGradientTreeBoost(100).train({
  features: trainingSamples,
  classProperty: 'landcover',
  inputProperties: bands
});

var classifiedRF  = image2023.classify(rf).rename('classification');
var classifiedSVM = image2023.classify(svm).rename('classification');
var classifiedGTB = image2023.classify(gtb).rename('classification');

// ===========================================================================
// PART 5. Vote
// ===========================================================================
// Stack the three predictions as bands and take the per pixel mode. Where all
// three agree, nothing changes. Where they disagree, the majority wins and
// one model's idiosyncratic error is outvoted.
//
// This works because the three algorithms fail differently. Ensembling three
// variants of the same algorithm gains almost nothing; the diversity is the
// mechanism.
var votes = ee.Image.cat([classifiedRF, classifiedSVM, classifiedGTB]);
var ensemble = votes.reduce(ee.Reducer.mode()).rename('classification');

// ===========================================================================
// PART 6. Post processing
// ===========================================================================
// Pixel based classification produces isolated misclassified pixels, the
// salt and pepper effect. A modal filter replaces each pixel with the most
// common value in its neighbourhood, consolidating small patches.
//
// Be deliberate about the radius. It is a minimum mapping unit decision in
// disguise: a 3 pixel circle at 10 m resolution erases any real feature
// smaller than roughly 30 m across. Over a landscape of narrow mangrove
// fringes that is capable of deleting the thing you are mapping.
var ensembleSmooth = ensemble.focalMode({
  radius: 3,
  kernelType: 'circle',
  units: 'pixels'
}).rename('classification');

// ===========================================================================
// DISPLAY
// ===========================================================================
Map.centerObject(aoi, 11);
Map.addLayer(classifiedRF,  {min: 0, max: 4, palette: lulcPalette}, 'Random Forest', false);
Map.addLayer(classifiedSVM, {min: 0, max: 4, palette: lulcPalette}, 'SVM', false);
Map.addLayer(classifiedGTB, {min: 0, max: 4, palette: lulcPalette}, 'Gradient tree boost', false);
Map.addLayer(ensemble,      {min: 0, max: 4, palette: lulcPalette}, 'Ensemble, raw', false);
Map.addLayer(ensembleSmooth,{min: 0, max: 4, palette: lulcPalette}, 'Ensemble, smoothed');

// Export the result rather than admiring it interactively. Every pan and zoom
// recomputes the whole chain; an exported asset computes once.
Export.image.toAsset({
  image: ensembleSmooth.clip(aoi),
  description: 'lulc_ensemble_2023',
  assetId: 'lulc_ensemble_2023',
  region: aoi,
  scale: 10,
  maxPixels: 1e13
});

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Toggle between the three individual classifications over a mangrove
//    fringe. Where they disagree is where your map is genuinely uncertain,
//    and it is a better uncertainty map than most formal ones.
// 2. Deliberately sample before splitting instead of after. Record how much
//    the reported accuracy rises. That gap is the size of the lie.
// 3. Drop the three lowest importance bands and retrain. Report the accuracy
//    change and decide whether the bands should stay.
// 4. Raise the focal mode radius to 6 and find a real feature it deleted.
