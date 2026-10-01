//| title: A multi sensor analysis ready stack
//| description: Optical, C band radar, L band radar, terrain and texture, fused into one image.

/**
 * CHAPTER 10 | The all weather feature stack
 * ---------------------------------------------------------------------------
 * Goal
 *   Build one ee.Image for a given year that carries every predictor a
 *   classifier will need: reflectance, spectral indices, C band and L band
 *   radar, elevation, slope and canopy texture.
 *
 * Why this is a function of year
 *   Writing the stack as getAnalysisReadyData(year) rather than as a linear
 *   script is the single change that turns a one off map into a monitoring
 *   system. chapter “Time Series and Change Detection” calls this same function in a loop to build a time
 *   series; chapter “Classical Supervised Learning” calls it once to train a classifier. Neither has to
 *   know how it works.
 *
 * Asset dependencies
 *   var aoi = ee.FeatureCollection('projects/YOUR_PROJECT/assets/aoi').geometry();
 */

// ---------------------------------------------------------------------------
// CONFIGURATION
// ---------------------------------------------------------------------------
// Everything a reader is expected to change lives at the top, in upper case.
// Nothing below this block should need editing to run over a new area.
var CLOUD_THRESHOLD = 25;   // percent. Scene level pre filter, see note below.
var SPECKLE_RADIUS  = 50;   // metres. Radar smoothing window.
var GLCM_WINDOW     = 4;    // pixels. Texture neighbourhood, see chapter “Spatial Texture Extraction”.

// ---------------------------------------------------------------------------
// HELPER 1. Cloud masking for Sentinel-2 Level-2A
// ---------------------------------------------------------------------------
// chapter “Cloud Masking and Composites” explains the SCL class codes in full. The short version: keep a
// pixel only if it is not cloud shadow (3), medium or high probability cloud
// (8, 9) or thin cirrus (10).
//
// The .divide(10000) converts stored integers to physical reflectance, 0 to 1.
// Doing it here, once, means every downstream index and every classifier sees
// physical units. Mixing scaled and unscaled bands is a silent, common and
// very hard to find error.
//
// copyProperties carries system:time_start forward. Without it the image
// loses its timestamp and any later filterDate or time series chart on the
// mapped collection returns nothing, with no error message.
function maskS2Clouds(image) {
  var scl = image.select('SCL');
  var clear = scl.neq(3).and(scl.neq(8)).and(scl.neq(9)).and(scl.neq(10));

  return image.updateMask(clear)
    .divide(10000)
    .select('B.*')
    .copyProperties(image, ['system:time_start']);
}

// ---------------------------------------------------------------------------
// HELPER 2. Spectral indices
// ---------------------------------------------------------------------------
// Four indices, each earning its place for a different reason. chapter “Band Math and Spectral Indices”
// derives them; here we just apply them.
function addIndices(image) {

  // NDVI: general photosynthetic vigour. Saturates over dense canopy, which
  // is precisely the mangrove case, so it is necessary but not sufficient.
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');

  // EVI: keeps responding where NDVI has saturated, because the blue term
  // corrects for atmospheric scattering and the soil adjustment reduces
  // background influence. The coefficients are the standard MODIS values.
  var evi = image.expression(
    '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))', {
      'NIR': image.select('B8'),
      'RED': image.select('B4'),
      'BLUE': image.select('B2')
    }).rename('EVI');

  // SAVI: soil adjusted. Matters on the landward fringe and over young
  // replanted stands where the background is visible between crowns.
  var savi = image.expression(
    '((NIR - RED) / (NIR + RED + 0.5)) * 1.5', {
      'NIR': image.select('B8'),
      'RED': image.select('B4')
    }).rename('SAVI');

  // MNDWI uses shortwave infrared rather than near infrared, which separates
  // open water from wet vegetation far better than plain NDWI. Over a delta
  // full of aquaculture ponds that distinction is the whole problem.
  var mndwi = image.normalizedDifference(['B3', 'B11']).rename('MNDWI');

  return image.addBands([ndvi, evi, savi, mndwi]);
}

// ---------------------------------------------------------------------------
// HELPER 3. Speckle filtering
// ---------------------------------------------------------------------------
// Radar speckle is inherent to coherent imaging, not a sensor fault. A focal
// median suppresses it while preserving edges better than a mean would.
//
// The window is specified in metres, not pixels, so the filter behaves the
// same way regardless of the scale the computation later runs at. Widening it
// gives a cleaner image and blurs narrow features; 50 m is a compromise that
// survives mangrove fringes roughly two pixels wide.
function speckleFilter(image) {
  return image.focal_median(SPECKLE_RADIUS, 'circle', 'meters');
}

