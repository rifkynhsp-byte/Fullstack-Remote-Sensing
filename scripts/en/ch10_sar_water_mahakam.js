//| title: Radar water through the seasons, middle Mahakam
//| description: Sentinel-1 VV, speckle filtered and thresholded, 2017 to 2024: water frequency and flooded area over time.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

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

// Flooded area per month, from the monthly maximum extent. Asking for one
// sum per month launches one aggregation per month, and Earth Engine refuses
// with "Too many concurrent aggregations". The trick: stack every month as a
// band of ONE image and sum them all in a single reduceRegion. Same numbers,
// one aggregation, all eight years.
var starts = ee.List.sequence(0, 95).map(function (i) { return ee.Date('2017-01-01').advance(i, 'month'); });
var monthly = ee.ImageCollection(starts.map(function (d) {
  d = ee.Date(d);
  var m = water.filterDate(d, d.advance(1, 'month'));
  return m.max().unmask(0).rename('water').set('month', d.format('YYYY-MM'), 'passes', m.size());
})).filter(ee.Filter.gt('passes', 0));
var stack = monthly.toBands().multiply(ee.Image.pixelArea()).divide(1e6);
var sums = stack.reduceRegion({reducer: ee.Reducer.sum(), geometry: roi, scale: 200, maxPixels: 1e10, tileScale: 4});
var labels = monthly.aggregate_array('month');
var monthlyKm2 = ee.FeatureCollection(ee.List.sequence(0, labels.size().subtract(1)).map(function (i) {
  return ee.Feature(null, {month: labels.get(i), water_km2: sums.values().get(i)});
}));
print(ui.Chart.feature.byFeature(monthlyKm2, 'month', ['water_km2'])
  .setOptions({title: 'Water extent per month, middle Mahakam',
               vAxis: {title: 'km²'}, lineWidth: 1, pointSize: 2}));

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Plot a histogram of filtered VV over the lakes in one wet-season scene.
//    Is -13 dB in the valley between water and land? chapter “Band Math and Spectral Indices”'s Otsu idea
//    would pick the threshold for you.
// 2. Switch to ASCENDING passes. Does the monthly series agree?
