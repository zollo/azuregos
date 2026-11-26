"""Render the Azuregos mark and every icon size the frontend ships.

The mark follows Navi's: a rounded square in a diagonal gradient with a
faceted white shape (here an azure crystal) crossed by an outlined object
(here a service-desk ticket), separated from it by a thin gap.

    python3 frontend/scripts/make_icons.py     # needs Pillow

Writes into frontend/public/ (see OUTPUTS). Re-run after changing the design.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

PUBLIC = Path(__file__).resolve().parent.parent / "public"

# Brand gradient, bottom-left -> top-right (mirrors --brand-gradient in index.css).
GRADIENT = [(0.0, (3, 105, 161)), (0.55, (14, 165, 233)), (1.0, (56, 189, 248))]
WHITE = (255, 255, 255)
# Crystal facets, lit from the upper left.
FACETS = {
    "top_left": (255, 255, 255),
    "left": (240, 248, 255),
    "bottom_left": (226, 241, 253),
    "top_right": (207, 232, 251),
    "right": (186, 222, 248),
    "bottom_right": (165, 210, 244),
}

S = 2048  # working resolution; every output is downsampled from this
U = S / 1000  # design units -> pixels


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def gradient(size: int) -> Image.Image:
    """45deg linear gradient across a size x size square."""
    line = Image.new("RGB", (512, 1))
    for i in range(512):
        t = i / 511
        for (t0, c0), (t1, c1) in zip(GRADIENT, GRADIENT[1:]):
            if t0 <= t <= t1:
                line.putpixel((i, 0), lerp(c0, c1, (t - t0) / (t1 - t0)))
                break
    big = line.resize((int(size * 1.5), int(size * 1.5)), Image.BILINEAR)
    big = big.rotate(45, resample=Image.BICUBIC)
    off = (big.width - size) // 2
    return big.crop((off, off, off + size, off + size))


def p(x, y):
    return (x * U, y * U)


def crystal() -> Image.Image:
    """Faceted crystal as an RGBA layer."""
    layer = Image.new("RGBA", (S, S))
    d = ImageDraw.Draw(layer)
    cx, top, bot, half_w, shoulder = 500, 70, 930, 255, 150
    t, b = p(cx, top), p(cx, bot)
    ul, ur = p(cx - half_w, 500 - shoulder), p(cx + half_w, 500 - shoulder)
    ll, lr = p(cx - half_w, 500 + shoulder), p(cx + half_w, 500 + shoulder)
    c = p(cx, 500)
    d.polygon([t, ul, c], fill=FACETS["top_left"])
    d.polygon([ul, ll, c], fill=FACETS["left"])
    d.polygon([ll, b, c], fill=FACETS["bottom_left"])
    d.polygon([t, ur, c], fill=FACETS["top_right"])
    d.polygon([ur, lr, c], fill=FACETS["right"])
    d.polygon([lr, b, c], fill=FACETS["bottom_right"])
    return layer


def ticket_shape(w, h, r, notch) -> Image.Image:
    """Filled ticket (rounded rect with a notch in each short side), unrotated, centered."""
    m = Image.new("L", (S, S))
    d = ImageDraw.Draw(m)
    x0, y0, x1, y1 = S / 2 - w * U / 2, S / 2 - h * U / 2, S / 2 + w * U / 2, S / 2 + h * U / 2
    d.rounded_rectangle((x0, y0, x1, y1), radius=r * U, fill=255)
    for nx in (x0, x1):
        d.ellipse((nx - notch * U, S / 2 - notch * U, nx + notch * U, S / 2 + notch * U), fill=0)
    return m


TICKET_ANGLE = 35  # degrees, counter-clockwise (rises to the right like Navi's link)
TICKET = dict(w=500, h=270, r=48, notch=50, stroke=46, gap=26)


def ticket() -> tuple[Image.Image, Image.Image]:
    """(white outline mask, gap mask), both rotated into place."""
    t = TICKET
    s = t["stroke"]
    outer = ticket_shape(t["w"], t["h"], t["r"], t["notch"])
    inner = ticket_shape(t["w"] - 2 * s, t["h"] - 2 * s, max(t["r"] - s, 4), t["notch"] + s)
    ring = ImageChops.subtract(outer, inner)
    # Perforation: dashes across the ticket, a third of the way in.
    d = ImageDraw.Draw(ring)
    px = S / 2 + (t["w"] / 2 - 150) * U
    dw, n = 22, 2  # dash width, number of dashes
    span = (t["h"] / 2 - s - 4) * U
    dash = span * 2 / (n * 1.3)
    step = (span * 2 - dash) / (n - 1)
    for i in range(n):
        y = S / 2 - span + i * step
        d.rounded_rectangle((px - dw / 2 * U, y, px + dw / 2 * U, y + dash), radius=dw / 2 * U, fill=255)
    ring = ring.rotate(TICKET_ANGLE, resample=Image.BICUBIC)
    # Gap: the outline grown by `gap` on every side.
    k = int(t["gap"] * U) * 2 + 1
    gap = ring.filter(ImageFilter.MaxFilter(min(k, 99)))
    while k > 99:  # MaxFilter sizes are capped; apply in passes
        k -= 98
        gap = gap.filter(ImageFilter.MaxFilter(min(k, 99)))
    return ring, gap


def symbol() -> Image.Image:
    """The crystal + ticket on a transparent layer."""
    layer = crystal()
    ring, gap = ticket()
    alpha = ImageChops.subtract(layer.getchannel("A"), gap)
    layer.putalpha(alpha)
    white = Image.new("RGBA", (S, S), WHITE + (255,))
    layer = Image.composite(white, layer, ring)
    return layer


def render(full_bleed: bool, scale: float = 1.0) -> Image.Image:
    """Master image at S x S. full_bleed: square background (no rounded corners);
    scale shrinks the symbol (maskable icons keep it inside the safe zone)."""
    bg = gradient(S).convert("RGBA")
    sym = symbol()
    if scale != 1.0:
        n = int(S * scale)
        small = sym.resize((n, n), Image.LANCZOS)
        sym = Image.new("RGBA", (S, S))
        sym.paste(small, ((S - n) // 2, (S - n) // 2))
    out = Image.alpha_composite(bg, sym)
    if not full_bleed:
        mask = Image.new("L", (S, S))
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=0.225 * S, fill=255)
        out.putalpha(mask)
    return out


def main() -> None:
    (PUBLIC / "icons").mkdir(parents=True, exist_ok=True)
    rounded = render(full_bleed=False)
    square = render(full_bleed=True)
    maskable = render(full_bleed=True, scale=0.78)

    def save(img: Image.Image, size: int, name: str, rgb: bool = False) -> None:
        out = img.resize((size, size), Image.LANCZOS)
        if rgb:
            out = out.convert("RGB")
        out.save(PUBLIC / name, optimize=True)

    save(rounded, 256, "icons/logo-256.png")
    save(rounded, 192, "icons/icon-192.png")
    save(rounded, 512, "icons/icon-512.png")
    save(rounded, 32, "icons/favicon-32.png")
    save(maskable, 512, "icons/icon-maskable-512.png", rgb=True)
    save(square, 180, "apple-touch-icon.png", rgb=True)
    rounded.resize((256, 256), Image.LANCZOS).save(
        PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)]
    )
    print("wrote icons to", PUBLIC)


if __name__ == "__main__":
    main()
