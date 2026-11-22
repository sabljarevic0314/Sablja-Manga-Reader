"""Rating: everything you've scored, best first, with your notes."""

import flet as ft

from storage import DB

from .core import age_str, cover_image, muted
from .history import stars


class RatingView:
    TITLE = "Rating"

    def __init__(self, app):
        self.app = app
        self.gen = 0
        self.list = ft.GridView(expand=True, max_extent=520, child_aspect_ratio=3.3, spacing=10, run_spacing=10,
                                padding=ft.Padding.only(left=16, right=16, bottom=16))
        self.control = self.list

    def show(self):
        self.gen += 1
        gen = self.gen
        alive = lambda: gen == self.gen and self.app.cur == "Rating"
        rows = sorted(DB["ratings"].values(), key=lambda r: (-r.get("score", 0), -r.get("ts", 0)))
        self.list.controls = [self.tile(r, alive) for r in rows] or [
            ft.Container(muted("No ratings yet. Rate a series from its page or from History.", 14), padding=40)]
        self.app.pump.mark()

    def tile(self, r, alive):
        m = r.get("m") or {}
        sc = r.get("score", 0)
        return ft.Container(ft.Row([
            cover_image(m, 70, 100, 10, alive),
            ft.Column([ft.Text(m.get("title", "?"), size=14, weight=ft.FontWeight.BOLD, max_lines=1,
                               overflow=ft.TextOverflow.ELLIPSIS),
                       ft.Row([ft.Text(stars(sc), color="#f5c451", size=16), ft.Text(f"{sc}/10", weight=ft.FontWeight.BOLD)],
                              spacing=8),
                       muted(r.get("note") or "No note", 12, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                       muted(age_str(r.get("ts")), 11)], spacing=3, expand=True, tight=True),
            ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Change rating", on_click=lambda e: self.app.rate(m, self.show)),
        ], spacing=12), padding=10, border_radius=16, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, ink=True,
            on_click=lambda e: self.app.open_manga(m))
