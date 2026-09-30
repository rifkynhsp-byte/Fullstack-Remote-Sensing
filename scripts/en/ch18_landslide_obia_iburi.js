//| title: Pixels or objects? Earthquake landslides at Iburi, Hokkaido
//| description: Before/after Sentinel-2, a pixel rule and an object rule, both scored against a landslide inventory.

/**
 * CHAPTER 18 | The 6 September 2018 Iburi earthquake triggered thousands of
 * shallow landslides on forested hills around Atsuma. Seen from space they
 * are bright scars where canopy was. This is the GEE101 landslide exercise,
 * rebuilt: change in indices, a slope rule, then the same logic applied to
 * SNIC objects instead of pixels, and both checked against an inventory.
 */

var window = ee.Geometry.Rectangle([141.93, 42.70, 142.05, 42.80]);   // Atsuma hills
// Landslide inventory: CAS Landslide Dataset, Hokkaido Iburi-Tobu subset
// (Xu et al. 2024, Scientific Data 11:12, doi:10.1038/s41597-023-02847-z),
// prepared as polygons for the GEE101 course.
var inventory = ee.FeatureCollection('users/rifkynauvalhsp/IburiLandslideInventory/trainingset');

// ---------------------------------------------------------------------------
// STEP 1. Before and after, SAME SEASON. The first version of this exercise
// compared summer 2016 with autumn 2018; Hokkaido's forest browns in autumn,
// and whole hillsides passed the landslide rule. Compare September-October
// with September-October. Level-1C, because surface reflectance coverage is
// patchy here before 2019. QA60 is still populated in these years (Chapter 9
// explains why that changes after 2022).
// ---------------------------------------------------------------------------
var maskAndIndex = function (image) {
  var qa = image.select('QA60');
  var clear = qa.bitwiseAnd(1 << 10).eq(0).and(qa.bitwiseAnd(1 << 11).eq(0));
  var s = image.updateMask(clear).divide(10000);
  return s.addBands([
    s.normalizedDifference(['B8', 'B4']).rename('ndvi'),
    s.normalizedDifference(['B3', 'B4']).rename('grvi'),
    s.normalizedDifference(['B2', 'B4']).rename('ndbrbi')]);
};
var s2 = ee.ImageCollection('COPERNICUS/S2_HARMONIZED').filterBounds(window);
var pre = s2.filterDate('2017-09-01', '2017-10-31')
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).map(maskAndIndex).median();
var post = s2.filterDate('2018-09-07', '2018-10-31')
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).map(maskAndIndex).median();
var change = post.select(['ndvi', 'grvi', 'ndbrbi'])
  .subtract(pre.select(['ndvi', 'grvi', 'ndbrbi'])).rename(['dNDVI', 'dGRVI', 'dNDBRBI']);

var aw3d = ee.ImageCollection('JAXA/ALOS/AW3D30/V4_1');
var slope = ee.Terrain.slope(aw3d.select('DSM').filterBounds(window).mosaic()
  .setDefaultProjection(aw3d.first().projection())).rename('slope');

// ---------------------------------------------------------------------------
// STEP 2. The pixel rule: canopy lost, bare soil exposed, on a slope
// ---------------------------------------------------------------------------
var pixelRule = change.select('dNDVI').lt(-0.3)
  .and(change.select('dGRVI').lt(-0.05))
  .and(slope.gt(8)).rename('landslide');

// STEP 2b. Normalise. Thin cloud, haze and sun angle shift the WHOLE scene:
// the median dNDVI across this window is about -0.3, so the fixed rule above
// catches healthy forest. Subtract the scene-wide median and threshold the
// change relative to the landscape.
var shift = ee.Number(change.select('dNDVI').reduceRegion({
  reducer: ee.Reducer.median(), geometry: window, scale: 30, maxPixels: 1e9}).get('dNDVI'));
var relative = change.select('dNDVI').subtract(shift).rename('dNDVI_rel');
var relativeRule = relative.lt(-0.2).and(slope.gt(8)).rename('landslide');

// ---------------------------------------------------------------------------
// STEP 3. The object rule: segment first, decide per object
// ---------------------------------------------------------------------------
var snic = ee.Algorithms.Image.Segmentation.SNIC({
  image: post.select(['B4', 'B8']).addBands(relative),
  size: 8, compactness: 1, connectivity: 8, neighborhoodSize: 64,
  seeds: ee.Algorithms.Image.Segmentation.seedGrid(8)
});
var objectMeans = relative.addBands(slope)
  .addBands(snic.select('clusters'))
  .reduceConnectedComponents({reducer: ee.Reducer.mean(), labelBand: 'clusters',
                              maxSize: 256});
var objectRule = objectMeans.select('dNDVI_rel').lt(-0.2)
  .and(objectMeans.select('slope').gt(8)).rename('landslide');

// ---------------------------------------------------------------------------
// STEP 4. Score both against the inventory, as areas
// ---------------------------------------------------------------------------
var truth = ee.Image(0).paint(inventory, 1).rename('truth').clip(window);
var score = function (detected, label) {
  var d = detected.unmask(0);
  var km2 = function (img) {
    return ee.Number(img.multiply(ee.Image.pixelArea()).divide(1e6).reduceRegion({
      reducer: ee.Reducer.sum(), geometry: window, scale: 10, maxPixels: 1e10,
      tileScale: 4}).values().get(0));
  };
  var tp = km2(d.and(truth)), fp = km2(d.and(truth.not())), fn = km2(d.not().and(truth));
  var precision = tp.divide(tp.add(fp)), recall = tp.divide(tp.add(fn));
  return ee.Feature(null, {method: label, detected_km2: tp.add(fp), inventory_km2: tp.add(fn),
    precision: precision, recall: recall,
    f1: precision.multiply(recall).multiply(2).divide(precision.add(recall))});
};
print('Pixel rule against object rule', ee.FeatureCollection([
  score(pixelRule, 'pixel rule, fixed threshold'),
  score(relativeRule, 'pixel rule, normalised'),
  score(objectRule, 'object rule (SNIC), normalised')]));

Map.centerObject(window, 13);
Map.addLayer(pre, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.25}, 'Before, autumn 2017');
Map.addLayer(post, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.25}, 'After, 2018');
Map.addLayer(objectRule.selfMask(), {palette: ['#d7301f']}, 'Object rule', false);
Map.addLayer(ee.Image().byte().paint(inventory, 1, 1), {palette: ['#ffff00']}, 'Inventory');

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Move the dNDVI threshold from -0.3 to -0.2 and -0.4. Plot precision
//    against recall. Which point would you publish, and why?
// 2. Raise the SNIC size to 16. What happens to small scars?
