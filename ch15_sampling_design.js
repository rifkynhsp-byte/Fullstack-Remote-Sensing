//| title: Building a defensible training set
//| description: Stratified sampling, class balance, spatial thinning and an honest split.

/**
 * CHAPTER 15 | Ground truth and sampling design
 * ---------------------------------------------------------------------------
 * Goal
 *   Produce a training and validation set that a reviewer cannot dismantle:
 *   stratified across classes, balanced enough that rare classes survive,
 *   spatially thinned so neighbouring pixels do not leak between the splits,
 *   and exported so the same samples can be reused across every experiment.
 *
 * Why this chapter comes before the classifier chapter
 *   Swapping Random Forest for gradient boosting moves accuracy by one or two
 *   points. Fixing a sampling design moves it by ten, and more importantly it
 *   changes whether the number you report is true. Sample quality outranks
 *   model choice, and it is not close.
 *
 * Asset dependencies
 *   var aoi = ...                              study area geometry
 *   var image2023 = getAnalysisReadyData(2023) feature stack, Chapter 10
 *   var trainingPolygons = ...                 hand drawn polygons, one per class,
 *                                              each with a 'landcover' property
 */

// ---------------------------------------------------------------------------
// CONFIGURATION
// ---------------------------------------------------------------------------
var CLASS_PROPERTY = 'landcover';
var SCALE = 10;                 // metres. Match the finest band in the stack.
var SPLIT = 0.7;                // proportion used for training
var SEED = 42;                  // any fixed integer. Fixed means reproducible.

// Points per class. Not equal on purpose, see the note on class imbalance.
var CLASS_TARGETS = {
  0: 300,   // mangrove, the class of interest, sampled heavily
  1: 250,   // other forest, the main confusion partner, also heavy
  2: 150,   // water, spectrally distinct and easy, needs fewer
  3: 200,   // bareland or agriculture, highly variable, needs more than water
  4: 150    // urban
};

// Minimum separation between samples, in metres. See the thinning section.
var MIN_SEPARATION = 60;

// ===========================================================================
// PART 1. Points or polygons
// ===========================================================================
// Both are defensible and they fail differently.
//
// POLYGONS capture within class variability: a forest polygon spanning sunlit
// crowns and shadowed gaps teaches the model that both are forest. They also
// invite edge contamination, and every pixel inside one polygon is nearly
// identical to its neighbours, which inflates the apparent sample size
// enormously. Thirty polygons can yield forty thousand pixels, and a model
// validated on those pixels reports an accuracy that means nothing.
//
// POINTS are precise and independent, and they under represent variability
// unless you place a lot of them.
//
// The approach below takes the middle route used in most operational work:
// draw small, confidently pure polygons, then sample a controlled number of
// POINTS from inside them. You get polygon convenience with point statistics.

print('Training polygons by class:',
  trainingPolygons.aggregate_histogram(CLASS_PROPERTY));

// ===========================================================================
// PART 2. Stratified sampling
// ===========================================================================
// stratifiedSample guarantees a number of points per class rather than
// sampling proportionally to area. That distinction is the whole reason it
// exists.
//
// In a coastal scene, water might cover 40 percent of the frame and a newly
// restored mangrove patch 0.3 percent. Proportional random sampling would
// return roughly 400 water points and 3 restoration points, and the model
// would learn that predicting water is almost always safe. Stratification
// forces the rare class to be represented.

// Paint the class labels into a raster so stratifiedSample has a stratum band
// to work from. This is the step people miss: the function stratifies on an
// image band, not on a feature property.
var classImage = trainingPolygons
  .reduceToImage({
    properties: [CLASS_PROPERTY],
    reducer: ee.Reducer.first()
  })
  .rename(CLASS_PROPERTY)
  .toInt();

var classValues = Object.keys(CLASS_TARGETS).map(Number);
var classPoints = classValues.map(function (k) { return CLASS_TARGETS[k]; });

var samples = classImage.addBands(ee.Image.pixelLonLat()).stratifiedSample({
  numPoints: 0,                  // ignored when classPoints is supplied
  classBand: CLASS_PROPERTY,
  region: aoi,
  scale: SCALE,
  seed: SEED,
  classValues: classValues,
  classPoints: classPoints,
  geometries: true,              // keep the geometry, we need it for thinning
  tileScale: 4
});

print('Samples drawn:', samples.size());
print('Samples by class:', samples.aggregate_histogram(CLASS_PROPERTY));

// Compare that histogram against CLASS_TARGETS. A class that came back short
// did not have enough eligible pixels, which usually means the polygons for
// it are too small or too few. That is a data collection problem and no
// amount of modelling fixes it.

