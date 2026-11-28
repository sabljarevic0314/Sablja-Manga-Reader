"""Generate the app icon (black-and-white manga panels, a sabre behind, a big "S") .

    .venv/Scripts/python tools/make_icon.py

Writes SabljaMangaReaderApp.ico (exe + installer) and the embedded logo in assets.py (tray, window, rail).
Sizes <= 48 px get a simplified drawing. Requires Pillow.
"""

from __future__ import annotations

import base64
import io
import math
import random
import re
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
FONT = Path(r"C:\Windows\Fonts\seguibl.ttf")  # Segoe UI Black

INK, PAPER, GREY = (12, 12, 14, 255), (255, 255, 255, 255), (168, 168, 172, 255)


def _panels(S: int, simple: bool) -> Image.Image:
    """The page behind everything: slanted panels with speed lines, screentone and hatching."""
    k = S / 1024
    page = Image.new("RGBA", (S, S), PAPER)
    P = lambda pts: [(x * k, y * k) for x, y in pts]

    def speed(d):  # focus lines bursting in from the edges
        rnd = random.Random(7)
        cx, cy = 800, 190
        for i in range(70):
            a = 2 * math.pi * (i + rnd.random() * 0.6) / 70
            r0, w = 170 + rnd.random() * 130, 0.008 + rnd.random() * 0.018
            d.polygon(P([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)),
                         (cx + 1200 * math.cos(a - w), cy + 1200 * math.sin(a - w)),
                         (cx + 1200 * math.cos(a + w), cy + 1200 * math.sin(a + w))]), fill=INK)

    def dots(d):  # screentone, heavier towards the bottom
        step = 34
        for row, y in enumerate(range(0, 1060, step)):
            for x in range(0, 1060, step):
                x2 = x + (step // 2 if row % 2 else 0)
                r = 3 + 8 * max(0, min(1, (y - 380) / 640))
                d.ellipse(P([(x2 - r, y - r), (x2 + r, y + r)]), fill=INK)

    def hatch(d):
        for c in range(-1000, 1100, 38):
            d.line(P([(c, 1100), (c + 1100, 0)]), fill=INK, width=max(1, int(11 * k)))

    def black(d):
        d.rectangle([0, 0, S, S], fill=INK)
        for x, y, length in ((40, 900, 250), (70, 975, 300), (170, 990, 240)):
            d.polygon(P([(x, y), (x + length, y - length), (x + 22, y - 8)]), fill=PAPER)

    if simple:
        panels = [([(0, 0), (1024, 0), (1024, 330), (0, 650)], None),
                  ([(0, 700), (1024, 380), (1024, 1024), (0, 1024)], black)]
    else:
        panels = [([(0, 0), (500, 0), (440, 468), (0, 560)], None),
                  ([(536, 0), (1024, 0), (1024, 364), (476, 464)], speed),
                  ([(0, 596), (470, 500), (540, 1024), (0, 1024)], black),
                  ([(506, 493), (1024, 400), (1024, 1024), (576, 1024)], dots)]
    for pts, art in panels:
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).polygon(P(pts), fill=255)
        fill = Image.new("RGBA", (S, S), PAPER)
        if art:
            art(ImageDraw.Draw(fill))
        page.paste(fill, (0, 0), mask)
        ImageDraw.Draw(page).line(P(pts + pts[:2]), fill=INK, width=int((26 if simple else 16) * k), joint="curve")
    return page


