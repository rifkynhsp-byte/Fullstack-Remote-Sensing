//| title: Accuracy assessment and area estimation
//| description: Confusion matrix, per class metrics, independent validation and area with error bars.

/**
 * CHAPTER 17 | Proving the map is worth trusting
 * ---------------------------------------------------------------------------
 * Goal
 *   Take the classification from chapter “Classical Supervised Learning” and produce the numbers a
 *   reviewer will ask for: a confusion matrix, producer and user accuracy per
 *   class, an independent field validation score, and an area estimate with a
 *   confidence interval rather than a bare figure.
 *
 * The distinction that runs through this script
 *   Internal validation asks whether the model generalises to points it did
 *   not train on. Independent validation asks whether the map is true. They
 *   are different questions and they routinely give answers five to ten
 *   points apart. Report both.
 *
 * Asset dependencies
 *   var classified = ...       classification from chapter “Classical Supervised Learning”
 *   var validationSet = ...    held out points from chapter “Ground Truth and Sampling Design”
 *   var fieldPlots = ...       independently collected reference data
 *   var aoi = ...
 */

// ---------------------------------------------------------------------------
// INPUTS. Everything this script needs, so it runs on its own
// ---------------------------------------------------------------------------
// The Mahakam Delta and the feature stack from chapter "Synthetic Aperture Radar
// Fusion", loaded as a module. Replace aoi with your own area (draw it, or use
// an asset) and the rest follows.
var aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60]);
var image2023 = require('users/rifkynauvalhsp/Fullstack-Remote-Sensing:lib_stack').getAnalysisReadyData(2023, aoi);
// A classification to assess: Random Forest on the stack, trained on 70 per cent
// of WorldCover-labelled points (chapter "Ground Truth and Sampling Design");
// the other 30 per cent are the held-out validation set. Bring your own map
// and field points and replace these lines.
var labels = require('users/rifkynauvalhsp/Fullstack-Remote-Sensing:book_labels');
var points = labels.labelledPoints(aoi).randomColumn('random', 42);
var trainingSet = image2023.sampleRegions({collection: points.filter(ee.Filter.lt('random', 0.7)), properties: ['landcover'], scale: 10, tileScale: 4});
var validationSet = points.filter(ee.Filter.gte('random', 0.7));
var classified = image2023.classify(ee.Classifier.smileRandomForest(100).train(trainingSet, 'landcover', image2023.bandNames()));

var CLASS_NAMES = ['Mangrove', 'Other forest', 'Water', 'Bareland', 'Urban'];
var SCALE = 10;

// ===========================================================================
// PART 1. The confusion matrix
// ===========================================================================
// Classify the held out validation points, then compare prediction against
// label. errorMatrix returns rows as ACTUAL class and columns as PREDICTED,
// which is the convention this chapter uses throughout. Get the orientation
// backwards and you will swap producer and user accuracy, which inverts the
// story your map tells about itself.
var validated = classified.sampleRegions({
  collection: validationSet,
  properties: ['landcover'],
  scale: SCALE,
  tileScale: 4
});

var matrix = validated.errorMatrix('landcover', 'classification');

print('Confusion matrix (rows actual, columns predicted):', matrix);
print('Overall accuracy:', matrix.accuracy());
print('Kappa:', matrix.kappa());

// ===========================================================================
// PART 2. Per class metrics, which are the ones that matter
// ===========================================================================
// Overall accuracy is a single number describing a multi class problem, and
// it is dominated by whichever class covers the most area. A map that is
// perfect on water and useless on mangrove can report 88 percent.
//
// Producer accuracy answers: of the mangrove that is really there, how much
// did the map find? Its complement is omission error, what the map missed.
//
// User accuracy answers: of the pixels the map calls mangrove, how many
// really are? Its complement is commission error, what the map invented.
//
// Which one matters depends on the decision. For a carbon claim, commission
// is the dangerous direction, because you are being paid for area you cannot
// prove exists. For a conservation alert system, omission is worse, because a
// missed clearing is a clearing nobody responded to.
var producers = matrix.producersAccuracy();
var users = matrix.consumersAccuracy();

