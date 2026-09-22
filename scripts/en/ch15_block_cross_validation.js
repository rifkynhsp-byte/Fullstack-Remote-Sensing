//| title: Spatial block cross validation
//| description: Partition into geographic blocks so training and testing are spatially decoupled.

/**
 * CHAPTER 15 | Spatial block cross validation
 * ---------------------------------------------------------------------------
 * Goal
 *   Replace a random train and test split with one that separates data
 *   geographically, then measure the difference between the two. That
 *   difference is how much your reported accuracy has been inflated by
 *   spatial autocorrelation.
 *
 * Why a random split is not enough
 *   Thinning, covered in the main script for this chapter, enforces a minimum
 *   distance between samples. It reduces near duplicate pairs, and it does not
 *   solve the underlying problem, because Tobler's first law does not stop at
 *   60 metres. Samples from the same estuary share tide state, water
 *   chemistry, species composition, sun angle and atmospheric conditions. A
 *   model can learn "this estuary looks like this" and score well on held out
 *   points from the same estuary while failing completely on the next one.
 *
 *   That failure mode has a name, spatial data leakage, and it is why models
 *   reporting 95 percent in validation routinely deliver 60 percent when
 *   deployed to a neighbouring province.
 *
 * The fix
 *   Partition the study area into geographic blocks. Assign whole blocks to
 *   folds, never individual points. Train on some blocks, test on the blocks
 *   held out. The model is then forced to generalise across space rather than
 *   interpolate within it.
 *
 * Asset dependencies
 *   var aoi = ...                                 study area geometry
 *   var image2023 = getAnalysisReadyData(2023)    feature stack, Chapter 10
 *   var samples = ...                             labelled points, this chapter
 */

var CLASS_PROPERTY = 'landcover';
var SCALE = 10;

// Block size in metres. This is the parameter that matters and it is an
// ecological decision, not a statistical one.
//
// Too small and neighbouring blocks remain correlated, so you have merely
// made the random split slightly harder. Too large and each fold covers a
// different landscape entirely, so the score reflects landscape difference
// rather than model quality.
//
// The defensible starting point is the range over which your predictors are
// autocorrelated, which you can estimate from a semivariogram, or approximate
// from what you know of the landscape. Over a delta, the scale at which
// conditions genuinely change is the sub estuary, a few kilometres.
var BLOCK_SIZE_M = 5000;
var N_FOLDS = 5;

// ===========================================================================
// PART 1. Build the blocks
// ===========================================================================
// A regular grid over the study area. Each cell gets a fold number, assigned
// so that adjacent cells land in different folds. A simple checkerboard style
// assignment is better than random assignment here, because random assignment
// can place several adjacent blocks in the same fold and reintroduce exactly
// the correlation we are removing.
var proj = ee.Projection('EPSG:3857').atScale(BLOCK_SIZE_M);

var blocks = ee.Image.random(42)
  .multiply(N_FOLDS)
  .floor()
  .reproject(proj)          // snap to the block grid
  .rename('fold')
  .toInt();

// Give every sample the fold of the block it falls in.
var samplesWithFold = blocks.sampleRegions({
  collection: samples,
  scale: BLOCK_SIZE_M,
  geometries: true,
  tileScale: 4
});

print('Samples per fold:', samplesWithFold.aggregate_histogram('fold'));

// Check that histogram. Folds should be roughly balanced. Badly uneven folds
// usually mean the block size is close to the size of the study area, so
// reduce BLOCK_SIZE_M or reduce N_FOLDS.

Map.centerObject(aoi, 10);
Map.addLayer(blocks.clip(aoi).randomVisualizer(), {}, 'Cross validation blocks', false);
Map.addLayer(samplesWithFold, {color: '#14a37f'}, 'Samples', false);

// ===========================================================================
// PART 2. Run the folds
// ===========================================================================
// For each fold: train on every OTHER block, test on this one. The result is
// N independent estimates of how well the model transfers to ground it has
// never seen.
var bands = image2023.bandNames();

var foldResults = ee.List.sequence(0, N_FOLDS - 1).map(function (fold) {
  fold = ee.Number(fold);

  var trainPoints = samplesWithFold.filter(ee.Filter.neq('fold', fold));
  var testPoints  = samplesWithFold.filter(ee.Filter.eq('fold', fold));

  var trainSamples = image2023.sampleRegions({
    collection: trainPoints,
    properties: [CLASS_PROPERTY],
    scale: SCALE,
    tileScale: 4
  });

  var testSamples = image2023.sampleRegions({
    collection: testPoints,
    properties: [CLASS_PROPERTY],
    scale: SCALE,
    tileScale: 4
  });

  var classifier = ee.Classifier.smileRandomForest(100).train({
    features: trainSamples,
    classProperty: CLASS_PROPERTY,
    inputProperties: bands
  });

  var matrix = testSamples.classify(classifier)
    .errorMatrix(CLASS_PROPERTY, 'classification');

  return ee.Feature(null, {
    fold: fold,
    n_train: trainPoints.size(),
    n_test: testPoints.size(),
    accuracy: matrix.accuracy()
  });
});

var results = ee.FeatureCollection(foldResults);
print('Per fold results:', results);

var accuracies = results.aggregate_array('accuracy');
print('Block CV mean accuracy:', ee.Array(accuracies).reduce(ee.Reducer.mean(), [0]));
print('Block CV standard deviation:', ee.Array(accuracies).reduce(ee.Reducer.stdDev(), [0]));

// The standard deviation is as informative as the mean. A model scoring
// 0.84 plus or minus 0.02 across blocks transfers reliably. The same mean
// with plus or minus 0.15 tells you the model works in some parts of the
// landscape and fails in others, which is a fact worth knowing before anyone
// makes a decision from the map.

// ===========================================================================
// PART 3. Measure the inflation
// ===========================================================================
// Run the ordinary random split for comparison. The gap between the two is
// the number this whole script exists to reveal.
var withRandom = samplesWithFold.randomColumn('random', 42);

var randomTrain = image2023.sampleRegions({
  collection: withRandom.filter(ee.Filter.lt('random', 0.7)),
  properties: [CLASS_PROPERTY], scale: SCALE, tileScale: 4
});
var randomTest = image2023.sampleRegions({
  collection: withRandom.filter(ee.Filter.gte('random', 0.7)),
  properties: [CLASS_PROPERTY], scale: SCALE, tileScale: 4
});

var randomClassifier = ee.Classifier.smileRandomForest(100)
  .train(randomTrain, CLASS_PROPERTY, bands);

var randomAccuracy = randomTest.classify(randomClassifier)
  .errorMatrix(CLASS_PROPERTY, 'classification')
  .accuracy();

print('Random split accuracy:', randomAccuracy);
print('--- Compare the two numbers above ---');

// A gap of two to four points is normal and tolerable.
//
// A gap of ten or more means the random split was measuring interpolation
// rather than prediction, and the block figure is the one to report. It will
// be lower, and it is the one that will match what happens when someone
// applies your model to the next province.
//
// Report both, and say which is which. A methods section that quotes only the
// random split figure is not wrong so much as incomplete, and a reviewer who
// knows this literature will ask.

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Run at BLOCK_SIZE_M of 1000, 5000 and 20000. Plot accuracy against block
//    size. The point where accuracy stops falling is an empirical estimate of
//    your data's autocorrelation range.
// 2. Report the per fold spread. Identify the worst performing block and look
//    at it on the map. What is different about that part of the landscape?
// 3. Apply your model trained on one estuary to a different one entirely.
//    Compare that accuracy to your block CV mean. They should be close. If
//    the real transfer is much worse, your blocks were too small.
