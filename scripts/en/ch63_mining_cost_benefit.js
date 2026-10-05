//| title: Does the benefit outweigh the loss?
//| description: The forest footprint of nickel mining at Pomalaa since 2001, the carbon it released from GEDI biomass, and the break-even benefit per hectare at stated carbon prices and service values.

/**
 * CHAPTER 63 | Does the benefit outweigh the loss?
 * ---------------------------------------------------------------------------
 * An environmental impact statement asks what a project removes. A
 * cost-benefit analysis asks whether what it gives is worth more. Satellites
 * measure the first part well; this script measures it and turns it into a
 * break-even.
 *   1. footprint  forest (Hansen tree cover >= 30 % in 2000) lost since 2001 and
 *                 still bare in 2024 (Dynamic World mode). Built land is
 *                 excluded: a first version counted the growing towns as mine.
 *   2. carbon     median GEDI L4A biomass of intact forest nearby (Mg/ha),
 *                 x 1.37 (roots, IPCC 2006 R = 0.37) x 0.47 (carbon fraction)
 *                 x 44/12 (CO2): tonnes CO2 released per hectare cleared
 *   3. price      US EPA (2023) social cost of carbon: 120 / 190 / 340 US$ per t CO2
 *   4. services   tropical forest unit values, Costanza et al. (2014): median
 *                 2,355 and mean 5,264 US$/ha/yr (2007 international dollars)
 *   5. break-even carbon (once) + services x T years (undiscounted)
 * Mining older than 2001 is not in the footprint: Hansen starts in 2001.
 */

// ---------------------------------------------------------------------------
// STEP 1. Pomalaa, the footprint
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Rectangle([121.50, -4.35, 121.78, -4.02], null, false);   // Pomalaa, Kolaka
var gfc = ee.Image('UMD/hansen/global_forest_change_2025_v1_13');
var forest2000 = gfc.select('treecover2000').gte(30);
var lossyear = gfc.select('lossyear').unmask(0);
var dw24 = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(aoi).filterDate('2024-01-01', '2025-01-01').select('label').mode();
var mine = forest2000.and(lossyear.gt(0)).and(dw24.eq(7)).selfMask().clip(aoi).rename('mine');   // bare in 2024
var intact = forest2000.and(lossyear.eq(0)).and(gfc.select('treecover2000').gte(60));
var area = ee.Image.pixelArea().divide(1e4);
var byYear = ee.List(area.updateMask(mine).addBands(lossyear.rename('y'))
  .reduceRegion({reducer: ee.Reducer.sum().group(1, 'y'), geometry: aoi, scale: 30, maxPixels: 1e10, tileScale: 8}).get('groups'));
var footprint = ee.FeatureCollection(byYear.map(function (g) {
  g = ee.Dictionary(g);
  return ee.Feature(null, {year: ee.Number(g.get('y')).add(2000), new_mine_ha: g.get('sum')});
}));
var mineHa = ee.Number(footprint.aggregate_sum('new_mine_ha'));
print(ui.Chart.feature.byFeature(footprint, 'year', 'new_mine_ha').setChartType('ColumnChart')
  .setOptions({title: 'Forest cleared since 2001 and still bare in 2024, by year of clearing (ha)', colors: ['#b8433a']}));
print('Mine footprint since 2001 (ha)', mineHa);

// ---------------------------------------------------------------------------
// STEP 2. Carbon released per hectare, from GEDI biomass of nearby intact forest
// ---------------------------------------------------------------------------
var l4a = ee.ImageCollection('LARSE/GEDI/GEDI04_A_002_MONTHLY').filterBounds(aoi).filterDate('2019-04-01', '2024-01-01')
  .map(function (i) { return i.updateMask(i.select('l4_quality_flag').eq(1).and(i.select('degrade_flag').eq(0))); })
  .select('agbd').mosaic().updateMask(intact);
var agb = l4a.sample({region: aoi, scale: 25, numPixels: 20000, seed: 2, tileScale: 8})
  .filter(ee.Filter.rangeContains('agbd', 0.01, 999));
var q = agb.reduceColumns(ee.Reducer.percentile([25, 50, 75]), ['agbd']);
var CO2_PER_MG = 1.37 * 0.47 * 44 / 12;
var tco2 = ee.Number(q.get('p50')).multiply(CO2_PER_MG);
print('Forest biomass (Mg/ha, p25/p50/p75) and GEDI shots', q.set('shots', agb.size()));
print('t CO2 released per hectare cleared (median biomass)', tco2);

// ---------------------------------------------------------------------------
// STEP 3. Break-even: what mining must return per hectare to outweigh the loss
// ---------------------------------------------------------------------------
var SCC = {low: 120, central: 190, high: 340};
var SERVICES = {median: 2355, mean: 5264};
var rows = [];
Object.keys(SCC).forEach(function (s) {
  Object.keys(SERVICES).forEach(function (v) {
    [10, 30].forEach(function (T) {
      var be = tco2.multiply(SCC[s]).add(SERVICES[v] * T);
      rows.push(ee.Feature(null, {carbon_price: s + ' ' + SCC[s] + ' $/t', service_value: v + ' ' + SERVICES[v] + ' $/ha/yr',
        years: T, breakeven_usd_ha: be, breakeven_footprint_musd: be.multiply(mineHa).divide(1e6)}));
    });
  });
});
print('Break-even per hectare and for the whole footprint', ee.FeatureCollection(rows));

// ---------------------------------------------------------------------------
// STEP 4. The map: 2024 imagery with the footprint outlined
// ---------------------------------------------------------------------------
var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(aoi).filterDate('2024-01-01', '2025-01-01')
  .linkCollection(ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'), ['cs'])
  .map(function (i) { return i.updateMask(i.select('cs').gte(0.6)); }).median();
Map.centerObject(aoi, 12);
Map.addLayer(s2, {bands: ['B4', 'B3', 'B2'], min: 200, max: 2200}, 'Sentinel-2, 2024');
Map.addLayer(mine, {palette: ['ffff00']}, 'Forest cleared since 2001, still bare in 2024', false);
Map.addLayer(ee.Image().byte().paint(mine.reduceToVectors({geometry: aoi, scale: 60, maxPixels: 1e10, tileScale: 8}), 1, 1),
             {palette: ['ffff00']}, 'Footprint outline');