print('Producer accuracy (1 minus omission):', producers);
print('User accuracy (1 minus commission):', users);

// Rendered as a readable table rather than a nested array.
var perClass = ee.FeatureCollection(
  CLASS_NAMES.map(function (name, i) {
    return ee.Feature(null, {
      'class': name,
      'producer': ee.Number(ee.List(producers.toList().get(i)).get(0)).multiply(100),
      'user': ee.Number(ee.List(users.toList().get(0)).get(i)).multiply(100)
    });
  })
);

print(ui.Chart.feature.byFeature(perClass, 'class', ['producer', 'user'])
  .setChartType('ColumnChart')
  .setOptions({
    title: 'Per class accuracy, internal validation',
    hAxis: {title: 'Class'},
    vAxis: {title: 'Accuracy, percent', viewWindow: {min: 0, max: 100}}
  }));

// ===========================================================================
// PART 3. Where the confusion actually is
// ===========================================================================
// The off diagonal cells are the useful part of the matrix and are usually
// skipped. Cell [0][1] is mangrove that the map called other forest. If that
// cell holds most of your error, the fix is not a better classifier: it is
// more training data along the mangrove and upland forest boundary, or a
// predictor that separates them, which chapter “Choosing Your Eyes” argued is elevation and
// radar rather than anything spectral.
var array = matrix.array();
print('Mangrove misread as other forest:', array.get([0, 1]));
print('Other forest misread as mangrove:', array.get([1, 0]));

// ===========================================================================
// PART 4. Independent validation
// ===========================================================================
// Everything above splits one dataset that one person drew from one set of
// imagery. It cannot detect a systematic labelling error, because both splits
// contain it.
//
// This section scores the map against reference data collected by a different
// process: field plots. The number it returns is almost always lower, and it
// is the honest one.
if (typeof fieldPlots !== 'undefined') {
  var fieldValidated = classified.sampleRegions({
    collection: fieldPlots,
    properties: ['landcover'],
    scale: SCALE,
    tileScale: 4
  });

  var fieldMatrix = fieldValidated.errorMatrix('landcover', 'classification');

  print('--- Independent field validation ---');
  print('Field plots used:', fieldValidated.size());
  print('Field confusion matrix:', fieldMatrix);
  print('Field overall accuracy:', fieldMatrix.accuracy());
} else {
  print('No fieldPlots imported: independent validation skipped.');
}

// Report both numbers side by side and let the gap speak. A five point gap is
// normal. A twenty point gap means your training data does not represent the
// landscape, and no amount of tuning will close it.

// ===========================================================================
// PART 5. Area estimation with a confidence interval
// ===========================================================================
// Counting classified pixels and multiplying by pixel area gives the MAP
// area. It is not the population area, because the map has known errors, and
// those errors are not symmetric.
//
// The good practice correction, following Olofsson and colleagues, adjusts
// the pixel count using the confusion matrix and returns a standard error.
// The steps below implement the stratified estimator in the form Earth Engine
// composes most directly.

// (a) Map area per class, in hectares.
// Area is summed at 30 m to stay inside the Code Editor's interactive limits;
// Exercise 4 asks you to repeat it at 10 m with an export.
var AREA_SCALE = 30;
var areaImage = ee.Image.pixelArea().divide(10000).addBands(classified);
var mapAreas = areaImage.reduceRegion({
  reducer: ee.Reducer.sum().group({groupField: 1, groupName: 'class'}),
  geometry: aoi,
  scale: AREA_SCALE,
  maxPixels: 1e13,
  tileScale: 4
});

// Keyed by class number, so a class missing from the map cannot shift the rest.
var areaByClass = ee.Dictionary(ee.List(mapAreas.get('groups')).iterate(
  function (g, acc) {
    g = ee.Dictionary(g);
    return ee.Dictionary(acc).set(ee.Number(g.get('class')).format('%d'), g.get('sum'));
  }, ee.Dictionary({})));
var totalArea = ee.Number(areaByClass.values().reduce(ee.Reducer.sum()));
print('Mapped area by class, hectares:', areaByClass);

