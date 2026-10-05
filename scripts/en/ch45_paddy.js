//| title: Rice through the clouds
//| description: Map paddy and count crops per year from Sentinel-1 VH in Karawang, calibrate a yield map to BPS production, and find fields flooded while growing.

/**
 * CHAPTER 45 | Rice through the clouds
 * ---------------------------------------------------------------------------
 * A rice field is flooded before transplanting: smooth water, very low VH
 * backscatter. As the crop grows, VH rises; at harvest it drops. Counting
 * and timing those cycles tells how a landscape farms.
 *
 *   data     Sentinel-1 IW GRD VH, 12-day composites, 2021-2023
 *   paddy    >= 1 flooding dip (VH < -21 dB) per year and a seasonal VH range
 *            >= 6 dB, on ESA WorldCover cropland
 *   yield    BPS: Karawang produced about 1.09 million t of dry milled grain
 *            (GKG) in 2023 (preliminary, BPS West Java, 1 Nov 2023), spread
 *            over the mapped harvests in proportion to MODIS GPP
 *
 * The per-field season statistics, the failure rule and the Ciptagelar
 * comparison with Sentinel-2 are in the Python notebook.
 */

// ---------------------------------------------------------------------------
// STEP 1. Karawang, Sentinel-1 VH and cropland
// ---------------------------------------------------------------------------
var karawang = ee.FeatureCollection('FAO/GAUL/2025/level2')
  .filter(ee.Filter.eq('GAUL1_NAME', 'Jawa Barat')).filter(ee.Filter.eq('GAUL2_NAME', 'Karawang')).geometry();
var PRODUCTION_2023_T = 1.09e6;   // t GKG, BPS West Java preliminary figure (1 Nov 2023)
var s1 = ee.ImageCollection('COPERNICUS/S1_GRD').filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH')).select('VH');
var cropland = ee.Image('ESA/WorldCover/v200/2021').select('Map').eq(40);

// ---------------------------------------------------------------------------
// STEP 2. 12-day VH composites
// ---------------------------------------------------------------------------
// Empty periods get a masked placeholder, so the series keeps its rhythm.
function composites(region, start, end) {
  var step = 12, col = s1.filterBounds(region), d0 = ee.Date(start);
  var n = ee.Date(end).difference(d0, 'day').divide(step).floor();
  return ee.ImageCollection(ee.List.sequence(0, n.subtract(1)).map(function (i) {
    var a = d0.advance(ee.Number(i).multiply(step), 'day');
    var empty = ee.Image.constant(0).rename('VH').updateMask(0);
    return col.filterDate(a, a.advance(step, 'day')).merge(ee.ImageCollection([empty])).mean()
      .focalMedian(1.5, 'square', 'pixels').rename('VH').set('system:time_start', a.millis());
  }));
}

// ---------------------------------------------------------------------------
// STEP 3. Paddy: count the flooding onsets per year
// ---------------------------------------------------------------------------
// An onset is a composite below -21 dB whose predecessor was not. Paddy needs
// at least one onset a year and a seasonal range (p90 - p10) of 6 dB or more.
function paddyMask(region, start, end) {
  var ts = composites(region, start, end);
  var years = ee.Date(end).difference(ee.Date(start), 'year');
  var fl = ts.map(function (i) { return i.lt(-21).unmask(0); }).toList(200);
  var onsets = ee.ImageCollection(ee.List.sequence(1, fl.size().subtract(1)).map(function (i) {
    return ee.Image(fl.get(i)).and(ee.Image(fl.get(ee.Number(i).subtract(1))).not());
  }));
  var dips = onsets.sum().divide(years);
  var range = ts.reduce(ee.Reducer.percentile([90])).subtract(ts.reduce(ee.Reducer.percentile([10])));
  return dips.updateMask(dips.gte(1).and(range.gte(6)).and(cropland)).rename('dips');
}
var paddy = paddyMask(karawang, '2021-01-01', '2024-01-01');

