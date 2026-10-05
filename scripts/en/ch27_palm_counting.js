//| title: Counting oil palms without deep learning
//| description: The author's Earth Engine method: blur a greenness index, keep local maxima, count one point per crown.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 27 | One point per crown, in the Code Editor
 * ---------------------------------------------------------------------------
 * The same recipe as the Python tab, as the author runs it in Earth Engine
 * (sawitML and GEE101 PalmOil_Detection). The drone orthophoto (OpenAerialMap,
 * CC BY 4.0) is published with this book as a public Earth Engine asset at
 * 0.3 m, so it runs as it is. To use your own drone or Pleiades image instead,
 * upload it (Assets > New > Image upload) and change the asset id below.
 * At 0.3 m a mature palm crown is about 25 pixels across.
 */

var ortho = ee.Image('projects/shaped-producer-482312-m0/assets/fullstack_rs/drone_oilpalm_banjarbaru_30cm');
var area = ortho.geometry();

// 1. Excess green: (2G - R - B) / (R + G + B).
var rgb = ortho.select(['R', 'G', 'B']).toFloat();
var exg = rgb.expression('(2 * G - R - B) / (R + G + B)',
  {R: rgb.select('R'), G: rgb.select('G'), B: rgb.select('B')}).rename('exg');

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
Map.addLayer(ortho, {bands: ['R', 'G', 'B'], min: 0, max: 255}, 'Orthophoto');
Map.addLayer(points, {color: 'ff2d55'}, 'Crowns');

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Set the focal_max radius to 3 m and to 8 m. Where do double counts and
//    missed palms appear?
// 2. Draw the plantation boundary and count inside it only. How many of the
//    points outside were ordinary trees?
