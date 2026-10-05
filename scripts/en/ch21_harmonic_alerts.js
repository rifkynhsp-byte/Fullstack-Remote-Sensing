//| title: Harmonic regression, radar change and alert rules on real data
//| description: Fit a seasonal model to Sentinel-2 NDVI in Nusantara's core zone, turn residuals into alerts, and check the change map against Sentinel-1 and Dynamic World.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 21 | From fitted seasons to change alerts, on real data
 * ---------------------------------------------------------------------------
 * The synthetic example earlier in the chapter shows the mechanism. Here it
 * meets reality: a pixel in the core zone of Nusantara, Indonesia's new
 * capital, that was vegetated until it was cleared for construction. Then the
 * same model runs on every pixel of the zone, and Sentinel-1 radar gives an
 * independent second opinion that does not care about cloud.
 *
 * Why no trend term
 *   Cloud Score+ for Sentinel-2 surface reflectance starts in 2019, so the
 *   season is learned on 2019-2020, two years with no clearing. Fitted on two
 *   years, a trend term extrapolates wildly (an earlier version predicted an
 *   NDVI of 1.2 by 2024 and raised a false alert).
 */

// ---------------------------------------------------------------------------
// STEP 1. Place, periods and the alert rule
// ---------------------------------------------------------------------------
var PIXEL = ee.Geometry.Point([116.6948, -0.9876]);   // vegetated in 2019, bare or built by 2023
var BOX = ee.Geometry.Rectangle([116.66, -1.02, 116.75, -0.93], null, false);
var FIT_START = '2019-01-01', FIT_END = '2021-01-01';
var Z = 3;                                            // alert below -3 sigma ...
var RUN = 3;                                          // ... on three consecutive observations
var TERMS = ['c', 'cos1', 'sin1', 'cos2', 'sin2'];

// ---------------------------------------------------------------------------
// STEP 2. NDVI screened with Cloud Score+, and the harmonic design
// ---------------------------------------------------------------------------
// Each image carries NDVI and t, the time in years since 2017. Pixels with a
// Cloud Score+ "cs" below 0.6 are masked, not whole scenes dropped.
function s2Ndvi(region, start, end) {
  var cs = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED');
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(region).filterDate(start, end)
    .linkCollection(cs, ['cs'])
    .map(function (im) {
      var t = ee.Date(im.get('system:time_start'));
      var years = t.difference(ee.Date.fromYMD(2017, 1, 1), 'year');
      var nd = im.updateMask(im.select('cs').gte(0.6)).normalizedDifference(['B8', 'B4']).rename('NDVI');
      return nd.addBands(ee.Image.constant(years).float().rename('t'))
        .set('system:time_start', t.millis());
    });
}

// Intercept plus two annual harmonics: 1, cos 2pi t, sin 2pi t, cos 4pi t, sin 4pi t.
function harmonicTerms(img) {
  var w = img.select('t').multiply(2 * Math.PI);
  return ee.Image.constant(1).rename('c')
    .addBands(w.cos().rename('cos1')).addBands(w.sin().rename('sin1'))
    .addBands(w.multiply(2).cos().rename('cos2')).addBands(w.multiply(2).sin().rename('sin2'))
    .addBands(img.select('NDVI')).float()
    .copyProperties(img, ['system:time_start']);       // keep the date, or filterDate finds nothing
}

// ---------------------------------------------------------------------------
// STEP 3. One pixel: the season, then the clearing
// ---------------------------------------------------------------------------
// The Code Editor charts the raw observations directly. The per-pixel alert
// (three consecutive observations below -3 sigma) is computed in the Python
// notebook, where a running count is one line; here the same model is fitted
// and drawn so you can see the residual collapse after 2021.
var pixelCol = s2Ndvi(PIXEL, '2017-01-01', '2025-01-01').map(harmonicTerms);
var pixelCoef = pixelCol.filterDate(FIT_START, FIT_END)
  .select(TERMS.concat(['NDVI']))
  .reduce(ee.Reducer.linearRegression(TERMS.length, 1))
  .select('coefficients').arrayProject([0]).arrayFlatten([TERMS]);
var fitted = pixelCol.map(function (im) {
  return im.select('NDVI')
    .addBands(im.select(TERMS).multiply(pixelCoef).reduce('sum').rename('fitted'))
    .copyProperties(im, ['system:time_start']);
});
print(ui.Chart.image.series(fitted, PIXEL, ee.Reducer.first(), 10)
  .setOptions({title: 'One pixel in the core zone: observations and the 2019-2020 harmonic model',
               vAxis: {title: 'NDVI'}, lineWidth: 1, pointSize: 2,
               series: {0: {color: '#555555', lineWidth: 0}, 1: {color: '#2a78d6', pointSize: 0}}}));

