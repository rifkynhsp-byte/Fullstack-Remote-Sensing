//| title: Change through time with Dynamic World
//| description: Yearly built-up area 2016 to 2024 in the GEE101 Lampung study area, from Dynamic World.

/**
 * CHAPTER 21 | Near real time land cover, and what a yearly count hides
 * ---------------------------------------------------------------------------
 * Dynamic World gives a class and nine class probabilities for every
 * Sentinel-2 scene since 2015. From the GEE101 course: map one scene with
 * its confidence as relief, then count built-up land year by year.
 *
 * A bug worth knowing about: the original exercise extracted built-up land
 * with label == 2. In Dynamic World 2 is GRASS; BUILT is 6. The map looked
 * reasonable, because grass and new suburbs sit next to each other. Look up
 * a class index, never remember it.
 */

var area = ee.Geometry.Rectangle([105.16, -4.10, 105.28, -4.02]);   // GEE101 Lampung area
var CLASSES = ['water', 'trees', 'grass', 'flooded_vegetation', 'crops',
               'shrub_and_scrub', 'built', 'bare', 'snow_and_ice'];
var BUILT = CLASSES.indexOf('built');   // 6
var palette = ['#419BDF', '#397D49', '#88B053', '#7A87C6', '#E49635',
               '#DFC35A', '#C4281B', '#A59B8F', '#B39FE1'];

var dw = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(area);

// ---------------------------------------------------------------------------
// STEP 1. One year as a map: the most frequent label, shaded by confidence
// ---------------------------------------------------------------------------
var yearComposite = function (year) {
  var yr = dw.filterDate(ee.Date.fromYMD(year, 1, 1), ee.Date.fromYMD(year + 1, 1, 1));
  var label = yr.select('label').reduce(ee.Reducer.mode()).rename('label');
  var confidence = yr.select(CLASSES).mean().reduce(ee.Reducer.max());
  return label.addBands(confidence.rename('confidence')).set('year', year);
};
var y2024 = yearComposite(2024);
var shaded = y2024.select('label').visualize({min: 0, max: 8, palette: palette})
  .divide(255).multiply(ee.Terrain.hillshade(y2024.select('confidence').multiply(100)).divide(255));
Map.centerObject(area, 13);
Map.addLayer(shaded, {min: 0, max: 0.8}, 'Dynamic World 2024, shaded by confidence');

// ---------------------------------------------------------------------------
// STEP 2. Count built-up land every year
// ---------------------------------------------------------------------------
var builtKm2 = function (year) {
  var c = yearComposite(year);
  var km2 = c.select('label').eq(BUILT).multiply(ee.Image.pixelArea()).divide(1e6)
    .reduceRegion({reducer: ee.Reducer.sum(), geometry: area, scale: 10, maxPixels: 1e9})
    .get('label');
  var yr = dw.filterDate(ee.Date.fromYMD(year, 1, 1), ee.Date.fromYMD(year + 1, 1, 1));
  // The steadier alternative: average the 'built' probability over the year.
  var km2Prob = yr.select('built').mean().gt(0.5).multiply(ee.Image.pixelArea()).divide(1e6)
    .reduceRegion({reducer: ee.Reducer.sum(), geometry: area, scale: 10, maxPixels: 1e9})
    .get('built');
  return ee.Feature(null, {year: year, built_km2: km2, built_km2_prob: km2Prob,
                           scenes: yr.size()});
};
var series = ee.FeatureCollection(ee.List.sequence(2016, 2024).map(builtKm2));
print('Built-up area by year', series);
print(ui.Chart.feature.byFeature(series, 'year', ['built_km2', 'built_km2_prob'])
  .setOptions({title: 'Built-up area, Dynamic World yearly mode',
               vAxis: {title: 'km²'}, hAxis: {format: '####'}, pointSize: 4}));

// ---------------------------------------------------------------------------
// STEP 3. Where did it change? New built-up land, 2017 to 2024
// ---------------------------------------------------------------------------
var newBuilt = yearComposite(2024).select('label').eq(BUILT)
  .and(yearComposite(2017).select('label').neq(BUILT));
Map.addLayer(newBuilt.selfMask(), {palette: ['#ff00ff']}, 'Built since 2017');

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Plot the scene count next to the area. Do the jumps follow the number
//    of clear scenes rather than real construction?
// 2. The chart has the mode and the mean probability. Which series is
//    steadier, and why does averaging probabilities beat voting labels?
