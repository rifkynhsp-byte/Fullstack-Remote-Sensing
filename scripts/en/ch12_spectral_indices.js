//| title: Building a spectral index library
//| description: NDVI, EVI, SAVI, NDWI, MNDWI, CMRI and MVI, with the traps that break each.

/**
 * CHAPTER 12 | Band math and spectral indices
 * ---------------------------------------------------------------------------
 * Goal
 *   Build every index this book uses, from first principles, and understand
 *   where each one stops working. An index you cannot explain is an index you
 *   cannot debug.
 *
 * Asset dependencies
 *   var aoi = ...
 *   var composite = ...   cloud free composite in physical reflectance, 0 to 1
 *                         from Chapter 9
 */

var aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60]);

var composite = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterDate('2023-01-01', '2023-12-31')
  .filterBounds(aoi)
  .map(function (image) {
    var scl = image.select('SCL');
    var clear = scl.neq(3).and(scl.neq(8)).and(scl.neq(9)).and(scl.neq(10));
    // Scale to physical reflectance ONCE, here. Every formula below assumes
    // 0 to 1. Mixing scaled and unscaled bands is the single most common way
    // to get an index that is silently wrong.
    return image.updateMask(clear).divide(10000).select('B.*');
  })
  .median()
  .clip(aoi);

// ===========================================================================
// PART 1. The normalised difference form
// ===========================================================================
// Nearly every index in remote sensing is a variation on one expression:
//
//     (A - B) / (A + B)
//
// Two properties make it the workhorse.
//
// It is BOUNDED between -1 and 1 regardless of input magnitude, so values are
// comparable between images, sensors and dates.
//
// And it CANCELS multiplicative effects. If a hillside is in partial shade,
// every band is scaled down by roughly the same factor. That factor appears
// in both numerator and denominator and divides out. This is why a ratio
// index is far more stable across illumination conditions than any single
// band, and it is the reason the form dominates the field.
//
// What it does NOT cancel is an ADDITIVE effect. Atmospheric path radiance
// adds to every band, unequally, which is why Chapter 8 insisted on surface
// reflectance rather than top of atmosphere.

// ===========================================================================
// PART 2. Vegetation
// ===========================================================================

// NDVI = (NIR - Red) / (NIR + Red)
//
// The physical logic, from Chapter 2: chlorophyll absorbs red for
// photosynthesis, and leaf mesophyll scatters near infrared. Dense healthy
// canopy therefore has a large gap between the two. Water goes negative
// because it absorbs NIR almost completely.
//
// Where it fails: SATURATION. Once leaf area index exceeds roughly 3, adding
// more leaves does not increase NIR reflectance much, so NDVI flattens near
// 0.8 to 0.9 and stops responding. Tropical forest lives permanently in that
// saturated zone, which means NDVI can tell forest from not forest and is
// nearly useless for distinguishing degraded forest from intact forest.
var ndvi = composite.normalizedDifference(['B8', 'B4']).rename('NDVI');

// EVI keeps responding where NDVI has saturated.
//
// Three additions do the work. The blue term (-7.5 * BLUE) corrects for
// residual atmospheric scattering, which affects blue most. The soil
// adjustment (+1 in the denominator) reduces background influence. The gain
// (2.5) rescales the result to a comparable range.
//
// The coefficients are the standard MODIS values. They are empirical, not
// derived, and they are what everyone uses, so keep them unless you have a
// specific reason and a citation.
var evi = composite.expression(
  '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))', {
    'NIR': composite.select('B8'),
    'RED': composite.select('B4'),
    'BLUE': composite.select('B2')
  }).rename('EVI');

// SAVI: soil adjusted vegetation index.
//
// L is a soil brightness correction. L = 0.5 suits intermediate cover and is
// the usual default. L = 1 suits very sparse cover, L = 0.25 dense. At L = 0
// SAVI reduces exactly to NDVI, which is a useful check that you understand
// what the parameter does.
//
// It matters on the landward fringe and over young replanted stands, where
// bright mud between crowns inflates NDVI.
var L = 0.5;
var savi = composite.expression(
  '((NIR - RED) / (NIR + RED + L)) * (1 + L)', {
    'NIR': composite.select('B8'),
    'RED': composite.select('B4'),
    'L': L
  }).rename('SAVI');

// ===========================================================================
// PART 3. Water
// ===========================================================================

// NDWI = (Green - NIR) / (Green + NIR), McFeeters 1996.
//
// Inverts the NDVI logic. Water reflects modestly in green and absorbs NIR,
// so open water goes strongly positive.
//
// Where it fails: built surfaces. Concrete and metal roofing also have low
// NIR relative to green, so NDWI misclassifies urban areas as water with
// depressing regularity.
var ndwi = composite.normalizedDifference(['B3', 'B8']).rename('NDWI');

