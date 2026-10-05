//| title: How sensors scan
//| description: See a whisk broom's weak point in the archive: Landsat 7 before and after its scan line corrector failed on 31 May 2003, over the same path and row.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * PRINCIPLES P3 | A scanning mirror you can see in the data
 * ---------------------------------------------------------------------------
 * Landsat 7's ETM+ is a whisk broom: a mirror sweeps across track while the
 * satellite moves forward. A second small mirror, the scan line corrector
 * (SLC), straightened each sweep. It failed on 31 May 2003. Every Landsat 7
 * image since has wedge-shaped gaps. The drawings and the IFOV and dwell-time
 * numbers are in the Python tab.
 */

var area = ee.Geometry.Rectangle([107.35, -7.10, 107.95, -6.75], null, false);   // Bandung
var L7 = ee.ImageCollection('LANDSAT/LE07/C02/T1_L2').filterBounds(area)
  .filter(ee.Filter.lt('CLOUD_COVER', 30)).sort('CLOUD_COVER');

var before = ee.Image(L7.filterDate('2000-01-01', '2003-05-01').first());
var after = ee.Image(L7.filterDate('2015-01-01', '2016-12-31')
  .filter(ee.Filter.eq('WRS_PATH', before.get('WRS_PATH')))
  .filter(ee.Filter.eq('WRS_ROW', before.get('WRS_ROW'))).first());
print('Before', before.date(), 'After', after.date());

var VIS = {bands: ['SR_B3', 'SR_B2', 'SR_B1'], min: 7000, max: 16000};
Map.centerObject(area, 11);
Map.addLayer(before.clip(area), VIS, 'SLC on (before May 2003)');
Map.addLayer(after.clip(area), VIS, 'SLC off (2015-2016)');

// Share of pixels with data where both scenes cover the box.
var common = area.intersection(before.geometry(), 30).intersection(after.geometry(), 30);
function share(img) {
  return img.select('SR_B1').mask().gt(0).unmask(0)
    .reduceRegion(ee.Reducer.mean(), common, 30).values().get(0);
}
print('Valid share before', share(before), 'after', share(after));
