#| title: Automatic LiDAR point classification (Python)
#| description: Ground points found automatically with a progressive morphological filter, vegetation split by height above ground, and the result scored against the classes delivered with the lidR example data.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

"""
CHAPTER 54 | Teaching the computer which points are ground.

A raw LiDAR delivery is a cloud of points with no labels, or with labels you
should check. The first and most important label is GROUND: everything
else (terrain models, canopy height, biomass) depends on it.

    1. hide the delivered classes of the lidR "Topography" file
    2. ground: progressive morphological filter (Zhang et al. 2003), the
       algorithm behind lidR's pmf(): open a minimum surface with growing
       windows; a point is ground if it lies close to the opened surface
    3. vegetation: height above the new ground, ASPRS classes
       3 low (< 2 m), 4 medium (2-5 m), 5 high (> 5 m)
    4. score ground against the delivered classes

No Earth Engine: LiDAR stays on your own machine (Chapter 32).
"""

from pathlib import Path

import laspy
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from scipy.interpolate import griddata

DATA = Path(__file__).resolve().parents[2] / "data" / "lidar"
CELL = 1.0


def read(name="Topography.laz"):
    las = laspy.read(DATA / name)
    last = np.asarray(las.return_number) == np.asarray(las.number_of_returns)
    return (np.asarray(las.x), np.asarray(las.y), np.asarray(las.z),
            np.asarray(las.classification), last)


def pmf_ground(x, y, z, last, windows=(3, 5, 9, 17, 33, 65), dh0=0.3, slope=0.15, dh_max=3.0):
    """Progressive morphological filter on a minimum-elevation grid of LAST returns
    (ground is usually the last thing a pulse hits). Windows must grow beyond the
    widest patch of canopy, or the filter cannot see past it."""
    ix = ((x - x.min()) / CELL).astype(int)
    iy = ((y.max() - y) / CELL).astype(int)
    grid = np.full((iy.max() + 1, ix.max() + 1), np.inf)
    np.minimum.at(grid, (iy[last], ix[last]), z[last])
    grid[np.isinf(grid)] = np.nan
    filled = np.where(np.isnan(grid), ndi.grey_erosion(np.nan_to_num(grid, nan=1e9), 3), grid)
    surface = filled.copy()
    ground_cell = np.ones_like(filled, bool)
    w_prev = 1
    for w in windows:
        opened = ndi.grey_dilation(ndi.grey_erosion(surface, size=w), size=w)
        dh = min(dh0 + slope * (w - w_prev) * CELL, dh_max)        # threshold grows with window
        ground_cell &= (surface - opened) <= dh
        surface = opened
        w_prev = w
    # Interpolate a terrain surface from the ground cells, then test every point.
    gy, gx = np.nonzero(ground_cell & ~np.isnan(grid))
    dtm = griddata((gx, gy), filled[gy, gx], (ix, iy), method="linear")
    dtm = np.where(np.isnan(dtm), griddata((gx, gy), filled[gy, gx], (ix, iy), method="nearest"), dtm)
    return z - dtm


_c = {}


def classified():
    if not _c:
        x, y, z, cls, last = read()
        hag = pmf_ground(x, y, z, last)                        # height above the estimated ground
        auto = np.select([hag <= 0.3, hag < 2, hag < 5], [2, 3, 4], default=5)
        _c.update(x=x, y=y, z=z, cls=cls, hag=hag, auto=auto)
    return _c


def ground_table():
    c = classified()
    keep = c["cls"] != 9                                 # water points: not part of the test
    truth = (c["cls"] == 2)[keep]
    pred = (c["auto"] == 2)[keep]
    tp = (truth & pred).sum(); fp = (~truth & pred).sum(); fn = (truth & ~pred).sum()
    tn = (~truth & ~pred).sum()
    n = tp + fp + fn + tn
    po = (tp + tn) / n
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / n ** 2
    return pd.DataFrame([{"points": n, "delivered_ground_share": truth.mean(),
                          "ground_recall": tp / (tp + fn), "ground_precision": tp / (tp + fp),
                          "overall_accuracy": po, "kappa": (po - pe) / (1 - pe)}])


