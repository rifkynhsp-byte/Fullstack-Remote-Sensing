//| title: How much electricity could the sun give here?
//| description: Solar resource from ERA5-Land, a performance ratio calibrated on Cirata floating PV, and the potential of Bandung rooftops, the Saguling reservoir and open land.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 64 | How much electricity could the sun give here?
 * ---------------------------------------------------------------------------
 *  1. resource   ERA5-Land monthly, 2019-2023: global horizontal irradiance (GHI,
 *                surface solar radiation downwards, J/m2 -> kWh/m2), 2 m air
 *                temperature and rainfall
 *  2. calibrate  Cirata floating PV: 192 MWp, 245-300 GWh/yr reported. With
 *                Cirata's GHI this gives the specific yield (kWh/kWp/yr) and the
 *                performance ratio PR = yield / GHI. Density: 192 MWp on about
 *                260 ha including the water lanes (Chapter 57).
 *  3. rooftops   North Bandung: Google Open Buildings v3 (confidence >= 0.75),
 *                30 % of each roof covered with 0.2 kWp/m2 modules
 *  4. reservoir  Saguling: floating panels on 5, 10 or 20 % of the surface
 *  5. land       open land on slopes < 10 deg outside protected areas, Bandung basin
 *  6. needs      a planning assumption of 150 kWh per household per month
 */

// ---------------------------------------------------------------------------
// STEP 1. The resource at four sites
// ---------------------------------------------------------------------------
var ERA = ee.ImageCollection('ECMWF/ERA5_LAND/MONTHLY_AGGR').filterDate('2019-01-01', '2024-01-01')
  .select(['surface_solar_radiation_downwards_sum', 'temperature_2m', 'total_precipitation_sum'], ['ghi', 't2m', 'rain']);
var SITES = ee.FeatureCollection([
  ee.Feature(ee.Geometry.Point([107.334, -6.704]), {site: 'Cirata (floating PV)'}),
  ee.Feature(ee.Geometry.Point([107.61, -6.87]), {site: 'North Bandung'}),
  ee.Feature(ee.Geometry.Point([107.40, -6.92]), {site: 'Saguling reservoir'}),
  ee.Feature(ee.Geometry.Point([123.61, -10.17]), {site: 'Kupang, NTT'})]);
// GHI in kWh/m2 per day: J/m2 per month / 3.6e6 / 30.4 days
var ghiDaily = ERA.select('ghi').map(function (i) {
  return i.divide(3.6e6).divide(30.4).copyProperties(i, ['system:time_start']);
});
print(ui.Chart.image.seriesByRegion(ghiDaily, SITES, ee.Reducer.first(), 'ghi', 11132, 'system:time_start', 'site')
  .setOptions({title: 'Global horizontal irradiance, monthly mean (kWh/m2 per day), ERA5-Land', lineWidth: 1, pointSize: 2}));
var ghiYear = ghiDaily.mean().multiply(365).rename('ghi_year');
var siteGhi = ghiYear.reduceRegions({collection: SITES, reducer: ee.Reducer.first(), scale: 11132});
print('GHI per year at each site (kWh/m2)', siteGhi);
function ghiAt(name) { return ee.Number(siteGhi.filter(ee.Filter.eq('site', name)).first().get('first')); }

// ---------------------------------------------------------------------------
// STEP 2. Calibrate on Cirata: specific yield and performance ratio
// ---------------------------------------------------------------------------
var CIRATA_MWP = 192, OUTLINE_HA = 260;
var cirataGhi = ghiAt('Cirata (floating PV)');
var prLow = ee.Number(245e6).divide(CIRATA_MWP * 1e3).divide(cirataGhi);   // 245 GWh/yr reported
var prHigh = ee.Number(300e6).divide(CIRATA_MWP * 1e3).divide(cirataGhi);  // 300 GWh/yr reported
print('Cirata performance ratio (low, high)', ee.List([prLow, prHigh]));

// ---------------------------------------------------------------------------
// STEP 3. North Bandung rooftops
// ---------------------------------------------------------------------------
var northBandung = ee.Geometry.Rectangle([107.585, -6.885, 107.635, -6.855], null, false);
var buildings = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons')
  .filterBounds(northBandung).filter(ee.Filter.gte('confidence', 0.75));
