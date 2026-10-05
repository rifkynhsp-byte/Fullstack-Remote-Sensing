//| title: Measurement, Reporting and Verification, end to end
//| description: Activity data from two forest-loss maps, an emission factor from GEDI biomass, and annual emissions for Tebo, Jambi.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 41 | Measurement, Reporting and Verification, done once, end to end
 * ---------------------------------------------------------------------------
 * IPCC gain-loss logic for deforestation:
 *
 *   emissions (t CO2) = activity data (ha lost) x emission factor (t CO2 per ha)
 *   emission factor   = AGB x (1 + R) x CF x 44/12
 *     AGB    above-ground biomass of the forest being cleared (Mg/ha), GEDI L4B
 *     R      root-to-shoot ratio, tropical rainforest, 0.37 (IPCC 2006 default)
 *     CF     carbon fraction of dry matter, 0.47 (IPCC 2006 default)
 *
 * Activity data come from two independent maps, Hansen GFC and JRC Tropical
 * Moist Forest (TMF), so the effect of choosing a map is visible. Reference
 * period 2013-2019; monitoring period 2020-2023. The Monte Carlo uncertainty
 * is in the Python notebook; here every term is computed on the server.
 */

// ---------------------------------------------------------------------------
// STEP 1. District, years and IPCC defaults
// ---------------------------------------------------------------------------
var district = ee.FeatureCollection('FAO/GAUL/2025/level2')
  .filter(ee.Filter.eq('GAUL1_NAME', 'Jambi')).filter(ee.Filter.eq('GAUL2_NAME', 'Tebo')).geometry();
var YEARS = ee.List.sequence(2013, 2023);
var R = 0.37, CF = 0.47;

var gfc = ee.Image('UMD/hansen/global_forest_change_2025_v1_13');
var tmfCol = ee.ImageCollection('projects/JRC/TMF/v1_2023/AnnualChanges');
// mosaic() drops the native projection; put it back so it can be aggregated later.
var tmf = tmfCol.mosaic().setDefaultProjection(tmfCol.first().projection());

// ---------------------------------------------------------------------------
// STEP 2. Activity data: hectares lost per year, two maps
// ---------------------------------------------------------------------------
// Hansen: tree cover >= 30 % in 2000, lost in year Y (lossyear = Y - 2000).
var hansenForest = gfc.select('treecover2000').gte(30);
function hansenLoss(y) { return hansenForest.and(gfc.select('lossyear').eq(ee.Number(y).subtract(2000))); }
// TMF: forest (undisturbed 1, degraded 2, regrowth 4) in December Y-1, deforested (3) in December Y.
function tmfLoss(y) {
  y = ee.Number(y).int();
  var before = tmf.select(ee.String('Dec').cat(y.subtract(1).format('%d')));
  var after = tmf.select(ee.String('Dec').cat(y.format('%d')));
  return before.remap([1, 2, 4], [1, 1, 1], 0).eq(1).and(after.eq(3));
}
var areaHa = ee.Image.pixelArea().divide(1e4);
var activity = ee.FeatureCollection(YEARS.map(function (y) {
  var img = ee.Image.cat(hansenLoss(y).rename('hansen_ha'), tmfLoss(y).rename('tmf_ha')).multiply(areaHa);
  var s = img.reduceRegion({reducer: ee.Reducer.sum(), geometry: district, scale: 30, maxPixels: 1e11, tileScale: 8});
  return ee.Feature(null, s).set('year', y);
}));
print(ui.Chart.feature.byFeature(activity, 'year', ['hansen_ha', 'tmf_ha'])
  .setChartType('ColumnChart')
  .setOptions({title: 'Forest lost per year in Tebo (ha): Hansen GFC and JRC TMF', colors: ['#2a78d6', '#eb6834']}));

// ---------------------------------------------------------------------------
// STEP 3. Emission factor from GEDI L4B over forest still intact in 2020
// ---------------------------------------------------------------------------
// TMF "undisturbed" in 2020 is the closest thing to "forest about to be
// cleared" available everywhere; a 1 km GEDI cell counts if half of it is intact.
var l4b = ee.Image('LARSE/GEDI/GEDI04_B_002');
var intact = tmf.select('Dec2020').eq(1);
var shareIntact = intact.reduceResolution({reducer: ee.Reducer.mean(), bestEffort: true, maxPixels: 2048})
  .reproject(l4b.projection());
var agbStats = l4b.select(['MU', 'SE']).updateMask(shareIntact.gte(0.5)).reduceRegion({
  reducer: ee.Reducer.mean().combine(ee.Reducer.count(), null, true),
  geometry: district, scale: 1000, maxPixels: 1e9});
var agb = ee.Number(agbStats.get('MU_mean'));
var ef = agb.multiply(1 + R).multiply(CF).multiply(44 / 12);
print('Emission factor', ee.Dictionary({gedi_cells: agbStats.get('MU_count'), agb_Mg_ha: agb,
  agb_se_Mg_ha: agbStats.get('SE_mean'), ef_tCO2_ha: ef}));

// ---------------------------------------------------------------------------
// STEP 4. Emissions, the reference level and the monitoring period
// ---------------------------------------------------------------------------
var emissions = activity.map(function (f) {
  return f.set({hansen_MtCO2: ee.Number(f.get('hansen_ha')).multiply(ef).divide(1e6),
                tmf_MtCO2: ee.Number(f.get('tmf_ha')).multiply(ef).divide(1e6)});
});
print(ui.Chart.feature.byFeature(emissions, 'year', ['hansen_MtCO2', 'tmf_MtCO2'])
  .setOptions({title: 'Emissions from deforestation, Tebo (Mt CO2 per year)', colors: ['#2a78d6', '#eb6834'], pointSize: 4}));
function periodMean(col, a, b) {
  return emissions.filter(ee.Filter.rangeContains('year', a, b)).aggregate_mean(col);
}
['hansen_MtCO2', 'tmf_MtCO2'].forEach(function (c) {
  var ref = ee.Number(periodMean(c, 2013, 2019)), mon = ee.Number(periodMean(c, 2020, 2023));
  print('Reference level vs monitoring, ' + c, ee.Dictionary({
    reference_Mt_yr: ref, monitoring_Mt_yr: mon, reduction_Mt_yr: ref.subtract(mon),
    reduction_share: ref.subtract(mon).divide(ref)}));
});

// ---------------------------------------------------------------------------
// STEP 5. Where the loss happened
// ---------------------------------------------------------------------------
var lossYear = gfc.select('lossyear').updateMask(
  hansenForest.and(gfc.select('lossyear').gte(13)).and(gfc.select('lossyear').lte(23))).add(2000).clip(district);
Map.centerObject(district, 9);
Map.addLayer(lossYear, {min: 2013, max: 2023, palette: ['fde725', '5ec962', '21918c', '3b528b', '440154']},
             'Hansen loss year 2013-2023');
Map.addLayer(ee.Image().paint(district, 0, 2), {palette: ['000000']}, 'Tebo district');