// ===========================================================================
// PART 3. Spatial thinning
// ===========================================================================
// Two samples ten metres apart are, for practical purposes, one sample
// measured twice. They share illumination, atmosphere, canopy and often the
// same tree. If one lands in training and its twin in validation, the model
// is being tested on data it has effectively already seen.
//
// This is the quiet reason internal accuracy so often exceeds field accuracy
// by five to ten points. It is not that the model is overfitting in the
// textbook sense. It is that the validation set was never independent.
//
// The thinning below is deliberately simple: snap every sample to a coarse
// grid and keep one per cell. More sophisticated approaches exist, but the
// gain over this is small and the complexity is not.
var thinned = samples.map(function (feature) {
  var coords = feature.geometry().coordinates();
  // Convert to an approximate metric grid cell index. At these latitudes one
  // degree of longitude is roughly 111 km, which is close enough for the
  // purpose of deduplication.
  var cell = ee.String(
    ee.Number(coords.get(0)).multiply(111000).divide(MIN_SEPARATION).round().format('%d')
  ).cat('_').cat(
    ee.Number(coords.get(1)).multiply(111000).divide(MIN_SEPARATION).round().format('%d')
  );
  return feature.set('grid_cell', cell);
});

// distinct() keeps one feature per unique grid cell value.
thinned = thinned.distinct(['grid_cell']);

print('Samples after thinning:', thinned.size());
print('Thinned by class:', thinned.aggregate_histogram(CLASS_PROPERTY));

// If thinning removed more than about a third of your samples, the polygons
// are clustered too tightly. Spread them across the study area rather than
// drawing many in one convenient corner.

// ===========================================================================
// PART 4. Split the POINTS, not the pixels
// ===========================================================================
// Order matters and getting it wrong is invisible in the output.
//
// randomColumn attaches a reproducible pseudo random number to each feature.
// Filtering on it divides the POINTS. Only afterwards does each side sample
// the image. Do it the other way round and pixels from the same polygon land
// on both sides of the split.
var withRandom = thinned.randomColumn('random', SEED);

var training = withRandom.filter(ee.Filter.lt('random', SPLIT));
var validation = withRandom.filter(ee.Filter.gte('random', SPLIT));

print('Training points:', training.size());
print('Validation points:', validation.size());
print('Training balance:', training.aggregate_histogram(CLASS_PROPERTY));
print('Validation balance:', validation.aggregate_histogram(CLASS_PROPERTY));

// Check the validation histogram specifically. A random split can leave a
// rare class with four validation points, and a producer accuracy computed
// from four points is not a statistic. If that happens, raise the target for
// that class and redraw rather than reporting the number.

// ===========================================================================
// PART 5. Look at the samples before trusting them
// ===========================================================================
// Two diagnostics catch most collection errors before they reach a model.

// (a) Spectral separability. Chart the mean value of each class across the
//     predictor bands. Classes whose curves overlap everywhere will confuse,
//     and you now know that before spending an afternoon on training.
var separability = image2023.select(['B2', 'B3', 'B4', 'B8', 'B11', 'NDVI', 'S1_VH'])
  .sampleRegions({
    collection: thinned,
    properties: [CLASS_PROPERTY],
    scale: SCALE,
    tileScale: 4
  });

print(ui.Chart.feature.groups({
  features: separability,
  xProperty: 'NDVI',
  yProperty: 'S1_VH',
  seriesProperty: CLASS_PROPERTY
}).setChartType('ScatterChart').setOptions({
  title: 'Class separability: NDVI against radar backscatter',
  hAxis: {title: 'NDVI'},
  vAxis: {title: 'Sentinel-1 VH, dB'},
  pointSize: 3
}));

// Read that scatter carefully. If mangrove and other forest overlap
// completely on NDVI but separate along VH, you have just confirmed why
// Chapter 10 put radar in the stack.

// (b) Where the samples actually are. A map of the points, coloured by class,
//     reveals clustering, classes drawn only in one corner, and points that
//     fell in the sea.
Map.centerObject(aoi, 11);
Map.addLayer(image2023, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.3}, 'Composite');
Map.addLayer(training, {color: '#14a37f'}, 'Training points');
Map.addLayer(validation, {color: '#c8792b'}, 'Validation points');

// ===========================================================================
// PART 6. Export, and stop redrawing
// ===========================================================================
// Export both sets to assets. From this point on, every experiment in
// Chapters 16 to 19 loads the same samples, which means an accuracy
// difference between two models is a difference between the models rather
// than between two different random draws.
//
// This is the single cheapest thing you can do to make your results
// comparable, and almost nobody does it.
Export.table.toAsset({
  collection: training,
  description: 'training_points_2023',
  assetId: 'training_points_2023'
});

Export.table.toAsset({
  collection: validation,
  description: 'validation_points_2023',
  assetId: 'validation_points_2023'
});

// Also export to Drive as CSV, so the samples can be inspected in a
// spreadsheet, shared with a field team, or loaded into desktop GIS for
// checking against high resolution imagery.
Export.table.toDrive({
  collection: thinned,
  description: 'all_samples_2023_csv',
  fileFormat: 'CSV'
});

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Set every class target to the same number and rerun. Which class becomes
//    harder to model, and why does equal sampling not mean fair sampling?
// 2. Set MIN_SEPARATION to 10 metres, effectively disabling thinning, and run
//    Chapter 16 with the result. Record how much reported accuracy rises.
// 3. Open the exported CSV and check twenty random points against high
//    resolution basemap imagery. Count how many are mislabelled. That rate is
//    the ceiling on your map's accuracy and nothing downstream can exceed it.
