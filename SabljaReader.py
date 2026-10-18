import os, sys, json, re, time, hashlib, threading, queue, shutil, zipfile, random, html, io, math, base64
from urllib.parse import urljoin, quote_plus
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps, ImageTk, ImageDraw, ImageFont, ImageFilter, ImageChops, ImageStat
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk

try:  # real Chrome/Firefox TLS fingerprint (bypasses many 403s)
    from curl_cffi import requests as cffi
except Exception:
    cffi = None

BASE = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
CACHE = os.path.join(DATA, "cache")
DB_FILE = os.path.join(DATA, "db.json")
SRC_FILE = os.path.join(BASE, "sources.json")
os.makedirs(CACHE, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
IMG_ATTRS = ["data-src", "lazy-src", "data-original", "data-lazy-src", "src"]
PAGE_SIZE = 32
MD_API = "https://api.mangadex.org"

# ---------------- theme (silver on graphite) ----------------
# The chrome colours follow the chosen background, so the flat menu areas sit on the
# same surface as the textured sidebar/reader instead of fighting it. theme_pick()
# swaps these when the Background setting changes.
ROLES = ("BG", "SIDE", "PANEL", "CARD", "CARD_HI", "BTN", "BTN_HI", "LINE", "READER_BG")
PALETTES = {
    "Off": {"BG": "#131417", "SIDE": "#0f1012", "PANEL": "#1b1c20", "CARD": "#222428",
            "CARD_HI": "#2d2f36", "BTN": "#2b2d33", "BTN_HI": "#3a3d45", "LINE": "#32353c",
            "READER_BG": "#0c0c0e"},
    "Graphite matte": {"BG": "#1d1e22", "SIDE": "#1c1d21", "PANEL": "#24252a", "CARD": "#2b2d33",
                       "CARD_HI": "#373941", "BTN": "#2d2f35", "BTN_HI": "#3c3f47", "LINE": "#35383f",
                       "READER_BG": "#1a1b1f"},
    "Ink matte": {"BG": "#101113", "SIDE": "#0f1012", "PANEL": "#17181c", "CARD": "#1e2024",
                  "CARD_HI": "#292b31", "BTN": "#202226", "BTN_HI": "#2e3038", "LINE": "#272a30",
                  "READER_BG": "#0e0e10"},
}
BG, SIDE, PANEL, CARD, CARD_HI = "#131417", "#0f1012", "#1b1c20", "#222428", "#2d2f36"
BTN, BTN_HI, LINE = "#2b2d33", "#3a3d45", "#32353c"
SILVER, SILVER_HI, SILVER_DIM, INK = "#c5cad3", "#e8ebf0", "#7d838e", "#14151a"
TEXT, MUTED, READER_BG = "#e7e9ed", "#8a8f99", "#0c0c0e"
FONT = ("Segoe UI", 12)

MODES = ["Webtoon (vertical)", "Single · left→right", "Single · right→left", "Double · left→right", "Double · right→left"]
ZOOMS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
# paper textures (the "hardback" look) - the names are what Settings shows
PAPERS = ["Off", "Graphite matte", "Ink matte"]
PAPER_RGB = {"Graphite matte": (41, 42, 46), "Ink matte": (23, 24, 27)}
PAPER_KIND = {"Graphite matte": "matte", "Ink matte": "matte"}
PAGE_BORDER = 5     # black contour drawn around a page in the paged modes
PAGE_GAP = 16       # black gutter between the two halves of a double spread
DEFAULTS = {"mode": MODES[0], "dl_delay": 1.0, "dl_order": "Oldest first",
            "dl_dir": os.path.join(BASE, "downloads"), "nsfw": True,
            "show_arrows": True, "paged_guides": True, "paper": "Graphite matte"}

# reading-direction hints shown briefly at the start of every chapter
ARROWS = {"webtoon": "↓   scroll down", "ltr": "→   click the right side / press the right arrow",
          "rtl": "←   click the left side / press the left arrow"}
DL_VIEW_CHIP = "__downloaded__"


def _rot(pts, deg, cx, cy):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]


LOGO_B64 = (
    "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"
    "7Wa+wzLrr5RpushDt4SmI12jDZ1SOOIuGIUwUWoJ6UaT9LugWra9nFLziLZhco4fphbwymExaYRyIxTbcio3EBPRZEcuYE9qnMK7rTMSTPFm7m"
    "CRtbKiUJms6jQuSnFo6CDrURDkE5VNEKG2BZ/YKLyLkBXdKFnxIiJhKdfwUUvKPp5vUecp/IydSQwz+FtsZpr1DBq5ZJ/wlWuIaLuxJDXT5etO"
    "BJCFJq7iH0riddop9WLqeRlMnsG+rvB7nmdIKx7d1hYXXibVLuGsZzOa4812arGKc3k6kh/yLgu5f5wrWE7D4B/u3ECXpF4Ovv1ZqN2Pr+7cG9"
    "j9KzxHW1dgbNpR3EzYhlM5k5iIj3Ii8Fx+xkJaRGjqrOfXCI7lZdxLbMDevKqnjcBs0Q1pJyLIOhpkSa9QBwInUWqU8FtBU7O5lQkFhdObgCV6"
    "KmfUbGpZi5nrSaizmgM5joSbuN1kVE0W8TNeTMRZvANFjZM4iW1IbMFJFCRxXIXQ8LHU3lSV8EEusgVi4ZQoq/Sm/UqgX/7xp37pwm8Lp/yiTP"
    "Q+n0/xBH7MaWhewqkMoAz/XXAHk4zwalbyALczSmIlo4Q928Ib/yCcEZHK6bNXpSsv9z/ncjjaiZI1uZSbLsBj2su3tT2dkqLMTXsQRbvet5Gd"
    "+Bbr+TbruIGdLNVlkDN5KxfzE+A1fJ5Fpq1LBdpJ8wqADgZ4OtAA6o/Cza2UmzZKPOyvs7qEO1a5GASGNXzzLoJ8LEvMNAfzAxocxPcZsEi4AO"
    "5mgqXMYZBTGGacuuHMSDsgJWf4CKs47DaCqIqyZ5VgVS75mHGQ8v587Ymu+l1LbvuJdFpBpQn/sn/XmKTOKQwxzDY0WON0V7RT4GNIOI9XmGKz"
    "9pZf4ysoKEIapNLhVeggFxKP0ue2AMoinVF0Mf66RDjQXYJIZaP+rNegnxrjvJYzqXsnGjYjWcNlwA6cQcKETfNwBGKymli+vejIfPXRu3KMkl"
    "NMlIP3pd4Qeqxryesjbv6hHLQtNcwmBYwzxVnsDvyKOxkKjLY5gfcwTZ9pkJOFsZi5+Jx2EtJcYVl7zzcU8AlniEa5+iFdzkhnsaQ8VfTPHMEu"
    "dNdAqVIH/mrew6koSwzNfn8edYZ4P78Dnsp32GTPlt8rnNrKXexV61TgQWiH7VQFkeBYGOGQP5XtRsgynYzNkNqBre74amV6BzNr12Kc7/As4G"
    "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"
    "8O+qAAAAAElFTkSuQmCC"
)
_LOGO = [None]


def make_icon(size=256):
    """App logo (the crossed-sabres SR badge); falls back to the old drawn logo if decoding fails."""
    try:
        if _LOGO[0] is None:
            _LOGO[0] = Image.open(io.BytesIO(base64.b64decode("".join(LOGO_B64)))).convert("RGBA")
        im = _LOGO[0]
        return im.copy() if size == im.width else im.resize((size, size), Image.LANCZOS)
    except Exception:
        return _make_icon_old(size)


def _make_icon_old(size=256):
    """Old logo: the letters SR with a sabre ("sablja") lying underneath them."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=(12, 13, 17, 255))
    font = None
    for n in ("arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            font = ImageFont.truetype(n, int(size * 0.42))
            break
        except Exception:
            pass
    try:  # lettering, lifted a little to leave room for the sword
        d.text((size / 2, size * 0.35), "SR", font=font, fill=(228, 232, 239, 255), anchor="mm",
               stroke_width=max(1, size // 60), stroke_fill=(228, 232, 239, 255))
    except Exception:
        d.text((size * 0.26, size * 0.16), "SR", fill=(228, 232, 239, 255))
    # ---- the saber ----
    L, tip = size * 0.60, size * 0.075         # blade
    bh, th = size * 0.036, size * 0.020         # blade half-height at guard / at tip
    guard, grip = size * 0.088, size * 0.155
    ang, cx, cy = -12, size * 0.50, size * 0.735
    edge = (238, 242, 248, 255)
    blade = _rot([(0, -bh), (L, -th), (L + tip * 0.7, -th * 0.5), (L + tip, 0),
                  (L + tip * 0.7, th * 0.5), (L, th), (0, bh)], ang, cx, cy)
    d.polygon(blade, fill=(188, 196, 208, 255))
    d.line(_rot([(0, -bh * 0.5), (L, -th * 0.5)], ang, cx, cy), fill=edge, width=max(1, size // 90))
    d.line(_rot([(0, bh), (L, th)], ang, cx, cy), fill=(120, 128, 140, 255), width=max(1, size // 110))
    d.polygon(_rot([(-size * 0.012, -guard), (size * 0.020, -guard * 0.85),
                    (size * 0.020, guard * 0.85), (-size * 0.012, guard)], ang, cx, cy), fill=(128, 134, 145, 255))
    d.polygon(_rot([(-grip, -bh * 0.62), (0, -bh * 0.34), (0, bh * 0.34), (-grip, bh * 0.62)], ang, cx, cy),
              fill=(52, 45, 40, 255))
    for k in range(4):  # grip wrap
        t = -grip * (0.16 + 0.2 * k)
        d.line(_rot([(t, -bh * 0.55), (t, bh * 0.55)], ang, cx, cy), fill=(104, 92, 78, 255), width=max(1, size // 120))
    pr = size * 0.030
    px, py = _rot([(-grip - pr * 0.35, 0)], ang, cx, cy)[0]
    d.ellipse((px - pr, py - pr, px + pr, py + pr), fill=(152, 159, 170, 255))
    return im


# ---------------- paper / book-cloth textures ----------------
# Everything here is generated, so the app stays a single self-contained .exe.
_TEX_PIL, _TEX_TK, _TEX_AVG = {}, {}, {}
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
        make = {"matte": _matte, "cloth": _cloth}.get(PAPER_KIND.get(name), _matte)
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
        px = list(tile.resize((16, 16), Image.LANCZOS).getdata())
        kn = len(px)
        _TEX_AVG[name] = "#%02x%02x%02x" % tuple(sum(c[i] for c in px) // kn for i in range(3))
    return _TEX_AVG[name]


def theme_pick(paper):
    """Adopt the palette that belongs with a background.

    Returns the {old colour: new colour} pairs, so an already-built window can be
    recoloured in place instead of being torn down and rebuilt.
    """
    global BG, SIDE, PANEL, CARD, CARD_HI, BTN, BTN_HI, LINE, READER_BG
    cur = {"BG": BG, "SIDE": SIDE, "PANEL": PANEL, "CARD": CARD, "CARD_HI": CARD_HI,
           "BTN": BTN, "BTN_HI": BTN_HI, "LINE": LINE, "READER_BG": READER_BG}
    want = PALETTES.get(paper) or PALETTES["Off"]
    if all(cur[r] == want[r] for r in ROLES):
        return {}
    BG, SIDE, PANEL, CARD, CARD_HI = want["BG"], want["SIDE"], want["PANEL"], want["CARD"], want["CARD_HI"]
    BTN, BTN_HI, LINE = want["BTN"], want["BTN_HI"], want["LINE"]
    READER_BG = want["READER_BG"]
    return {cur[r].lower(): want[r] for r in ROLES if cur[r] != want[r]}


def retint(widget, mapping):
    """Recolour a built widget tree in place. Tk/CTk only - canvas items repaint themselves."""
    if not mapping:
        return
    for w in widget.winfo_children():
        for prop in ("fg_color", "hover_color", "bg", "fg"):
            try:
                old = w.cget(prop)
            except Exception:
                continue
            if not isinstance(old, str):
                continue
            new = mapping.get(old.lower())
            if new is None and old == "transparent":
                new = "transparent"   # re-resolve "transparent" against the new parent colour
            if new is not None:
                try:
                    w.configure(**{prop: new})
                except Exception:
                    pass
        retint(w, mapping)


def make_icon_file(path):
    if not os.path.exists(path):
        make_icon(256).save(path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])


# ---------------- storage ----------------
def load_db():
    try:
        with open(DB_FILE, encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        db = {}
    for k, v in dict(bookmarks=[], progress={}, last=None, folders=[], set={}, downloads=[], ratings={}).items():
        db.setdefault(k, v)
    return db


DB = load_db()


def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(DB, f, indent=1, ensure_ascii=False)


def S(k):
    v = DB["set"].get(k, DEFAULTS[k])
    if k == "paper" and v not in PAPERS:   # older builds saved "Grey paper"/"Dark blue paper"
        v = DEFAULTS["paper"]
    return v


def pkey(m):
    return f'{m["source"]}|{m["url"]}'


def safe(s):
    return re.sub(r'[\\/:*?"<>|]+', "_", s).strip(" .") or "untitled"


def cache_path(url):
    return os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest())


def dl_path(m, i, ch):
    src = SOURCES.get(m["source"])
    return os.path.join(S("dl_dir"), safe(src.name if src else m["source"]), safe(m["title"]),
                        f"{i + 1:04d} - {safe(ch['title'])}.cbz")


# ---------------- local library (downloaded .cbz) ----------------
_JOB_ID = [0]


def next_job_id():
    _JOB_ID[0] += 1
    return f"{int(time.time())}-{_JOB_ID[0]}"


def manga_dl_dir(m):
    src = SOURCES.get(m["source"])
    return os.path.join(S("dl_dir"), safe(src.name if src else m["source"]), safe(m["title"]))


def dl_records(m):
    k = pkey(m)
    return [r for r in DB["downloads"] if r.get("key") == k]


def scan_dl_dir(m):
    """Files on disk, keyed by chapter index (from the '0001 - Title.cbz' name). Survives a lost db."""
    out = {}
    d = manga_dl_dir(m)
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            mt = re.match(r"(\d+)\s*-\s*(.*)\.cbz$", fn, re.I)
            if mt:
                out[int(mt.group(1)) - 1] = os.path.join(d, fn)
    return out


def local_chapters(m):
    """{chapter index: absolute .cbz path} - db records first, disk scan as a fallback."""
    out = scan_dl_dir(m)
    for r in dl_records(m):
        p = r.get("path")
        if p and os.path.exists(p):
            out[r.get("i")] = p
    return out


def dl_record(m, i, ch=None):
    recs = dl_records(m)
    if ch:
        u = ch.get("url")
        for r in recs:
            if u and r.get("ch", {}).get("url") == u:
                return r
    return next((r for r in recs if r.get("i") == i), None)


def source_by_name(name):
    return next((s for s in SOURCES.values() if s.name == name), None)


def hidden_ids():
    """Source ids the user switched off in Settings."""
    return set(DB["set"].get("hidden") or [])


def source_hidden(sid):
    return sid in hidden_ids()


def get_rating(m):
    """{'score': 1-10, 'note': str, ...} for a manga, or None."""
    return DB["ratings"].get(pkey(m))


def source_label(m):
    """Human name of a manga's source (falls back to the id stored in a disk folder)."""
    src = SOURCES.get(m.get("source"))
    return src.name if src else (m.get("name") or m.get("source") or "Local")


def dl_folder_for(m):
    return os.path.join(S("dl_dir"), safe(source_label(m)), safe(m.get("title", "untitled")))


def disk_chapters(m):
    """{chapter index: .cbz path} straight from the download folder - no db required."""
    out, d = {}, dl_folder_for(m)
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            mt = re.match(r"(\d+)\s*-\s*(.*)\.cbz$", fn, re.I)
            if mt:
                out[int(mt.group(1)) - 1] = os.path.join(d, fn)
    return out


def local_chapters_any(m):
    """local_chapters, but also works for a manga that was never bookmarked (no url/db key)."""
    out = local_chapters(m)
    return out or disk_chapters(m)


def local_path(m, i, ch=None):
    """The .cbz for chapter index i, whether it is in the db index or only on disk."""
    r = dl_record(m, i, ch)
    if r and r.get("path") and os.path.exists(r["path"]):
        return r["path"]
    p = disk_chapters(m).get(i)
    return p if p and os.path.exists(p) else None


def downloaded_manga():
    """Every manga you have .cbz files for - bookmarked or not (index first, then a disk sweep)."""
    groups = {}
    for r in DB["downloads"]:
        m = r.get("m") or {}
        p = r.get("path") or ""
        if not (m.get("title") and p and os.path.exists(p)):
            continue
        e = groups.setdefault((source_label(m), m["title"]),
                              {"source": m.get("source", ""), "url": m.get("url", ""), "title": m["title"],
                               "cover": m.get("cover", ""), "name": source_label(m)})
        if not e["cover"]:
            e["cover"] = m.get("cover", "")
    root, titles = S("dl_dir"), {t for _, t in groups}
    if os.path.isdir(root):
        for sname in sorted(os.listdir(root)):
            sdir = os.path.join(root, sname)
            if not os.path.isdir(sdir):
                continue
            for title in sorted(os.listdir(sdir)):
                tdir = os.path.join(sdir, title)
                if (sname, title) in groups or title in titles or not os.path.isdir(tdir):
                    continue
                try:
                    if not any(f.lower().endswith(".cbz") for f in os.listdir(tdir)):
                        continue
                except OSError:
                    continue
                src = source_by_name(sname)
                groups[(sname, title)] = {"source": src.id if src else "", "url": "", "title": title,
                                          "cover": "", "name": sname}
    return list(groups.values())


class _Resp:
    __slots__ = ("content",)

    def __init__(self, content):
        self.content = content


class LocalZip:
    """Serves page bytes straight from a downloaded .cbz so the reader works offline."""
    name = "Local"
    nsfw = False

    def get(self, url):
        _, path, member = url.split("|", 2)
        with zipfile.ZipFile(path) as z:
            return _Resp(z.read(member))


