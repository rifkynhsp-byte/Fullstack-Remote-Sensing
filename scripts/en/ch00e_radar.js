//| title: Radar basics
//| description: Sentinel-1 ascending and descending over Rinjani to see foreshortening, layover and shadow flip sides; speckle against a multi-date mean; and backscatter by land cover around Jatiluhur.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * PRINCIPLES P5 | Reading a radar image
 * ---------------------------------------------------------------------------
 * Three experiments with Sentinel-1 GRD (C-band, VV and VH, in dB).
 * The geometry and resolution figures are computed in the Python tab.
 */

// 1. One volcano, two viewing directions.
var rinjani = ee.Geometry.Rectangle([116.25, -8.55, 116.65, -8.25], null, false);
var s1 = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(rinjani)
  .filterDate('2023-01-01', '2024-01-01')
  .filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'));
var asc = s1.filter(ee.Filter.eq('orbitProperties_pass', 'ASCENDING')).select('VV').mean();
var desc = s1.filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING')).select('VV').mean();
Map.centerObject(rinjani, 11);
Map.addLayer(asc.clip(rinjani), {min: -18, max: 2}, 'Ascending (looks east)');
Map.addLayer(desc.clip(rinjani), {min: -18, max: 2}, 'Descending (looks west)');

// 2. Speckle: one date against the mean of many (average in linear power).
var karawang = ee.Geometry.Rectangle([107.28, -6.33, 107.38, -6.26], null, false);
var s1k = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(karawang)
  .filterDate('2023-06-01', '2023-10-01').filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING')).select('VV');
var toLinear = function (i) { return ee.Image(10).pow(i.divide(10)); };
var many = s1k.map(toLinear).mean().log10().multiply(10);
Map.addLayer(ee.Image(s1k.first()).clip(karawang), {min: -20, max: 0}, 'One date', false);
Map.addLayer(many.clip(karawang), {min: -20, max: 0}, 'Mean of all dates', false);

// 3. Backscatter by land cover (Dynamic World), dry season 2023.
var box = ee.Geometry.Rectangle([107.20, -6.65, 107.50, -6.35], null, false);  // Jatiluhur
var db = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(box)
  .filterDate('2023-06-01', '2023-10-01').filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
  .select(['VV', 'VH']).map(toLinear).mean().log10().multiply(10);
var dw = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(box)
  .filterDate('2023-06-01', '2023-10-01').select('label').mode();
// Median VV and VH for water (0), trees (1), crops (4) and built (6).
print('Median backscatter by class (group 0 water, 1 trees, 4 crops, 6 built)',
  db.addBands(dw.rename('cls')).updateMask(dw.remap([0, 1, 4, 6], [1, 1, 1, 1], 0))
    .reduceRegion({reducer: ee.Reducer.median().forEach(['VV', 'VH'])
                     .group({groupField: 2, groupName: 'cls'}),
                   geometry: box, scale: 20, maxPixels: 1e9, tileScale: 4}));
