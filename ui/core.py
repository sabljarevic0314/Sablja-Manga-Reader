"""Shared plumbing for the Flet UI: theme, the UI pump, and image files for Flutter.

Speed rules this module exists for:
- Worker threads never touch controls. They put (callback, result) on sources.Q; the pump runs the
  callbacks on the UI loop and sends ONE page.update() per batch.
- Flutter gets image *files* from the shared disk cache, never bytes over the socket. Covers are
  pre-shrunk to small JPEG thumbnails so a grid of 300 covers decodes instantly.
- Every network request still goes through Source.get, which keeps the per-host pacing and 429
  backoff, so a fast UI never means hammering a site.
"""

import asyncio
import os
import queue
import threading
import time

import flet as ft
from PIL import Image, ImageOps

from sources import IMG_POOL, PAGE_POOL, Q, SOURCES
from storage import DB, S, cache_path, log_error, save_db_soon

ACCENT = "#5fd0c2"
PALETTES = {
    "Black": dict(bg="#0f1012", surface="#16171b", card="#1d1f24", card_hi="#26292f", line="#2a2d33",
                  text="#e7e9ed", muted="#8a8f99", reader="#0b0b0d"),
    "White": dict(bg="#eef0f3", surface="#f7f8fa", card="#ffffff", card_hi="#e9ebef", line="#d4d8de",
                  text="#1f2126", muted="#6a707b", reader="#d5d8de"),
}


def pal():
    return PALETTES.get(S("paper")) or PALETTES["Black"]


def apply_theme(page: ft.Page):
    p = pal()
    dark = S("paper") != "White"
    scheme = ft.ColorScheme(
        primary=ACCENT if dark else "#00796b",
        surface=p["surface"], on_surface=p["text"], on_surface_variant=p["muted"],
        surface_container_lowest=p["bg"], surface_container_low=p["card"], surface_container=p["card"],
        surface_container_high=p["card_hi"], surface_container_highest=p["card_hi"], outline_variant=p["line"])
    theme = ft.Theme(color_scheme_seed=ACCENT, color_scheme=scheme)
    page.theme = page.dark_theme = theme
    page.theme_mode = ft.ThemeMode.DARK if dark else ft.ThemeMode.LIGHT
    page.bgcolor = p["bg"]


def setv(k, v):
    DB["set"][k] = v
    save_db_soon(0.3)


# ---------------- UI pump ----------------

PUMP = None          # the running Pump; set by the app


def dirty():
    """Ask for one page.update() on the next pump tick (cheaper than updating controls one by one)."""
    if PUMP is not None:
        PUMP.mark()


def post(fn, *args):
    """Run fn(*args) on the UI loop (safe from any thread)."""
    Q.put((lambda r, e: fn(*args), (None, None)))


class Pump:
    """Drains sources.Q on the UI loop; one page.update() per batch."""

    def __init__(self, page: ft.Page):
        global PUMP
        self.page = page
        self.dirty = False
        PUMP = self

    def mark(self):
        self.dirty = True

    async def run(self):
        while True:
            t0, n = time.perf_counter(), 0
            while time.perf_counter() - t0 < 0.014:
                try:
                    cb, res = Q.get_nowait()
                except queue.Empty:
                    break
                n += 1
                try:
                    cb(*res)
                except Exception as ex:
                    log_error("ui callback", ex)
            if n or self.dirty:
                self.dirty = False
                try:
                    self.page.update()
                except RuntimeError as ex:
                    if "destroyed session" in str(ex):
                        return                      # window closed
                    log_error("page.update", ex)
                except Exception as ex:
                    log_error("page.update", ex)
            await asyncio.sleep(0.016 if n else 0.035)


# ---------------- image files ----------------

_inflight: dict[str, list] = {}
_inflight_lock = threading.Lock()


def download(src, url, alive=None):
    """Fetch url into the shared disk cache (once). Returns the file path or raises."""
    p = cache_path(url)
    if os.path.exists(p):
        return p
    data, last = None, None
    for attempt in range(2):
        if alive and not alive():
            raise InterruptedError
        try:
            data = src.get(url).content
            if data:
                break
            last = RuntimeError("empty image response")
        except Exception as e:
            last = e
            resp = getattr(e, "response", None)
            if resp is not None and 400 <= getattr(resp, "status_code", 0) < 500:
                break                       # 404/403 will not fix itself
        if attempt < 1:
            time.sleep(0.35)
    if not data:
        raise last or RuntimeError("image download failed")
    tmp = f"{p}.{threading.get_ident()}.part"
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
    return p


def thumb_path(url, w, h):
    return f"{cache_path(url)}.{w}x{h}.jpg"


