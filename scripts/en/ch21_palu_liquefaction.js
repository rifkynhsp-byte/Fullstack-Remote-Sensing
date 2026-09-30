//| title: Palu, 28 September 2018: before, after, and who was exposed
//| description: Sentinel-2 change after the Palu earthquake, split into coastal and inland zones, with buildings and people inside.

/**
 * CHAPTER 21 | A disaster seen twice, a week apart
 * ---------------------------------------------------------------------------
 * From the GEE101 course (Palu liquefaction). The M7.5 earthquake of
 * 28 September 2018 turned whole neighbourhoods of Petobo and Balaroa into
 * flowing mud, and a tsunami struck the bay shore the same evening. Both
 * leave the same trace from orbit: vegetation and roofs replaced by bare,
 * bright ground. Distance from the bay separates the two.
 *
 * The original exercise used uploaded imagery that is no longer available;
 * this version uses public Sentinel-2, Open Buildings and WorldPop.
 */

var palu = ee.Geometry.Rectangle([119.84, -0.98, 119.94, -0.87]);

var prep = function (image) {
  var qa = image.select('QA60');
  var clear = qa.bitwiseAnd(1 << 10).eq(0).and(qa.bitwiseAnd(1 << 11).eq(0));
  var s = image.updateMask(clear).divide(10000);
  return s.addBands(s.normalizedDifference(['B8', 'B4']).rename('ndvi'));
};
var s2 = ee.ImageCollection('COPERNICUS/S2_HARMONIZED').filterBounds(palu);
var before = s2.filterDate('2018-07-01', '2018-09-27')
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 40)).map(prep).median();
var after = s2.filterDate('2018-09-29', '2018-11-30')
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60)).map(prep).median();

// Change: vegetation or roofs gone, bare bright ground left behind.
var dNdvi = after.select('ndvi').subtract(before.select('ndvi'));
var dBright = after.select(['B2', 'B3', 'B4']).reduce(ee.Reducer.mean())
  .subtract(before.select(['B2', 'B3', 'B4']).reduce(ee.Reducer.mean()));
var land = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').unmask(0).lt(50);
var changed = dNdvi.lt(-0.2).and(dBright.gt(0.02)).and(land);
// Drop speckles under half a hectare (50 pixels of 100 m²).
changed = changed.updateMask(changed.connectedPixelCount(100).gte(50)).selfMask();

// Coastal (tsunami) or inland (liquefaction)? Distance from the bay.
var sea = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gt(80);
// Distance needs a grid in metres: unprojected, it would measure in degrees
// and call every pixel coastal. 30 m UTM, 256 pixels = 7.7 km search radius.
var distSea = sea.unmask(0).reproject(ee.Projection('EPSG:32750').atScale(30))
  .fastDistanceTransform(256).sqrt().multiply(30);
var inland = changed.and(distSea.gt(500)).selfMask();    // keep only the 1s
var coastal = changed.and(distSea.lte(500)).selfMask();

// Who and what was inside?
var buildings = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons')
  .filterBounds(palu).filter(ee.Filter.gte('confidence', 0.75));
var worldpop = ee.ImageCollection('WorldPop/GP/100m/pop')
  .filter(ee.Filter.eq('country', 'IDN')).filter(ee.Filter.eq('year', 2018));
// mosaic() forgets the native grid; give it back.
var people = worldpop.mosaic().setDefaultProjection(worldpop.first().projection());
var zoneStats = function (mask, label) {
  var ha = mask.unmask(0).multiply(ee.Image.pixelArea()).divide(1e4)
    .reduceRegion({reducer: ee.Reducer.sum(), geometry: palu, scale: 10, maxPixels: 1e9})
    .values().get(0);
  var hits = mask.unmask(0).reduceRegions({
    collection: buildings.map(function (b) { return ee.Feature(b.geometry().centroid(1)); }),
    reducer: ee.Reducer.first(), scale: 10}).filter(ee.Filter.eq('first', 1)).size();
  // A median composite has no fixed grid: pin the mask to 10 m UTM first,
  // then ask what share of each 100 m population cell it covers.
  var share = mask.unmask(0).reproject(ee.Projection('EPSG:32750').atScale(10))
    .reduceResolution({reducer: ee.Reducer.mean(), maxPixels: 256})
    .reproject(people.projection());
  var pop = people.updateMask(share.gt(0.5))
    .reduceRegion({reducer: ee.Reducer.sum(), geometry: palu, scale: 100}).values().get(0);
  return ee.Feature(null, {zone: label, changed_ha: ha, buildings: hits, people: pop});
};
print('Exposure by zone', ee.FeatureCollection([
  zoneStats(inland, 'inland (liquefaction flow slides)'),
  zoneStats(coastal, 'within 500 m of the bay (tsunami)')]));

Map.centerObject(palu, 13);
Map.addLayer(before, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.25}, 'Before');
Map.addLayer(after, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.25}, 'After');
Map.addLayer(inland, {palette: ['#d7301f']}, 'Inland change');
Map.addLayer(coastal, {palette: ['#2171b5']}, 'Coastal change');

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Zoom to Petobo (119.915, -0.955). How much of the red zone is one
//    connected flow slide, and how much is scattered noise?
// 2. Raise the dNDVI threshold to -0.3. Which exposure number changes most?
