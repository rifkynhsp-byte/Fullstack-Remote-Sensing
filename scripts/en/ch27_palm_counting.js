//| title: Counting oil palms without deep learning
//| description: The author's Earth Engine method: blur a greenness index, keep local maxima, count one point per crown.

/**
 * CHAPTER 27 | One point per crown, in the Code Editor
 * ---------------------------------------------------------------------------
 * The same recipe as the Python tab, as the author runs it in Earth Engine
 * (sawitML and GEE101 PalmOil_Detection). Earth Engine has no public drone
 * imagery of Indonesian plantations, so first bring your own:
 *   1. Download the orthophoto from OpenAerialMap (CC BY 4.0), or use your
 *      own drone or Pleiades image.
 *   2. Assets > New > Image upload (GeoTIFF). Name it as below.
 * At 0.3 m a mature palm crown is about 25 pixels across.
 */

var ortho = ee.Image('users/your_name/kebun_sawit_bangkal_baru');   // <- your asset
var area = ortho.geometry();

// 1. Excess green: (2G - R - B) / (R + G + B). Bands b1, b2, b3 = R, G, B.
var rgb = ortho.select(['b1', 'b2', 'b3']).toFloat();
var exg = rgb.expression('(2 * G - R - B) / (R + G + B)',
  {R: rgb.select('b1'), G: rgb.select('b2'), B: rgb.select('b3')}).rename('exg');

// 2. Blur about a third of a crown radius, so each crown has one summit.
var smooth = exg.convolve(ee.Kernel.gaussian({radius: 3, sigma: 3, units: 'pixels'}));

// 3. A pixel is a crown centre if it is the highest within 5.5 m.
var localMax = smooth.focal_max({radius: 5.5, units: 'meters'});
var crowns = smooth.eq(localMax).and(smooth.gt(0.04)).selfMask();

// 4. One point per crown, then count.
var points = crowns.reduceToVectors({geometry: area, scale: 0.3, geometryType: 'centroid',
                                     maxPixels: 1e10});
print('Palms counted:', points.size());

Map.centerObject(area, 17);
Map.addLayer(ortho, {bands: ['b1', 'b2', 'b3'], min: 0, max: 255}, 'Orthophoto');
Map.addLayer(points, {color: 'ff2d55'}, 'Crowns');

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Set the focal_max radius to 3 m and to 8 m. Where do double counts and
//    missed palms appear?
// 2. Draw the plantation boundary and count inside it only. How many of the
//    points outside were ordinary trees?