def thumb_cached(url, w, h):
    p = thumb_path(url, w, h) if url else None
    return p if p and os.path.exists(p) else None


def thumb(src, url, w, h, cb, alive=None):
    """Cover as a small cropped JPEG file; cb(path or None) runs on the UI loop. Duplicate requests
    for the same thumbnail share one download."""
    if not src or not url:
        cb(None)
        return
    tp = thumb_path(url, w, h)
    if os.path.exists(tp):
        cb(tp)
        return
    with _inflight_lock:
        if tp in _inflight:
            _inflight[tp].append(cb)
            return
        _inflight[tp] = [cb]

    def work():
        out = None
        try:
            if alive and not alive():
                raise InterruptedError
            p = download(src, url, alive)
            im = Image.open(p)
            try:
                im.draft("RGB", (w * 2, h * 2))
            except Exception:
                pass
            ImageOps.fit(im.convert("RGB"), (w, h), Image.Resampling.LANCZOS).save(tp, "JPEG", quality=86)
            out = tp
        except InterruptedError:
            pass
        except Exception as e:
            log_error("cover", e)
            try:
                if os.path.exists(cache_path(url)):
                    os.remove(cache_path(url))
            except OSError:
                pass
        with _inflight_lock:
            cbs = _inflight.pop(tp, [])
        for c in cbs:
            Q.put((lambda r, e, c=c: c(out), (None, None)))

    IMG_POOL.submit(work)


SPLIT_H = 4000          # very tall webtoon strips are cut so Flutter never hits GPU texture limits
SPLIT_MIN = 6000


def page_parts(src, url, alive=None):
    """Worker: a reader page as [(file, width, height)], split into pieces when it is extremely tall."""
    p = download(src, url, alive)
    with Image.open(p) as im:
        w, h = im.size
        fmt = (im.format or "").upper()
        if h > SPLIT_MIN and h > 2.5 * w:
            parts = []
            for i, y in enumerate(range(0, h, SPLIT_H)):
                sp = f"{p}.s{i}.jpg"
                bh = min(SPLIT_H, h - y)
                if not os.path.exists(sp):
                    im.convert("RGB").crop((0, y, w, y + bh)).save(sp, "JPEG", quality=90)
                parts.append((sp, w, bh))
            return parts
        if fmt not in ("JPEG", "PNG", "GIF", "WEBP", "BMP"):
            cp = p + ".jpg"
            if not os.path.exists(cp):
                im.convert("RGB").save(cp, "JPEG", quality=92)
            return [(cp, w, h)]
    return [(p, w, h)]


def load_page(src, url, cb, alive=None):
    """cb(parts or None, error) on the UI loop."""
    def work():
        try:
            res = (page_parts(src, url, alive), None)
        except Exception as e:
            res = (None, e)
        Q.put((cb, res))
    PAGE_POOL.submit(work)


# ---------------- small widgets ----------------

def cover_image(m, w, h, radius=10, alive=None, fit=ft.BoxFit.COVER):
    """A cover that fills in when its thumbnail is ready. Returns the Container."""
    box = ft.Container(width=w, height=h, border_radius=radius, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                       clip_behavior=ft.ClipBehavior.ANTI_ALIAS)
    url = m.get("cover")
    tw, th = int(w * 1.5), int(h * 1.5)       # sharp on 150% displays, still small
    have = thumb_cached(url, tw, th)

    def put(path):
        if path:
            box.content = ft.Image(src=path, width=w, height=h, fit=fit, gapless_playback=True)
            dirty()

    if have:
        box.content = ft.Image(src=have, width=w, height=h, fit=fit, gapless_playback=True)
    elif url:
        thumb(SOURCES.get(m.get("source")), url, tw, th, put, alive)
    return box


def card(*controls, padding=14, **kw):
    return ft.Container(ft.Column(list(controls), spacing=8, tight=True), padding=padding, border_radius=16,
                        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, **kw)


def title(text, size=24):
    return ft.Text(text, size=size, weight=ft.FontWeight.BOLD)


def muted(text, size=12, **kw):
    return ft.Text(text, size=size, color=ft.Colors.ON_SURFACE_VARIANT, **kw)


def age_str(ts):
    try:
        d = max(0, int(time.time() - float(ts)))
    except Exception:
        return ""
    if d < 90:
        return "just now"
    if d < 3600:
        return f"{d // 60} min ago"
    if d < 86400:
        return f"{d // 3600} h ago"
    if d < 86400 * 30:
        return f"{d // 86400} d ago"
    return time.strftime("%d %b %Y", time.localtime(float(ts)))


def fmt_time(sec):
    m = int((sec or 0) // 60)
    if m < 1:
        return "<1 min" if sec else "—"
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m} min"
