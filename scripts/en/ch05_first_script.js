//| title: Your first Earth Engine script
//| description: Load a global elevation model, inspect it, and paint it on the map.

/**
 * CHAPTER 5 | Your first Earth Engine script
 * ---------------------------------------------------------------------------
 * Goal
 *   Touch every panel of the Code Editor once, using the smallest useful
 *   dataset in the catalogue: a single global elevation image.
 *
 * What to watch
 *   Nothing here downloads a pixel to your laptop. Every line below builds a
 *   description of work. Google's servers do the work only when the map needs
 *   a tile or the Console needs a value.
 *
 * Adapted from the EE101 teaching series by Noel Gorelick, David Gibson,
 * Nicholas Clinton and Hadi. See the References chapter for repository links.
 */

// ---------------------------------------------------------------------------
// 1. Load a single image from the public catalogue
// ---------------------------------------------------------------------------
// CGIAR/SRTM90_V4 is one image covering the whole planet: the Shuttle Radar
// Topography Mission elevation model, resampled to roughly 90 m.
//
// Two routes get you the same object. You can search "SRTM" in the catalogue
// bar, click Import, and rename the variable in the Imports block at the top
// of the editor. Or you can name the asset ID directly, as below. The second
// route is preferred in a book, because the script is self contained and
// survives being copied between accounts.
var dem = ee.Image('CGIAR/SRTM90_V4');

// ---------------------------------------------------------------------------
// 2. Ask the server what it is holding
// ---------------------------------------------------------------------------
// print() sends a request to Earth Engine and writes the reply into the
// Console tab on the right. Expand the result to see the band list, the data
// type, the pixel footprint and the metadata properties. Reading this reply
// carefully is the habit that prevents most later errors: band names and data
// types are the two things scripts most often get wrong.
print('SRTM image object:', dem);

// ---------------------------------------------------------------------------
// 3. Draw it, plainly
// ---------------------------------------------------------------------------
// Map.addLayer(eeObject, visParams, name, shown, opacity)
//
//   eeObject  what to draw
//   visParams how to stretch it into pixels the screen can show
//   name      the label in the Layers control, top right of the map
//   shown     1 or true draws it immediately, 0 or false leaves it unticked
//   opacity   0 is invisible, 1 is solid
//
// The layer below is deliberately added with shown = 0, so it appears in the
// Layers list but stays switched off. Toggling it on and off is the quickest
// way to compare two renderings of the same data.
Map.addLayer(dem.select('elevation'), {min: 0, max: 1200}, 'DEM grey', 0, 0.5);

// ---------------------------------------------------------------------------
// 4. Draw it again, with a colour ramp
// ---------------------------------------------------------------------------
// A greyscale stretch answers "how high", but poorly. A palette maps the
// same numeric range onto colours the eye separates far more easily.
// Palette entries are spread evenly across the min to max range.
var elevationPalette = ['blue', 'cyan', 'green', 'yellow', 'red', 'brown'];

var elevationVis = {
  min: 0,               // metres. Sea level and below clamps to the first colour.
  max: 1200,            // metres. Anything higher clamps to the last colour.
  palette: elevationPalette
};

Map.addLayer(dem.select('elevation'), elevationVis, 'DEM palettised', 1, 0.5);

// ---------------------------------------------------------------------------
// 5. Point the map somewhere useful
// ---------------------------------------------------------------------------
// Map.setCenter(longitude, latitude, zoom). Longitude first, which is the
// reverse of the latitude first order used by most web mapping libraries and
// by nearly every GPS app. This is a common source of "my study area is in
// the ocean" bugs.
//
// Tip: open the Inspector tab, click anywhere on the map, and the panel
// reports the coordinates and the pixel value under the cursor. That is where
// the numbers below came from.
Map.setCenter(117.161, -0.53, 5);   // central Kalimantan, Indonesia

// ---------------------------------------------------------------------------
// Exercise
// ---------------------------------------------------------------------------
// 1. Change max from 1200 to 3000 and rerun. Which landscapes lose detail,
//    and why does the coastline become harder to read?
// 2. Replace the palette with a two colour ramp such as ['white', 'black'].
//    Decide which version communicates relief better to a non specialist.
// 3. Use the Inspector to find the elevation at the summit nearest your own
//    study area, then set min and max to bracket that value.