var n = buildings.size(), roof = ee.Number(buildings.aggregate_sum('area_in_meters'));
var kwp = roof.multiply(0.30).multiply(0.20);
var bandungGhi = ghiAt('North Bandung');
function perBuildingMonth(pr) { return kwp.multiply(bandungGhi).multiply(pr).divide(n).divide(12); }   // kWh
print('North Bandung rooftops', ee.Dictionary({buildings: n, roof_ha: roof.divide(1e4), mwp: kwp.divide(1000),
  kwh_per_building_month_low: perBuildingMonth(prLow), kwh_per_building_month_high: perBuildingMonth(prHigh),
  share_of_150kwh_need_low: perBuildingMonth(prLow).divide(150)}));

// ---------------------------------------------------------------------------
// STEP 4. Saguling reservoir: floating PV at Cirata's density
// ---------------------------------------------------------------------------
var sagulingBox = ee.Geometry.Rectangle([107.30, -7.00, 107.50, -6.85], null, false);
var waterHa = ee.Number(ee.Image.pixelArea().divide(1e4)
  .updateMask(ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gte(80))
  .reduceRegion({reducer: ee.Reducer.sum(), geometry: sagulingBox, scale: 30, maxPixels: 1e10}).values().get(0));
var sagulingGhi = ghiAt('Saguling reservoir');
print('Saguling reservoir (ha of permanent water)', waterHa);
[0.05, 0.10, 0.20].forEach(function (cover) {
  var mwp = waterHa.multiply(cover).multiply(CIRATA_MWP / OUTLINE_HA);
  var gwh = mwp.multiply(1e3).multiply(sagulingGhi).multiply(prLow).divide(1e6);
  print('Saguling, ' + cover * 100 + ' % covered (low PR)', ee.Dictionary({mwp: mwp, gwh_per_year: gwh,
    households_at_150kwh: gwh.multiply(1e6).divide(150 * 12)}));
});

// ---------------------------------------------------------------------------
// STEP 5. Open land in the Bandung basin
// ---------------------------------------------------------------------------
var basin = ee.Geometry.Rectangle([107.25, -7.15, 107.95, -6.75], null, false);
var dw = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(basin).filterDate('2024-01-01', '2025-01-01').select('label').mode();
var slope = ee.Terrain.slope(ee.ImageCollection('COPERNICUS/DEM/GLO30').select('DEM').mosaic()
  .setDefaultProjection(ee.Projection('EPSG:4326').atScale(30)));
var protectedAreas = ee.Image(0).paint(ee.FeatureCollection('WCMC/WDPA/current/polygons').filterBounds(basin), 1);
var suitable = dw.eq(2).or(dw.eq(5)).or(dw.eq(7)).and(slope.lt(10)).and(protectedAreas.not()).selfMask().clip(basin);
var landHa = ee.Number(ee.Image.pixelArea().divide(1e4).updateMask(suitable)
  .reduceRegion({reducer: ee.Reducer.sum(), geometry: basin, scale: 30, maxPixels: 1e10, tileScale: 8}).values().get(0));
var landMwp = landHa.multiply(CIRATA_MWP / OUTLINE_HA);
print('Open land in the basin', ee.Dictionary({suitable_ha: landHa, mwp_at_cirata_density: landMwp,
  gwh_per_year_low: landMwp.multiply(1e3).multiply(bandungGhi).multiply(prLow).divide(1e6)}));

// ---------------------------------------------------------------------------
// STEP 6. Maps
// ---------------------------------------------------------------------------
Map.centerObject(basin, 10);
Map.addLayer(ghiDaily.mean(), {min: 4, max: 6, palette: ['ffffcc', 'fed976', 'fd8d3c', 'e31a1c', '800026']},
             'GHI 2019-2023 (kWh/m2 per day)', false);
Map.addLayer(suitable, {palette: ['d95f02']}, 'Open land, slope < 10 deg, not protected');
Map.addLayer(buildings, {color: '2a78d6'}, 'North Bandung buildings (Open Buildings v3)', false);
