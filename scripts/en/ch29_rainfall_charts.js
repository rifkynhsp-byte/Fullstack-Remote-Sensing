//| title: One rainfall table, charted badly and well
//| description: CHIRPS monthly rainfall 1991-2024 for six Indonesian cities, charted in the Code Editor.

/**
 * CHAPTER 29 | The table is the same; the chart is a choice
 * ---------------------------------------------------------------------------
 * Earth Engine builds one tidy table: monthly CHIRPS rainfall for six cities
 * in different rainfall regimes. The Code Editor can chart it directly. Its
 * charts are quick and interactive, but small multiples, range bands and
 * annotated dot plots are easier in Python (the other tab).
 */

var PLACES = {Padang: [100.36, -0.95], Pontianak: [109.34, -0.03],
              Jakarta: [106.83, -6.20], Makassar: [119.44, -5.14],
              Kupang: [123.61, -10.17], Ambon: [128.18, -3.70]};
var cities = ee.FeatureCollection(Object.keys(PLACES).map(function (name) {
  return ee.Feature(ee.Geometry.Point(PLACES[name]).buffer(10000), {place: name});
}));

var pentads = ee.ImageCollection('UCSB-CHG/CHIRPS/PENTAD').select('precipitation');

// Mean rainfall for each calendar month, 1991-2020, as one 12-band image.
var climatology = ee.ImageCollection(ee.List.sequence(1, 12).map(function (m) {
  return pentads.filterDate('1991-01-01', '2021-01-01')
    .filter(ee.Filter.calendarRange(m, m, 'month')).sum().divide(30)
    .rename('rain').set('month', m);
}));

// 1. The first draft: every city on one axis. Quick, and hard to read.
print(ui.Chart.image.seriesByRegion({
  imageCollection: climatology, regions: cities, reducer: ee.Reducer.mean(),
  band: 'rain', scale: 5000, xProperty: 'month', seriesProperty: 'place'
}).setOptions({title: 'Monthly rainfall, 1991-2020 mean (mm)', lineWidth: 2,
               pointSize: 3, hAxis: {title: 'Month'}}));

// 2. One chart per city on the same axis: the Code Editor's small multiples.
Object.keys(PLACES).forEach(function (name) {
  print(ui.Chart.image.series({
    imageCollection: climatology, region: cities.filter(ee.Filter.eq('place', name)),
    reducer: ee.Reducer.mean(), scale: 5000, xProperty: 'month'
  }).setOptions({title: name, legend: {position: 'none'}, colors: ['#2a78d6'],
                 vAxis: {viewWindow: {min: 0, max: 750}}, height: 180}));
});

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Remove the fixed vAxis range from the small charts. Which city now looks
//    wetter than it is?
// 2. Chart annual totals per year for Kupang. Which years stand out?
