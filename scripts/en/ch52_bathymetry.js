//| title: How deep is the water, from colour alone?
//| description: Satellite-derived bathymetry for Kepulauan Seribu with the Stumpf log-ratio, calibrated against GEBCO and checked against coral reef zones.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 52 | How deep is the water, from colour alone?
 * ---------------------------------------------------------------------------
 * Light weakens with depth, and blue light weakens more slowly than green.
 * Over a uniform bottom in clear water, the log-ratio of blue to green
 * reflectance rises with depth (Stumpf et al. 2003):
 *     ratio = ln(n * blue) / ln(n * green)     n a constant (1000) keeping logs positive
 *     depth = m1 * ratio - m0                  m1, m0 fitted against known depths
 *   imagery      Sentinel-2 L2A dry-season median, B2 (blue), B3 (green)
 *   calibration  GEBCO 2023 grid (~450 m) in its 0-20 m range: coarse, but public
 *   context      Allen Coral Atlas geomorphic zones
 * Real surveys calibrate against ICESat-2 photons or echo-sounder tracks. The
 * sensitivity test (composite, mask, n) is in the Python notebook.
 */

// ---------------------------------------------------------------------------
// STEP 1. A clear, calm dry-season composite over water only
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Rectangle([106.45, -5.80, 106.75, -5.50], null, false);   // Kepulauan Seribu
var N = 1000;
var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(aoi)
  .filterDate('2022-05-01', '2024-10-31')
  .filter(ee.Filter.calendarRange(5, 10, 'month'))               // dry season, calmer, clearer
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
  .map(function (i) {
    var water = i.select('SCL').eq(6);                            // scene classification 6: water
    return i.select(['B2', 'B3', 'B4', 'B8']).divide(10000).updateMask(water)
      .copyProperties(i, ['system:time_start']);
  });
var comp = s2.median().clip(aoi);

// ---------------------------------------------------------------------------
// STEP 2. The Stumpf log-ratio
// ---------------------------------------------------------------------------
var ratio = comp.select('B2').multiply(N).log().divide(comp.select('B3').multiply(N).log())
  .rename('ratio').setDefaultProjection('EPSG:32748', null, 10);

// ---------------------------------------------------------------------------
// STEP 3. Calibrate against GEBCO depths of 0.5-20 m
// ---------------------------------------------------------------------------
var gebco = ee.ImageCollection('projects/sat-io/open-datasets/gebco/gebco_grid').mosaic()
  .rename('elev').setDefaultProjection('EPSG:4326', null, 463);
var gebcoDepth = gebco.multiply(-1).rename('depth');              // elevation < 0 under sea
var ratioCoarse = ratio.reduceResolution({reducer: ee.Reducer.mean(), bestEffort: true, maxPixels: 4096})
  .reproject(gebco.projection());
var pairs = ratioCoarse.addBands(gebcoDepth).updateMask(gebcoDepth.gt(0.5).and(gebcoDepth.lt(20)))
  .sample({region: aoi, scale: 463, numPixels: 2000, seed: 1}).filter(ee.Filter.notNull(['ratio', 'depth']));
var fit = ee.Dictionary(pairs.reduceColumns(ee.Reducer.linearFit(), ['ratio', 'depth']));
var r = ee.Dictionary(pairs.reduceColumns(ee.Reducer.pearsonsCorrelation(), ['ratio', 'depth'])).get('correlation');
print('Calibration (depth = scale * ratio + offset)', fit.combine({cells: pairs.size(), R2: ee.Number(r).pow(2)}));
print(ui.Chart.feature.byFeature(pairs, 'ratio', 'depth').setChartType('ScatterChart')
  .setOptions({title: 'Blue/green log-ratio against GEBCO depth, ~450 m cells', hAxis: {title: 'ratio'},
               vAxis: {title: 'depth (m)'}, pointSize: 2, colors: ['#2a78d6'], trendlines: {0: {color: '#e34948'}}}));
var sdb = ratio.multiply(ee.Number(fit.get('scale'))).add(ee.Number(fit.get('offset'))).rename('sdb');
sdb = sdb.updateMask(sdb.gte(0).and(sdb.lte(20)));

// ---------------------------------------------------------------------------
// STEP 4. Does the ratio follow the reef zones' depth order?
// ---------------------------------------------------------------------------
var REEF_CODES = [11, 12, 13, 14, 15, 16, 21, 22, 23, 24, 25];
var REEF_COLORS = ['77d0fc', '2ca2f9', 'c5a7cb', '92739d', '614272', 'fbdefb', '10bda6', '288471', 'cd6812', 'befbff', 'ffba15'];
var reefs = ee.Image('ACA/reef_habitat/v2_0').select('geomorphic')
  .remap(REEF_CODES, ee.List.sequence(0, REEF_CODES.length - 1)).toInt().clip(aoi);
var byZone = ratio.addBands(reefs.rename('zone'))
  .stratifiedSample({numPoints: 300, classBand: 'zone', region: aoi, scale: 10, seed: 3, tileScale: 4});
print('Median ratio per reef zone (0 shallow lagoon, 1 deep lagoon, 2 inner reef flat, 3 outer reef flat, 4 reef crest, ...)',
      byZone.reduceColumns(ee.Reducer.median().group(1, 'zone'), ['ratio', 'zone']));

// ---------------------------------------------------------------------------
// STEP 5. Maps
// ---------------------------------------------------------------------------
Map.centerObject(aoi, 12);
Map.addLayer(comp, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.12}, 'True colour, dry-season median');
Map.addLayer(ratio, {min: 1.0, max: 1.15, palette: ['c6dbef', '6baed6', '2171b5', '08306b']}, 'Blue/green log-ratio', false);
Map.addLayer(sdb, {min: 0, max: 20, palette: ['c6dbef', '6baed6', '2171b5', '08306b']}, 'Satellite-derived depth (m)');
Map.addLayer(reefs, {min: 0, max: REEF_CODES.length - 1, palette: REEF_COLORS}, 'Allen Coral Atlas zones', false);
