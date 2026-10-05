//| title: Three ecosystem services, one landscape, one scenario
//| description: Water yield, carbon storage and habitat quality for the Bandung basin, their hotspots, and what a cropland expansion scenario costs.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 43 | Three services, one landscape, one scenario
 * ---------------------------------------------------------------------------
 *   water yield     P - ET (CHIRPS, MODIS MOD16), mm per year
 *   carbon storage  GEDI L4A biomass footprints averaged per land-cover class,
 *                   then mapped back by class (InVEST's carbon "lookup" logic)
 *   habitat         forest, discounted by closeness to built-up land
 *   scenario        forest within 500 m of cropland becomes cropland
 * Land cover: ESA WorldCover 2021, 10 m. Area: the Bandung basin, upper Citarum.
 */

// ---------------------------------------------------------------------------
// STEP 1. Area and land cover
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Rectangle([107.30, -7.35, 107.95, -6.75], null, false);
var wc = ee.Image('ESA/WorldCover/v200/2021').select('Map').clip(aoi);
var CODES = [10, 20, 30, 40, 50, 60, 80];   // tree, shrub, grass, crop, built-up, bare, water
var utm = ee.Projection('EPSG:32748').atScale(30);

// ---------------------------------------------------------------------------
// STEP 2. Water yield: P - ET, 2018-2023 mean (mm per year)
// ---------------------------------------------------------------------------
var P = ee.ImageCollection('UCSB-CHG/CHIRPS/PENTAD').select('precipitation')
  .filterDate('2018-01-01', '2024-01-01').sum().divide(6);
var ET = ee.ImageCollection('MODIS/061/MOD16A2GF').select('ET')
  .filterDate('2018-01-01', '2024-01-01').sum().multiply(0.1).divide(6);
// CHIRPS pixels are 5 km. The squares this leaves in the map are the true
// resolution of the rainfall data; smoothing them would only hide it.
var waterYield = P.subtract(ET).rename('water_mm').clip(aoi);

// ---------------------------------------------------------------------------
// STEP 3. Carbon: mean GEDI biomass per land-cover class, mapped back by class
// ---------------------------------------------------------------------------
var gedi = ee.ImageCollection('LARSE/GEDI/GEDI04_A_002_MONTHLY').filterBounds(aoi)
  .filterDate('2019-04-01', '2024-01-01')
  .map(function (i) { return i.updateMask(i.select('l4_quality_flag').eq(1).and(i.select('degrade_flag').eq(0))); })
  .select('agbd').mosaic();
var groups = ee.List(gedi.addBands(wc.rename('cls')).reduceRegion({
  reducer: ee.Reducer.mean().combine(ee.Reducer.count(), null, true).group(1, 'cls'),
  geometry: aoi, scale: 25, maxPixels: 1e10, tileScale: 8}).get('groups'));
var lookup = ee.FeatureCollection(groups.map(function (g) {
  g = ee.Dictionary(g);
  var m = g.get('mean', -1);                     // a class without GEDI shots has no mean
  return ee.Feature(null, {code: g.get('cls'), gedi_shots: g.get('count', 0), agbd_Mg_ha: m,
                           carbon_MgC_ha: ee.Number(m).multiply(0.47)});
})).filter(ee.Filter.inList('code', CODES)).filter(ee.Filter.gte('agbd_Mg_ha', 0));
print('Carbon lookup: GEDI footprints per land-cover class', lookup);
function carbonMap(lc) {
  return lc.remap(lookup.aggregate_array('code'), lookup.aggregate_array('carbon_MgC_ha')).rename('carbon');
}

// ---------------------------------------------------------------------------
// STEP 4. Habitat quality: forest, less valuable near built-up land
// ---------------------------------------------------------------------------
function habitatMap(lc) {
  var distKm = lc.eq(50).reproject(utm).fastDistanceTransform(256).sqrt().multiply(30).divide(1000);
  // 0 at a settlement edge, rising towards 1 far away
  return lc.eq(10).multiply(ee.Image(1).subtract(distKm.multiply(-1).divide(2).exp())).rename('habitat');
}

// ---------------------------------------------------------------------------
// STEP 5. Scenario: forest within 500 m of cropland becomes cropland
// ---------------------------------------------------------------------------
var nearCrop = wc.eq(40).reproject(utm).fastDistanceTransform(32).sqrt().multiply(30).lte(500);
var scenario = wc.where(wc.eq(10).and(nearCrop), 40);
// Mean ET per class moves water yield with land use in the scenario.
var etGroups = ee.List(ET.addBands(wc.rename('cls')).reduceRegion({
  reducer: ee.Reducer.mean().group(1, 'cls'), geometry: aoi, scale: 500, maxPixels: 1e10}).get('groups'));
var etCodes = etGroups.map(function (g) { return ee.Dictionary(g).get('cls'); });
var etVals = etGroups.map(function (g) { return ee.Dictionary(g).get('mean'); });
var pMean = ee.Number(P.reduceRegion({reducer: ee.Reducer.mean(), geometry: aoi, scale: 5000}).get('precipitation'));
function summarise(name, lc) {
  var area = ee.Image.pixelArea();
  var wy = ee.Image.constant(pMean).subtract(lc.remap(etCodes, etVals));
  var s = area.multiply(carbonMap(lc)).divide(1e4).rename('carbon_MgC')
    .addBands(area.multiply(wy).divide(1e3).rename('water_m3'))
    .addBands(habitatMap(lc).multiply(area).divide(1e4).rename('habitat_units_ha'))
    .addBands(area.updateMask(lc.eq(10)).divide(1e4).rename('forest_ha'))
    .reduceRegion({reducer: ee.Reducer.sum(), geometry: aoi, scale: 30, maxPixels: 1e11, tileScale: 8});
  print(name, s);
}
summarise('Services today (2021)', wc);
summarise('Services under the scenario', scenario);

// ---------------------------------------------------------------------------
// STEP 6. Maps: land cover, water yield and service hotspots
// ---------------------------------------------------------------------------
// A hotspot is the top 20 % of a service; each pixel counts 0 to 3 services.
function top(img) {
  var q = img.reduceRegion({reducer: ee.Reducer.percentile([80]), geometry: aoi, scale: 300,
                            maxPixels: 1e10, tileScale: 4}).values().get(0);
  return img.gte(ee.Number(q));
}
var hotspots = top(carbonMap(wc)).add(top(habitatMap(wc))).add(top(waterYield)).rename('n').clip(aoi);
Map.centerObject(aoi, 10);
Map.addLayer(wc, {min: 10, max: 80, palette: ['006400', 'ffbb22', 'ffff4c', 'f096ff', 'fa0000', 'b4b4b4', '000000', '0064c8']},
             'ESA WorldCover 2021');
Map.addLayer(waterYield, {min: 500, max: 3000, palette: ['fff7bc', 'c7e9b4', '41b6c4', '225ea8', '081d58']},
             'Water yield P - ET (mm/yr)', false);
Map.addLayer(hotspots, {min: 0, max: 3, palette: ['f0f0f0', 'fdcc8a', 'fc8d59', 'b30000']}, 'Service hotspots (0-3)');
Map.addLayer(scenario.neq(wc).selfMask(), {palette: ['f096ff']}, 'Scenario: forest turned to cropland', false);
