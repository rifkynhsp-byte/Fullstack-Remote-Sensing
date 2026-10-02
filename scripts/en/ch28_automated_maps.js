//| title: Print-ready maps and an automated report
//| description: A map layout in the Code Editor, then one print-resolution export per district, generated in a loop.

/**
 * CHAPTER 28 | Map production in the Code Editor
 * ---------------------------------------------------------------------------
 * The Code Editor is not a layout tool, but it gets you most of the way:
 * a legend panel with units and a title on the map, and exports that
 * render a styled map at print resolution. A loop over districts turns one
 * map into a series: every district, the same style, the same scale of colour.
 * The Python tab adds the frame, scale bar, inset and a PDF report.
 */

var DISTRICTS = ['Kota Bandung', 'Kota Bekasi', 'Garut'];
var PALETTE = ['313695', '74add1', 'ffffbf', 'f46d43', 'a50026'];
var VIS = {min: 22, max: 46, palette: PALETTE};          // the same for every map, wide enough for the hottest

var gaul = ee.FeatureCollection('FAO/GAUL/2025/level2');

var landsatLst = function (region) {
  return ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')
    .merge(ee.ImageCollection('LANDSAT/LC08/C02/T1_L2'))
    .filterBounds(region).filterDate('2024-06-01', '2024-10-31')
    .map(function (img) {
      var qa = img.select('QA_PIXEL');
      var clear = qa.bitwiseAnd(1 << 3).eq(0).and(qa.bitwiseAnd(1 << 4).eq(0));
      return img.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15)
        .rename('lst').updateMask(clear);
    }).median().clip(region);
};

// ---------------------------------------------------------------------------
// 1. A map on screen with a real legend: colour ramp, numbers, units
// ---------------------------------------------------------------------------
var first = gaul.filter(ee.Filter.eq('GAUL2_NAME', DISTRICTS[0]));
Map.centerObject(first, 12);
Map.addLayer(landsatLst(first.geometry()), VIS, 'LST 2024');
Map.addLayer(ee.Image().byte().paint(first, 1, 2), {palette: ['000000']}, 'Boundary');

var legend = ui.Panel({style: {position: 'bottom-left', padding: '8px'}});
legend.add(ui.Label(DISTRICTS[0] + ': land surface temperature',
                    {fontWeight: 'bold', fontSize: '14px'}));
legend.add(ui.Label('Landsat 8 and 9, median June to October 2024', {fontSize: '11px'}));
legend.add(ui.Thumbnail({image: ee.Image.pixelLonLat().select(0),
  params: {bbox: [0, 0, 1, 0.1], dimensions: '200x12', format: 'png',
           min: 0, max: 1, palette: PALETTE}}));
legend.add(ui.Panel([ui.Label(VIS.min + ' °C'), ui.Label('', {stretch: 'horizontal'}),
                     ui.Label(VIS.max + ' °C')], ui.Panel.Layout.flow('horizontal')));
Map.add(legend);

// ---------------------------------------------------------------------------
// 2. The series: one styled, print-resolution map per district
// ---------------------------------------------------------------------------
// visualize() bakes the colours in, so the exported GeoTIFF opens in any GIS
// or layout tool looking exactly like the screen. Scale 10 m is ample for A4.
DISTRICTS.forEach(function (name) {
  var d = gaul.filter(ee.Filter.eq('GAUL2_NAME', name));
  var styled = landsatLst(d.geometry()).visualize(VIS)
    .blend(ee.Image().byte().paint(d, 1, 3).visualize({palette: ['000000']}));
  Export.image.toDrive({image: styled, description: 'LST_map_' + name.replace(/ /g, '_'),
                        region: d.geometry().bounds(), scale: 10, maxPixels: 1e10});
});
// Run the tasks from the Tasks tab; each arrives in Drive as a styled GeoTIFF.

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Add all 27 West Java districts to the loop. What must stay fixed across
//    the series for the maps to be comparable?
// 2. Replace the fixed 22 to 46 °C range with each district's own 2nd to
//    98th percentile. What does a reader lose?
