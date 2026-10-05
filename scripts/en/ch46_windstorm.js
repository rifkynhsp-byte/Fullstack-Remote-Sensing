//| title: Wind damage, separated from the season
//| description: Cyclone Seroja's damage to forest on Rote and neighbouring islands, as a canopy-water anomaly against a baseline year, checked with Sentinel-1.

/**
 * CHAPTER 46 | Wind damage, separated from the season
 * ---------------------------------------------------------------------------
 * Seroja struck Nusa Tenggara Timur on 4-5 April 2021, at the turn from wet
 * to dry season. Leaves dry out every April anyway, so a simple before/after
 * drop would blame the wind for the season. The fix is a baseline year:
 *
 *   anomaly = (after - before, 2021) - (after - before, 2020)
 *   index   NDMI = (NIR - SWIR1) / (NIR + SWIR1), canopy water; also NDVI
 *   before  1 Feb - 31 Mar, after 10 Apr - 31 May, Sentinel-2 L2A, clear pixels
 *   forest  ESA WorldCover 2021 tree cover
 *   check   Sentinel-1 VH change, same windows, same baseline logic
 */

// ---------------------------------------------------------------------------
// STEP 1. Three islands and the forest mask
// ---------------------------------------------------------------------------
var ISLANDS = {
  'Rote': [122.85, -10.95, 123.45, -10.60],
  'Sumba (east)': [119.90, -10.10, 120.60, -9.60],
  'West Timor (Kupang)': [123.60, -10.40, 124.30, -9.90]
};
var rote = ee.Geometry.Rectangle(ISLANDS['Rote'], null, false);
var trees = ee.Image('ESA/WorldCover/v200/2021').select('Map').eq(10);

// ---------------------------------------------------------------------------
// STEP 2. Before, after, and the baseline year
// ---------------------------------------------------------------------------
function s2Index(a, b, box) {
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(box).filterDate(a, b)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))
    .map(function (i) {
      var clear = i.select('SCL').remap([4, 5], [1, 1], 0);      // vegetation and bare soil only
      return i.normalizedDifference(['B8', 'B11']).rename('ndmi')
        .addBands(i.normalizedDifference(['B8', 'B4']).rename('ndvi')).updateMask(clear);
    }).median();
}
function change(year, box) {
  return s2Index(year + '-04-10', year + '-05-31', box).subtract(s2Index(year + '-02-01', year + '-03-31', box));
}
function anomaly(box, base) {
  return change(2021, box).subtract(change(base || 2020, box)).updateMask(trees)
    .setDefaultProjection('EPSG:4326', null, 20);
}

// ---------------------------------------------------------------------------
// STEP 3. Radar check: Sentinel-1 VH, same windows, same baseline
// ---------------------------------------------------------------------------
// Averaging in linear power, then back to dB, is the correct way to average backscatter.
function s1Change(year, box) {
  var vh = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(box).filter(ee.Filter.eq('instrumentMode', 'IW')).select('VH');
  var lin = function (c) { return c.map(function (i) { return ee.Image(10).pow(i.divide(10)); }).mean().log10().multiply(10); };
  return lin(vh.filterDate(year + '-04-10', year + '-05-31')).subtract(lin(vh.filterDate(year + '-02-01', year + '-03-31')));
}

// ---------------------------------------------------------------------------
// STEP 4. Per island: how much forest lost canopy water?
// ---------------------------------------------------------------------------
Object.keys(ISLANDS).forEach(function (name) {
  var box = ee.Geometry.Rectangle(ISLANDS[name], null, false);
  var a = anomaly(box).select('ndmi');
  var hit = a.lt(-0.1);
  var stats = a.rename('median_NDMI_anomaly').addBands(hit.rename('hit'))
    .reduceRegion({reducer: ee.Reducer.median().combine(ee.Reducer.mean(), '', true), geometry: box, scale: 30,
                   maxPixels: 1e10, tileScale: 8});
  var ha = ee.Image.pixelArea().divide(1e4).updateMask(hit)
    .reduceRegion({reducer: ee.Reducer.sum(), geometry: box, scale: 30, maxPixels: 1e10, tileScale: 8});
  var vh = s1Change(2021, box).subtract(s1Change(2020, box)).updateMask(trees)
    .reduceRegion({reducer: ee.Reducer.median(), geometry: box, scale: 60, maxPixels: 1e10, tileScale: 8});
  print(name, ee.Dictionary({median_NDMI_anomaly: stats.get('median_NDMI_anomaly_median'),
    share_forest_below_minus_0_1: stats.get('hit_mean'),
    forest_ha_below_minus_0_1: ha.values().get(0), median_VH_anomaly_dB: vh.values().get(0)}));
});

// ---------------------------------------------------------------------------
// STEP 5. Why the baseline matters: 2020 against 2021 change on Rote
// ---------------------------------------------------------------------------
var pixels = change(2020, rote).select('ndmi').rename('y2020')
  .addBands(change(2021, rote).select('ndmi').rename('y2021')).updateMask(trees)
  .sample({region: rote, scale: 30, numPixels: 3000, seed: 4, tileScale: 4});
print(ui.Chart.feature.byFeature(pixels, 'y2020', 'y2021').setChartType('ScatterChart')
  .setOptions({title: 'Rote forest pixels: NDMI change Feb-Mar to Apr-May, 2020 (no cyclone) against 2021 (Seroja)',
               hAxis: {title: 'change 2020'}, vAxis: {title: 'change 2021'}, pointSize: 1, colors: ['#2a78d6']}));

// ---------------------------------------------------------------------------
// STEP 6. Maps: the anomaly, and 1 km blocks for a forester
// ---------------------------------------------------------------------------
var blocks = anomaly(rote).select('ndmi')
  .reduceResolution({reducer: ee.Reducer.mean(), bestEffort: false, maxPixels: 4096})   // 1 km = 2,500 pixels of 20 m
  .reproject(ee.Projection('EPSG:32751').atScale(1000)).rename('block');
Map.centerObject(rote, 11);
Map.addLayer(anomaly(rote).select('ndmi'), {min: -0.3, max: 0.1, palette: ['67001f', 'd6604d', 'fddbc7', 'f7f7f7', 'd1e5f0']},
             'NDMI anomaly, Seroja (2021 change minus 2020 change)');
Map.addLayer(blocks, {min: -0.25, max: 0.0, palette: ['67001f', 'd6604d', 'fddbc7', 'f7f7f7']}, '1 km blocks, mean anomaly', false);
