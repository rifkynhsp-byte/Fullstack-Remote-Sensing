//| title: Watching a power plant appear on a lake
//| description: Find the Cirata floating solar plant on the reservoir, separate it from old fish cages, measure its area against the reported 200 ha, and date it with Sentinel-1.

/**
 * CHAPTER 57 | Watching a power plant appear on a lake
 * ---------------------------------------------------------------------------
 * Cirata floating PV: 192 MWp on about 200 ha of the reservoir, inaugurated
 * on 9 November 2023 (reported figures). From space:
 *   1. reservoir  JRC water occurrence >= 80 % (always water, 1984-2021)
 *   2. panels     open water in the 2021 dry season, not water in the 2024 dry
 *                 season (Sentinel-2 SWIR B11 < 0.05 = water)
 *   3. cages      not water in BOTH years: the old floating fish cages
 *                 (keramba jaring apung), which are not the plant
 *   4. size       largest connected patch of new non-water, against 200 ha
 *   5. timeline   Sentinel-1 VV backscatter over that patch, every month:
 *                 calm water is dark to radar, metal frames and panels are bright
 */

// ---------------------------------------------------------------------------
// STEP 1. The reservoir and two dry seasons
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Rectangle([107.18, -6.84, 107.42, -6.62], null, false);
var reservoir = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gte(80).unmask(0).clip(aoi);
var REPORTED_HA = 200;
function s2(start, end) {
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(aoi).filterDate(start, end)
    .linkCollection(ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'), ['cs'])
    .map(function (i) { return i.updateMask(i.select('cs').gte(0.6)).divide(10000); })
    .median().select(['B2', 'B3', 'B4', 'B8', 'B11', 'B12']);
}
var before = s2('2021-05-01', '2021-10-31'), after = s2('2024-05-01', '2024-10-31');

// ---------------------------------------------------------------------------
// STEP 2. Water, panels and cages
// ---------------------------------------------------------------------------
// Open water absorbs shortwave infrared almost completely (B11 about 0.015).
// NDWI is NOT used: grey panels on water still give a positive NDWI.
function water(img) { return img.select('B11').lt(0.05); }
var notGreen = after.normalizedDifference(['B8', 'B4']).lt(0.1);   // floating weeds are green; panels are not
var newFloat = reservoir.and(water(before)).and(water(after).not()).and(notGreen);
var cages = reservoir.and(water(before).not()).and(water(after).not());
var newClean = newFloat.updateMask(newFloat.connectedPixelCount(1024, true).gte(100)).selfMask();

// ---------------------------------------------------------------------------
// STEP 3. The plant: the largest patch of new floating material
// ---------------------------------------------------------------------------
// Panel rows have water lanes between them; a 30 m grid and one dilation merge them into one outline.
var grid30 = ee.Projection('EPSG:32748').atScale(30);
var merged = newFloat.reproject(grid30).unmask(0).focalMax(3, 'square', 'pixels').reproject(grid30).selfMask();
merged = merged.updateMask(merged.connectedPixelCount(1024, true).gte(50));
var patches = merged.reduceToVectors({geometry: aoi, crs: grid30, eightConnected: true, maxPixels: 1e10, tileScale: 8});
var plant = ee.Feature(patches.map(function (f) { return f.set('ha', f.geometry().area(5).divide(1e4)); })
  .sort('ha', false).first());
var plantZone = plant.geometry();
var plantPx = newClean.clip(plantZone);
var area = ee.Image.pixelArea().divide(1e4);
function ha(img, geom) {
  return area.updateMask(img).reduceRegion({reducer: ee.Reducer.sum(), geometry: geom, scale: 10, maxPixels: 1e10}).values().get(0);
}
print('Cirata floating PV', ee.Dictionary({detected_plant_ha: ha(plantPx, plantZone), reported_ha: REPORTED_HA,
  plant_outline_ha: plant.get('ha'), old_fish_cages_ha: ha(cages, aoi), reservoir_ha: ha(reservoir.selfMask(), aoi),
  plant_centre: plantZone.centroid(10).coordinates()}));

// ---------------------------------------------------------------------------
// STEP 4. The timeline from radar: when did the panels arrive?
// ---------------------------------------------------------------------------
var s1 = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(plantZone).filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')).filterDate('2021-01-01', '2025-01-01').select('VV');
var waterRef = reservoir.and(water(after)).and(plantPx.unmask(0).not()).selfMask();
var monthly = ee.FeatureCollection(ee.List.sequence(0, 47).map(function (m) {
  var start = ee.Date('2021-01-01').advance(m, 'month');
  var img = s1.filterDate(start, start.advance(1, 'month')).mean();
  return ee.Feature(null, {'system:time_start': start.millis(),
    plant_VV_dB: img.updateMask(plantPx).reduceRegion({reducer: ee.Reducer.mean(), geometry: plantZone, scale: 20, maxPixels: 1e9}).get('VV'),
    open_water_VV_dB: img.updateMask(waterRef).reduceRegion({reducer: ee.Reducer.mean(), geometry: plantZone.buffer(2000), scale: 20, maxPixels: 1e9}).get('VV')});
}));
print(ui.Chart.feature.byFeature(monthly, 'system:time_start', ['plant_VV_dB', 'open_water_VV_dB'])
  .setOptions({title: 'Sentinel-1 VV over the plant and over open water, monthly 2021-2024 (dB)',
               colors: ['#d000ff', '#2a78d6'], lineWidth: 2, pointSize: 3}));

// ---------------------------------------------------------------------------
// STEP 5. Maps: before, after, and what is what
// ---------------------------------------------------------------------------
var rgb = {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.12, gamma: 1.3};
Map.centerObject(plantZone, 14);
Map.addLayer(before, rgb, 'Dry season 2021');
Map.addLayer(after, rgb, 'Dry season 2024');
Map.addLayer(cages.selfMask(), {palette: ['ff7f00']}, 'Old fish cages (not water in both years)');
Map.addLayer(newClean, {palette: ['d000ff']}, 'New floating material: the PV plant');
Map.addLayer(ee.Image().byte().paint(ee.FeatureCollection([plant]), 1, 2), {palette: ['ffff00']}, 'Plant outline');
