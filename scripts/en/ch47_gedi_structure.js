//| title: One laser shot, many numbers
//| description: GEDI height, cover, plant area, foliage height diversity and biomass across intact forest, degraded forest, oil palm and other tree crops in Jambi, and pre-fire fuel in South Sumatra.

/**
 * CHAPTER 47 | One laser shot, many numbers
 * ---------------------------------------------------------------------------
 * GEDI fires a laser from the International Space Station and records the
 * full returned waveform from a 25 m footprint. From that waveform come:
 *   L2A  rh0 ... rh100   height below which 0 ... 100 % of the returned energy lies
 *   L2B  cover, pai      canopy cover, plant area index
 *        pavd_z0, z1 ... plant area volume density in 5 m layers (0-5, 5-10 m ...)
 *        fhd_normal      foliage height diversity (how evenly leaves fill the height)
 *   L4A  agbd            above-ground biomass density, from L2A heights by allometry
 * Classes: JRC TMF 2022 (undisturbed, degraded), the Descals oil palm map, and
 * other tree cover from ESA WorldCover (mostly rubber, acacia, smallholder mixes).
 */

// ---------------------------------------------------------------------------
// STEP 1. Area, dates and good-quality shots
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Rectangle([102.45, -2.15, 102.90, -1.75], null, false);
var LAYERS = ['pavd_z0', 'pavd_z1', 'pavd_z2', 'pavd_z3', 'pavd_z4', 'pavd_z5', 'pavd_z6', 'pavd_z7', 'pavd_z8'];  // 0-45 m
function good(id, flag, region, start, end, sensitivity) {
  return ee.ImageCollection(id).filterBounds(region).filterDate(start, end).map(function (i) {
    var ok = i.select(flag).eq(1).and(i.select('degrade_flag').eq(0));
    if (sensitivity) ok = ok.and(i.select('sensitivity').gt(0.95));
    return i.updateMask(ok);
  });
}
var l2a = good('LARSE/GEDI/GEDI02_A_002_MONTHLY', 'quality_flag', aoi, '2019-04-01', '2024-01-01', true)
  .select(['rh25', 'rh50', 'rh75', 'rh98']).mosaic();
var l2b = good('LARSE/GEDI/GEDI02_B_002_MONTHLY', 'l2b_quality_flag', aoi, '2019-04-01', '2024-01-01')
  .select(['cover', 'pai', 'fhd_normal'].concat(LAYERS)).mosaic();
var l4a = good('LARSE/GEDI/GEDI04_A_002_MONTHLY', 'l4_quality_flag', aoi, '2019-04-01', '2024-01-01')
  .select('agbd').mosaic();

// ---------------------------------------------------------------------------
// STEP 2. Four land classes
// ---------------------------------------------------------------------------
var tmf = ee.ImageCollection('projects/JRC/TMF/v1_2023/AnnualChanges').mosaic().select('Dec2022');
var palm = ee.ImageCollection('BIOPAMA/GlobalOilPalm/v1').select('classification').mosaic().lte(2).unmask(0);
var wcTrees = ee.Image('ESA/WorldCover/v200/2021').select('Map').eq(10);
// 1 intact forest, 2 degraded forest, 3 oil palm, 4 other tree crops
var cls = ee.Image(0).where(wcTrees, 4).where(palm.eq(1), 3).where(tmf.eq(2), 2).where(tmf.eq(1), 1)
  .selfMask().rename('cls');

// ---------------------------------------------------------------------------
// STEP 3. Shots that carry all three products, 400 per class
// ---------------------------------------------------------------------------
var hasShot = l2a.select('rh98').mask().and(l2b.select('cover').mask()).and(l4a.select('agbd').mask());
var shots = l2a.addBands(l2b).addBands(l4a).addBands(cls).updateMask(hasShot)
  .stratifiedSample({numPoints: 400, classBand: 'cls', region: aoi, scale: 25, seed: 2, tileScale: 8});
