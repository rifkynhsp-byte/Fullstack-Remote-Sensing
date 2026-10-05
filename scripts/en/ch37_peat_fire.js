//| title: Peat, drought and fire
//| description: Peat extent, burned area on and off peat in El Niño years, and monthly fire against rainfall in Central Kalimantan, all from open data.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 37 | Drained peat dries, dry peat burns.
 * ---------------------------------------------------------------------------
 * Open data only: Global Peatland Map 2.0 (1 km), MODIS MCD64A1 burned area,
 * FIRMS active fire and CHIRPS rainfall. The box covers Palangka Raya,
 * Sebangau and the former Mega Rice Project, plus mineral uplands to the north.
 */

var aoi = ee.Geometry.Rectangle([113.3, -3.4, 114.7, -1.2], null, false);
Map.centerObject(aoi, 8);

var gpm = ee.Image('projects/sat-io/open-datasets/GLOBAL-PEATLAND-DATABASE');
var peat = gpm.gte(1).unmask(0).rename('peat');
Map.addLayer(gpm.selfMask().clip(aoi), {min: 1, max: 2, palette: ['7b3f00', 'd2a86e']}, 'Peat');

// Burned area in one year, split into peat and not peat (km²).
function burnedIn(year) {
  return ee.ImageCollection('MODIS/061/MCD64A1').select('BurnDate')
    .filterDate(ee.Date.fromYMD(year, 1, 1), ee.Date.fromYMD(year + 1, 1, 1))
    .max().gt(0).unmask(0);
}
[2015, 2019, 2023].forEach(function (y) {
  var byPeat = ee.Image.pixelArea().divide(1e6).updateMask(burnedIn(y)).addBands(peat)
    .reduceRegion({reducer: ee.Reducer.sum().group(1, 'peat'), geometry: aoi, scale: 500,
                   maxPixels: 1e9, tileScale: 4});
  print('Burned ' + y + ' (km², group 1 = peat)', byPeat.get('groups'));
});
Map.addLayer(burnedIn(2015).selfMask().clip(aoi), {palette: ['c0392b']}, 'Burned 2015');

// Monthly fire on peat and rainfall, 2012-2024, as one chart.
var firms = ee.ImageCollection('FIRMS').select('T21');
var chirps = ee.ImageCollection('UCSB-CHG/CHIRPS/PENTAD').select('precipitation');
var months = ee.List.sequence(0, 12 * 13 - 1).map(function (i) {
  var d = ee.Date('2012-01-01').advance(i, 'month');
  var fires = firms.filterDate(d, d.advance(1, 'month')).count().updateMask(peat)
    .reduceRegion({reducer: ee.Reducer.sum(), geometry: aoi, scale: 1000, maxPixels: 1e9})
    .get('T21');
  var rain = chirps.filterDate(d, d.advance(1, 'month')).sum()
    .reduceRegion({reducer: ee.Reducer.mean(), geometry: aoi, scale: 5000}).get('precipitation');
  return ee.Feature(null, {date: d.millis(), fires: fires, rain_mm: rain});
});
print(ui.Chart.feature.byFeature(ee.FeatureCollection(months), 'date', ['fires', 'rain_mm'])
  .setChartType('LineChart')
  .setOptions({title: 'Fire pixel-days on peat and monthly rain',
               series: {0: {targetAxisIndex: 0, color: 'c0392b'},
                        1: {targetAxisIndex: 1, color: '2a78d6'}},
               vAxes: {0: {title: 'fire pixel-days'}, 1: {title: 'rain (mm)'}},
               hAxis: {format: 'yyyy'}}));
