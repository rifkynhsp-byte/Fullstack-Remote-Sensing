//| title: Training patches out, a Random Forest baseline in (Code Editor)
//| description: Build the Mahakam Delta image and label, score an Earth Engine Random Forest on the held-out block, and export the same area as TFRecord patches for PyTorch or TensorFlow.

/**
 * CHAPTER 31 | The Earth Engine half of a deep learning job
 * ---------------------------------------------------------------------------
 * Earth Engine cannot train a convolutional network. What it does very well
 * is everything before and after training:
 *   before: build a clean composite and a label image, and cut them into
 *           patches a network can read;
 *   after:  hold the prediction as an asset, next to every other layer, so it
 *           can be checked, mapped and summarised.
 *
 * This script does the "before" half and a Random Forest baseline, on the
 * same grid the Python tab uses:
 *   - 2021 Sentinel-2 composite, six bands, Cloud Score+ masked
 *   - ESA WorldCover 2021 as the label: 0 mangrove, 1 water, 2 other
 *   - training tiles 128 x 128 pixels at 10 m, on a 0.03 degree grid
 *   - one 768 x 768 pixel block held out, with no training tile within 2 km
 *
 * The labels are a map, not ground truth. Every accuracy here is agreement
 * with WorldCover.
 */

var BANDS = ['B2', 'B3', 'B4', 'B8', 'B11', 'B12'];
var delta = ee.Geometry.Rectangle([117.15, -1.00, 117.75, -0.30]);
var DEG_10M = 0.0000898315;          // 10 m at the equator, in degrees
var TILE = 128 * DEG_10M;            // one training tile
var HALF = 768 * DEG_10M / 2;        // half the held-out block
var testBox = ee.Geometry.Rectangle([117.37 - HALF, -0.66 - HALF,
                                     117.37 + HALF, -0.66 + HALF]);

// ===========================================================================
// PART 1. The image and the label
// ===========================================================================
function s2Composite(start, end, threshold) {
  var cs = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED');
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(delta).filterDate(start, end)
    .linkCollection(cs, ['cs_cdf'])
    .map(function (img) { return img.updateMask(img.select('cs_cdf').gte(threshold)); })
    .select(BANDS).median();
}

// 2021 to match WorldCover 2021; a looser two-year composite fills holes.
var composite = s2Composite('2021-01-01', '2022-01-01', 0.6)
  .unmask(s2Composite('2020-07-01', '2022-07-01', 0.4));
var label = ee.Image('ESA/WorldCover/v200/2021').select('Map')
  .remap([95, 80], [0, 1], 2).rename('label');
var stack = composite.addBands(label).toFloat();

// ===========================================================================
// PART 2. Training tiles on a spaced grid, away from the test block
// ===========================================================================
// Tiles 1.28 km wide, 0.03 degrees (about 3.3 km) apart, so no two touch.
// Neighbouring pixels look alike; if training and test pixels touched,
// the test score would flatter the model (chapter “Ground Truth and Sampling Design”).
var tiles = [];
for (var x = 117.15; x < 117.75 - TILE; x += 0.03) {
  for (var y = -0.30; y > -1.00 + TILE; y -= 0.03) {
    var nearTest = x + TILE > 117.37 - HALF - 0.02 && x < 117.37 + HALF + 0.02 &&
                   y > -0.66 - HALF - 0.02 && y - TILE < -0.66 + HALF + 0.02;
    if (!nearTest) {
      tiles.push(ee.Feature(ee.Geometry.Rectangle([x, y - TILE, x + TILE, y])));
    }
  }
}
tiles = ee.FeatureCollection(tiles);

// Drop tiles that are almost all sea: they teach nothing new.
tiles = label.eq(1).reduceRegions({collection: tiles, reducer: ee.Reducer.mean(),
                                   scale: 10, tileScale: 4})
  .filter(ee.Filter.lt('mean', 0.98));
print('Training tiles kept:', tiles.size());

