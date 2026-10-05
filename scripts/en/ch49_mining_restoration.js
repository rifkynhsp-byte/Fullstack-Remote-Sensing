//| title: Restoration effectiveness, measured three ways
//| description: Tin-mined land on Bangka since 1995: when it was mined, whether it is green again, and whether its height has come back.

/**
 * CHAPTER 49 | Restoration effectiveness, measured three ways
 * ---------------------------------------------------------------------------
 * Tin mining on Bangka strips the land to bare sand and leaves ponds. Some of
 * it is reclaimed (planted), some regrows on its own, some stays bare.
 *   disturbed   annual Landsat NDVI fell below 0.15 at least once in 1995-2015,
 *               and the pixel was vegetated (NDVI > 0.5) before
 *   reference   pixels above NDVI 0.6 every year: undisturbed vegetation
 *   greenness   NDVI years after disturbance, against the reference
 *   structure   GEDI rh98 height of recovered land against the reference
 * Greenness returns within a few years; height and biomass take decades. A
 * restoration report that shows only NDVI overstates success. The survival
 * analysis (years to green) is in the Python notebook.
 */

// ---------------------------------------------------------------------------
// STEP 1. Area, permanent water, and 34 years of Landsat NDVI
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Rectangle([105.95, -2.15, 106.30, -1.75], null, false);   // central Bangka
var water = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gt(80).unmask(0);
function landsat(col, nir, red) {
  return ee.ImageCollection(col).filterBounds(aoi).map(function (img) {
    var qa = img.select('QA_PIXEL');
    var ok = qa.bitwiseAnd(1 << 3).eq(0).and(qa.bitwiseAnd(1 << 4).eq(0));
    var sr = img.select([nir, red]).multiply(0.0000275).add(-0.2);
    return sr.normalizedDifference([nir, red]).rename('ndvi').updateMask(ok)
      .copyProperties(img, ['system:time_start']);
  });
}
var ls = landsat('LANDSAT/LT05/C02/T1_L2', 'SR_B4', 'SR_B3')
  .merge(landsat('LANDSAT/LE07/C02/T1_L2', 'SR_B4', 'SR_B3'))
  .merge(landsat('LANDSAT/LC08/C02/T1_L2', 'SR_B5', 'SR_B4'))
  .merge(landsat('LANDSAT/LC09/C02/T1_L2', 'SR_B5', 'SR_B4'));
var EMPTY = ee.ImageCollection([ee.Image.constant(0).rename('ndvi').updateMask(0)]);
var annual = ee.ImageCollection(ee.List.sequence(1990, 2023).map(function (y) {
  var d = ee.Date.fromYMD(y, 1, 1);
  return ls.filterDate(d, d.advance(1, 'year')).merge(EMPTY).median()
    .addBands(ee.Image.constant(y).toInt16().rename('year')).set('year', y);
}));

// ---------------------------------------------------------------------------
// STEP 2. When was each pixel mined?
// ---------------------------------------------------------------------------
var firstBare = annual.filter(ee.Filter.rangeContains('year', 1995, 2015))
  .map(function (i) { return i.select('year').updateMask(i.select('ndvi').lt(0.15)); })
  .reduce(ee.Reducer.min()).rename('mined_year');
var wasGreen = annual.filter(ee.Filter.rangeContains('year', 1990, 1994)).select('ndvi').max().gt(0.5);
var disturbed = firstBare.updateMask(wasGreen).updateMask(water.not()).clip(aoi);

// ---------------------------------------------------------------------------
// STEP 3. Status in 2023, and the undisturbed reference
// ---------------------------------------------------------------------------
var ndvi2023 = ee.Image(annual.filter(ee.Filter.eq('year', 2023)).first()).select('ndvi');
var reference = annual.filter(ee.Filter.rangeContains('year', 1995, 2023)).select('ndvi')
  .min().gt(0.6).selfMask().rename('ref').clip(aoi);
