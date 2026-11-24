"""Discover: browse a source (infinite scroll), search every source, roll a random title."""

import random
import re

import flet as ft

from sources import SOURCES, bg, source_hidden
from storage import S

from .core import cover_image, muted, setv
from .library import DENSITY, fill_cover, manga_tile


def enabled_sources(search=False):
    return [s for s in SOURCES.values() if (S("nsfw") or not s.nsfw) and not source_hidden(s.id)
            and (s.can_search() if search else s.kinds())]


class SourcesView:
    TITLE = "Sources"

    def __init__(self, app):
        self.app = app
        self.src = None
        self.kind = "popular"
        self.genre = ""
        self.query = ""
        self.page_no = 0
        self.gen = 0
        self.loading = False
        self.has_more = True
        self.seen = set()
        self.genres = {}
        self.pick = ft.Dropdown(dense=True, width=210, on_select=lambda e: self.select(e.control.value))
        self.kinds = ft.SegmentedButton(selected=["popular"], show_selected_icon=False,
                                        segments=[ft.Segment(value="popular", label=ft.Text("Popular")),
                                                  ft.Segment(value="latest", label=ft.Text("Latest"))],
                                        on_change=self._kind)
        self.genre_pick = ft.Dropdown(dense=True, width=190, hint_text="Genre", visible=False,
                                      on_select=lambda e: self._genre(e.control.value))
        self.search = ft.TextField(hint_text="Search this source", prefix_icon=ft.Icons.SEARCH, dense=True, width=240,
                                   border_radius=20, content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                                   on_submit=lambda e: self._search(e.control.value))
        self.status = muted("")
        self.grid = ft.GridView(expand=True, max_extent=DENSITY["M"], child_aspect_ratio=0.69, spacing=10,
                                run_spacing=10, padding=ft.Padding.only(left=16, right=16, bottom=16),
                                on_scroll=self._scroll, scroll_interval=120,
                                scroll=ft.Scrollbar(thumb_visibility=True, interactive=True, thickness=10, radius=5))
        self.size = ft.SegmentedButton(selected=[S("lib_size") if S("lib_size") in DENSITY else "M"],
                                       segments=[ft.Segment(value=k, label=ft.Text(k)) for k in DENSITY],
                                       on_change=self._size, show_selected_icon=False)
        self.more_btn = ft.TextButton("Load more", icon=ft.Icons.EXPAND_MORE, on_click=lambda e: self.load_more())
        bar = ft.Row([self.pick, self.kinds, self.genre_pick, ft.Container(expand=True), self.search,
                      ft.IconButton(ft.Icons.SHUFFLE, tooltip="Shuffle: a random page", on_click=lambda e: self.shuffle()),
                      self.size],
                     spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.control = ft.Column([ft.Container(bar, padding=ft.Padding.only(left=16, right=16, bottom=8)),
                                  ft.Container(ft.Row([self.status, self.more_btn], spacing=6,
                                                      vertical_alignment=ft.CrossAxisAlignment.CENTER),
                                               padding=ft.Padding.only(left=18, bottom=2)),
                                  self.grid], spacing=0, expand=True)

    def _size(self, e):
        v = list(e.control.selected)[0] if e.control.selected else "M"
        setv("lib_size", v)
        self.grid.max_extent = DENSITY[v]
        self.fill()
        self.app.pump.mark()

    def fill(self):
        """Keep loading pages until the grid is taller than the window (a big screen never scrolls, so
        the scroll trigger alone left only one page on screen)."""
        avail = max(200, self.app.width() - 88 - 32)
        ext = self.grid.max_extent or DENSITY["M"]
        cols = max(1, -(-avail // (ext + 10)))
        cell_h = (avail / cols) / 0.69 + 10
        rows_needed = int((self.app.height() + 900) // cell_h) + 1
        if len(self.grid.controls) < cols * rows_needed:
            self.load_more()

    def show(self):
        srcs = enabled_sources()
        self.pick.options = [ft.DropdownOption(key=s.id, text=s.name + ("  · 18+" if s.nsfw else "")) for s in srcs]
        if not srcs:
            self.status.value = "No sources enabled. Turn some on in Settings."
            return
        if self.src is None or self.src not in SOURCES or source_hidden(self.src):
            want = DB_last_source() or srcs[0].id
            self.src = want if any(s.id == want for s in srcs) else srcs[0].id
            self.pick.value = self.src
            self.reload()
        size = S("lib_size") if S("lib_size") in DENSITY else "M"
        self.grid.max_extent = DENSITY[size]
        self.size.selected = [size]

    def select(self, sid, query=""):
        self.src = sid
        setv("last_source", sid)
        self.pick.value = sid
        self.genre, self.query = "", query
        self.search.value = query
        self.reload()

    def _kind(self, e):
        self.kind = list(e.control.selected)[0]
        self.query = ""
        self.search.value = ""
        self.reload()

    def _genre(self, label):
        self.genre = self.genres.get(label, "")
        self.reload()

    def _search(self, q):
        self.query = (q or "").strip()
        self.reload()

    def reload(self, start=1):
        self.gen += 1
        self.page_no = start - 1
        self.has_more = True
        self.loading = False
        self.seen = set()
        self.grid.controls = []
        src = SOURCES.get(self.src)
        if not src:
            return
        kinds = src.kinds()
        self.kinds.visible = len(kinds) > 1
        if self.kind not in kinds and kinds:
            self.kind = kinds[0]
            self.kinds.selected = [self.kind]
        self.search.visible = src.can_search()
        gen = self.gen
        bg(src.genres, lambda r, e: self._genres_ready(gen, r))
        self.load_more()

    def _genres_ready(self, gen, r):
        if gen != self.gen:
            return
        self.genres = {"All genres": ""}
        self.genres.update({lab: val for lab, val in (r or [])})
        self.genre_pick.options = [ft.DropdownOption(x) for x in self.genres]
        self.genre_pick.visible = len(self.genres) > 1

    def load_more(self):
        src = SOURCES.get(self.src)
        if not src or self.loading or not self.has_more:
            return
        self.loading = True
        self.page_no += 1
        n, gen = self.page_no, self.gen
        kind = "search" if self.query else self.kind
        q, g = self.query, self.genre
        self.status.value = f"Loading page {n}…"
        bg(lambda: src.listing(kind, n, q, g), lambda r, e: self._more(gen, r, e))
        self.app.pump.mark()

    def _more(self, gen, r, e):
        if gen != self.gen:
            return
        self.loading = False
        if e:
            self.status.value = f"Couldn't load: {str(e)[:100]}"
            return
        fresh = [x for x in (r or []) if x["url"] not in self.seen]
        self.seen.update(x["url"] for x in fresh)
        if not fresh:
            self.has_more = False
            self.more_btn.visible = False
            self.status.value = f"{len(self.grid.controls)} titles · end of results"
            return
        alive = lambda: gen == self.gen
        self.grid.controls.extend(manga_tile(m, self.app.open_manga, lambda m, pos=None: self.app.manga_menu(m, pos=pos),
                                             alive=alive)
                                  for m in fresh)
        self.status.value = f"{len(self.grid.controls)} titles · page {self.page_no}"
        self.more_btn.visible = True
        self.fill()

    def _scroll(self, e: ft.OnScrollEvent):
        self.app.note_activity()
        if e.max_scroll_extent and e.pixels > e.max_scroll_extent - 900:
            self.load_more()

    def shuffle(self):
        src = SOURCES.get(self.src)
        if not src:
            return
        top = len(getattr(src, "WT_RANKS", [])) if src.api == "webtoons" else 15
        self.query = ""
        self.reload(start=random.randint(2, max(2, top)))


def DB_last_source():
    from storage import DB
    return DB["set"].get("last_source")


class SearchView:
    TITLE = "Search"

    def __init__(self, app):
        self.app = app
        self.gen = 0
        self.seen = set()
        self.q = ft.TextField(hint_text="Search every source…", prefix_icon=ft.Icons.SEARCH, autofocus=True,
                              border_radius=24, expand=True, on_submit=lambda e: self.run())
        self.res = ft.ListView(expand=True, spacing=14, padding=ft.Padding.only(left=16, right=16, bottom=16))
        self.control = ft.Column([ft.Container(ft.Row([self.q, ft.FilledButton("Search", on_click=lambda e: self.run())]),
                                               padding=ft.Padding.only(left=16, right=16, bottom=10)), self.res],
                                 spacing=0, expand=True)

    def show(self):
        pass

    def run(self):
        q = (self.q.value or "").strip()
        if not q:
            return
        self.gen += 1
        gen = self.gen
        self.seen = set()
        self.res.controls = []
        srcs = enabled_sources(search=True)
        if not srcs:
            self.res.controls = [muted("No searchable sources enabled. Check Settings.", 14)]
        for src in srcs:
            head = ft.Text(f"{src.name} · searching…", size=15, weight=ft.FontWeight.BOLD)
            row = ft.Row([], spacing=10, scroll=ft.ScrollMode.AUTO)
            sec = ft.Column([head, row], spacing=6)
            self.res.controls.append(sec)
            bg(lambda src=src: src.listing("search", 1, q),
               lambda r, e, src=src, head=head, row=row, sec=sec: self.done(gen, src, q, head, row, sec, r, e))
        self.app.pump.mark()

    def done(self, gen, src, q, head, row, sec, r, e):
        if gen != self.gen:
            return
        if e:
            head.value = f"{src.name} · unavailable"
            head.color = ft.Colors.ON_SURFACE_VARIANT
            return
        toks = [t for t in re.findall(r"[a-z0-9]+", q.lower()) if len(t) > 1] or [q.lower()]
        hits = []
        for x in r or []:
            t = x["title"].lower()
            key = re.sub(r"[^a-z0-9]+", "", t)
            if all(tok in t for tok in toks) and key not in self.seen:
                self.seen.add(key)
                hits.append(x)
        if not hits:
            self.res.controls.remove(sec)
            return
        head.value = f"{src.name} · {len(hits)} result{'s' if len(hits) != 1 else ''}"
        alive = lambda: gen == self.gen
        row.controls = [ft.Container(manga_tile(m, self.app.open_manga, lambda m, pos=None: self.app.manga_menu(m, pos=pos),
                                                alive=alive),
                                     width=130, height=188) for m in hits[:20]]
        if len(hits) > 6:
            row.controls.append(ft.TextButton("See all →", on_click=lambda e: self.see_all(src.id, q)))

    def see_all(self, sid, q):
        self.app.show("Sources")
        self.app.views["Sources"].select(sid, q)




class RandomView:
    """Four random titles at once from your enabled sources: a 2x2 grid of rectangles that fills the window, re-roll, earlier rolls below."""
    TITLE = "Random"
    N = 4

    def __init__(self, app):
        self.app = app
        self.seen = set()
        self.history = []
        self.slots = []
        self.gen = 0
        self.only = ""                     # "" = every enabled source
        self.src_pick = ft.Dropdown(dense=True, width=220, value="", on_select=lambda e: self._only(e.control.value))
        self.roll_btn = ft.FilledButton("Roll again", icon=ft.Icons.CASINO, on_click=lambda e: self.roll())
        self.grid = ft.Column(spacing=14, expand=True)        # two rows of two, fills the window
        self.trail = ft.Row([], spacing=8, scroll=ft.ScrollMode.AUTO)
        self.trail_box = ft.Container(ft.Column([muted("Earlier rolls", 12), self.trail], spacing=6, tight=True),
                                      padding=ft.Padding.only(left=16, right=16, bottom=12), visible=False)
        bar = ft.Row([self.src_pick, ft.Container(expand=True), self.roll_btn],
                     vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.control = ft.Column([ft.Container(bar, padding=ft.Padding.only(left=16, right=16, bottom=10)),
                                  ft.Container(self.grid, expand=True,
                                               padding=ft.Padding.only(left=16, right=16, bottom=10)),
                                  self.trail_box], spacing=0, expand=True)

    def show(self):
        srcs = enabled_sources()
        self.src_pick.options = [ft.DropdownOption(key="", text="All enabled sources")] +             [ft.DropdownOption(key=x.id, text=x.name) for x in srcs]
        if not self.slots:
            self.roll()

    def _only(self, v):
        self.only = v or ""
        self.roll()

    def slot(self):
        return ft.Container(ft.Column([ft.ProgressRing(width=28, height=28), muted("Rolling…", 12)],
                                      horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True, spacing=8),
                            alignment=ft.Alignment(0, 0), border_radius=16, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                            expand=1)

    def roll(self):
        self.gen += 1
        gen = self.gen
        for c in self.slots:
            m = getattr(c, "data", None)
            if m and m not in self.history:
                self.history.insert(0, m)
        self.slots = [self.slot() for _ in range(self.N)]
        self.lay()
        self.render_trail()
        only = self.only
        for k in range(self.N):
            bg(lambda: random_pick(self.seen, only), lambda r, e, k=k: self.done(gen, k, r, e))
        self.app.pump.mark()

    def done(self, gen, k, r, e):
        if gen != self.gen:
            return
        if e or not r:
            self.slots[k] = ft.Container(ft.Column([ft.Icon(ft.Icons.CASINO_OUTLINED, size=30),
                                                            muted("No luck on this one", 12)],
                                                           horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
                                                 alignment=ft.Alignment(0, 0), border_radius=16,
                                                 bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, expand=1)
            return
        self.seen.add(r["url"])
        self.slots[k] = self.card(r)
        self.lay()

    def lay(self):
        """Put the four slots in a 2x2 grid; each quarter takes an equal share of the window."""
        s = self.slots
        self.grid.controls = [ft.Row(s[i:i + 2], spacing=14, expand=1, vertical_alignment=ft.CrossAxisAlignment.STRETCH)
                              for i in range(0, len(s), 2)]

    def card(self, m):
        """Rectangle: the cover fills its height on the left, title / source / genres / actions on the right."""
        src = SOURCES.get(m["source"])
        in_lib = self.app.find_bm(m) is not None
        bm = ft.IconButton(ft.Icons.BOOKMARK if in_lib else ft.Icons.BOOKMARK_ADD_OUTLINED, tooltip="Add to Library")

        def save(e):
            on = self.app.toggle_bm(m)
            bm.icon = ft.Icons.BOOKMARK if on else ft.Icons.BOOKMARK_ADD_OUTLINED
            self.app.pump.mark()
        bm.on_click = save
        chips = [ft.Container(ft.Text(g, size=12), bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH, border_radius=10,
                              padding=ft.Padding.symmetric(horizontal=10, vertical=4)) for g in (m.get("genres") or [])[:5]]
        cover = ft.GestureDetector(
            ft.Container(fill_cover(m), aspect_ratio=0.69, border_radius=12, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                         ink=True, on_click=lambda e: self.app.open_manga(m)),
            on_secondary_tap_down=lambda e: self.app.manga_menu(m, pos=None), mouse_cursor=ft.MouseCursor.CLICK)
        info = ft.Column([
            ft.Text(m["title"], size=22, weight=ft.FontWeight.BOLD, max_lines=4, overflow=ft.TextOverflow.ELLIPSIS),
            muted(src.name if src else m["source"], 14),
            ft.Row(chips, spacing=6, run_spacing=6, wrap=True),
            ft.Container(expand=True),
            ft.Row([ft.FilledButton("Open", icon=ft.Icons.AUTO_STORIES, on_click=lambda e: self.app.open_manga(m)),
                    bm], spacing=6)],
            spacing=8, expand=True)
        return ft.Container(ft.Row([cover, info], spacing=18, vertical_alignment=ft.CrossAxisAlignment.STRETCH),
                            data=m, expand=1, padding=16, border_radius=16, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW)

    def render_trail(self):
        self.trail.controls = [ft.Container(cover_image(m, 56, 80, 8), on_click=lambda e, m=m: self.app.open_manga(m),
                                            tooltip=m["title"]) for m in self.history[:40]]
        self.trail_box.visible = bool(self.history)


def random_pick(avoid, only=""):
    """Worker: one random title from a random enabled source (or the chosen one)."""
    srcs = [s for s in enabled_sources() if not only or s.id == only]
    random.shuffle(srcs)
    err = None
    for s in srcs[:6]:
        kind = "popular" if "popular" in s.kinds() else s.kinds()[0]
        top = len(getattr(s, "WT_RANKS", [])) if s.api == "webtoons" else 20
        page = random.randint(1, max(1, top))
        while True:
            try:
                items = [x for x in s.listing(kind, page) if x["url"] not in avoid]
            except Exception as e:
                err, items = e, []
                if page == 1:
                    break
            if items:
                pick = random.choice(items)
                avoid.add(pick["url"])
                return pick
            if page == 1:
                break
            page = max(1, page // 2)
    if err:
        raise err
    return None