LOCAL = LocalZip()


def cbz_pages(path):
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
    return [f"cbz|{path}|{n}" for n in sorted(names)]


# ---------------- sources ----------------
def pick(el, sel):
    return el if not sel or sel == "self" else el.select_one(sel)


def txt(el):
    if el is not None and el.name == "meta":
        return (el.get("content") or "").strip()
    return el.get_text(" ", strip=True) if el else ""


def attr(el, names):
    if el is None:
        return ""
    if el.name == "meta":
        return (el.get("content") or "").strip()
    for n in names:
        v = el.get(n)
        if v and not v.startswith("data:"):
            return v.strip().split(" ")[0] if n == "srcset" else v.strip()
    return ""


def href(el):
    if el is None:
        return ""
    return el.get("href") or (el.find("a").get("href") if el.find("a") else "") or ""


class Source:
    def __init__(self, d):
        self.d, self.id, self.name = d, d["id"], d["name"]
        self.api = d.get("api")
        self.base = d.get("base_url", "").rstrip("/")
        self.nsfw = bool(d.get("nsfw"))
        self._tl = threading.local()
        self._genres = None

    # ---- http ----
    def _session(self):
        s = getattr(self._tl, "s", None)
        if s is None:
            s = cffi.Session(impersonate=self.d.get("impersonate", "chrome124")) if cffi else requests.Session()
            self._tl.s = s
        return s

    def get(self, url, referer=None):
        h = dict(UA)
        h["Referer"] = referer or (self.base + "/")
        h.update(self.d.get("headers", {}))
        # per-source overrides saved in Settings (User-Agent / Cookie) - used for Cloudflare sites
        h.update((DB["set"].get("headers") or {}).get(self.id) or {})
        r = self._session().get(url, headers=h, timeout=25)
        r.raise_for_status()
        return r

    def soup(self, url):
        return BeautifulSoup(self.get(url).text, "html.parser")

    def abs(self, u):
        return urljoin(self.base + "/", u) if u else ""

    # ---- capabilities ----
    def kinds(self):
        return ["popular", "latest"] if self.api else [k for k in ("popular", "latest") if k in self.d]

    def can_search(self):
        return bool(self.api) or "search" in self.d

    def genres(self):
        """[(label, value)] or []. Called from a worker thread."""
        if self.api == "mangadex":
            if self._genres is None:
                j = requests.get(MD_API + "/manga/tag", headers=UA, timeout=25).json()
                tags = [(t["attributes"]["name"].get("en", "?"), t["id"]) for t in j["data"]
                        if t["attributes"].get("group") in ("genre", "theme")]
                self._genres = sorted(tags)
            return self._genres
        if self.api == "webtoons":
            return [("Trending", "trending"), ("Popular", "popular"),
                    ("Originals", "originals"), ("Canvas", "canvas")]
        return [tuple(g) for g in self.d.get("genres", [])] if "genre" in self.d else []

    # ---- listing ----
    def listing(self, kind, page=1, query="", genre=""):
        if self.api == "mangadex":
            return self._md_listing(kind, page, query, genre)
        if self.api == "webtoons":
            return self._wt_listing(kind, page, query, genre)
        key = "genre" if genre and kind != "search" else kind
        c = self.d.get(key)
        if not c:
            return []
        if key in ("latest", "genre"):
            c = {**self.d.get("popular", {}), **c}
        if c.get("single_page") and page > 1:
            return []
        url = self.abs(c["url"].format(page=page, query=quote_plus(query), offset=(page - 1) * PAGE_SIZE, genre=genre))
        out, seen = [], set()
        for it in self.soup(url).select(c["item"]):
            t = pick(it, c.get("title"))
            link = pick(it, c.get("link") or c.get("title"))
            title = txt(t) or (t.get("title", "") if t else "")
            u = self.abs(href(link))
            if not title or not u or u in seen:
                continue
            seen.add(u)
            cover = self.abs(attr(pick(it, c.get("cover", "img")), c.get("cover_attr", IMG_ATTRS)))
            out.append({"title": title, "url": u, "cover": cover, "source": self.id})
        return out

    def _chapters(self, soup, c):
        chs, seen = [], set()
        if not c.get("item"):
            return chs
        pat = re.compile(c["title_pattern"]) if c.get("title_pattern") else None
        for it in soup.select(c["item"]):
            u = self.abs(href(it))
            if not u or u in seen:
                continue
            seen.add(u)
            t = txt(it) or it.get("title", "Chapter")
            if pat:
                m = pat.search(t)
                if m and m.group(1).strip():
                    t = m.group(1).strip()
            chs.append({"title": t, "url": u})
        return chs

    def details(self, url):
        if self.api == "mangadex":
            return self._md_details(url)
        if self.api == "webtoons":
            return self._wt_details(url)
        d, soup = self.d.get("details", {}), self.soup(url)
        sel = lambda k: soup.select_one(d[k]) if d.get(k) else None
        cover = self.abs(attr(sel("cover"), d.get("cover_attr", IMG_ATTRS))) if d.get("cover") else ""
        c = self.d.get("chapters") or {}
        chs = []
        if c.get("list_path"):
            try:
                chs = self._chapters(self.soup(url.rstrip("/").rsplit("/", 1)[0] + c["list_path"]), c)
            except Exception:
                chs = []
        if not chs:
            chs = self._chapters(soup, c)
        if c.get("newest_first", True):
            chs.reverse()
        return {"title": txt(sel("title")), "description": txt(sel("description")), "cover": cover, "chapters": chs}

    def pages(self, url):
        if self.api == "mangadex":
            return self._md_pages(url)
        if self.api == "webtoons":
            return self._wt_pages(url)
        p = self.d["pages"]
        if p.get("url_suffix"):
            url = url.rstrip("/") + p["url_suffix"]
        out, seen = [], set()
        if p.get("script_regex"):  # image list stored in a <script> array
            m = re.search(p["script_regex"], self.get(url).text, re.S)
            for u in re.findall(r"""['"](https?://[^'"]+)['"]""", m.group(1)) if m else []:
                if u not in seen:
                    seen.add(u)
                    out.append(u)
            return out
        for i in self.soup(url).select(p["image"]):
            u = self.abs(attr(i, p.get("attr", IMG_ATTRS)))
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out

    # ---- MangaDex (official API, no scraping) ----
    def _md(self, path, **params):
        r = requests.get(MD_API + path, params=params, headers=UA, timeout=25)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _md_title(a):
        t = a.get("title") or {}
        return t.get("en") or next(iter(t.values()), "Untitled")

    def _md_cover(self, x, size=".256.jpg"):
        for r in x.get("relationships", []):
            if r["type"] == "cover_art" and r.get("attributes"):
                return f"https://uploads.mangadex.org/covers/{x['id']}/{r['attributes']['fileName']}{size}"
        return ""

    def _md_listing(self, kind, page, query, genre):
        p = {"limit": PAGE_SIZE, "offset": (page - 1) * PAGE_SIZE, "includes[]": ["cover_art"],
             "contentRating[]": self._md_ratings(), "hasAvailableChapters": "true",
             "availableTranslatedLanguage[]": ["en"]}
        if kind == "search" and query:
            p["title"] = query
            p["order[relevance]"] = "desc"
        elif kind == "latest":
            p["order[latestUploadedChapter]"] = "desc"
        else:
            p["order[followedCount]"] = "desc"
        if genre:
            p["includedTags[]"] = [genre]
        return [{"title": self._md_title(x["attributes"]), "url": f"https://mangadex.org/title/{x['id']}",
                 "cover": self._md_cover(x), "source": self.id} for x in self._md("/manga", **p)["data"]]

    def _md_ratings(self):
        return ["safe", "suggestive", "erotica", "pornographic"] if S("nsfw") else ["safe", "suggestive"]

    def _md_feed(self, mid, langs):
        """One pass over a manga's chapter feed. langs=None means 'every language'."""
        chs, seen, off = [], set(), 0
        while True:
            p = {"order[chapter]": "asc", "limit": 500, "offset": off, "includeExternalUrl": 0,
                 "contentRating[]": self._md_ratings()}
            if langs:
                p["translatedLanguage[]"] = langs
            j = self._md(f"/manga/{mid}/feed", **p)
            for c in j["data"]:
                ca = c["attributes"]
                if not ca.get("pages"):
                    continue
                num = ca.get("chapter")
                key = num if num is not None else (None, ca.get("translatedLanguage"), c["id"])
                if key in seen:
                    continue
                seen.add(key)
                title = f"Chapter {num}" if num else "Oneshot"
                if ca.get("title"):
                    title += f" – {ca['title']}"
                chs.append({"title": title, "url": f"https://mangadex.org/chapter/{c['id']}"})
            off += 500
            if off >= j.get("total", 0):
                break
        return chs

    def _md_details(self, url):
        mid = url.rstrip("/").split("/")[-1]
        x = self._md(f"/manga/{mid}", **{"includes[]": ["cover_art"]})["data"]
        a = x["attributes"]
        chs = self._md_feed(mid, ["en"])
        if not chs:  # lots of titles only have chapters in other languages - don't show an empty list
            chs = self._md_feed(mid, None)
        return {"title": self._md_title(a), "description": (a.get("description") or {}).get("en", ""),
                "cover": self._md_cover(x, ".512.jpg"), "chapters": chs}

    def _md_pages(self, url):
        j = self._md(f"/at-home/server/{url.rstrip('/').split('/')[-1]}")
        ch = j["chapter"]
        files, folder = (ch["dataSaver"], "data-saver") if ch.get("dataSaver") else (ch["data"], "data")
        return [f"{j['baseUrl']}/{folder}/{ch['hash']}/{f}" for f in files]

    # ---- WEBTOON (official site; listing/viewer are HTML, episodes come from the mobile API) ----
    WT_RANKS = ("trending", "popular", "originals", "canvas")

    @staticmethod
    def _wt_day():
        return ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[time.localtime().tm_wday]

    def _wt_listing(self, kind, page=1, query="", genre=""):
        if genre in self.WT_RANKS:
            if page > 1:
                return []
            url = f"{self.base}/en/ranking/{genre}"
        elif kind == "search":
            if page > 1:
                return []
            url = f"{self.base}/en/search?keyword={quote_plus(query)}"
        elif kind == "latest":
            if page > 1:
                return []
            url = f"{self.base}/en/originals/{self._wt_day()}?sortOrder=UPDATE"
        else:
            if page > len(self.WT_RANKS):
                return []
            url = f"{self.base}/en/ranking/{self.WT_RANKS[page - 1]}"
        out, seen = [], set()
        for a in self.soup(url).select(".webtoon_list li a"):
            u = self.abs(a.get("href"))
            if not u or u in seen:
                continue
            seen.add(u)
            t = a.select_one(".title") or a.select_one(".subj")
            title = txt(t) or a.get("title", "")
            if not title:
                continue
            img = a.select_one("img")
            out.append({"title": title, "url": u,
                        "cover": attr(img, ["data-src", "src"]) if img else "", "source": self.id})
        return out

    def _wt_details(self, url):
        soup = self.soup(url)
        t = soup.select_one("h1.subj") or soup.select_one("h3.subj") or soup.select_one("h1")
        desc = soup.select_one("#_asideDetail p.summary") or soup.select_one("p.summary")
        cov = soup.select_one("meta[property='og:image']")
        return {"title": txt(t), "description": txt(desc), "cover": attr(cov, []) if cov else "",
                "chapters": self._wt_chapters(url)}

    def _wt_chapters(self, url):
        m = re.search(r"title_no=(\d+)", url or "")
        if not m:
            return []
        kind = "canvas" if "/canvas/" in url else "webtoon"
        api = f"https://m.webtoons.com/api/v1/{kind}/{m.group(1)}/episodes?pageSize=99999"
        if kind == "canvas":
            api += "&readingLanguageCode=en"
        j = self.get(api, referer="https://m.webtoons.com/").json()
        eps = ((j.get("result") or {}).get("episodeList")) or []
        chs = []
        for e in eps:
            u = e.get("viewerLink") or ""
            if not u:
                continue
            chs.append({"title": html.unescape(e.get("episodeTitle") or "Episode"), "url": self.abs(u)})
        chs.reverse()  # the API returns newest first
        return chs

    def _wt_pages(self, url):
        out, seen = [], set()
        for i in self.soup(url).select("div#_imageList img, #_imageList img"):
            u = attr(i, ["data-url", "data-src", "src"])
            if u and u not in seen:
                seen.add(u)
                out.append(self.abs(u))
        return out


SOURCES = {}


def rebuild_sources():
    SOURCES.clear()
    if not os.path.exists(SRC_FILE):
        with open(SRC_FILE, "w", encoding="utf-8") as f:
            json.dump({"sources": []}, f, indent=2)
    try:
        with open(SRC_FILE, encoding="utf-8") as f:
            data = json.load(f).get("sources", [])
    except Exception:
        data = []
    for d in data:
        try:
            SOURCES[d["id"]] = Source(d)
        except Exception:
            pass


# ---------------- background work ----------------
Q = queue.Queue()
NET_POOL = ThreadPoolExecutor(4)
IMG_POOL = ThreadPoolExecutor(8)
PAGE_POOL = ThreadPoolExecutor(6)
WT_MAX_INFLIGHT = 4        # pages downloading at once in webtoon mode
WT_AHEAD = 3               # pages kept loaded below the viewport
WT_BEHIND = 1              # ... and above it
WT_KEEP = 1                # extra pages kept before an image is dropped from memory
WT_MAX_PX = 14000000       # cap for one page's Tk image (~56 MB): tall strips are the memory hogs
_PH = None


def page_box():
    """A 1x1 transparent image. A label needs an image for width/height to be in pixels, so this is
    what lets a page keep its exact box (and the scroll position) before/after its real image loads."""
    global _PH
    if _PH is None:
        _PH = tk.PhotoImage(width=1, height=1)
    return _PH


def img_size(url):
    """(width, height) of a page without decoding its pixels - cache file or downloaded .cbz member."""
    try:
        if url.startswith("cbz|"):
            _, path, member = url.split("|", 2)
            with zipfile.ZipFile(path) as z:
                with Image.open(io.BytesIO(z.read(member))) as im:
                    return im.size
        p = cache_path(url)
        if os.path.exists(p):
            with Image.open(p) as im:
                return im.size
    except Exception:
        pass
    return (0, 0)



def bg(fn, cb):
    def w():
        try:
            res = (fn(), None)
        except Exception as e:
            res = (None, e)
        Q.put((cb, res))
    NET_POOL.submit(w)


def load_img(src, url, cb, size=None, width=None, height=None, pool=None, alive=None):
    """Download (cached) + decode + resize in a worker; cb(PIL image or None) runs on the UI thread.

    Returns True when the work was actually queued - callers count in-flight jobs from this, so a
    request that cannot be made never leaves a slot occupied forever.
    """
    if not src or not url:
        return False

    def w():
        if alive and not alive():
            return
        im = None
        new_file = False
        try:
            p = cache_path(url)
            if not os.path.exists(p):
                data = src.get(url).content
                tmp = f"{p}.{threading.get_ident()}.part"  # two pages of the same url must not share a temp file
                try:
                    with open(tmp, "wb") as f:
                        f.write(data)
                    os.replace(tmp, p)
                finally:
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
                new_file = True
            if alive and not alive():
                return
            im = Image.open(p)
            if width:
                th = height or max(1, int(im.height * width / float(im.width)))
                try:
                    im.draft("RGB", (width * 2, th * 2))
                except Exception:
                    pass
                im = im.convert("RGB")
                im = im.resize((width, th), Image.BICUBIC)
            elif size:
                try:
                    im.draft("RGB", (size[0] * 2, size[1] * 2))
                except Exception:
                    pass
                im = ImageOps.fit(im.convert("RGB"), size)
            else:
                im = im.convert("RGB")
        except Exception:
            im = None
            if new_file:  # an html error page saved as an image must not sit in the cache and fail forever
                try:
                    if os.path.getsize(cache_path(url)) < 1024:
                        os.remove(cache_path(url))
                except OSError:
                    pass
        Q.put((lambda r, e: cb(r), (im, None)))

    (pool or IMG_POOL).submit(w)
    return True


# ---------------- download manager (one CBZ per chapter, slow + polite) ----------------
DL_Q = queue.Queue()
JOBS = []


def _ext(b):
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[:3] == b"GIF":
        return "gif"
    return "jpg"


def run_job(job):
    src, m, ch = SOURCES[job["m"]["source"]], job["m"], job["ch"]
    job["state"] = "getting pages"
    urls = src.pages(ch["url"])
    job["total"] = len(urls)
    dest = job["path"]
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
            for i, u in enumerate(urls):
                if job["state"] == "cancelled":
                    raise InterruptedError
                job["state"] = "downloading"
                cp, data = cache_path(u), None
                if os.path.exists(cp):
                    data = open(cp, "rb").read()  # already viewed in the reader: no request, no delay
                else:
                    for attempt in range(3):
                        try:
                            data = src.get(u).content
                            break
                        except Exception as e:
                            if attempt == 2:
                                raise
                            time.sleep(15 if "429" in str(e) else 3 * (attempt + 1))
                    time.sleep(S("dl_delay") * random.uniform(0.7, 1.4))
                z.writestr(f"{i + 1:03d}.{_ext(data)}", data)
                job["done"] = i + 1
        os.replace(tmp, dest)
        job["state"] = "done"
        time.sleep(max(2.0, S("dl_delay") * 2))  # pause between chapters
    except InterruptedError:
        job["state"] = "cancelled"
        try:
            os.remove(tmp)
        except Exception:
            pass
    except Exception as e:
        job["state"] = "error: " + str(e)[:50]
        try:
            os.remove(tmp)
        except Exception:
            pass


def dl_worker():
    while True:
        job = DL_Q.get()
        if job["state"] == "cancelled":
            continue
        try:
            run_job(job)
        except Exception as e:
            job["state"] = "error: " + str(e)[:50]


threading.Thread(target=dl_worker, daemon=True).start()


# ---------------- ui helpers ----------------
def clear(f):
    for w in f.winfo_children():
        w.destroy()


