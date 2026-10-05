//| title: A thesis starter: GEDI biomass from embeddings, tested two ways
//| description: Spread GEDI LiDAR biomass footprints wall to wall with AlphaEarth embeddings, and score the model with random folds and with spatial blocks.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 36 | A one-week starting point for three open topics at once
 * ---------------------------------------------------------------------------
 * Question
 *   GEDI, the spaceborne LiDAR on the International Space Station, estimates
 *   above ground biomass density (AGBD) at scattered 25 m footprints. Can the
 *   64 AlphaEarth embedding dimensions fill the gaps between footprints, and
 *   does the answer change when the test is spatially honest?
 *
 * Area
 *   Lowland forest and plantations on the Jambi / South Sumatra border.
 *
 * What to change first
 *   The rectangle, the years, and BLOCK_SIZE_M. Then swap the target: GEDI
 *   canopy height (L2A rh98) instead of biomass, or your own field plots.
 */

var aoi = ee.Geometry.Rectangle([103.10, -2.40, 103.70, -1.90]);
var N_POINTS = 1500;
var N_FOLDS = 5;
var BLOCK_SIZE_M = 5000;

// ===========================================================================
// PART 1. GEDI L4A footprints, good quality only, 2022-2023
// ===========================================================================
// The monthly raster holds one 25 m pixel per footprint. Keep shots that pass
// the L4 quality flag and were not taken in a degraded pointing state.
var agbd = ee.ImageCollection('LARSE/GEDI/GEDI04_A_002_MONTHLY')
  .filterDate('2022-01-01', '2024-01-01')
  .filterBounds(aoi)
  .map(function (img) {
    var ok = img.select('l4_quality_flag').eq(1).and(img.select('degrade_flag').eq(0));
    return img.updateMask(ok);
  })
  .select('agbd')
  .mosaic()
  .clip(aoi);

// ===========================================================================
// PART 2. The 2023 embeddings
// ===========================================================================
var embeddings = ee.ImageCollection('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL')
  .filterDate('2023-01-01', '2024-01-01')
  .filterBounds(aoi)
  .mosaic();
var bands = embeddings.bandNames();

// ===========================================================================
// PART 3. Sample footprints, give each a random fold and a block fold
// ===========================================================================
var hasShot = agbd.gt(0).rename('shot').toInt();
var footprints = agbd.addBands(hasShot).stratifiedSample({
  numPoints: N_POINTS, classBand: 'shot', region: aoi, scale: 25, seed: 7,
  geometries: true, tileScale: 4
});

// Every 5 km cell gets one fold number, so a whole block is held out at once.
var blockFold = ee.Image.random(42).multiply(N_FOLDS).floor()
  .reproject(ee.Projection('EPSG:3857').atScale(BLOCK_SIZE_M))
  .rename('block_fold').toInt();

var samples = embeddings.addBands(blockFold)
  .sampleRegions({collection: footprints, properties: ['agbd'], scale: 10,
                  tileScale: 4, geometries: true})
  .randomColumn('r', 42)
  .map(function (f) {
    return f.set('random_fold', ee.Number(f.get('r')).multiply(N_FOLDS).floor());
  });

function forest() {
  return ee.Classifier.smileRandomForest({numberOfTrees: 100, seed: 7})
    .setOutputMode('REGRESSION');
}

// Train on four folds, predict the fifth, five times over.
function outOfFold(foldProperty) {
  return ee.FeatureCollection(ee.List.sequence(0, N_FOLDS - 1).map(function (k) {
    var train = samples.filter(ee.Filter.neq(foldProperty, k));
    var test = samples.filter(ee.Filter.eq(foldProperty, k));
    return test.classify(forest().train(train, 'agbd', bands), 'predicted');
  })).flatten();
}

// R squared and RMSE from out-of-fold predictions, on the server.
function score(fc, label) {
  var mean = fc.aggregate_mean('agbd');
  var withErr = fc.map(function (f) {
    var e = ee.Number(f.get('predicted')).subtract(f.get('agbd'));
    var d = ee.Number(f.get('agbd')).subtract(mean);
    return f.set({se: e.pow(2), ss: d.pow(2)});
  });
  var sse = withErr.aggregate_sum('se');
  return ee.Dictionary({
    design: label,
    r2: ee.Number(1).subtract(sse.divide(withErr.aggregate_sum('ss'))),
    rmse: sse.divide(fc.size()).sqrt()
  });
}

print('Footprints used:', samples.size());
print('GEDI AGBD standard deviation:', samples.aggregate_total_sd('agbd'));
print(score(outOfFold('random_fold'), 'random 5-fold'));
print(score(outOfFold('block_fold'), '5 km block 5-fold'));

// ===========================================================================
// PART 4. A wall-to-wall map from every footprint
// ===========================================================================
// This is a model of a model: GEDI AGBD is itself predicted from waveform
// metrics. Report the block score next to it, never the map alone.
var agbdMap = embeddings.clip(aoi).classify(forest().train(samples, 'agbd', bands));

Map.centerObject(aoi, 11);
Map.addLayer(agbdMap, {min: 0, max: 250,
  palette: ['f7fcb9', 'addd8e', '41ab5d', '006837', '00361c']}, 'Predicted AGBD');
Map.addLayer(agbd, {min: 0, max: 250, palette: ['ffffcc', 'fd8d3c', '800026']},
  'GEDI footprints');