// ---------------------------------------------------------------------------
// STEP 4. What a paddy field looks like to the radar
// ---------------------------------------------------------------------------
var box = ee.Geometry.Rectangle([107.25, -6.35, 107.55, -6.05], null, false);
var fields = paddyMask(box, '2021-01-01', '2024-01-01')
  .sample({region: box, scale: 20, numPixels: 400, seed: 5, geometries: true}).limit(4);
print(ui.Chart.image.seriesByRegion(composites(box, '2021-01-01', '2024-07-01'), fields, ee.Reducer.first(), 'VH', 20)
  .setOptions({title: 'Four Karawang paddy fields: VH every 12 days. Each deep dip is a flooded field before planting.',
               vAxis: {title: 'VH (dB)'}, lineWidth: 1, pointSize: 2}));

// ---------------------------------------------------------------------------
// STEP 5. Harvested area and the implied yield, 2023
// ---------------------------------------------------------------------------
var pad23 = paddyMask(karawang, '2023-01-01', '2024-01-01');
var gpp = ee.ImageCollection('MODIS/061/MOD17A2HGF').select('Gpp')
  .filterDate('2023-01-01', '2024-01-01').sum().multiply(0.0001);         // kg C/m2
var areaHa = ee.Image.pixelArea().divide(1e4);
var s = areaHa.updateMask(pad23.mask()).rename('paddy_ha')
  .addBands(areaHa.multiply(pad23).rename('harvested_ha'))
  .reduceRegion({reducer: ee.Reducer.sum(), geometry: karawang, scale: 30, maxPixels: 1e11, tileScale: 16});
var implied = ee.Number(PRODUCTION_2023_T).divide(s.get('harvested_ha'));
print('Karawang 2023', s.combine({official_production_t: PRODUCTION_2023_T, implied_yield_t_per_ha: implied,
  crops_per_year: ee.Number(s.get('harvested_ha')).divide(s.get('paddy_ha'))}));

// The yield map: GPP per crop, scaled so the district mean equals the implied yield.
var perSeason = gpp.divide(pad23);
var meanPs = ee.Number(perSeason.reduceRegion({reducer: ee.Reducer.mean(), geometry: karawang, scale: 500,
                                                maxPixels: 1e10, tileScale: 8}).values().get(0));
var yieldMap = perSeason.divide(meanPs).multiply(implied).rename('t_ha').clip(karawang);

// ---------------------------------------------------------------------------
// STEP 6. Growing paddy that went under water in March
// ---------------------------------------------------------------------------
// Rough in February (a crop standing) and smooth in March (water): flooded while growing.
function submerged(year) {
  var col = s1.filterBounds(karawang);
  var feb = col.filterDate(year + '-02-01', year + '-03-01').mean();
  var mar = col.filterDate(year + '-03-01', year + '-04-01').min();
  return feb.gt(-17).and(mar.lt(-21)).and(paddy.mask()).selfMask().rename('sub');
}
[2022, 2023].forEach(function (y) {
  print('Growing paddy flooded in March ' + y + ' (ha)', areaHa.updateMask(submerged(y))
    .reduceRegion({reducer: ee.Reducer.sum(), geometry: karawang, scale: 20, maxPixels: 1e11, tileScale: 16}));
});

// ---------------------------------------------------------------------------
// STEP 7. Maps
// ---------------------------------------------------------------------------
Map.centerObject(karawang, 10);
Map.addLayer(paddy.clip(karawang), {min: 1, max: 3, palette: ['c7e9c0', '41ab5d', '005a32']}, 'Paddy: crops per year');
Map.addLayer(yieldMap, {min: 3, max: 9, palette: ['fee08b', 'd9ef8b', '66bd63', '1a9850']}, 'Yield 2023 (t/ha GKG)', false);
Map.addLayer(submerged(2023).clip(karawang), {palette: ['2a78d6']}, 'Flooded while growing, March 2023', false);
