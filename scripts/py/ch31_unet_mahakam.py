#| title: A small U-Net against a Random Forest, Mahakam Delta (Python)
#| description: Fetch Sentinel-2 patches and WorldCover labels straight from Earth Engine as NumPy arrays, train a U-Net on an ordinary CPU, and score it against a Random Forest on the same held-out block.

"""
CHAPTER 31 | What Earth Engine cannot train.

Earth Engine trains Random Forests, SVMs and boosted trees on pixels. It does
not train convolutional networks, which learn from a patch of pixels around
each pixel. This script does the round trip the author uses in his Colab
notebooks, small enough to run on an ordinary CPU in a few minutes:

  1. Earth Engine builds the image: a 2021 Sentinel-2 composite of the
     Mahakam Delta (six bands) and ESA WorldCover 2021 as the label.
  2. ee.data.computePixels hands back small tiles as NumPy arrays. No
     export task, no Cloud Storage bucket.
  3. PyTorch trains a small U-Net on 64 x 64 patches cut from those tiles.
  4. A Random Forest is trained on the SAME training pixels (same six bands,
     one pixel at a time) as the baseline.
  5. Both predict one 7.7 km block that no training tile touches, and both
     are scored against WorldCover there.

The labels are WorldCover, a map made by another model. Every number below
is agreement with WorldCover, not accuracy against the ground.

Three classes: 0 mangrove (WorldCover 95), 1 water (80), 2 everything else.

    pip install earthengine-api torch scikit-learn matplotlib pandas
    (CPU torch: pip install torch --index-url https://download.pytorch.org/whl/cpu)
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ee
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SEED = 42
BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
CLASSES = ["mangrove", "water", "other"]
COLOURS = ["#075e11", "#1a5bab", "#e8c872"]

DELTA = [117.15, -1.00, 117.75, -0.30]        # the whole delta, lon/lat
TEST_CENTRE = (117.37, -0.66)                 # the held-out block
DEG_10M = 0.0000898315                        # 10 m at the equator, in degrees
TILE = 128                                    # training tiles, pixels (1.28 km)
TEST = 768                                    # held-out block, pixels (7.7 km)
SPACING = 0.03                                # training tile spacing, degrees
EPOCHS = 30

CACHE = Path(os.environ.get("BOOK_CACHE", Path.home() / ".cache" / "fullstack-rs"))
_cache = {}

# ---------------------------------------------------------------------------
# STEP 1. The image and the label, built in Earth Engine
# ---------------------------------------------------------------------------
delta = ee.Geometry.Rectangle(DELTA)


def s2_composite(start, end, threshold):
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(delta)
            .filterDate(start, end).linkCollection(cs, ["cs_cdf"])
            .map(lambda i: i.updateMask(i.select("cs_cdf").gte(threshold)))
            .select(BANDS).median())


# 2021 to match WorldCover 2021; a looser two-year composite fills any hole.
composite = s2_composite("2021-01-01", "2022-01-01", 0.6).unmask(
    s2_composite("2020-07-01", "2022-07-01", 0.4))
label = (ee.Image("ESA/WorldCover/v200/2021").select("Map")
         .remap([95, 80], [0, 1], 2).rename("label"))
stack = composite.addBands(label).toFloat()

half = TEST * DEG_10M / 2
test_box = [TEST_CENTRE[0] - half, TEST_CENTRE[1] - half,
            TEST_CENTRE[0] + half, TEST_CENTRE[1] + half]


def tile_origins():
    """Upper-left corners of training tiles on a spaced grid.

    Tiles are 0.0115 degrees wide and 0.03 degrees apart, so no two tiles
    touch, and none comes within 0.02 degrees (about 2 km) of the test block.
    """
    size = TILE * DEG_10M
    out = []
    for x in np.arange(DELTA[0], DELTA[2] - size, SPACING):
        for y in np.arange(DELTA[3], DELTA[1] + size, -SPACING):
            if (x + size > test_box[0] - 0.02 and x < test_box[2] + 0.02 and
                    y > test_box[1] - 0.02 and y - size < test_box[3] + 0.02):
                continue
            out.append((round(float(x), 5), round(float(y), 5)))
    return out


# ---------------------------------------------------------------------------
# STEP 2. Pixels to NumPy, no export task
# ---------------------------------------------------------------------------
def fetch(x0, y0, size):
    """One size x size block at 10 m as a (7, size, size) float array.

    computePixels returns a structured NumPy array, one field per band. The
    limit is 48 MB per request, so a 768 x 768 x 7 float block (16.5 MB) is
    fine; a whole delta at 10 m is not, which is when you export instead.
    """
    arr = ee.data.computePixels({
        "expression": stack, "fileFormat": "NUMPY_NDARRAY",
        "grid": {"dimensions": {"width": size, "height": size},
                 "affineTransform": {"scaleX": DEG_10M, "shearX": 0, "translateX": x0,
                                     "shearY": 0, "scaleY": -DEG_10M, "translateY": y0},
                 "crsCode": "EPSG:4326"}})
    return np.stack([arr[b] for b in BANDS + ["label"]]).astype(np.float32)


def load_data():
    """Training tiles and the test block, cached on disk after the first run."""
    if "data" in _cache:
        return _cache["data"]
    path = CACHE / "ch31_mahakam_patches.npz"
    if path.exists():
        z = np.load(path)
        data = {k: z[k] for k in z.files}
    else:
        origins = tile_origins()
        with ThreadPoolExecutor(8) as pool:        # a few requests at a time
            tiles = list(pool.map(lambda o: fetch(o[0], o[1], TILE), origins))
        tiles = np.stack(tiles)
        test = fetch(test_box[0], test_box[3], TEST)
        data = {"tiles": tiles, "origins": np.array(origins), "test": test}
        CACHE.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, **data)
    # Drop open-sea tiles: 98 % water teaches the network nothing new.
    water = (data["tiles"][:, 6] == 1).mean(axis=(1, 2))
    keep = water < 0.98
    data = {"tiles": data["tiles"][keep], "origins": data["origins"][keep],
            "test": data["test"]}
    _cache["data"] = data
    return data


def split_tiles(n, frac=1.0):
    """Whole tiles go to training or validation, never pixels from one tile to both.

    frac < 1 keeps only that share of the training tiles (whole tiles, chosen at
    random); validation tiles and the held-out block stay the same, so results
    at different fractions are comparable.
    """
    rng = np.random.default_rng(SEED)
    idx = rng.permutation(n)
    n_val = int(0.2 * n)
    tr = idx[n_val:]
    if frac < 1:
        tr = np.random.default_rng(SEED + 1).choice(tr, size=max(4, int(round(frac * len(tr)))), replace=False)
    return tr, idx[:n_val]


# ---------------------------------------------------------------------------
# STEP 3. The U-Net
# ---------------------------------------------------------------------------
def build_unet(in_ch=6, n_classes=3, base=16):
    """A three-level U-Net (Ronneberger et al. 2015), about half a million weights.

    Encoder: two 3 x 3 convolutions, then halve the size. Decoder: double the
    size and join the encoder's features at the same scale (the skip
    connections), so fine edges survive the trip through the bottleneck.
    """
    import torch
    from torch import nn

    def block(i, o):
        return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                             nn.Conv2d(o, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True))

    class UNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.e1, self.e2, self.e3 = block(in_ch, base), block(base, base * 2), block(base * 2, base * 4)
            self.mid = block(base * 4, base * 8)
            self.u3 = nn.ConvTranspose2d(base * 8, base * 4, 2, stride=2)
            self.d3 = block(base * 8, base * 4)
            self.u2 = nn.ConvTranspose2d(base * 4, base * 2, 2, stride=2)
            self.d2 = block(base * 4, base * 2)
            self.u1 = nn.ConvTranspose2d(base * 2, base, 2, stride=2)
            self.d1 = block(base * 2, base)
            self.out = nn.Conv2d(base, n_classes, 1)
            self.pool = nn.MaxPool2d(2)

        def forward(self, x):
            e1 = self.e1(x)
            e2 = self.e2(self.pool(e1))
            e3 = self.e3(self.pool(e2))
            m = self.mid(self.pool(e3))
            d3 = self.d3(torch.cat([self.u3(m), e3], 1))
            d2 = self.d2(torch.cat([self.u2(d3), e2], 1))
            d1 = self.d1(torch.cat([self.u1(d2), e1], 1))
            return self.out(d1)

    return UNet()


def normalise(x, stats):
    return (x - stats[0][:, None, None]) / stats[1][:, None, None]


def to_patches(tiles, size=64):
    """Cut each 128 x 128 tile into four 64 x 64 patches."""
    out = []
    for t in tiles:
        for i in range(0, TILE, size):
            for j in range(0, TILE, size):
                out.append(t[:, i:i + size, j:j + size])
    return np.stack(out)


def train_unet(seed=SEED, frac=1.0):
    """Train on CPU with fixed seeds; keep the epoch with the lowest validation loss."""
    if ("unet", seed, frac) in _cache:
        return _cache[("unet", seed, frac)]
    import torch
    from torch import nn
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.set_num_threads(min(8, os.cpu_count() or 1))

    data = load_data()
    tr, va = split_tiles(len(data["tiles"]), frac)
    x_tr = data["tiles"][tr, :6] / 10000
    stats = (x_tr.mean(axis=(0, 2, 3)), x_tr.std(axis=(0, 2, 3)))
    p_tr = to_patches(data["tiles"][tr])
    p_va = to_patches(data["tiles"][va])
    xt = torch.tensor(normalise(p_tr[:, :6] / 10000, stats), dtype=torch.float32)
    yt = torch.tensor(p_tr[:, 6], dtype=torch.long)
    xv = torch.tensor(normalise(p_va[:, :6] / 10000, stats), dtype=torch.float32)
    yv = torch.tensor(p_va[:, 6], dtype=torch.long)

    # Water dominates the delta. Weight each class by 1 / sqrt(frequency) so
    # the loss does not let the network ignore the rarer classes.
    freq = np.bincount(p_tr[:, 6].astype(int).ravel(), minlength=3) / p_tr[:, 6].size
    weights = torch.tensor(1 / np.sqrt(freq), dtype=torch.float32)
    weights = weights / weights.mean()

    model = build_unet()
    loss_fn = nn.CrossEntropyLoss(weight=weights)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    gen = torch.Generator().manual_seed(seed)
    history, best, best_state = [], np.inf, None
    t0 = time.perf_counter()
    for epoch in range(1, EPOCHS + 1):
        model.train()
        order = torch.randperm(len(xt), generator=gen)
        total = 0.0
        for k in range(0, len(xt), 16):
            b = order[k:k + 16]
            x, y = xt[b], yt[b]
            # Augment: random flips and quarter turns. A mangrove patch is
            # still a mangrove patch upside down.
            r = int(torch.randint(4, (1,), generator=gen))
            x, y = torch.rot90(x, r, (2, 3)), torch.rot90(y, r, (1, 2))
            if torch.rand(1, generator=gen) < 0.5:
                x, y = x.flip(3), y.flip(2)
            opt.zero_grad()
            loss = loss_fn(model(x), y)
            loss.backward()
            opt.step()
            total += loss.item() * len(b)
        model.eval()
        with torch.no_grad():
            out = model(xv)
            v_loss = loss_fn(out, yv).item()
            v_acc = (out.argmax(1) == yv).float().mean().item()
        history.append({"epoch": epoch, "train_loss": total / len(xt),
                        "val_loss": v_loss, "val_accuracy": v_acc})
        if v_loss < best:
            best = v_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
    seconds = time.perf_counter() - t0
    model.load_state_dict(best_state)
    model.eval()
    n_params = sum(p.numel() for p in model.parameters())
    _cache[("unet", seed, frac)] = {"model": model, "stats": stats, "history": pd.DataFrame(history),
                      "seconds": seconds, "params": n_params,
                      "train_pixels": int(p_tr[:, 6].size), "tiles_train": len(tr),
                      "tiles_val": len(va)}
    return _cache[("unet", seed, frac)]


# ---------------------------------------------------------------------------
# STEP 4. The Random Forest baseline, on the same training pixels
# ---------------------------------------------------------------------------
def pixel_features(block, context=False):
    """(pixels, features) for one (7, h, w) block.

    context=False: the six bands, nothing else.
    context=True: the six bands plus their mean and standard deviation in a
    5 x 5 window, a cheap way to give a pixel classifier some neighbourhood.
    """
    from scipy.ndimage import uniform_filter
    x = block[:6] / 10000
    feats = [x]
    if context:
        m = uniform_filter(x, size=(1, 5, 5), mode="reflect")
        sd = np.sqrt(np.maximum(uniform_filter(x ** 2, size=(1, 5, 5), mode="reflect") - m ** 2, 0))
        feats += [m, sd]
    f = np.concatenate(feats)
    return f.reshape(len(f), -1).T


def train_rf(context=False, frac=1.0):
    """Same tiles, same six bands, one pixel at a time."""
    if ("rf", context, frac) in _cache:
        return _cache[("rf", context, frac)]
    from sklearn.ensemble import RandomForestClassifier
    data = load_data()
    tr, _ = split_tiles(len(data["tiles"]), frac)
    t = data["tiles"][tr]
    x = np.concatenate([pixel_features(b, context) for b in t])
    y = t[:, 6].ravel().astype(int)
    rng = np.random.default_rng(SEED)
    pick = rng.choice(len(y), size=min(200_000, len(y)), replace=False)
    rf = RandomForestClassifier(n_estimators=100, n_jobs=-1, random_state=SEED,
                                class_weight="balanced")
    t0 = time.perf_counter()
    rf.fit(x[pick], y[pick])
    _cache[("rf", context, frac)] = {"model": rf, "seconds": time.perf_counter() - t0,
                                     "pixels": len(pick)}
    return _cache[("rf", context, frac)]


# ---------------------------------------------------------------------------
# STEP 5. Predict the held-out block and score both
# ---------------------------------------------------------------------------
def predictions():
    if "pred" in _cache:
        return _cache["pred"]
    data = load_data()
    test = data["test"]
    p_unet = unet_predict(SEED, test)
    p_rf = train_rf()["model"].predict(pixel_features(test)).reshape(TEST, TEST)
    p_rfc = train_rf(True)["model"].predict(pixel_features(test, True)).reshape(TEST, TEST)
    _cache["pred"] = {"truth": test[6].astype(int), "unet": p_unet, "rf": p_rf, "rf_context": p_rfc}
    return _cache["pred"]


def confusion(truth, pred):
    m = np.zeros((3, 3), dtype=int)
    np.add.at(m, (truth.ravel(), pred.ravel()), 1)
    return m


def scores(m):
    oa = np.trace(m) / m.sum()
    pe = (m.sum(0) * m.sum(1)).sum() / m.sum() ** 2
    f1 = [2 * m[i, i] / (m[i].sum() + m[:, i].sum()) for i in range(3)]
    return oa, (oa - pe) / (1 - pe), f1


def unet_predict(seed, test, frac=1.0):
    import torch
    u = train_unet(seed, frac)
    x = torch.tensor(normalise(test[None, :6] / 10000, u["stats"]), dtype=torch.float32)
    with torch.no_grad():
        return u["model"](x).argmax(1)[0].numpy()


def summary_frame():
    p = predictions()
    rows = []
    for name, key, secs in [("Random Forest, 6 bands per pixel", "rf", train_rf()["seconds"]),
                            ("Random Forest, + 5 x 5 mean and s.d.", "rf_context",
                             train_rf(True)["seconds"]),
                            ("U-Net, 64 x 64 patches", "unet", train_unet()["seconds"])]:
        oa, kappa, f1 = scores(confusion(p["truth"], p[key]))
        rows.append({"model": name, "overall_agreement": oa, "kappa": kappa,
                     "F1_mangrove": f1[0], "F1_water": f1[1], "F1_other": f1[2],
                     "train_seconds_cpu": secs})
    return pd.DataFrame(rows)


def seeds_frame():
    """The same U-Net, trained three times with different seeds.

    A deep network's result depends on its random start and the order it
    sees the patches. Before you claim one model beats another by a point,
    see how far the same model moves on its own.
    """
    test = load_data()["test"]
    truth = test[6].astype(int)
    rows = []
    for seed in (SEED, 7, 2021):
        oa, kappa, f1 = scores(confusion(truth, unet_predict(seed, test)))
        rows.append({"seed": seed, "overall_agreement": oa, "kappa": kappa,
                     "F1_other": f1[2], "train_seconds_cpu": train_unet(seed)["seconds"]})
    return pd.DataFrame(rows)


def setup_frame():
    d, u, rf = load_data(), train_unet(), train_rf()
    truth = predictions()["truth"]
    share = np.bincount(truth.ravel(), minlength=3) / truth.size
    return pd.DataFrame([
        {"item": "Training tiles / validation tiles (128 x 128 px)",
         "value": f"{u['tiles_train']} / {u['tiles_val']}"},
        {"item": "U-Net training pixels (all of them)", "value": f"{u['train_pixels']:,}"},
        {"item": "Random Forest training pixels (random subset)", "value": f"{rf['pixels']:,}"},
        {"item": "U-Net weights", "value": f"{u['params']:,}"},
        {"item": "Held-out block, WorldCover share mangrove / water / other",
         "value": " / ".join(f"{s:.0%}" for s in share)},
    ])


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def history_frame():
    return train_unet()["history"]


def plot_history(df):
    """Loss falls on both sets; where validation stops falling, training has learnt enough."""
    fig, (a, b) = plt.subplots(1, 2, figsize=(9, 3.2))
    a.plot(df["epoch"], df["train_loss"], color="#1f78b4", label="training")
    a.plot(df["epoch"], df["val_loss"], color="#e66101", label="validation")
    best = df.loc[df["val_loss"].idxmin(), "epoch"]
    a.axvline(best, color="#616e7c", ls=":", lw=1)
    a.text(best + 0.3, a.get_ylim()[1] * 0.95, f"kept: epoch {best}", fontsize=7, va="top")
    a.set_xlabel("Epoch")
    a.set_ylabel("Weighted cross-entropy")
    a.legend(frameon=False, fontsize=8)
    a.set_title("Loss", loc="left")
    b.plot(df["epoch"], df["val_accuracy"], color="#e66101")
    b.set_xlabel("Epoch")
    b.set_ylabel("Share of validation pixels")
    b.set_title("Validation agreement with WorldCover", loc="left")
    fig.tight_layout()
    return fig


def figure_confusion():
    p = predictions()
    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    for ax, key, title in [(axes[0], "rf", "Random Forest"), (axes[1], "unet", "U-Net")]:
        m = confusion(p["truth"], p[key])
        row = m / m.sum(1, keepdims=True)
        ax.imshow(row, cmap="Blues", vmin=0, vmax=1)
        for i in range(3):
            for j in range(3):
                ax.text(j, i, f"{row[i, j]:.0%}\n{m[i, j]:,}", ha="center", va="center",
                        fontsize=8, color="white" if row[i, j] > 0.6 else "#1f2933")
        ax.set_xticks(range(3), CLASSES)
        ax.set_yticks(range(3), CLASSES)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("WorldCover 2021")
        oa, kappa, _ = scores(m)
        ax.set_title(f"{title}: agreement {oa:.1%}, kappa {kappa:.2f}", loc="left", fontsize=9)
        ax.spines[:].set_visible(False)
    fig.text(0.01, 0.005, "Rows sum to 100 %: of the pixels WorldCover calls X, "
             "where each model put them. Held-out block, 589,824 pixels.",
             fontsize=7, color="#616e7c")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def figure_maps():
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    d, p = load_data(), predictions()
    rgb = d["test"][[4, 3, 2]].transpose(1, 2, 0)            # SWIR1, NIR, red
    rgb = np.clip((rgb - 100) / 3400, 0, 1)
    cmap = ListedColormap(COLOURS)
    diff = np.where(p["unet"] == p["truth"], 0, 1) - np.where(p["rf"] == p["truth"], 0, 1)
    panels = [("Sentinel-2 2021 (SWIR1, NIR, red)", rgb, None),
              ("WorldCover 2021, the label", p["truth"], cmap),
              ("Random Forest", p["rf"], cmap),
              ("U-Net", p["unet"], cmap)]
    fig, axes = plt.subplots(2, 2, figsize=(9, 9.4))
    for ax, (title, img, cm) in zip(axes.ravel(), panels):
        if cm is None:
            ax.imshow(img)
        else:
            ax.imshow(img, cmap=cm, vmin=0, vmax=2, interpolation="nearest")
        ax.set_title(title, loc="left", fontsize=9)
        ax.set_axis_off()
    fig.legend(handles=[Patch(color=c, label=n) for n, c in zip(CLASSES, COLOURS)],
               loc="lower center", bbox_to_anchor=(0.5, 0.035), ncol=3, frameon=False,
               fontsize=9)
    fig.text(0.01, 0.005, f"Held-out block, 7.7 km across, centred {TEST_CENTRE[0]}°E "
             f"{abs(TEST_CENTRE[1])}°S. U-Net disagrees with WorldCover on "
             f"{(p['unet'] != p['truth']).mean():.1%} of pixels, Random Forest on "
             f"{(p['rf'] != p['truth']).mean():.1%}.", fontsize=7, color="#616e7c")
    fig.tight_layout(rect=(0, 0.075, 1, 1))
    return fig


def overview_image():
    """The composite with the training tiles (white) and the held-out block (red)."""
    d = load_data()
    size = TILE * DEG_10M
    tiles = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle(
        [float(x), float(y) - size, float(x) + size, float(y)])) for x, y in d["origins"]])
    block = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle(test_box))])
    base = composite.visualize(bands=["B11", "B8", "B4"], min=100, max=3500)
    return (base.blend(ee.Image().byte().paint(tiles, 1, 2).visualize(palette=["ffffff"]))
            .blend(ee.Image().byte().paint(block, 1, 3).visualize(palette=["ff2d55"])))


# ---------------------------------------------------------------------------
# STEP 6. Fewer labels: which model loses more?
# ---------------------------------------------------------------------------
FRACTIONS = (0.1, 0.25, 0.5, 1.0)


def scarcity_frame():
    """Both models trained on 10 %, 25 %, 50 % and all of the training tiles, scored on the same block."""
    if "scarcity" in _cache:
        return _cache["scarcity"]
    data = load_data()
    test = data["test"]
    truth = test[6].astype(int)
    rows = []
    for f in FRACTIONS:
        tr, _ = split_tiles(len(data["tiles"]), f)
        for name, pred in (("U-Net", lambda: unet_predict(SEED, test, f)),
                           ("Random Forest + 5 x 5", lambda: train_rf(True, f)["model"].predict(pixel_features(test, True)).reshape(TEST, TEST))):
            oa, kappa, f1 = scores(confusion(truth, pred()))
            rows.append({"training tiles": len(tr), "share": f, "model": name, "overall_agreement": oa,
                         "kappa": kappa, "F1_other": f1[2]})
    _cache["scarcity"] = pd.DataFrame(rows)
    return _cache["scarcity"]


def plot_scarcity(df):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.6))
    for name, c in (("U-Net", "#6a51a3"), ("Random Forest + 5 x 5", "#1b7837")):
        g = df[df.model == name].sort_values("training tiles")
        a1.plot(g["training tiles"], g.kappa, marker="o", color=c, label=name)
        a2.plot(g["training tiles"], g.F1_other, marker="o", color=c, label=name)
    for a, lab in ((a1, "kappa"), (a2, "F1, class 'other'")):
        a.set_xscale("log"); a.set_xlabel("training tiles (128 x 128 px, log scale)"); a.set_ylabel(lab)
        a.spines[["top", "right"]].set_visible(False)
    a1.legend(frameon=False, fontsize=8)
    small = df[df.share == FRACTIONS[0]].set_index("model").kappa
    fig.suptitle(f"With {int(df[df.share == FRACTIONS[0]]['training tiles'].iloc[0])} tiles: kappa {small['U-Net']:.2f} for the U-Net, "
                 f"{small['Random Forest + 5 x 5']:.2f} for the forest", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return fig


def products():
    return [
        {"kind": "map", "name": "ch31-tiles", "image": overview_image(),
         "vis": {}, "region": delta,
         "title": "Training tiles and the held-out block, Mahakam Delta",
         "source": "Sentinel-2 SR 2021 (SWIR1, NIR, red), Cloud Score+. GEE.",
         "caption": "Every white square is one 1.28 km training tile fetched with "
                    "computePixels; open sea tiles are dropped. The red square is the "
                    "held-out block. No training tile comes within 2 km of it."},
        {"kind": "chart", "name": "ch31-history", "data": history_frame, "plot": plot_history,
         "caption": "Training curves for the U-Net on a desktop CPU. The dotted line is the "
                    "epoch that was kept: the one with the lowest validation loss."},
        {"kind": "figure", "name": "ch31-maps", "figure": figure_maps,
         "caption": "The held-out block through both models. Compare the edges of the "
                    "aquaculture ponds and the thin creeks."},
        {"kind": "figure", "name": "ch31-confusion", "figure": figure_confusion,
         "caption": "Confusion matrices on the held-out block, against WorldCover 2021."},
        {"kind": "table", "name": "ch31-scores", "data": summary_frame,
         "floatfmt": ("", ".3f", ".3f", ".3f", ".3f", ".3f", ".0f"),
         "caption": "Agreement with WorldCover 2021 on the held-out block. Training "
                    "time is wall-clock seconds on the author's desktop CPU (8 threads, "
                    "no GPU); yours will differ."},
        {"kind": "table", "name": "ch31-seeds", "data": seeds_frame,
         "floatfmt": (".0f", ".3f", ".3f", ".3f", ".0f"),
         "caption": "The same U-Net trained with three seeds. The spread is the noise "
                    "floor: a gap between models smaller than this is not a result."},
        {"kind": "table", "name": "ch31-setup", "data": setup_frame,
         "caption": "What went into the comparison."},
        {"kind": "table", "name": "ch31-scarcity", "data": scarcity_frame, "floatfmt": (".0f", ".2f", "", ".3f", ".3f", ".3f"),
         "caption": "Both models trained on a random share of whole training tiles (same seed, same validation tiles), scored on the same held-out block."},
        {"kind": "chart", "name": "ch31-scarcity-chart", "data": scarcity_frame, "plot": plot_scarcity, "live": False,
         "caption": "Fewer labels, measured: kappa and the F1 of the hardest class as the training set shrinks."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    print(summary_frame().to_string())
