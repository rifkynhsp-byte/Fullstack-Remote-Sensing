//| title: Object based classification with SNIC
//| description: Segment, summarise per object, classify objects, and vectorise for delivery.

/**
 * CHAPTER 18 | Classifying objects instead of pixels
 * ---------------------------------------------------------------------------
 * Goal
 *   Replace the noisy pixel by pixel classification of chapter “Classical Supervised Learning” with one
 *   that classifies spatially coherent objects, then export the result as
 *   vectors that open cleanly in QGIS or ArcGIS.
 *
 * The idea in one sentence
 *   Group pixels that belong together, describe each group by its average
 *   properties, and classify the groups, so the unit of analysis becomes
 *   something that resembles a feature on the ground rather than an arbitrary
 *   ten metre square.
 *
 * Asset dependencies
 *   var aoi = ...
 *   var image2023 = getAnalysisReadyData(2023)   feature stack, chapter “Synthetic Aperture Radar Fusion”
 *   var trainingPoints = ...                     from chapter “Ground Truth and Sampling Design”
 */

// ---------------------------------------------------------------------------
// INPUTS. Everything this script needs, so it runs on its own
// ---------------------------------------------------------------------------
// The Mahakam Delta and the feature stack from chapter "Synthetic Aperture Radar
// Fusion", loaded as a module. Replace aoi with your own area (draw it, or use
// an asset) and the rest follows.
// Segmentation at 10 m is memory-hungry: a 10 x 10 km corner of the delta keeps it within limits.
var aoi = ee.Geometry.Rectangle([117.55, -0.80, 117.65, -0.70]);
var image2023 = require('users/rifkynauvalhsp/Fullstack-Remote-Sensing:lib_stack').getAnalysisReadyData(2023, aoi)
  // The GLCM texture bands are left out: averaging them per object exceeds the memory limit, and the
  // per-object standard deviation in PART 3 already measures texture.
  .select(['B2', 'B3', 'B4', 'B8', 'B11', 'B12', 'NDVI', 'EVI', 'SAVI', 'MNDWI', 'S1_VV', 'S1_VH']);
// Labelled points (WorldCover stand-ins) for the object classifier.
// 60 per class: sampling through a segmentation is memory-hungry.
var trainingPoints = require('users/rifkynauvalhsp/Fullstack-Remote-Sensing:book_labels').labelledPoints(aoi, [60, 60, 60, 60, 60]);

var CLASS_PROPERTY = 'landcover';
var SCALE = 10;

var lulcPalette = ['#075e11', '#358221', '#1A5BAB', '#FFDB5C', '#ED022A'];

// ===========================================================================
// PART 1. Choose the bands that drive segmentation
// ===========================================================================
// Segmentation should be driven by the bands that define object boundaries,
// not by every band in the stack. Feeding twenty correlated bands into SNIC
// produces boundaries dominated by whichever group is largest, and it is far
// slower.
//
// Four bands are usually enough over a coastal landscape: two that separate
// vegetation from everything else, one that separates water, and one radar
// band that responds to structure rather than colour.
var segmentationBands = image2023.select(['B4', 'B8', 'MNDWI', 'S1_VH']);

// ===========================================================================
// PART 2. SNIC
// ===========================================================================
// Simple Non Iterative Clustering grows superpixels outward from a regular
// grid of seed points, assigning each pixel to the seed it is closest to in a
// combined spectral and spatial distance.
//
// Three parameters do the work and each is an ecological decision rather than
// a computational one.
//
//   size         seed spacing in pixels. This sets the approximate object
//                size and it is the parameter to think hardest about. At 10 m
//                resolution, size 10 gives objects around 100 m across. Set
//                it larger than the features you are mapping and those
//                features disappear inside bigger objects. Over narrow
//                mangrove fringes, small is safer than efficient.
//
//   compactness  how much the algorithm favours regular shapes over
//                following spectral boundaries. 0 lets objects take whatever
//                shape the imagery dictates, which is right when boundaries
//                are real and irregular, such as a coastline. Higher values
//                produce tidier, more square objects, which suits agricultural
//                fields and suits nothing on a delta.
//
//   connectivity 4 or 8. Eight allows diagonal connection and produces
//                objects that follow narrow diagonal features such as tidal
//                creeks. Four is stricter.
var seeds = ee.Algorithms.Image.Segmentation.seedGrid(10);

var snic = ee.Algorithms.Image.Segmentation.SNIC({
  image: segmentationBands,
  size: 10,
  compactness: 0,        // let the coastline decide the shapes
  connectivity: 8,
  neighborhoodSize: 64,  // must exceed size, or objects are cut at tile edges
  seeds: seeds
});

// SNIC returns one band per input band holding the object mean, plus a
// 'clusters' band holding a unique id per object.
var clusters = snic.select('clusters');

print('SNIC output bands:', snic.bandNames());

// ===========================================================================
// PART 3. Summarise the full stack per object
// ===========================================================================
// SNIC only averaged the four segmentation bands. The classifier should see
// object level statistics for every predictor, so reduce the whole stack over
// the cluster ids.
//
// reduceConnectedComponents does exactly this: for each connected group of
// pixels sharing a cluster id, compute a statistic and write it back to every
// pixel in that group. The output is still a raster, which keeps everything
// downstream identical to chapter “Classical Supervised Learning”.
var objectMeans = image2023
  .addBands(clusters)
  .reduceConnectedComponents({
    reducer: ee.Reducer.mean(),
    labelBand: 'clusters',
    maxSize: 256         // objects larger than this are left unreduced
  });