// ---------------------------------------------------------------------------
// MAIN. Assemble one analysis ready image for a given year
// ---------------------------------------------------------------------------
function getAnalysisReadyData(year, aoi) {
  var startDate = ee.Date.fromYMD(year, 1, 1);
  var endDate   = ee.Date.fromYMD(year, 12, 31);

  // --- 1. Optical: Sentinel-2 -----------------------------------------------
  // Note the double defence against cloud. The metadata filter discards the
  // worst scenes cheaply before any pixels are touched, and the SCL mask then
  // removes surviving cloud pixel by pixel. In an extremely cloudy year,
  // raise CLOUD_THRESHOLD or remove the metadata filter entirely and let the
  // per pixel mask do all the work; see the discussion in chapter “Cloud Masking and Composites”.
  var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterDate(startDate, endDate)
    .filterBounds(aoi)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', CLOUD_THRESHOLD))
    .map(maskS2Clouds);

  var s2Composite = s2.median().clip(aoi);
  var s2Indices = addIndices(s2Composite);

  // --- 2. Radar, C band: Sentinel-1 -----------------------------------------
  // Three filters are mandatory and each removes a real failure mode.
  //   instrumentMode IW      the standard land mode; other modes have
  //                          different geometry and cannot be mixed in
  //   both polarisations     scenes carrying only VV would produce a band
  //                          mismatch when the collection is reduced
  //   select VV, VH          drops the incidence angle band, which is
  //                          metadata rather than a predictor
  //
  // Consider also filtering on orbitProperties_pass to a single direction.
  // Ascending and descending passes view the same terrain from opposite
  // sides, and mixing them adds a geometric signal that has nothing to do
  // with the ground.
  var s1 = ee.ImageCollection('COPERNICUS/S1_GRD')
    .filterDate(startDate, endDate)
    .filterBounds(aoi)
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
    .filter(ee.Filter.eq('instrumentMode', 'IW'))
    .select(['VV', 'VH']);

  var s1Composite = s1.median().clip(aoi).rename('S1_VV', 'S1_VH');
  var s1Filtered = speckleFilter(s1Composite);

  // --- 3. Radar, L band: ALOS PALSAR ----------------------------------------
  // L band penetrates the canopy and interacts with trunks and large branches,
  // so it carries structural information C band cannot reach.
  //
  // The yearly mosaic does not exist for every year. The ee.Algorithms.If
  // below falls back to the most recent earlier epoch rather than failing, so
  // the function stays callable across a whole time series. This is defensive
  // coding, and it is the difference between a script and a system.
  // Check what a layer COVERS, not just that it exists. The 2023 PALSAR
  // yearly mosaic covers only about a quarter of the Mahakam Delta; 2022
  // covers all of it. An earlier version took .first() of the year, and
  // sampleRegions then silently dropped three quarters of the training
  // points, because a point with any masked band is discarded.
  // Here the chosen year is laid over the year before, so gaps fall back to
  // the previous epoch instead of to nothing.
  var palsarCollection = ee.ImageCollection('JAXA/ALOS/PALSAR/YEARLY/SAR_EPOCH')
    .filterBounds(aoi);
  var palsarImage = palsarCollection
    .filter(ee.Filter.calendarRange(year - 1, year, 'year'))
    .sort('system:time_start')          // later year last, so it wins the mosaic
    .mosaic();

  // PALSAR ships digital numbers, not physical backscatter. The published
  // conversion to gamma nought in decibels is:
  //
  //     gamma0_dB = 10 * log10(DN^2) - 83.0
  //
  // Note the order: log10 of DN squared, times ten, minus 83. An earlier
  // version of this script raised 10 to the power of (log10(DN^2) - 83),
  // which is DN^2 times 10^-83: every pixel came out as zero and nothing
  // complained. Chart a band before you trust it.
  // Skipping this step is a real and common error: raw DN values are on a
  // completely different scale from the 0 to 1 reflectance bands beside them,
  // and a distance based classifier such as SVM will be dominated by whichever
  // band has the largest numeric range.
  var palsarDN = palsarImage.select(['HH', 'HV']).clip(aoi);
  var palsarGamma0 = palsarDN.pow(2).log10().multiply(10).subtract(83.0)
    .rename('PALSAR_HH', 'PALSAR_HV');

  // --- 4. Terrain -----------------------------------------------------------
  // The single most valuable non spectral predictor for mangroves, and the
  // fix for the classic failure of putting mangrove on a hillside. Mangroves
  // occupy the intertidal band, a few metres above sea level. Upland forest
  // that is spectrally identical is not. Elevation encodes that rule in a
  // form the classifier can learn.
  // AW3D30 v4.1 is a tiled collection (V2_2 is deprecated): mosaic, then
  // restore the native projection so slope is computed on the right grid.
  var aw3d = ee.ImageCollection('JAXA/ALOS/AW3D30/V4_1');
  var dem = aw3d.select('DSM').filterBounds(aoi).mosaic()
    .setDefaultProjection(aw3d.first().projection()).clip(aoi);
  var slope = ee.Terrain.slope(dem);

  // --- 5. Texture -----------------------------------------------------------
  // GLCM measures how pixel values co occur with their neighbours, which
  // captures canopy structure rather than canopy colour. It is what separates
  // a uniform plantation from a structurally complex natural stand when both
  // are spectrally the same.
  //
  // Two preparation steps are compulsory and easy to miss. glcmTexture needs
  // integer input, so the reflectance band is rescaled and cast; passing a
  // float silently returns nonsense. And it is applied to one band rather
  // than all of them, because the full GLCM output is 18 bands per input band
  // and stacking 18 times 10 predictors will exhaust memory and add little.
  var nir = s2Composite.select('B8').multiply(10000).toInt16();
  var glcm = nir.glcmTexture({size: GLCM_WINDOW});
  var contrast = glcm.select('B8_contrast').rename('contrast');
  var asm = glcm.select('B8_asm').rename('asm');

  // --- 6. Fuse --------------------------------------------------------------
  // .float() at the end forces a single consistent data type across the whole
  // stack. Without it the image carries a mix of int16, float and double
  // bands, and several classifiers and most export paths will refuse it.
  return s2Indices
    .addBands(s1Filtered)
    .addBands(palsarGamma0)
    .addBands(dem)
    .addBands(slope)
    .addBands(contrast)
    .addBands(asm)
    .float()
    .set('year', year);
}

