//| title: A landscape carbon balance, term by term
//| description: Productivity from MODIS, peat drainage by land class with IPCC factors, and clearing and fire losses for Tanjung Jabung Timur, Jambi.

/**
 * CHAPTER 42 | A landscape carbon balance, term by term
 * ---------------------------------------------------------------------------
 *   GPP  gross primary production: carbon fixed by photosynthesis    MODIS MOD17
 *   NPP  net primary production = GPP - plant respiration             MODIS MOD17
 *   NEP  = NPP - soil (heterotrophic) respiration                     NOT measurable from space
 *   NBP  = NEP - disturbance losses (clearing, fire, harvest, peat)   partly measurable
 *
 * Peat drainage CO2: IPCC 2013 Wetlands Supplement, Table 2.1 (tropical),
 * t CO2-C/ha/yr: oil palm 11 (5.6-17); plantations, unknown or long rotation
 * 15 (10-21); forest and cleared forest (shrubland), drained 5.3 (-0.7-9.5).
 * GPP and NPP are uptake, not a net sink: the chapter explains why the
 * balance cannot be closed from space.
 */

// ---------------------------------------------------------------------------
// STEP 1. District and datasets
// ---------------------------------------------------------------------------
var district = ee.FeatureCollection('FAO/GAUL/2025/level2')
  .filter(ee.Filter.eq('GAUL1_NAME', 'Jambi')).filter(ee.Filter.eq('GAUL2_NAME', 'Tanjung Jabung Timur')).geometry();
var C2CO2 = 44 / 12;
var mod17 = ee.ImageCollection('MODIS/061/MOD17A3HGF');
var peat = ee.Image('projects/sat-io/open-datasets/GLOBAL-PEATLAND-DATABASE').gte(1).unmask(0);
var palm = ee.ImageCollection('BIOPAMA/GlobalOilPalm/v1').select('classification').mosaic().lte(2).unmask(0);  // 1 industrial, 2 smallholder
var tmfCol = ee.ImageCollection('projects/JRC/TMF/v1_2023/AnnualChanges');
var tmf23 = tmfCol.mosaic().setDefaultProjection(tmfCol.first().projection()).select('Dec2023');
var gfc = ee.Image('UMD/hansen/global_forest_change_2025_v1_13');
var l4b = ee.Image('LARSE/GEDI/GEDI04_B_002').select('MU');
var areaHa = ee.Image.pixelArea().divide(1e4);

// ---------------------------------------------------------------------------
// STEP 2. Productivity: GPP and NPP, 2001-2024 (Mt C per year)
// ---------------------------------------------------------------------------
var productivity = mod17.filterDate('2001-01-01', '2025-01-01').map(function (img) {
  var s = img.select(['Gpp', 'Npp']).multiply(0.0001)           // kg C / m2 / yr
    .multiply(ee.Image.pixelArea()).divide(1e9)                  // -> Mt C per pixel
    .reduceRegion({reducer: ee.Reducer.sum(), geometry: district, scale: 500, maxPixels: 1e10});
  return ee.Feature(null, s).set('year', img.date().get('year'));
});
print(ui.Chart.feature.byFeature(productivity, 'year', ['Gpp', 'Npp'])
  .setOptions({title: 'GPP and NPP, Tanjung Jabung Timur (Mt C per year): uptake, not a net sink',
               colors: ['#1b7837', '#5ec962'], pointSize: 3}));

// ---------------------------------------------------------------------------
// STEP 3. Land classes on peat, and the peat drainage flux
// ---------------------------------------------------------------------------
// Strata on peat (TMF 2023 and the oil palm map):
//   0 undisturbed forest (taken as undrained)   1 degraded or regrowing forest
//   2 oil palm                                   3 other cleared land
var strata = ee.Image(3)
  .where(tmf23.eq(2).or(tmf23.eq(4)), 1)
  .where(tmf23.eq(1), 0)
  .where(palm.eq(1), 2)
  .updateMask(peat.eq(1).and(tmf23.neq(5)))                      // peat, not open water
  .rename('stratum');
