#| title: Clusters before classes: k-means over the Bandung basin (Python)
#| description: The same clustering and cross-tabulation as the JavaScript tab, in Python.

"""
CHAPTER 16 | k-means over the Bandung basin, then what the clusters are,
according to ESA WorldCover.
"""

import ee
import matplotlib.pyplot as plt
import numpy as np

region = ee.Geometry.Rectangle([107.394, -7.070, 107.801, -6.808])   # Bandung basin
MAX_CLOUD_PROBABILITY = 35
criteria = ee.Filter.And(ee.Filter.bounds(region),
                         ee.Filter.date("2024-01-01", "2025-03-01"))
s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filter(criteria)
clouds = ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY").filter(criteria)
joined = ee.ImageCollection(ee.Join.saveFirst("cloud_mask").apply(
    primary=s2, secondary=clouds,
    condition=ee.Filter.equals(leftField="system:index", rightField="system:index")))
composite = (joined.map(lambda img: img.updateMask(
    ee.Image(img.get("cloud_mask")).select("probability").lt(MAX_CLOUD_PROBABILITY)))
             .median().select("B.*").clip(region))

K = 10
training = composite.sample(region=region, scale=300, numPixels=5000, seed=1)
clusterer = ee.Clusterer.wekaKMeans(nClusters=K, seed=1).train(training)
clusters = composite.cluster(clusterer).clip(region)

world_cover = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
crosstab = clusters.addBands(world_cover).stratifiedSample(
    numPoints=100, classBand="cluster", region=region, scale=60, seed=2, tileScale=8)

WC_NAMES = {10: "tree cover", 20: "shrub", 30: "grass", 40: "cropland", 50: "built-up",
            60: "bare", 80: "water", 90: "wetland", 95: "mangrove"}
CLUSTER_PALETTE = ["1f77b4", "ff7f0e", "2ca02c", "d62728", "9467bd", "8c564b",
                   "e377c2", "7f7f7f", "bcbd22", "17becf"]


def plot_crosstab(df):
    """For each cluster, what share of its points WorldCover puts in each class."""
    tab = (df.assign(wc=df["Map"].map(WC_NAMES)).groupby(["cluster", "wc"]).size()
           .unstack(fill_value=0))
    share = tab.div(tab.sum(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    left = np.zeros(len(share))
    colours = {"tree cover": "#397D49", "cropland": "#E49635", "built-up": "#C4281B",
               "grass": "#88B053", "water": "#419BDF", "bare": "#A59B8F",
               "shrub": "#DFC35A", "wetland": "#7A87C6", "mangrove": "#075e11"}
    for col in share.columns:
        ax.barh(share.index.astype(str), share[col], left=left, label=col,
                color=colours.get(col, "#cccccc"))
        left += share[col].to_numpy()
    ax.set_xlabel("Share of the cluster's sample points")
    ax.set_ylabel("k-means cluster")
    ax.set_title("What each cluster is, according to WorldCover", loc="left")
    ax.legend(frameon=False, fontsize=7, ncol=4, loc="upper center",
              bbox_to_anchor=(0.5, -0.18))
    return fig


def products():
    src = "Sentinel-2 SR 2024, s2cloudless mask. GEE."
    return [
        {"kind": "map", "name": "ch16-bandung-rgb", "image": composite, "region": region,
         "vis": {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000},
         "title": "Bandung basin, 2024 composite", "source": src,
         "caption": "The input: a cloud-masked median, January 2024 to February 2025."},
        {"kind": "map", "name": "ch16-bandung-kmeans", "image": clusters, "region": region,
         "vis": {"min": 0, "max": K - 1, "palette": CLUSTER_PALETTE},
         "title": f"k-means, {K} clusters, no labels", "source": src,
         "classes": [(f"cluster {i}", "#" + c) for i, c in enumerate(CLUSTER_PALETTE)],
         "caption": "Ten spectral groups. The colours are arbitrary; so are the numbers."},
        {"kind": "chart", "name": "ch16-kmeans-crosstab", "data": crosstab,
         "plot": plot_crosstab,
         "caption": "100 points per cluster, labelled by WorldCover. A cluster that is "
                    "all one colour could be named; a mixed bar is a spectral group, "
                    "not a land cover class. Cluster 0 is half water and half cropland: "
                    "flooded rice paddies look like water to a spectrum."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(crosstab.limit(5).getInfo())
