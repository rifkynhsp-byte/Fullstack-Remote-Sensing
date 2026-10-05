//| title: Supervised flood mapping with Sentinel-1
//| description: The author's GEE101 flood script for the Jakarta New Year flood of 2020, with the band-name bug fixed and accuracy measured on held-out polygons.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 39 | Jakarta, 1 January 2020
 * ---------------------------------------------------------------------------
 * Labels: data/jakarta_flood2020_training.geojson in the book repository
 * (50 polygons, 10 per class, drawn by the author). It is published as a
 * public Earth Engine table, so the script runs as is; to use your own
 * polygons, upload them (Assets > New > Shape files / GeoJSON) and change the path.
 *   landcover 1 permanent water, 2 vegetation, 3 flooded vegetation,
 *             4 urban, 5 flooded urban;  polygon 0-9 within each class
 */
var labels = ee.FeatureCollection('projects/shaped-producer-482312-m0/assets/fullstack_rs/jakarta_flood/jakarta_flood2020_training');
var roi = ee.Geometry.Rectangle([106.674, -6.329, 106.995, -6.121], null, false);

var s1 = ee.ImageCollection('COPERNICUS/S1_GRD')
  .filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.eq('orbitProperties_pass', 'ASCENDING'))
  .filter(ee.Filter.eq('resolution_meters', 10))
  .filterBounds(roi).select(['VV', 'VH']);
var before = s1.filterDate('2019-12-20', '2019-12-31').mosaic().focalMean(50, 'circle', 'meters');
var after = s1.filterDate('2020-01-01', '2020-01-10').mosaic().focalMean(50, 'circle', 'meters');

// The bug in the original: cat() renames the second image's bands to VV_1, VH_1,
// so select('VV') takes the BEFORE image only.
print('Band names after cat():', ee.Image.cat(before, after).bandNames());

// The fix: name every input and add the change as a feature.
var stack = ee.Image.cat(
  before.rename(['VV_before', 'VH_before']),
  after.rename(['VV_after', 'VH_after']),
  after.subtract(before).rename(['VV_change', 'VH_change']));
var bands = stack.bandNames();

// Hold out 3 polygons per class: pixels of one polygon never train and test.
var train = stack.sampleRegions({collection: labels.filter(ee.Filter.lt('polygon', 7)),
                                 properties: ['landcover'], scale: 30, tileScale: 4});
var test = stack.sampleRegions({collection: labels.filter(ee.Filter.gte('polygon', 7)),
                                properties: ['landcover'], scale: 30, tileScale: 4});
var rf = ee.Classifier.smileRandomForest({numberOfTrees: 50, seed: 1})
  .train(train, 'landcover', bands);
var em = test.classify(rf).errorMatrix('landcover', 'classification');
print('Training accuracy (optimistic)', rf.confusionMatrix().accuracy());
print('Held-out accuracy', em.accuracy(), 'kappa', em.kappa(), em);

var classified = stack.classify(rf).reduceNeighborhood(ee.Reducer.mode(), ee.Kernel.circle(3));
Map.centerObject(roi, 12);
Map.addLayer(ee.Image.cat(before.select('VV'), after.select('VV'), after.select('VV')).clip(roi),
             {min: -20, max: 0}, 'Change: before red, after cyan');
Map.addLayer(classified.clip(roi), {min: 1, max: 5,
  palette: ['106fd0', '35ff1c', '12ffc7', 'c20000', 'ffdb8d']}, 'Flood classes');