// IPCC 2013 Table 2.1 means per stratum, t CO2-C/ha/yr (0: undrained, no drainage emission)
var EF = ee.Dictionary({'0': 0, '1': 5.3, '2': 11.0, '3': 15.0});
var NAMES = ee.Dictionary({'0': 'undisturbed forest', '1': 'degraded / regrowing forest', '2': 'oil palm', '3': 'other cleared land'});
var groups = ee.List(areaHa.addBands(strata).reduceRegion({
  reducer: ee.Reducer.sum().group(1, 'stratum'), geometry: district, scale: 30, maxPixels: 1e11, tileScale: 8}).get('groups'));
var peatTable = ee.FeatureCollection(groups.map(function (g) {
  g = ee.Dictionary(g);
  var k = ee.Number(g.get('stratum')).format('%d');
  var ha = ee.Number(g.get('sum'));
  return ee.Feature(null, {stratum: NAMES.get(k), area_ha: ha, EF_tC_ha_yr: EF.get(k),
                           Mt_CO2_yr: ha.multiply(ee.Number(EF.get(k))).multiply(C2CO2).divide(1e6)});
}));
print('Peat drainage emissions by land class (IPCC Tier 1)', peatTable);
print('Total peat drainage (Mt CO2 per year)', peatTable.aggregate_sum('Mt_CO2_yr'));

// ---------------------------------------------------------------------------
// STEP 4. Biomass stock, clearing and fire, 2015-2023
// ---------------------------------------------------------------------------
var forest = tmf23.eq(1).or(tmf23.eq(2));
var stockC = ee.Number(l4b.multiply(0.47).rename('c')                // Mg C/ha above ground
  .updateMask(forest.reduceResolution({reducer: ee.Reducer.mean(), bestEffort: true, maxPixels: 2048})
                .reproject(l4b.projection()).gte(0.5))
  .reduceRegion({reducer: ee.Reducer.mean(), geometry: district, scale: 1000, maxPixels: 1e9}).get('c'));
var losses = ee.FeatureCollection(ee.List.sequence(2015, 2023).map(function (y) {
  y = ee.Number(y);
  var lost = gfc.select('treecover2000').gte(30).and(gfc.select('lossyear').eq(y.subtract(2000)));
  var start = ee.Date.fromYMD(y, 1, 1);
  var burned = ee.ImageCollection('MODIS/061/MCD64A1').select('BurnDate')
    .filterDate(start, start.advance(1, 'year')).max().gt(0);
  var s = areaHa.updateMask(lost).rename('lost_ha')
    .addBands(areaHa.updateMask(burned).rename('burned_ha'))
    .addBands(areaHa.updateMask(burned.and(peat.eq(1))).rename('burned_peat_ha'))
    .reduceRegion({reducer: ee.Reducer.sum(), geometry: district, scale: 30, maxPixels: 1e11, tileScale: 8});
  // clearing emission: above + below ground (R = 0.37) of the mean forest stock
  return ee.Feature(null, s).set({year: y,
    clearing_Mt_CO2: ee.Number(s.get('lost_ha')).multiply(stockC).multiply(1.37).multiply(C2CO2).divide(1e6)});
}));
print('Mean above-ground forest carbon from GEDI (Mg C/ha)', stockC);
print(ui.Chart.feature.byFeature(losses, 'year', ['lost_ha', 'burned_ha', 'burned_peat_ha'])
  .setChartType('ColumnChart')
  .setOptions({title: 'Forest cleared and area burned per year (ha)', colors: ['#7b8794', '#e34948', '#b8433a']}));
print('Mean clearing emission 2015-2023 (Mt CO2 per year)', losses.aggregate_mean('clearing_Mt_CO2'));

// ---------------------------------------------------------------------------
// STEP 5. Map: the land classes on peat
// ---------------------------------------------------------------------------
Map.centerObject(district, 9);
Map.addLayer(strata.clip(district), {min: 0, max: 3, palette: ['1b7837', 'a6dba0', 'eda100', 'b8433a']},
             'On peat: undisturbed, degraded/regrowing, oil palm, other cleared');
Map.addLayer(ee.Image().paint(district, 0, 2), {palette: ['000000']}, 'Tanjung Jabung Timur');