// (b) Adjust. Earth Engine's matrix has rows = REFERENCE, columns = MAP.
// For map class i, W_i is its share of mapped area and n_i its COLUMN total.
//   adjusted proportion of reference class j:  p_j = sum_i W_i * n_ji / n_i
//   standard error:  SE(p_j) = sqrt( sum_i W_i^2 * q (1 - q) / (n_i - 1) ),
//   with q = n_ji / n_i   (Olofsson et al. 2014, equations 9 and 10).
// An earlier version divided by ROW totals while weighting by MAP area,
// which mixes the two directions and gives areas that look plausible and
// are wrong. Keep the directions straight.
var confusionArray = matrix.array();
var nClasses = CLASS_NAMES.length;

var adjusted = ee.List.sequence(0, nClasses - 1).map(function (j) {
  j = ee.Number(j);
  var terms = ee.List.sequence(0, nClasses - 1).map(function (i) {
    i = ee.Number(i);
    var colTotal = ee.Number(confusionArray.slice(1, i, i.add(1))
      .reduce(ee.Reducer.sum(), [0]).get([0, 0]));
    var q = ee.Number(ee.Algorithms.If(colTotal.gt(0),
      ee.Number(confusionArray.get([j, i])).divide(colTotal), 0));
    var w = ee.Number(areaByClass.get(i.format('%d'), 0)).divide(totalArea);
    var variance = ee.Number(ee.Algorithms.If(colTotal.gt(1),
      w.pow(2).multiply(q).multiply(ee.Number(1).subtract(q))
        .divide(colTotal.subtract(1)), 0));
    return ee.List([w.multiply(q), variance]);
  });
  var p = ee.Number(terms.map(function (t) { return ee.List(t).get(0); })
    .reduce(ee.Reducer.sum()));
  var se = ee.Number(terms.map(function (t) { return ee.List(t).get(1); })
    .reduce(ee.Reducer.sum())).sqrt();
  return ee.Feature(null, {
    'class': ee.List(CLASS_NAMES).get(j),
    'map_ha': areaByClass.get(j.format('%d'), 0),
    'adjusted_ha': p.multiply(totalArea),
    'ci95_ha': se.multiply(1.96).multiply(totalArea)
  });
});

print('Area adjusted for classification error, with 95% interval:',
  ee.FeatureCollection(adjusted));

// ===========================================================================
// PART 6. Compare against an existing product
// ===========================================================================
// Independent products are not truth, and they are a useful sanity check.
// A map that disagrees with Global Mangrove Watch by 40 percent is not
// necessarily wrong, and it does need an explanation before publication.
//
// Common legitimate reasons for disagreement: different years, different
// minimum mapping units, a different definition of what counts as mangrove,
// and different treatment of degraded or sparse stands.
var gmw = ee.FeatureCollection('projects/sat-io/open-datasets/GMW/extent/gmw_v3_2020_vec')
  .filterBounds(aoi);

var gmwArea = ee.Image.pixelArea().divide(10000)
  .clip(gmw.geometry())
  .reduceRegion({
    reducer: ee.Reducer.sum(),
    geometry: aoi,
    scale: AREA_SCALE,
    maxPixels: 1e13,
    tileScale: 4
  });

print('Global Mangrove Watch 2020 area in AOI, hectares:', gmwArea);

// Visual comparison beats a number here. Where do the two disagree?
Map.centerObject(aoi, 11);
Map.addLayer(classified.eq(0).selfMask(), {palette: ['#075e11']}, 'This map, mangrove');
Map.addLayer(gmw, {color: '#c8792b'}, 'Global Mangrove Watch 2020', false);

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Find the largest off diagonal cell in your matrix. Name the two classes
//    and propose one predictor that would separate them physically.
// 2. Report your internal and independent accuracy side by side. If the gap
//    exceeds ten points, explain what about your training data caused it.
// 3. Overlay this map and Global Mangrove Watch. Pick three disagreement
//    areas and determine, from high resolution imagery, which is right.
// 4. Compute area at 10 m and at 100 m. Report both, with the scale stated.