var medians = ee.List([1, 2, 3, 4]).map(function (c) {
  var s = shots.filter(ee.Filter.eq('cls', c));
  var cols = ['rh98', 'rh50', 'cover', 'pai', 'fhd_normal', 'agbd', 'pavd_z0'];
  var med = ee.List(s.reduceColumns(ee.Reducer.median().repeat(cols.length), cols).get('median'));
  return ee.Feature(null, ee.Dictionary.fromLists(cols, med)).set({cls: c, shots: s.size()});
});
print('Median per class (1 intact, 2 degraded, 3 oil palm, 4 other tree crops): rh98, rh50, cover, pai, fhd, agbd, pavd_z0',
      ee.FeatureCollection(medians));
print(ui.Chart.feature.groups(shots, 'rh98', 'agbd', 'cls').setChartType('ScatterChart')
  .setOptions({title: 'Height (rh98) against biomass (agbd) per GEDI shot, by class',
               hAxis: {title: 'rh98 (m)'}, vAxis: {title: 'agbd (Mg/ha)'}, pointSize: 2,
               colors: ['#00441b', '#41ab5d', '#e08214', '#8073ac']}));

// ---------------------------------------------------------------------------
// STEP 4. Fuel before a fire: Ogan Komering Ilir, South Sumatra, 2019
// ---------------------------------------------------------------------------
// GEDI shots from April-July 2019, compared between pixels that burned in
// August-November 2019 and pixels that did not.
var oki = ee.Geometry.Rectangle([105.30, -3.60, 105.90, -3.10], null, false);
var preL2a = good('LARSE/GEDI/GEDI02_A_002_MONTHLY', 'quality_flag', oki, '2019-04-01', '2019-08-01')
  .select(['rh25', 'rh50', 'rh98']).mosaic();
var preL2b = good('LARSE/GEDI/GEDI02_B_002_MONTHLY', 'l2b_quality_flag', oki, '2019-04-01', '2019-08-01')
  .select(['cover', 'pavd_z0', 'pavd_z1', 'pavd_z2']).mosaic();
var burned19 = ee.ImageCollection('MODIS/061/MCD64A1').select('BurnDate')
  .filterDate('2019-08-01', '2019-12-01').max().gt(0).unmask(0).rename('burned');
var fuel = preL2a.addBands(preL2b)
  .addBands(preL2b.select('pavd_z0').add(preL2b.select('pavd_z1')).add(preL2b.select('pavd_z2')).rename('low_fuel_0_15m'))
  .addBands(preL2b.select('pavd_z1').divide(preL2b.select('pavd_z0').add(0.001)).rename('ladder_ratio'))
  .addBands(burned19.toInt());
var fuelShots = fuel.updateMask(preL2a.select('rh98').mask().and(preL2b.select('cover').mask()))
  .stratifiedSample({numPoints: 500, classBand: 'burned', region: oki, scale: 25, seed: 6, tileScale: 8});
[0, 1].forEach(function (b) {
  print(b ? 'Burned Aug-Nov 2019: pre-fire medians' : 'Did not burn: pre-fire medians',
        fuelShots.filter(ee.Filter.eq('burned', b)).reduceColumns(ee.Reducer.median().repeat(5),
          ['rh98', 'rh25', 'cover', 'low_fuel_0_15m', 'ladder_ratio']));
});

// ---------------------------------------------------------------------------
// STEP 5. Maps: classes, and foliage height diversity on a 500 m grid
// ---------------------------------------------------------------------------
var fhdGrid = l2b.select('fhd_normal').setDefaultProjection(ee.Projection('EPSG:4326').atScale(25))
  .reduceResolution({reducer: ee.Reducer.mean(), bestEffort: true, maxPixels: 1024})
  .reproject(ee.Projection('EPSG:32748').atScale(500)).clip(aoi);
Map.centerObject(aoi, 11);
Map.addLayer(cls.clip(aoi), {min: 1, max: 4, palette: ['00441b', '41ab5d', 'e08214', '8073ac']},
             'Intact, degraded, oil palm, other tree crops');
Map.addLayer(fhdGrid, {min: 1.5, max: 3.3, palette: ['fff5eb', 'fdae6b', 'e6550d', '7f2704']},
             'Foliage height diversity, 500 m mean', false);
