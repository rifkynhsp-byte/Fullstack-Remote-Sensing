//| title: How old is this plantation?
//| description: Date oil palm planting from the deepest dip in 34 years of Landsat NBR, check it against GEDI height, and map life stages in Kotawaringin Timur.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 44 | How old is this plantation?
 * ---------------------------------------------------------------------------
 * Planting oil palm starts with clearing: the land is bare for a year or two,
 * then the canopy closes again over about five years. In a yearly series of
 * the Normalised Burn Ratio (NBR, sensitive to bare soil and canopy water)
 * the clearing shows as the deepest dip. The year of that dip is a good
 * estimate of the planting year, and 2023 minus it is the age.
 *
 *   palm pixels   Descals et al. (2021) global oil palm map
 *   time series   Landsat 5, 7, 8, 9 Collection 2 surface reflectance, 1990-2023
 *   check         GEDI L2A rh98 height should rise with age
 *
 * The growth-curve fit to the GEDI pairs is in the Python notebook.
 */

// ---------------------------------------------------------------------------
// STEP 1. Area and palm pixels
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Rectangle([112.60, -2.50, 113.10, -2.00], null, false);   // Kotawaringin Timur
var palm = ee.ImageCollection('BIOPAMA/GlobalOilPalm/v1').select('classification').mosaic()
  .lte(2).selfMask().clip(aoi);
var YEARS = ee.List.sequence(1990, 2023);

// ---------------------------------------------------------------------------
// STEP 2. Landsat 5-9 cloud-masked, one index per scene
// ---------------------------------------------------------------------------
function landsat(col, b1, b2) {
  return ee.ImageCollection(col).filterBounds(aoi).map(function (img) {
    var qa = img.select('QA_PIXEL');
    var ok = qa.bitwiseAnd(1 << 3).eq(0).and(qa.bitwiseAnd(1 << 4).eq(0));   // no cloud, no shadow
    var sr = img.select([b1, b2]).multiply(0.0000275).add(-0.2);
    // normalizedDifference makes a new image: copy the date, or filterDate finds nothing.
    return sr.normalizedDifference([b1, b2]).rename('nbr').updateMask(ok)
      .copyProperties(img, ['system:time_start']);
  });
}
var ls = landsat('LANDSAT/LT05/C02/T1_L2', 'SR_B4', 'SR_B7')
  .merge(landsat('LANDSAT/LE07/C02/T1_L2', 'SR_B4', 'SR_B7'))
  .merge(landsat('LANDSAT/LC08/C02/T1_L2', 'SR_B5', 'SR_B7'))
  .merge(landsat('LANDSAT/LC09/C02/T1_L2', 'SR_B5', 'SR_B7'));

// ---------------------------------------------------------------------------
// STEP 3. One median per year, and the deepest dip
// ---------------------------------------------------------------------------
// Some early years have no clear scene here; a masked placeholder keeps the band.
var EMPTY = ee.ImageCollection([ee.Image.constant(0).rename('nbr').updateMask(0)]);
function annualSeries(col) {
  return ee.ImageCollection(YEARS.map(function (y) {
    var d = ee.Date.fromYMD(y, 1, 1);
    return col.filterDate(d, d.advance(1, 'year')).merge(EMPTY).median()
      .addBands(ee.Image.constant(y).toInt16().rename('year')).set('year', y);
  }));
}
var annual = annualSeries(ls);
// qualityMosaic picks, per pixel, the year with the highest -NBR: the deepest dip.
var negate = function (i) { return i.addBands(i.select('nbr').multiply(-1).rename('q')); };
var dip = annual.map(negate).qualityMosaic('q');
var plantYear = dip.select('year').updateMask(palm).updateMask(dip.select('nbr').lt(0.3));
var age = ee.Image(2023).subtract(plantYear).rename('age');

// ---------------------------------------------------------------------------
// STEP 4. Five palm pixels: their whole NBR history
// ---------------------------------------------------------------------------
var pts = palm.sample({region: aoi, scale: 30, numPixels: 400, seed: 11, geometries: true}).limit(5);
print(ui.Chart.image.seriesByRegion(annual.map(function (i) {
    return i.select('nbr').set('system:time_start', ee.Date.fromYMD(i.get('year'), 7, 1).millis());
  }), pts, ee.Reducer.first(), 'nbr', 30)
  .setOptions({title: 'Five palm pixels: yearly NBR, 1990-2023. The deepest dip is the clearing before planting.',
               vAxis: {title: 'NBR'}, lineWidth: 1, pointSize: 2}));

