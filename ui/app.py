"""App shell: nav rail (the Sablja Fitness layout), header, view switching, keyboard, lock, tray, quitting."""

import asyncio
import os
import time

import flet as ft

from assets import make_icon, make_icon_file
from config import DATA
from desktop import HAVE_TRAY, Tray, pin_ok
from sources import SOURCES, rebuild_sources
from storage import DB, S, log_error, pkey, save_db

from .core import Pump, apply_theme, muted, post, setv
from .gifs import GifSpot
from .updates import Updates

NAV = [("Library", ft.Icons.COLLECTIONS_BOOKMARK_OUTLINED, ft.Icons.COLLECTIONS_BOOKMARK),
       ("History", ft.Icons.HISTORY, ft.Icons.HISTORY),
       ("Rating", ft.Icons.STAR_OUTLINE, ft.Icons.STAR),
       ("Sources", ft.Icons.EXPLORE_OUTLINED, ft.Icons.EXPLORE),
       ("Search", ft.Icons.SEARCH, ft.Icons.SEARCH),
       ("Random", ft.Icons.CASINO_OUTLINED, ft.Icons.CASINO),
       ("Downloads", ft.Icons.DOWNLOAD_OUTLINED, ft.Icons.DOWNLOAD)]
RAIL_W = 88
APP = None            # the running App (handy for tests)


