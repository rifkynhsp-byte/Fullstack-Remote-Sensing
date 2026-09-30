//| title: Trends and spatial autocorrelation
//| description: A per-pixel Sen's slope map of dry-season land surface temperature over West Java, 2003-2024.

/**
 * CHAPTER 30 | A robust trend for every pixel
 * ---------------------------------------------------------------------------
 * ee.Reducer.sensSlope() fits the median of all pairwise slopes, per pixel,
 * in one call; ee.Reducer.kendallsCorrelation() gives the Mann-Kendall
 * statistic. The Python tab adds a bootstrap interval for one pixel and a
 * semivariogram, which are awkward in the Code Editor.
 */

var westJava = ee.FeatureCollection('FAO/GAUL/2025/level2')
  .filter(ee.Filter.eq('GAUL1_NAME', 'Jawa Barat'));
var modis = ee.ImageCollection('MODIS/061/MOD11A2').select('LST_Day_1km');

var annual = ee.ImageCollection(ee.List.sequence(2003, 2024).map(function (y) {
  var img = modis.filterDate(ee.Date.fromYMD(y, 6, 1), ee.Date.fromYMD(y, 11, 1)).mean()
    .multiply(0.02).subtract(273.15).rename('lst');
  // sensSlope expects two bands: the x variable first, then y.
  return ee.Image.constant(y).float().rename('year').addBands(img).set('year', y);
}));

var trend = annual.reduce(ee.Reducer.sensSlope()).select('slope').multiply(10)
  .rename('trend').clip(westJava);
var tau = annual.reduce(ee.Reducer.kendallsCorrelation(2)).select('lst_tau').clip(westJava);

Map.centerObject(westJava, 8);
Map.addLayer(trend, {min: -1.5, max: 1.5, palette: ['2166ac', '92c5de', 'f7f7f7',
  'f4a582', 'b2182b']}, "Sen's slope, °C per decade");
Map.addLayer(tau, {min: -0.6, max: 0.6, palette: ['2166ac', 'f7f7f7', 'b2182b']},
  "Kendall's tau", false);

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Repeat with MODIS Aqua (MYD11A2). Where do Terra and Aqua disagree, and
//    what does that suggest about orbit drift?
// 2. Mask pixels whose Kendall's tau is below 0.3 in absolute value.
