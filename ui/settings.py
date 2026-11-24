"""Settings: reading, look, sources, downloads, notifications, privacy, updates, bug report, data."""

import os
import platform
import shutil
import sys
import webbrowser
from urllib.parse import urlencode

import flet as ft

from config import APP_VERSION, AUTO_SPEEDS, CACHE, DATA, MODES, PANIC_KEYS, REPO_URL
from desktop import HAVE_TRAY, pin_hash
from sources import SOURCES, hidden_ids, rebuild_sources, source_hidden
from storage import DB, S, save_db

from .core import apply_theme, card, muted, setv
from .downloads_view import open_path
from .gifs import DIR as GIF_DIR


class SettingsView:
    TITLE = "Settings"

    def __init__(self, app):
        self.app = app
        self.col = ft.ListView(expand=True, spacing=12, padding=ft.Padding.only(left=16, right=16, bottom=20))
        self.control = self.col

    def show(self):
        self.col.controls = [self.reading(), self.look(), self.sources(), self.downloads(), self.notifications(),
                             self.privacy(), self.updates(), self.report(), self.data()]
        self.app.pump.mark()

    # helpers
    def section(self, name, icon, *rows):
        return card(ft.Row([ft.Icon(icon, color=ft.Colors.PRIMARY), ft.Text(name, size=16, weight=ft.FontWeight.BOLD)]),
                    *rows, padding=16)

    def row(self, label, control, hint=None):
        return ft.Row([ft.Text(label, width=220), control, *( [muted(hint, 12)] if hint else [])],
                      vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True)

    def dropdown(self, key, values, width=220, after=None):
        def ch(e):
            setv(key, e.control.value)
            if after:
                after(e.control.value)
        return ft.Dropdown(value=str(S(key)), options=[ft.DropdownOption(str(v)) for v in values], width=width, dense=True,
                           on_select=ch)

    def switch(self, key, label, after=None):
        def ch(e):
            setv(key, bool(e.control.value))
            if after:
                after(bool(e.control.value))
        return ft.Switch(label=label, value=bool(S(key)), on_change=ch)

    # sections
    def reading(self):
        return self.section("Reading", ft.Icons.MENU_BOOK,
                            self.row("Default reading mode", self.dropdown("mode", MODES, 240)),
                            self.row("Auto-scroll speed", self.dropdown("autoscroll", list(AUTO_SPEEDS), 160),
                                     "webtoon mode: A starts / stops, , and . change speed"),
                            self.switch("paged_guides", "Paged modes: page borders, page numbers and the double-page gutter"),
                            muted("Reader keys: ↑ ↓ Space scroll · ← → chapters (webtoon) or pages (paged) · N / P next / "
                                  "previous chapter · C chapter list · + / − zoom · H hide the bar · Esc back", 12))

    def look(self):
        def theme(v):
            apply_theme(self.app.page)
            self.app.pump.mark()
        return self.section("Look", ft.Icons.PALETTE_OUTLINED,
                            self.row("Theme", self.dropdown("paper", ["Black", "White"], 160, after=theme)),
                            self.row("Cover size in grids", self.dropdown("lib_size", ["S", "M", "L"], 100)),
                            self.switch("start_fullscreen", "Start in full screen (F11 toggles it)"),
                            self.switch("group_dupes", "Show the same series from different sources as one card"),
                            ft.Row([self.switch("gifs", "Random GIF at the bottom of the menu",
                                                after=lambda v: self.app.gif.next()),
                                    ft.TextButton("Open GIF folder", icon=ft.Icons.FOLDER_OPEN,
                                                  on_click=lambda e: open_path(GIF_DIR))], wrap=True),
                            muted("A random character that says something whenever it changes. Right-click it to turn it "
                                  "off. To add your own, drop transparent .gif files into the GIF folder (name them like "
                                  "luffy3.gif).", 12))

    def sources(self):
        hid = hidden_ids()

        def toggle(sid, on):
            h = hidden_ids()
            (h.discard if on else h.add)(sid)
            DB["set"]["hidden"] = sorted(h)
            save_db()

        def reload(e):
            rebuild_sources()
            self.app.toast(f"Reloaded sources.json: {len(SOURCES)} sources")
            self.show()

        chips = [ft.Switch(label=s.name + ("  (18+)" if s.nsfw else ""), value=s.id not in hid,
                           on_change=lambda e, sid=s.id: toggle(sid, bool(e.control.value)))
                 for s in SOURCES.values()]
        return self.section("Sources", ft.Icons.EXPLORE_OUTLINED,
                            self.switch("nsfw", "Show 18+ sources"),
                            ft.Row(chips, wrap=True, spacing=16, run_spacing=4),
                            ft.Row([ft.OutlinedButton("Reload sources.json", icon=ft.Icons.REFRESH, on_click=reload)]))

    def downloads(self):
        path = ft.TextField(value=S("dl_dir"), dense=True, width=420,
                            on_blur=lambda e: setv("dl_dir", e.control.value.strip() or S("dl_dir")))
        return self.section("Downloads", ft.Icons.DOWNLOAD_OUTLINED,
                            self.row("Download folder", path),
                            self.row("Pause between pages (s)", self.dropdown("dl_delay", [0.5, 1.0, 1.5, 2.0, 3.0], 120),
                                     "higher = gentler on the site"),
                            self.row("Order", self.dropdown("dl_order", ["Oldest first", "Newest first"], 180)))

    def privacy(self):
        has_pin = bool(DB["set"].get("pin"))
        pin = ft.TextField(label="New PIN (4+ digits)", password=True, width=200, dense=True)

        def set_pin(e):
            v = (pin.value or "").strip()
            if len(v) < 4 or not v.isdigit():
                self.app.toast("Use at least 4 digits", error=True)
                return
            setv("pin", pin_hash(v))
            self.app.toast("PIN set")
            self.show()

        def clear_pin(e):
            setv("pin", "")
            self.app.toast("PIN removed")
            self.show()

        return self.section("Privacy", ft.Icons.LOCK_OUTLINE,
                            self.row("Panic key (hides the window)", self.dropdown("panic_key", PANIC_KEYS, 120)),
                            ft.Row([pin, ft.FilledButton("Set PIN", on_click=set_pin),
                                    *( [ft.TextButton("Remove PIN", on_click=clear_pin)] if has_pin else [])]),
                            self.switch("pin_on_start", "Ask for the PIN when the app starts"),
                            self.switch("pin_on_hide", "Lock when the panic key hides the window"))

    def notifications(self):
        def check(e):
            self.app.views["Library"].check_new()
            self.app.toast("Checking your Library for new chapters…")
        rows = [self.switch("notify_new", "Notify me when a Library series gets new chapters (checked every 30 "
                                          "minutes while the app is open)", after=lambda v: self.app.set_tray()),
                ft.Row([ft.OutlinedButton("Check now", icon=ft.Icons.REFRESH, on_click=check)]),
                muted("Off by default. While it's on, a tray icon shows; closing the window still quits the app, "
                      "and nothing starts with Windows.", 12)]
        if not HAVE_TRAY:
            rows.insert(0, muted("Toasts need the optional pystray package.", 12))
        return self.section("Notifications", ft.Icons.NOTIFICATIONS_OUTLINED, *rows)

    def updates(self):
        up = self.app.updates
        return self.section("Updates", ft.Icons.SYSTEM_UPDATE_ALT,
                            ft.Row([ft.Text(f"Installed version: {APP_VERSION}", width=220),
                                    ft.FilledButton("Check for updates", icon=ft.Icons.REFRESH,
                                                    on_click=lambda e: up.check(manual=True)),
                                    ft.TextButton("Release page", icon=ft.Icons.NEW_RELEASES_OUTLINED,
                                                  on_click=lambda e: up.open_page()), up.status],
                                   wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            self.switch("update_auto", "Check for updates automatically on start (once a day)"),
                            muted("Updates come from this project's GitHub releases. The installer only replaces the "
                                  "app; your library, progress, cache and downloads stay in the data folder, and "
                                  "db.json is backed up before every update.", 12))

    def report(self):
        kind = ft.Dropdown(value="Bug", options=[ft.DropdownOption(k) for k in ("Bug", "Source problem", "Feature request")],
                           width=200, dense=True)
        title_f = ft.TextField(label="Short summary", hint_text="e.g. The reader freezes on chapter 12", dense=True,
                               expand=True)
        body_f = ft.TextField(label="What happened?", multiline=True, min_lines=3, max_lines=8)
        msg = muted("", 12)

        def send(e):
            title, what = (title_f.value or "").strip(), (body_f.value or "").strip()
            if not title and not what:
                msg.value = "Add a short summary or describe what happened first."
                self.app.pump.mark()
                return
            body = f"{what or '(no details given)'}\n\n---\n### Diagnostics\n```\n{self.diagnostics()}\n```\n"
            url = f"{REPO_URL}/issues/new?" + urlencode({"title": f"[{kind.value}] {title or 'Report'}", "body": body})
            try:
                webbrowser.open(url)
                msg.value = "Opened GitHub in your browser. Review it there and press Submit."
            except Exception as ex:
                msg.value = f"Couldn't open a browser: {str(ex)[:80]}"
            self.app.pump.mark()

        return self.section("Report a bug / request a feature", ft.Icons.BUG_REPORT_OUTLINED,
                            ft.Row([kind, title_f], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            body_f,
                            ft.Row([ft.FilledButton("Open GitHub issue", icon=ft.Icons.OPEN_IN_NEW, on_click=send), msg],
                                   wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            muted("Opens a new issue on GitHub with your text and the diagnostics below filled in. "
                                  "Nothing is sent automatically, and no reading history is included.", 12),
                            ft.Text(self.diagnostics(), size=11, selectable=True, color=ft.Colors.ON_SURFACE_VARIANT,
                                    font_family="Consolas"))

    def diagnostics(self):
        """Technical context for a bug report, without reading history or personal data."""
        try:
            import curl_cffi  # noqa: F401
            cffi = True
        except Exception:
            cffi = False
        shown = [s for s in SOURCES.values() if (S("nsfw") or not s.nsfw) and not source_hidden(s.id)]
        return "\n".join([
            f"App version: {APP_VERSION}",
            f"OS: {platform.platform()}",
            f"Python: {platform.python_version()}" + ("  (installed exe)" if getattr(sys, "frozen", False) else ""),
            f"Window: {int(self.app.width())}x{int(self.app.height())}",
            f"Reading mode: {S('mode')}   Theme: {S('paper')}",
            f"Sources loaded: {len(SOURCES)}   Shown: {len(shown)}",
            f"curl_cffi available: {cffi}",
        ])

    def data(self):
        def clear_cache(e):
            shutil.rmtree(CACHE, ignore_errors=True)
            os.makedirs(CACHE, exist_ok=True)
            self.app.toast("Image cache cleared")

        return self.section("Data", ft.Icons.STORAGE,
                            muted(f"Sablja Manga Reader App {APP_VERSION}. Your library lives in {DATA}", 12),
                            ft.Row([ft.OutlinedButton("Open data folder", icon=ft.Icons.FOLDER_OPEN,
                                                      on_click=lambda e: open_path(DATA)),
                                    ft.OutlinedButton("Clear image cache", icon=ft.Icons.DELETE_SWEEP,
                                                      on_click=clear_cache)],
                                   wrap=True))
