//| title: Three maps, three kinds of colour
//| description: Sequential, diverging and categorical colour on CHIRPS rainfall for Indonesia.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 29 | One dataset, three questions, three colour jobs
 *   How much rain in a year?        sequential: one hue, light to dark
 *   Was 2023 wetter or drier?       diverging: two hues, neutral at zero
 *   Which season is the wettest?    categorical: distinct hues, no order
 */

var indonesia = ee.Geometry.Rectangle([94.8, -11.2, 141.2, 6.2], null, false);
var pentads = ee.ImageCollection('UCSB-CHG/CHIRPS/PENTAD').select('precipitation')
  .filterBounds(indonesia);
var normal = pentads.filterDate('1991-01-01', '2021-01-01');

var annualMean = normal.sum().divide(30).rename('rain');
var anomalyPct = pentads.filterDate('2023-01-01', '2024-01-01').sum()
  .divide(annualMean).subtract(1).multiply(100).rename('anom');

var monthly = ee.ImageCollection(ee.List.sequence(1, 12).map(function (m) {
  return normal.filter(ee.Filter.calendarRange(m, m, 'month')).sum().divide(30).rename('rain');
}));
var wettest = monthly.toArray().arrayProject([0]).arrayArgmax().arrayGet([0]).add(1);
var season = wettest.mod(12).divide(3).floor().rename('season');   // DJF 0 ... SON 3

Map.setCenter(118, -2.5, 5);
Map.addLayer(annualMean, {min: 1000, max: 4500, palette: ['f7fbff', 'c6dbef', '6baed6',
  '2171b5', '08306b']}, 'Sequential: mean annual rainfall (mm)');
Map.addLayer(anomalyPct, {min: -50, max: 50, palette: ['8c510a', 'dfc27d', 'f5f5f5',
  '80cdc1', '01665e']}, 'Diverging: 2023 vs normal (%)', false);
Map.addLayer(season.updateMask(annualMean.mask()), {min: 0, max: 3,
  palette: ['0072B2', 'E69F00', 'D55E00', '009E73']}, 'Categorical: wettest season', false);

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Show the anomaly with the sequential palette. What does a reader now
//    think a pale pixel means?
// 2. Replace the four season colours with a rainbow ramp. Which two seasons
//    become hard to tell apart for a colour-blind reader?
