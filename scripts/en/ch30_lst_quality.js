//| title: Before any statistics: what is missing, and why
//| description: 22 years of daily MODIS land surface temperature over Bandung, checked for missing days and quality flags.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 30 | A data quality check on a satellite time series
 * ---------------------------------------------------------------------------
 * The same order as a weather-station check: count what is missing, find out
 * why, read the quality flags. The Python tab adds outlier rules and the
 * full summary table.
 */

var point = ee.Geometry.Point(107.61, -6.91);   // central Bandung, one 1 km pixel
var lst = ee.ImageCollection('MODIS/061/MOD11A1').filterDate('2003-01-01', '2025-01-01')
  .select(['LST_Day_1km', 'QC_Day']);

// Days with a file, and days with a value. A day with no granule is not
// "missing" in the table; it is simply absent.
var withValue = lst.map(function (img) {
  var v = img.select('LST_Day_1km').reduceRegion(ee.Reducer.first(), point, 1000)
    .get('LST_Day_1km');
  var qc = img.select('QC_Day').reduceRegion(ee.Reducer.first(), point, 1000).get('QC_Day');
  return ee.Feature(null, {date: img.date().format('YYYY-MM-dd'),
    month: img.date().get('month'), lst_c: v, qc: qc});
});
print('Granules:', withValue.size());
print('Granules with a daytime LST:', withValue.filter(ee.Filter.notNull(['lst_c'])).size());

// Share of days without a value, month by month. The pattern follows the rain.
var missingByMonth = ee.FeatureCollection(ee.List.sequence(1, 12).map(function (m) {
  var inMonth = withValue.filter(ee.Filter.eq('month', m));
  var missing = ee.Number(1).subtract(
    ee.Number(inMonth.filter(ee.Filter.notNull(['lst_c'])).size()).divide(inMonth.size()));
  return ee.Feature(null, {month: m, missing_share: missing});
}));
print(ui.Chart.feature.byFeature(missingByMonth, 'month', ['missing_share'])
  .setChartType('ColumnChart')
  .setOptions({title: 'Share of days with no LST, by month', vAxis: {format: 'percent'}}));

// The mandatory QC bits (0-1): 0 = good quality, 1 = other quality.
var qcClass = withValue.filter(ee.Filter.notNull(['lst_c'])).map(function (f) {
  return f.set('qc_mandatory', ee.Number(f.get('qc')).bitwiseAnd(3));
});
print('Valid days by QC class:', qcClass.aggregate_histogram('qc_mandatory'));
