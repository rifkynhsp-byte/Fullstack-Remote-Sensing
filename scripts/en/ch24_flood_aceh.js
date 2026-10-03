//| title: Flood: terrain first, then the event, then who was exposed
//| description: HAND and drainage, Sentinel-1 flood extent for the November 2025 Sumatra floods in Aceh Tamiang, buildings and people inside.

/**
 * CHAPTER 24 | Flood mapping as a service
 * ---------------------------------------------------------------------------
 * Built from the beginning with public data, following the same approach
 * as the author's own (unpublished) flood explorer. Free to use and adapt:
 *   1. Terrain says where water CAN go: height above nearest drainage (HAND).
 *   2. Radar says where water IS: Sentinel-1 VV below -13 dB after the event,
 *      and at least 1.25 times darker than the dry-season baseline, on slopes
 *      under 5 degrees (radar shadow on ridges looks like water), minus
 *      permanent water.
 *   3. Exposure says who is affected: buildings and people inside.
 * Event: the floods of late November 2025, Aceh Tamiang district.
 */

var district = ee.FeatureCollection('FAO/GAUL/2025/level2')
  .filter(ee.Filter.eq('GAUL2_NAME', 'Aceh Tamiang'));
var aoi = district.geometry();

var CONFIG = {waterThreshold: -13.0, changeRatio: 1.25, slopeMax: 5};

// ---------------------------------------------------------------------------
// STEP 1. Terrain: where can water go?
// ---------------------------------------------------------------------------
var hydro = ee.Image('MERIT/Hydro/v1_0_1');
var hand = hydro.select('hnd').clip(aoi);
var rivers = hydro.select('upa').gt(100).selfMask().clip(aoi);   // > 100 km2 upstream
var slope = ee.Terrain.slope(ee.Image('NASA/NASADEM_HGT/001').select('elevation'));

// ---------------------------------------------------------------------------
// STEP 2. The event from radar (one orbit direction for both dates)
// ---------------------------------------------------------------------------
var s1 = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(aoi)
  .filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'))
  .select('VV');
var smooth = function (img) { return img.focal_median(50, 'circle', 'meters'); };
var baseline = smooth(s1.filterDate('2025-09-01', '2025-10-31').median());
var flooded = smooth(s1.filterDate('2025-11-26', '2025-11-30').mosaic());

var permanent = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gt(80);
// In dB, "1.25 times darker" is a drop of 10*log10(1.25) = 0.97 dB.
var flood = flooded.lt(CONFIG.waterThreshold)
  .and(baseline.subtract(flooded).gt(10 * Math.log(CONFIG.changeRatio) / Math.LN10))
  .and(slope.lt(CONFIG.slopeMax))
  .and(permanent.unmask(0).not())
  .selfMask().clip(aoi).rename('flood');

// ---------------------------------------------------------------------------
// STEP 3. Exposure
// ---------------------------------------------------------------------------
// Check a footprint layer's coverage before trusting it. Google Open Buildings
// v3 holds about 500 footprints for this whole district; Microsoft's (seven
// tiles for Indonesia) hold about 60,000. Merge the Microsoft tiles.
var buildings = ee.FeatureCollection([1, 2, 3, 4, 5, 6, 7].map(function (i) {
  return ee.FeatureCollection('projects/sat-io/open-datasets/MSBuildings/Indonesia/indonesia_' + i)
    .filterBounds(aoi);
})).flatten();
var worldpop = ee.ImageCollection('WorldPop/GP/100m/pop')
  .filter(ee.Filter.eq('country', 'IDN')).filter(ee.Filter.eq('year', 2020));
var people = worldpop.mosaic().setDefaultProjection(worldpop.first().projection());

var floodKm2 = flood.multiply(ee.Image.pixelArea()).divide(1e6)
  .reduceRegion({reducer: ee.Reducer.sum(), geometry: aoi, scale: 20, maxPixels: 1e10,
                 tileScale: 8}).get('flood');
var floodedBuildings = flood.unmask(0).reduceRegions({
  collection: buildings.map(function (b) { return ee.Feature(b.geometry().centroid(1)); }),
  reducer: ee.Reducer.first(), scale: 20, tileScale: 8
}).filter(ee.Filter.eq('first', 1)).size();
var share = flood.unmask(0).reproject(ee.Projection('EPSG:32647').atScale(20))
  .reduceResolution({reducer: ee.Reducer.mean(), maxPixels: 64})
  .reproject(people.projection());
var floodedPeople = people.updateMask(share.gt(0.5)).reduceRegion({
  reducer: ee.Reducer.sum(), geometry: aoi, scale: 100, maxPixels: 1e10}).values().get(0);
print('Flood extent (km2) and people:', floodKm2, floodedPeople);
// Counting ~60,000 footprints interactively times out. Export the count as a
// task instead (Tasks tab); the Python tab counts one tile at a time.
Export.table.toDrive({
  collection: ee.FeatureCollection([ee.Feature(null, {buildings_in_flood: floodedBuildings})]),
  description: 'aceh_tamiang_flooded_buildings', fileFormat: 'CSV'});

Map.centerObject(aoi, 10);
Map.addLayer(hand, {min: 0, max: 20, palette: ['#08306b', '#6baed6', '#f7fbff']}, 'HAND (m)', false);
Map.addLayer(flooded, {min: -25, max: 0}, 'VV after, 26-30 Nov 2025', false);
Map.addLayer(flood, {palette: ['#00d0ff']}, 'Flood extent');
Map.addLayer(rivers, {palette: ['#08306b']}, 'Rivers');

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. How much of the flood lies below 5 m HAND? What does the rest tell you?
// 2. Repeat with ASCENDING passes on 2025-11-28. Where do the two differ?
