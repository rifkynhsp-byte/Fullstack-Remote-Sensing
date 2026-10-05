//| title: Land suitability and its limiting factor
//| description: FAO land evaluation for jarak (Jatropha curcas) in Pangandaran: four factors, the worst one decides, and what reading the wrong rainfall band does.

// Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
// MIT licence: free to use and adapt; please keep this credit line.

/**
 * CHAPTER 48 | Is this land suitable for this crop, and if not, why not?
 * ---------------------------------------------------------------------------
 * FAO land evaluation sorts land into S1 (highly suitable), S2 (moderately),
 * S3 (marginally) and N (not suitable). Each factor gets its own class from
 * threshold ranges; the land takes the class of its WORST factor (the law of
 * the limiting factor).
 *
 * Rules (the author's Bentala Aksa script for jarak):
 *   class  mean temp (C)  annual rain (mm)  soil pH     slope (deg)
 *   S1     24-35          700-1,400         6.0-7.0     < 8
 *   S2     20-32          600-1,800         5.5-7.2     < 15
 *   S3     16-50          500-4,000         < 14 (x10)  < 30
 *   N      everything else (inside the area)
 *
 * The original script read BIO18 (rain of the warmest quarter) as "annual
 * rain". Both versions run, to show what one band does.
 */

// ---------------------------------------------------------------------------
// STEP 1. Area and the four factors
// ---------------------------------------------------------------------------
var aoi = ee.Geometry.Rectangle([108.40, -7.85, 108.85, -7.50], null, false);   // Pangandaran
var wc = ee.Image('WORLDCLIM/V1/BIO');
var temp = wc.select('bio01').divide(10).rename('temp');        // deg C x 10 in WorldClim V1
var rain = wc.select('bio12').rename('rain');                   // annual precipitation, mm
var rainBio18 = wc.select('bio18').rename('rain');              // warmest-quarter rain, mm
var ph = ee.Image('OpenLandMap/SOL/SOL_PH-H2O_USDA-4C1A2A_M/v02').select('b0').rename('ph');  // pH x 10
var slope = ee.Terrain.slope(ee.Image('USGS/SRTMGL1_003')).rename('slope');
var land = ee.Image('ESA/WorldCover/v200/2021').select('Map').neq(80);   // not water

// ---------------------------------------------------------------------------
// STEP 2. One factor, four classes
// ---------------------------------------------------------------------------
// s1, s2, s3 are [low, high] ranges; outside s3 is N (4).
function factorClass(img, s1, s2, s3) {
  return ee.Image(4)
    .where(img.gt(s3[0]).and(img.lt(s3[1])), 3)
    .where(img.gt(s2[0]).and(img.lt(s2[1])), 2)
    .where(img.gt(s1[0]).and(img.lt(s1[1])), 1);
}

// ---------------------------------------------------------------------------
// STEP 3. The worst factor decides, and we record which one it was
// ---------------------------------------------------------------------------
function suitability(rainImg) {
  var f = ee.Image.cat(
    factorClass(temp, [24, 35], [20, 32], [16, 50]).rename('temp'),
    factorClass(rainImg, [700, 1400], [600, 1800], [500, 4000]).rename('rain'),
    factorClass(ph, [60, 70], [55, 72], [0, 140]).rename('ph'),
    factorClass(slope, [-1, 8], [-1, 15], [-1, 30]).rename('slope'));
  var overall = f.reduce(ee.Reducer.max()).rename('class');
  // limiting factor: 1 temperature, 2 rain, 3 pH, 4 slope (first match wins)
  var lim = ee.Image(0).where(f.select('slope').eq(overall), 4).where(f.select('ph').eq(overall), 3)
    .where(f.select('rain').eq(overall), 2).where(f.select('temp').eq(overall), 1);
  return {cls: overall.clip(aoi), limit: lim.rename('limit').updateMask(overall.gt(1)).clip(aoi), factors: f};
}
var ok = suitability(rain);
var orig = suitability(rainBio18);

// ---------------------------------------------------------------------------
// STEP 4. Area per class, corrected and original
// ---------------------------------------------------------------------------
var area = ee.Image.pixelArea().divide(1e4);
function byClass(c) {
  return area.addBands(c.updateMask(land)).reduceRegion({reducer: ee.Reducer.sum().group(1, 'class'),
    geometry: aoi, scale: 90, maxPixels: 1e10}).get('groups');
}
print('Area per class (ha; 1 S1, 2 S2, 3 S3, 4 N), annual rain BIO12 (corrected)', byClass(ok.cls));
print('Area per class (ha), original script with BIO18 read as annual rain', byClass(orig.cls));

// ---------------------------------------------------------------------------
// STEP 5. Maps: suitability and the limiting factor
// ---------------------------------------------------------------------------
Map.centerObject(aoi, 11);
Map.addLayer(ok.cls.updateMask(land), {min: 1, max: 4, palette: ['1a9850', 'a6d96a', 'fee08b', 'd73027']},
             'Suitability for jarak: S1, S2, S3, N');
Map.addLayer(ok.limit.updateMask(land), {min: 1, max: 4, palette: ['e41a1c', '377eb8', '984ea3', 'ff7f00']},
             'Limiting factor: temperature, rain, pH, slope', false);
Map.addLayer(orig.cls.updateMask(land), {min: 1, max: 4, palette: ['1a9850', 'a6d96a', 'fee08b', 'd73027']},
             'Original script (BIO18): for comparison', false);
