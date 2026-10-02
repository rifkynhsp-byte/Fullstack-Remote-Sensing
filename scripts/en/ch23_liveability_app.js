//| title: Where is it liveable? A Greater Bandung explorer (Earth Engine App)
//| description: A complete Earth Engine App: seven liveability indicators from public data, a slider for each weight, a score map that redraws, and a click panel that profiles any place. Publish it from the Code Editor with Apps > New App.

/**
 * CHAPTER 23 | From script to tool
 * ---------------------------------------------------------------------------
 * Seven indicators, each rescaled from worst (0) to best (1) between stated
 * limits, then combined with weights the USER sets. The analysis is the same
 * as in earlier chapters; what is new is that someone who has never seen this
 * code can ask their own question of it.
 *
 * Everything is public Earth Engine data: no uploads, no assets.
 */

// ---------------------------------------------------------------- the area
var area = ee.FeatureCollection('FAO/GAUL/2025/level2')
  .filter(ee.Filter.eq('GAUL1_NAME', 'Jawa Barat'))
  .filter(ee.Filter.inList('GAUL2_NAME', ['Kota Bandung', 'Kota Cimahi', 'Bandung', 'Bandung Barat']));
var geom = area.geometry();

// ---------------------------------------------------------------- the seven layers
function landsatST(img) {
  var qa = img.select('QA_PIXEL');
  var clear = qa.bitwiseAnd(1 << 3).eq(0).and(qa.bitwiseAnd(1 << 4).eq(0));    // no cloud, no shadow
  return img.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15).updateMask(clear);
}
var heat = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2').merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
  .filterBounds(geom).filterDate('2023-06-01', '2024-10-01').filter(ee.Filter.calendarRange(6, 9, 'month'))
  .map(landsatST).median().rename('heat');
var dw = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(geom)
  .filterDate('2024-01-01', '2025-01-01').select(['trees', 'grass']).mean();
var greenery = dw.select('trees').add(dw.select('grass')).focalMean(300, 'circle', 'meters').rename('greenery');
var flooding = ee.Image('MERIT/Hydro/v1_0_1').select('hnd').rename('flooding');   // height above nearest drainage
var slopes = ee.Terrain.slope(ee.ImageCollection('COPERNICUS/DEM/GLO30').filterBounds(geom).select('DEM')
  .mosaic().setDefaultProjection('EPSG:4326', null, 30)).rename('slopes');
var air = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_NO2').filterDate('2024-01-01', '2025-01-01')
  .select('tropospheric_NO2_column_number_density').mean().rename('air');
var services = ee.ImageCollection('NOAA/VIIRS/DNB/ANNUAL_V22').filterDate('2024-01-01', '2025-01-01').first()
  .select('average').rename('services');                                           // night light as a proxy
var crowding = ee.ImageCollection('WorldPop/GP/100m/pop').filter(ee.Filter.eq('country', 'IDN'))
  .filter(ee.Filter.eq('year', 2020)).mosaic().unmask(0).rename('crowding');       // people per hectare; gaps = nobody

// Worst and best value of each indicator: the limits the 0..1 scale runs between.
var INDICATORS = [
  {key: 'heat',     label: 'Cooler (land surface °C)',    image: heat,     worst: 40,     best: 25,     weight: 2},
  {key: 'greenery', label: 'Greener (trees + grass)',     image: greenery, worst: 0,      best: 0.6,    weight: 2},
  {key: 'flooding', label: 'Away from flooding (HAND m)', image: flooding, worst: 0,      best: 15,     weight: 2},
  {key: 'slopes',   label: 'Flatter (slope °)',           image: slopes,   worst: 30,     best: 0,      weight: 1},
  {key: 'air',      label: 'Cleaner air (NO₂)',           image: air,      worst: 5e-5,   best: 1.5e-5, weight: 1},
  {key: 'services', label: 'Near services (night light)', image: services, worst: 0,      best: 20,     weight: 2},
  {key: 'crowding', label: 'Less crowded (people/ha)',    image: crowding, worst: 150,    best: 0,      weight: 1}
];
// (value - worst) / (best - worst), clamped: 1 is always the good end
var good = ee.Image.cat(INDICATORS.map(function (d) {
  return d.image.subtract(d.worst).divide(d.best - d.worst).clamp(0, 1).rename(d.key);
})).clip(geom);

