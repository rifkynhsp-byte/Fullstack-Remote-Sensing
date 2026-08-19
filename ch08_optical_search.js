//| title: Searching the Sentinel-2 archive
//| description: Filter millions of scenes down to the one clear image over a mangrove delta.

/**
 * CHAPTER 8 | Searching the optical archive
 * ---------------------------------------------------------------------------
 * Goal
 *   Reduce the global Sentinel-2 surface reflectance archive to a single,
 *   clear scene over the Mahakam Delta, East Kalimantan, and display it in
 *   true colour.
 *
 * The pattern to memorise
 *   collection -> filterDate -> filterBounds -> filter on metadata -> sort ->
 *   first(). Every optical workflow in this book starts with some version of
 *   that chain. Order matters for readability, not for speed: Earth Engine
 *   optimises the query plan on the server regardless of the order you write.
 */

// ---------------------------------------------------------------------------
// STEP 1. Define where to look
// ---------------------------------------------------------------------------
// A point is the cheapest possible area of interest. It is enough to answer
// "which scenes cover this spot", which is all filterBounds needs.
// Coordinates are always [longitude, latitude].
var aoi = ee.Geometry.Point([117.58, -0.84]);   // Mahakam Delta, Indonesia

// ---------------------------------------------------------------------------
// STEP 2. Name the collection
// ---------------------------------------------------------------------------
// COPERNICUS/S2_SR_HARMONIZED is the Level-2A product: surface reflectance,
// meaning the atmosphere has already been corrected out. Prefer it over the
// Level-1C top of atmosphere product for anything quantitative, because
// indices computed on uncorrected radiance are not comparable across dates.
//
// "HARMONIZED" matters. In January 2022 ESA shifted the reflectance offset of
// the raw product. The harmonised collection rewrites older scenes onto the
// new scale, so a time series that crosses that date stays continuous.
var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED');

// ---------------------------------------------------------------------------
// STEP 3. Narrow the archive
// ---------------------------------------------------------------------------
// Each filter is lazy. Nothing is fetched until something forces evaluation,
// so chaining ten filters costs no more than chaining one.
var filtered = s2
  // Keep acquisitions inside a calendar window. End date is exclusive.
  .filterDate('2023-01-01', '2023-12-01')

  // Keep only scenes whose footprint intersects the area of interest.
  .filterBounds(aoi)

  // Keep only scenes whose scene level cloud estimate is under 15 percent.
  // This is a metadata filter, not a pixel filter: it throws away whole
  // scenes. Chapter 6 replaces it with per pixel masking, which is what you
  // want for compositing. Scene level filtering is still useful here, where
  // the aim is to look at one good image.
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 15));

// Always check how much survived before going further. An empty collection
// produces confusing downstream errors rather than an obvious one.
print('Scenes after filtering:', filtered.size());
print('Acquisition dates:', filtered.aggregate_array('system:time_start')
  .map(function (millis) { return ee.Date(millis).format('YYYY-MM-dd'); }));

// ---------------------------------------------------------------------------
// STEP 4. Choose one scene
// ---------------------------------------------------------------------------
// sort() puts the least cloudy scene first, ascending by default.
// first() takes it. The result is an ee.Image rather than a collection, so
// image level methods become available from here on.
var image = filtered.sort('CLOUDY_PIXEL_PERCENTAGE').first();

print('Selected scene ID:', image.get('system:index'));
print('Cloud percentage:', image.get('CLOUDY_PIXEL_PERCENTAGE'));

// ---------------------------------------------------------------------------
// STEP 5. Describe how to draw it
// ---------------------------------------------------------------------------
// A visualisation dictionary answers three questions: which bands feed the
// red, green and blue channels; what numeric range maps onto 0 to 255; and
// how much to brighten the midtones.
var trueColour = {
  // Sentinel-2 red, green and blue. Mapping them onto the screen's own red,
  // green and blue channels gives the scene the colours a passenger in an
  // aircraft would see.
  bands: ['B4', 'B3', 'B2'],

  // Level-2A reflectance is stored scaled by 10000, so 3000 here means a
  // reflectance of 0.30. Bright coastal water and wet mangrove mud both sit
  // low in this range, which is why 0 to 3000 works better over a delta than
  // the 0 to 5000 stretch often used over farmland.
  min: 0,
  max: 3000,

  // Gamma above 1 lifts the dark end without blowing out the highlights.
  // Useful over tropical coasts where the interesting material is dark.
  gamma: 1.4
};

// ---------------------------------------------------------------------------
// STEP 6. Draw it
// ---------------------------------------------------------------------------
Map.centerObject(aoi, 10);
Map.addLayer(image, trueColour, 'Sentinel-2 true colour, Mahakam');

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Raise the cloud threshold from 15 to 60 and rerun. How many more scenes
//    survive, and is the top ranked scene still usable?
// 2. Swap .first() for .sort('CLOUDY_PIXEL_PERCENTAGE', false).first() to
//    select the worst scene instead. Keep it on the map as a reminder of what
//    the cloud masking in Chapter 6 has to remove.
// 3. Replace the point with your own study area and adjust min and max until
//    the darkest land surface is still readable.
