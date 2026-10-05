//| title: LiDAR beyond the forest: terrain and cities
//| description: What 1 m LiDAR terrain shows at the Oso landslide that a 30 m DEM cannot, and a 3D city from the Dutch AHN4: building height, tree canopy, solar roofs and land below sea level in Rotterdam.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 74 | LiDAR beyond the forest: terrain and cities
 * ---------------------------------------------------------------------------
 * Most LiDAR flown in the world is flown for terrain and for cities. Two
 * national programmes make that data free, and Earth Engine carries both:
 *   USGS 3DEP 1 m  bare-earth terrain models for the United States
 *   AHN4           0.5 m surface (DSM) and terrain (DTM) models for the Netherlands
 * Part 1: Oso, Washington, where a slope failure on 22 March 2014 buried the
 * Steelhead Haven neighbourhood. Part 2: central Rotterdam in 3D.
 */

// ---------------------------------------------------------------------------
// STEP 1. Oso: three terrain models of the same slope
// ---------------------------------------------------------------------------
var oso = ee.Geometry.Rectangle([-121.875, 48.266, -121.815, 48.300], null, false);
var col3dep = ee.ImageCollection('USGS/3DEP/1m').filterBounds(oso);
var lidar = col3dep.mosaic().rename('elev').setDefaultProjection(col3dep.first().projection());
var srtm = ee.Image('USGS/SRTMGL1_003').rename('elev');
var cop = ee.ImageCollection('COPERNICUS/DEM/GLO30_2024_1').filterBounds(oso).select('DEM').mosaic()
  .setDefaultProjection(ee.Projection('EPSG:4326').atScale(30)).rename('elev');
var DEMS = {'LiDAR 1 m (3DEP 2016)': [lidar, 1], 'SRTM 30 m (2000)': [srtm, 30], 'Copernicus 30 m': [cop, 30]};

// ---------------------------------------------------------------------------
// STEP 2. A profile across the slide, from each terrain model
// ---------------------------------------------------------------------------
var transect = ee.Geometry.LineString([[-121.848, 48.297], [-121.848, 48.270]]);
var pts = ee.FeatureCollection(ee.List.sequence(0, 299).map(function (i) {
  var f = ee.Number(i).divide(299);
  return ee.Feature(ee.Geometry.Point([-121.848, ee.Number(48.297).subtract(f.multiply(0.027))]),
                    {distance_m: f.multiply(3002)});
}));
var profile = ee.Image.cat([lidar.rename('lidar_1m'), srtm.rename('srtm_30m'), cop.rename('copernicus_30m')])
  .reduceRegions({collection: pts, reducer: ee.Reducer.first(), scale: 1});
print(ui.Chart.feature.byFeature(profile, 'distance_m', ['lidar_1m', 'srtm_30m', 'copernicus_30m'])
  .setOptions({title: 'Elevation across the Oso slide, north to south (m)', hAxis: {title: 'distance (m)'},
               vAxis: {title: 'elevation (m)'}, lineWidth: 1.5, colors: ['#0b0b0b', '#eb6834', '#2a78d6']}));

// ---------------------------------------------------------------------------
// STEP 3. Slope and roughness: what 30 m smooths away
// ---------------------------------------------------------------------------
Object.keys(DEMS).forEach(function (name) {
  var img = DEMS[name][0], scale = DEMS[name][1];
  var s = ee.Terrain.slope(img);
  var rough = s.reduceNeighborhood(ee.Reducer.stdDev(), ee.Kernel.square(15, 'meters')).rename('rough');
  print(name, s.rename('slope').addBands(s.gt(35).rename('steep')).addBands(rough).reduceRegion({
    reducer: ee.Reducer.mean().combine(ee.Reducer.percentile([50, 95]), '', true), geometry: oso, scale: scale, maxPixels: 1e9}));
});

