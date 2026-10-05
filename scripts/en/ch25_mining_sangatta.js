//| title: A coal mine from orbit: footprint, volume and heat
//| description: Open-pit growth 2016 to 2024, cut and fill from two elevation models, and thermal hot spots, near Sangatta, East Kalimantan.

/**
 * CHAPTER 25 | Mining and stockpiles
 * ---------------------------------------------------------------------------
 * Three questions a mining client, a regulator or an insurer asks, answered
 * from public data. The methods come from the author's mine and stockpile
 * monitoring work (supervised footprint mapping, DSM-difference volume grids,
 * Landsat thermal for self-heating), shown here on a public area.
 *   1. How fast is the disturbed footprint growing?   Dynamic World 'bare'
 *   2. How much material has moved?   NASADEM (2000) against Copernicus GLO-30
 *   3. Where is it hot?   Landsat 8 and 9 surface temperature, dry season
 */

var mine = ee.Geometry.Rectangle([117.40, 0.48, 117.65, 0.75]);   // near Sangatta

// ---------------------------------------------------------------------------
// 1. Footprint: bare ground year by year
// ---------------------------------------------------------------------------
var dw = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(mine);
var bareIn = function (year) {
  return dw.filterDate(ee.Date.fromYMD(year, 1, 1), ee.Date.fromYMD(year, 1, 1).advance(1, 'year'))
    .select('bare').mean().gt(0.5);
};
var footprint = ee.FeatureCollection(ee.List.sequence(2016, 2024).map(function (y) {
  var km2 = bareIn(y).multiply(ee.Image.pixelArea()).divide(1e6).reduceRegion({
    reducer: ee.Reducer.sum(), geometry: mine, scale: 30, maxPixels: 1e10}).get('bare');
  return ee.Feature(null, {year: y, bare_km2: km2});
}));
print(ui.Chart.feature.byFeature(footprint, 'year', ['bare_km2'])
  .setOptions({title: 'Bare ground (Dynamic World), km²', hAxis: {format: '####'}}));
var newSince2017 = bareIn(2024).and(bareIn(2017).not()).selfMask();

// ---------------------------------------------------------------------------
// 2. Volume: difference two elevation models, cell by cell
// ---------------------------------------------------------------------------
// NASADEM is the 2000 SRTM surface; GLO-30 comes from TanDEM-X, 2011 to 2015.
// Both are SURFACE models: cleared forest also reads as a 20-30 m "cut".
// Only count change inside today's bare footprint, and only beyond +-30 m.
var before = ee.Image('NASA/NASADEM_HGT/001').select('elevation');
var glo = ee.ImageCollection('COPERNICUS/DEM/GLO30_2024_1').filterBounds(mine).select('DEM');
var after = glo.mosaic().setDefaultProjection(glo.first().projection());
var dz = after.subtract(before).rename('dz').updateMask(bareIn(2024));
var cut = dz.lt(-30), fill = dz.gt(30);
var volume = function (mask) {
  return dz.updateMask(mask).multiply(ee.Image.pixelArea()).reduceRegion({
    reducer: ee.Reducer.sum(), geometry: mine, scale: 30, maxPixels: 1e10}).get('dz');
};
print('Cut volume (m3), fill volume (m3):', volume(cut), volume(fill));

// ---------------------------------------------------------------------------
// 3. Heat: dry-season land surface temperature, and its local anomaly
// ---------------------------------------------------------------------------
var landsat = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')
  .merge(ee.ImageCollection('LANDSAT/LC08/C02/T1_L2'))
  .filterBounds(mine).filterDate('2023-06-01', '2024-10-31')
  .filter(ee.Filter.calendarRange(6, 10, 'month'))
  .map(function (img) {
    var qa = img.select('QA_PIXEL');
    var clear = qa.bitwiseAnd(1 << 3).eq(0).and(qa.bitwiseAnd(1 << 4).eq(0));
    return img.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15)
      .rename('lst').updateMask(clear);
  });
var lst = landsat.median().clip(mine);
var lstMedian = ee.Number(lst.reduceRegion({reducer: ee.Reducer.median(), geometry: mine,
  scale: 30, maxPixels: 1e10}).get('lst'));
var anomaly = lst.subtract(lstMedian).rename('anomaly');

Map.centerObject(mine, 12);
Map.addLayer(dz, {min: -80, max: 80, palette: ['#b2182b', '#f7f7f7', '#2166ac']}, 'Elevation change (m)');
Map.addLayer(newSince2017, {palette: ['#ff7f00']}, 'Bare since 2017', false);
Map.addLayer(anomaly, {min: -5, max: 10, palette: ['#313695', '#ffffbf', '#a50026']},
  'LST anomaly (°C)', false);

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Change the +-30 m cut-off to +-15 m. How much does the volume grow, and
//    how much of that growth is cleared forest rather than excavation?
// 2. Find the hottest 1 % of pixels. Are they on pits, dumps or stockpiles?
