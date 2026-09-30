//| title: Clusters before classes: k-means over the Bandung basin
//| description: Unsupervised grouping of a cloud-masked Sentinel-2 composite, then a check of what the clusters actually are.

/**
 * CHAPTER 16 | Before you draw a single training polygon
 * ---------------------------------------------------------------------------
 * From the GEE101 course. k-means sorts pixels into k groups by spectral
 * similarity alone: no labels, no training polygons. It is the quickest look
 * at how a landscape divides itself, and a lesson in why clusters are not
 * classes. The last step cross-tabulates clusters against ESA WorldCover.
 */

var region = ee.Geometry.Rectangle([107.394, -7.070, 107.801, -6.808]);   // Bandung basin

// Cloud mask from the separate s2cloudless probability collection, joined by
// scene ID. This is a better mask than SCL over bright urban roofs.
var MAX_CLOUD_PROBABILITY = 35;
var criteria = ee.Filter.and(ee.Filter.bounds(region),
                             ee.Filter.date('2024-01-01', '2025-03-01'));
var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filter(criteria);
var clouds = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY').filter(criteria);
var joined = ee.ImageCollection(ee.Join.saveFirst('cloud_mask').apply({
  primary: s2, secondary: clouds,
  condition: ee.Filter.equals({leftField: 'system:index', rightField: 'system:index'})
}));
var composite = joined.map(function (img) {
  var prob = ee.Image(img.get('cloud_mask')).select('probability');
  return img.updateMask(prob.lt(MAX_CLOUD_PROBABILITY));
}).median().select('B.*').clip(region);

// k-means: sample, train, assign every pixel
var K = 10;
var training = composite.sample({region: region, scale: 300, numPixels: 5000, seed: 1});
var clusterer = ee.Clusterer.wekaKMeans({nClusters: K, seed: 1}).train(training);
var clusters = composite.cluster(clusterer).clip(region);

Map.centerObject(region, 11);
Map.addLayer(composite, {bands: ['B4', 'B3', 'B2'], min: 0, max: 3000}, 'Sentinel-2');
Map.addLayer(clusters.randomVisualizer(), {}, 'k-means, ' + K + ' clusters');

// What ARE the clusters? Cross-tabulate against WorldCover.
var worldCover = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map');
var crosstab = clusters.addBands(worldCover).stratifiedSample({
  numPoints: 100, classBand: 'cluster', region: region, scale: 60, seed: 2,
  tileScale: 8   // spread the work: a year of joined scenes is memory hungry
});
print('Cluster against WorldCover class (counts)',
  crosstab.reduceColumns(ee.Reducer.frequencyHistogram().group({groupField: 0,
    groupName: 'cluster'}), ['cluster', 'Map']));

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Run with K = 4 and K = 20. Which K gives clusters you could name?
// 2. Find a cluster that mixes two WorldCover classes. What do those two
//    surfaces have in common spectrally?
