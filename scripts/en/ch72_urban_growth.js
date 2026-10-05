//| title: Urban growth: where cities grow, how fast, and where next
//| description: Jabodetabek's built-up growth since 1975, the SDG 11.3.1 land-use efficiency of fourteen cities, a growth-probability map from a model trained on 2000-2020, and densification from building footprints.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 72 | Urban growth: where Indonesian cities grew, how fast, and where next
 * ---------------------------------------------------------------------------
 * Data: GHSL P2023A built-up surface, population and settlement model,
 * 1975-2030 in 5-year epochs (100 m and 1 km; 2025 and 2030 are projections);
 * Google Open Buildings 2.5D Temporal (2016-2023); Copernicus DEM; FAO GAUL 2025.
 * The Python notebook adds the logistic regression with odds ratios and the
 * national Degree of Urbanisation table; here the growth model is a random
 * forest in probability mode, trained and applied entirely in Earth Engine.
 */

// ---------------------------------------------------------------------------
// STEP 1. Jabodetabek and the GHSL layers
// ---------------------------------------------------------------------------
var JABO = ee.Geometry.Rectangle([106.35, -6.80, 107.25, -5.95], null, false);
var MONAS = ee.Geometry.Point([106.8272, -6.1754]);                  // the national monument, Jakarta's centre
function ghsl(name, year) { return ee.Image('JRC/GHSL/P2023A/' + name + '/' + year); }
// Share of each 100 m cell covered by buildings (built_surface is m2 per 10,000 m2 cell)
function builtFrac(year) { return ghsl('GHS_BUILT_S', year).select('built_surface').divide(10000).rename('built'); }
var water = ee.ImageCollection('COPERNICUS/DEM/GLO30_2024_1').select('WBM').mosaic().gt(0);

// ---------------------------------------------------------------------------
// STEP 2. Fifty years of growth around Monas: the radial profile
// ---------------------------------------------------------------------------
var rings = ee.FeatureCollection(ee.List.sequence(0, 58000, 2000).map(function (r) {
  r = ee.Number(r);
  var outer = MONAS.buffer(r.add(2000), 50);
  var geom = ee.Geometry(ee.Algorithms.If(r.eq(0), outer, outer.difference(MONAS.buffer(r, 50), 50)));
  return ee.Feature(geom, {km: r.add(1000).divide(1000)});
}));
var epochs = [1975, 1990, 2000, 2010, 2020];
var profile = ee.Image.cat(epochs.map(function (y) { return builtFrac(y).rename('y' + y); }))
  .reduceRegions({collection: rings, reducer: ee.Reducer.mean(), scale: 100});
print(ui.Chart.feature.byFeature(profile, 'km', epochs.map(function (y) { return 'y' + y; }))
  .setOptions({title: 'Built-up share in 2 km rings around Monas, 1975-2020 (GHSL)', hAxis: {title: 'km from Monas'},
               vAxis: {title: 'built-up share'}, lineWidth: 2}));

// ---------------------------------------------------------------------------
// STEP 3. SDG 11.3.1: is land built on faster than people arrive?
// ---------------------------------------------------------------------------
// LCRPGR = land consumption rate / population growth rate, 2000-2020. Above 1: sprawl.
var gaul = ee.FeatureCollection('FAO/GAUL/2025/level2').filter(ee.Filter.eq('ISO3_CODE', 'IDN'));
var cities = gaul.filter(ee.Filter.inList('GAUL2_NAME', ['Kota Surabaya', 'Kota Bandung', 'Kota Medan', 'Kota Semarang',
  'Kota Makassar', 'Kota Palembang', 'Kota Denpasar', 'Kota Pekanbaru', 'Kota Balikpapan', 'Kota Batam', 'Kota Yogyakarta', 'Kota Malang']));
var sums = ee.Image.cat([ghsl('GHS_BUILT_S', 2000).select('built_surface').rename('b2000'),
                         ghsl('GHS_BUILT_S', 2020).select('built_surface').rename('b2020'),
                         ghsl('GHS_POP', 2000).select('population_count').rename('p2000'),
                         ghsl('GHS_POP', 2020).select('population_count').rename('p2020')])
  .reduceRegions({collection: cities, reducer: ee.Reducer.sum(), scale: 100, tileScale: 4})
  .map(function (f) {
    var lcr = ee.Number(f.get('b2020')).divide(f.get('b2000')).log().divide(20);
    var pgr = ee.Number(f.get('p2020')).divide(f.get('p2000')).log().divide(20);
    return f.set({LCRPGR: lcr.divide(pgr), built_m2_per_person_2020: ee.Number(f.get('b2020')).divide(f.get('p2020'))});
  });
