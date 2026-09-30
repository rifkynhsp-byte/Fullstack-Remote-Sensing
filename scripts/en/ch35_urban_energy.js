//| title: Urban heat and a solar site screen
//| description: Landsat land surface temperature of Surabaya by land cover, and a weighted-overlay screen for solar farms on Sumbawa built from public layers.

/**
 * CHAPTER 35 | Two planning questions
 * ---------------------------------------------------------------------------
 *   1. Where is the city hottest, and what covers that ground?
 *   2. Where could a solar farm go? A multi-criteria screen: score each
 *      criterion 0-1, weight, add, and blank out land that is ruled out.
 */

// ---- 1. Urban heat, Surabaya, dry season 2023 -------------------------------
var city = ee.Geometry.Rectangle([112.55, -7.40, 112.85, -7.15], null, false);

function clearLst(img) {
  var qa = img.select('QA_PIXEL');
  var clear = qa.bitwiseAnd(1 << 3).eq(0).and(qa.bitwiseAnd(1 << 4).eq(0));
  return img.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15)
    .rename('lst').updateMask(clear);
}
var lst = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')
  .merge(ee.ImageCollection('LANDSAT/LC08/C02/T1_L2'))
  .filterBounds(city).filterDate('2023-06-01', '2023-11-01')
  .filter(ee.Filter.lt('CLOUD_COVER', 40))
  .map(clearLst).median().clip(city);
Map.centerObject(city, 11);
Map.addLayer(lst, {min: 28, max: 46,
  palette: ['313695', '74add1', 'e0f3f8', 'fee090', 'f46d43', 'a50026']}, 'LST 2023 (°C)');

// Mean temperature per Dynamic World class (0 water, 1 trees, 4 crops, 6 built ...).
var dw = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(city)
  .filterDate('2023-01-01', '2024-01-01').select('label').mode();
print('LST by land cover class', lst.addBands(dw.rename('cls')).reduceRegion({
  reducer: ee.Reducer.mean().group({groupField: 1, groupName: 'cls'}),
  geometry: city, scale: 30, maxPixels: 1e9, tileScale: 4}).get('groups'));

// ---- 2. Solar farm screen, Sumbawa -------------------------------------------
var island = ee.Geometry.Rectangle([116.75, -9.10, 118.20, -8.35], null, false);
var utm = ee.Projection('EPSG:32750').atScale(100);

var ghi = ee.ImageCollection('ECMWF/ERA5_LAND/MONTHLY_AGGR')
  .filterDate('2023-01-01', '2024-01-01')
  .select('surface_solar_radiation_downwards_sum').sum().divide(3.6e6);   // kWh/m²/yr
var dem = ee.ImageCollection('COPERNICUS/DEM/GLO30').filterBounds(island).select('DEM')
  .mosaic().setDefaultProjection('EPSG:4326', null, 30);
var slope = ee.Terrain.slope(dem);
var built = ee.Image('JRC/GHSL/P2023A/GHS_BUILT_S/2020').select('built_surface').gt(500);
var distKm = built.unmask(0).reproject(utm).fastDistanceTransform(256).sqrt()
  .multiply(100).divide(1000);

var dwIsland = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(island)
  .filterDate('2023-01-01', '2024-01-01').select('label').mode();
var prot = ee.FeatureCollection('WCMC/WDPA/current/polygons').filterBounds(island)
  .reduceToImage(['WDPAID'], ee.Reducer.first()).gt(0).unmask(0);
var allowed = dem.gt(0).and(dwIsland.remap([0, 1, 3, 6], [0, 0, 0, 0], 1).eq(1))
  .and(prot.eq(0)).and(slope.lte(15));

// Scores 0-1. Sunshine is stretched between its 5th and 95th percentile.
var g = ghi.reduceRegion(ee.Reducer.percentile([5, 95]), island, 10000);
var gLo = ee.Number(g.values().get(0)), gHi = ee.Number(g.values().get(1));
var sun = ghi.subtract(gLo).divide(gHi.subtract(gLo)).clamp(0, 1);
var flat = slope.divide(10).multiply(-1).add(1).clamp(0, 1);      // 1 at 0°, 0 at 10°
var near = distKm.divide(20).multiply(-1).add(1).clamp(0, 1);     // 1 at 0 km, 0 at 20 km

var score = sun.multiply(0.4).add(flat.multiply(0.3)).add(near.multiply(0.3))
  .updateMask(allowed).rename('score');
Map.addLayer(score.clip(island), {min: 0.5, max: 1,
  palette: ['d7191c', 'fdae61', 'a6d96a', '1a9641']}, 'Solar suitability', false);

// The top 10 % of allowed land: change the weights above and watch it move.
var p90 = score.reduceRegion(ee.Reducer.percentile([90]), island, 100, null, null, false,
                             1e10, 8).get('score');
print('Score that starts the top 10 %', p90);
Map.addLayer(score.gte(ee.Number(p90)).selfMask().clip(island), {palette: ['1a9641']},
             'Top 10 %', false);
