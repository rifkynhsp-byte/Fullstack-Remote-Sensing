//| title: Texture features with GLCM
//| description: Separate a uniform plantation from a complex natural stand that reflects identically.

/**
 * CHAPTER 14 | Spatial texture extraction
 * ---------------------------------------------------------------------------
 * Goal
 *   Add pattern to spectrum. Compute grey level co-occurrence matrix features
 *   so a classifier can tell a planted monoculture from a structurally
 *   complex natural forest when the two are spectrally indistinguishable.
 *
 * The problem in one sentence
 *   An oil palm plantation and a natural mangrove stand can have identical
 *   mean reflectance in every band, because both are dense broadleaf canopy.
 *   What differs is the ARRANGEMENT: palm is planted on a regular grid with
 *   uniform crown size, mangrove is not. Texture measures arrangement.
 */

var aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60]);

var composite = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterDate('2023-01-01', '2023-12-31')
  .filterBounds(aoi)
  .map(function (i) {
    var scl = i.select('SCL');
    return i.updateMask(scl.neq(3).and(scl.neq(8)).and(scl.neq(9)).and(scl.neq(10)))
            .divide(10000).select('B.*');
  })
  .median()
  .clip(aoi);

// ===========================================================================
// PART 1. Preparing the input, which is where most attempts fail
// ===========================================================================
// glcmTexture has two hard requirements and neither is enforced with a useful
// error message.
//
// REQUIREMENT 1: integer input. Pass a float band and you get nonsense, not an
// exception. The reflectance values above are floats between 0 and 1, so they
// must be rescaled and cast.
//
// REQUIREMENT 2: a sensible number of grey levels. GLCM builds a matrix of
// size N by N where N is the number of distinct values. Cast 0 to 1 float
// reflectance straight to int16 and you get two levels, which carries no
// information. Multiply by 10000 first and you get thousands of levels, a
// matrix with millions of cells, and a computation that will exhaust memory.
//
// Quantising to 0 to 255 is the standard compromise: enough levels to capture
// structure, small enough to compute. This is not arbitrary, it is what the
// original Haralick formulation assumed.
var QUANT_LEVELS = 255;

var nir = composite.select('B8')
  .unitScale(0, 0.5)          // reflectance above 0.5 is rare over vegetation
  .clamp(0, 1)
  .multiply(QUANT_LEVELS)
  .toByte()                   // 8 bit integer, 256 grey levels
  .rename('B8_quantised');

// ===========================================================================
// PART 2. Which band to run it on
// ===========================================================================
// Run GLCM on ONE band, not the whole stack. Two reasons.
//
// glcmTexture returns EIGHTEEN bands per input band. Ten input bands produce
// 180 texture bands, which will exhaust memory and add mostly redundant
// information, because texture in adjacent spectral bands is highly
// correlated.
//
// And the choice of band is not arbitrary. Near infrared has the greatest
// contrast between sunlit crown and shadowed gap, so canopy structure is most
// visible there. Over urban work, a visible band is often better because
// shadow between buildings is what carries the structure.
//
// Alternatively run it on a principal component or on NDVI, both of which
// concentrate the structural signal.

// ===========================================================================
// PART 3. Window size is an ecological decision
// ===========================================================================
// The `size` parameter is a radius in pixels, so the analysis window is
// (2 * size + 1) square. At Sentinel-2's 10 m:
//
//   size 1  ->  3x3 window,   30 m.  Smaller than one large tree crown.
//                             Measures noise more than structure.
//   size 3  ->  7x7 window,   70 m.  Spans several crowns. Good default for
//                             distinguishing canopy types.
//   size 7  -> 15x15 window, 150 m.  Spans a stand. Good for distinguishing
//                             land cover types, blurs boundaries between them.
//
// The rule: the window must be large enough to contain several instances of
// the pattern you want to detect, and small enough not to straddle a boundary
// between two cover types. Match it to crown diameter, not to a default.
var WINDOW = 3;

var glcm = nir.glcmTexture({size: WINDOW});

print('GLCM output bands:', glcm.bandNames());

// ===========================================================================
// PART 4. Which of the eighteen to keep
// ===========================================================================
// The full set is highly redundant; several measures are near duplicates of
// each other. Four carry most of the independent information, and each
// answers a different question.
//
//   contrast  How different are neighbouring pixels? High over a broken,
//             heterogeneous canopy with gaps. Low over a smooth uniform one.
//
//   ent       Entropy. How disordered is the local arrangement? A planted
//             grid is ordered and scores low; natural regeneration is
//             disordered and scores high. This is usually the single most
//             discriminating texture band for plantation versus natural.
//
//   asm       Angular second moment, sometimes called energy. The inverse of
//             entropy: high means uniform. Included because classifiers
//             sometimes split more cleanly on it.
//
//   corr      Correlation. How linearly predictable is a pixel from its
//             neighbour? High along the rows of a plantation, because the
//             planting geometry is genuinely periodic.
var texture = glcm.select(
  ['B8_quantised_contrast', 'B8_quantised_ent',
   'B8_quantised_asm', 'B8_quantised_corr'],
  ['tex_contrast', 'tex_entropy', 'tex_asm', 'tex_correlation']
);

// ===========================================================================
// PART 5. Does it actually separate anything?
// ===========================================================================
// Do not add texture bands on faith. Test whether they separate the classes
// you are confusing, using the training data from Chapter 15.
//
// Uncomment once trainingPoints exists. If the two classes overlap completely
// on entropy, the texture bands are costing computation and contributing
// nothing, and should be dropped.
//
// var separability = texture.sampleRegions({
//   collection: trainingPoints,
//   properties: ['landcover'],
//   scale: 10,
//   tileScale: 4
// });
//
// print(ui.Chart.feature.groups({
//   features: separability,
//   xProperty: 'tex_entropy',
//   yProperty: 'tex_contrast',
//   seriesProperty: 'landcover'
// }).setChartType('ScatterChart').setOptions({
//   title: 'Do texture features separate the classes that confuse?',
//   hAxis: {title: 'Entropy'},
//   vAxis: {title: 'Contrast'}
// }));

// ===========================================================================
// DISPLAY
// ===========================================================================
Map.centerObject(aoi, 12);
Map.addLayer(composite, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.3}, 'True colour');
Map.addLayer(texture, {bands: ['tex_entropy'], min: 0, max: 4,
  palette: ['#000000', '#14a37f', '#ffffff']}, 'Entropy');
Map.addLayer(texture, {bands: ['tex_contrast'], min: 0, max: 300,
  palette: ['#000000', '#c8792b', '#ffffff']}, 'Contrast', false);

// What to look for: zoom to a boundary between plantation and natural forest.
// In true colour it may be nearly invisible. In entropy it should be obvious.
// If it is not, either the window size is wrong for the crown size, or the
// two stands are more similar than you assumed, which is itself worth knowing.

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Run at WINDOW of 1, 3 and 7 over the same plantation boundary. Find the
//    size at which the boundary becomes clearest, and relate it to crown
//    diameter.
// 2. Skip the .toByte() cast and run on the float band. Inspect the output
//    and describe how the failure presents itself.
// 3. Quantise to 32 levels instead of 255. What is gained and what is lost?
// 4. Run GLCM on NDVI rather than B8. Does the structural signal improve?
