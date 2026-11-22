"""History: every series you've opened, newest first, with where you are, time spent and your rating."""

import re

import flet as ft

import stats
from storage import DB, pkey, save_db

from .core import age_str, cover_image, fmt_time, muted


def hist_entries():
    """Newest-first rows: (ts, key, manga, progress)."""
    bm = {pkey(b): b for b in DB["bookmarks"]}
    last = DB["last"] or {}
    out = []
    for key, p in DB["progress"].items():
        if not p.get("chapter"):
            continue
        m = p.get("manga") or bm.get(key)
        if not m and last.get("key") == key:
            m = last.get("manga")
        if not m:
            src_id, _, url = key.partition("|")
            tail = url.rstrip("/").split("/")[-1] or url
            m = {"source": src_id, "url": url, "title": (re.sub(r"[-_]+", " ", tail).strip()[:44] or "Unknown").title(),
                 "cover": ""}
        out.append((p.get("ts") or 0, key, m, p))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


def stars(score):
    if not score:
        return None
    full = round(score / 2)
    return "★" * full + "☆" * (5 - full)


class HistoryView:
    TITLE = "History"

    def __init__(self, app):
        self.app = app
        self.query = ""
        self.gen = 0
        self.summary = ft.Row([], spacing=10, wrap=True)
        self.filter = ft.TextField(hint_text="Filter", prefix_icon=ft.Icons.SEARCH, dense=True, width=220,
                                   border_radius=20, content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                                   on_change=lambda e: (setattr(self, "query", (e.control.value or "").lower()), self.show()))
        self.list = ft.ListView(expand=True, spacing=8, padding=ft.Padding.only(left=16, right=16, bottom=16))
        self.control = ft.Column([ft.Container(ft.Row([self.summary, ft.Container(expand=True), self.filter],
                                                      vertical_alignment=ft.CrossAxisAlignment.CENTER),
                                               padding=ft.Padding.only(left=16, right=16, bottom=10)),
                                  self.list], spacing=0, expand=True)

    def stat(self, big, small, icon):
        return ft.Container(ft.Row([ft.Icon(icon, size=20, color=ft.Colors.PRIMARY),
                                    ft.Column([ft.Text(big, size=16, weight=ft.FontWeight.BOLD), muted(small, 11)],
                                              spacing=0, tight=True)], spacing=10),
                            padding=ft.Padding.symmetric(horizontal=14, vertical=8), border_radius=14,
                            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW)

    def show(self):
        self.gen += 1
        gen = self.gen
        alive = lambda: gen == self.gen and self.app.cur == "History"
        rows = hist_entries()
        total = sum(p.get("sec", 0) for _, _, _, p in rows)
        week = sum(r.get("sec", 0) for _, r in stats.week())
        streak, best = stats.streak()
        chapters = sum(len(p.get("read") or []) for _, _, _, p in rows)
        self.summary.controls = [self.stat(fmt_time(total), "total reading time", ft.Icons.SCHEDULE),
                                 self.stat(fmt_time(week), "last 7 days", ft.Icons.DATE_RANGE),
                                 self.stat(str(chapters), "chapters finished", ft.Icons.TASK_ALT),
                                 self.stat(f"{streak} days", f"streak · best {best}", ft.Icons.LOCAL_FIRE_DEPARTMENT)]
        if self.query:
            rows = [r for r in rows if self.query in r[2].get("title", "").lower()]
        self.list.controls = [self.row(ts, key, m, p, alive) for ts, key, m, p in rows] or [
            ft.Container(muted("Nothing read yet. Your series show up here with time spent and progress.", 14),
                         padding=40, alignment=ft.Alignment(0, 0))]
        self.app.pump.mark()

    def row(self, ts, key, m, p, alive):
        read = len(p.get("read") or [])
        total = (DB["meta"].get("chapter_seen") or {}).get(key)
        rating = (DB["ratings"].get(key) or {}).get("score")
        new = self.app.fresh.get(key, {}).get("n", 0)
        chapter = p.get("title") or "Chapter ?"
        prog = []
        if total:
            prog = [ft.ProgressBar(value=min(1, read / total), bar_height=5, border_radius=3, width=220),
                    muted(f"{read} of {total} chapters read", 11)]
        elif read:
            prog = [muted(f"{read} chapters read", 11)]
        rate_btn = ft.TextButton(
            content=ft.Row([ft.Text(stars(rating), color="#f5c451", size=15), muted(f"{rating}/10", 12)], spacing=6, tight=True)
            if rating else muted("Rate it", 12), on_click=lambda e: self.app.rate(m, self.show), tooltip="Your rating")
        info = ft.Column([
            ft.Row([ft.Text(m.get("title", "?"), size=15, weight=ft.FontWeight.BOLD, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                    *( [ft.Container(ft.Text(f"+{new} new", size=11, color="#06211e", weight=ft.FontWeight.BOLD),
                                     bgcolor="#5fd0c2", border_radius=10, padding=ft.Padding.symmetric(horizontal=8, vertical=2))]
                       if new else [])]),
            ft.Row([ft.Icon(ft.Icons.BOOKMARK, size=16, color=ft.Colors.PRIMARY),
                    ft.Text(chapter, size=14, weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    muted(f"page {p.get('page', 0) + 1}", 12)], spacing=6),
            *prog,
            ft.Row([ft.Icon(ft.Icons.SCHEDULE, size=14, color=ft.Colors.ON_SURFACE_VARIANT), muted(fmt_time(p.get("sec")), 12),
                    ft.Container(width=8), ft.Icon(ft.Icons.UPDATE, size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                    muted(age_str(ts), 12), ft.Container(width=8), rate_btn], spacing=4,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=4, expand=True, tight=True)
        actions = ft.Column([
            ft.FilledButton("Continue", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: self.app.open_manga(m, resume=True)),
            ft.Row([ft.IconButton(ft.Icons.INFO_OUTLINE, tooltip="Details", on_click=lambda e: self.app.open_manga(m)),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Remove from history",
                                  on_click=lambda e: self.remove(key))], spacing=0, tight=True),
        ], horizontal_alignment=ft.CrossAxisAlignment.END, spacing=2, tight=True)
        cover = ft.Container(cover_image(m, 72, 102, 10, alive), on_click=lambda e: self.app.open_manga(m),
                             tooltip="Open series")
        return ft.Container(ft.Row([cover, info, actions], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            padding=12, border_radius=16, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW)

    def remove(self, key):
        """Drop a series from History (its read chapters and rating stay). Undo from the snackbar."""
        p = DB["progress"].get(key)
        if p is None:
            return
        saved = {k: p[k] for k in ("chapter", "title", "page", "ts") if k in p}
        for k in saved:
            p.pop(k, None)
        last = DB["last"]
        if last and last.get("key") == key:
            DB["last"] = None
        save_db()
        self.show()

        def undo(e):
            p.update(saved)
            if last and last.get("key") == key:
                DB["last"] = last
            save_db()
            self.show()

        self.app.page.show_dialog(ft.SnackBar(ft.Text("Removed from History"), action="Undo", on_action=undo,
                                              behavior=ft.SnackBarBehavior.FLOATING, duration=4000,
                                              persist=False))
