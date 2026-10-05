//| title: Seeing an outbreak spread, one summer at a time
//| description: Bark-beetle dieback in the Harz conifers: the summer each stand first lost canopy water, how the outbreak spread, and how long before salvage logging followed.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 58 | Seeing an outbreak spread, one summer at a time
 * ---------------------------------------------------------------------------
 * A pest or disease kills trees from the inside before the canopy changes
 * colour, and the canopy changes before anyone cuts the trees. Satellites see
 * the middle step: a drop in canopy water and leaf area.
 *   1. forest  conifer forest (Copernicus land cover 2019, needle-leaved
 *              evergreen) with Hansen tree cover >= 50 % in 2000
 *   2. signal  NDMI (NIR - SWIR) / (NIR + SWIR), June-August median, 2017-2024
 *   3. onset   first year NDMI falls more than 0.15 below its 2017 value, and
 *              stays down the following year
 *   4. check   year Hansen first records the pixel as lost: stress should come
 *              first, clearance (salvage logging) after
 */

// ---------------------------------------------------------------------------
// STEP 1. Conifer forest in the Harz
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Rectangle([10.40, 51.65, 10.90, 51.95], null, false);
var YEARS = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024];
var DROP = 0.15;
var cgls = ee.Image('COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019');
var gfc = ee.Image('UMD/hansen/global_forest_change_2025_v1_13');
var conifer = cgls.select('forest_type').eq(1).and(gfc.select('treecover2000').gte(50)).clip(aoi);
var lossyear = gfc.select('lossyear').unmask(0);

// ---------------------------------------------------------------------------
// STEP 2. Summer NDMI, every year
// ---------------------------------------------------------------------------
function ndmi(year) {
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(aoi)
    .filterDate(year + '-06-01', year + '-09-01')
    .linkCollection(ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'), ['cs'])
    .map(function (i) { return i.updateMask(i.select('cs').gte(0.6)).normalizedDifference(['B8', 'B11']); })
    .median().rename('n' + year);
}
var stack = ee.Image.cat(YEARS.map(ndmi)).updateMask(conifer);
var base = stack.select('n2017');
function dropped(y) { return base.subtract(stack.select('n' + y)).gt(DROP); }

// ---------------------------------------------------------------------------
// STEP 3. Onset: the first summer of a lasting drop
// ---------------------------------------------------------------------------
var onset = ee.Image(0);
YEARS.slice(1).reverse().forEach(function (y) { onset = onset.where(dropped(y), y); });
var lasting = ee.Image(0);
YEARS.slice(1).forEach(function (y) {
  var next = Math.min(y + 1, 2024);
  lasting = lasting.where(onset.eq(y).and(dropped(y)).and(dropped(next)), 1);
});
onset = onset.updateMask(conifer).updateMask(onset.eq(0).or(lasting)).unmask(0).updateMask(conifer).rename('onset');

// ---------------------------------------------------------------------------
// STEP 4. How fast it spread
// ---------------------------------------------------------------------------
var area = ee.Image.pixelArea().divide(1e4);
print('Conifer hectares by onset year (0 = never stressed)',
      area.addBands(onset).reduceRegion({reducer: ee.Reducer.sum().group(1, 'onset'), geometry: aoi, scale: 20,
                                         maxPixels: 1e10, tileScale: 8}).get('groups'));
var byOnset = ee.FeatureCollection(YEARS.map(function (y) {
  var g = ee.List(stack.select('n' + y).addBands(onset).reduceRegion({reducer: ee.Reducer.mean().group(1, 'onset'),
    geometry: aoi, scale: 40, maxPixels: 1e10, tileScale: 8}).get('groups'));
  var props = ee.Dictionary(g.iterate(function (d, acc) {
    d = ee.Dictionary(d);
    return ee.Dictionary(acc).set(ee.String('onset_').cat(ee.Number(d.get('onset')).format('%d')), d.get('mean'));
  }, ee.Dictionary({})));
  return ee.Feature(null, props).set('year', y);
}));
print(ui.Chart.feature.byFeature(byOnset, 'year', ['onset_0', 'onset_2018', 'onset_2019', 'onset_2020', 'onset_2021', 'onset_2022'])
  .setOptions({title: 'Mean summer NDMI of conifer pixels, grouped by the year their stress began',
               vAxis: {title: 'NDMI'}, lineWidth: 2, pointSize: 3}));

// ---------------------------------------------------------------------------
// STEP 5. Stress first, felling after? Years from onset to Hansen loss
// ---------------------------------------------------------------------------
var lossY = lossyear.add(2000).where(lossyear.eq(0), 0).rename('loss');
var lagPts = onset.addBands(lossY).updateMask(onset.gt(0))
  .sample({region: aoi, scale: 20, numPixels: 6000, seed: 4, tileScale: 8})
  .map(function (f) {
    var lost = ee.Number(f.get('loss')).gt(0);
    return f.set('lag', ee.Algorithms.If(lost, ee.Number(f.get('loss')).subtract(f.get('onset')), -99));
  });
print(ui.Chart.feature.histogram(lagPts.filter(ee.Filter.neq('lag', -99)), 'lag')
  .setOptions({title: 'Years from stress onset to recorded loss (stressed pixels that were felled)', colors: ['#3b528b']}));
print('Share of stressed pixels never recorded lost to 2024', lagPts.filter(ee.Filter.eq('lag', -99)).size().divide(lagPts.size()));

// ---------------------------------------------------------------------------
// STEP 6. The map: the summer each stand first lost canopy water
// ---------------------------------------------------------------------------
Map.centerObject(aoi, 11);
Map.addLayer(conifer.selfMask(), {palette: ['c7e9c0']}, 'Conifer forest');
Map.addLayer(onset.updateMask(onset.gt(0)), {min: 2018, max: 2024,
  palette: ['3b528b', '2c728e', '21918c', '28ae80', '5ec962', 'addc30', 'fde725']}, 'Onset year (2018 dark to 2024 yellow)');
