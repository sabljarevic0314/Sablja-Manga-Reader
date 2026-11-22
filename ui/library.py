"""Library: a compact, adaptive cover grid (columns follow the window width)."""

import asyncio
import threading
import time

import flet as ft

from desktop import norm_title
from sources import SOURCES, Q, downloaded_manga
from storage import DB, S, pkey, save_db_soon

from .core import dirty, setv, thumb, thumb_cached

DENSITY = {"S": 118, "M": 146, "L": 182}       # max card width per size
TW, TH = 240, 340                               # thumbnail file size (shared by every grid)
DL_CHIP = "__downloaded__"


def fill_cover(m, alive=None):
    """Cover that fills its grid cell."""
    box = ft.Container(expand=True, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH)
    url = m.get("cover")

    def put(path):
        if path:
            box.content = ft.Image(src=path, fit=ft.BoxFit.COVER, expand=True, gapless_playback=True)
            dirty()

    have = thumb_cached(url, TW, TH)
    if have:
        box.content = ft.Image(src=have, fit=ft.BoxFit.COVER, expand=True, gapless_playback=True)
    elif url:
        thumb(SOURCES.get(m.get("source")), url, TW, TH, put, alive)
    return box


def _xy(e):
    g = getattr(e, "global_position", None)
    return (g.x, g.y) if g is not None else None