// ===========================================================================
// PART 3. The baseline Earth Engine can train: a Random Forest per pixel
// ===========================================================================
// The class band must be an integer, so sample from composite + label, not
// from the all-float stack that is exported below.
var training = composite.addBands(label).stratifiedSample({
  numPoints: 3000, classBand: 'label', region: tiles.geometry(),
  scale: 10, seed: 42, tileScale: 4
});
var rf = ee.Classifier.smileRandomForest(100)
  .train(training, 'label', BANDS);

var rfMap = composite.classify(rf).clip(testBox);
var check = label.addBands(rfMap).sample({region: testBox, scale: 10,
                                          numPixels: 20000, seed: 1});
var matrix = check.errorMatrix('label', 'classification');
print('RF agreement with WorldCover, held-out block:', matrix.accuracy());
print('RF kappa:', matrix.kappa());

var classVis = {min: 0, max: 2, palette: ['075e11', '1a5bab', 'e8c872']};
Map.centerObject(testBox, 13);
Map.addLayer(composite, {bands: ['B11', 'B8', 'B4'], min: 100, max: 3500}, 'Sentinel-2 2021');
Map.addLayer(label.clip(testBox), classVis, 'WorldCover 2021 (label)');
Map.addLayer(rfMap, classVis, 'Random Forest');
Map.addLayer(tiles.style({color: 'white', fillColor: '00000000'}), {}, 'Training tiles');
Map.addLayer(ee.FeatureCollection([ee.Feature(testBox)])
  .style({color: 'ff2d55', fillColor: '00000000', width: 3}), {}, 'Held-out block');

// ===========================================================================
// PART 4. Patches out, for a network to train on
// ===========================================================================
// For a few hundred small tiles, the Python tab's ee.data.computePixels is
// quicker: no task, no bucket. For thousands of patches, export. TFRecord
// writes the image as fixed-size patches that TensorFlow reads directly and
// PyTorch reads with the `tfrecord` package (the author's Colab notebooks
// do exactly this).
Export.image.toCloudStorage({
  image: stack, description: 'mahakam_patches_2021',
  bucket: 'your-bucket',                            // <- your bucket
  fileNamePrefix: 'mahakam/patches_2021',
  region: delta, scale: 10, crs: 'EPSG:4326',
  fileFormat: 'TFRecord', maxPixels: 1e10,
  formatOptions: {patchDimensions: [128, 128], compressed: true}
});

// No bucket? The same export goes to Google Drive, where Colab can mount it.
Export.image.toDrive({
  image: stack, description: 'mahakam_patches_2021_drive',
  folder: 'ee_patches', fileNamePrefix: 'mahakam_patches_2021',
  region: delta, scale: 10, crs: 'EPSG:4326',
  fileFormat: 'TFRecord', maxPixels: 1e10,
  formatOptions: {patchDimensions: [128, 128], compressed: true}
});

// ===========================================================================
// PART 5. Predictions back in (after training elsewhere)
// ===========================================================================
// Option A, most common: write the prediction as a GeoTIFF in Python, upload
// it as an asset (Assets > New > GeoTIFF, or `earthengine upload image`),
// then treat it like any other layer:
//
//   var unet = ee.Image('projects/your-project/assets/mahakam_unet_2021');
//   Map.addLayer(unet, classVis, 'U-Net prediction');
//   print(label.addBands(unet.rename('unet'))
//     .sample({region: testBox, scale: 10, numPixels: 20000, seed: 1})
//     .errorMatrix('label', 'unet').accuracy());
//
// Option B, for maps that must be redrawn often: host the model on a Vertex
// AI endpoint and let Earth Engine call it tile by tile. This costs money
// every time a tile is computed. An outline, not run here:
//
//   var model = ee.Model.fromVertexAi({
//     endpoint: 'projects/your-project/locations/us-central1/endpoints/123',
//     inputTileSize: [64, 64], inputOverlapSize: [16, 16],
//     proj: ee.Projection('EPSG:4326').atScale(10), fixInputProj: true,
//     outputBands: {label: {type: ee.PixelType.float(), dimensions: 1}}
//   });
//   var predicted = model.predictImage(composite.divide(10000).toFloat());
