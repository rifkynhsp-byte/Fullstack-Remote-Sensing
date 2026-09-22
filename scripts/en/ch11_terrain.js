//| title: Terrain as an ecological constraint
//| description: Elevation, slope, aspect and the intertidal envelope that fixes mangrove maps.

/**
 * CHAPTER 11 | Terrain and hydrological context
 * ---------------------------------------------------------------------------
 * Goal
 *   Derive elevation, slope, aspect and a coastal distance surface, then use
 *   them to encode an ecological rule a classifier can learn: mangroves live
 *   in a narrow band above sea level, and forest twenty metres up a hillside
 *   is not mangrove no matter what it looks like.
 *
 * Why this is the cheapest accuracy gain in the book
 *   The confusion that caps mangrove mapping accuracy is with other dense
 *   broadleaf forest. Spectrally they are nearly identical. Positionally they
 *   are not, and elevation is free, global and already in the catalogue.
 */

var aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60]);   // Mahakam Delta

// ---------------------------------------------------------------------------
// STEP 1. Choose a DEM, knowing what you are choosing
// ---------------------------------------------------------------------------
// Three global options, and the difference matters more than it looks.
//
//   CGIAR/SRTM90_V4        90 m, acquired 2000. The old default. Still fine
//                          where terrain has not changed and detail is not
//                          critical.
//   USGS/SRTMGL1_003       30 m, same 2000 acquisition, resampled product.
//   JAXA/ALOS/AW3D30/V2_2  30 m, better vertical accuracy across most of
//                          Asia. This book's default.
//   COPERNICUS/DEM/GLO30   30 m, most recent, excellent quality, though
//                          coverage gaps exist in some regions.
//
// All four are SURFACE models, not terrain models. Read the next comment
// before using any of them over forest.
var dem = ee.Image('JAXA/ALOS/AW3D30/V2_2').select('AVE_DSM').clip(aoi);

// ---------------------------------------------------------------------------
// The surface model trap
// ---------------------------------------------------------------------------
// A digital SURFACE model records the top of whatever is there: canopy,
// rooftops, the sea surface. A digital TERRAIN model records the ground.
//
// Every global 30 m product listed above is a surface model. Over a 25 m tall
// mangrove stand, it reports roughly 25 m, not 1 m. So the naive rule
// "mangrove sits below 10 m elevation" excludes the tallest and most carbon
// rich stands, which are exactly the ones a carbon project cares about.
//
// Three ways to handle it, in order of preference.
//
//   1. Do not threshold. Hand elevation to the classifier as a predictor and
//      let it learn the relationship, including the canopy offset. This is
//      what Chapter 10's feature stack does and it is usually right.
//   2. Threshold generously. If you must apply a rule, use 40 m rather than
//      10 m, and understand you are excluding hillside forest rather than
//      isolating the tidal zone precisely.
//   3. Subtract a canopy height product. ETH Global Canopy Height gives a
//      10 m estimate that can be differenced from the surface model. This is
//      the most correct and the most fragile, because two error budgets
//      combine.
var canopyHeight = ee.Image('users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1')
  .clip(aoi)
  .rename('canopy_height');

var approxGround = dem.subtract(canopyHeight.unmask(0)).rename('ground_est');

// ---------------------------------------------------------------------------
// STEP 2. Derived terrain surfaces
// ---------------------------------------------------------------------------
// ee.Terrain.products returns elevation, slope, aspect and hillshade in one
// call. Slope is in degrees, aspect in degrees clockwise from north.
var terrain = ee.Terrain.products(dem);

var slope = terrain.select('slope');
var aspect = terrain.select('aspect');
var hillshade = terrain.select('hillshade');

// Slope is a stronger mangrove discriminator than most people expect, and for
// a reason that has nothing to do with the trees. Tidal flats are flat, by
// definition: they are depositional surfaces. Terrestrial forest sits on
// slopes. Even a poor surface model preserves that distinction, because the
// canopy offset is roughly constant across a stand and differencing removes
// a constant.
var isFlat = slope.lt(3).rename('is_flat');

