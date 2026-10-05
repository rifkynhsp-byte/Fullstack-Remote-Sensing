//| title: Images, collections and reducers on a real reservoir
//| description: Map, reduce and measure the Jatiluhur reservoir, West Java, 2014 to 2024.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist,
// adapted from the EE101 teaching series by Noel Gorelick, David Gibson, Nicholas Clinton and Hadi
// Book additions MIT licence; the EE101 parts keep their original terms. Please keep this credit.

/**
 * CHAPTER 7 | Server side thinking on a real reservoir
 * ---------------------------------------------------------------------------
 * Adapted from the GEE101 Bandung course (itself built on Gorelick, Gibson,
 * Clinton and Hadi's EE101 material), rewritten for Landsat Collection 2
 * surface reflectance.
 *
 * Goal
 *   1. Compute an index on every image with map().
 *   2. Reduce a collection three ways and see that they disagree.
 *   3. Reduce a region to a number: the water area of Jatiluhur, the
 *      reservoir that supplies Jakarta, for every dry season since 2014.
 */

var jatiluhur = ee.Geometry.Rectangle([107.348, -6.986, 107.506, -6.871]);

// ---------------------------------------------------------------------------
// STEP 1. One function for one image: scale, mask cloud, add two indices
// ---------------------------------------------------------------------------
// Collection 2 Level 2 stores reflectance as integers: multiply by 0.0000275
// and add -0.2. Skip this and every index is still computable and wrong.
var prepare = function (image) {
  var qa = image.select('QA_PIXEL');
  var clear = qa.bitwiseAnd(1 << 3).eq(0)      // cloud
    .and(qa.bitwiseAnd(1 << 4).eq(0));         // cloud shadow
  var sr = image.select('SR_B.').multiply(0.0000275).add(-0.2);
  var ndvi = sr.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI');
  var mndwi = sr.normalizedDifference(['SR_B3', 'SR_B6']).rename('MNDWI');
  return sr.addBands([ndvi, mndwi]).updateMask(clear)
    .copyProperties(image, ['system:time_start']);
};

var landsat = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
  .filterBounds(jatiluhur)
  .map(prepare);

// ---------------------------------------------------------------------------
// STEP 2. Three reductions of the same collection
// ---------------------------------------------------------------------------
var year2019 = landsat.filterDate('2019-01-01', '2020-01-01');
var median = year2019.median();                         // per band median
var greenest = year2019.qualityMosaic('NDVI');           // whole pixel at max NDVI

Map.centerObject(jatiluhur, 12);
Map.addLayer(median, {bands: ['SR_B4', 'SR_B3', 'SR_B2'], min: 0, max: 0.25},
  'Median 2019');
Map.addLayer(greenest, {bands: ['SR_B4', 'SR_B3', 'SR_B2'], min: 0, max: 0.25},
  'Greenest pixel 2019', false);

// ---------------------------------------------------------------------------
// STEP 3. From a picture to a number: water area each dry season
// ---------------------------------------------------------------------------
// MNDWI above zero is water. Multiply the mask by pixel area and sum it
// over the region: one reduceRegion call, one number per year.
var waterArea = function (year) {
  var dry = landsat.filterDate(ee.Date.fromYMD(year, 7, 1),
                               ee.Date.fromYMD(year, 10, 31)).median();
  var water = dry.select('MNDWI').gt(0);
  var km2 = water.multiply(ee.Image.pixelArea()).divide(1e6).reduceRegion({
    reducer: ee.Reducer.sum(), geometry: jatiluhur, scale: 30, maxPixels: 1e9
  }).get('MNDWI');
  return ee.Feature(null, {year: year, water_km2: km2,
                           scenes: landsat.filterDate(ee.Date.fromYMD(year, 7, 1),
                                                      ee.Date.fromYMD(year, 10, 31)).size()});
};
var areas = ee.FeatureCollection(ee.List.sequence(2014, 2024).map(waterArea));

print('Dry season water area by year', areas);
print(ui.Chart.feature.byFeature(areas, 'year', ['water_km2'])
  .setOptions({title: 'Jatiluhur water area, July to October median',
               vAxis: {title: 'km²'}, hAxis: {format: '####'}, pointSize: 4}));

Map.addLayer(median.select('MNDWI').gt(0).selfMask(), {palette: ['#1A5BAB']},
  'Water 2019 (MNDWI > 0)', false);

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Add NDVI of the median, addIndices(landsat.median()), as a layer and
//    compare it with the median of NDVI. Why are they different?
// 2. Change the dry season to the wet season (January to April). Which years
//    lose the most area, and does that match the rainfall record?
