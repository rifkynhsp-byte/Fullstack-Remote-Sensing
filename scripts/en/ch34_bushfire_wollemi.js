//| title: A bushfire from orbit: dryness, progression and burn severity
//| description: The 2019-20 Black Summer fires in the Wollemi and Blue Mountains, NSW: fuel dryness, fire progression and dNBR severity.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 34 | Fire and bushfire
 * ---------------------------------------------------------------------------
 * The author's bushfire monitors (NSW Bushfire Monitor, the Waterfall and
 * Central Coast explorers) answer three questions for any fire:
 *   1. How dry was the fuel before it burned?   MODIS NDMI anomaly
 *   2. How did the fire spread?                  MODIS burned-area dates
 *   3. How badly did it burn?                    Sentinel-2 dNBR, USGS classes
 */

var aoi = ee.Geometry.Rectangle([149.8, -33.8, 151.3, -32.5]);
var forest = ee.ImageCollection('ESA/WorldCover/v100').first().eq(10);

// 1. Fuel dryness: NDMI (NIR against SWIR 1.6 um) over forest, month by month
var ndmi = function (img) {
  var qa = img.select('StateQA');
  var clear = qa.bitwiseAnd(3).eq(0).and(qa.bitwiseAnd(1 << 2).eq(0));
  return img.normalizedDifference(['sur_refl_b02', 'sur_refl_b06']).rename('ndmi')
    .updateMask(clear).updateMask(forest).copyProperties(img, ['system:time_start']);
};
var mod09 = ee.ImageCollection('MODIS/061/MOD09A1').filterBounds(aoi)
  .filterDate('2014-01-01', '2020-01-01').map(ndmi);
print(ui.Chart.image.series({imageCollection: mod09, region: aoi,
  reducer: ee.Reducer.mean(), scale: 1000})
  .setOptions({title: 'Forest NDMI, 8-day, 2014-2019', pointSize: 1, lineWidth: 1}));

// 2. Progression: days since 1 September 2019 when each pixel first burned
var start = ee.Date('2019-09-01');
var mcd64 = ee.ImageCollection('MODIS/061/MCD64A1').filterDate('2019-09-01', '2020-03-01');
var days = mcd64.map(function (img) {
  var offset = ee.Date.fromYMD(img.date().get('year'), 1, 1).difference(start, 'day');
  return img.select('BurnDate').selfMask().add(offset).rename('day').toFloat();
}).min().clip(aoi);

// 3. Severity: dNBR = NBR before minus NBR after, x 1000, Key and Benson classes
var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(aoi);
var maskS2 = function (img) {
  var scl = img.select('SCL');
  var ok = scl.neq(3).and(scl.neq(8)).and(scl.neq(9)).and(scl.neq(10)).and(scl.neq(11));
  return img.updateMask(ok).divide(10000);
};
var pre = s2.filterDate('2018-12-20', '2019-01-18').map(maskS2).median();
var post = s2.filterDate('2020-02-20', '2020-03-28').map(maskS2).median();
var dnbr = pre.normalizedDifference(['B8', 'B12'])
  .subtract(post.normalizedDifference(['B8', 'B12'])).multiply(1000).rename('dNBR').clip(aoi);
var breaks = [-251, -101, 100, 270, 440, 660];
var severity = ee.Image(0);
breaks.forEach(function (b, i) { severity = severity.where(dnbr.gte(b), i + 1); });
severity = severity.updateMask(dnbr.mask()).clip(aoi);

var grouped = ee.Image.pixelArea().divide(1e4).addBands(severity).reduceRegion({
  reducer: ee.Reducer.sum().group({groupField: 1, groupName: 'class'}),
  geometry: aoi, scale: 20, maxPixels: 1e11, tileScale: 8});
print('Hectares per severity class (0 = regrowth high ... 6 = high severity)', grouped);

Map.centerObject(aoi, 9);
Map.addLayer(days, {min: 0, max: 150, palette: ['ffffb2', 'fd8d3c', 'bd0026', '4a1486']},
  'Day of burning since 1 Sep 2019', false);
Map.addLayer(severity, {min: 0, max: 6, palette: ['7a8737', 'acbe4d', '0ae042', 'fff70b',
  'ffaf38', 'ff641b', 'a41fd6']}, 'Burn severity (dNBR)');
