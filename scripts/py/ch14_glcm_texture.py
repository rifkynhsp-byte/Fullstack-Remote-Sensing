#| title: Texture from the grey level co-occurrence matrix (Python)
#| description: The same texture workflow as the JavaScript tab, run from Python.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 14 | Quantise one band, compute GLCM, keep four measures, and test
whether they separate anything. In Python.

A note on the maps below: a thumbnail is computed at its own pixel size. GLCM
over the whole delta at 1,400 pixels wide would be a 40 m texture, not a 10 m
one, so the maps show a 5 km window where the output pixel is near native.
"""

import ee
import matplotlib.pyplot as plt

from book_labels import CLASS_NAMES, LULC_PALETTE, labelled_points

aoi = ee.Geometry.Rectangle([117.30, -1.05, 117.85, -0.60])
window = ee.Geometry.Rectangle([117.45, -0.78, 117.50, -0.73])   # ponds meet mangrove


def mask_and_scale(i):
    scl = i.select("SCL")
    return (i.updateMask(scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)))
            .divide(10000).select("B.*"))


composite = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
             .filterDate("2023-01-01", "2023-12-31").filterBounds(aoi)
             .map(mask_and_scale).median().clip(aoi))

QUANT_LEVELS = 255
nir = (composite.select("B8").unitScale(0, 0.5).clamp(0, 1)
       .multiply(QUANT_LEVELS).toByte().rename("B8_quantised"))

WINDOW = 3
glcm = nir.glcmTexture(size=WINDOW)
texture = glcm.select(
    ["B8_quantised_contrast", "B8_quantised_ent", "B8_quantised_asm", "B8_quantised_corr"],
    ["tex_contrast", "tex_entropy", "tex_asm", "tex_correlation"])

# PART 5. Does it separate anything? WorldCover labels until you have your own.
training_points = labelled_points(aoi, per_class=(200, 200, 100, 100, 100))
separability = texture.sampleRegions(collection=training_points, properties=["landcover"],
                                     scale=10, tileScale=4)


def plot_texture_separability(df):
    """Entropy against contrast, one colour per class."""
    fig, ax = plt.subplots(figsize=(6.5, 4))
    for k, name in enumerate(CLASS_NAMES):
        part = df[df["landcover"] == k]
        ax.scatter(part["tex_entropy"], part["tex_contrast"], s=7, alpha=0.6,
                   color="#" + LULC_PALETTE[k], label=name)
    ax.set_yscale("symlog")
    ax.set_xlabel("Entropy (3 × 3 window)")
    ax.set_ylabel("Contrast (symlog)")
    ax.set_title("Entropy against contrast, by class", loc="left")
    ax.legend(frameon=False, fontsize=7, markerscale=2)
    return fig


def products():
    src = "Sentinel-2 B8, 2023 median, GLCM 3 × 3. GEE."
    return [
        {"kind": "map", "name": "ch14-window-rgb", "image": composite, "region": window,
         "vis": {"bands": ["B4", "B3", "B2"], "min": 0, "max": 0.3},
         "title": "True colour, 5 km window", "source": src,
         "caption": "Aquaculture ponds cut into mangrove on the delta. In true colour "
                    "the pond walls and the canopy read as similar greens."},
        {"kind": "map", "name": "ch14-entropy", "image": texture.select("tex_entropy"),
         "region": window, "vis": {"min": 0, "max": 4, "palette": ["000000", "14a37f", "ffffff"]},
         "legend": "GLCM entropy", "title": "Entropy", "source": src,
         "caption": "Entropy: smooth water is black, the broken canopy is bright, and the "
                    "straight pond walls draw themselves."},
        {"kind": "map", "name": "ch14-contrast", "image": texture.select("tex_contrast"),
         "region": window, "vis": {"min": 0, "max": 300, "palette": ["000000", "c8792b", "ffffff"]},
         "legend": "GLCM contrast", "title": "Contrast", "source": src,
         "caption": "Contrast peaks along edges, which is why it helps with narrow "
                    "fringes and hurts inside large uniform stands."},
        {"kind": "chart", "name": "ch14-separability", "data": separability,
         "plot": plot_texture_separability,
         "caption": "Texture measured at WorldCover-labelled points. Worth its cost only "
                    "if it pulls apart classes the spectra could not."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(texture.bandNames().getInfo())