// MNDWI = (Green - SWIR) / (Green + SWIR), Xu 2006.
//
// Swaps near infrared for shortwave infrared. Water absorbs shortwave even
// more completely than near infrared, while built surfaces reflect it, so the
// urban confusion largely disappears.
//
// Over a delta full of aquaculture ponds, roads and settlements, MNDWI is the
// better default and NDWI is the historical one. Prefer MNDWI unless you need
// continuity with older work.
var mndwi = composite.normalizedDifference(['B3', 'B11']).rename('MNDWI');

// ===========================================================================
// PART 4. Mangrove specific
// ===========================================================================
// Generic indices separate vegetation from water. Mangrove mapping needs to
// separate vegetation that is STANDING IN water from vegetation that is not,
// which is a different question and needs a different construction.

// CMRI, Combined Mangrove Recognition Index = NDVI - NDWI.
//
// The logic is direct: mangrove is the only cover type that is simultaneously
// high in vegetation signal and adjacent to, or over, water. Subtracting NDWI
// from NDVI pushes terrestrial forest up (high NDVI, very negative NDWI) and
// open water down, leaving mangrove in a distinguishable middle band.
var cmri = ndvi.subtract(ndwi).rename('CMRI');

// MVI, Mangrove Vegetation Index = (NIR - Green) / (SWIR1 - Green).
//
// Baloloy et al. 2020. Unlike the indices above this is not a normalised
// difference, so it is unbounded and can produce extreme values wherever the
// denominator approaches zero. Guard against that.
//
// The construction exploits mangrove greenness in NIR against the moisture
// signal in SWIR, and it separates mangrove from terrestrial vegetation more
// cleanly than NDVI alone in published comparisons.
var green = composite.select('B3');
var nir = composite.select('B8');
var swir = composite.select('B11');

var denominator = swir.subtract(green);
var mvi = nir.subtract(green)
  .divide(denominator.where(denominator.abs().lt(0.001), 0.001))
  .rename('MVI');

// ===========================================================================
// PART 5. Two traps
// ===========================================================================

// TRAP 1: normalizedDifference renames the output to 'nd'.
//
// Always .rename(). Two indices computed without renaming produce two bands
// both called 'nd', and addBands silently keeps only one. The error surfaces
// far away, as a classifier that mysteriously ignores a predictor.

// TRAP 2: integer division truncates.
//
// If you compute an index on unscaled integer reflectance without casting,
// the division rounds towards zero and you get an image of zeros and ones.
// It renders as a plausible looking binary mask, which is why it survives
// review. Dividing by 10000 in the masking function, as above, avoids it
// entirely by making everything float.
//
// Verify with the Inspector rather than by eye: click a forest pixel and
// confirm NDVI reads something like 0.83, not 0 or 1.

var indices = composite
  .addBands([ndvi, evi, savi, ndwi, mndwi, cmri, mvi]);

print('Bands after adding indices:', indices.bandNames());

// ===========================================================================
// DISPLAY
// ===========================================================================
Map.centerObject(aoi, 11);
Map.addLayer(composite, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.3}, 'True colour');
Map.addLayer(ndvi, {min: -0.2, max: 0.9,
  palette: ['#AF963C', '#F6E652', '#0C6316', '#023E0A']}, 'NDVI', false);
Map.addLayer(mndwi, {min: -0.5, max: 0.5,
  palette: ['#E9DEB5', '#FFFFFF', '#8ED2E5', '#0047AB']}, 'MNDWI', false);
Map.addLayer(cmri, {min: -0.5, max: 1.5,
  palette: ['#0047AB', '#FFFFFF', '#14a37f', '#075e11']}, 'CMRI', false);

// A histogram tells you more than a map about whether an index separates your
// classes. Two peaks with a valley between them is separability; one broad
// hump is not.
print(ui.Chart.image.histogram({
  image: cmri,
  region: aoi,
  scale: 100,
  maxPixels: 1e9
}).setOptions({title: 'CMRI distribution, look for two peaks'}));

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Set L = 0 in SAVI and difference the result against NDVI. Confirm it is
//    zero everywhere, then explain in one sentence why.
// 2. Map NDWI and MNDWI over an urban area and find where they disagree.
// 3. Compute NDVI on the unscaled integer composite without dividing by
//    10000. Look at the result and note how plausible a wrong answer looks.
// 4. Chart CMRI and NDVI histograms over the same area. Which one shows two
//    peaks, and what does that tell you about which to give the classifier?
