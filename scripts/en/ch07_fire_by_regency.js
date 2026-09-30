//| title: reduceRegions: a decade of fire detections per district in Riau
//| description: FIRMS active fire, 2015 to 2024, summed per district and per year.

/**
 * CHAPTER 7 | One reducer, many regions
 * ---------------------------------------------------------------------------
 * From the GEE101 fire exercise. reduceRegion gives one number for one
 * area; reduceRegions gives a number for every feature in a collection, in
 * one call. Here: how many fire detections each Riau district had across a
 * decade, and how the province's total moved year by year.
 *
 * Boundaries are FAO GAUL 2025 (level 2). The original exercise used
 * uploaded district files that are no longer available.
 */

var districts = ee.FeatureCollection('FAO/GAUL/2025/level2')
  .filter(ee.Filter.eq('GAUL1_NAME', 'Riau'));
var riau = districts.geometry();

// FIRMS: one image per day, 1 km pixels, T21 = brightness temperature of
// pixels flagged as fire. Keep detections with confidence of at least 50.
var firms = ee.ImageCollection('FIRMS').filterBounds(riau)
  .map(function (img) {
    return img.select('confidence').gte(50).selfMask().rename('fire')
      .copyProperties(img, ['system:time_start']);
  });

// Fire-days per pixel over the decade
var fireDays = firms.filterDate('2015-01-01', '2025-01-01').count().rename('fire_days').clip(riau);
Map.centerObject(districts, 7);
Map.addLayer(fireDays, {min: 1, max: 30, palette: ['#fee391', '#fe9929', '#cc4c02', '#662506']},
  'Fire detection days, 2015 to 2024');
Map.addLayer(ee.Image().byte().paint(districts, 1, 1), {palette: ['black']}, 'Districts');

// reduceRegions: the sum of fire-days inside every district, in one call
var perDistrict = fireDays.reduceRegions({
  collection: districts, reducer: ee.Reducer.sum(), scale: 1000, tileScale: 4
}).map(function (f) {
  var km2 = f.geometry().area(100).divide(1e6);
  return f.set({district: f.get('GAUL2_NAME'), fire_days: f.get('sum'),
                per_1000_km2: ee.Number(f.get('sum')).divide(km2).multiply(1000)});
});
print('Fire detection days per district', perDistrict.select(['district', 'fire_days', 'per_1000_km2']));

// The same province, one number per year
var perYear = ee.FeatureCollection(ee.List.sequence(2015, 2024).map(function (y) {
  var n = firms.filter(ee.Filter.calendarRange(y, y, 'year')).count()
    .reduceRegion({reducer: ee.Reducer.sum(), geometry: riau, scale: 1000,
                   maxPixels: 1e10, tileScale: 4}).get('fire');
  return ee.Feature(null, {year: y, fire_days: n});
}));
print(ui.Chart.feature.byFeature(perYear, 'year', ['fire_days'])
  .setChartType('ColumnChart')
  .setOptions({title: 'Fire detection days in Riau, per year', hAxis: {format: '####'}}));

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Rank districts by raw total and by per 1000 km². Which ranking would
//    you give a provincial fire agency, and why?
// 2. Overlay the peat map (Chapter 11). What share of fire-days fell on peat?
