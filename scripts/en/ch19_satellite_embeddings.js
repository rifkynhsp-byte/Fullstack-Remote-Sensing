//| title: Low shot mapping with satellite embeddings
//| description: The same map as Chapter 16, from 20 points per class and no feature engineering.

/**
 * CHAPTER 19 | The GeoAI shortcut, and its price
 * ---------------------------------------------------------------------------
 * Goal
 *   Produce a land cover map comparable to Chapter 16 using Google's annual
 *   satellite embeddings, with roughly 20 training points per class, no cloud
 *   masking, no compositing and no feature engineering.
 *
 * What the dataset is
 *   GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL. A foundation model, AlphaEarth,
 *   was trained on trillions of pixels from many sensors across space and
 *   time. For every 10 m pixel on Earth, for each year, it emits a 64
 *   dimensional vector. Those 64 numbers are not measurements. Band A00 is
 *   not a wavelength. Each is a learned coordinate in a space the model
 *   organised so that semantically similar places sit near each other.
 *
 * Why this changes the workload
 *   Chapter 10 spent 180 lines assembling optical, radar, terrain and texture
 *   into a stack. The embedding already encodes all of that context, because
 *   the model saw all of those sensors during training. The stack below is
 *   one line.
 *
 * Asset dependencies
 *   var aoi = ...            study area geometry
 *   var samplePoints = ...   ~20 labelled points per class, property 'landcover'
 */

var YEAR = 2023;

var lulcPalette = ['#075e11', '#358221', '#1A5BAB', '#FFDB5C', '#ED022A'];
var classNames = ['Mangrove', 'Other forest', 'Water', 'Bareland', 'Urban'];

// ===========================================================================
// PART 1. Load the embedding
// ===========================================================================
// One image. 64 bands, named A00 to A63. No masking is needed because the
// model already handled cloud during training, and no compositing is needed
// because the product is already annual.
//
// Note the date filter still uses a full year window. The collection holds
// one image per year per tile, timestamped at the start of the year.
var embeddings = ee.ImageCollection('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL')
  .filterDate(YEAR + '-01-01', (YEAR + 1) + '-01-01')
  .filterBounds(aoi)
  .mosaic()
  .clip(aoi);

print('Embedding bands:', embeddings.bandNames());

// The vectors are unit normalised, so every band sits roughly between -1 and
// 1 with no outliers and no scaling to worry about. This is one of the
// quieter conveniences: distance based classifiers work out of the box.

// ===========================================================================
// PART 2. Train on very little
// ===========================================================================
// The same split discipline as Chapter 16 applies. Small sample sizes make
// the split matter more, not less: with 20 points per class, a leak between
// training and validation is proportionally far more damaging.
var withRandom = samplePoints.randomColumn('random', 42);
var trainingSet   = withRandom.filter(ee.Filter.lt('random', 0.7));
var validationSet = withRandom.filter(ee.Filter.gte('random', 0.7));

var training = embeddings.sampleRegions({
  collection: trainingSet,
  properties: ['landcover'],
  scale: 10,
  tileScale: 4
});

print('Training samples used:', training.size());

// A modest forest is enough. With 64 well organised dimensions and few
// points, a large ensemble adds computation without adding information.
var classifier = ee.Classifier.smileRandomForest(100).train({
  features: training,
  classProperty: 'landcover',
  inputProperties: embeddings.bandNames()
});

var classified = embeddings.classify(classifier).rename('classification');

// ===========================================================================
// PART 3. Validate exactly as harshly as before
// ===========================================================================
// The temptation with a low shot workflow is to trust it because it was easy.
// Resist that. Independent validation is more important here, not less,
// because you have less training data to have caught problems with.
var validated = embeddings.sampleRegions({
  collection: validationSet,
  properties: ['landcover'],
  scale: 10,
  tileScale: 4
}).classify(classifier);

var matrix = validated.errorMatrix('landcover', 'classification');
print('Confusion matrix:', matrix);
print('Overall accuracy:', matrix.accuracy());
print('Producer accuracy (omission):', matrix.producersAccuracy());
print('User accuracy (commission):', matrix.consumersAccuracy());

// ===========================================================================
// PART 4. Similarity search: find everywhere that looks like here
// ===========================================================================
// This capability has no equivalent in the classical workflow and it is worth
// the chapter on its own.
//
// Because semantically similar places sit near each other in the 64
// dimensional space, the distance between a reference pixel's vector and
// every other pixel's vector is a meaningful similarity measure. Give it one
// location you know is healthy mangrove and it will find everywhere else that
// resembles it, with no training and no labels at all.
var referencePoint = ee.Geometry.Point([117.58, -0.84]);

var referenceVector = ee.Image.constant(
  embeddings.reduceRegion({
    reducer: ee.Reducer.first(),
    geometry: referencePoint,
    scale: 10
  }).values()
);

// Euclidean distance in embedding space. Lower is more similar.
var similarity = embeddings.subtract(referenceVector)
  .pow(2)
  .reduce(ee.Reducer.sum())
  .sqrt()
  .rename('distance');

Map.addLayer(similarity, {min: 0, max: 2,
  palette: ['#08306b', '#4292c6', '#deebf7', '#ffffff']},
  'Similarity to reference (dark is similar)', false);

// Practical use: drop a point on a stand you know from fieldwork, run this,
// and use the result to decide where to send the next survey team. It is a
// sampling design tool as much as a mapping one.

// ===========================================================================
// DISPLAY
// ===========================================================================
Map.centerObject(aoi, 11);

// The first three principal bands rendered as RGB give a false colour view of
// the embedding space itself. It has no physical meaning, but similar
// colours mean similar land cover, which makes it a surprisingly good
// exploratory layer for spotting boundaries before any classification.
Map.addLayer(embeddings, {bands: ['A01', 'A16', 'A09'], min: -0.3, max: 0.3},
  'Embedding space, false colour', false);
Map.addLayer(classified, {min: 0, max: 4, palette: lulcPalette},
  'Low shot classification');

// ---------------------------------------------------------------------------
// The honest caveats
// ---------------------------------------------------------------------------
// Annual granularity. One vector per year. This cannot answer a question
// about a single storm, a single harvest, or the month a clearing happened.
// For those, Chapter 21 and the optical time series remain the only route.
//
// Opacity. When a boundary looks wrong there is no band to inspect and no
// physical reasoning to apply, because A37 does not mean anything you can
// interrogate. The classical stack is debuggable; this is not.
//
// Dependency. The dataset exists because Google publishes it, on Google's
// schedule, with Google's coverage decisions. A monitoring system that cannot
// function without it has an external dependency it does not control.
//
// This is why the book teaches both. Someone who only learned this shortcut
// has no way to check whether the shortcut worked.
//
// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Run this over the same area as Chapter 16 and put the two classifications
//    side by side. Find three places where they disagree and use high
//    resolution basemap imagery to decide which one is right.
// 2. Cut the training points to 10 per class, then 5. Plot accuracy against
//    sample size and find where it collapses.
// 3. Run the similarity search from a degraded stand instead of a healthy one.
//    Compare the two result maps and describe what the difference shows.