// ---------------------------------------------------------------------------
// USE IT
// ---------------------------------------------------------------------------
// Replace this with your own area of interest asset.
var aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60]);  // Mahakam Delta

var image2023 = getAnalysisReadyData(2023, aoi);

// Always print the band names before going further. This one line prevents
// most of the errors in Appendix B, because nearly all of them reduce to a
// band that is not called what you thought it was called.
print('Bands in the stack:', image2023.bandNames());
print('Band count:', image2023.bandNames().size());

Map.centerObject(aoi, 11);
Map.addLayer(image2023, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.3},
  'S2 composite 2023');
Map.addLayer(image2023, {bands: ['S1_VH'], min: -25, max: -5},
  'Sentinel-1 VH', false);
Map.addLayer(image2023, {bands: ['DSM'], min: 0, max: 50,
  palette: ['#2b83ba', '#ffffbf', '#d7191c']}, 'Elevation', false);

// ---------------------------------------------------------------------------
// Why fuse at all? Put optical and radar side by side
// ---------------------------------------------------------------------------
// Radar in false colour (VV, VH, VV/VH) shows structure the optical image
// cannot: bright volume scattering over canopy, dark smooth water.
var s1FalseColour = image2023.select('S1_VV').addBands(image2023.select('S1_VH'))
  .addBands(image2023.select('S1_VV').subtract(image2023.select('S1_VH')));
Map.addLayer(s1FalseColour, {min: [-20, -26, 2], max: [0, -8, 12]},
  'Sentinel-1 VV, VH, VV-VH', false);

// Sample land pixels and compare what each sensor says. Where NDVI has
// flattened out near its ceiling, radar is still changing: that spread is
// the information fusion adds.
var land = ee.Image('MERIT/Hydro/v1_0_1').select('hnd').mask();
var pairs = image2023.select(['NDVI', 'S1_VH', 'PALSAR_HV']).updateMask(land)
  .sample({region: aoi, scale: 30, numPixels: 6000, seed: 7, geometries: false});
print(ui.Chart.feature.byFeature(pairs, 'NDVI', ['S1_VH'])
  .setChartType('ScatterChart')
  .setOptions({title: 'Optical saturates, radar keeps going',
               hAxis: {title: 'NDVI'}, vAxis: {title: 'Sentinel-1 VH (dB)'},
               pointSize: 2}));

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Toggle between the optical composite and the S1_VH layer over a stand of
//    mangrove at high tide. The bright double bounce return is the structural
//    signature chapter “Choosing Your Eyes” described. Find it.
// 2. Remove .divide(10000) from maskS2Clouds and rerun. The map will look
//    almost unchanged and every index will be wrong. Explain why.
// 3. Call getAnalysisReadyData for 2019 and check the Console for which
//    PALSAR epoch the fallback selected.
