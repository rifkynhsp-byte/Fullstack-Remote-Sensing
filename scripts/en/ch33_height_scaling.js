//| title: One footprint, two maps
//| description: GEDI rh98 footprints against the ETH 10 m and GLAD 30 m canopy height maps over a Sumatran lowland, with the error split by height class, and GEDI's own 1 km biomass grid.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 33 | Scaling up from a LiDAR plot
 * ---------------------------------------------------------------------------
 * GEDI is a laser: it measures height directly, but only in 25 m footprints
 * spaced hundreds of metres apart. Wall-to-wall height maps fill the gaps by
 * training on GEDI with optical images. Here we ask how well they do, and
 * where they fail. (The 0.5 m LiDAR part of this chapter is in the Python tab.)
 */

var aoi = ee.Geometry.Rectangle([102.45, -2.15, 102.90, -1.75], null, false);
Map.centerObject(aoi, 11);

var eth = ee.Image('users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1').rename('eth');
var glad = ee.ImageCollection('users/potapovpeter/GEDI_V27').mosaic().rename('glad');

// Good GEDI shots only: quality flag, not degraded, high beam sensitivity.
var gedi = ee.ImageCollection('LARSE/GEDI/GEDI02_A_002_MONTHLY')
  .filterBounds(aoi).filterDate('2019-04-01', '2021-01-01')
  .map(function (img) {
    var ok = img.select('quality_flag').eq(1)
      .and(img.select('degrade_flag').eq(0))
      .and(img.select('sensitivity').gt(0.95));
    return img.select('rh98').updateMask(ok);
  })
  .mosaic().rename('gedi');

Map.addLayer(eth.clip(aoi), {min: 0, max: 35,
  palette: ['ffffe5', 'd9f0a3', 'addd8e', '41ab5d', '238443', '005a32']}, 'ETH height 2020');
Map.addLayer(gedi.clip(aoi), {min: 0, max: 40, palette: ['ffffcc', 'fd8d3c', '800026']},
             'GEDI rh98 shots');

// Sample only where a shot exists: the shot mask is the stratum.
var shots = gedi.addBands(eth).addBands(glad)
  .addBands(gedi.mask().rename('stratum').toInt())
  .stratifiedSample({numPoints: 2500, classBand: 'stratum', region: aoi, scale: 25,
                     seed: 4, dropNulls: true, tileScale: 4});

// Bias (map minus GEDI) in three height classes.
function bias(fc, band) {
  return fc.map(function (f) {
    return f.set('err', ee.Number(f.get(band)).subtract(f.get('gedi')));
  }).aggregate_mean('err');
}
[[0, 15], [15, 25], [25, 999]].forEach(function (b) {
  var d = shots.filter(ee.Filter.rangeContains('gedi', b[0], b[1]));
  print('GEDI ' + b[0] + '-' + b[1] + ' m: shots, ETH bias, GLAD bias',
        d.size(), bias(d, 'eth'), bias(d, 'glad'));
});

print(ui.Chart.feature.byFeature(shots, 'gedi', ['eth', 'glad'])
  .setChartType('ScatterChart')
  .setOptions({title: 'Map height against GEDI rh98', pointSize: 1,
               hAxis: {title: 'GEDI rh98 (m)'}, vAxis: {title: 'Map height (m)'}}));

// GEDI's own biomass grid (1 km), made from footprints, not from optical images.
var agbd = ee.Image('LARSE/GEDI/GEDI04_B_002').select('MU');
Map.addLayer(agbd.clip(aoi), {min: 0, max: 300,
  palette: ['ffffcc', 'c2e699', '78c679', '31a354', '006837']}, 'GEDI L4B AGBD (Mg/ha)', false);