def class_table():
    c = classified()
    names = {2: "2 ground", 3: "3 low vegetation (< 2 m)", 4: "4 medium vegetation (2-5 m)",
             5: "5 high vegetation (> 5 m)"}
    s = pd.Series(c["auto"]).map(names).value_counts(normalize=True).reindex(names.values()).fillna(0)
    return s.rename("share_of_points").reset_index().rename(columns={"index": "automatic class"})


def section_figure():
    c = classified()
    strip = np.abs(c["y"] - np.median(c["y"])) < 2.5
    cols = {2: "#8c510a", 3: "#c7e9c0", 4: "#74c476", 5: "#00441b"}
    fig, (a, b) = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
    xs = c["x"][strip] - c["x"].min()
    a.scatter(xs, c["z"][strip], s=0.8, c=np.where(c["cls"][strip] == 2, "#8c510a", "#1b7837"))
    a.set_title("Delivered classes: ground (brown) and everything else", loc="left", fontsize=10)
    b.scatter(xs, c["z"][strip], s=0.8, c=[cols[k] for k in c["auto"][strip]])
    b.set_title("Automatic: ground by PMF, vegetation split by height above it", loc="left",
                fontsize=10)
    b.set_xlabel("Distance along a 5 m slice (m)")
    for ax in (a, b):
        ax.set_ylabel("Elevation (m)")
    fig.tight_layout()
    return fig


def dtm_table():
    """What the ground class is FOR: compare the terrain models it produces."""
    c = classified()
    x, y, z = c["x"], c["y"], c["z"]
    gx = np.arange(x.min() + 5, x.max() - 5, CELL)
    gy = np.arange(y.min() + 5, y.max() - 5, CELL)
    GX, GY = np.meshgrid(gx, gy)
    mine = c["auto"] == 2
    theirs = c["cls"] == 2
    d_mine = griddata((x[mine], y[mine]), z[mine], (GX, GY), method="linear")
    d_theirs = griddata((x[theirs], y[theirs]), z[theirs], (GX, GY), method="linear")
    diff = (d_mine - d_theirs)[~np.isnan(d_mine - d_theirs)]
    return pd.DataFrame([{"grid_cells": diff.size, "median_difference_m": np.median(diff),
                          "mean_abs_difference_m": np.abs(diff).mean(),
                          "rmse_m": np.sqrt((diff ** 2).mean()),
                          "share_within_0.5m": (np.abs(diff) <= 0.5).mean(),
                          "p95_abs_m": np.percentile(np.abs(diff), 95)}])


def products():
    return [
        {"kind": "figure", "name": "ch54-section", "figure": section_figure,
         "caption": "The same 5 m slice of the lidR Topography file, classified by the data "
                    "provider (top) and automatically (bottom)."},
        {"kind": "table", "name": "ch54-ground", "data": ground_table,
         "floatfmt": (",.0f", ".1%", ".1%", ".1%", ".1%", ".2f"),
         "caption": "Automatic ground against the delivered ground class, point by point "
                    "(water points excluded). The delivered class is conservative: many "
                    "unlabelled points lie on the provider's own ground surface, so "
                    "precision here is understated."},
        {"kind": "table", "name": "ch54-dtm", "data": dtm_table,
         "floatfmt": (",.0f", ".2f", ".2f", ".2f", ".1%", ".2f"),
         "caption": "The fair test: terrain models (1 m) built from the automatic ground and "
                    "from the delivered ground, cell by cell."},
        {"kind": "table", "name": "ch54-classes", "data": class_table,
         "floatfmt": ("", ".1%"),
         "caption": "Share of points in each automatic class (ASPRS codes)."},
    ]


if __name__ == "__main__":
    print(ground_table())
