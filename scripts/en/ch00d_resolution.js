//| title: The four resolutions
//| description: One harbour at 250, 30 and 10 m, the data type behind each band, and a count of every image over one city since 1984.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * PRINCIPLES P4 | Spatial, spectral, radiometric, temporal
 * ---------------------------------------------------------------------------
 * Toggle the three layers to see spatial resolution. The printed band types
 * show what each archive stores. The chart counts images per year: temporal
 * resolution. (The band-width figure and the bit-depth demonstration are in
 * the Python tab.)
 */

var port = ee.Geometry.Rectangle([110.36, -6.99, 110.46, -6.92], null, false);   // Semarang
var date = ['2023-06-01', '2023-10-01'];

var modis = ee.ImageCollection('MODIS/061/MOD09GQ').filterDate(date[0], date[1]).median();
var l8 = ee.Image(ee.ImageCollection('LANDSAT/LC08/C02/T1_L2').filterBounds(port)
  .filterDate(date[0], date[1]).sort('CLOUD_COVER').first());
var s2 = ee.Image(ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(port)
  .filterDate(date[0], date[1]).sort('CLOUDY_PIXEL_PERCENTAGE').first());

Map.centerObject(port, 13);
Map.addLayer(modis.clip(port), {bands: ['sur_refl_b02', 'sur_refl_b01', 'sur_refl_b01'],
                                min: 0, max: 4000}, 'MODIS 250 m');
Map.addLayer(l8.clip(port), {bands: ['SR_B5', 'SR_B4', 'SR_B3'], min: 7500, max: 25000},
             'Landsat 8 30 m');
Map.addLayer(s2.clip(port), {bands: ['B8', 'B4', 'B3'], min: 0, max: 4000}, 'Sentinel-2 10 m');

// What is stored per pixel: the data type of each archive band.
print('Landsat 8 SR band types', l8.select(['SR_B4', 'SR_B5']).bandTypes());
print('Sentinel-2 band types', s2.select(['B4', 'B8']).bandTypes());

// Temporal resolution: images per year covering Bandung.
var bandung = ee.Geometry.Point(107.61, -6.91);
function perYear(id, name) {
  return ee.ImageCollection(id).filterBounds(bandung).filterDate('1984-01-01', '2025-01-01')
    .map(function (im) { return ee.Feature(null, {sensor: name, year: im.date().get('year')}); });
}
var all = perYear('LANDSAT/LT05/C02/T1_L2', 'Landsat 5')
  .merge(perYear('LANDSAT/LE07/C02/T1_L2', 'Landsat 7'))
  .merge(perYear('LANDSAT/LC08/C02/T1_L2', 'Landsat 8'))
  .merge(perYear('LANDSAT/LC09/C02/T1_L2', 'Landsat 9'))
  .merge(perYear('COPERNICUS/S2_HARMONIZED', 'Sentinel-2'));
print(ui.Chart.feature.histogram(all, 'year', 41)
  .setOptions({title: 'Images covering Bandung per year, all sensors', legend: 'none'}));
