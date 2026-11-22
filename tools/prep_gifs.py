"""Tidy GIFs for the rail spot (ui/gifs.py) and copy them into data/gifs.

    python tools/prep_gifs.py <file.gif | folder> [...] [--out data/gifs]

- Crops every frame to the area any frame uses (plus 2 px), so a small character on a big empty canvas
  doesn't shrink to nothing in the 88 px rail.
- Frame times of 0-10 ms become 100 ms, which is what browsers do; Flutter would play them flat out.
- Keeps transparency (frames are saved with disposal 2, so nothing smears between frames).
"""

import glob
import os
import sys

from PIL import Image

PAD = 2


def frames_of(path):
    im = Image.open(path)
    out = []
    for i in range(getattr(im, "n_frames", 1)):
        im.seek(i)
        d = im.info.get("duration") or 0
        out.append((im.convert("RGBA"), 100 if d <= 10 else d))
    return out


def prep(path, out_dir):
    fr = frames_of(path)
    box = None
    for f, _ in fr:
        b = f.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    if box is None:
        print("  skipped (every frame is empty):", path)
        return
    w, h = fr[0][0].size
    box = (max(0, box[0] - PAD), max(0, box[1] - PAD), min(w, box[2] + PAD), min(h, box[3] + PAD))
    imgs = [f.crop(box) for f, _ in fr]
    dst = os.path.join(out_dir, os.path.basename(path))
    imgs[0].save(dst, save_all=True, append_images=imgs[1:], duration=[d for _, d in fr], loop=0, disposal=2,
                 optimize=False)
    print(f"  {os.path.basename(path)}: {w}x{h} -> {imgs[0].width}x{imgs[0].height}, {len(imgs)} frames")


def main(args):
    out = "data/gifs"
    if "--out" in args:
        i = args.index("--out")
        out = args[i + 1]
        args = args[:i] + args[i + 2:]
    os.makedirs(out, exist_ok=True)
    for a in args:
        for p in sorted(glob.glob(os.path.join(a, "*.gif")) if os.path.isdir(a) else [a]):
            prep(p, out)


if __name__ == "__main__":
    main(sys.argv[1:])