// ---------------------------------------------------------------------------
// STEP 4. Every pixel: mean residual in a test year, in units of its own SD
// ---------------------------------------------------------------------------
function harmonicChange(testStart, testEnd, fitStart, fitEnd) {
  var col = s2Ndvi(BOX, fitStart, testEnd).map(harmonicTerms);
  var train = col.filterDate(fitStart, fitEnd);
  var coef = train.select(TERMS.concat(['NDVI']))
    .reduce(ee.Reducer.linearRegression(TERMS.length, 1))
    .select('coefficients').arrayProject([0]).arrayFlatten([TERMS]);
  var predict = function (im) {
    return im.select('NDVI').subtract(im.select(TERMS).multiply(coef).reduce('sum')).rename('r');
  };
  var sd = train.map(predict).reduce(ee.Reducer.stdDev());
  var test = col.filterDate(testStart, testEnd).map(predict).mean();
  return test.divide(sd).rename('z');
}
var optical = harmonicChange('2023-01-01', '2024-01-01', FIT_START, FIT_END).lt(-Z).rename('optical');

// ---------------------------------------------------------------------------
// STEP 5. Radar: Sentinel-1 VH, same orbit direction, 2019 against 2023
// ---------------------------------------------------------------------------
function s1Year(y) {
  return ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(BOX)
    .filterDate(y + '-01-01', (y + 1) + '-01-01')
    .filter(ee.Filter.eq('instrumentMode', 'IW'))
    .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'))
    .select('VH').median().focalMedian(30, 'circle', 'meters');
}
var dB = s1Year(2023).subtract(s1Year(2019)).rename('dB');   // a difference in dB is a log ratio
var sar = dB.abs().gt(3).rename('sar');

// ---------------------------------------------------------------------------
// STEP 6. The change map: red optical only, blue radar only, magenta both
// ---------------------------------------------------------------------------
var code = ee.Image(0).where(optical.and(sar.not()), 1).where(sar.and(optical.not()), 2)
  .where(optical.and(sar), 3).selfMask();
var backdrop = s2Ndvi(BOX, '2023-01-01', '2024-01-01').select('NDVI').median();
Map.centerObject(BOX, 13);
Map.addLayer(backdrop, {min: 0, max: 0.9, palette: ['ffffff', 'd9d9d9', '737373']}, 'NDVI 2023 (dark = green)');
Map.addLayer(code, {min: 1, max: 3, palette: ['e41a1c', '377eb8', '984ea3']}, 'Change 2023: optical, radar, both');

// ---------------------------------------------------------------------------
// STEP 7. The change in hectares, and two honesty checks
// ---------------------------------------------------------------------------
// A minimum mapping unit of 10 pixels (0.1 ha) removes speckle. Dynamic World
// labels give an independent check. And a year in which nothing should have
// changed (2020, fitting on 2019 only) shows how much "change" the rule
// raises on its own.
var mmu = optical.selfMask().connectedPixelCount(100, true).gte(10).unmask(0).and(optical).rename('opt_mmu');
var stable = harmonicChange('2020-01-01', '2021-01-01', '2019-01-01', '2020-01-01').lt(-Z).rename('stable');
var oneYear = harmonicChange('2023-01-01', '2024-01-01', '2019-01-01', '2020-01-01').lt(-Z).rename('one_year');
var dwYear = function (y) {
  return ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(BOX)
    .filterDate(y + '-01-01', (y + 1) + '-01-01').select('label').mode();
};
var dwChanged = dwYear(2019).neq(dwYear(2023)).rename('dw');
var stack = ee.Image.cat([optical, mmu, sar, optical.and(sar).rename('both'), stable, oneYear, dwChanged,
                          optical.and(dwChanged).rename('opt_dw'), sar.and(dwChanged).rename('sar_dw'),
                          ee.Image(1).rename('all')]);
var ha = stack.multiply(ee.Image.pixelArea().divide(1e4))
  .reduceRegion({reducer: ee.Reducer.sum(), geometry: BOX, scale: 10, maxPixels: 1e10, tileScale: 8});
print('Change in the box (hectares; opt_dw and sar_dw: area where Dynamic World also changed)', ha);
