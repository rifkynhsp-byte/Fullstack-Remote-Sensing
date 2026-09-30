//| title: From points to trees: the Earth Engine side
//| description: Earth Engine cannot read a point cloud, so the Code Editor shows what LiDAR is compared with: spaceborne GEDI heights and a satellite canopy height map over a lowland forest.

/**
 * CHAPTER 32 | Where LiDAR and Earth Engine meet
 * ---------------------------------------------------------------------------
 * Airborne LiDAR arrives as .las/.laz files of millions of points. Earth
 * Engine stores rasters and vector tables, not point clouds, so the chain
 * points -> terrain -> canopy height -> trees runs on your own machine (the
 * Python tab, or lidR in R). What Earth Engine gives you is the wide view the
 * plot is later scaled to:
 *
 *   GEDI       laser footprints from the space station: relative height rh98
 *              of each 25 m shot (Dubayah et al. 2020)
 *   ETH map    a 10 m canopy height map for 2020 made by a deep network
 *              trained on GEDI (Lang et al. 2023)
 *
 * An airborne CHM from a plot is the check on both.
 */

var aoi = ee.Geometry.Rectangle([102.55, -2.05, 102.85, -1.80]);   // lowland forest, Jambi
Map.centerObject(aoi, 11);

// 1. A satellite canopy height map (metres), 10 m, year 2020.
var eth = ee.Image('users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1').clip(aoi);
Map.addLayer(eth, {min: 0, max: 35, palette: ['ffffe5', 'addd8e', '41ab5d', '005a32']},
             'ETH canopy height 2020 (m)');

// 2. GEDI shots: keep only good-quality, non-degraded footprints.
var gedi = ee.ImageCollection('LARSE/GEDI/GEDI02_A_002_MONTHLY')
  .filterBounds(aoi)
  .map(function (img) {
    return img.updateMask(img.select('quality_flag').eq(1))
              .updateMask(img.select('degrade_flag').eq(0))
              .select('rh98');
  })
  .mosaic().clip(aoi);
Map.addLayer(gedi, {min: 0, max: 40, palette: ['ffffcc', 'fd8d3c', '800026']}, 'GEDI rh98 (m)');

// 3. Compare the two where both exist. Sample GEDI pixels, read the map below.
var pairs = gedi.rename('gedi').addBands(eth.rename('eth'))
  .sample({region: aoi, scale: 25, numPixels: 3000, seed: 1, dropNulls: true});
print('GEDI shots with a map value', pairs.size());
print(ui.Chart.feature.byFeature(pairs.limit(1500), 'gedi', 'eth')
  .setChartType('ScatterChart')
  .setOptions({title: 'Satellite map against GEDI footprints',
               hAxis: {title: 'GEDI rh98 (m)'}, vAxis: {title: 'ETH map height (m)'},
               pointSize: 2, legend: 'none'}));

// A plot's airborne LiDAR CHM, uploaded as a GeoTIFF asset, would be added
// here the same way and sampled against both layers.