// ---------------------------------------------------------------- the user interface
var PALETTE = ['#a50026', '#f46d43', '#fee08b', '#a6d96a', '#1a9850'];
var panel = ui.Panel({style: {width: '330px', padding: '8px'}});
panel.add(ui.Label('Where is it liveable?', {fontSize: '20px', fontWeight: 'bold'}));
panel.add(ui.Label('Greater Bandung. Move a slider to say how much each thing matters to you; ' +
                   'the map redraws. Click the map to see why a place scores as it does.', {fontSize: '12px'}));

var sliders = {};
INDICATORS.forEach(function (d) {
  var s = ui.Slider({min: 0, max: 3, step: 1, value: d.weight, style: {stretch: 'horizontal'}, onChange: redraw});
  sliders[d.key] = s;
  panel.add(ui.Label(d.label, {fontSize: '12px', margin: '6px 8px 0 8px'})).add(s);
});
var info = ui.Panel();
panel.add(ui.Label('Click a place on the map', {fontWeight: 'bold', margin: '12px 8px 4px 8px'})).add(info);
panel.add(ui.Label('Data: Landsat 8/9, Dynamic World, MERIT Hydro, Copernicus DEM, Sentinel-5P, VIIRS, WorldPop. ' +
                   'A score is a summary of your weights, not a verdict on a neighbourhood.',
                   {fontSize: '10px', color: 'grey'}));
ui.root.insert(0, panel);

// A colour bar, so the map can be read without the code.
var legend = ui.Panel({style: {position: 'bottom-right', padding: '6px'}});
legend.add(ui.Label('Liveability score', {fontWeight: 'bold', fontSize: '12px'}));
legend.add(ui.Thumbnail({image: ee.Image.pixelLonLat().select(0), params: {bbox: '0,0,1,0.1', dimensions: '120x10',
  format: 'png', min: 0, max: 1, palette: PALETTE}}));
legend.add(ui.Panel([ui.Label('worse', {fontSize: '10px'}), ui.Label('better', {fontSize: '10px', margin: '0 0 0 60px'})],
                    ui.Panel.Layout.flow('horizontal')));
Map.add(legend);
Map.centerObject(area, 10);
Map.style().set('cursor', 'crosshair');

function currentScore() {
  var total = 0, img = ee.Image(0);
  INDICATORS.forEach(function (d) {
    var w = sliders[d.key].getValue();
    total += w;
    img = img.add(good.select(d.key).multiply(w));
  });
  return img.divide(Math.max(total, 1)).rename('score').clip(geom);
}

function redraw() {
  Map.layers().reset();                                       // replace, don't stack, layers
  Map.addLayer(currentScore(), {min: 0.2, max: 0.8, palette: PALETTE}, 'Liveability score');
  Map.addLayer(ee.Image().paint(area, 0, 1), {palette: ['333333']}, 'Districts');
}
redraw();

Map.onClick(function (pt) {
  info.clear().add(ui.Label('Computing...'));                 // show that something is happening
  var p = ee.Geometry.Point([pt.lon, pt.lat]).buffer(250);
  good.addBands(currentScore()).reduceRegion({reducer: ee.Reducer.mean(), geometry: p, scale: 30})
    .evaluate(function (v) {                                   // evaluate, never getInfo, in an app
      info.clear();
      if (!v || v.score === null) { info.add(ui.Label('Outside Greater Bandung.')); return; }
      info.add(ui.Label('Score ' + v.score.toFixed(2) + '  (' + pt.lat.toFixed(4) + ', ' + pt.lon.toFixed(4) + ')',
                        {fontWeight: 'bold'}));
      INDICATORS.forEach(function (d) {
        var x = v[d.key] === null ? 0 : v[d.key];
        var bar = new Array(Math.round(x * 10) + 1).join('■');   // ES5: the Code Editor has no String.repeat
        info.add(ui.Label(d.label + ': ' + bar + ' ' + x.toFixed(2), {fontSize: '11px'}));
      });
    });
});