def _sabre(S: int, simple: bool) -> Image.Image:
    """A line-art sabre, hilt top-left and tip bottom-right (the corners the S leaves open)."""
    k = S / 1024
    layer = Image.new("RGBA", (2 * S, 2 * S), (0, 0, 0, 0))  # oversized: the flat sword is longer than the tile
    d = ImageDraw.Draw(layer)
    P = lambda x, y: ((1024 + x) * k, (1024 + y) * k)
    W = lambda v: max(1, int(v * k))
    tip, guard = -552, 300
    half, edge = (50, 30) if simple else (40, 17)

    def curve(x):
        return -64 * ((guard - x) / (guard - tip)) ** 2
    xs = list(range(tip + 150, guard + 1, 10))
    blade = ([P(tip, curve(tip) - 14)] + [P(x, curve(x) - half) for x in xs]
             + [P(x, curve(x) + half) for x in reversed(xs)])
    grip = [P(guard + 20, -27), P(guard + 200, -33), P(guard + 200, 33), P(guard + 20, 27)]
    cross = [P(guard - 4, -112), P(guard + 36, -112), P(guard + 36, 112), P(guard - 4, 112)]
    p0, p1, p2 = (guard + 20, 96), (guard + 150, 168), (guard + 214, 24)
    bow = [P(*[(1 - t) ** 2 * p0[i] + 2 * (1 - t) * t * p1[i] + t * t * p2[i] for i in (0, 1)])
           for t in (n / 40 for n in range(41))]

    def outline(pts, width, colour):
        d.line(pts + pts[:2], fill=colour, width=W(width), joint="curve")

    # white halo first so the sword stands off the panels, then the inked parts
    for pts in (blade, grip, cross):
        outline(pts, 2 * edge + 30, PAPER)
    d.line(bow, fill=PAPER, width=W(62), joint="curve")
    d.polygon(blade, fill=PAPER)
    d.polygon([P(tip, curve(tip) - 14)] + [P(x, curve(x)) for x in xs]
              + [P(x, curve(x) + half) for x in reversed(xs)], fill=GREY)
    outline(blade, edge, INK)
    d.line(bow, fill=INK, width=W(30), joint="curve")
    d.polygon(grip, fill=INK)
    if not simple:
        for x in range(guard + 70, guard + 190, 40):
            d.line([P(x - 10, -27), P(x + 12, 27)], fill=PAPER, width=W(12))
    d.polygon(cross, fill=INK)
    for y in (-112, 112):
        d.ellipse([P(guard - 14, y - 30), P(guard + 46, y + 30)], fill=INK)
    d.ellipse([P(guard + 184, -45), P(guard + 260, 45)], fill=INK)
    turned = layer.rotate(45, resample=Image.BICUBIC, center=(S, S))
    return ImageOps.mirror(turned.crop((S // 2, S // 2, S // 2 + S, S // 2 + S)))


def _letter(S: int, simple: bool) -> Image.Image:
    """The big S: black ink, thick white border, black outline, hard drop shadow."""
    k = S / 1024
    font = ImageFont.truetype(str(FONT), int((920 if simple else 850) * k))
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = S / 2, S / 2
    white, edge = (46, 18) if simple else (34, 14)

    def text(dx, colour, grow):
        d.text((x + dx * k, y + dx * k), "S", font=font, anchor="mm", fill=colour,
               stroke_width=int(grow * k), stroke_fill=colour)
    text(24, INK, white + edge)
    text(0, INK, white + edge)
    text(0, PAPER, white)
    text(0, INK, 0)
    return layer


def render(size: int) -> Image.Image:
    simple = size <= 48
    S = max(size * 4, 1024)
    k = S / 1024
    img = _panels(S, simple)
    img.alpha_composite(_sabre(S, simple))
    img.alpha_composite(_letter(S, simple))
    box = [16 * k, 16 * k, S - 16 * k, S - 16 * k]
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=150 * k, fill=255)
    ImageDraw.Draw(img).rounded_rectangle(box, radius=150 * k, outline=INK, width=int((40 if simple else 28) * k))
    img.putalpha(ImageChops.multiply(img.getchannel("A"), mask))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = {s: render(s) for s in sizes}
    frames[256].save(ROOT / "SabljaMangaReaderApp.ico", sizes=[(s, s) for s in sizes],
                     append_images=[frames[s] for s in sizes if s != 256])

    buf = io.BytesIO()
    frames[256].save(buf, "PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    body = "".join(f'    "{b64[i:i + 100]}",\n' for i in range(0, len(b64), 100))
    assets = ROOT / "assets.py"
    text, n = re.subn(r"LOGO_B64 = [\[(]\n.*?\n[\])]\n", lambda m: "LOGO_B64 = [\n" + body + "]\n",
                      assets.read_text(encoding="utf-8"), flags=re.S)
    assert n == 1, "LOGO_B64 block not found"
    assets.write_text(text, encoding="utf-8")

    sheet = Image.new("RGBA", (1024 + 40 + 256 + 20, 1024), (255, 255, 255, 255))
    sheet.alpha_composite(render(1024), (0, 0))
    y = 20
    for s in (256, 64, 48, 32, 24, 16):
        sheet.alpha_composite(frames[s], (1064, y))
        y += s + 20
    sheet.save(ROOT / "tools" / "icon_preview.png")
    print("wrote SabljaMangaReaderApp.ico, assets.py logo, tools/icon_preview.png")


if __name__ == "__main__":
    main()
