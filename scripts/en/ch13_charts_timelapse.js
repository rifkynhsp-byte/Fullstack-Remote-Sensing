//| title: A chart over time and a time-lapse
//| description: Ten years of NDVI at one Bandung point, and the new capital (IKN) being built, 2019 to 2024.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 13 | Two ways to show time: a line and a moving picture
 * ---------------------------------------------------------------------------
 * The first half comes from the GEE101 Bandung course: one point, every
 * Landsat 8 observation since 2013, one chart. The second half turns six
 * annual composites into an animated GIF of the Nusantara capital (IKN)
 * core zone in East Kalimantan, where forest and plantation became a city.
 */

// ---------------------------------------------------------------------------
// PART 1. NDVI through time at one point
// ---------------------------------------------------------------------------
var point = ee.Geometry.Point([107.6262, -6.9230]);   // Bandung

var addNdvi = function (image) {
  var qa = image.select('QA_PIXEL');
  var clear = qa.bitwiseAnd(1 << 3).eq(0).and(qa.bitwiseAnd(1 << 4).eq(0));
  var sr = image.select(['SR_B4', 'SR_B5']).multiply(0.0000275).add(-0.2);
  return sr.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI')
    .updateMask(clear).copyProperties(image, ['system:time_start']);
};

var ndviSeries = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
  .filterBounds(point)
  .filterDate('2013-04-01', '2025-01-01')
  .map(addNdvi);

print(ui.Chart.image.series({
  imageCollection: ndviSeries, region: point,
  reducer: ee.Reducer.first(), scale: 30
}).setOptions({title: 'NDVI over time, Bandung', vAxis: {title: 'NDVI'},
               series: {0: {color: 'green'}}, pointSize: 2, lineWidth: 0}));

// ---------------------------------------------------------------------------
// PART 2. A time-lapse: one clear composite per year, then an animation
// ---------------------------------------------------------------------------
var ikn = ee.Geometry.Rectangle([116.66, -1.01, 116.75, -0.93]);

var yearlyFrame = function (year) {
  var composite = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(ikn)
    .filterDate(ee.Date.fromYMD(year, 5, 1), ee.Date.fromYMD(year, 10, 31))
    .map(function (image) {
      var scl = image.select('SCL');
      return image.updateMask(scl.neq(3).and(scl.neq(8)).and(scl.neq(9)).and(scl.neq(10)));
    })
    .median();
  return composite.visualize({bands: ['B4', 'B3', 'B2'], min: 200, max: 2200, gamma: 1.2})
    .set('year', year);
};
var frames = ee.ImageCollection(ee.List.sequence(2019, 2024).map(yearlyFrame));

// If this thumbnail reports "User memory limit exceeded", the six medians are
// too much for one request. Lower dimensions to 300, or shrink the rectangle;
// the Python tab shows the other way out: one request per frame.
print(ui.Thumbnail({image: frames, params: {region: ikn, dimensions: 400,
                                            framesPerSecond: 1, crs: 'EPSG:3857'}}));
Map.centerObject(ikn, 13);
Map.addLayer(ee.Image(frames.toList(6).get(5)), {}, '2024 composite');

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Swap reducer first() for mean() over a 300 m buffer around the point.
//    What does averaging do to the seasonal signal?
// 2. Build the frames from the dry season only (July to September) and from
//    the wet season only. Which gives the steadier animation, and why?