class App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.pump = Pump(page)
        self.views = {}
        self.cur = None
        self.back_to = "Library"
        self._act = time.time()
        self._locked = False
        self.fresh = {}                    # series key -> {"n": new chapters}
        self.updates = Updates(self)
        self.tray = None

    # ----- small services for views -----
    def note_activity(self, e=None):
        self._act = time.time()

    def last_activity(self):
        return self._act

    def hidden(self):
        try:
            return bool(self.page.window.minimized) or self._locked
        except Exception:
            return False

    def width(self):
        return self.page.width or 1200

    def height(self):
        return self.page.height or 800

    def view_name(self):
        return self.cur

    def toast(self, msg, error=False):
        self.page.show_dialog(ft.SnackBar(ft.Text(msg), bgcolor=ft.Colors.RED_700 if error else None,
                                          behavior=ft.SnackBarBehavior.FLOATING, duration=2600,
                                          persist=False))

    # ----- tray + new-chapter toasts (only while Settings → Notifications is on) -----
    def set_tray(self):
        want = bool(S("notify_new")) and HAVE_TRAY
        if want and self.tray is None:
            self.tray = Tray(make_icon(64), post, [("Open Sablja Manga Reader App", self.restore, True),
                                                   ("Quit", lambda: self.page.run_task(self.quit), False)])
            if not self.tray.start():
                self.tray = None
        elif not want and self.tray is not None:
            self.tray.stop()
            self.tray = None

    def notify(self, title, text):
        if self.tray is not None:
            if self._locked:                    # a toast must not show titles while the app is locked
                title, text = "Sablja Manga Reader App", title
            self.tray.notify(title, text)

    def restore(self):
        self.page.window.minimized = False
        self.page.run_task(self.page.window.to_front)
        self.pump.mark()

    # ----- quitting: every way out saves first -----
    def on_window(self, e):
        if e.type == ft.WindowEventType.CLOSE:
            self.page.run_task(self.quit)

    async def quit(self, delay=0):
        await asyncio.sleep(delay)
        try:
            if self.cur == "Reader":
                self.views["Reader"].save(final=True)
            save_db()
        except Exception as ex:
            log_error("quit save", ex)
        if self.tray is not None:
            self.tray.stop()                    # pystray's thread would keep the process alive
            self.tray = None
        await self.page.window.destroy()

    async def check_updates_soon(self):
        await asyncio.sleep(3)
        self.updates.check()

    # ----- shell -----
    def build(self):
        from .browse import RandomView, SearchView, SourcesView
        from .details import DetailsView
        from .downloads_view import DownloadsView
        from .history import HistoryView
        from .library import LibraryView
        from .ratings import RatingView
        from .reader import ReaderView
        from .settings import SettingsView
        page = self.page
        page.title = "Sablja Manga Reader App"
        page.padding = 0
        page.spacing = 0
        apply_theme(page)
        logo = os.path.join(DATA, "logo64-v2.png")
        if not os.path.exists(logo):
            make_icon(128).resize((64, 64)).save(logo)
        self.views = {"Library": LibraryView(self), "History": HistoryView(self), "Rating": RatingView(self),
                      "Sources": SourcesView(self), "Search": SearchView(self), "Random": RandomView(self),
                      "Downloads": DownloadsView(self), "Settings": SettingsView(self), "Details": DetailsView(self),
                      "Reader": ReaderView(self)}
        self.rail = ft.NavigationRail(
            selected_index=0, label_type=ft.NavigationRailLabelType.ALL, min_width=RAIL_W,
            destinations=[ft.NavigationRailDestination(icon=i, selected_icon=si, label=l) for l, i, si in NAV],
            on_change=lambda e: self.show(NAV[e.control.selected_index][0]),
            leading=ft.Container(ft.Image(src=logo, width=40, height=40), padding=ft.Padding.only(top=10, bottom=6)),
            bgcolor=ft.Colors.TRANSPARENT, expand=True)
        self.gif = GifSpot(self, RAIL_W, 96)
        self.side = ft.Container(ft.Column([self.rail, self.gif.control], spacing=0), width=RAIL_W)
        self.title = ft.Text("", size=22, weight=ft.FontWeight.BOLD)
        self.header_extra = ft.Row([], spacing=4)
        self.header = ft.Container(ft.Row([
            ft.WindowDragArea(ft.Container(self.title, padding=ft.Padding.only(left=4)), expand=True),
            self.header_extra,
            ft.IconButton(ft.Icons.FULLSCREEN, tooltip="Full screen (F11)", on_click=lambda e: self.toggle_full()),
            ft.IconButton(ft.Icons.SETTINGS_OUTLINED, tooltip="Settings", on_click=lambda e: self.show("Settings")),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.only(left=16, right=10, top=6, bottom=2))
        self.body = ft.Container(expand=True)
        self.main = ft.Column([self.header, self.body], spacing=0, expand=True)
        self.divider = ft.VerticalDivider(width=1)
        page.add(ft.Row([self.side, self.divider, self.main], spacing=0, expand=True))
        page.overlay.append(self.gif.bubble)
        page.on_keyboard_event = self.on_key
        page.on_resize = self.on_resize
        self.show("Library")
        self.gif.next()

    def show(self, name, back=None):
        if self.cur == "Reader" and name != "Reader":
            self.views["Reader"].leave()
        if name not in ("Details", "Reader"):
            self.back_to = name
        elif back:
            self.back_to = back
        self.cur = name
        v = self.views[name]
        immersive = name == "Reader"
        self.side.visible = self.divider.visible = self.header.visible = not immersive
        if immersive:
            self.gif.hush()
        names = [n for n, _, _ in NAV]
        if name in names:
            self.rail.selected_index = names.index(name)
        elif name not in ("Details", "Reader"):
            self.rail.selected_index = None
        self.title.value = getattr(v, "TITLE", name)
        self.header_extra.controls = list(getattr(v, "header_controls", lambda: [])())
        self.body.content = v.control
        try:
            v.show()
        except Exception as ex:
            log_error(f"show {name}", ex)
        self.pump.mark()

    def go_back(self):
        self.show(self.back_to if self.back_to in self.views else "Library")

    def on_resize(self, e):
        v = self.views.get(self.cur)
        if v and hasattr(v, "on_resize"):
            v.on_resize()

    def toggle_full(self):
        w = self.page.window
        w.full_screen = not w.full_screen
        setv("start_fullscreen", bool(w.full_screen))
        self.pump.mark()

    def on_key(self, e: ft.KeyboardEvent):
        self.note_activity()
        k = e.key
        if k == S("panic_key"):
            self.panic()
            return
        if self._locked:
            return
        if k == "F11":
            self.toggle_full()
            return
        v = self.views.get(self.cur)
        if v and hasattr(v, "on_key"):
            v.on_key(e)

    # ----- panic key / PIN lock -----
    def panic(self):
        try:
            self.page.window.minimized = True
        except Exception:
            pass
        if DB["set"].get("pin") and S("pin_on_hide"):
            self.lock()
        self.pump.mark()

    def lock(self):
        if self._locked:
            return
        self._locked = True
        field = ft.TextField(label="PIN", password=True, autofocus=True, width=220, text_align=ft.TextAlign.CENTER)
        msg = muted("")

        def go(e=None):
            if pin_ok(field.value or "", DB["set"].get("pin", "")):
                self._locked = False
                self.page.pop_dialog()
            else:
                msg.value = "Wrong PIN"
                field.value = ""
            self.pump.mark()

        field.on_submit = go
        self.page.show_dialog(ft.AlertDialog(modal=True, title=ft.Text("Sablja Manga Reader App is locked"),
                                             content=ft.Column([field, msg], tight=True),
                                             actions=[ft.FilledButton("Unlock", on_click=go)]))

    # ----- manga actions shared by every view -----
    def find_bm(self, m):
        k = pkey(m)
        return next((b for b in DB["bookmarks"] if pkey(b) == k), None)

    def toggle_bm(self, m):
        b = self.find_bm(m)
        if b:
            DB["bookmarks"].remove(b)
            self.toast("Removed from Library")
        else:
            DB["bookmarks"].append({**{k: m.get(k, "") for k in ("source", "url", "title", "cover")}, "folder": ""})
        save_db()
        return not b

    def move_to(self, m, folder):
        b = self.find_bm(m)
        if b is None:
            DB["bookmarks"].append({**{k: m.get(k, "") for k in ("source", "url", "title", "cover")}, "folder": folder})
        else:
            b["folder"] = folder
        save_db()

    def ask_text(self, title_, label, cb, value=""):
        f = ft.TextField(label=label, value=value, autofocus=True)

        def ok(e=None):
            v = (f.value or "").strip()
            self.page.pop_dialog()
            if v:
                cb(v)

        f.on_submit = ok
        self.page.show_dialog(ft.AlertDialog(title=ft.Text(title_), content=f,
                                             actions=[ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                                                      ft.FilledButton("OK", on_click=ok)]))

    def new_folder(self, m=None, after=None):
        def made(name):
            if name in ("All", "Unsorted") or name in DB["folders"]:
                return
            DB["folders"].append(name)
            if m is not None:
                self.move_to(m, name)
            save_db()
            if after:
                after()
        self.ask_text("New folder", "Folder name", made)

    def rate(self, m, after=None):
        r = DB["ratings"].get(pkey(m)) or {}
        score = ft.Slider(min=1, max=10, divisions=9, value=r.get("score", 8), label="{value}")
        note = ft.TextField(label="Note (optional)", value=r.get("note", ""), multiline=True, min_lines=2, max_lines=4)

        def save(e=None):
            DB["ratings"][pkey(m)] = {"m": {k: m.get(k, "") for k in ("source", "url", "title", "cover")},
                                      "score": int(score.value), "note": (note.value or "").strip(), "ts": int(time.time())}
            save_db()
            self.page.pop_dialog()
            if after:
                after()

        def remove(e=None):
            DB["ratings"].pop(pkey(m), None)
            save_db()
            self.page.pop_dialog()
            if after:
                after()

        acts = [ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()), ft.FilledButton("Save", on_click=save)]
        if r:
            acts.insert(0, ft.TextButton("Remove rating", on_click=remove))
        self.page.show_dialog(ft.AlertDialog(title=ft.Text(f"Rate {m.get('title', '')[:40]}"),
                                             content=ft.Column([score, note], tight=True, width=380), actions=acts))

    # ----- context menu (opens at the cursor, like a desktop app) -----
    def context_menu(self, pos, items, header=None):
        """items: [(icon, label, fn) | None for a separator]. pos: global (x, y) of the click."""
        self.close_menu()
        rows = []
        if header:
            rows.append(ft.Container(ft.Text(header, size=12, weight=ft.FontWeight.BOLD, max_lines=1,
                                             overflow=ft.TextOverflow.ELLIPSIS, color=ft.Colors.ON_SURFACE_VARIANT),
                                     padding=ft.Padding.only(left=12, right=12, top=8, bottom=4)))

        def run(fn):
            def h(e):
                self.close_menu()
                fn()
            return h

        for it in items:
            if it is None:
                rows.append(ft.Divider(height=6))
                continue
            icon, label, fn = it
            rows.append(ft.Container(ft.Row([ft.Icon(icon, size=18), ft.Text(label, size=13)], spacing=12),
                                     padding=ft.Padding.symmetric(horizontal=12, vertical=7), border_radius=8, ink=True,
                                     on_click=run(fn)))
        W = 250
        H = sum(28 if r.__class__ is ft.Divider else 34 for r in rows) + 12
        x, y = pos
        x = max(4, min(x, self.width() - W - 8))
        y = max(4, min(y, self.height() - H - 8))
        menu = ft.Container(ft.Column(rows, spacing=0, tight=True, scroll=ft.ScrollMode.AUTO), left=x, top=y, width=W,
                            padding=6, border_radius=12, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                            shadow=ft.BoxShadow(blur_radius=18, color="#66000000"))
        shield = ft.GestureDetector(ft.Container(expand=True, bgcolor="#01000000"), left=0, top=0, right=0, bottom=0,
                                    on_tap=lambda e: self.close_menu(), on_secondary_tap=lambda e: self.close_menu())
        self._menu = [shield, menu]
        self.page.overlay.extend(self._menu)
        self.pump.mark()

    def close_menu(self):
        for c in getattr(self, "_menu", []) or []:
            if c in self.page.overlay:
                self.page.overlay.remove(c)
        self._menu = []
        self.pump.mark()

    def manga_menu(self, m, after=None, extra=None, pos=None):
        """Right-click actions for a manga card, at the cursor."""
        from sources import local_chapters_any
        from .downloads_view import delete_series_downloads

        def then(fn):
            def h():
                fn()
                if after:
                    after()
            return h

        b = self.find_bm(m)
        folder = (b or {}).get("folder", "")
        items = [(ft.Icons.MENU_BOOK, "Open", lambda: self.open_manga(m)),
                 (ft.Icons.PLAY_ARROW, "Continue reading", lambda: self.open_manga(m, resume=True)),
                 None,
                 (ft.Icons.BOOKMARK_REMOVE if b else ft.Icons.BOOKMARK_ADD,
                  "Remove from Library" if b else "Add to Library", then(lambda: self.toggle_bm(m))),
                 (ft.Icons.STAR_OUTLINE, "Rate…", lambda: self.rate(m, after))]
        moves = [(ft.Icons.DRIVE_FILE_MOVE_OUTLINE, f"Move to {f}", then(lambda f=f: self.move_to(m, f)))
                 for f in DB["folders"] if f != folder]
        if folder:
            moves.insert(0, (ft.Icons.FOLDER_OFF_OUTLINED, f"Remove from {folder}", then(lambda: self.move_to(m, ""))))
        items += [None, *moves, (ft.Icons.CREATE_NEW_FOLDER_OUTLINED, "New folder…", lambda: self.new_folder(m, after))]
        alts = [(ft.Icons.SWAP_HORIZ, f"Open on {SOURCES[a['source']].name if a['source'] in SOURCES else a['source']}",
                 lambda a=a: self.open_manga(a)) for a in m.get("_alts") or []]
        if alts:
            items += [None, *alts]
        n_dl = len(local_chapters_any(m))
        if n_dl:
            items += [None, (ft.Icons.DELETE_OUTLINE, f"Delete {n_dl} downloaded chapter{'s' if n_dl != 1 else ''}",
                             lambda: delete_series_downloads(self, m, after))]
        items += extra or []
        if pos is None:
            pos = (self.width() / 2 - 125, self.height() / 3)
        self.context_menu(pos, items, header=m.get("title", ""))

    def open_manga(self, m, resume=False):
        self.views["Details"].open(m, resume)

    def open_chapter(self, m, chs, idx, restart=False):
        self.views["Reader"].open(m, chs, idx, restart)


async def main(page: ft.Page):
    page.window.min_width, page.window.min_height = 760, 560
    page.window.width, page.window.height = 1320, 860
    ico = os.path.join(DATA, "sablja4.ico")
    if not os.path.exists(ico):
        make_icon_file(ico)
    page.window.icon = ico
    page.window.prevent_close = True
    rebuild_sources()
    global APP
    app = APP = App(page)
    app.build()
    page.window.on_event = app.on_window
    app.set_tray()
    if S("start_fullscreen"):
        page.window.full_screen = True
    page.update()
    page.run_task(app.pump.run)
    page.run_task(app.gif.run)
    page.run_task(app.views["Reader"].ticker)
    page.run_task(app.views["Library"].check_new_loop)
    page.run_task(app.check_updates_soon)
    if DB["set"].get("pin") and S("pin_on_start"):
        app.lock()
        page.update()
