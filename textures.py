"""Generated paper / book-cloth textures, so no image files ship with the app."""

from typing import Any, cast

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat, ImageTk

PAPER_RGB = {"Graphite matte": (41, 42, 46), "Ink matte": (23, 24, 27), "Paper": (226, 219, 200)}
PAPER_KIND = {"Graphite matte": "matte", "Ink matte": "matte", "Paper": "matte"}


# ---------------- paper / book-cloth textures ----------------
# Everything here is generated, so the app stays a single self-contained .exe.
_TEX_PIL: dict[tuple[str, int], Image.Image] = {}
_TEX_TK: dict[tuple[str, int], ImageTk.PhotoImage] = {}
_TEX_AVG: dict[str, str] = {}
TEX = 512           # tile edge; big enough that the repeat is not readable


def _octave(size, radius, std, seed):
    """Smooth tonal drift that tiles with no seam and no symmetry.

    A random field is pasted as a 3x3 periodic lattice and then blurred; because
    the source repeats with period `size`, so does the result, so the tile joins
    seamlessly. (Mirroring a blob grid - the old approach - also hides the seam,
    but the reflection makes the noise symmetric, which reads as a damask motif.)
    """
    noise = Image.effect_noise((size, size), 128).convert("L")
    pad = int(radius * 3) + 2
    big = Image.new("L", (size + 2 * pad, size + 2 * pad))
    for y in range(0, size + 2 * pad, size):
        for x in range(0, size + 2 * pad, size):
            big.paste(noise, (x, y))
    tile = big.filter(ImageFilter.GaussianBlur(radius)).crop((pad, pad, pad + size, pad + size))
    sd = ImageStat.Stat(tile).stddev[0] or 1.0
    k = std / sd
    return tile.point(lambda v: max(0, min(255, int(128 + (v - 128) * k))))


def _grain(size, std):
    """Per-pixel paper grain, normalised to a known strength."""
    g = Image.effect_noise((size, size), 9).convert("L")
    sd = ImageStat.Stat(g).stddev[0] or 1.0
    k = std / sd
    return g.point(lambda v: max(0, min(255, int(128 + (v - 128) * k))))


def _weave(size, amp, period, vertical):
    """One direction of a cloth weave: alternating warp/weft threads."""
    im = Image.new("L", (size, size), 128)
    d = ImageDraw.Draw(im)
    for i in range(0, size, period):
        v = 128 + amp if (i // period) % 2 == 0 else 128 - amp
        d.line((i, 0, i, size) if vertical else (0, i, size, i), fill=int(v))
    return im.filter(ImageFilter.GaussianBlur(period * 0.30))


def _tone(rgb, size, layers):
    """Base colour plus a stack of 128-centred noise layers."""
    delta = Image.new("L", (size, size), 128)
    for lay in layers:
        delta = ImageChops.add(delta, lay, scale=1.0, offset=-128)
    return ImageChops.add(Image.new("RGB", (size, size), rgb), delta.convert("RGB"),
                          scale=1.0, offset=-128)


def _matte(rgb, size, seed):
    """Flat matte surface: fine per-pixel grain only, so nothing repeats visibly."""
    return _tone(rgb, size, [_grain(size, 1.7)])


def _cloth(rgb, size, seed):
    """A hardback book-cloth surface: soft drift, a woven weft/warp and paper grain."""
    return _tone(rgb, size, [_octave(size, 12, 1.9, seed), _octave(size, 4, 1.3, seed + 5),
                             _weave(size, 2.0, 4, True), _weave(size, 1.6, 4, False),
                             _grain(size, 1.1)])


def paper_pil(name, size=TEX):
    """The generated tile for a paper name (None when the background is Off)."""
    if name not in PAPER_RGB:
        return None
    key = (name, size)
    if key not in _TEX_PIL:
        make = {"matte": _matte, "cloth": _cloth}.get(PAPER_KIND.get(name, "matte"), _matte)
        _TEX_PIL[key] = make(PAPER_RGB[name], size, 20260 + sum(PAPER_RGB[name]) + len(name) * 7)
    return _TEX_PIL[key]


def paper_tile(master, name, size=TEX):
    """One PhotoImage tile, cached - canvas items need it on every repaint."""
    if paper_pil(name, size) is None:
        return None
    key = (name, size)
    if key not in _TEX_TK:
        _TEX_TK[key] = ImageTk.PhotoImage(paper_pil(name, size), master=master)
    return _TEX_TK[key]


def paper_avg(name):
    """Average colour of a tile as #rrggbb, so solid widget backgrounds blend with it."""
    tile = paper_pil(name)
    if tile is None:
        return None
    if name not in _TEX_AVG:
        px = list(cast(Any, tile.resize((16, 16), Image.Resampling.LANCZOS).getdata()))
        kn = len(px)
        _TEX_AVG[name] = "#%02x%02x%02x" % tuple(sum(c[i] for c in px) // kn for i in range(3))
    return _TEX_AVG[name]
