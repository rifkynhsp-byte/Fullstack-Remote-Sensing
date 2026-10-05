//| title: The water balance of a river basin, every term from space
//| description: Precipitation, evapotranspiration, runoff and storage change for the Kapuas basin, 2003-2023, and where the water yield comes from.

/**
 * CHAPTER 40 | The water balance of a river basin, every term from space
 * ---------------------------------------------------------------------------
 *     P - ET - Q = dS
 *
 *   P   precipitation         CHIRPS v2, 5 km
 *   ET  evapotranspiration    MODIS MOD16A2GF, 500 m
 *   dS  change in storage     GRACE / GRACE-FO mascons (JPL, CRI-filtered), ~300 km footprint
 *   Q   runoff                ERA5-Land reanalysis (a model, not a gauge)
 *
 * Basin: the Kapuas, West Kalimantan, from HydroSHEDS level 4. The Python
 * notebook adds the closure test (GRACE storage change against P - ET - Q);
 * here every term is computed and charted month by month.
 */

// ---------------------------------------------------------------------------
// STEP 1. The basin and the four datasets
// ---------------------------------------------------------------------------
var basin = ee.FeatureCollection('WWF/HydroSHEDS/v1/Basins/hybas_4')
  .filterBounds(ee.Geometry.Point(111.5, 0.3)).first().geometry();
var chirps = ee.ImageCollection('UCSB-CHG/CHIRPS/PENTAD').select('precipitation');
var mod16 = ee.ImageCollection('MODIS/061/MOD16A2GF').select('ET');
var grace = ee.ImageCollection('NASA/GRACE/MASS_GRIDS_V04/MASCON_CRI').select('lwe_thickness');
var era5 = ee.ImageCollection('ECMWF/ERA5_LAND/MONTHLY_AGGR').select('runoff_sum');

// ---------------------------------------------------------------------------
// STEP 2. One month: every term as a basin mean, in mm
// ---------------------------------------------------------------------------
function monthTerms(d0) {
  d0 = ee.Date(d0);
  var d1 = d0.advance(1, 'month');
  var p = chirps.filterDate(d0, d1).sum();
  var et = mod16.filterDate(d0, d1).sum().multiply(0.1);            // 0.1 kg/m2 per unit = 0.1 mm
  var q = era5.filterDate(d0, d1).first().multiply(1000);           // m -> mm
  // GRACE has gap months; a masked placeholder keeps the band so the month comes back empty, not as an error.
  var empty = ee.Image.constant(0).rename('lwe_thickness').updateMask(0);
  var tws = grace.filterDate(d0, d1).merge(ee.ImageCollection([empty])).mean().multiply(10);   // cm -> mm
  var img = ee.Image.cat(p.rename('P'), et.rename('ET'), q.rename('Q'), tws.rename('TWS'));
  var vals = img.reduceRegion({reducer: ee.Reducer.mean(), geometry: basin, scale: 5000, maxPixels: 1e10, tileScale: 4});
  return ee.Feature(null, vals).set({'system:time_start': d0.millis(), year: d0.get('year'), month: d0.get('month')});
}

// ---------------------------------------------------------------------------
// STEP 3. 2003-2023, month by month
// ---------------------------------------------------------------------------
var months = ee.List.sequence(0, 21 * 12 - 1).map(function (i) {
  return ee.Date.fromYMD(2003, 1, 1).advance(i, 'month');
});
var balance = ee.FeatureCollection(months.map(monthTerms));
print(ui.Chart.feature.byFeature(balance, 'system:time_start', ['P', 'ET', 'Q'])
  .setChartType('LineChart')
  .setOptions({title: 'Kapuas basin: monthly precipitation, evapotranspiration and runoff (mm)',
               hAxis: {format: 'yyyy'}, lineWidth: 1, colors: ['#2a78d6', '#1b7837', '#eb6834']}));
print(ui.Chart.feature.byFeature(balance, 'system:time_start', ['TWS'])
  .setOptions({title: 'Terrestrial water storage anomaly from GRACE (mm; gaps are missing months)',
               hAxis: {format: 'yyyy'}, lineWidth: 1, colors: ['#4a3aa7']}));

// ---------------------------------------------------------------------------
// STEP 4. Annual totals: does the budget close?
// ---------------------------------------------------------------------------
// Over 21 years storage change averages out, so P - ET - Q should sit near zero
// if the three products agree. Its size is the honest uncertainty of the budget.
var annual = ee.FeatureCollection(ee.List.sequence(2003, 2023).map(function (y) {
  var fy = balance.filter(ee.Filter.eq('year', y));
  var P = fy.aggregate_sum('P'), ET = fy.aggregate_sum('ET'), Q = fy.aggregate_sum('Q');
  return ee.Feature(null, {year: y, P: P, ET: ET, Q: Q,
                           P_minus_ET_minus_Q: ee.Number(P).subtract(ET).subtract(Q)});
}));
print('Mean annual terms 2003-2023 (mm/yr)', annual.reduceColumns({
  reducer: ee.Reducer.mean().repeat(4), selectors: ['P', 'ET', 'Q', 'P_minus_ET_minus_Q']}));
print(ui.Chart.feature.byFeature(annual, 'year', ['P', 'ET', 'Q', 'P_minus_ET_minus_Q'])
  .setChartType('ColumnChart')
  .setOptions({title: 'Annual water balance terms (mm/yr)', colors: ['#2a78d6', '#1b7837', '#eb6834', '#7b8794']}));

// ---------------------------------------------------------------------------
// STEP 5. Where the water yield comes from: mean P - ET, 2003-2023
// ---------------------------------------------------------------------------
var pMinusEt = chirps.filterDate('2003-01-01', '2024-01-01').sum().divide(21)
  .subtract(mod16.filterDate('2003-01-01', '2024-01-01').sum().multiply(0.1).divide(21))
  .rename('p_et').clip(basin);
Map.centerObject(basin, 7);
Map.addLayer(pMinusEt, {min: 500, max: 3500, palette: ['fff7bc', 'c7e9b4', '41b6c4', '225ea8', '081d58']},
             'Mean P - ET 2003-2023 (mm/yr)');
Map.addLayer(ee.Image().paint(basin, 0, 2), {palette: ['000000']}, 'Kapuas basin (HydroSHEDS L4)');
