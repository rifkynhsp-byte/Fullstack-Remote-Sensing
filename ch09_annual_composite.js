//| title: A cloud free annual composite
//| description: Mask cloud per pixel, add indices, and reduce a year of imagery to one image.

/**
 * CHAPTER 9 | From a stack of cloudy scenes to one clean image
 * ---------------------------------------------------------------------------
 * Goal
 *   Build a single, seamless, cloud free image representing a full year over
 *   the Mahakam Delta, carrying NDVI and NDWI alongside the raw bands.
 *
 * Why compositing beats scene picking
 *   In equatorial Indonesia a genuinely clear scene may not exist in a given
 *   year. Rather than hunting for one, take every scene, delete the bad
 *   pixels, and let the median of what remains fill the holes. Each output
 *   pixel is then assembled from whichever dates happened to be clear there.
 *
 * Note the deliberate omission
 *   There is no CLOUDY_PIXEL_PERCENTAGE filter here. Discarding a scene that
 *   is 80 percent cloudy also discards the 20 percent that was clear, and
 *   over a small delta that clear fifth may be exactly the part you need.
 */

// ---------------------------------------------------------------------------
// STEP 1. Area of interest and raw collection
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Point([117.58, -0.84]);   // Mahakam Delta, Indonesia

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterDate('2023-01-01', '2023-12-31')
  .filterBounds(aoi);

print('Scenes available for compositing:', s2.size());

// ---------------------------------------------------------------------------
// STEP 2. One function, applied to every scene
// ---------------------------------------------------------------------------
// This function receives one image and returns one image. It never mentions
// the collection. That separation is the whole point: write the recipe once
// for a single scene, then let map() fan it out across the archive.
var maskCloudsAndAddIndices = function (image) {

  // (a) Cloud masking from the Scene Classification Layer.
  //
  // Level-2A ships an SCL band holding a per pixel class label produced by
  // ESA's Sen2Cor processor. The codes worth knowing:
  //
  //     1  saturated or defective      7  unclassified
  //     2  dark area pixels            8  cloud, medium probability
  //     3  cloud shadow                9  cloud, high probability
  //     4  vegetation                 10  thin cirrus
  //     5  bare soil                  11  snow or ice
  //     6  water
  //
  // Keeping a pixel means asserting it is none of the contaminated classes.
  // neq() returns 1 where the test passes and 0 where it fails, and and()
  // multiplies those tests together, so the mask is 1 only where every test
  // passed.
  //
  // Class 11 is included for portability rather than necessity. There is no
  // snow on a tropical delta, but Sen2Cor mislabels bright sand and cloud
  // edges as snow often enough to be worth excluding.
  var scl = image.select('SCL');

  var clear = scl.neq(3)      // not cloud shadow
    .and(scl.neq(8))          // not medium probability cloud
    .and(scl.neq(9))          // not high probability cloud
    .and(scl.neq(10))         // not thin cirrus
    .and(scl.neq(11));        // not snow or ice

  // (b) Spectral indices, computed before masking is applied so the
  //     arithmetic runs on the original band values.
  //
  // NDVI = (NIR - Red) / (NIR + Red). On Sentinel-2, (B8 - B4) / (B8 + B4).
  // Healthy leaves reflect strongly in the near infrared and absorb red for
  // photosynthesis, so dense canopy trends towards 1 and open water goes
  // negative.
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');

  // NDWI = (Green - NIR) / (Green + NIR). On Sentinel-2, (B3 - B8) / (B3 + B8).
  // Water absorbs near infrared almost completely, so the index inverts the
  // NDVI logic and lights up open water and flooded ground.
  var ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI');

  // (c) Apply the mask and hand back an enriched image.
  //
  // updateMask() does not set rejected pixels to zero. It marks them as
  // having no data, which is the important difference: a zero would drag the
  // median down, whereas a masked pixel is simply skipped by the reducer.
  return image
    .updateMask(clear)
    .addBands(ndvi)
    .addBands(ndwi);
};

// ---------------------------------------------------------------------------
// STEP 3. Fan the function out across the year
// ---------------------------------------------------------------------------
// map() applies the function to every image in parallel across Google's
// infrastructure. A JavaScript for loop would try to do this on your browser,
// one scene at a time, and would fail on a collection of this size. Chapter 4
// explains why in detail.
var processed = s2.map(maskCloudsAndAddIndices);

// ---------------------------------------------------------------------------
// STEP 4. Collapse the stack into one image
// ---------------------------------------------------------------------------
// A reducer walks down the time axis at every pixel location and returns one
// number per band.
//
// median() is the workhorse. It ignores masked observations, resists the
// remaining thin cloud that slipped past the SCL test, and does not invent
// values the sensor never recorded, which mean() can do at cloud edges.
//
// Alternatives worth knowing:
//   .mosaic()      last clear observation wins. Fast, but seams show.
//   .qualityMosaic('NDVI')  greenest pixel. Good for peak season maps,
//                           biased towards the wettest dates.
//   .percentile([25])  darker composite, useful for suppressing haze.
var annualComposite = processed.median();

// ---------------------------------------------------------------------------
// STEP 5. Visualisation parameters, one set per layer
// ---------------------------------------------------------------------------
// A common trap: after median() the band names are unchanged. They stay 'B4',
// 'NDVI' and so on. Only a grouped reducer such as reduce(ee.Reducer.median())
// appends a suffix like 'B4_median'. If a layer refuses to draw, print the
// band names first and check which of the two you actually built.
var visTrueColour = {
  bands: ['B4', 'B3', 'B2'],
  min: 0,
  max: 3000,
  gamma: 1.4
};

var visNdvi = {
  bands: ['NDVI'],
  min: -0.5,
  max: 1,
  palette: ['#AF963C', '#F6E652', '#0C6316', '#023E0A']  // bare, sparse, green, dense
};

var visNdwi = {
  bands: ['NDWI'],
  min: -0.5,
  max: 0.5,
  palette: ['#E9DEB5', '#FFFFFF', '#8ED2E5', '#0047AB']  // dry, edge, shallow, deep
};

// ---------------------------------------------------------------------------
// STEP 6. Draw the results
// ---------------------------------------------------------------------------
Map.centerObject(aoi, 10);

Map.addLayer(annualComposite, visTrueColour, 'Annual true colour composite');

// The fourth argument is visibility. Passing false registers the layer in the
// Layers control but leaves it unticked, which keeps the map readable while
// still letting you flick between interpretations.
Map.addLayer(annualComposite, visNdwi, 'Annual NDWI', false);
Map.addLayer(annualComposite, visNdvi, 'Annual NDVI', false);

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Comment out .updateMask(clear) and rerun. The median will survive, but
//    look at the river mouths: describe what changed and why.
// 2. Swap median() for qualityMosaic('NDVI'). Where do the two composites
//    disagree most, and which would you defend in a monitoring report?
// 3. Split the year into wet season and dry season composites and difference
//    the NDWI bands. That difference map is the seed of Chapter 19.