// ---------------------------------------------------------------------------
// STEP 3. Distance to the coast
// ---------------------------------------------------------------------------
// Elevation says how high. Distance to open water says how connected, and
// mangroves are defined by tidal connection rather than by altitude alone. A
// flat, low patch fifty kilometres inland is a swamp, not a mangrove.
//
// Build the water mask from the composite rather than from a static product,
// so the surface reflects the year being mapped.
var water = ee.Image('JRC/GSW1_4/GlobalSurfaceWater')
  .select('occurrence')
  .gt(80)                 // present in at least 80 percent of observations
  .selfMask();

// fastDistanceTransform works in pixel units, so multiply by the scale to get
// metres. neighborhood caps the search radius; raise it for wide coastal
// plains and lower it to save computation.
var distanceToWater = water.fastDistanceTransform({
  neighborhood: 512,
  units: 'pixels'
}).sqrt().multiply(30).rename('dist_to_water').clip(aoi);

// ---------------------------------------------------------------------------
// STEP 4. The intertidal envelope
// ---------------------------------------------------------------------------
// Combine the three conditions into one mask. This is not a classification.
// It is a constraint surface: a statement about where mangrove CAN be, which
// the classifier then uses to decide where it IS.
//
// Applying it as a hard mask after classification is the crude version and it
// works. Adding these bands to the feature stack is better, because the model
// can weigh them against the spectral evidence rather than being overruled by
// a threshold you chose.
var intertidalEnvelope = dem.lt(40)
  .and(slope.lt(5))
  .and(distanceToWater.lt(5000))
  .rename('intertidal')
  .clip(aoi);

// ---------------------------------------------------------------------------
// STEP 5. Assemble the terrain contribution to the feature stack
// ---------------------------------------------------------------------------
var terrainStack = dem.rename('elevation')
  .addBands(slope)
  .addBands(aspect)
  .addBands(distanceToWater)
  .addBands(intertidalEnvelope)
  .float();

print('Terrain bands:', terrainStack.bandNames());

// Summary statistics are worth printing once. If the reported minimum
// elevation over a coastal AOI is 40 m, your area of interest does not
// actually reach the coast, and every conclusion below it is wrong.
print('Elevation statistics:', dem.reduceRegion({
  reducer: ee.Reducer.minMax().combine(ee.Reducer.mean(), '', true),
  geometry: aoi,
  scale: 30,
  maxPixels: 1e10,
  bestEffort: true
}));

// ---------------------------------------------------------------------------
// DISPLAY
// ---------------------------------------------------------------------------
Map.centerObject(aoi, 10);
Map.addLayer(hillshade, {min: 0, max: 255}, 'Hillshade', false);
Map.addLayer(dem, {min: 0, max: 100,
  palette: ['#2b83ba', '#abdda4', '#ffffbf', '#fdae61', '#d7191c']}, 'Elevation');
Map.addLayer(slope, {min: 0, max: 30, palette: ['#ffffff', '#000000']}, 'Slope', false);
Map.addLayer(distanceToWater, {min: 0, max: 10000,
  palette: ['#0047AB', '#8ED2E5', '#FFFFFF']}, 'Distance to water', false);
Map.addLayer(intertidalEnvelope.selfMask(), {palette: ['#14a37f']},
  'Intertidal envelope', false);

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Use the Inspector on a stand of tall mangrove. Compare the reported
//    elevation to what you know the ground height to be. That gap is the
//    canopy offset, and it is why the naive threshold fails.
// 2. Tighten the envelope to dem.lt(10) and map what it excludes. Are the
//    excluded areas really not mangrove?
// 3. Replace the elevation term with approxGround and compare. Does canopy
//    subtraction help, or has it added more noise than it removed?
// 4. Raise the distance to water limit to 20 km. What non mangrove wetland
//    does the envelope now wrongly admit?
