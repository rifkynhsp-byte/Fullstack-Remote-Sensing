#| title: An analysis ready multisensor stack (Python)
#| description: The same fusion as the JavaScript tab, run from Python.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 10 | Sentinel-2, Sentinel-1, ALOS PALSAR, terrain and texture fused
into one stack, in Python. The function mirrors getAnalysisReadyData() in
the JavaScript tab step for step.
"""

import ee
import matplotlib.pyplot as plt

CLOUD_THRESHOLD = 25   # percent, scene level pre filter
SPECKLE_RADIUS = 50    # metres, radar smoothing window
GLCM_WINDOW = 4        # pixels, texture neighbourhood


def mask_s2_clouds(image):
    scl = image.select("SCL")
    clear = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
    return (image.updateMask(clear).divide(10000).select("B.*")
            .copyProperties(image, ["system:time_start"]))


def add_indices(image):
    ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
    evi = image.expression(
        "2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))",
        {"NIR": image.select("B8"), "RED": image.select("B4"),
         "BLUE": image.select("B2")}).rename("EVI")
    savi = image.expression(
        "((NIR - RED) / (NIR + RED + 0.5)) * 1.5",
        {"NIR": image.select("B8"), "RED": image.select("B4")}).rename("SAVI")
    mndwi = image.normalizedDifference(["B3", "B11"]).rename("MNDWI")
    return image.addBands([ndvi, evi, savi, mndwi])


def speckle_filter(image):
    return image.focal_median(SPECKLE_RADIUS, "circle", "meters")


def get_analysis_ready_data(year, aoi):
    start, end = ee.Date.fromYMD(year, 1, 1), ee.Date.fromYMD(year, 12, 31)

    # 1. Optical
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
          .filterDate(start, end).filterBounds(aoi)
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_THRESHOLD))
          .map(mask_s2_clouds))
    s2_composite = s2.median().clip(aoi)
    s2_indices = add_indices(s2_composite)

    # 2. C-band radar
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD")
          .filterDate(start, end).filterBounds(aoi)
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .select(["VV", "VH"]))
    s1_filtered = speckle_filter(s1.median().clip(aoi).rename(["S1_VV", "S1_VH"]))

    # 3. L-band radar. Check coverage, not existence: the 2023 epoch covers
    #    about a quarter of the delta, so lay the chosen year over the one
    #    before and let gaps fall back to the previous epoch.
    palsar = (ee.ImageCollection("JAXA/ALOS/PALSAR/YEARLY/SAR_EPOCH").filterBounds(aoi)
              .filter(ee.Filter.calendarRange(year - 1, year, "year"))
              .sort("system:time_start").mosaic())
    dn = palsar.select(["HH", "HV"]).clip(aoi)
    # gamma0 in dB = 10 * log10(DN^2) - 83. Chart it before trusting it.
    gamma0 = dn.pow(2).log10().multiply(10).subtract(83.0).rename(["PALSAR_HH", "PALSAR_HV"])

    # 4. Terrain (AW3D30 v4.1: mosaic the tiles, restore the projection)
    aw3d = ee.ImageCollection("JAXA/ALOS/AW3D30/V4_1")
    dem = (aw3d.select("DSM").filterBounds(aoi).mosaic()
           .setDefaultProjection(aw3d.first().projection()).clip(aoi))
    slope = ee.Terrain.slope(dem)

    # 5. Texture on one integer band
    nir = s2_composite.select("B8").multiply(10000).toInt16()
    glcm = nir.glcmTexture(size=GLCM_WINDOW)
    contrast = glcm.select("B8_contrast").rename("contrast")
    asm = glcm.select("B8_asm").rename("asm")

    # 6. Fuse, one data type throughout
    return (s2_indices.addBands(s1_filtered).addBands(gamma0).addBands(dem)
            .addBands(slope).addBands(contrast).addBands(asm)
            .float().set("year", year))


aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60])   # Mahakam Delta
image2023 = get_analysis_ready_data(2023, aoi)

s1_false_colour = (image2023.select("S1_VV").addBands(image2023.select("S1_VH"))
                   .addBands(image2023.select("S1_VV").subtract(image2023.select("S1_VH"))))

land = ee.Image("MERIT/Hydro/v1_0_1").select("hnd").mask()
pairs = (image2023.select(["NDVI", "S1_VH", "PALSAR_HV"]).updateMask(land)
         .sample(region=aoi, scale=30, numPixels=6000, seed=7, geometries=False))


def plot_optical_vs_radar(df):
    """Each dot is one land pixel. Where NDVI piles up near 0.8-0.9, VH still spreads."""
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.3), sharex=True)
    for ax, band, colour, label in [(axes[0], "S1_VH", "#2166ac", "Sentinel-1 VH (dB)"),
                                    (axes[1], "PALSAR_HV", "#b35806", "PALSAR-2 HV (dB)")]:
        ax.scatter(df["NDVI"], df[band], s=3, alpha=0.35, color=colour)
        ax.set_xlabel("NDVI (Sentinel-2)")
        ax.set_ylabel(label)
    fig.suptitle("Optical saturates, radar keeps going", x=0.02, ha="left")
    fig.tight_layout()
    return fig


def products():
    src = "Sentinel-2, Sentinel-1, ALOS PALSAR-2, AW3D30 v4.1, 2023. GEE."
    return [
        {"kind": "map", "name": "ch10-s2", "image": image2023, "region": aoi,
         "vis": {"bands": ["B4", "B3", "B2"], "min": 0, "max": 0.3},
         "title": "Optical: Sentinel-2 composite", "source": src,
         "caption": "The optical layer of the stack, scenes under 25 % cloud only."},
        {"kind": "map", "name": "ch10-s1", "image": s1_false_colour, "region": aoi,
         "vis": {"min": [-20, -26, 2], "max": [0, -8, 12]},
         "title": "Radar: Sentinel-1 VV, VH, VV−VH", "source": src,
         "caption": "Sentinel-1 in false colour. Smooth water is black, canopy is "
                    "bright from volume scattering, and settlements flare from double bounce."},
        {"kind": "chart", "name": "ch10-optical-vs-radar", "data": pairs,
         "plot": plot_optical_vs_radar,
         "caption": "Land pixels across the delta. Once NDVI saturates, both radar bands still "
                    "vary: that spread is the information fusion adds."},
        {"kind": "table", "name": "ch10-bands",
         "data": ee.Dictionary({"bands": image2023.bandNames().join(", "),
                                "band_count": image2023.bandNames().size()}),
         "caption": "Always print the band names before going further."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(image2023.bandNames().getInfo())