// 1 still bare or ponds (NDVI < 0.3), 2 early regrowth (0.3-0.6), 3 green again (>= 0.6)
var status = ee.Image(1).where(ndvi2023.gte(0.3), 2).where(ndvi2023.gte(0.6), 3)
  .updateMask(disturbed.mask()).rename('status').clip(aoi);
var area = ee.Image.pixelArea().divide(1e4);
print('Mined land by status in 2023 (ha; 1 bare/ponds, 2 early regrowth, 3 green again)',
      area.addBands(status).reduceRegion({reducer: ee.Reducer.sum().group(1, 'status'), geometry: aoi, scale: 30,
                                          maxPixels: 1e10, tileScale: 8}).get('groups'));

// ---------------------------------------------------------------------------
// STEP 4. Greenness after mining, against the reference
// ---------------------------------------------------------------------------
var minedPts = disturbed.updateMask(disturbed.gte(2000).and(disturbed.lte(2008)))
  .sample({region: aoi, scale: 30, numPixels: 600, seed: 3, geometries: true}).limit(15)
  .map(function (f) { return f.set('kind', 'mined 2000-2008'); });
var refPts = reference.sample({region: aoi, scale: 30, numPixels: 300, seed: 4, geometries: true}).limit(15)
  .map(function (f) { return f.set('kind', 'reference'); });
var pts = minedPts.merge(refPts);
var meanSeries = ee.FeatureCollection(annual.map(function (img) {
  var v = img.select('ndvi').reduceRegions(pts, ee.Reducer.first(), 30);
  return ee.Feature(null, {year: img.get('year'),
    mined: v.filter(ee.Filter.eq('kind', 'mined 2000-2008')).aggregate_mean('first'),
    reference: v.filter(ee.Filter.eq('kind', 'reference')).aggregate_mean('first')});
}));
print(ui.Chart.feature.byFeature(meanSeries, 'year', ['mined', 'reference'])
  .setOptions({title: 'Mean NDVI of 15 pixels mined in 2000-2008 and 15 undisturbed reference pixels',
               vAxis: {title: 'NDVI'}, colors: ['#d7301f', '#1a9850'], lineWidth: 2}));

// ---------------------------------------------------------------------------
// STEP 5. Structure: is it as tall as the reference?
// ---------------------------------------------------------------------------
var gedi = ee.ImageCollection('LARSE/GEDI/GEDI02_A_002_MONTHLY').filterBounds(aoi)
  .filterDate('2019-04-01', '2024-01-01')
  .map(function (i) { return i.updateMask(i.select('quality_flag').eq(1).and(i.select('degrade_flag').eq(0))); })
  .select('rh98').mosaic();
// 1 reference, 2 mined and green again, 3 mined, early regrowth
var grp = ee.Image(0).where(reference.mask(), 1).where(status.eq(3), 2).where(status.eq(2), 3).selfMask().rename('grp');
var heights = gedi.addBands(grp).updateMask(gedi.mask())
  .stratifiedSample({numPoints: 300, classBand: 'grp', region: aoi, scale: 25, seed: 5, tileScale: 8});
[1, 2, 3].forEach(function (g) {
  var names = {1: 'reference', 2: 'mined, green again', 3: 'mined, early regrowth'};
  print('GEDI rh98, ' + names[g] + ' (median m, shots)',
        heights.filter(ee.Filter.eq('grp', g)).reduceColumns(ee.Reducer.median().combine(ee.Reducer.count(), null, true), ['rh98']));
});

// ---------------------------------------------------------------------------
// STEP 6. Maps: status in 2023 and the year mined
// ---------------------------------------------------------------------------
Map.centerObject(aoi, 11);
Map.addLayer(disturbed, {min: 1995, max: 2015, palette: ['440154', '3b528b', '21918c', '5ec962', 'fde725']},
             'Year first mined (1995-2015)', false);
Map.addLayer(status, {min: 1, max: 3, palette: ['d7301f', 'fdae61', '1a9850']},
             'Status 2023: bare or ponds, early regrowth, green again');
