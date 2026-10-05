//| title: Library: WorldCover labels for the book's five classes
//| description: worldcoverClasses(aoi) and labelledPoints(aoi): stand-in labels for chapters 15 to 19 until you have field data.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * LIBRARY | book_labels
 * ESA WorldCover 2021 (10 m) has a mangrove class, so it can stand in for
 * training polygons over the Mahakam Delta. It is a map, not ground truth:
 * any accuracy computed against these labels measures agreement with
 * WorldCover, not correctness. Chapter "Ground Truth and Sampling Design"
 * explains why that matters.
 *   0 mangrove (WorldCover 95)         1 other forest (10)     2 water (80)
 *   3 bare or agriculture (20, 30, 40, 60)                     4 urban (50)
 *
 *   var labels = require('users/rifkynauvalhsp/Fullstack-Remote-Sensing:book_labels');
 *   var points = labels.labelledPoints(aoi);
 */
exports.CLASS_PROPERTY = 'landcover';
exports.CLASS_NAMES = ['mangrove', 'other forest', 'water', 'bare or agriculture', 'urban'];
exports.PALETTE = ['075e11', '358221', '1A5BAB', 'FFDB5C', 'ED022A'];

exports.worldcoverClasses = function (aoi) {
  return ee.ImageCollection('ESA/WorldCover/v200').first().select('Map')
    .remap([95, 10, 80, 20, 30, 40, 60, 50], [0, 1, 2, 3, 3, 3, 3, 4])
    .rename('landcover').toInt().clip(aoi);
};

exports.labelledPoints = function (aoi, perClass, seed) {
  return exports.worldcoverClasses(aoi).stratifiedSample({
    numPoints: 0, classBand: 'landcover', region: aoi, scale: 10, seed: seed || 42,
    classValues: [0, 1, 2, 3, 4], classPoints: perClass || [300, 250, 150, 200, 150],
    geometries: true, tileScale: 4});
};