def set_img(widget, im, size=None):
    if im is None:
        return
    try:
        ci = ctk.CTkImage(im, size=size or im.size)
        widget.configure(image=ci, text="")
        widget.image = ci
    except Exception:
        pass


def btn(parent, text, cmd=None, primary=False, **kw):
    if primary:
        kw.setdefault("fg_color", SILVER); kw.setdefault("hover_color", SILVER_HI); kw.setdefault("text_color", INK)
    else:
        kw.setdefault("fg_color", BTN); kw.setdefault("hover_color", BTN_HI); kw.setdefault("text_color", TEXT)
    kw.setdefault("corner_radius", 8); kw.setdefault("height", 34); kw.setdefault("font", FONT)
    return ctk.CTkButton(parent, text=text, command=cmd, **kw)


def menu(parent, values, cmd, **kw):
    kw.setdefault("width", 160)
    return ctk.CTkOptionMenu(parent, values=values, command=cmd, fg_color=BTN, button_color=BTN_HI, button_hover_color=SILVER_DIM,
                             dropdown_fg_color=PANEL, dropdown_hover_color=BTN_HI, text_color=TEXT, dropdown_text_color=TEXT,
                             font=FONT, dropdown_font=FONT, corner_radius=8, height=34, **kw)


def entry(parent, **kw):
    return ctk.CTkEntry(parent, fg_color=CARD, border_color=LINE, text_color=TEXT, placeholder_text_color=MUTED,
                        corner_radius=8, height=36, font=FONT, **kw)


