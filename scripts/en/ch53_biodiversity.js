//| title: What satellites can say about biodiversity: habitat
//| description: Forest amount, core forest and structure inside and outside Bukit Barisan Selatan National Park, 2000 to 2023, with tree crops separated out.

/**
 * CHAPTER 53 | What satellites can say about biodiversity: habitat
 * ---------------------------------------------------------------------------
 * Species are not seen from space; their habitat is. Three habitat measures:
 *   amount         forest area (Hansen GFC: tree cover >= 30 % in 2000, minus loss)
 *   configuration  core forest = forest more than 300 m from any non-forest edge,
 *                  where edge effects (light, wind, hunters, fire) fade
 *   quality        GEDI foliage height diversity (Chapter 47)
 * Inside versus outside the national park boundary (WDPA).
 */

// ---------------------------------------------------------------------------
// STEP 1. Area, park and forest in 2000 and 2023
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Rectangle([103.80, -5.95, 104.60, -4.90], null, false);
var park = ee.FeatureCollection('WCMC/WDPA/current/polygons')
  .filter(ee.Filter.stringContains('NAME', 'Bukit Barisan Selatan')).geometry();
var gfc = ee.Image('UMD/hansen/global_forest_change_2025_v1_13');
var forest2000 = gfc.select('treecover2000').gte(30);
var lossyear = gfc.select('lossyear').unmask(0);                 // 0 = never lost
var forest2023 = forest2000.and(lossyear.eq(0).or(lossyear.gt(23)));

// ---------------------------------------------------------------------------
// STEP 2. Core forest: more than 300 m from any edge
// ---------------------------------------------------------------------------
var UTM = ee.Projection('EPSG:32748').atScale(30);
function core(forest) {
  var dist = forest.not().reproject(UTM).fastDistanceTransform(32).sqrt().multiply(30);
  return forest.and(dist.gt(300));
}
var core2000 = core(forest2000), core2023 = core(forest2023);
var inside = ee.Image(0).paint(ee.FeatureCollection([ee.Feature(park)]), 1).rename('inside');

// ---------------------------------------------------------------------------
// STEP 3. Amount and configuration, inside and outside the park
// ---------------------------------------------------------------------------
var area = ee.Image.pixelArea().divide(1e4);
var stack = ee.Image.cat([area.updateMask(forest2000).rename('f2000'), area.updateMask(forest2023).rename('f2023'),
                          area.updateMask(core2000).rename('c2000'), area.updateMask(core2023).rename('c2023')]).addBands(inside);
print('Hectares [forest 2000, forest 2023, core 2000, core 2023]; inside 1 = park',
      stack.reduceRegion({reducer: ee.Reducer.sum().repeat(4).group(4, 'inside'), geometry: aoi, scale: 30,
                          maxPixels: 1e11, tileScale: 16}).get('groups'));

// ---------------------------------------------------------------------------
// STEP 4. Is all of that "forest" natural? Coffee, rubber and oil palm
// ---------------------------------------------------------------------------
function fdp(crop) {
  return ee.ImageCollection('projects/forestdatapartnership/assets/' + crop + '/model_2026a')
    .filterDate('2020-01-01', '2021-01-01').mosaic().select('probability');
}
var treeCrop = fdp('rubber').gt(0.5).or(fdp('palm').gt(0.5)).or(fdp('coffee').gt(0.5)).unmask(0);
var coreNatural = core(forest2023.and(treeCrop.not()));
print('Hectares [forest 2023, of which tree crops, core 2023, core without tree crops]',
      ee.Image.cat([area.updateMask(forest2023), area.updateMask(forest2023.and(treeCrop)),
                    area.updateMask(core2023), area.updateMask(coreNatural)]).addBands(inside)
        .reduceRegion({reducer: ee.Reducer.sum().repeat(4).group(4, 'inside'), geometry: aoi, scale: 30,
                       maxPixels: 1e11, tileScale: 16}).get('groups'));

// ---------------------------------------------------------------------------
// STEP 5. Quality: foliage height diversity from GEDI
// ---------------------------------------------------------------------------
var fhd = ee.ImageCollection('LARSE/GEDI/GEDI02_B_002_MONTHLY').filterBounds(aoi)
  .filterDate('2019-04-01', '2024-01-01')
  .map(function (i) { return i.updateMask(i.select('l2b_quality_flag').eq(1).and(i.select('degrade_flag').eq(0))); })
  .select(['fhd_normal', 'cover']).mosaic();
var grp = ee.Image(0).where(forest2023.and(inside.eq(1)), 1).where(forest2023.and(inside.eq(0)), 2).selfMask().rename('grp');
var fhdPts = fhd.addBands(grp).updateMask(fhd.select('fhd_normal').mask())
  .stratifiedSample({numPoints: 400, classBand: 'grp', region: aoi, scale: 25, seed: 2, tileScale: 8});
print(ui.Chart.feature.histogram(fhdPts.filter(ee.Filter.eq('grp', 1)), 'fhd_normal', 30)
  .setOptions({title: 'Foliage height diversity of forest inside the park (GEDI)', colors: ['#00441b']}));
print(ui.Chart.feature.histogram(fhdPts.filter(ee.Filter.eq('grp', 2)), 'fhd_normal', 30)
  .setOptions({title: 'Foliage height diversity of forest outside the park (GEDI)', colors: ['#a1d99b']}));

// ---------------------------------------------------------------------------
// STEP 6. Map: lost since 2000, forest in 2023, core in 2023
// ---------------------------------------------------------------------------
var status = ee.Image(0).where(forest2000, 1).where(forest2023, 2).where(core2023, 3).selfMask().clip(aoi);
Map.centerObject(aoi, 9);
Map.addLayer(status, {min: 1, max: 3, palette: ['e6550d', 'a1d99b', '00441b']}, 'Lost since 2000, forest 2023, core 2023');
Map.addLayer(ee.Image().byte().paint(ee.FeatureCollection([ee.Feature(park)]), 1, 2), {palette: ['000000']}, 'National park');