// Standard deviation within an object is a genuinely new predictor that pixel
// based classification cannot produce. A uniform plantation has low internal
// variance; a structurally complex natural stand has high variance, even when
// their means are identical. This is the same insight as the GLCM texture of
// chapter “Spatial Texture Extraction”, arriving by a different route.
var objectSD = image2023.select(['B8', 'NDVI'])
  .addBands(clusters)
  .reduceConnectedComponents({
    reducer: ee.Reducer.stdDev(),
    labelBand: 'clusters',
    maxSize: 256
  }).rename(['B8_sd', 'NDVI_sd']);

// Object size in pixels, which separates a large contiguous forest block from
// a scatter of small patches with the same spectral signature.
var objectSize = clusters.connectedPixelCount({maxSize: 256}).rename('object_size');

var objectStack = objectMeans.addBands(objectSD).addBands(objectSize).float();

print('Object level predictors:', objectStack.bandNames());

// ===========================================================================
// PART 4. Classify the objects
// ===========================================================================
// From here the workflow is identical to chapter “Classical Supervised Learning”. The only change is what
// the classifier is looking at: object statistics rather than raw pixels.
var withRandom = trainingPoints.randomColumn('random', 42);
var training = withRandom.filter(ee.Filter.lt('random', 0.7));
var validation = withRandom.filter(ee.Filter.gte('random', 0.7));

var trainingSamples = objectStack.sampleRegions({
  collection: training,
  properties: [CLASS_PROPERTY],
  scale: SCALE,
  tileScale: 16         // object stacks are memory hungry, start higher
});

var classifier = ee.Classifier.smileRandomForest(100).train({
  features: trainingSamples,
  classProperty: CLASS_PROPERTY,
  inputProperties: objectStack.bandNames()
});

var objectClassified = objectStack.classify(classifier).rename('classification');

// ===========================================================================
// PART 5. Did it help?
// ===========================================================================
// Object based classification is not automatically better and the honest
// answer varies by landscape. Score it the same way as the pixel version and
// compare like with like.
var validated = objectClassified.sampleRegions({
  collection: validation,
  properties: [CLASS_PROPERTY],
  scale: SCALE,
  tileScale: 8
});

var matrix = validated.errorMatrix(CLASS_PROPERTY, 'classification');
print('Object based confusion matrix:', matrix);
print('Object based overall accuracy:', matrix.accuracy());

// Expect the comparison to go one of two ways.
//
// Over landscapes with genuine discrete objects, agricultural fields,
// aquaculture ponds, plantation blocks, OBIA usually wins clearly and the
// output is far more usable cartographically.
//
// Over landscapes with gradational boundaries, the transition from mangrove
// to upland forest across an elevation gradient, OBIA can perform WORSE,
// because it forces a hard boundary where the ground has a gradient, and it
// commits every pixel in an object to a single wrong answer when the object
// straddles the transition.

// ===========================================================================
// PART 6. Vectorise for delivery
// ===========================================================================
// This is the practical argument for OBIA that has nothing to do with
// accuracy. Object boundaries vectorise into clean polygons that a planner
// can open in desktop GIS, edit, attribute and put in a report. A pixel based
// classification vectorises into tens of thousands of ragged squares.
var vectors = objectClassified.addBands(ee.Image.pixelArea().divide(10000))
  .reduceToVectors({
    geometry: aoi,
    scale: SCALE,
    geometryType: 'polygon',
    labelProperty: 'class',
    reducer: ee.Reducer.sum(),      // sums the area band per polygon
    maxPixels: 1e13,
    tileScale: 8
  });

// Apply a minimum mapping unit. This is the standard cartographic step and it
// should be stated in the metadata, because it changes area statistics.
var MMU_HECTARES = 0.5;
var cleaned = vectors.filter(ee.Filter.gte('sum', MMU_HECTARES));

print('Polygons before MMU:', vectors.size());
print('Polygons after MMU:', cleaned.size());

// ===========================================================================
// DISPLAY AND EXPORT
// ===========================================================================
Map.centerObject(aoi, 12);
Map.addLayer(image2023, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.3}, 'Composite');
Map.addLayer(clusters.randomVisualizer(), {}, 'SNIC objects', false);
Map.addLayer(objectClassified, {min: 0, max: 4, palette: lulcPalette}, 'Object based');
Map.addLayer(cleaned, {color: '#14a37f'}, 'Vector output', false);

Export.table.toDrive({
  collection: cleaned,
  description: 'lulc_objects_2023',
  fileFormat: 'SHP'
});

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Run SNIC at size 5, 10 and 25. Find the size at which a narrow mangrove
//    fringe stops being its own object and gets absorbed into the water.
// 2. Set compactness to 5 and compare the coastline. Explain why compactness
//    suits farmland and not deltas.
// 3. Compare object and pixel accuracy for each class separately, not just
//    overall. Which classes gained and which lost?
// 4. Raise the minimum mapping unit to 2 hectares and report how much mangrove
//    area disappeared. That number belongs in your metadata.
