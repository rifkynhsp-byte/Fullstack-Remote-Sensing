//| title: From a map to a case file
//| description: Forest clearing inside Gunung Leuser National Park as a list of dated, located cases with before and after imagery, and river gold mining near Merangin, Jambi.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 55 | From a map to a case file
 * ---------------------------------------------------------------------------
 * An enforcement officer does not need a pretty map. They need: WHERE
 * (coordinates), WHEN (a date window, bracketed by two dated images), HOW
 * MUCH (area), and HOW WE KNOW (a method anyone can rerun).
 *   A  protected-area encroachment: Hansen loss inside Gunung Leuser National
 *      Park against a 5 km band outside, and the largest recent clearings
 *   B  river gold mining (PETI): vegetation in 2019 that became bare ground or
 *      turbid water by 2024 within 1 km of a river, Merangin, Jambi
 * Satellites find LEADS. Whether a clearing is illegal depends on permits and
 * boundaries only the authorities hold. The output is a list to inspect.
 */

// ---------------------------------------------------------------------------
// STEP 1. A: the park, a 5 km band, and forest loss
// ---------------------------------------------------------------------------
var gfc = ee.Image('UMD/hansen/global_forest_change_2025_v1_13');
var lossyear = gfc.select('lossyear').unmask(0);
var forest2000 = gfc.select('treecover2000').gte(30);
var LAST = 24;                                                    // last loss year used (2024)
var park = ee.FeatureCollection('WCMC/WDPA/current/polygons')
  .filter(ee.Filter.eq('NAME', 'Gunung Leuser')).geometry().simplify(100);
var band5k = park.buffer(5000, 100).difference(park, 100);

// ---------------------------------------------------------------------------
// STEP 2. Hectares cleared per year, inside and just outside
// ---------------------------------------------------------------------------
var zone = ee.Image(0).paint(ee.FeatureCollection([ee.Feature(band5k)]), 2)
  .paint(ee.FeatureCollection([ee.Feature(park)]), 1).rename('zone');
var lossImg = ee.Image.pixelArea().divide(1e4).updateMask(forest2000)
  .addBands(lossyear.rename('year')).addBands(zone).updateMask(lossyear.gt(0).and(lossyear.lte(LAST)));
print('Forest lost per year (ha): zone 1 inside the park, 2 the 5 km band (year = 2000 + group)',
      lossImg.reduceRegion({reducer: ee.Reducer.sum().group(1, 'year').group(2, 'zone'),
                            geometry: park.buffer(5000, 100), scale: 30, maxPixels: 1e11, tileScale: 16}).get('groups'));

// ---------------------------------------------------------------------------
// STEP 3. The case list: the ten largest clearings of 2021-2024 inside the park
// ---------------------------------------------------------------------------
var recent = lossyear.gte(21).and(lossyear.lte(LAST)).and(forest2000).selfMask();
var patches = recent.addBands(lossyear.rename('year'))
  .reduceToVectors({geometry: park, scale: 30, geometryType: 'polygon', eightConnected: true,
                    labelProperty: 'lost', reducer: ee.Reducer.mode(), maxPixels: 1e10, tileScale: 8})
  .map(function (f) { return f.set('ha', f.geometry().area(10).divide(1e4)); });
var cases = patches.sort('ha', false).limit(10).map(function (f) {
  var c = f.geometry().centroid(10).coordinates();
  return f.set({loss_year: ee.Number(f.get('mode')).add(2000), lon: c.get(0), lat: c.get(1)});
});
print('Cases: the ten largest recent clearings (loss_year, ha, lon, lat)', cases.select(['loss_year', 'ha', 'lon', 'lat'], null, false));

// ---------------------------------------------------------------------------
// STEP 4. Evidence for case 1: the year before and the year after
// ---------------------------------------------------------------------------
function s2(start, end, region) {
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(region).filterDate(start, end)
    .linkCollection(ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'), ['cs'])
    .map(function (i) { return i.updateMask(i.select('cs').gte(0.6)).divide(10000); }).median();
}
var top = ee.Feature(cases.first());
var topYear = ee.Number(top.get('loss_year'));
var boxA = top.geometry().bounds(10).buffer(600, 10).bounds(10);
function evidence(offset) {
  var y = topYear.add(offset);
  return s2(ee.Date.fromYMD(y, 1, 1), ee.Date.fromYMD(y, 12, 31), boxA)
    .visualize({bands: ['B4', 'B3', 'B2'], min: 0.01, max: 0.12, gamma: 1.2})
    .blend(ee.Image().byte().paint(ee.FeatureCollection([top]), 1, 2).visualize({palette: ['ffff00']}));
}
Map.centerObject(boxA, 15);
Map.addLayer(evidence(-1), {}, 'Case 1: the year before');
Map.addLayer(evidence(1), {}, 'Case 1: the year after');

// ---------------------------------------------------------------------------
// STEP 5. B: river gold mining near Merangin
// ---------------------------------------------------------------------------
var aoiB = ee.Geometry.Rectangle([101.90, -2.45, 102.70, -1.95], null, false);
var water = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('max_extent');
var nearRiver = water.focalMax(1000, 'circle', 'meters').and(water.not()).or(water).rename('near');  // channel plus 1 km
var built = ee.ImageCollection('ESA/WorldCover/v200').first().eq(50);
function dry(year) { return s2(ee.Date.fromYMD(year, 5, 1), ee.Date.fromYMD(year, 10, 31), aoiB); }   // May-October
function ndvi(img) { return img.normalizedDifference(['B8', 'B4']); }
function bareNearRiver(img) { return ndvi(img).lt(0.2).and(img.select('B4').gt(0.06)).and(nearRiver).and(built.not()); }
var before = dry(2019), after = dry(2024);                         // 2018 has one usable scene here
var mining = ndvi(before).gt(0.5).and(bareNearRiver(after)).selfMask();
var miningClean = mining.updateMask(mining.connectedPixelCount(50, true).gte(10));   // >= 0.1 ha
var areaHa = ee.Image.pixelArea().divide(1e4);
var perYear = ee.FeatureCollection(ee.List.sequence(2019, 2024).map(function (y) {
  var ha = areaHa.updateMask(bareNearRiver(dry(y))).reduceRegion({reducer: ee.Reducer.sum(), geometry: aoiB, scale: 60,
                                                                   maxPixels: 1e11, tileScale: 16}).values().get(0);
  return ee.Feature(null, {year: y, bare_or_turbid_near_rivers_ha: ha});
}));
print(ui.Chart.feature.byFeature(perYear, 'year', 'bare_or_turbid_near_rivers_ha').setChartType('ColumnChart')
  .setOptions({title: 'Bare ground or turbid water within 1 km of rivers, Merangin, dry season (ha)', colors: ['#b8433a']}));
Map.addLayer(after.visualize({bands: ['B4', 'B3', 'B2'], min: 0.01, max: 0.14, gamma: 1.2}), {}, 'Merangin, dry season 2024', false);
Map.addLayer(miningClean, {palette: ['ff00ff']}, 'Vegetated in 2019, bare or turbid by 2024, near a river', false);
