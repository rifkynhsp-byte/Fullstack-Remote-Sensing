//| title: A land-cover map nobody had to label
//| description: Use the agreement of WorldCover and Dynamic World as free training labels for Lombok, train on 2021 satellite embeddings, and update the map to 2024 with no new labels.

/**
 * CHAPTER 56 | A land-cover map nobody had to label
 * ---------------------------------------------------------------------------
 * Collecting training points is the slow part of every classification
 * (Chapter 15). When two independent global maps agree on a pixel, that pixel
 * is probably right; use the agreement as free training data.
 *   1. labels    WorldCover 2021 and the 2021 mode of Dynamic World, mapped to
 *                7 shared classes; keep only pixels where both agree
 *   2. features  Google Satellite Embedding, 2021 (64 bands)
 *   3. model     random forest, trained once
 *   4. update    apply the same model to the 2024 embeddings: a new map with no
 *                new labels (the embedding space is the same every year)
 *   5. check     held-out consensus points (optimistic: easy pixels only) and
 *                random points against Dynamic World 2024 (includes hard pixels)
 */

// ---------------------------------------------------------------------------
// STEP 1. Lombok and seven shared classes
// ---------------------------------------------------------------------------
var NAMES = ['water', 'trees', 'mangrove', 'shrub and grass', 'cropland', 'built', 'bare'];
var PALETTE = ['2c7fb8', '1a9850', '00a884', 'c2e699', 'fee08b', 'd73027', 'bdbdbd'];
var lombok = ee.FeatureCollection('FAO/GAUL/2015/level1').filter(ee.Filter.eq('ADM1_NAME', 'Nusatenggara Barat'))
  .geometry().intersection(ee.Geometry.Rectangle([115.80, -9.10, 116.75, -8.20]), 100);
var aoi = lombok.bounds(100);
var wc = ee.ImageCollection('ESA/WorldCover/v200').first()
  .remap([80, 10, 95, 20, 30, 40, 50, 60, 90], [0, 1, 2, 3, 3, 4, 5, 6, 3], -1).rename('lc');
function dynamicWorld7(year) {
  var d = ee.Date.fromYMD(year, 1, 1);
  return ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(aoi).filterDate(d, d.advance(1, 'year'))
    .select('label').mode().remap([0, 1, 3, 2, 5, 4, 6, 7], [0, 1, 2, 3, 3, 4, 5, 6], -1).rename('lc');
}
function embeddings(year) {
  var d = ee.Date.fromYMD(year, 1, 1);
  return ee.ImageCollection('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL').filterDate(d, d.advance(1, 'year'))
    .filterBounds(aoi).mosaic().clip(lombok);
}
var dw21 = dynamicWorld7(2021), dw24 = dynamicWorld7(2024);

// ---------------------------------------------------------------------------
// STEP 2. Free labels: where the two maps agree
// ---------------------------------------------------------------------------
// Dynamic World has no mangrove class; WorldCover mangrove counts as agreeing with DW trees.
var agree = wc.eq(dw21).or(wc.eq(2).and(dw21.eq(1))).and(wc.gte(0));
var labels = wc.updateMask(agree).clip(lombok).rename('lc');

// ---------------------------------------------------------------------------
// STEP 3. Train once on 2021 embeddings
// ---------------------------------------------------------------------------
var emb21 = embeddings(2021), emb24 = embeddings(2024);
var pts = labels.stratifiedSample({numPoints: 300, classBand: 'lc', region: lombok, scale: 10, seed: 7,
                                   geometries: true, tileScale: 8});
var samples = emb21.sampleRegions({collection: pts, properties: ['lc'], scale: 10, tileScale: 8}).randomColumn('r', 3);
var train = samples.filter(ee.Filter.lt('r', 0.7)), test = samples.filter(ee.Filter.gte('r', 0.7));
var model = ee.Classifier.smileRandomForest(150).train(train, 'lc', emb21.bandNames());
var map21 = emb21.classify(model).rename('lc');
var map24 = emb24.classify(model).rename('lc');

// ---------------------------------------------------------------------------
// STEP 4. Two checks: easy held-out points, and random points
// ---------------------------------------------------------------------------
var cm = test.classify(model).errorMatrix('lc', 'classification', ee.List.sequence(0, 6));
print('Held-out consensus points (optimistic)', ee.Dictionary({overall_accuracy: cm.accuracy(),
  producers: cm.producersAccuracy(), consumers: cm.consumersAccuracy()}));
var rnd = ee.FeatureCollection.randomPoints(lombok, 3000, 11);
var checked = map24.rename('ours').addBands(dw24.rename('dw24')).addBands(map21.rename('ours21'))
  .addBands(wc.rename('wc')).addBands(agree.rename('agree'))
  .sampleRegions({collection: rnd, scale: 10, tileScale: 8})
  .filter(ee.Filter.gte('dw24', 0)).filter(ee.Filter.gte('wc', 0))
  .map(function (f) {
    return f.set({same24: ee.Number(f.get('ours')).eq(f.get('dw24')), same21: ee.Number(f.get('ours21')).eq(f.get('wc'))});
  });
print('Random points over the island', ee.Dictionary({
  n: checked.size(), ours_2024_vs_DW_2024: checked.aggregate_mean('same24'),
  ours_2021_vs_WorldCover: checked.aggregate_mean('same21'),
  same24_where_maps_disagreed: checked.filter(ee.Filter.eq('agree', 0)).aggregate_mean('same24')}));

// ---------------------------------------------------------------------------
// STEP 5. Area per class, 2021 and 2024
// ---------------------------------------------------------------------------
var area = ee.Image.pixelArea().divide(1e4);
[[2021, map21], [2024, map24]].forEach(function (p) {
  print('Hectares per class ' + p[0] + ' (0 water, 1 trees, 2 mangrove, 3 shrub/grass, 4 cropland, 5 built, 6 bare)',
        area.addBands(p[1]).reduceRegion({reducer: ee.Reducer.sum().group(1, 'lc'), geometry: lombok, scale: 20,
                                          maxPixels: 1e11, tileScale: 16}).get('groups'));
});

// ---------------------------------------------------------------------------
// STEP 6. Maps
// ---------------------------------------------------------------------------
Map.centerObject(lombok, 10);
Map.addLayer(labels, {min: 0, max: 6, palette: PALETTE}, 'Free labels: WorldCover and Dynamic World agree', false);
Map.addLayer(map24.clip(lombok), {min: 0, max: 6, palette: PALETTE}, 'Our map, 2024 (no new labels)');
