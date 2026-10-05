//| title: Platforms and orbits
//| description: Real scene footprints along one Landsat path, and the local time of every pass over one city, straight from the archive metadata.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * PRINCIPLES P2 | Orbits you can read from the archive
 * ---------------------------------------------------------------------------
 * Every image in Earth Engine carries its footprint and its acquisition time.
 * That is enough to see the orbit: tilted scenes along a path, and passes that
 * come back at the same local time day after day (sun-synchronous).
 * The orbit physics figures (Kepler, ground track) are in the Python tab.
 */

// 1. Footprints of one Landsat 8 path across Java.
var java = ee.Geometry.Rectangle([104.5, -9.5, 116.5, -4.5], null, false);
var path120 = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2').filterBounds(java)
  .filterDate('2024-08-01', '2024-08-31').filter(ee.Filter.eq('WRS_PATH', 120));
var frames = ee.FeatureCollection(path120.map(function (im) {
  return ee.Feature(im.geometry(), {row: im.get('WRS_ROW'),
                                    time: im.date().format('YYYY-MM-dd HH:mm')});
}));
print('Scenes on path 120', frames);
Map.centerObject(java, 6);
Map.addLayer(ee.Image().byte().paint(frames, 1, 2), {palette: ['c0392b']}, 'Footprints');

// 2. Local solar time of every 2023 pass over Bandung.
var bandung = ee.Geometry.Point(107.61, -6.91);
function passes(col, name) {
  return col.filterBounds(bandung).filterDate('2023-01-01', '2024-01-01')
    .map(function (im) {
      var utcHour = ee.Number(im.date().getFraction('day')).multiply(24);
      var solar = utcHour.add(107.61 / 15).mod(24);            // mean local solar time
      return ee.Feature(null, {sensor: name, date: im.date().millis(), hour: solar});
    });
}
var s1 = ee.ImageCollection('COPERNICUS/S1_GRD').filter(ee.Filter.eq('instrumentMode', 'IW'));
var all = passes(ee.ImageCollection('LANDSAT/LC08/C02/T1_L2'), 'Landsat 8')
  .merge(passes(ee.ImageCollection('COPERNICUS/S2_HARMONIZED'), 'Sentinel-2'))
  .merge(passes(s1.filter(ee.Filter.eq('orbitProperties_pass', 'ASCENDING')), 'S1 ascending'))
  .merge(passes(s1.filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING')), 'S1 descending'));
print(ui.Chart.feature.groups(all, 'date', 'hour', 'sensor')
  .setChartType('ScatterChart')
  .setOptions({title: 'Local solar time of each pass over Bandung, 2023',
               vAxis: {title: 'hour', viewWindow: {min: 0, max: 24}},
               hAxis: {format: 'MMM'}, pointSize: 3}));
