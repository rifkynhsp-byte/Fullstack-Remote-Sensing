//| title: The simplest landslide map worth making
//| description: A weighted overlay of slope, rain and land cover for West Java, tested against the NASA Global Landslide Catalog and the mapped Iburi 2018 inventory.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 50 | The simplest landslide map worth making
 * ---------------------------------------------------------------------------
 * Score each factor 1 (low) to 5 (high), then add with weights:
 *   factor      1        2            3            4            5        weight
 *   slope (deg) < 8      8-15         15-25        25-35        > 35     0.5
 *   rain (mm)   < 2,000  2,000-2,500  2,500-3,000  3,000-3,500  > 3,500  0.3
 *   land cover  -        trees, built cropland     grass, shrub bare     0.2
 * These classes and weights are choices made for teaching, not published
 * values. The test decides whether they are any good: ROC AUC, where 0.5 is
 * no better than chance and 1 is perfect. The weight and threshold tuning
 * with a west/east split is in the Python notebook.
 */

// ---------------------------------------------------------------------------
// STEP 1. West Java: slope, rain and land cover
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Rectangle([106.3, -7.9, 108.9, -6.3], null, false);
var dem = ee.ImageCollection('COPERNICUS/DEM/GLO30').filterBounds(aoi).select('DEM').mosaic()
  .setDefaultProjection('EPSG:4326', null, 30);
var slope = ee.Terrain.slope(dem);
var rain = ee.ImageCollection('UCSB-CHG/CHIRPS/PENTAD').select('precipitation')
  .filterDate('2001-01-01', '2021-01-01').sum().divide(20);
var wc = ee.Image('ESA/WorldCover/v200/2021').select('Map');
var land = wc.neq(80);

// ---------------------------------------------------------------------------
// STEP 2. Classes and the weighted score
// ---------------------------------------------------------------------------
function classes(img, breaks) {
  var out = ee.Image(1);
  breaks.forEach(function (b, k) { out = out.where(img.gte(b), k + 2); });
  return out;
}
function scoreOf(sl) {
  return classes(sl, [8, 15, 25, 35]).multiply(0.5)
    .add(classes(rain, [2000, 2500, 3000, 3500]).multiply(0.3))
    .add(wc.remap([10, 50, 40, 20, 30, 60], [2, 2, 3, 4, 4, 5], 2).multiply(0.2));
}
var score = scoreOf(slope).updateMask(land).rename('score').clip(aoi);

// ---------------------------------------------------------------------------
// STEP 3. ROC AUC on the server: sweep a threshold, integrate the curve
// ---------------------------------------------------------------------------
// fc carries a 0/1 property `truth` and a numeric property `prop`.
function auc(fc, prop, lo, hi) {
  var ths = ee.List.sequence(hi, lo, null, 60);
  var pos = fc.filter(ee.Filter.eq('truth', 1)), neg = fc.filter(ee.Filter.eq('truth', 0));
  var np = pos.size(), nn = neg.size();
  var pts = ths.map(function (t) {
    return ee.List([neg.filter(ee.Filter.gte(prop, t)).size().divide(nn),
                    pos.filter(ee.Filter.gte(prop, t)).size().divide(np)]);
  });
  pts = ee.List([[0, 0]]).cat(pts).cat([[1, 1]]);
  var areas = ee.List.sequence(1, pts.size().subtract(1)).map(function (i) {
    var a = ee.List(pts.get(ee.Number(i).subtract(1))), b = ee.List(pts.get(i));
    return ee.Number(b.get(0)).subtract(a.get(0)).multiply(ee.Number(b.get(1)).add(a.get(1))).divide(2);
  });
  return ee.Number(areas.reduce(ee.Reducer.sum()));
}

// ---------------------------------------------------------------------------
// STEP 4. Test 1: the NASA Global Landslide Catalog, West Java
// ---------------------------------------------------------------------------
// Each landslide is compared through the mean score within its location
// accuracy (exact 250 m, 1 km, 5 km). Random places across West Java get a
// 1 km radius here (the notebook matches each one to a landslide's radius).
var RADIUS = ee.Dictionary({exact: 250, '1km': 1000, '5km': 5000});
var glc = ee.FeatureCollection('projects/sat-io/open-datasets/events/global_landslide_1970-2019')
  .filterBounds(aoi).filter(ee.Filter.inList('location_a', RADIUS.keys()));
var slides = glc.map(function (f) {
  return ee.Feature(f.geometry().buffer(RADIUS.get(f.get('location_a'))), {truth: 1});
});
// points that fall on the sea get no score and drop out below
var random = ee.FeatureCollection.randomPoints(aoi, 400, 1)
  .map(function (f) { return ee.Feature(f.geometry().buffer(1000), {truth: 0}); });
var stack = score.addBands(slope.rename('slope').updateMask(land));
var tested = stack.reduceRegions({collection: slides.merge(random), reducer: ee.Reducer.mean(), scale: 90, tileScale: 8})
  .filter(ee.Filter.notNull(['score']));
print('Global Landslide Catalog, West Java', ee.Dictionary({
  landslides: tested.filter(ee.Filter.eq('truth', 1)).size(),
  AUC_weighted_overlay: auc(tested, 'score', 1, 5), AUC_slope_alone: auc(tested, 'slope', 0, 60)}));

// ---------------------------------------------------------------------------
// STEP 5. Test 2: a mapped inventory, Iburi (Hokkaido) 2018
// ---------------------------------------------------------------------------
var iburi = ee.Geometry.Rectangle([141.93, 42.70, 142.05, 42.80]);
var inventory = ee.FeatureCollection('users/rifkynauvalhsp/IburiLandslideInventory/trainingset');
var slI = ee.Terrain.slope(ee.ImageCollection('COPERNICUS/DEM/GLO30').filterBounds(iburi).select('DEM').mosaic()
  .setDefaultProjection('EPSG:4326', null, 30));
var iburiPts = scoreOf(slI).rename('score').addBands(slI.rename('slope'))
  .addBands(ee.Image(0).paint(inventory, 1).rename('truth'))
  .stratifiedSample({numPoints: 800, classBand: 'truth', region: iburi, scale: 30, seed: 2, tileScale: 4});
print('Iburi 2018, mapped polygons', ee.Dictionary({
  landslide_pixels: iburiPts.filter(ee.Filter.eq('truth', 1)).size(),
  AUC_weighted_overlay: auc(iburiPts, 'score', 1, 5), AUC_slope_alone: auc(iburiPts, 'slope', 0, 60)}));

// ---------------------------------------------------------------------------
// STEP 6. The map
// ---------------------------------------------------------------------------
Map.centerObject(aoi, 8);
Map.addLayer(score, {min: 1.5, max: 4.5, palette: ['1a9850', 'a6d96a', 'ffffbf', 'fdae61', 'd73027']},
             'Landslide score (weighted overlay)');
Map.addLayer(glc, {color: '000000'}, 'Global Landslide Catalog points');