print('SDG 11.3.1 by city (LCRPGR above 1 = land consumed faster than population grows)',
      sums.select(['GAUL2_NAME', 'LCRPGR', 'built_m2_per_person_2020'], null, false).sort('LCRPGR', false));

// ---------------------------------------------------------------------------
// STEP 4. Where next: a growth model trained on what happened in 2000-2020
// ---------------------------------------------------------------------------
var proj = ee.Projection('EPSG:32748').atScale(100);
var dem = ee.ImageCollection('COPERNICUS/DEM/GLO30_2024_1').select('DEM').mosaic().setDefaultProjection(proj);
function drivers(year) {
  var urban = builtFrac(year).gt(0.2);
  return ee.Image.cat([
    ee.FeatureCollection([ee.Feature(MONAS)]).distance(80000).divide(1000).rename('km_to_centre'),
    urban.selfMask().fastDistanceTransform(256, 'pixels', 'squared_euclidean').sqrt().multiply(0.1).reproject(proj).rename('km_to_urban'),
    builtFrac(year).focalMean(1000, 'circle', 'meters').rename('built_1km'),
    ghsl('GHS_POP', year).select('population_count').max(0).add(1).log().rename('people_log'),
    ee.Terrain.slope(dem).rename('slope_deg'), dem.rename('elev_m')]).toFloat();
}
// Cells not urban in 2000 (built share < 20 %), on land: did they become urban by 2020?
var candidates = builtFrac(2000).lt(0.2).and(water.not());
var sample = drivers(2000).addBands(builtFrac(2020).gte(0.2).rename('urbanised').toInt()).updateMask(candidates)
  .stratifiedSample({numPoints: 0, classBand: 'urbanised', region: JABO, scale: 100, seed: 42,
                     classValues: [0, 1], classPoints: [2500, 2500], tileScale: 4}).randomColumn('r', 1);
var train = sample.filter(ee.Filter.lt('r', 0.7)), test = sample.filter(ee.Filter.gte('r', 0.7));
var rf = ee.Classifier.smileRandomForest({numberOfTrees: 300, minLeafPopulation: 5, seed: 0})
  .setOutputMode('PROBABILITY').train(train, 'urbanised', drivers(2000).bandNames());
print('Driver importance (random forest)', ee.Dictionary(rf.explain().get('importance')));
var scored = test.classify(rf, 'p').map(function (f) { return f.set('hit', ee.Number(f.get('p')).gt(0.5).eq(ee.Number(f.get('urbanised')))); });
print('Hold-out agreement at p > 0.5 (random split; the notebook uses spatial blocks)', scored.aggregate_mean('hit'));
// Applied to the city of 2020: "where growth would go if the last twenty years repeated".
var growthProb = drivers(2020).classify(rf).updateMask(builtFrac(2020).lt(0.2)).updateMask(water.not()).clip(JABO);

// ---------------------------------------------------------------------------
// STEP 5. Densification inside the city: building cover 2016 to 2023
// ---------------------------------------------------------------------------
function buildings(year) {
  return ee.ImageCollection('GOOGLE/Research/open-buildings-temporal/v1').filterBounds(JABO)
    .filter(ee.Filter.calendarRange(year, year, 'year')).mosaic().select('building_presence').gt(0.5);
}
var newCover = buildings(2023).subtract(buildings(2016)).setDefaultProjection(ee.Projection('EPSG:32748').atScale(4))
  .reduceResolution({reducer: ee.Reducer.mean(), maxPixels: 1024}).reproject(ee.Projection('EPSG:32748').atScale(50)).clip(JABO);

// ---------------------------------------------------------------------------
// STEP 6. Maps
// ---------------------------------------------------------------------------
var builtVis = {min: 0, max: 0.6, palette: ['f7f7f7', 'fddbc7', 'f4a582', 'd6604d', 'b2182b', '67001f']};
Map.centerObject(JABO, 9);
Map.addLayer(builtFrac(1975).updateMask(builtFrac(1975).gt(0.02)).clip(JABO), builtVis, 'Built-up share 1975', false);
Map.addLayer(builtFrac(2020).updateMask(builtFrac(2020).gt(0.02)).clip(JABO), builtVis, 'Built-up share 2020');
Map.addLayer(growthProb, {min: 0, max: 1, palette: ['ffffcc', 'c2e699', '78c679', 'fd8d3c', 'e31a1c', '800026']},
             'Probability of urbanising (model 2000-2020 applied to 2020)', false);
Map.addLayer(newCover, {min: -0.2, max: 0.4, palette: ['2166ac', 'f7f7f7', 'fdae61', 'd7191c']}, 'Change in building cover 2016-2023', false);
