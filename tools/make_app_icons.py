#!/usr/bin/env python3
"""
make_app_icons.py
=================

Draw the app icons a phone needs when the site is installed to a home screen.

Why a script and not a design tool
----------------------------------
The icon is the favicon in ``landing/assets/favicon.svg``: a rounded teal
square, a globe outline with one meridian and one parallel, and a solid patch
at the centre standing for a pixel. Redrawing that by hand at four sizes, in a
raster editor, is how an icon set drifts out of step with the favicon it is
supposed to match. Here the geometry is written once and scaled.

    python3 tools/make_app_icons.py

Writes into ``landing/assets/``:

    icon-192.png          the ordinary launcher icon
    icon-512.png          the large one, used for splash screens
    icon-maskable-512.png the same art inset, for platforms that crop
    apple-touch-icon.png  180 px, iOS, which ignores the manifest

About the maskable one: Android may crop a launcher icon to a circle, a
squircle or a rounded square depending on the device. It guarantees only the
middle 80 percent of the image, the "safe zone", so that file carries the art
at 62 percent scale on a full bleed background. Supplying it is the difference
between an icon that looks deliberate and one with its edges shaved off.

Requires Pillow, which is in requirements.txt.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "landing" / "assets"

TEAL = (15, 107, 87, 255)        # #0f6b57, the background
LINE = (127, 227, 196, 255)      # #7fe3c4, the globe
PATCH = (20, 163, 127, 255)      # #14a37f, the pixel at the centre

# Everything below is drawn at 8x and downsampled, which is cheaper than
# computing antialiased curves and looks better than either.
SUPER = 8


def draw_icon(size: int, art_scale: float = 1.0, full_bleed: bool = False) -> Image.Image:
    """The icon at ``size`` pixels.

    ``art_scale`` shrinks the artwork inside the canvas without shrinking the
    background, which is what a maskable icon needs. ``full_bleed`` fills the
    whole canvas with the background colour instead of drawing a rounded
    square, because a platform that crops will supply its own shape.
    """
    s = size * SUPER
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if full_bleed:
        d.rectangle([0, 0, s, s], fill=TEAL)
    else:
        # 12/64 corner radius, the same proportion as the SVG.
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 12 / 64), fill=TEAL)

    # Artwork geometry, in units of the 64 unit SVG viewBox.
    c = s / 2
    unit = (s / 64) * art_scale
    r = 17 * unit                      # globe radius
    stroke = max(int(3 * unit), 2)
    thin = max(int(2.2 * unit), 2)

    d.ellipse([c - r, c - r, c + r, c + r], outline=LINE, width=stroke)

    # The equator.
    d.line([c - r, c, c + r, c], fill=LINE, width=thin)

    # Two meridians, as ellipses narrowed to a third of the globe's width.
    # In the SVG these are quadratic curves; an ellipse of the same extent is
    # indistinguishable at icon sizes and does not need a path rasteriser.
    mer = r * 0.42
    d.ellipse([c - mer, c - r, c + mer, c + r], outline=LINE, width=thin)

    # The pixel: 12 units square, centred.
    half = 6 * unit
    d.rectangle([c - half, c - half, c + half, c + half], fill=PATCH)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    written = []
    for name, size, scale, bleed in [
        ("icon-192.png", 192, 1.0, False),
        ("icon-512.png", 512, 1.0, False),
        ("icon-maskable-512.png", 512, 0.62, True),
        # iOS does not read the manifest and does not apply a mask, so this
        # one is the plain rounded square at the size iOS asks for.
        ("apple-touch-icon.png", 180, 1.0, False),
    ]:
        path = OUT / name
        draw_icon(size, art_scale=scale, full_bleed=bleed).save(path, "PNG", optimize=True)
        written.append(f"  {name}  {path.stat().st_size // 1024} KB")

    print("make_app_icons: wrote")
    print("\n".join(written))


if __name__ == "__main__":
    main()
