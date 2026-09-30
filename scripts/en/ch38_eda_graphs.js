//| title: Exploratory data analysis and graphs that explain themselves
//| description: The Code Editor side of exploration: a summary of the rainfall table, its distribution, and charts with a stated title, units and a fixed scale.

/**
 * CHAPTER 38 | Explore in the Code Editor, polish in Python
 * ---------------------------------------------------------------------------
 * The Code Editor is quick for a first look: print the summary, draw the
 * distribution, chart one series. The paired bad/good figures in the Python
 * tab are where the rules of this chapter are shown side by side.
 */

var PLACES = {Padang: [100.36, -0.95], Pontianak: [109.34, -0.03],
              Jakarta: [106.83, -6.20], Makassar: [119.44, -5.14],
              Kupang: [123.61, -10.17], Ambon: [128.18, -3.70]};
var pentads = ee.ImageCollection('UCSB-CHG/CHIRPS/PENTAD').select('precipitation');

// Annual rainfall per city and year: the table every rule below draws from.
var rows = [];
Object.keys(PLACES).forEach(function (name) {
  var region = ee.Geometry.Point(PLACES[name]).buffer(10000);
  ee.List.sequence(1991, 2024).getInfo().forEach(function (y) {
    rows.push(ee.Feature(null, {place: name, year: y,
      rain_mm: pentads.filterDate(ee.Date.fromYMD(y, 1, 1), ee.Date.fromYMD(y + 1, 1, 1))
        .sum().reduceRegion(ee.Reducer.mean(), region, 5000).get('precipitation')}));
  });
});
var annual = ee.FeatureCollection(rows);

// Step 1: what is in the table? Count, spread and range, per city.
print('Kupang annual rainfall (mm): summary',
  annual.filter(ee.Filter.eq('place', 'Kupang')).aggregate_stats('rain_mm'));

// Rule 1: the distribution, not just the mean. A histogram of every city-year.
print(ui.Chart.feature.histogram({features: annual, property: 'rain_mm', maxBuckets: 20})
  .setOptions({title: 'Annual rainfall, six cities, 1991-2024 (mm per year)',
               hAxis: {title: 'mm per year'}, vAxis: {title: 'city-years'},
               legend: {position: 'none'}}));

// Rule 5: a chart that explains itself. The title states the finding; the axis
// has units; the scale starts at zero so a bar's length means something.
print(ui.Chart.feature.byFeature(annual.filter(ee.Filter.eq('place', 'Kupang')),
    'year', ['rain_mm'])
  .setChartType('ColumnChart')
  .setOptions({title: 'Kupang: the wettest year (2021) had 2.3 times the rain of the driest (1992)',
               hAxis: {title: 'Year', format: '####'},
               vAxis: {title: 'Rainfall (mm per year)', viewWindow: {min: 0}},
               legend: {position: 'none'}, colors: ['#2a78d6']}));
