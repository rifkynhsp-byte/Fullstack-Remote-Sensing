//| title: Energy, waves and the atmosphere
//| description: Measure the atmosphere yourself: the same Sentinel-2 overpass over Jakarta before (Level-1C) and after (Level-2A) atmospheric correction, band by band.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * PRINCIPLES P1 | What the atmosphere does to a satellite measurement
 * ---------------------------------------------------------------------------
 * Level-1C is top-of-atmosphere reflectance: what reached the sensor.
 * Level-2A is surface reflectance: an estimate of what left the ground.
 * The difference, band by band, is the atmosphere. (The Planck curves and
 * the other physics figures of this chapter are in the Python tab.)
 */

var site = ee.Geometry.Rectangle([106.81, -6.30, 107.05, -6.05], null, false);   // Jakarta

// One clear overpass on one tile, so both levels show exactly the same pixels.
var sr = ee.Image(ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(site).filterDate('2023-05-01', '2024-11-01')
  .filter(ee.Filter.eq('MGRS_TILE', '48MYU'))
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 5))
  .sort('CLOUDY_PIXEL_PERCENTAGE').first());
var toa = ee.Image(ee.ImageCollection('COPERNICUS/S2_HARMONIZED')
  .filter(ee.Filter.eq('system:index', sr.get('system:index'))).first());
print('Scene', sr.get('system:index'));

var TRUE = {bands: ['B4', 'B3', 'B2'], min: 0, max: 2500, gamma: 1.1};
Map.centerObject(site, 12);
Map.addLayer(toa.clip(site), TRUE, 'Top of atmosphere (L1C)');
Map.addLayer(sr.clip(site), TRUE, 'Surface (L2A)');

// Band-by-band mean over the box, and the difference.
var BANDS = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B11', 'B12'];
var a = toa.select(BANDS).reduceRegion(ee.Reducer.mean(), site, 60);
var b = sr.select(BANDS).reduceRegion(ee.Reducer.mean(), site, 60);
var rows = BANDS.map(function (band) {
  var t = ee.Number(a.get(band)).divide(1e4), s = ee.Number(b.get(band)).divide(1e4);
  return ee.Feature(null, {band: band, toa: t, surface: s, added: t.subtract(s)});
});
var table = ee.FeatureCollection(rows);
print(ui.Chart.feature.byFeature(table, 'band', ['toa', 'surface'])
  .setOptions({title: 'Same pixels, two reflectances', vAxis: {title: 'reflectance'},
               pointSize: 4}));
print(ui.Chart.feature.byFeature(table, 'band', ['added'])
  .setChartType('ColumnChart')
  .setOptions({title: 'Top of atmosphere minus surface', legend: 'none'}));