// ---------------------------------------------------------------------------
// STEP 4. Rotterdam: the city as surface minus ground
// ---------------------------------------------------------------------------
var rdam = ee.Geometry.Rectangle([4.462, 51.900, 4.500, 51.925], null, false);
var ahnCol = ee.ImageCollection('AHN/AHN4').filterBounds(rdam);
var projA = ahnCol.first().select('dsm').projection();
var ahn = ahnCol.mosaic();
var dsm = ahn.select('dsm').setDefaultProjection(projA), dtm = ahn.select('dtm').setDefaultProjection(projA);
// The DTM has holes under buildings; fill them from the surrounding ground before subtracting.
var ground = dtm.reduceResolution({reducer: ee.Reducer.mean(), maxPixels: 64}).reproject(projA.atScale(2));
[10, 30, 80].forEach(function (r) { ground = ground.unmask(ground.focalMedian(r, 'square', 'meters')); });
ground = ground.resample('bilinear');
var ndsm = dsm.subtract(ground).max(0).rename('ndsm');                 // height above ground
var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(rdam).filterDate('2022-05-01', '2022-09-30')
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).median();
var ndvi = s2.normalizedDifference(['B8', 'B4']);
var water = dtm.mask().not().and(dsm.mask().not());                     // no LiDAR return at all: open water
var smooth = dsm.focalMedian(1, 'square', 'meters');
var roofSlope = ee.Terrain.slope(smooth), aspect = ee.Terrain.aspect(smooth);

// ---------------------------------------------------------------------------
// STEP 5. Buildings, trees, solar roofs and land below sea level
// ---------------------------------------------------------------------------
var tall = ndsm.gt(2.5);
var building = tall.and(ndvi.lt(0.3));                                   // tall and not green
var tree = tall.and(ndvi.gte(0.4));                                      // tall and green
var roof = building.focalMin(1, 'square', 'meters');                     // roof interiors, edges removed
var south = aspect.gte(135).and(aspect.lte(225));
var solar = roof.and(roofSlope.lt(10).or(roofSlope.lt(60).and(south)));  // flat, or tilted to the south
var area = ee.Image.pixelArea();
var t = ee.Image.cat([area.rename('total'), area.updateMask(building).rename('building'), area.updateMask(roof).rename('roof'),
                      area.updateMask(tree).rename('tree'), area.updateMask(solar).rename('solar'),
                      ndsm.updateMask(building).multiply(area).rename('volume'), area.updateMask(ground.lt(0)).rename('below_sea'),
                      area.updateMask(water).rename('water')])
  .reduceRegion({reducer: ee.Reducer.sum(), geometry: rdam, scale: 1, maxPixels: 1e10, tileScale: 16});
var land = ee.Number(t.get('total')).subtract(t.get('water'));
print('Rotterdam centre', ee.Dictionary({
  area_ha: ee.Number(t.get('total')).divide(1e4),
  below_sea_share_of_land: ee.Number(t.get('below_sea')).divide(land),
  building_share_of_land: ee.Number(t.get('building')).divide(land),
  tree_share_of_land: ee.Number(t.get('tree')).divide(land),
  mean_building_height_m: ee.Number(t.get('volume')).divide(t.get('building')),
  solar_share_of_roof_interiors: ee.Number(t.get('solar')).divide(t.get('roof')),
  screening_solar_GWh_yr: ee.Number(t.get('solar')).multiply(1000 * 0.20).divide(1e6)}));   // 1000 kWh/m2/yr x 20 % efficiency

// ---------------------------------------------------------------------------
// STEP 6. Maps
// ---------------------------------------------------------------------------
Map.centerObject(oso, 14);
Map.addLayer(ee.Terrain.hillshade(lidar, 315, 35), {min: 0, max: 255}, 'Oso: LiDAR 1 m hillshade');
Map.addLayer(ee.Terrain.hillshade(srtm, 315, 35), {min: 0, max: 255}, 'Oso: SRTM 30 m hillshade', false);
Map.addLayer(ndsm, {min: 0, max: 40, palette: ['ffffff', 'fee391', 'fe9929', 'cc4c02', '662506']}, 'Rotterdam: height above ground (m)', false);
Map.addLayer(ee.Image(0).where(tree, 1).where(building, 2).where(solar, 3).selfMask(),
             {min: 1, max: 3, palette: ['1b7837', '969696', 'fd8d3c']}, 'Rotterdam: tree, building, solar roof', false);
Map.addLayer(ground, {min: -6, max: 6, palette: ['08306b', '4292c6', 'c6dbef', 'ffffff', 'fdd49e', 'd7301f', '7f0000']},
             'Rotterdam: ground height (m above NAP)', false);