def manga_tile(m, on_open, on_menu, badge=0, progress=None, sub=None, alive=None):
    """One grid cell: cover, title on a gradient, optional 'new' badge and read-progress bar."""
    layers = [fill_cover(m, alive),
              ft.Container(gradient=ft.LinearGradient(begin=ft.Alignment(0, -0.1), end=ft.Alignment(0, 1),
                                                      colors=["#00000000", "#e6000000"]), expand=True),
              ft.Container(ft.Column([ft.Text(m.get("title", "?"), size=12, weight=ft.FontWeight.W_600, color="#ffffff",
                                              max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                      *( [ft.Text(sub, size=10, color="#c8cdd6", max_lines=1)] if sub else [])],
                                     spacing=1, tight=True),
                           left=8, right=8, bottom=8 if progress is None else 10)]
    if badge:
        layers.append(ft.Container(ft.Text(f"+{badge}", size=11, weight=ft.FontWeight.BOLD, color="#06211e"),
                                   bgcolor="#5fd0c2", border_radius=10, padding=ft.Padding.symmetric(horizontal=7, vertical=2),
                                   right=6, top=6))
    if m.get("_alts"):
        layers.append(ft.Container(ft.Text(f"{len(m['_alts']) + 1} sources", size=10, color="#ffffff"),
                                   bgcolor="#99000000", border_radius=10, padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                                   left=6, top=6))
    if progress is not None:
        layers.append(ft.Container(ft.ProgressBar(value=max(0.02, min(1, progress)), bar_height=3, color="#5fd0c2",
                                                  bgcolor="#55ffffff"), left=0, right=0, bottom=0))
    return ft.GestureDetector(
        ft.Container(ft.Stack(layers, expand=True), border_radius=12, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                     ink=True, on_click=lambda e: on_open(m)),
        on_secondary_tap_down=lambda e: on_menu(m, _xy(e)), on_long_press_start=lambda e: on_menu(m, _xy(e)),
        mouse_cursor=ft.MouseCursor.CLICK)


def group_library(items):
    """Same series from several sources becomes one card (nothing merged in db.json)."""
    if not S("group_dupes"):
        return items
    skip = set(DB["meta"].get("no_group") or [])
    buckets = {}
    for b in items:
        n = norm_title(b["title"])
        buckets.setdefault(n if n and pkey(b) not in skip else pkey(b), []).append(b)
    out, done = [], set()
    for b in items:
        n = norm_title(b["title"])
        k = n if n and pkey(b) not in skip else pkey(b)
        if k in done:
            continue
        done.add(k)
        g = buckets[k]
        if len({x["source"] for x in g}) < 2:
            out.extend(g)
            continue
        lead = max(g, key=lambda x: DB["progress"].get(pkey(x), {}).get("ts", 0))
        out.append({**lead, "_alts": [x for x in g if x is not lead]})
    return out


def read_progress(m):
    """Fraction of chapters read, when the chapter count is known (else None)."""
    k = pkey(m)
    total = (DB["meta"].get("chapter_seen") or {}).get(k)
    read = len(DB["progress"].get(k, {}).get("read") or [])
    if not total or not read:
        return None
    return read / total


class LibraryView:
    TITLE = "Library"

    def __init__(self, app):
        self.app = app
        self.folder = "All"
        self.gen = 0
        self.query = ""
        self.chips = ft.Row([], spacing=6, scroll=ft.ScrollMode.AUTO)
        self.filter = ft.TextField(hint_text="Filter your library", prefix_icon=ft.Icons.SEARCH, dense=True,
                                   width=240, border_radius=20, content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                                   on_change=self._filter)
        self.sort = ft.Dropdown(value=S("lib_sort") if S("lib_sort") in ("Recent", "Title", "Rating", "New") else "Recent",
                                options=[ft.DropdownOption(x) for x in ("Recent", "Title", "Rating", "New")], dense=True,
                                width=130, on_select=lambda e: (setv("lib_sort", e.control.value), self.show()))
        self.size = ft.SegmentedButton(selected=[S("lib_size") if S("lib_size") in DENSITY else "M"],
                                       segments=[ft.Segment(value=k, label=ft.Text(k)) for k in DENSITY],
                                       on_change=self._size, show_selected_icon=False)
        self.grid = ft.GridView(expand=True, max_extent=DENSITY["M"], child_aspect_ratio=0.69, spacing=10,
                                run_spacing=10, padding=ft.Padding.only(left=16, right=16, bottom=16),
                                scroll=ft.Scrollbar(thumb_visibility=True, interactive=True, thickness=10, radius=5))
        self.empty = ft.Container(ft.Text("Nothing here yet.\nOpen a manga from Sources and press Bookmark.",
                                          text_align=ft.TextAlign.CENTER, color=ft.Colors.ON_SURFACE_VARIANT, size=14),
                                  alignment=ft.Alignment(0, -0.3), expand=True, visible=False)
        self.cont = ft.FilledButton("Continue", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: self.continue_last())
        bar = ft.Row([self.chips, ft.Container(expand=True), self.filter, self.sort, self.size], spacing=8,
                     vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.control = ft.Column([ft.Container(bar, padding=ft.Padding.only(left=16, right=16, bottom=10)),
                                  ft.Stack([self.grid, self.empty], expand=True)], spacing=0, expand=True)

    def header_controls(self):
        l = DB["last"]
        self.cont.visible = bool(l)
        if l:
            self.cont.content = f"Continue: {l['manga']['title'][:28]}"
        return [self.cont]

    def continue_last(self):
        if DB["last"]:
            self.app.open_manga(DB["last"]["manga"], resume=True)

    def _filter(self, e):
        self.query = (e.control.value or "").strip().lower()
        self.show()

    def _size(self, e):
        v = list(e.control.selected)[0] if e.control.selected else "M"
        setv("lib_size", v)
        self.show()

    def set_folder(self, f):
        self.folder = f
        self.show()

    def show(self):
        self.gen += 1
        gen = self.gen
        alive = lambda: gen == self.gen and self.app.cur == "Library"
        bms = DB["bookmarks"]
        if self.folder not in ["All", "Unsorted", DL_CHIP] + DB["folders"]:
            self.folder = "All"
        dls = downloaded_manga()
        chips = [("All", f"All {len(bms)}"), (DL_CHIP, f"Downloaded {len(dls)}")]
        if DB["folders"]:
            chips.append(("Unsorted", "Unsorted"))
        chips += [(f, f) for f in DB["folders"]]
        self.chips.controls = [ft.Chip(label=ft.Text(lab), selected=k == self.folder,
                                       on_select=lambda e, k=k: self.set_folder(k), show_checkmark=False)
                               for k, lab in chips]
        self.chips.controls.append(ft.IconButton(ft.Icons.CREATE_NEW_FOLDER_OUTLINED, tooltip="New folder",
                                                 on_click=lambda e: self.app.new_folder(after=self.show)))
        if self.folder == "All":
            shown = list(bms)
        elif self.folder == DL_CHIP:
            shown = dls
        elif self.folder == "Unsorted":
            shown = [b for b in bms if not b.get("folder")]
        else:
            shown = [b for b in bms if b.get("folder") == self.folder]
        if self.folder != DL_CHIP:
            shown = group_library(shown)
        if self.query:
            shown = [m for m in shown if self.query in m.get("title", "").lower()]
        how = self.sort.value
        if how == "Title":
            shown.sort(key=lambda m: m.get("title", "").lower())
        elif how == "Rating":
            shown.sort(key=lambda m: -(DB["ratings"].get(pkey(m)) or {}).get("score", 0))
        elif how == "New":
            shown.sort(key=lambda m: -self.badge(m))
        else:
            shown.sort(key=lambda m: -max(DB["progress"].get(pkey(x), {}).get("ts", 0) for x in [m, *(m.get("_alts") or [])]))
        size = S("lib_size") if S("lib_size") in DENSITY else "M"
        self.grid.max_extent = DENSITY[size]
        self.grid.controls = [manga_tile(m, self.app.open_manga, lambda m, pos=None: self.app.manga_menu(m, after=self.show, pos=pos),
                                         badge=self.badge(m), progress=read_progress(m), alive=alive) for m in shown]
        self.empty.visible = not shown
        self.app.pump.mark()

    def badge(self, m):
        return max((self.app.fresh.get(pkey(x), {}).get("n", 0) for x in [m, *(m.get("_alts") or [])]), default=0)

    # ----- new-chapter check (one polite background walk every 30 min) -----
    async def check_new_loop(self):
        await asyncio.sleep(8)
        while True:
            self.check_new()
            await asyncio.sleep(30 * 60)

    def check_new(self):
        if getattr(self, "_thr", None) is not None and self._thr.is_alive():
            return

        def run():
            out, totals = {}, {}
            for b in list(DB["bookmarks"]):
                src = SOURCES.get(b.get("source"))
                if not src or not b.get("url"):
                    continue
                try:
                    chs = (src.details(b["url"]) or {}).get("chapters") or []
                except Exception:
                    continue
                key = pkey(b)
                if chs:
                    totals[key] = len(chs)
                prog = DB["progress"].get(key, {})
                seen, cur, i_last = set(prog.get("read") or []), prog.get("chapter"), -1
                for i, c in enumerate(chs):
                    if c.get("url") == cur or c.get("url") in seen:
                        i_last = i
                if i_last >= 0 and len(chs) - 1 - i_last > 0:
                    out[key] = {"n": len(chs) - 1 - i_last}
                time.sleep(0.5)                  # polite: one series at a time, with a pause
            Q.put((self._fresh_done, (out, totals)))

        self._thr = threading.Thread(target=run, daemon=True)
        self._thr.start()

    def _fresh_done(self, out, totals):
        """chapter_seen remembers each series' chapter count; a series seen for the first time only sets
        that baseline, so turning toasts on never floods you with old chapters."""
        seen = DB["meta"].setdefault("chapter_seen", {})
        names = {pkey(b): b.get("title", "?") for b in DB["bookmarks"]}
        grew = [(names.get(k, "?"), t - seen[k]) for k, t in totals.items()
                if seen.get(k) is not None and t > seen[k] and k in out]
        seen.update(totals)
        save_db_soon()
        if grew and S("notify_new"):
            n = sum(c for _, c in grew)
            shown = ", ".join(f"{t} (+{c})" for t, c in grew[:3]) + (f" and {len(grew) - 3} more" if len(grew) > 3 else "")
            self.app.notify(f"{n} new chapter{'s' if n != 1 else ''}", shown)
        old = self.app.fresh
        self.app.fresh = out
        if old != out and self.app.cur == "Library":
            self.show()