def style_ttk():
    st = ttk.Style()
    try:
        st.theme_use("clam")
    except Exception:
        pass
    st.configure("S.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=34, borderwidth=0,
                 font=("Segoe UI", 11), relief="flat")
    st.map("S.Treeview", background=[("selected", CARD_HI)], foreground=[("selected", SILVER_HI)])
    st.configure("S.Treeview.Heading", background=PANEL, foreground=MUTED, relief="flat", font=("Segoe UI", 10, "bold"))
    st.layout("S.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])


# ---------------- app ----------------
# ---------------- randomizer ----------------
def random_pick(avoid):
    """Worker thread: one random title from a random enabled source (popular listing, random page)."""
    srcs = [s for s in SOURCES.values() if (S("nsfw") or not s.nsfw) and not source_hidden(s.id) and s.kinds()]
    random.shuffle(srcs)
    err = None
    for s in srcs[:6]:
        kind = "popular" if "popular" in s.kinds() else s.kinds()[0]
        top = 100 if s.api == "mangadex" else (len(s.WT_RANKS) if s.api == "webtoons" else 20)
        page = random.randint(1, top)
        while True:
            try:
                items = [x for x in s.listing(kind, page) if x["url"] not in avoid]
            except Exception as e:
                err, items = e, []
                if page == 1:
                    break
            if items:
                return random.choice(items)
            if page == 1:
                break
            page = max(1, page // 2)   # past the last page -> retry closer to the start
    if err:
        raise err
    return None


# ---------------- lofi radio ----------------
class Lofi:
    """Internet-radio player (needs `pip install miniaudio`). Streams are found through the free
    radio-browser.info directory (tag "lofi", MP3 only), with SomaFM Groove Salad as a fallback."""
    API = ["https://de1.api.radio-browser.info", "https://de2.api.radio-browser.info",
           "https://nl1.api.radio-browser.info", "https://at1.api.radio-browser.info"]
    QUERY = "/json/stations/search?tag=lofi&codec=MP3&hidebroken=true&order=votes&reverse=true&limit=25"
    FALLBACK = [("SomaFM Groove Salad", "https://ice1.somafm.com/groovesalad-128-mp3"),
                ("SomaFM Groove Salad", "https://ice2.somafm.com/groovesalad-128-mp3")]

    def __init__(self):
        self.state, self.name, self.i = "off", "", 0       # state: off | connecting | on | error
        self.stations, self.on_change = None, None
        self._gen, self._dev, self._src = 0, None, None
        self._lock = threading.Lock()

    @staticmethod
    def available():
        try:
            import miniaudio  # noqa: F401
            return True
        except Exception:
            return False

    def _notify(self):
        if self.on_change:
            Q.put((self.on_change, ()))

    def _close(self):
        with self._lock:
            dev, src, self._dev, self._src = self._dev, self._src, None, None
        for o, fn in ((dev, "stop"), (dev, "close"), (src, "close")):
            try:
                if o is not None:
                    getattr(o, fn)()
            except Exception:
                pass

    def _stations(self):
        if self.stations:
            return self.stations
        out = []
        for base in self.API:
            try:
                r = requests.get(base + self.QUERY, headers={"User-Agent": "SabljaReader/1.0"}, timeout=8)
                r.raise_for_status()
                for s in r.json():
                    u = (s.get("url_resolved") or "").strip()
                    if u.startswith("http") and s.get("lastcheckok", 1):
                        out.append(((s.get("name") or "Lofi radio").strip() or "Lofi radio", u))
                if out:
                    break
            except Exception:
                continue
        self.stations = out + self.FALLBACK
        return self.stations

    @staticmethod
    def _probe(url):
        """Quick reachability check so a dead station fails in seconds instead of hanging."""
        try:
            with requests.get(url, headers={"User-Agent": "SabljaReader/1.0"}, stream=True, timeout=(6, 6)) as r:
                ct = (r.headers.get("content-type") or "").lower()
                return r.status_code < 400 and ("mpeg" in ct or "mp3" in ct)
        except Exception:
            return False

    def _run(self, gen, step):
        import miniaudio
        self._close()
        st = self._stations()
        for k in range(len(st)):
            if gen != self._gen:
                return
            idx = (self.i + step + k) % len(st)
            name, url = st[idx]
            if not self._probe(url):
                continue
            src = dev = None
            try:
                src = miniaudio.IceCastClient(url)
                dev = miniaudio.PlaybackDevice()
                dev.start(miniaudio.stream_any(src, src.audio_format))
            except Exception:
                for o in (dev, src):
                    try:
                        o and o.close()
                    except Exception:
                        pass
                continue
            with self._lock:
                ok = gen == self._gen
                if ok:
                    self._dev, self._src = dev, src
            if not ok:
                for o in (dev, src):
                    try:
                        o.close()
                    except Exception:
                        pass
                return
            self.i, self.name, self.state = idx, name, "on"
            self._notify()
            return
        if gen == self._gen:
            self.state, self.name = "error", ""
            self._notify()

    def start(self, step=0):
        """False when the miniaudio package is missing."""
        if not self.available():
            return False
        self._gen += 1
        self.state = "connecting"
        self._notify()
        threading.Thread(target=self._run, args=(self._gen, step), daemon=True).start()
        return True

    def stop(self):
        self._gen += 1
        self.state, self.name = "off", ""
        threading.Thread(target=self._close, daemon=True).start()
        self._notify()


LOFI = Lofi()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        theme_pick(S("paper"))          # the saved background decides the chrome palette
        self.configure(fg_color=BG)
        self.title("Sablja Reader")
        self.geometry("1280x800")
        self.minsize(1000, 640)
        ico = os.path.join(DATA, "sablja2.ico")   # new name so the new logo replaces an old cached icon
        try:
            make_icon_file(ico)
            self.after(300, lambda: self.iconbitmap(ico))  # CTk sets its own icon at ~200ms, so set ours after
        except Exception:
            try:
                self.iconphoto(True, ImageTk.PhotoImage(make_icon(64)))
            except Exception:
                pass
        style_ttk()
        self.cur, self.back, self.reader, self.cur_detail, self.b = None, "Library", None, None, None
        self.rtok = self.dtok = self.rgen = 0
        self.lib_folder, self.sel, self.desc, self.desc_full = "All", set(), True, False
        self.genre_map, self.kind_btns, self.zoom_job = {}, {}, None
        self.genre_menu, self.btok = None, 0
        self.stok, self.search_src = 0, None
        self._seen_titles = set()
        self.rand_mode, self._rand_open, self.rdm_tok = False, False, 0
        self.rand_hist, self.rand_i, self.rand_seen = [], -1, set()
        LOFI.on_change = self.lofi_refresh
        rebuild_sources()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # The sidebar is a canvas, not a frame: that is the only way the paper texture can show
        # through the menu (a CTk frame always paints a flat colour on top of it).
        self.side = tk.Canvas(self, width=210, highlightthickness=0, bd=0, bg=SIDE)
        self.side.grid(row=0, column=0, sticky="ns")
        self.nav_order = ["Library", "Rating", "Sources", "Search", "Randomizer", "Downloads", "Settings"]
        self.nav, self._nav_items, self._hover, self._logo_img = {}, {}, None, None
        self.side.bind("<Configure>", lambda e: self.paint_side())
        self.after(40, self.paint_side)

        self.main = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.views = {n: ctk.CTkFrame(self.main, fg_color="transparent", corner_radius=0)
                      for n in self.nav_order + ["Details", "Reader"]}
        self.build_library(); self.build_rating(); self.build_sources(); self.build_search(); self.build_downloads()
        self.build_settings(); self.build_details(); self.build_reader()
        self.refresh = {"Library": self.refresh_library, "Rating": self.refresh_rating, "Sources": self.refresh_sources,
                        "Settings": self.refresh_settings, "Search": self.refresh_search}
        self.bind_all("<MouseWheel>", self.on_wheel, add="+")
        self.bind_all("<Key>", self.on_key, add="+")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.show("Library")
        self.after(60, self.poll)
        self.after(500, self.watch)

    # ----- plumbing -----
    def poll(self):
        t0, n = time.perf_counter(), 0
        while n < 6 and time.perf_counter() - t0 < 0.015:
            try:
                cb, res = Q.get_nowait()
            except queue.Empty:
                break
            try:
                cb(*res)
            except Exception:
                pass
            n += 1
        self.after(12 if not Q.empty() else 40, self.poll)

    def watch(self):
        """Infinite scroll for Sources + live refresh for Downloads."""
        try:
            b = self.b
            if self.cur == "Sources" and b and b.get("has_more") and not b.get("loading") and not b.get("err"):
                top, bot = self.browse_scroll._parent_canvas.yview()
                if bot > 0.88:
                    self.load_more()
            self.sync_done_jobs()
            if self.cur == "Downloads":
                self.refresh_downloads()
        except Exception:
            pass
        self.after(350, self.watch)

    def close(self):
        LOFI.stop()
        if self.cur == "Reader":
            self.save_reader()
        self.destroy()

    def show(self, name):
        if self.cur == "Reader" and name != "Reader":
            self.save_reader()
            self.rtok += 1
            self.rgen += 1
        if self.cur:
            self.views[self.cur].pack_forget()
        self.cur = name
        self.views[name].pack(fill="both", expand=True)
        self.nav_hl(name)
        if name in self.refresh:
            self.refresh[name]()

    # ----- sidebar (canvas so the paper texture shows) -----
    def paint_side(self):
        c = self.side
        try:
            w, h = c.winfo_width() or 210, max(c.winfo_height() or 800, 320)
        except Exception:
            return
        c.delete("all")
        paper = S("paper")
        c.configure(bg=paper_avg(paper) or SIDE)
        tile = paper_tile(self, paper)
        if tile:
            ts = tile.width()
            for y in range(0, h + ts, ts):
                for x in range(0, w + ts, ts):
                    c.create_image(x, y, anchor="nw", image=tile)
        try:
            self._logo_img = ImageTk.PhotoImage(make_icon(128).resize((42, 42), Image.LANCZOS))
            c.create_image(18, 26, anchor="nw", image=self._logo_img)
        except Exception:
            pass
        c.create_text(68, 47, anchor="w", text="Sablja\nReader", fill=SILVER_HI, justify="left",
                      font=("Segoe UI", 15, "bold"))
        self._nav_items = {}
        for i, n in enumerate(self.nav_order):
            y = 122 + i * 44
            tag = f"nav:{n}"
            rect = c.create_rectangle(12, y, w - 12, y + 38, fill="", outline="", tags=(tag,))
            txt = c.create_text(28, y + 19, anchor="w", text=n, fill=MUTED, font=("Segoe UI", 13), tags=(tag,))
            self._nav_items[n] = (rect, txt)
            self.nav[n] = True
            c.tag_bind(tag, "<Button-1>", lambda e, n=n: self.nav_click(n))
            c.tag_bind(tag, "<Enter>", lambda e, n=n: self.nav_hover(n, True))
            c.tag_bind(tag, "<Leave>", lambda e, n=n: self.nav_hover(n, False))
        ly = max(h - 84, 122 + len(self.nav_order) * 44 + 8)
        c.create_rectangle(12, ly, w - 12, ly + 38, fill=PANEL, outline=LINE, tags=("lofi",))
        self._lofi_txt = c.create_text(28, ly + 19, anchor="w", text="", fill=MUTED, font=("Segoe UI", 12), tags=("lofi",))
        self._lofi_sub = c.create_text(28, ly + 48, anchor="w", text="", fill=SILVER_DIM, font=("Segoe UI", 9))
        self._lofi_skip = c.create_text(w - 26, ly + 19, anchor="e", text="\u23ed", fill=SILVER, font=("Segoe UI", 14),
                                        tags=("lofi_next",), state="hidden")
        c.tag_bind("lofi", "<Button-1>", lambda e: self.lofi_toggle())
        c.tag_bind("lofi_next", "<Button-1>", lambda e: LOFI.start(1))
        for tg in ("lofi", "lofi_next"):
            c.tag_bind(tg, "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind(tg, "<Leave>", lambda e: c.configure(cursor=""))
        self.lofi_refresh()
        self.nav_hl(self.cur or "Library")

    def nav_hover(self, n, on):
        self._hover = n if on else None
        try:
            self.side.configure(cursor="hand2" if on else "")
        except Exception:
            pass
        self.nav_hl(self.cur or "Library")

    def nav_hl(self, name):
        if name in ("Details", "Reader") and self.rand_mode:
            name = "Randomizer"
        for n, (rect, txt) in self._nav_items.items():
            on, hov = n == name, n == self._hover
            self.side.itemconfigure(rect, fill=(PANEL if (on or hov) else ""))
            self.side.itemconfigure(txt, fill=SILVER_HI if on else (TEXT if hov else MUTED))

    def title_label(self, parent, text):
        return ctk.CTkLabel(parent, text=text, font=("Segoe UI", 26, "bold"), text_color=SILVER_HI, anchor="w")

    def cols_for(self, extra=0, card=162):
        return max(2, (self.main.winfo_width() - 80 - extra) // card)

    # ----- cards -----
    def grid_cards(self, parent, items, cols, cb, start=0, small=False, ctx=None):
        def step(lo):
            try:
                if not parent.winfo_exists():
                    return
            except Exception:
                return
            for i in range(lo, min(lo + 6, len(items))):
                self.make_card(parent, items[i], start + i, cols, cb, small, ctx)
            if lo + 6 < len(items):
                self.after(10, lambda: step(lo + 6))
        step(0)

    def make_card(self, parent, m, i, cols, cb, small=False, ctx=None):
        iw, ih = (104, 148) if small else (138, 196)
        card = ctk.CTkFrame(parent, width=iw + 12, corner_radius=12, fg_color=CARD)
        card.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="n")
        img = ctk.CTkLabel(card, text="", width=iw, height=ih, corner_radius=8, fg_color=PANEL)
        img.pack(padx=6, pady=(6, 2))
        t = m["title"] if len(m["title"]) < 46 else m["title"][:43] + "…"
        ttl = ctk.CTkLabel(card, text=t, wraplength=iw - 6, height=34 if small else 44, font=("Segoe UI", 11 if small else 12), text_color=TEXT)
        ttl.pack(padx=6, pady=(0, 6))
        for w in (card, img, ttl):
            w.bind("<Button-1>", lambda e, m=m: cb(m))
            w.bind("<Enter>", lambda e, c=card: c.configure(fg_color=CARD_HI))
            w.bind("<Leave>", lambda e, c=card: c.configure(fg_color=CARD))
            if ctx:
                w.bind("<Button-3>", lambda e, m=m: ctx(e, m))
            w.configure(cursor="hand2")
        load_img(SOURCES.get(m["source"]), m["cover"], lambda im, l=img: set_img(l, im, (iw, ih)), size=(iw, ih))

    # ----- library -----
    def build_library(self):
        v = self.views["Library"]
        top = ctk.CTkFrame(v, fg_color="transparent")
        top.pack(fill="x", padx=28, pady=(24, 6))
        self.title_label(top, "Library").pack(side="left")
        self.cont_btn = btn(top, "", self.continue_reading, primary=True, height=38)
        self.cont_btn.pack(side="right")
        ctk.CTkLabel(v, text="Tip: right-click a cover for folders, bookmarks and more.", anchor="w",
                     text_color=SILVER_DIM, font=("Segoe UI", 11)).pack(fill="x", padx=30, pady=(0, 4))
        self.chip_row = ctk.CTkFrame(v, fg_color="transparent")
        self.chip_row.pack(fill="x", padx=28, pady=(0, 8))
        self.lib_scroll = ctk.CTkScrollableFrame(v, fg_color="transparent")
        self.lib_scroll.pack(fill="both", expand=True, padx=18, pady=(0, 12))

    def popup(self, e, entries):
        mn = tk.Menu(self, tearoff=0, bg=PANEL, fg=TEXT, activebackground=BTN_HI, activeforeground=SILVER_HI, bd=0)
        for lab, fn in entries:
            if lab == "-":
                mn.add_separator()
            elif isinstance(fn, list):
                sub = tk.Menu(mn, tearoff=0, bg=PANEL, fg=TEXT, activebackground=BTN_HI, activeforeground=SILVER_HI, bd=0)
                for l2, f2 in fn:
                    sub.add_command(label=l2, command=f2)
                mn.add_cascade(label=lab, menu=sub)
            else:
                mn.add_command(label=lab, command=fn)
        try:
            mn.tk_popup(e.x_root, e.y_root)
        finally:
            mn.grab_release()

    def refresh_library(self):
        l = DB["last"]
        if l:
            p = DB["progress"].get(l["key"], {})
            self.cont_btn.configure(text=f'▶  Continue: {l["manga"]["title"][:26]} · {p.get("title", "")[:20]}', state="normal")
        else:
            self.cont_btn.configure(text="Nothing read yet", state="disabled")
        bms = DB["bookmarks"]
        if self.lib_folder not in ["All", "Unsorted", DL_VIEW_CHIP] + DB["folders"]:
            self.lib_folder = "All"
        dls = downloaded_manga()
        clear(self.chip_row)
        chips = [("All", f"All ({len(bms)})"), (DL_VIEW_CHIP, f"⬇ Downloaded ({len(dls)})")]
        if DB["folders"]:
            chips.append(("Unsorted", "Unsorted"))
        chips += [(f, f) for f in DB["folders"]]
        for key, label in chips:
            on = key == self.lib_folder
            c = btn(self.chip_row, label, lambda k=key: self.set_folder(k), primary=on, height=30, corner_radius=15, width=20)
            c.pack(side="left", padx=(0, 6))
            if key in DB["folders"]:
                c.bind("<Button-3>", lambda e, k=key: self.popup(e, [("Rename folder", lambda: self.rename_folder(k)),
                                                                      ("Delete folder", lambda: self.delete_folder(k))]))
        btn(self.chip_row, "+ Folder", lambda: self.new_folder(), height=30, corner_radius=15, width=20, fg_color="transparent",
            text_color=SILVER_DIM, hover_color=PANEL).pack(side="left")
        clear(self.lib_scroll)
        if self.lib_folder == "All":
            shown = list(bms)
        elif self.lib_folder == DL_VIEW_CHIP:
            shown = dls
        elif self.lib_folder == "Unsorted":
            shown = [b for b in bms if not b.get("folder")]
        else:
            shown = [b for b in bms if b.get("folder") == self.lib_folder]
        if not shown:
            msg = ("Nothing downloaded yet.\nUse the ⬇ Download button on a manga's page."
                   if self.lib_folder == DL_VIEW_CHIP else
                   "Nothing here yet.\nOpen a manga from Sources or Search and press Bookmark.\n"
                   "Right-click a cover to move it into a folder.")
            ctk.CTkLabel(self.lib_scroll, text=msg, font=("Segoe UI", 14), text_color=MUTED).pack(pady=90)
        else:
            self.grid_cards(self.lib_scroll, shown, self.cols_for(), self.open_manga,
                            ctx=self.dl_ctx if self.lib_folder == DL_VIEW_CHIP else self.lib_ctx)

    # ----- rating -----
    def build_rating(self):
        v = self.views["Rating"]
        top = ctk.CTkFrame(v, fg_color="transparent")
        top.pack(fill="x", padx=28, pady=(24, 6))
        self.title_label(top, "Rating").pack(side="left")
        self.rate_info = ctk.CTkLabel(top, text="", text_color=MUTED, anchor="e")
        self.rate_info.pack(side="right")
        ctk.CTkLabel(v, text="Right-click a cover (Library, Sources, Search or a manga page) and pick "
                             '"★ Rate / comment" to give it 1-10 and write a note.',
                     anchor="w", text_color=SILVER_DIM, font=("Segoe UI", 11)).pack(fill="x", padx=30, pady=(0, 8))
        self.rate_scroll = ctk.CTkScrollableFrame(v, fg_color="transparent")
        self.rate_scroll.pack(fill="both", expand=True, padx=18, pady=(0, 12))

    def refresh_rating(self):
        clear(self.rate_scroll)
        items = sorted(DB["ratings"].items(), key=lambda kv: (-(kv[1].get("score") or 0),
                                                             (kv[1].get("m") or {}).get("title", "").lower()))
        n = len(items)
        avg = (sum(v.get("score") or 0 for _, v in items) / n) if n else 0
        self.rate_info.configure(text=f"{n} rated · average {avg:.1f}/10" if n else "")
        if not items:
            ctk.CTkLabel(self.rate_scroll, text="Nothing rated yet.\nRight-click a manga and choose "
                                                '"★ Rate / comment".',
                         font=("Segoe UI", 14), text_color=MUTED, justify="left").pack(pady=90)
            return
        cols = self.cols_for(card=250)
        for i, (key, r) in enumerate(items):
            self.make_rate_card(self.rate_scroll, r, i, cols)

    def make_rate_card(self, parent, r, i, cols):
        m = r.get("m") or {"source": "", "url": "", "title": "?", "cover": ""}
        iw, ih = 104, 146
        card = ctk.CTkFrame(parent, width=iw + 152, corner_radius=12, fg_color=CARD)
        card.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="nw")
        cov = ctk.CTkLabel(card, text="", width=iw, height=ih, corner_radius=8, fg_color=PANEL)
        cov.pack(side="left", padx=(6, 8), pady=6)
        right = ctk.CTkFrame(card, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=6)
        ctk.CTkLabel(right, text=m.get("title", "?"), font=("Segoe UI", 12, "bold"), text_color=TEXT,
                     wraplength=138, justify="left", anchor="w").pack(fill="x")
        ctk.CTkLabel(right, text=f"{r.get('score') or 0}/10", font=("Segoe UI", 20, "bold"), text_color=SILVER_HI,
                     anchor="w").pack(fill="x", pady=(2, 0))
        note = (r.get("note") or "").strip()
        if note:
            ctk.CTkLabel(right, text=note[:150] + ("…" if len(note) > 150 else ""), font=("Segoe UI", 11),
                         text_color=MUTED, wraplength=138, justify="left", anchor="nw").pack(fill="x", pady=(4, 0))
        for w in (card, cov, right):
            w.bind("<Button-1>", lambda e, m=m: self.open_manga(m))
            w.bind("<Enter>", lambda e, c=card: c.configure(fg_color=CARD_HI))
            w.bind("<Leave>", lambda e, c=card: c.configure(fg_color=CARD))
            w.bind("<Button-3>", lambda e, m=m: self.popup(e, [("Open", lambda: self.open_manga(m)),
                                                               ("Change rating", lambda: self.rate_manga(m)),
                                                               ("Remove rating", lambda: self.remove_rating(m))]))
            w.configure(cursor="hand2")
        load_img(SOURCES.get(m.get("source")), m.get("cover", ""), lambda im, l=cov: set_img(l, im, (iw, ih)), size=(iw, ih))

    def rate_manga(self, m):
        cur = get_rating(m) or {}
        win = ctk.CTkToplevel(self)
        win.title("Rate / comment")
        win.geometry("540x410")
        win.configure(fg_color=BG)
        ctk.CTkLabel(win, text=m.get("title", "?"), font=("Segoe UI", 16, "bold"), text_color=SILVER_HI,
                     wraplength=490, justify="left", anchor="w").pack(fill="x", padx=22, pady=(20, 0))
        ctk.CTkLabel(win, text="Your score (1-10)", text_color=MUTED, anchor="w").pack(fill="x", padx=22, pady=(14, 0))
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(4, 0))
        val = ctk.CTkLabel(row, text="", font=("Segoe UI", 22, "bold"), text_color=SILVER_HI, width=66, anchor="w")
        val.pack(side="left")
        var = tk.IntVar(value=int(cur.get("score") or 7))

        def upd(v):
            var.set(int(round(float(v))))
            val.configure(text=f"{var.get()}/10")

        sl = ctk.CTkSlider(row, from_=1, to=10, number_of_steps=9, width=330, progress_color=SILVER,
                           button_color=SILVER_HI, button_hover_color="white", fg_color=BTN, command=upd)
        sl.pack(side="left", padx=10)
        sl.set(var.get())
        val.configure(text=f"{var.get()}/10")
        ctk.CTkLabel(win, text="Comment (optional)", text_color=MUTED, anchor="w").pack(fill="x", padx=22, pady=(16, 0))
        box = ctk.CTkTextbox(win, fg_color=CARD, border_color=LINE, border_width=1, text_color=TEXT, wrap="word",
                             font=("Segoe UI", 12), corner_radius=8)
        box.pack(fill="both", expand=True, padx=22, pady=(4, 10))
        box.insert("1.0", cur.get("note") or "")
        row2 = ctk.CTkFrame(win, fg_color="transparent")
        row2.pack(fill="x", padx=22, pady=(0, 16))

        def save():
            DB["ratings"][pkey(m)] = {"m": {k: m.get(k, "") for k in ("source", "url", "title", "cover")},
                                      "score": var.get(), "note": box.get("1.0", "end").strip(), "ts": int(time.time())}
            save_db()
            win.destroy()
            self.after_rating()

        btn(row2, "Save", save, primary=True, width=110).pack(side="right", padx=(8, 0))
        btn(row2, "Cancel", win.destroy, width=90).pack(side="right")
        if cur:
            btn(row2, "Remove rating", lambda: (self.remove_rating(m), win.destroy()), width=120).pack(side="left")
        win.transient(self)
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()

    def remove_rating(self, m):
        DB["ratings"].pop(pkey(m), None)
        save_db()
        self.after_rating()

    def after_rating(self):
        if self.cur == "Rating":
            self.refresh_rating()
        self.show_details_rating()

    def show_details_rating(self):
        m = (self.cur_detail or (None, None))[0]
        if not m or not hasattr(self, "d_rate"):
            return
        r = get_rating(m) or {}
        self.d_rate.configure(text=f"★ {r['score']}/10" if r.get("score") else "★ Rate")

    def dl_ctx(self, e, m):
        """Right-click menu for the Downloaded view (works even when the manga isn't bookmarked)."""
        entries = [("Open", lambda: self.open_manga(m)), ("Rate / comment…", lambda: self.rate_manga(m))]
        if m.get("url"):
            entries += [("☆ Bookmark", lambda: self.add_bm(m)),
                        ("Move to folder", [("None (Unsorted)", lambda: self.move_to(m, ""))] +
                         [(f, lambda f=f: self.move_to(m, f)) for f in DB["folders"]] +
                         [("New folder…", lambda: self.new_folder(m))])]
        entries += [("-", None),
                    ("Open download folder", lambda: self.open_dir(dl_folder_for(m))),
                    ("Delete downloaded chapters", lambda: self.delete_manga_dl(m))]
        self.popup(e, entries)

    def delete_manga_dl(self, m):
        chs = local_chapters_any(m)
        if not chs:
            return
        if not messagebox.askyesno("Delete downloads",
                                   f"Delete all {len(chs)} downloaded chapter file(s) for\n{m.get('title', '?')}?"):
            return
        paths = set(chs.values())
        for p in paths:
            try:
                os.remove(p)
            except Exception:
                pass
        DB["downloads"][:] = [r for r in DB["downloads"] if r.get("path") not in paths]
        save_db()
        self.refresh_library()

    def set_folder(self, k):
        self.lib_folder = k
        self.refresh_library()

    def lib_ctx(self, e, m):
        moves = [("None (Unsorted)", lambda: self.move_to(m, ""))] + [(f, lambda f=f: self.move_to(m, f)) for f in DB["folders"]]
        moves.append(("New folder…", lambda: self.new_folder(m)))
        self.popup(e, [("Open", lambda: self.open_manga(m)), ("Rate / comment…", lambda: self.rate_manga(m)),
                       ("Move to folder", moves), ("-", None),
                       ("Remove from library", lambda: self.remove_bm(m))])

    def card_ctx(self, e, m):
        """Right-click menu for manga cards in Sources / Search."""
        bm = self.find_bm(m)
        moves = [("None (Unsorted)", lambda: self.move_to(m, ""))]
        moves += [(("· " if bm and bm.get("folder") == f else "") + f, lambda f=f: self.move_to(m, f)) for f in DB["folders"]]
        moves.append(("New folder…", lambda: self.new_folder(m)))
        if bm:
            entries = [("Open", lambda: self.open_manga(m)), ("Rate / comment…", lambda: self.rate_manga(m)),
                       ("Move to folder", moves), ("-", None),
                       ("★ Remove bookmark", lambda: self.remove_bm(m))]
        else:
            entries = [("Open", lambda: self.open_manga(m)), ("Rate / comment…", lambda: self.rate_manga(m)),
                       ("☆ Bookmark", lambda: self.add_bm(m)),
                       ("☆ Bookmark in folder", moves)]
        self.popup(e, entries)

    def find_bm(self, m):
        return next((b for b in DB["bookmarks"] if b["source"] == m["source"] and b["url"] == m["url"]), None)

    def add_bm(self, m, folder=""):
        if self.find_bm(m):
            return
        DB["bookmarks"].append({**{k: m[k] for k in ("source", "url", "title", "cover")}, "folder": folder})
        save_db()
        if self.cur == "Library":
            self.refresh_library()

    def move_to(self, m, folder):
        b = self.find_bm(m)
        if b is None:  # not bookmarked yet: filing it implies adding it
            self.add_bm(m, folder)
            return
        b["folder"] = folder
        save_db()
        if self.cur == "Library":
            self.refresh_library()

    def remove_bm(self, m):
        b = self.find_bm(m)
        if b is not None:
            DB["bookmarks"].remove(b)
            save_db()
            if self.cur == "Library":
                self.refresh_library()

    def new_folder(self, m=None):
        name = ctk.CTkInputDialog(text="Folder name:", title="New folder").get_input()
        name = (name or "").strip()
        if not name or name in ("All", "Unsorted"):
            return
        if name not in DB["folders"]:
            DB["folders"].append(name)
        if m:
            self.move_to(m, name)
        save_db()
        self.refresh_library()

    def rename_folder(self, old):
        name = (ctk.CTkInputDialog(text=f'Rename "{old}" to:', title="Rename folder").get_input() or "").strip()
        if not name or name in DB["folders"] or name in ("All", "Unsorted"):
            return
        DB["folders"][DB["folders"].index(old)] = name
        for b in DB["bookmarks"]:
            if b.get("folder") == old:
                b["folder"] = name
        if self.lib_folder == old:
            self.lib_folder = name
        save_db()
        self.refresh_library()

    def delete_folder(self, name):
        DB["folders"].remove(name)
        for b in DB["bookmarks"]:
            if b.get("folder") == name:
                b["folder"] = ""
        save_db()
        self.refresh_library()

    def continue_reading(self):
        if DB["last"]:
            self.open_manga(DB["last"]["manga"], resume=True)

    # ----- sources -----
    def build_sources(self):
        v = self.views["Sources"]
        v.grid_columnconfigure(1, weight=1)
        v.grid_rowconfigure(0, weight=1)
        self.src_list = ctk.CTkScrollableFrame(v, width=170, fg_color=PANEL, corner_radius=12)
        self.src_list.grid(row=0, column=0, sticky="ns", padx=(18, 10), pady=18)
        right = ctk.CTkFrame(v, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", pady=18, padx=(0, 18))
        self.src_title = ctk.CTkLabel(right, text="Pick a source", font=("Segoe UI", 22, "bold"), text_color=SILVER_HI, anchor="w")
        self.src_title.pack(fill="x", padx=4)
        bar = ctk.CTkFrame(right, fg_color="transparent")
        bar.pack(fill="x", pady=(8, 2))
        self.q_entry = entry(bar, placeholder_text="Search in this source…", width=260)
        self.q_entry.pack(side="left")
        self.q_entry.bind("<Return>", lambda e: self.browse("search"))
        btn(bar, "Search", lambda: self.browse("search"), primary=True, width=80).pack(side="left", padx=8)
        self.filter_row = ctk.CTkFrame(bar, fg_color="transparent")
        self.filter_row.pack(side="left", padx=(10, 0))
        self.bstatus = ctk.CTkLabel(right, text="", text_color=MUTED, anchor="w")
        self.bstatus.pack(fill="x", padx=6)
        ctk.CTkLabel(right, text="Tip: right-click a cover to bookmark or file it.", anchor="w",
                     text_color=SILVER_DIM, font=("Segoe UI", 11)).pack(fill="x", padx=6)
        self.browse_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.browse_scroll.pack(fill="both", expand=True)

    def refresh_sources(self):
        clear(self.src_list)
        shown = [s for s in SOURCES.values() if (S("nsfw") or not s.nsfw) and not source_hidden(s.id)]
        if not shown:
            ctk.CTkLabel(self.src_list, text="No sources.\nCheck sources.json\nor unhide them in Settings", text_color=MUTED,
                         justify="left").pack(pady=20)
        for s in shown:
            b = self.b and self.b["src"] is s
            ctk.CTkButton(self.src_list, text=s.name + ("  18+" if s.nsfw else ""), anchor="w", height=36, corner_radius=8,
                          fg_color=BTN if b else "transparent", text_color=SILVER_HI if b else TEXT, hover_color=BTN_HI,
                          font=FONT, command=lambda s=s: self.select_source(s)).pack(fill="x", pady=1)

    def select_source(self, src, query=""):
        self.btok += 1
        self.b = {"src": src, "tok": 0, "loading": False, "has_more": False}
        self.src_title.configure(text=src.name + ("   (untested)" if src.d.get("untested") else ""))
        self.q_entry.delete(0, "end")
        if query:
            self.q_entry.insert(0, query)
        clear(self.filter_row)
        self.kind_btns, self.genre_map, self.genre_menu = {}, {}, None
        names = {"popular": "Popular", "latest": "Latest"}
        if len(src.kinds()) > 1:
            for k in src.kinds():
                bt = btn(self.filter_row, names[k], lambda k=k: self.set_kind(k), width=76, height=34)
                bt.pack(side="left", padx=(0, 6))
                self.kind_btns[k] = bt
        self.refresh_sources()
        tok = self.btok
        bg(src.genres, lambda r, e, tok=tok: self.genres_ready(tok, r, e))
        self.browse("search" if query else "popular")

    def genres_ready(self, tok, r, e):
        if e or not r or tok != self.btok or not self.b:
            return
        self.genre_map = dict(r)
        self.genre_menu = menu(self.filter_row, ["All genres"] + [g[0] for g in r], self.on_genre, width=150)
        self.genre_menu.pack(side="left", padx=(6, 0))

    def set_kind(self, k):
        if self.genre_menu:
            self.genre_menu.set("All genres")
        self.q_entry.delete(0, "end")
        self.browse(k)

    def on_genre(self, label):
        g = self.genre_map.get(label, "")
        k = self.b.get("kind", "popular")
        self.q_entry.delete(0, "end")
        self.browse("popular" if k == "search" else k, g)

    def browse(self, kind, genre=""):
        b = self.b
        if not b:
            return
        src = b["src"]
        q = self.q_entry.get().strip() if kind == "search" else ""
        if kind == "search":
            if not src.can_search():
                self.bstatus.configure(text="This source has no search.")
                return
            if not q:
                return
        b.update(kind=kind, query=q, genre=genre, page=1, n=0, tok=b["tok"] + 1, loading=False, has_more=True, err=None,
                 seen=set(), cols=self.cols_for(190))
        for k, bt in self.kind_btns.items():
            on = k == kind
            bt.configure(fg_color=SILVER if on else BTN, text_color=INK if on else TEXT, hover_color=SILVER_HI if on else BTN_HI)
        self.bstatus.configure(text="")
        clear(self.browse_scroll)
        self.holder = ctk.CTkFrame(self.browse_scroll, fg_color="transparent")
        self.holder.pack(anchor="w")
        self.footer = ctk.CTkLabel(self.browse_scroll, text="", text_color=MUTED)
        self.footer.pack(pady=16)
        self.load_more()

    def load_more(self):
        b = self.b
        if b["loading"] or not b["has_more"]:
            return
        b["loading"], tok = True, b["tok"]
        self.footer.configure(text="Loading…")
        bg(lambda: b["src"].listing(b["kind"], b["page"], b["query"], b["genre"]), lambda r, e: self.more_done(tok, r, e))

    def more_done(self, tok, r, e):
        b = self.b
        if tok != b["tok"]:
            return
        b["loading"] = False
        if e:
            b["err"] = True
            self.footer.configure(text=f"Error: {str(e)[:110]}   (click to retry)", cursor="hand2")
            self.footer.bind("<Button-1>", lambda ev: (b.update(err=None), self.load_more()))
            return
        new = [x for x in r if x["url"] not in b["seen"]]
        b["seen"].update(x["url"] for x in new)
        if not new:
            b["has_more"] = False
            self.footer.configure(text="End of results" if b["n"] else "No results")
            return
        self.grid_cards(self.holder, new, b["cols"], self.open_manga, start=b["n"], ctx=self.card_ctx)
        b["n"] += len(new)
        b["page"] += 1
        self.footer.configure(text="")

    # ----- global search -----
    def build_search(self):
        v = self.views["Search"]
        top = ctk.CTkFrame(v, fg_color="transparent")
        top.pack(fill="x", padx=28, pady=(24, 10))
        self.title_label(top, "Search").pack(side="left", padx=(0, 22))
        self.sq = entry(top, placeholder_text="Search every source…", width=340)
        self.sq.pack(side="left")
        self.sq.bind("<Return>", lambda e: self.run_search())
        btn(top, "Search", self.run_search, primary=True, width=90).pack(side="left", padx=8)
        self.search_map = {}
        self.search_pick = menu(top, ["All sources"], self.on_search_src, width=170)
        self.search_pick.pack(side="left", padx=4)
        self.sres = ctk.CTkScrollableFrame(v, fg_color="transparent")
        self.sres.pack(fill="both", expand=True, padx=18, pady=(0, 12))

    def searchable(self):
        return [s for s in SOURCES.values()
                if s.can_search() and (S("nsfw") or not s.nsfw) and not source_hidden(s.id)]

    def refresh_search(self):
        vals = ["All sources"] + sorted(s.name for s in self.searchable())
        self.search_map = {s.name: s.id for s in self.searchable()}
        try:
            self.search_pick.configure(values=vals)
            if self.search_pick.get() not in vals:
                self.search_pick.set("All sources")
        except Exception:
            pass

    def on_search_src(self, _value=""):
        if self.sq.get().strip():
            self.run_search()

    def run_search(self):
        q = self.sq.get().strip()
        if not q:
            return
        clear(self.sres)
        self.stok += 1
        tok = self.stok
        pick = self.search_pick.get() if hasattr(self, "search_pick") else "All sources"
        want = self.search_map.get(pick)
        self._seen_titles = set()
        srcs = [s for s in self.searchable() if not want or s.id == want]
        if not srcs:
            ctk.CTkLabel(self.sres, text="No searchable source selected — check Settings.", text_color=MUTED,
                         font=("Segoe UI", 14)).pack(pady=60)
            return
        for src in srcs:
            sec = ctk.CTkFrame(self.sres, corner_radius=12, fg_color=PANEL)
            sec.pack(fill="x", padx=6, pady=6)
            hd = ctk.CTkLabel(sec, text=f"{src.name}  ·  searching…", font=("Segoe UI", 14, "bold"), text_color=SILVER, anchor="w")
            hd.pack(fill="x", padx=14, pady=(10, 4))
            bg(lambda src=src: src.listing("search", 1, q), lambda r, e, src=src, sec=sec, hd=hd: self.search_done(tok, src, sec, hd, r, e, q))

    def filter_results(self, q, items):
        """Stricter search: every query word must appear in the title, and drop cross-source duplicates."""
        toks = [t for t in re.findall(r"[a-z0-9]+", q.lower()) if len(t) > 1] or [q.lower()]
        out = []
        for x in items:
            t = x["title"].lower()
            if not all(tok in t for tok in toks):
                continue
            key = re.sub(r"[^a-z0-9]+", "", t)
            if key in self._seen_titles:
                continue
            self._seen_titles.add(key)
            out.append(x)
        return out

    def search_done(self, tok, src, sec, hd, r, e, q):
        try:
            if tok != self.stok or not sec.winfo_exists():
                return
            if e:
                hd.configure(text=f"{src.name}  ·  unavailable ({str(e)[:60]})", text_color=MUTED)
                return
            r = self.filter_results(q, r or [])
            if not r:
                hd.configure(text=f"{src.name}  ·  no matching results", text_color=MUTED)
                return
            hd.configure(text=f"{src.name}  ·  {len(r)} results")
            grid = ctk.CTkFrame(sec, fg_color="transparent")
            grid.pack(fill="x", padx=8, pady=(0, 6))
            cols = max(3, (self.main.winfo_width() - 120) // 124)
            self.grid_cards(grid, r[:cols * 2 if len(r) > cols else cols], cols, self.open_manga, small=True,
                            ctx=self.card_ctx)
            if len(r) > cols:
                btn(sec, "See all in " + src.name + " →", lambda: (self.show("Sources"), self.select_source(src, q)),
                    height=30, width=20, fg_color="transparent", text_color=SILVER, hover_color=BTN).pack(anchor="w", padx=12, pady=(0, 10))
        except Exception:
            pass

    # ----- downloads view -----
    def build_downloads(self):
        v = self.views["Downloads"]
        top = ctk.CTkFrame(v, fg_color="transparent")
        top.pack(fill="x", padx=28, pady=(24, 10))
        self.title_label(top, "Downloads").pack(side="left")
        btn(top, "Open folder", lambda: self.open_dir(S("dl_dir")), width=100).pack(side="right")
        btn(top, "Clear finished", self.clear_jobs, width=110).pack(side="right", padx=8)
        btn(top, "Delete file", self.delete_dl, width=96).pack(side="right", padx=(0, 8))
        btn(top, "Cancel all", self.cancel_jobs, width=90).pack(side="right")
        ctk.CTkLabel(v, text="One .cbz per chapter, kept on disk and remembered between sessions. "
                             "The reader reuses saved chapters instead of downloading them again — even offline. "
                             "Double-click a row to open its folder.",
                     anchor="w", justify="left", wraplength=980, text_color=SILVER_DIM,
                     font=("Segoe UI", 11)).pack(fill="x", padx=28, pady=(0, 6))
        box = ctk.CTkFrame(v, fg_color=CARD, corner_radius=12)
        box.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        self.dtree_dl = ttk.Treeview(box, columns=("m", "c", "s"), show="headings", style="S.Treeview")
        for c, t, w in (("m", "Manga", 320), ("c", "Chapter", 320), ("s", "Status", 200)):
            self.dtree_dl.heading(c, text=t, anchor="w")
            self.dtree_dl.column(c, width=w, anchor="w")
        sb = ctk.CTkScrollbar(box, command=self.dtree_dl.yview)
        self.dtree_dl.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 4), pady=6)
        self.dtree_dl.pack(fill="both", expand=True, padx=6, pady=6)
        self.dtree_dl.bind("<Double-1>", self.dl_open_row)

    def refresh_downloads(self):
        t = self.dtree_dl
        live = set()
        for j in JOBS:
            st = "saved" if j["state"] == "done" else j["state"]
            if j["total"] and j["state"] in ("downloading", "done"):
                st += f"  {j['done']}/{j['total']}"
            iid = f"job:{j['id']}"
            live.add(j["path"])
            vals = (j["m"]["title"], j["ch"]["title"], st)
            if t.exists(iid):
                if t.item(iid, "values") != tuple(map(str, vals)):
                    t.item(iid, values=vals)
            else:
                t.insert("", "end", iid=iid, values=vals)
        for n, r in enumerate(DB["downloads"]):
            if r.get("path") in live:
                continue
            st = "saved" if os.path.exists(r["path"]) else "saved (file missing)"
            iid = f"dl:{n}"
            vals = (r.get("m", {}).get("title", "?"), r.get("ch", {}).get("title", "?"), st)
            if t.exists(iid):
                if t.item(iid, "values") != tuple(map(str, vals)):
                    t.item(iid, values=vals)
            else:
                t.insert("", "end", iid=iid, values=vals)

    def dl_row(self, iid):
        """The download record behind a tree row (live job or saved history)."""
        if not iid:
            return None
        if iid.startswith("dl:"):
            n = int(iid[3:])
            return DB["downloads"][n] if 0 <= n < len(DB["downloads"]) else None
        jid = iid[4:]
        j = next((x for x in JOBS if str(x["id"]) == jid), None)
        if j and j.get("state") == "done":
            return {"path": j["path"], "m": j["m"], "ch": j["ch"]}
        return None

    def dl_open_row(self, e):
        r = self.dl_row(self.dtree_dl.identify_row(e.y))
        if r:
            p = r.get("path", "")
            self.open_dir(os.path.dirname(p) if os.path.isfile(p) else S("dl_dir"))

    def delete_dl(self):
        rows = [r for r in (self.dl_row(i) for i in self.dtree_dl.selection()) if r]
        if not rows:
            return
        names = "\n".join(f'· {r.get("m", {}).get("title", "?")} — {r.get("ch", {}).get("title", "?")}' for r in rows)
        if not messagebox.askyesno("Delete downloads", f"Delete these chapter files from disk?\n\n{names}"):
            return
        for r in rows:
            p = r.get("path")
            if p:
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
                DB["downloads"][:] = [x for x in DB["downloads"] if x.get("path") != p]
        save_db()
        self.dtree_dl.delete(*self.dtree_dl.get_children())
        self.refresh_downloads()

    def cancel_jobs(self):
        for j in JOBS:
            if j["state"] in ("queued", "getting pages", "downloading"):
                j["state"] = "cancelled"

    def clear_jobs(self):
        for j in [j for j in JOBS if j["state"] in ("done", "cancelled") or j["state"].startswith("error")]:
            JOBS.remove(j)
            iid = f"job:{j['id']}"
            if self.dtree_dl.exists(iid):
                self.dtree_dl.delete(iid)

    def sync_done_jobs(self):
        """Fold finished jobs into the persistent download index (offline library)."""
        for j in JOBS:
            if j["state"] != "done" or j.get("recorded"):
                continue
            j["recorded"] = True
            if os.path.exists(j["path"]) and not any(r.get("path") == j["path"] for r in DB["downloads"]):
                DB["downloads"].append({"key": pkey(j["m"]), "m": j["m"], "i": j.get("i", 0), "ch": j["ch"],
                                        "path": j["path"], "ts": int(time.time())})
                save_db()

    def open_dir(self, p):
        os.makedirs(p, exist_ok=True)
        try:
            os.startfile(p)
        except Exception:
            pass

    # ----- settings -----
    def build_settings(self):
        v = self.views["Settings"]
        self.title_label(v, "Settings").pack(anchor="w", padx=28, pady=(24, 12))
        scroll = ctk.CTkScrollableFrame(v, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        def card(title):
            f = ctk.CTkFrame(scroll, fg_color=PANEL, corner_radius=12)
            f.pack(fill="x", padx=28, pady=6)
            ctk.CTkLabel(f, text=title, font=("Segoe UI", 14, "bold"), text_color=SILVER, anchor="w").pack(fill="x", padx=16, pady=(12, 6))
            return f

        def row(f):
            r = ctk.CTkFrame(f, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=5)
            return r

        f = card("Reading")
        r = row(f)
        ctk.CTkLabel(r, text="Default reading mode", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.set_mode = menu(r, MODES, lambda v: self.setv("mode", v), width=220)
        self.set_mode.set(S("mode"))
        self.set_mode.pack(side="left")
        r = row(f)
        ctk.CTkLabel(r, text="Background", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.set_paper = menu(r, PAPERS, self.apply_paper, width=200)
        self.set_paper.set(S("paper"))
        self.set_paper.pack(side="left")
        ctk.CTkLabel(r, text="paper texture behind the pages and the menu", text_color=MUTED,
                     font=("Segoe UI", 11)).pack(side="left", padx=10)
        r = row(f)
        self.sw_arrows = ctk.CTkSwitch(r, text="Show the reading-direction arrow at the start of a chapter",
                                       progress_color=SILVER, button_color=SILVER_HI, text_color=TEXT,
                                       command=lambda: self.setv("show_arrows", bool(self.sw_arrows.get())))
        self.sw_arrows.pack(side="left")
        if S("show_arrows"):
            self.sw_arrows.select()
        r = row(f)
        self.sw_guides = ctk.CTkSwitch(r, text="In paged modes: black page borders, page numbers and the double-page gutter",
                                       progress_color=SILVER, button_color=SILVER_HI, text_color=TEXT,
                                       command=lambda: self.setv("paged_guides", bool(self.sw_guides.get())))
        self.sw_guides.pack(side="left")
        if S("paged_guides"):
            self.sw_guides.select()
        ctk.CTkFrame(f, height=8, fg_color="transparent").pack()

        f = card("Downloads (saved as one .cbz per chapter)")
        r = row(f)
        ctk.CTkLabel(r, text="Folder", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.dl_dir_lbl = ctk.CTkLabel(r, text=S("dl_dir"), text_color=MUTED, anchor="w")
        self.dl_dir_lbl.pack(side="left", padx=(0, 10))
        btn(r, "Change…", self.pick_dl_dir, width=80).pack(side="left")
        r = row(f)
        ctk.CTkLabel(r, text="Download order", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.set_order = menu(r, ["Oldest first", "Newest first"], lambda v: self.setv("dl_order", v), width=160)
        self.set_order.set(S("dl_order"))
        self.set_order.pack(side="left")
        r = row(f)
        ctk.CTkLabel(r, text="Delay between images", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.delay_lbl = ctk.CTkLabel(r, text=f"{S('dl_delay'):.1f} s", text_color=SILVER, width=50)
        sl = ctk.CTkSlider(r, from_=0.3, to=5, number_of_steps=47, width=220, progress_color=SILVER, button_color=SILVER_HI,
                           button_hover_color="white", fg_color=BTN, command=self.set_delay)
        sl.set(S("dl_delay"))
        sl.pack(side="left")
        self.delay_lbl.pack(side="left", padx=8)
        ctk.CTkLabel(f, text="Higher delay = safer against bans. Pages already viewed in the reader are reused without any request.",
                     text_color=MUTED, font=("Segoe UI", 11), anchor="w").pack(fill="x", padx=16, pady=(0, 12))

        f = card("Sources")
        r = row(f)
        btn(r, "Reload sources.json", self.reload_sources, width=150).pack(side="left")
        btn(r, "Open app folder", lambda: self.open_dir(BASE), width=130).pack(side="left", padx=8)
        btn(r, "Clear image cache", self.clear_cache, width=140).pack(side="left")
        r = row(f)
        sw = ctk.CTkSwitch(r, text="Show 18+ sources", progress_color=SILVER, button_color=SILVER_HI, text_color=TEXT,
                           command=lambda: (self.setv("nsfw", bool(sw.get())), self.refresh_sources()))
        sw.pack(side="left")
        if S("nsfw"):
            sw.select()
        self.repo_status = ctk.CTkLabel(f, text="", text_color=MUTED, anchor="w")
        self.repo_status.pack(fill="x", padx=16)
        ctk.CTkLabel(f, text=f"Config file in use: {SRC_FILE}", text_color=SILVER_DIM, font=("Segoe UI", 11),
                     anchor="w", wraplength=900, justify="left").pack(fill="x", padx=16, pady=(2, 0))
        self.repo_list = ctk.CTkLabel(f, text="", anchor="w", justify="left", text_color=TEXT)
        self.repo_list.pack(fill="x", padx=16, pady=(4, 0))
        ctk.CTkLabel(f, text="Sources shown in Sources / Search — untick any you don't want:", text_color=MUTED,
                     font=("Segoe UI", 11), anchor="w").pack(fill="x", padx=16, pady=(6, 2))
        self.src_grid = ctk.CTkFrame(f, fg_color="transparent")
        self.src_grid.pack(fill="x", padx=16, pady=(0, 14))
        self.build_src_toggles()

        self.cf_map = {s.name: s.id for s in SOURCES.values() if s.d.get("cookie")}
        if not self.cf_map:
            return  # nothing in sources.json needs a pasted cookie right now
        f = card("Cloudflare-protected sources (paste your browser's User-Agent + Cookie)")
        r = row(f)
        ctk.CTkLabel(r, text="Source", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.cf_pick = menu(r, list(self.cf_map), self.cf_load, width=200)
        self.cf_pick.pack(side="left")
        btn(r, "Load saved", lambda: self.cf_load(self.cf_pick.get()), width=110).pack(side="left", padx=8)
        r = row(f)
        ctk.CTkLabel(r, text="User-Agent", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.cf_ua = entry(r, placeholder_text="Mozilla/5.0 (Windows NT 10.0; …) Chrome/1xx", width=520)
        self.cf_ua.pack(side="left")
        r = row(f)
        ctk.CTkLabel(r, text="Cookie", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.cf_ck = entry(r, placeholder_text="cf_clearance=…   (copy the whole Cookie request header)", width=520)
        self.cf_ck.pack(side="left")
        r = row(f)
        btn(r, "Save", self.cf_save, primary=True, width=90).pack(side="left", padx=(190, 8))
        btn(r, "Test", self.cf_test, width=80).pack(side="left")
        self.cf_status = ctk.CTkLabel(r, text="", text_color=MUTED, anchor="w")
        self.cf_status.pack(side="left", padx=10)
        ctk.CTkLabel(f, text='Only needed for sources marked "cookie" in sources.json. Open the site in your browser → '
                             "DevTools (F12) → Network → click any request → Request Headers → copy the User-Agent and the "
                             "whole Cookie value here, then Save. Browser and app must be on the same network/IP.",
                     text_color=MUTED, font=("Segoe UI", 11), anchor="w", wraplength=900,
                     justify="left").pack(fill="x", padx=16, pady=(6, 12))

    def cf_load(self, name):
        sid = self.cf_map.get(name)
        h = ((DB["set"].get("headers") or {}).get(sid) or {}) if sid else {}
        self.cf_ua.delete(0, "end"); self.cf_ua.insert(0, h.get("User-Agent", ""))
        self.cf_ck.delete(0, "end"); self.cf_ck.insert(0, h.get("Cookie", ""))
        self.cf_status.configure(text="Loaded saved values." if h else "Nothing saved for this source yet.")

    def cf_save(self):
        sid = self.cf_map.get(self.cf_pick.get())
        if not sid:
            self.cf_status.configure(text="Pick a protected source first.")
            return
        DB["set"].setdefault("headers", {})[sid] = {"User-Agent": self.cf_ua.get().strip(),
                                                    "Cookie": self.cf_ck.get().strip()}
        save_db()
        self.cf_status.configure(text=f"Saved for {self.cf_pick.get()} — re-open the source to use it.")

    def cf_test(self):
        sid = self.cf_map.get(self.cf_pick.get())
        src = SOURCES.get(sid) if sid else None
        if not src:
            self.cf_status.configure(text="Pick a protected source first.")
            return
        self.cf_status.configure(text="Testing…")
        bg(lambda: src.get(src.base + "/").status_code,
           lambda r, e: self.cf_status.configure(text=f"OK — HTTP {r} (access granted)" if not e else f"Failed: {str(e)[:90]}"))

    def setv(self, k, v):
        DB["set"][k] = v
        save_db()

    def set_delay(self, v):
        v = round(float(v), 1)
        self.delay_lbl.configure(text=f"{v:.1f} s")
        DB["set"]["dl_delay"] = v
        save_db()

    def pick_dl_dir(self):
        d = filedialog.askdirectory(initialdir=S("dl_dir"))
        if d:
            self.setv("dl_dir", d)
            self.dl_dir_lbl.configure(text=d)

    def refresh_settings(self):
        self.update_repo_list()
        hid = hidden_ids()
        for sid, sw in getattr(self, "src_switches", {}).items():
            sw.select() if sid not in hid else sw.deselect()

    def update_repo_list(self):
        if not SOURCES:
            self.repo_list.configure(text="No sources installed.")
            return
        hid = hidden_ids()
        self.repo_list.configure(text="Installed: " + ", ".join(
            s.name + (" (hidden)" if s.id in hid else "") for s in SOURCES.values()))

    def build_src_toggles(self):
        """One on/off switch per source - hidden ones vanish from Sources and Search."""
        clear(self.src_grid)
        self.src_switches = {}
        hid, cols = hidden_ids(), 2
        for i, s in enumerate(SOURCES.values()):
            cell = ctk.CTkFrame(self.src_grid, fg_color="transparent")
            cell.grid(row=i // cols, column=i % cols, sticky="w", padx=(0, 34), pady=2)
            sw = ctk.CTkSwitch(cell, text=s.name + ("  18+" if s.nsfw else ""), progress_color=SILVER,
                               button_color=SILVER_HI, text_color=TEXT, width=220,
                               command=lambda s=s: self.toggle_source(s))
            sw.pack(side="left")
            if s.id not in hid:
                sw.select()
            self.src_switches[s.id] = sw

    def toggle_source(self, s):
        hid = hidden_ids()
        (hid.discard if self.src_switches[s.id].get() else hid.add)(s.id)
        DB["set"]["hidden"] = sorted(hid)
        save_db()
        self.refresh_sources()
        self.refresh_search()
        self.update_repo_list()

    def apply_paper(self, name):
        """Switch the background: adopt its palette, repaint the sidebar and the open reader."""
        self.setv("paper", name)
        retint(self, theme_pick(name))
        self.configure(fg_color=BG)
        style_ttk()
        self.paint_side()
        try:
            self.refresh_settings()
        except Exception:
            pass
        r = self.reader
        if self.cur == "Reader" and r and r.get("urls") and not r.get("err"):
            r["restore"] = r.get("page", 0)
            self.build_body()

    def reload_sources(self):
        rebuild_sources()
        self.repo_status.configure(text=f"Loaded {len(SOURCES)} sources from {SRC_FILE}")
        self.build_src_toggles()
        self.refresh_settings()
        self.refresh_sources()
        self.refresh_search()

    def clear_cache(self):
        shutil.rmtree(CACHE, ignore_errors=True)
        os.makedirs(CACHE, exist_ok=True)
        self.repo_status.configure(text="Image cache cleared")

    # ----- details (built once, filled in place: no flicker) -----
    # ----- randomizer -----
    def nav_click(self, n):
        if n == "Randomizer":
            self.rand_roll()
            return
        self.rand_mode = False
        self.rdm_tok += 1
        self.rand_sync()
        self.show(n)

    def go_back(self):
        self.rand_mode = False
        self.rdm_tok += 1
        self.rand_sync()
        self.show(self.back or "Library")

    def rand_sync(self):
        """Previous / Next buttons only exist on the details page while browsing random picks."""
        try:
            self.d_prev.pack_forget()
            self.d_next.pack_forget()
            if self.rand_mode:
                self.d_prev.pack(side="left", padx=(8, 0))
                self.d_next.pack(side="left", padx=8)
                self.d_prev.configure(state="normal" if self.rand_i > 0 else "disabled")
        except Exception:
            pass

    def rand_roll(self):
        self.rand_mode = True
        self.rdm_tok += 1
        tok = self.rdm_tok
        if self.cur not in ("Details", "Reader"):
            self.back = self.cur
        self.dtok += 1
        self.cur_detail = None
        self.show("Details")
        self.rand_sync()
        self.d_title.configure(text="\U0001f3b2 Rolling the dice\u2026")
        self.d_src.configure(text="")
        self.d_desc.configure(text="Picking a random title from your enabled sources\u2026")
        for w in (self.d_more, self.d_count, self.d_status):
            w.configure(text="")
        self.d_cont.configure(text="\u25b6 Start reading", state="disabled")
        self.d_bm.configure(state="disabled", text="\u2606 Bookmark")
        self.dtree.delete(*self.dtree.get_children())
        self.d_cover.configure(image=None, text="")
        bg(lambda: random_pick(self.rand_seen), lambda r, e: self.rand_done(tok, r, e))

    def rand_done(self, tok, r, e):
        if tok != self.rdm_tok or not self.rand_mode:
            return
        if e or not r:
            self.d_title.configure(text="\U0001f3b2 No luck")
            self.d_desc.configure(text="Couldn't fetch a random title (" + (str(e)[:120] if e else "no sources available")
                                  + "). Press Next random to try again.")
            return
        self.rand_seen.add(r["url"])
        del self.rand_hist[self.rand_i + 1:]
        self.rand_hist.append(r)
        self.rand_i = len(self.rand_hist) - 1
        self.rand_open(r)

    def rand_open(self, m):
        self._rand_open = True
        try:
            self.open_manga(m)
        finally:
            self._rand_open = False
        self.rand_sync()

    def rand_prev(self):
        if self.rand_mode and self.rand_i > 0:
            self.rdm_tok += 1
            self.rand_i -= 1
            self.rand_open(self.rand_hist[self.rand_i])

    # ----- lofi radio -----
    def lofi_toggle(self):
        if LOFI.state in ("on", "connecting"):
            LOFI.stop()
        elif not LOFI.start():
            messagebox.showinfo("Lofi radio", "Lofi radio needs the 'miniaudio' package.\n\n"
                                "Run:   pip install miniaudio\n(and rebuild the exe if you use the packaged version)")

    def lofi_refresh(self):
        try:
            st = LOFI.state
            label = {"off": "\u266b  Lofi radio: off", "connecting": "\u266b  Connecting\u2026",
                     "on": "\u266b  Lofi radio: on", "error": "\u266b  No stream \u2013 retry"}[st]
            self.side.itemconfigure(self._lofi_txt, text=label, fill=SILVER_HI if st == "on" else MUTED)
            self.side.itemconfigure(self._lofi_sub, text=LOFI.name[:32] if st == "on" else "")
            self.side.itemconfigure(self._lofi_skip, state="normal" if st == "on" else "hidden")
        except Exception:
            pass

    def build_details(self):
        v = self.views["Details"]
        bar = ctk.CTkFrame(v, fg_color="transparent")
        bar.pack(fill="x", padx=22, pady=(18, 8))
        btn(bar, "← Back", self.go_back, width=80).pack(side="left")
        self.d_prev = btn(bar, "◀ Previous", self.rand_prev, width=110)
        self.d_next = btn(bar, "🎲 Next random", lambda: self.rand_roll(), width=150, primary=True)
        top = ctk.CTkFrame(v, fg_color="transparent")
        top.pack(fill="x", padx=22)
        self.d_cover = ctk.CTkLabel(top, text="", width=190, height=270, corner_radius=12, fg_color=PANEL)
        self.d_cover.pack(side="left", anchor="n")
        right = ctk.CTkFrame(top, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=20)
        self.d_title = ctk.CTkLabel(right, text="", font=("Segoe UI", 25, "bold"), text_color=SILVER_HI, wraplength=760, justify="left", anchor="w")
        self.d_title.pack(fill="x")
        self.d_src = ctk.CTkLabel(right, text="", text_color=MUTED, anchor="w")
        self.d_src.pack(fill="x", pady=(0, 8))
        row = ctk.CTkFrame(right, fg_color="transparent")
        row.pack(fill="x", pady=4)
        self.d_bm = btn(row, "☆ Bookmark", self.toggle_bm, width=130)
        self.d_bm.pack(side="left")
        self.d_cont = btn(row, "▶ Start reading", None, primary=True, width=190)
        self.d_cont.pack(side="left", padx=8)
        self.d_dl = btn(row, "⬇ Download (0)", self.enqueue_downloads, width=140, state="disabled")
        self.d_dl.pack(side="left")
        self.d_rate = btn(row, "★ Rate", lambda: self.cur_detail and self.rate_manga(self.cur_detail[0]), width=110)
        self.d_rate.pack(side="left", padx=8)
        self.d_desc = ctk.CTkLabel(right, text="", wraplength=760, justify="left", anchor="nw", text_color="#b4b9c2", font=("Segoe UI", 12))
        self.d_desc.pack(fill="x", pady=(12, 0))
        self.d_more = ctk.CTkLabel(right, text="", text_color=SILVER, cursor="hand2", anchor="w")
        self.d_more.pack(fill="x")
        self.d_more.bind("<Button-1>", lambda e: self.toggle_desc())
        hdr = ctk.CTkFrame(v, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(14, 4))
        self.d_count = ctk.CTkLabel(hdr, text="", font=("Segoe UI", 15, "bold"), text_color=SILVER_HI)
        self.d_count.pack(side="left")
        self.d_prog = ctk.CTkProgressBar(hdr, width=170, height=8, progress_color=SILVER, fg_color=BTN)
        self.d_prog.set(0)
        self.d_prog.pack(side="left", padx=12)
        self.d_status = ctk.CTkLabel(hdr, text="", text_color=MUTED)
        self.d_status.pack(side="left", padx=14)
        self.d_sort = btn(hdr, "Newest first ↓", self.toggle_sort, width=130, height=30)
        self.d_sort.pack(side="right")
        btn(hdr, "Select none", self.sel_none, width=90, height=30).pack(side="right", padx=6)
        btn(hdr, "Select all", self.sel_all, width=90, height=30).pack(side="right")
        box = ctk.CTkFrame(v, fg_color=CARD, corner_radius=12)
        box.pack(fill="both", expand=True, padx=22, pady=(0, 16))
        t = self.dtree = ttk.Treeview(box, columns=("chk", "title", "st"), show="", style="S.Treeview", selectmode="browse")
        t.column("chk", width=46, anchor="center", stretch=False)
        t.column("title", anchor="w")
        t.column("st", width=150, anchor="e", stretch=False)
        t.tag_configure("read", foreground=MUTED)
        sb = ctk.CTkScrollbar(box, command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 4), pady=6)
        t.pack(fill="both", expand=True, padx=6, pady=6)
        t.bind("<Button-1>", self.tree_click)
        t.bind("<Double-1>", self.tree_open)
        t.bind("<Return>", self.tree_open)

    def open_manga(self, m, resume=False):
        if not self._rand_open:
            self.rand_mode = False
            self.rdm_tok += 1
            self.rand_sync()
        if self.cur not in ("Details", "Reader"):
            self.back = self.cur
        self.dtok += 1
        tok = self.dtok
        self.cur_detail, self.sel, self.desc_full = None, set(), False
        src = SOURCES.get(m["source"])
        self.show("Details")
        self.d_title.configure(text=m["title"])
        self.d_rate.configure(text="★ Rate")
        self.d_src.configure(text=src.name if src else m["source"])
        self.d_desc.configure(text="Loading…")
        self.d_more.configure(text="")
        self.d_count.configure(text="")
        self.d_status.configure(text="")
        self.d_cont.configure(text="▶ Start reading", state="disabled")
        self.d_bm.configure(state="disabled", text="☆ Bookmark")
        self.dtree.delete(*self.dtree.get_children())
        self.d_cover.configure(image=None, text="")
        self.update_dl_btn()
        if not src:
            self.d_src.configure(text=m.get("name") or m.get("source") or "Local files")
            info = self.offline_info(m)
            if info:
                self.render_details(tok, m, info, None, resume)
            else:
                self.d_desc.configure(text="This source is no longer installed, and no downloaded chapters were found on disk.")
            return
        load_img(src, m["cover"], lambda im: self.dtok == tok and set_img(self.d_cover, im, (190, 270)), size=(190, 270))
        bg(lambda: src.details(m["url"]), lambda r, e: self.render_details(tok, m, r, e, resume))

    def render_details(self, tok, m, info, err, resume=False):
        if tok != self.dtok:
            return
        if err:
            info = self.offline_info(m)
            if not info:
                self.d_desc.configure(text=f"Failed to load: {str(err)[:160]}")
                return
        chs = info["chapters"]
        prog = DB["progress"].setdefault(pkey(m), {"read": []})
        urls = [c["url"] for c in chs]
        m = dict(m, title=info.get("title") or m["title"], cover=info.get("cover") or m["cover"])
        self.cur_detail = (m, info)
        self.d_title.configure(text=m["title"])
        self.show_details_rating()
        if m.get("url"):
            self.d_bm.configure(state="normal", text=self.bm_text(m))
        else:
            self.d_bm.configure(state="disabled", text="☆ Bookmark")
        self.full_desc = info.get("description") or "No description available."
        self.render_desc()
        if resume and prog.get("chapter") in urls:
            self.continue_or_restart(m, chs, urls.index(prog["chapter"]))
            return
        if chs:
            has = prog.get("chapter") in urls
            idx = urls.index(prog["chapter"]) if has else 0
            self.d_cont.configure(state="normal", text=f'▶ Continue: {prog["title"][:24]}' if has else "▶ Start reading",
                                  command=lambda: self.continue_or_restart(m, chs, idx))
        else:
            self.d_cont.configure(state="disabled", text="▶ Start reading")
        self.refresh_tree()

    def offline_info(self, m):
        """Rebuild a chapter list from saved .cbz files so an unreachable source still shows what you have."""
        local = local_chapters_any(m)
        if not local:
            return None
        recs = {r.get("i"): r for r in dl_records(m)}
        chs = []
        for i in sorted(local):
            c = (recs.get(i) or {}).get("ch") or {}
            title = c.get("title") or re.sub(r"^\d+\s*-\s*", "", os.path.splitext(os.path.basename(local[i]))[0])
            chs.append({"title": title, "url": c.get("url") or f"local:{local[i]}", "i": i})
        return {"title": m.get("title", ""), "cover": m.get("cover", ""), "chapters": chs,
                "description": "(Source unreachable — showing your downloaded chapters only.)"}

    def continue_or_restart(self, m, chs, idx):
        """Re-entering a manga: ask whether to resume the saved page or start this chapter over."""
        p = DB["progress"].get(pkey(m), {})
        page = p.get("page", 0) if p.get("chapter") == chs[idx]["url"] else 0
        restart = self.ask_resume(chs[idx]["title"], page) if page else False
        self.open_chapter(m, chs, idx, restart=restart)

    def ask_resume(self, chapter, page):
        """Modal: True = start this chapter from the beginning, False = resume the saved page."""
        win = ctk.CTkToplevel(self)
        win.title("Continue reading")
        win.geometry("460x210")
        win.resizable(False, False)
        win.configure(fg_color=BG)
        ans = {"restart": False}

        def pick(restart):
            ans["restart"] = restart
            win.destroy()

        ctk.CTkLabel(win, text="Continue where you left off?", font=("Segoe UI", 17, "bold"),
                     text_color=SILVER_HI).pack(pady=(26, 4))
        ctk.CTkLabel(win, text=f"{chapter} — saved at page {page + 1}", text_color=MUTED).pack()
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(pady=22)
        btn(row, f"▶ Resume page {page + 1}", lambda: pick(False), primary=True, width=180).pack(side="left", padx=6)
        btn(row, "⟲ Start chapter over", lambda: pick(True), width=180).pack(side="left", padx=6)
        win.protocol("WM_DELETE_WINDOW", lambda: pick(False))
        win.bind("<Escape>", lambda e: pick(False))
        win.transient(self)
        win.update_idletasks()
        try:
            x = self.winfo_rootx() + (self.winfo_width() - 460) // 2
            y = self.winfo_rooty() + (self.winfo_height() - 210) // 3
            win.geometry(f"+{max(0, x)}+{max(0, y)}")
            win.grab_set()
        except Exception:
            pass
        self.wait_window(win)
        return ans["restart"]

    def update_progress(self):
        if not self.cur_detail:
            return
        m, info = self.cur_detail
        chs = info["chapters"]
        n = len(chs)
        read = set(DB["progress"].get(pkey(m), {}).get("read", []))
        done = sum(1 for c in chs if c["url"] in read)
        saved = len(local_chapters_any(m))
        pct = int(round(done / n * 100)) if n else 0
        self.d_count.configure(text=f"{n} chapters · {done} read ({pct}% complete)" + (f" · {saved} saved" if saved else ""))
        try:
            self.d_prog.set(done / n if n else 0)
        except Exception:
            pass

    def render_desc(self):
        d = self.full_desc
        if len(d) > 420 and not self.desc_full:
            self.d_desc.configure(text=d[:420].rsplit(" ", 1)[0] + " …")
            self.d_more.configure(text="Show more")
        else:
            self.d_desc.configure(text=d)
            self.d_more.configure(text="Show less" if len(d) > 420 else "")

    def toggle_desc(self):
        self.desc_full = not self.desc_full
        self.render_desc()

    def refresh_tree(self):
        if not self.cur_detail:
            return
        m, info = self.cur_detail
        chs = info["chapters"]
        local = local_chapters(m)
        read = set(DB["progress"].get(pkey(m), {}).get("read", []))
        t = self.dtree
        t.delete(*t.get_children())
        for i in (range(len(chs) - 1, -1, -1) if self.desc else range(len(chs))):
            c = chs[i]
            st = (["Read"] if c["url"] in read else []) + (["Saved"] if c.get("i", i) in local else [])
            t.insert("", "end", iid=str(i), values=("☑" if i in self.sel else "☐", c["title"], " · ".join(st)),
                     tags=("read",) if c["url"] in read else ())
        self.update_progress()

    def toggle_sort(self):
        self.desc = not self.desc
        self.d_sort.configure(text="Newest first ↓" if self.desc else "Oldest first ↑")
        self.refresh_tree()

    def tree_click(self, e):
        t = self.dtree
        if t.identify_region(e.x, e.y) == "cell" and t.identify_column(e.x) == "#1":
            iid = t.identify_row(e.y)
            if iid:
                i = int(iid)
                self.sel.symmetric_difference_update({i})
                t.set(iid, "chk", "☑" if i in self.sel else "☐")
                self.update_dl_btn()
            return "break"

    def tree_open(self, e):
        if not self.cur_detail:
            return
        iid = self.dtree.identify_row(e.y) if e.type == "4" else (self.dtree.selection() or [""])[0]
        if iid and not (e.type == "4" and self.dtree.identify_column(e.x) == "#1"):
            m, info = self.cur_detail
            self.open_chapter(m, info["chapters"], int(iid))

    def sel_all(self):
        if self.cur_detail:
            self.sel = set(range(len(self.cur_detail[1]["chapters"])))
            self.refresh_tree()
            self.update_dl_btn()

    def sel_none(self):
        self.sel = set()
        self.refresh_tree()
        self.update_dl_btn()

    def update_dl_btn(self):
        self.d_dl.configure(text=f"⬇ Download ({len(self.sel)})", state="normal" if self.sel and self.cur_detail else "disabled")

    def enqueue_downloads(self):
        if not self.cur_detail or not self.sel:
            return
        m, info = self.cur_detail
        chs, n = info["chapters"], 0
        local = local_chapters(m)
        for i in sorted(self.sel, reverse=S("dl_order") == "Newest first"):
            c = chs[i]
            if c.get("i", i) in local:
                continue
            p = dl_path(m, i, c)
            if os.path.exists(p):
                continue
            job = {"id": next_job_id(), "i": i, "recorded": False,
                   "m": {k: m[k] for k in ("source", "url", "title", "cover")},
                   "ch": c, "path": p, "state": "queued", "done": 0, "total": 0}
            JOBS.append(job)
            DL_Q.put(job)
            n += 1
        self.sel = set()
        self.refresh_tree()
        self.update_dl_btn()
        self.d_status.configure(text=f"Queued {n} chapter(s) — see Downloads tab")

    def bm_text(self, m):
        return "★ Bookmarked" if self.find_bm(m) else "☆ Bookmark"

    def toggle_bm(self):
        if not self.cur_detail:
            return
        m = self.cur_detail[0]
        ex = self.find_bm(m)
        if ex:
            DB["bookmarks"].remove(ex)
        else:
            DB["bookmarks"].append({**{k: m[k] for k in ("source", "url", "title", "cover")}, "folder": ""})
        save_db()
        self.d_bm.configure(text=self.bm_text(m))

    # ----- reader -----
    def build_reader(self):
        v = self.views["Reader"]
        bar = ctk.CTkFrame(v, height=54, corner_radius=0, fg_color=SIDE)
        bar.pack(fill="x")
        btn(bar, "← Back", self.reader_back, width=76).pack(side="left", padx=(12, 8), pady=10)
        self.r_title = ctk.CTkLabel(bar, text="", font=("Segoe UI", 13, "bold"), text_color=TEXT)
        self.r_title.pack(side="left", padx=8)
        self.r_page = ctk.CTkLabel(bar, text="", text_color=MUTED)
        self.r_page.pack(side="left", padx=8)
        self.r_next = btn(bar, "Next ▶", lambda: self.chapter_step(1), primary=True, width=76)
        self.r_next.pack(side="right", padx=(6, 12))
        self.r_prev = btn(bar, "◀ Prev", lambda: self.chapter_step(-1), width=76)
        self.r_prev.pack(side="right")
        btn(bar, "+", lambda: self.zoom_by(1), width=34).pack(side="right", padx=(6, 12))
        self.r_zoom = ctk.CTkLabel(bar, text="100%", text_color=SILVER, width=48)
        self.r_zoom.pack(side="right")
        btn(bar, "−", lambda: self.zoom_by(-1), width=34).pack(side="right", padx=(12, 0))
        self.r_mode = menu(bar, MODES, self.change_mode, width=190)
        self.r_mode.pack(side="right", padx=8)
        self.rbody = ctk.CTkFrame(v, fg_color=READER_BG, corner_radius=0)
        self.rbody.pack(fill="both", expand=True)

    def is_web(self):
        return self.reader["mode"] == MODES[0]

    def is_rtl(self):
        return "right→left" in self.reader["mode"]

    def is_double(self):
        return self.reader["mode"].startswith("Double")

    def save_reader(self, mark=False):
        r = self.reader
        if not r or r.get("urls") is None:
            return
        p = DB["progress"].setdefault(pkey(r["m"]), {"read": []})
        url = r["chs"][r["idx"]]["url"]
        n = len(r["urls"])
        if not n:
            return
        atend = False
        if self.is_web():
            try:
                bot = r["c"].yview()[1]
            except Exception:
                bot = 0
            # images far from the viewport are dropped on purpose now, so judge "finished" by the last page
            atend = bot >= 0.97 and r.get("page", 0) >= n - 1
        else:
            atend = self.pg_spread(r["page"])[-1] >= n - 1
        if p.get("chapter") == url:
            p["page"] = r.get("page", 0)
        if mark or atend:
            p.setdefault("read", [])
            if url not in p["read"]:
                p["read"].append(url)
        save_db()

    def open_chapter(self, m, chs, idx, nxt=False, restart=False):
        if self.cur == "Reader":
            self.save_reader(mark=nxt)
        ch = chs[idx]
        p = DB["progress"].setdefault(pkey(m), {"read": []})
        page = 0 if restart else (p.get("page", 0) if p.get("chapter") == ch["url"] else 0)
        p.update(chapter=ch["url"], title=ch["title"], page=page)
        DB["last"] = {"manga": {k: m[k] for k in ("source", "url", "title", "cover")}, "key": pkey(m)}
        save_db()
        self.rtok += 1
        tok = self.rtok
        mode = p.get("mode", S("mode"))
        mode = mode if mode in MODES else MODES[0]
        local = local_path(m, ch.get("i", idx), ch)
        src = LOCAL if local else SOURCES.get(m["source"])
        self.reader = {"m": m, "chs": chs, "idx": idx, "urls": None, "mode": mode, "zoom": 1.0, "page": page, "tok": tok,
                       "restore": page if page > 0 else None, "err": None, "src": src, "local": local}
        self.show("Reader")
        self.r_title.configure(text=f'{m["title"][:34]}  ·  {ch["title"][:30]}')
        self.r_prev.configure(state="normal" if idx > 0 else "disabled")
        self.r_next.configure(state="normal" if idx + 1 < len(chs) else "disabled")
        self.r_mode.set(mode)
        self.r_zoom.configure(text="100%")
        self.r_page.configure(text="")
        self.build_body()
        bg(lambda: cbz_pages(local) if local else src.pages(ch["url"]), lambda res, e: self.pages_ready(tok, res, e))

    def pages_ready(self, tok, urls, err):
        if tok != self.rtok:
            return
        self.reader["urls"] = urls or []
        self.reader["err"] = str(err)[:120] if err else None
        self.build_body()
        if self.reader["urls"] and not self.reader["err"]:
            self.show_hint()

    def chapter_step(self, d):
        r = self.reader
        if r and 0 <= r["idx"] + d < len(r["chs"]):
            self.open_chapter(r["m"], r["chs"], r["idx"] + d, nxt=d > 0)

    def reader_back(self):
        self.show("Details")
        self.refresh_tree()

    def change_mode(self, name):
        r = self.reader
        if not r or name == r["mode"]:
            return
        was_web = self.is_web()
        r["mode"] = name
        DB["progress"].setdefault(pkey(r["m"]), {"read": []})["mode"] = name
        save_db()
        if not was_web and self.is_web() and r["page"] > 0:
            r["restore"] = r["page"]
        r["pan"] = [0, 0]
        self.build_body()
        if r["urls"] and not r["err"]:
            self.show_hint()

    def hint_text(self):
        if self.is_web():
            return ARROWS["webtoon"]
        return ARROWS["rtl"] if self.is_rtl() else ARROWS["ltr"]

    def show_hint(self):
        """Little reading-direction badge; fades away 5s after a chapter opens or the mode changes."""
        if not S("show_arrows") or not self.reader or self.reader.get("urls") is None:
            return
        old = getattr(self, "_hint", None)
        if old is not None:
            try:
                old.destroy()
            except Exception:
                pass
        try:
            lbl = ctk.CTkLabel(self.rbody, text=self.hint_text(), fg_color="#10131a", text_color=SILVER_HI,
                               corner_radius=14, font=("Segoe UI", 14, "bold"), padx=16, pady=7)
            lbl.place(relx=0.5, rely=0.94, anchor="s")
            self._hint = lbl
            self.after(5000, lambda l=lbl: self.drop_hint(l))
        except Exception:
            pass

    def drop_hint(self, lbl):
        try:
            lbl.destroy()
        except Exception:
            pass

    def build_body(self):
        r = self.reader
        self.rgen += 1
        r["gen"] = self.rgen
        for k in ("c", "labels", "items", "texts", "photos", "nextbtn", "ys", "total", "cw",
                  "state", "imgs", "dims", "t0", "_wz", "borders", "tex", "tex_items", "tex_cols", "tex_rows"):
            r.pop(k, None)
        clear(self.rbody)
        msg = None
        if r["urls"] is None:
            msg = "Loading chapter…"
        elif r["err"] or not r["urls"]:
            msg = f"Could not load pages: {r['err'] or 'none found'}"
        if msg:
            ctk.CTkLabel(self.rbody, text=msg, font=("Segoe UI", 15), text_color=MUTED).pack(pady=80)
            return
        self.update_idletasks()
        self.build_webtoon() if self.is_web() else self.build_paged()

    # --- webtoon (continuous vertical) ---
    def web_width(self):
        return int(max(300, min(900, self.rbody.winfo_width() - 40)) * self.reader["zoom"])

    def wt_dims(self, urls, W):
        """Pixel box for every page: exact when the file is already on disk, estimated otherwise.

        Knowing the sizes up-front keeps the scroll layout correct from the first frame, so resuming at
        page 40 no longer needs pages 1-39 to be downloaded first - and a page can be dropped from
        memory later without the pages below it jumping up.
        """
        raw, ratios = [], []
        for u in urls:
            wh = img_size(u)
            raw.append(wh)
            if wh[0] > 0 and wh[1] > 0:
                ratios.append(wh[1] / float(wh[0]))
        ratios.sort()
        est = ratios[len(ratios) // 2] if ratios else 1.45
        out = []
        for wh in raw:
            r = (wh[1] / float(wh[0])) if wh[0] > 0 and wh[1] > 0 else est
            w, h = W, max(1, int(round(W * r)))
            if w * h > WT_MAX_PX:  # one 1:30 strip must not eat the whole memory budget
                k = (WT_MAX_PX / float(w * h)) ** 0.5
                w, h = max(1, int(w * k)), max(1, int(h * k))
            out.append((w, h))
        return out

    def wt_tops(self, r):
        ys, y = [], 0
        for _w, h in r.get("dims") or []:
            ys.append(y)
            y += h
        return ys, y

    def build_webtoon(self):
        r, gen, n = self.reader, self.reader["gen"], len(self.reader["urls"])
        W = self.web_width()
        dims = self.wt_dims(r["urls"], W)
        c = tk.Canvas(self.rbody, bg=(paper_avg(S("paper")) or READER_BG), highlightthickness=0,
                      yscrollincrement=1, xscrollincrement=1)
        vs = ctk.CTkScrollbar(self.rbody, command=c.yview, fg_color=READER_BG, button_color=BTN_HI, button_hover_color=SILVER_DIM)
        hs = ctk.CTkScrollbar(self.rbody, orientation="horizontal", command=c.xview, fg_color=READER_BG, button_color=BTN_HI,
                              button_hover_color=SILVER_DIM)
        c.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        vs.pack(side="right", fill="y")
        c.pack(side="left", fill="both", expand=True)
        ph = page_box()
        r.update(c=c, hs=hs, dims=dims, state=[0] * n, tries=[0] * n, t0=[0.0] * n, inflight=0, wgen=0,
                 width=W, items=[], texts=[], photos={}, nextbtn=None, ys=[], total=0, cw=W, sreg=0, lastreq=0.0,
                 borders=[], tex=None, tex_items=[], tex_cols=0, tex_rows=0)
        self.wt_make_tex(r, c, c.winfo_width() or W, c.winfo_height() or 800)
        # Pages are canvas ITEMS, never child widgets: Windows refuses to place child windows beyond
        # +-32767 px, so a frame full of labels freezes in place once a chapter is longer than that
        # (the page counter kept going while the screen showed stale pages).
        y = 0
        for i, (w, h) in enumerate(dims):
            x = max(0, (W - w) // 2)
            bd = c.create_rectangle(x - 1, y - 1, x + w + 1, y + h + 1, outline="#000000", width=3)
            it = c.create_image(x, y, anchor="nw", image=ph)
            tx = c.create_text(x + w / 2, y + h / 2, anchor="center", text=f"Page {i + 1}",
                               fill=MUTED, font=("Segoe UI", 11))
            c.tag_bind(it, "<Button-1>", lambda e, i=i: self.wt_retry(i))
            c.tag_bind(tx, "<Button-1>", lambda e, i=i: self.wt_retry(i))
            r["borders"].append(bd)
            r["items"].append(it)
            r["texts"].append(tx)
            y += h
        if r["idx"] + 1 < len(r["chs"]):
            rect = c.create_rectangle(0, 0, 0, 0, fill=SILVER, outline="")
            txt = c.create_text(0, 0, text="Next chapter ▶", fill=INK, font=("Segoe UI", 12, "bold"))
            c.tag_bind(rect, "<Button-1>", lambda e: self.chapter_step(1))
            c.tag_bind(txt, "<Button-1>", lambda e: self.chapter_step(1))
            r["nextbtn"] = (rect, txt)
        self.wt_place()
        c.bind("<Configure>", lambda e: (self.wt_place(), self.wt_sched_resize()))
        self.after(80, lambda: self.wt_tick(gen))

    def wt_place(self):
        """Put every page item at its offset and refresh the scroll region.

        Canvas items are drawn by Tk itself, so (unlike child windows) they work at any depth.
        """
        r = self.reader
        try:
            c, dims, items, texts = r["c"], r["dims"], r["items"], r["texts"]
        except Exception:
            return
        borders = r.get("borders") or []
        cw = max(c.winfo_width(), r.get("width") or 0, max((w for w, _ in dims), default=0))
        r["cw"] = cw
        self.wt_make_tex(r, c, cw, c.winfo_height() or 800)
        ys, y = [], 0
        for i, (w, h) in enumerate(dims):
            ys.append(y)
            x = max(0, (cw - w) // 2)
            try:
                c.coords(items[i], x, y)
                c.coords(texts[i], x + w / 2, y + h / 2)
                if i < len(borders):
                    c.coords(borders[i], x - 1, y - 1, x + w + 1, y + h + 1)
            except Exception:
                pass
            y += h
        r["ys"], r["total"] = ys, y
        nb = r.get("nextbtn")
        if nb:
            bx, by = cw / 2, y + 24
            c.coords(nb[0], bx - 100, by, bx + 100, by + 40)
            c.coords(nb[1], bx, by + 20)
            y += 88
        r["sreg"] = max(1, y)
        c.configure(scrollregion=(0, 0, cw + 20, y))
        self.wt_paint_tex(r, c)

    def wt_make_tex(self, r, c, cw, ch):
        """(Re)build the pool of paper tiles that sit behind the pages, sized to the viewport."""
        tex = paper_tile(self, S("paper"))
        tiles = []
        if tex:
            ts = tex.width()
            cols, rows = max(1, (int(cw) + ts - 1) // ts + 1), max(1, (int(ch) + ts - 1) // ts + 1)
            tiles = [cols, rows]
        if tex is r.get("tex") and (not tex or (tiles[0] == r.get("tex_cols") and tiles[1] == r.get("tex_rows"))):
            return
        for it in r.get("tex_items") or []:
            try:
                c.delete(it)
            except Exception:
                pass
        r["tex"] = tex
        r["tex_cols"], r["tex_rows"] = (tiles or [0, 0])[0], (tiles or [0, 0])[1]
        r["tex_items"] = []
        if tex:
            r["tex_items"] = [c.create_image(0, 0, anchor="nw", image=tex, tags=("texbg",))
                              for _ in range(r["tex_cols"] * r["tex_rows"])]
            c.tag_lower("texbg")

    def wt_paint_tex(self, r, c):
        """Keep the tiles under the visible part of the chapter while it scrolls."""
        tex, items = r.get("tex"), r.get("tex_items") or []
        if not tex or not items:
            return
        ts, cols = tex.width(), max(1, r.get("tex_cols") or 1)
        top = c.canvasy(0)
        for k, it in enumerate(items):
            try:
                c.coords(it, (k % cols) * ts, top + (k // cols) * ts)
            except Exception:
                return

    def wt_layout(self):
        self.wt_place()

    def wt_sched_resize(self):
        """The window changed size - refit the pages to the new width (debounced)."""
        r = self.reader
        if not r or not self.is_web() or not r.get("items"):
            return
        old = r.get("_wz")
        if old:
            try:
                self.after_cancel(old)
            except Exception:
                pass
        r["_wz"] = self.after(280, self.wt_resize)

    def wt_resize(self):
        r = self.reader
        if r is not None:
            r["_wz"] = None
        if not r or not self.is_web() or not r.get("items") or r.get("c") is None:
            return
        if abs(self.web_width() - r.get("width", 0)) < 24:  # a scrollbar showing up is not a resize
            return
        self.wt_apply_zoom()

    def wt_retry(self, i):
        r = self.reader
        if r and r.get("state") and 0 <= i < len(r["state"]) and r["state"][i] == 3:
            r["state"][i], r["tries"][i] = 0, 0
            try:
                r["c"].itemconfigure(r["texts"][i], text=f"Page {i + 1}")
            except Exception:
                pass

    def wt_tick(self, gen):
        r = self.reader
        if gen != self.rgen or not r or not r.get("items"):
            return
        try:
            c, st = r["c"], r["state"]
            n = len(st)
            ys, _total = self.wt_tops(r)
            ch = max(1, c.winfo_height())
            top = c.canvasy(0)
            k = r.get("restore")
            if k is not None:  # resume: the layout is already right, so one jump is enough
                k = max(0, min(int(k), n - 1))
                r["restore"] = None
                self.wt_place()
                self.update_idletasks()
                c.yview_moveto(max(0.0, (ys[k] - 8) / float(max(1, r["sreg"]))))
                top = c.canvasy(0)
            bot = top + ch
            self.wt_paint_tex(r, c)
            i0 = 0
            for i, y in enumerate(ys):
                if y <= top + 8:
                    i0 = i
                elif y > bot:
                    break
            i1 = i0
            for i in range(i0, n):
                if ys[i] < bot:
                    i1 = i
                else:
                    break
            r["page"] = i0
            self.r_page.configure(text=f"{i0 + 1} / {n}")
            # only pages close to the viewport are downloaded - the rest waits until they are scrolled to
            lo, hi = max(0, i0 - WT_BEHIND), min(n - 1, i1 + WT_AHEAD)
            mid = (top + bot) / 2
            todo = [i for i in range(lo, hi + 1) if st[i] == 0]
            todo.sort(key=lambda i: abs(ys[i] + r["dims"][i][1] / 2.0 - mid))
            now = time.time()
            for i in todo:
                if r["inflight"] >= WT_MAX_INFLIGHT:
                    break
                self.wt_request(i, gen)
            if r["inflight"] and now - (r.get("lastreq") or now) > 30:
                # no answer came back for work that is supposedly running: never allow that to block
                # the whole chapter (a lost callback used to freeze every later page)
                r["inflight"] = 0
                for i in range(n):
                    if st[i] == 1:
                        st[i] = 0
            for i in range(lo, hi + 1):  # watchdog: a page that never answers must not block the queue
                if st[i] == 1 and now - (r["t0"][i] or now) > 90:
                    st[i], r["tries"][i], r["inflight"] = 0, r["tries"][i] + 1, max(0, r["inflight"] - 1)
                elif st[i] == 3 and now - (r["t0"][i] or now) > 20:
                    st[i] = 0  # a transient hiccup must not leave a page blank for the rest of the chapter
            # drop images far from the viewport: without this a long chapter piles up every page
            # in memory (a tall strip is ~40-60 MB as a Tk image) until the whole app crawls
            klo, khi = i0 - WT_BEHIND - WT_KEEP, i1 + WT_AHEAD + WT_KEEP
            ph = page_box()
            for i in range(n):
                if st[i] == 2 and (i < klo or i > khi):
                    c.itemconfigure(r["items"][i], image=ph)
                    c.itemconfigure(r["texts"][i], text=f"Page {i + 1}")
                    r["photos"].pop(i, None)
                    st[i] = 0
        except Exception:
            pass
        self.after(90, lambda: self.wt_tick(gen))

    def wt_request(self, i, gen):
        r = self.reader
        r["state"][i] = 1
        r["t0"][i] = time.time()
        r["lastreq"] = r["t0"][i]
        wg = r["wgen"]
        ok = load_img(r.get("src"), r["urls"][i], lambda im, i=i, wg=wg: self.wt_loaded(gen, wg, i, im),
                      width=r["dims"][i][0], pool=PAGE_POOL, alive=lambda: gen == self.rgen)
        if ok:
            r["inflight"] += 1  # counted only once the work is really queued
        else:
            r["state"][i] = 3

    def wt_loaded(self, gen, wg, i, im):
        if gen != self.rgen:
            return
        r = self.reader
        r["inflight"] = max(0, r["inflight"] - 1)
        if wg != r["wgen"] or not r.get("items") or i >= len(r["state"]):
            if r.get("state") and i < len(r["state"]):
                r["state"][i] = 0
            return
        c = r["c"]
        if im is None:
            r["tries"][i] += 1
            if r["tries"][i] < 3:
                r["state"][i] = 0
            else:
                r["state"][i] = 3
                c.itemconfigure(r["texts"][i], text=f"Page {i + 1} failed — click to retry")
            return
        self.wt_fix_box(i, im)
        try:
            ph = ImageTk.PhotoImage(im)
        except Exception:
            r["state"][i], r["tries"][i] = 0, r["tries"][i] + 1
            return
        r["photos"][i] = ph  # canvas items do not own their image - keep it alive here
        c.itemconfigure(r["items"][i], image=ph)
        c.itemconfigure(r["texts"][i], text="")
        r["state"][i] = 2

    def wt_fix_box(self, i, im):
        """The page turned out to have a different shape than the estimate - resize its box in place."""
        r = self.reader
        dims = r.get("dims")
        if not dims or i >= len(dims) or not r.get("items"):
            return
        w, h = im.size
        ow, oh = dims[i]
        if (w, h) == (ow, oh):
            return
        c = r["c"]
        top = c.canvasy(0)
        ys = r.get("ys") or self.wt_tops(r)[0]
        y_i = ys[i] if i < len(ys) else 0
        dims[i] = (w, h)
        self.wt_place()
        self.update_idletasks()
        if y_i < top:  # a page above the viewport grew/shrank: keep the text under the user's eyes still
            tot = float(max(1, r["sreg"]))
            c.yview_moveto(min(1.0, max(0.0, (top + h - oh) / tot)))

    def wt_apply_zoom(self):
        r = self.reader
        if not r or not r.get("items") or not self.is_web() or r.get("c") is None:
            return
        c = r["c"]
        ys = r.get("ys") or self.wt_tops(r)[0]
        cur = max(0, min(int(r.get("page", 0)), max(0, len(ys) - 1)))
        off = max(0.0, c.canvasy(0) - ys[cur]) if ys else 0.0
        r["wgen"] += 1
        r["width"] = self.web_width()
        r["dims"] = self.wt_dims(r["urls"], r["width"])
        ph = page_box()
        for i, it in enumerate(r["items"]):
            c.itemconfigure(it, image=ph)
            c.itemconfigure(r["texts"][i], text=f"Page {i + 1}")
        r["photos"].clear()
        r["state"] = [0 if s in (1, 2) else s for s in r["state"]]
        r["tries"] = [0] * len(r["state"])
        r["inflight"] = 0
        if r["zoom"] > 1:
            r["hs"].pack(side="bottom", fill="x", before=r["c"])
        else:
            r["hs"].pack_forget()
        self.wt_place()
        self.update_idletasks()
        ys = r["ys"]
        tot = float(max(1, r["sreg"]))
        c.yview_moveto(min(1.0, max(0.0, (ys[cur] + off) / tot)))

    # --- paged (single / double, LTR / RTL) ---
    def build_paged(self):
        r = self.reader
        c = tk.Canvas(self.rbody, bg=(paper_avg(S("paper")) or READER_BG), highlightthickness=0)
        c.pack(fill="both", expand=True)
        r.update(c=c, imgs={}, req=set(), failed=set(), pan=[0, 0], ph=None, rkey=None, drag=None)
        r["restore"] = None
        r["page"] = min(r["page"], len(r["urls"]) - 1)
        c.bind("<Configure>", lambda e: self.pg_sched())
        c.bind("<ButtonPress-1>", self.pg_press)
        c.bind("<B1-Motion>", self.pg_drag)
        c.bind("<ButtonRelease-1>", self.pg_release)
        self.pg_show()

    def pg_spread(self, p):
        n = len(self.reader["urls"])
        if not self.is_double():
            return [p]
        if p == 0:
            return [0]
        s = p if p % 2 == 1 else p - 1
        return [s] + ([s + 1] if s + 1 < n else [])

    def pg_show(self):
        r, gen, n = self.reader, self.reader["gen"], len(self.reader["urls"])
        sp = self.pg_spread(r["page"])
        want = sp + [i for i in range(sp[-1] + 1, min(n, sp[-1] + 5))] + ([sp[0] - 1] if sp[0] > 0 else [])
        for i in want:
            if i in r["imgs"] or i in r["req"]:
                continue
            ok = load_img(r.get("src"), r["urls"][i], lambda im, i=i: self.pg_loaded(gen, i, im), pool=PAGE_POOL,
                          alive=lambda: gen == self.rgen)
            if ok:
                r["req"].add(i)
            else:
                r["failed"].add(i)
        self.pg_render()

    def pg_loaded(self, gen, i, im):
        if gen != self.rgen:
            return
        r = self.reader
        r["req"].discard(i)
        if im is None:
            r["failed"].add(i)
        else:
            r["imgs"][i] = im
            keep = set(self.pg_spread(r["page"])) | set(range(r["page"] - 2, r["page"] + 6))
            while len(r["imgs"]) > 14:
                old = next((k for k in r["imgs"] if k not in keep), None)
                if old is None:
                    break
                r["imgs"].pop(old)
        if i in self.pg_spread(r["page"]):
            self.pg_render()

    def pg_sched(self):
        r = self.reader
        if r.get("_rs"):
            self.after_cancel(r["_rs"])
        r["_rs"] = self.after(120, self.pg_render)

    def pg_render(self):
        r = self.reader
        c = r.get("c")
        if not c or r.get("urls") is None or self.is_web():
            return
        cw, ch = c.winfo_width(), c.winfo_height()
        if cw < 30:
            return
        sp = self.pg_spread(r["page"])
        n = len(r["urls"])
        self.r_page.configure(text=f"{sp[0] + 1}{'–' + str(sp[-1] + 1) if len(sp) > 1 else ''} / {n}")
        ims = [r["imgs"].get(i) for i in sp]
        c.delete("all")
        tile = paper_tile(self, S("paper"))  # paper surface behind the pages
        if tile:
            ts = tile.width()
            for y in range(0, int(ch) + ts, ts):
                for x in range(0, int(cw) + ts, ts):
                    c.create_image(x, y, anchor="nw", image=tile)
        if any(im is None for im in ims):
            failed = any(i in r["failed"] for i in sp)
            c.create_text(cw / 2, ch / 2, text="Page failed to load — click to retry" if failed else "Loading…", fill=MUTED, font=("Segoe UI", 14))
            return
        rtl = self.is_rtl()
        pairs = list(zip(sp, ims))
        if rtl and len(pairs) == 2:
            ims = ims[::-1]
            pairs = pairs[::-1]
        gap = PAGE_GAP if len(pairs) == 2 else 0
        key = (tuple(sp), cw, ch, r["zoom"], rtl, gap)
        if r["rkey"] != key:
            H = max(im.height for _, im in pairs)
            tw = sum(im.width * H / im.height for _, im in pairs)
            th = max(1, int(H * min(cw / max(1, tw + gap * (len(pairs) - 1)), ch / H) * r["zoom"]))
            parts = [(pi, im.resize((max(1, int(im.width * th / im.height)), th), Image.LANCZOS)) for pi, im in pairs]
            # the spread is laid on black: the gap between the halves becomes the page gutter
            out = Image.new("RGB", (sum(p.width for _, p in parts) + gap * (len(parts) - 1), th), (0, 0, 0))
            x, lays = 0, []
            for pi, p in parts:
                out.paste(p, (x, 0))
                lays.append((pi, x, p.width))
                x += p.width + gap
            r["ph"], r["rkey"], r["size"], r["lays"] = ImageTk.PhotoImage(out), key, out.size, lays
        w, h = r["size"]
        mx, my = max(0, (w - cw) / 2), max(0, (h - ch) / 2)
        r["pan"][0] = max(-mx, min(mx, r["pan"][0]))
        r["pan"][1] = max(-my, min(my, r["pan"][1]))
        cx, cy = cw / 2 + r["pan"][0], ch / 2 + r["pan"][1]
        left, top = cx - w / 2, cy - h / 2
        c.create_image(cx, cy, image=r["ph"])
        if not S("paged_guides"):
            return
        for pi, lx, lw in r["lays"]:  # thick black contour + page number per visible page
            c.create_rectangle(left + lx, top, left + lx + lw, top + h, outline="#000000", width=PAGE_BORDER)
            c.create_text(left + lx + lw / 2, top + h - 14, text=str(pi + 1), fill=MUTED, font=("Segoe UI", 11))
        if len(r["lays"]) == 2:  # little binding mark in the middle of the gutter
            _, lx, lw = r["lays"][0]
            gx = left + lx + lw + gap / 2
            c.create_line(gx, top + h / 2 - 30, gx, top + h / 2 + 30, fill=SILVER_DIM, width=3)

    def pg_step(self, d):
        r = self.reader
        n = len(r["urls"])
        sp = self.pg_spread(r["page"])
        if d > 0:
            if sp[-1] + 1 >= n:
                self.chapter_step(1)
                return
            r["page"] = sp[-1] + 1
        else:
            if sp[0] == 0:
                self.chapter_step(-1)
                return
            r["page"] = self.pg_spread(sp[0] - 1)[0]
        r["pan"] = [0, 0]
        self.pg_show()

    def pg_press(self, e):
        self.reader["drag"] = [e.x, e.y, list(self.reader["pan"]), False]

    def pg_drag(self, e):
        r = self.reader
        d = r.get("drag")
        if not d:
            return
        if abs(e.x - d[0]) + abs(e.y - d[1]) > 5:
            d[3] = True
        if d[3] and r["zoom"] > 1:
            r["pan"] = [d[2][0] + e.x - d[0], d[2][1] + e.y - d[1]]
            self.pg_render()

    def pg_release(self, e):
        r = self.reader
        d, r["drag"] = r.get("drag"), None
        if not d or d[3]:
            return
        sp = self.pg_spread(r["page"])
        if any(i in r["failed"] for i in sp):
            r["failed"].difference_update(sp)
            self.pg_show()
            return
        left = e.x < r["c"].winfo_width() / 2
        self.pg_step(1 if (left == self.is_rtl()) else -1)

    # --- zoom / input ---
    def zoom_by(self, d):
        r = self.reader
        if not r:
            return
        z = r["zoom"]
        if d > 0:
            z = next((v for v in ZOOMS if v > z + 1e-6), ZOOMS[-1])
        else:
            z = next((v for v in reversed(ZOOMS) if v < z - 1e-6), ZOOMS[0])
        self.set_zoom(z)

    def set_zoom(self, z):
        r = self.reader
        r["zoom"] = z
        self.r_zoom.configure(text=f"{int(z * 100)}%")
        if self.is_web():
            if self.zoom_job:
                self.after_cancel(self.zoom_job)
            self.zoom_job = self.after(250, self.wt_apply_zoom)
        else:
            r["pan"] = [0, 0]
            self.pg_render()

    def on_wheel(self, e):
        r = self.reader
        if self.cur != "Reader" or not r or "c" not in r:
            return
        if e.state & 0x4:  # Ctrl + wheel = zoom
            self.zoom_by(1 if e.delta > 0 else -1)
        elif self.is_web():
            if e.state & 0x1:
                r["c"].xview_scroll(-int(e.delta * 0.9), "units")
            else:
                r["c"].yview_scroll(-int(e.delta * 0.9), "units")
        elif r["zoom"] > 1:
            r["pan"][1] += e.delta * 0.6
            self.pg_render()
        else:
            self.pg_step(1 if e.delta < 0 else -1)

    def on_key(self, e):
        r = self.reader
        if self.cur != "Reader" or not r or "c" not in r:
            return
        k = e.keysym
        if k in ("plus", "equal", "KP_Add"):
            self.zoom_by(1)
        elif k in ("minus", "KP_Subtract"):
            self.zoom_by(-1)
        elif k in ("0", "KP_0"):
            self.set_zoom(1.0)
        elif k == "Escape":
            self.reader_back()
        elif self.is_web():
            amt = {"Down": 120, "Up": -120, "space": 650, "Next": 650, "Prior": -650}.get(k)
            if amt:
                r["c"].yview_scroll(amt, "units")
        else:
            fwd = "Left" if self.is_rtl() else "Right"
            back = "Right" if self.is_rtl() else "Left"
            if k in (fwd, "space", "Next", "Down"):
                self.pg_step(1)
            elif k in (back, "Prior", "Up"):
                self.pg_step(-1)


if __name__ == "__main__":
    App().mainloop()