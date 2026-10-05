//| title: Smoke from space: the 2019 haze as a time-lapse
//| description: Two animations of the 2019 Sumatra and Kalimantan haze (MODIS true colour, and Sentinel-5P carbon monoxide with FIRMS fires), a daily CO chart for six cities, and the peak-fortnight anomaly against 2020.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 71 | Smoke from space: the 2019 haze, frame by frame
 * ---------------------------------------------------------------------------
 * The same season seen twice: as the eye would see it (MODIS true colour)
 * and as chemistry sees it (Sentinel-5P carbon monoxide, which passes through
 * cloud), with every fire FIRMS detected. Then one chart of daily CO over six
 * cities, and a map of how unusual the peak was against 2020, a wet year.
 */

var box = ee.Geometry.Rectangle([97, -5, 118, 7.5], null, false);   // Sumatra, Malaya, Borneo
Map.centerObject(box, 5);

// ---------------------------------------------------------------------------
// PART 1. Daily images
// ---------------------------------------------------------------------------
// Sentinel-5P L3 in Earth Engine is one image per orbit; a day is the mean of ~14 strips.
var coDay = function (d) {
  d = ee.Date(d);
  return ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_CO').filterDate(d, d.advance(1, 'day'))
    .select('CO_column_number_density').mean().multiply(1000).rename('co');   // mmol/m2
};
var firesDay = function (d) {
  d = ee.Date(d);
  return ee.ImageCollection('FIRMS').filterDate(d, d.advance(1, 'day')).select('T21').max();
};
var trueColourDay = function (d) {
  d = ee.Date(d);                       // Terra (morning) + Aqua (afternoon) fill each other's gaps
  return ee.ImageCollection('MODIS/061/MOD09GA').merge(ee.ImageCollection('MODIS/061/MYD09GA'))
    .filterDate(d, d.advance(1, 'day')).select(['sur_refl_b01', 'sur_refl_b04', 'sur_refl_b03'])
    .mosaic().visualize({min: 0, max: 3000, gamma: 1.4});
};

// ---------------------------------------------------------------------------
// PART 2. Two time-lapses, every fourth day, August to October 2019
// ---------------------------------------------------------------------------
var start = ee.Date('2019-08-01');
var days = ee.List.sequence(0, 90, 4).map(function (n) { return start.advance(n, 'day'); });

var backdrop = ee.ImageCollection('MODIS/061/MOD09A1').filterDate('2019-06-01', '2019-10-01')
  .select(['sur_refl_b01', 'sur_refl_b04', 'sur_refl_b03']).median()
  .visualize({min: 0, max: 3000, gamma: 1.4}).multiply(0.75).uint8();

var chemistry = function (d) {
  d = ee.Date(d);                       // 3-day mean: one day has gaps under thick cloud
  var co = ee.ImageCollection([coDay(d.advance(-1, 'day')), coDay(d), coDay(d.advance(1, 'day'))]).mean();
  var coVis = co.updateMask(co.gt(40)).visualize({min: 40, max: 150, opacity: 0.8,
    palette: ['#fff7bc', '#fec44f', '#ec7014', '#993404', '#4d1a02']});
  var fireVis = firesDay(d).focalMax(2500, 'circle', 'meters').mask().selfMask().visualize({palette: ['#ff0000']});
  return backdrop.blend(coVis).blend(fireVis);
};

var video = {region: box, dimensions: 520, framesPerSecond: 3, crs: 'EPSG:3857'};
print('What the eye sees: MODIS true colour');
print(ui.Thumbnail(ee.ImageCollection(days.map(trueColourDay)), video));
print('What the chemistry sees: Sentinel-5P CO (orange) and FIRMS fires (red)');
print(ui.Thumbnail(ee.ImageCollection(days.map(chemistry)), video));
// For a GIF file: ee.ImageCollection(days.map(chemistry)).getVideoThumbURL(video)

// ---------------------------------------------------------------------------
// PART 3. Daily CO over six cities, July to November 2019
// ---------------------------------------------------------------------------
var cities = ee.FeatureCollection([
  ee.Feature(ee.Geometry.Point([101.45, 0.51]).buffer(30000), {name: 'Pekanbaru'}),
  ee.Feature(ee.Geometry.Point([113.92, -2.21]).buffer(30000), {name: 'Palangka Raya'}),
  ee.Feature(ee.Geometry.Point([109.33, -0.03]).buffer(30000), {name: 'Pontianak'}),
  ee.Feature(ee.Geometry.Point([103.82, 1.35]).buffer(30000), {name: 'Singapore'}),
  ee.Feature(ee.Geometry.Point([110.35, 1.55]).buffer(30000), {name: 'Kuching'}),
  ee.Feature(ee.Geometry.Point([101.69, 3.14]).buffer(30000), {name: 'Kuala Lumpur'})]);

var daily = ee.ImageCollection(ee.List.sequence(0, 152).map(function (n) {
  var d = ee.Date('2019-07-01').advance(n, 'day');
  return coDay(d).set('system:time_start', d.millis());
}));
print(ui.Chart.image.seriesByRegion({imageCollection: daily, regions: cities, reducer: ee.Reducer.mean(),
  band: 'co', scale: 5000, seriesProperty: 'name'})
  .setOptions({title: 'Sentinel-5P CO over six cities, 2019 (mmol/m2)', lineWidth: 1, pointSize: 0}));

// ---------------------------------------------------------------------------
// PART 4. The peak fortnight, 2019 minus 2020
// ---------------------------------------------------------------------------
var peak = function (y) {
  return ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_CO').filterDate(y + '-09-08', y + '-09-23')
    .select('CO_column_number_density').mean().multiply(1000);
};
Map.addLayer(peak(2019).subtract(peak(2020)).clip(box),
  {min: -10, max: 80, palette: ['#2166ac', '#f7f7f7', '#fee391', '#fe9929', '#cc4c02', '#662506']},
  'CO 8-22 Sep: 2019 minus 2020');