// ---------------------------------------------------------------------------
// STEP 5. Is the age believable? GEDI height should rise with it
// ---------------------------------------------------------------------------
var rh98 = ee.ImageCollection('LARSE/GEDI/GEDI02_A_002_MONTHLY').filterBounds(aoi)
  .filterDate('2019-04-01', '2024-01-01')
  .map(function (i) { return i.updateMask(i.select('quality_flag').eq(1).and(i.select('degrade_flag').eq(0))).select('rh98'); })
  .mosaic();
var pairs = rh98.addBands(age).addBands(rh98.mask().and(age.mask()).rename('s').toInt())
  .stratifiedSample({numPoints: 3000, classBand: 's', region: aoi, scale: 25, seed: 3, tileScale: 8,
                     classValues: [1], classPoints: [3000]})
  .filter(ee.Filter.lte('rh98', 25));   // oil palm does not reach 25 m: taller returns are neighbouring forest
print(ui.Chart.feature.byFeature(pairs, 'age', 'rh98').setChartType('ScatterChart')
  .setOptions({title: 'GEDI rh98 against the dated age of the palm under it', hAxis: {title: 'age (years)'},
               vAxis: {title: 'rh98 (m)'}, pointSize: 2, colors: ['#2a78d6']}));

// ---------------------------------------------------------------------------
// STEP 6. Sensitivity: NDVI instead of NBR, and ambiguous double dips
// ---------------------------------------------------------------------------
var lsNdvi = landsat('LANDSAT/LT05/C02/T1_L2', 'SR_B4', 'SR_B3')
  .merge(landsat('LANDSAT/LE07/C02/T1_L2', 'SR_B4', 'SR_B3'))
  .merge(landsat('LANDSAT/LC08/C02/T1_L2', 'SR_B5', 'SR_B4'))
  .merge(landsat('LANDSAT/LC09/C02/T1_L2', 'SR_B5', 'SR_B4'));
var plantYearNdvi = annualSeries(lsNdvi).map(negate).qualityMosaic('q').select('year').updateMask(palm);
// A second dip more than 4 years away that is almost as deep: planted, burned or replanted.
var second = annual.map(function (i) { return i.updateMask(i.select('year').subtract(plantYear).abs().gt(4)); })
  .map(negate).qualityMosaic('q');
var ambiguous = second.select('nbr').subtract(dip.select('nbr')).lt(0.05).updateMask(plantYear.mask());
var area = ee.Image.pixelArea().divide(1e4);
var diff = plantYear.subtract(plantYearNdvi).abs();
print('Sensitivity (hectares)', ee.Image.cat([
    area.updateMask(plantYear.mask()).rename('palm_dated'), area.updateMask(diff.lte(1)).rename('nbr_ndvi_within_1yr'),
    area.updateMask(diff.lte(3)).rename('nbr_ndvi_within_3yr'), area.updateMask(ambiguous).rename('ambiguous_double_dip')])
  .reduceRegion({reducer: ee.Reducer.sum(), geometry: aoi, scale: 30, maxPixels: 1e10, tileScale: 8}));

// ---------------------------------------------------------------------------
// STEP 7. Life stages and the age map
// ---------------------------------------------------------------------------
var stage = ee.Image(0).where(age.lt(3), 1).where(age.gte(3).and(age.lt(9)), 2)
  .where(age.gte(9).and(age.lt(19)), 3).where(age.gte(19).and(age.lt(25)), 4)
  .where(age.gte(25), 5).updateMask(age.mask()).rename('stage');
print('Area by life stage (ha): 1 immature 0-2, 2 young 3-8, 3 prime 9-18, 4 mature 19-24, 5 replanting due 25+',
      area.addBands(stage).reduceRegion({reducer: ee.Reducer.sum().group(1, 'stage'), geometry: aoi, scale: 30,
                                         maxPixels: 1e10, tileScale: 8}).get('groups'));
Map.centerObject(aoi, 11);
Map.addLayer(age, {min: 0, max: 30, palette: ['ffffcc', 'a1dab4', '41b6c4', '2c7fb8', '253494']}, 'Palm age in 2023 (years)');
Map.addLayer(ambiguous.selfMask(), {palette: ['e34948']}, 'Ambiguous: a second dip almost as deep', false);
