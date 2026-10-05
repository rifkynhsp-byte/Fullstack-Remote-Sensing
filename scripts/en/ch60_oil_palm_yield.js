//| title: From the age of a palm to the fruit it can bear
//| description: Palm age, GEDI height and height-based biomass, health against palms of the same age, a fresh fruit bunch map and a per-desa summary for Kotawaringin Timur.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 60 | From the age of a palm to the fruit it can bear
 * ---------------------------------------------------------------------------
 *  1. age      planting year from the Landsat archive (Chapter 44, repeated here)
 *  2. height   GEDI L2A rh98, good-quality shots, 2019-2023
 *  3. biomass  Khalid (1999): AGB = (725 + 197 H) kg per palm x 136 palms/ha
 *  4. health   2023 dry-season NDVI against the median of palms of the SAME age;
 *              water, built and bare (Dynamic World) and open land or water
 *              (the author's 10-class model) are removed first
 *  5. fruit    FFB potential by age (rise 3-9, plateau 9-18, decline to 70 % at
 *              25), peak 34.5 t/ha/yr x 0.42 smallholder achievement, x a health
 *              multiplier (1.0, 0.9, 0.6). A model with stated assumptions; real
 *              numbers need mill records.
 */

// ---------------------------------------------------------------------------
// STEP 1. Age (as in Chapter 44)
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Rectangle([112.60, -2.50, 113.10, -2.00], null, false);   // Kotawaringin Timur
var palm = ee.ImageCollection('BIOPAMA/GlobalOilPalm/v1').select('classification').mosaic().lte(2).selfMask().clip(aoi);
function landsat(col, nir, swir2) {
  return ee.ImageCollection(col).filterBounds(aoi).map(function (img) {
    var qa = img.select('QA_PIXEL');
    var ok = qa.bitwiseAnd(1 << 3).eq(0).and(qa.bitwiseAnd(1 << 4).eq(0));
    return img.select([nir, swir2]).multiply(0.0000275).add(-0.2).normalizedDifference([nir, swir2])
      .rename('nbr').updateMask(ok).copyProperties(img, ['system:time_start']);
  });
}
var ls = landsat('LANDSAT/LT05/C02/T1_L2', 'SR_B4', 'SR_B7').merge(landsat('LANDSAT/LE07/C02/T1_L2', 'SR_B4', 'SR_B7'))
  .merge(landsat('LANDSAT/LC08/C02/T1_L2', 'SR_B5', 'SR_B7')).merge(landsat('LANDSAT/LC09/C02/T1_L2', 'SR_B5', 'SR_B7'));
var EMPTY = ee.ImageCollection([ee.Image.constant(0).rename('nbr').updateMask(0)]);
var dip = ee.ImageCollection(ee.List.sequence(1990, 2023).map(function (y) {
  var d = ee.Date.fromYMD(y, 1, 1);
  var m = ls.filterDate(d, d.advance(1, 'year')).merge(EMPTY).median();
  return m.addBands(ee.Image.constant(y).toInt16().rename('year')).addBands(m.multiply(-1).rename('q'));
})).qualityMosaic('q');
var age = ee.Image(2023).subtract(dip.select('year').updateMask(palm).updateMask(dip.select('nbr').lt(0.3))).rename('age');
var ageInt = age.toInt().rename('age_int');

// ---------------------------------------------------------------------------
// STEP 2. Height from GEDI, biomass from height
// ---------------------------------------------------------------------------
function quality(id, flag) {
  return ee.ImageCollection(id).filterBounds(aoi).filterDate('2019-04-01', '2024-01-01')
    .map(function (i) { return i.updateMask(i.select(flag).eq(1).and(i.select('degrade_flag').eq(0))); });
}
var rh98 = quality('LARSE/GEDI/GEDI02_A_002_MONTHLY', 'quality_flag').select('rh98').mosaic();
var agbd = quality('LARSE/GEDI/GEDI04_A_002_MONTHLY', 'l4_quality_flag').select('agbd').mosaic();
var shots = rh98.addBands(agbd).addBands(age).addBands(rh98.mask().and(agbd.mask()).and(age.mask()).rename('s').toInt())
  .stratifiedSample({numPoints: 4000, classBand: 's', region: aoi, scale: 25, seed: 5, tileScale: 8,
                     classValues: [1], classPoints: [4000]})
  .filter(ee.Filter.rangeContains('rh98', 0.1, 39.9)).filter(ee.Filter.gte('age', 1))
  .map(function (f) {   // Khalid (1999): (725 + 197 H) kg per palm x 136 palms per ha, in Mg/ha
    return f.set('agb_khalid', ee.Number(f.get('rh98')).multiply(197).add(725).multiply(136).divide(1000));
  });
print(ui.Chart.feature.groups(shots, 'age', 'agb_khalid', 's').setChartType('ScatterChart')
  .setOptions({title: 'Height-based palm biomass (Khalid) against age, one point per GEDI shot',
               hAxis: {title: 'age (years)'}, vAxis: {title: 'AGB (Mg/ha)'}, pointSize: 2, colors: ['#e6550d']}));
print('Prime-age (9-18 yr) medians: Khalid AGB and GEDI L4A (a global allometry, not built for palms)',
      shots.filter(ee.Filter.rangeContains('age', 9, 18)).reduceColumns(ee.Reducer.median().repeat(2), ['agb_khalid', 'agbd']));

// ---------------------------------------------------------------------------
// STEP 3. Health: NDVI against palms of the same age
// ---------------------------------------------------------------------------
var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(aoi).filterDate('2023-06-01', '2023-10-01')
  .linkCollection(ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'), ['cs'])
  .map(function (i) { return i.updateMask(i.select('cs').gte(0.6)); }).median();
var dw23 = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(aoi).filterDate('2023-01-01', '2024-01-01').select('label').mode();
var srtm = ee.Image('USGS/SRTMGL1_003').select('elevation');
var authorClass = ee.Image.cat([ee.ImageCollection('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL')
    .filter(ee.Filter.calendarRange(2023, 2023, 'year')).mosaic(), srtm, ee.Terrain.slope(srtm)])
  .classify(ee.Classifier.load('projects/ee-rifkynauvalhsp2/assets/LULC_Classifier_Embeddings_Topo_rubber'));
var notPalm = dw23.eq(0).or(dw23.eq(6)).or(dw23.eq(7)).or(authorClass.eq(3)).or(authorClass.eq(4));
var core = age.mask().and(notPalm.not());
var ndvi = s2.normalizedDifference(['B8', 'B4']).rename('ndvi').updateMask(core);
// The median NDVI of each age group, then each pixel against its own group.
var groups = ee.List(ndvi.addBands(ageInt).reduceRegion({reducer: ee.Reducer.median().group(1, 'age_int'),
  geometry: aoi, scale: 30, maxPixels: 1e10, tileScale: 16}).get('groups'));
var expected = ageInt.remap(groups.map(function (g) { return ee.Dictionary(g).get('age_int'); }),
                            groups.map(function (g) { return ee.Dictionary(g).get('median'); }));
var dev = ndvi.subtract(expected).rename('dev');
// Estate roads and drains are 1-2 pixel lines of low NDVI: a morphological opening removes them.
var low = dev.lt(-0.05).unmask(0);
var lines = low.and(low.focalMin(1, 'square', 'pixels').focalMax(1, 'square', 'pixels').not());
dev = dev.updateMask(lines.not());
var health = ee.Image(1).where(dev.lt(-0.05), 2).where(dev.lt(-0.15), 3).updateMask(dev.mask());

// ---------------------------------------------------------------------------
// STEP 4. Fresh fruit bunches: potential by age x achievement x health
// ---------------------------------------------------------------------------
var PEAK = 34.5, ACHIEVE = 0.42;
var a = age.toFloat();
var pot = ee.Image(0).where(a.gte(3).and(a.lt(9)), a.subtract(3).divide(6)).where(a.gte(9).and(a.lte(18)), 1)
  .where(a.gt(18).and(a.lte(25)), ee.Image(1).subtract(a.subtract(18).multiply(0.3 / 7))).where(a.gt(25), 0.7)
  .multiply(PEAK * ACHIEVE);
var ffb = pot.multiply(ee.Image(1.0).where(dev.lt(-0.05), 0.9).where(dev.lt(-0.15), 0.6)).updateMask(dev.mask()).rename('ffb');
var areaHa = ee.Image.pixelArea().divide(1e4);
var tot = ffb.multiply(areaHa).rename('t').addBands(areaHa.updateMask(ffb.mask()).rename('ha'))
  .reduceRegion({reducer: ee.Reducer.sum(), geometry: aoi, scale: 30, maxPixels: 1e10, tileScale: 16});
print('Modelled FFB for the scored palm area', tot.set('mean_t_ha_yr', ee.Number(tot.get('t')).divide(tot.get('ha'))));

// ---------------------------------------------------------------------------
// STEP 5. Per desa, the unit a district office plans with
// ---------------------------------------------------------------------------
var desa = ee.FeatureCollection('projects/shaped-producer-482312-m0/assets/ijb/idn_desa_bps').filterBounds(aoi);
var perDesa = ffb.multiply(areaHa).rename('t').addBands(areaHa.updateMask(ffb.mask()).rename('ha'))
  .reduceRegions({collection: desa, reducer: ee.Reducer.sum(), scale: 30, tileScale: 16})
  .filter(ee.Filter.gt('ha', 50))
  .map(function (f) { return f.set('t_ha', ee.Number(f.get('t')).divide(f.get('ha'))); });
print('Top 15 desa by modelled FFB (t per year)', perDesa.sort('t', false).limit(15).select(['nama', 'kab', 'ha', 't', 't_ha']));

// ---------------------------------------------------------------------------
// STEP 6. Maps
// ---------------------------------------------------------------------------
Map.centerObject(aoi, 11);
Map.addLayer(health, {min: 1, max: 3, palette: ['d9f0d3', 'fdae61', 'b2182b']}, 'Health: as expected, below, well below its age group');
Map.addLayer(ffb, {min: 0, max: 15, palette: ['ffffe5', 'fee391', 'fe9929', 'cc4c02', '662506']}, 'Modelled FFB (t/ha/yr)', false);
// The per-desa numbers are in the table above. Drawing them as a map layer recomputes every desa for
// every map tile and times out; Export.table.toDrive(perDesa) and a join in QGIS is the practical route.
Map.addLayer(ee.Image().byte().paint(desa, 1, 1), {palette: ['555555']}, 'Desa boundaries (BPS)', false);
