//| title: Radar water through the seasons, middle Mahakam
//| description: Sentinel-1 VV, speckle filtered and thresholded, 2017 to 2024: water frequency and flooded area over time.

/**
 * CHAPTER 10 | The sensor that sees through the wet season
 * ---------------------------------------------------------------------------
 * From the GEE101 course. Calm water reflects radar away from the satellite
 * and shows up dark in VV. Threshold every Sentinel-1 scene, and the stack
 * becomes a record of when and where the Mahakam floodplain went under,
 * through the cloudy months that optical sensors miss.
 *
 * One change from the original: a single orbit direction. The original mixed
 * ascending and descending passes, which adds a geometric wobble to the
 * series that has nothing to do with water (see Common failure above).
 */

var roi = ee.Geometry.Polygon([[[115.988, -0.083], [117.020, -0.203],
                                [117.285, 0.919], [116.269, 1.114]]]);

var s1 = ee.ImageCollection('COPERNICUS/S1_GRD')
  .filterBounds(roi)
  .filterDate('2017-01-01', '2025-01-01')
  .filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
  .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'))
  .select('VV');

// Speckle: a 100 m focal median, then a fixed threshold. -13 dB is from the
// GEE101 exercise; Exercise 1 asks you to test it.
var THRESHOLD = -13;
var water = s1.map(function (img) {
  var smooth = img.focal_median(100, 'circle', 'meters');
  return smooth.lt(THRESHOLD).rename('water')
    .copyProperties(img, ['system:time_start']);
});

// How often was each pixel water? 0 = never, 1 = every pass.
var frequency = water.mean().clip(roi);
Map.centerObject(roi, 9);
Map.addLayer(frequency, {min: 0, max: 1,
  palette: ['#ffffff', '#c6dbef', '#6baed6', '#2171b5', '#08306b']}, 'Water frequency');

// Flooded area per month, from the monthly maximum extent. Ninety-six
// monthly sums in one request can fail with "Too many concurrent
// aggregations"; this version asks for the last four years only (48 months)
// at 200 m. The Python tab fetches all eight years, one year per request.
var months = ee.List.sequence(48, 95).map(function (i) {
  var start = ee.Date('2017-01-01').advance(i, 'month');
  var m = water.filterDate(start, start.advance(1, 'month'));
  var km2 = m.max().multiply(ee.Image.pixelArea()).divide(1e6).reduceRegion({
    reducer: ee.Reducer.sum(), geometry: roi, scale: 200, maxPixels: 1e10,
    tileScale: 4}).get('water');
  return ee.Feature(null, {month: start.format('YYYY-MM'), water_km2: km2,
                           passes: m.size()});
});
var monthly = ee.FeatureCollection(months).filter(ee.Filter.gt('passes', 0));
print(ui.Chart.feature.byFeature(monthly, 'month', ['water_km2'])
  .setOptions({title: 'Water extent per month, middle Mahakam',
               vAxis: {title: 'km²'}, lineWidth: 1, pointSize: 2}));

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Plot a histogram of filtered VV over the lakes in one wet-season scene.
//    Is -13 dB in the valley between water and land? Chapter 12's Otsu idea
//    would pick the threshold for you.
// 2. Switch to ASCENDING passes. Does the monthly series agree?
