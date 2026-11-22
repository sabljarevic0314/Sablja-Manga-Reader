"""Downloads: the polite CBZ queue (one chapter at a time, with pauses) and the chapters on disk."""

import asyncio
import os
import time

import flet as ft

from downloads import JOBS
from sources import downloaded_manga, local_chapters_any
from storage import DB, S, dl_records, pkey, save_db

from .core import cover_image, muted


def open_path(p):
    os.makedirs(p, exist_ok=True)
    os.startfile(p)


def sync_done_jobs():
    """Fold finished jobs into the persistent download index (offline library)."""
    changed = False
    for j in JOBS:
        if j["state"] != "done" or j.get("recorded"):
            continue
        j["recorded"] = True
        if os.path.exists(j["path"]) and not any(r.get("path") == j["path"] for r in DB["downloads"]):
            DB["downloads"].append({"key": pkey(j["m"]), "m": j["m"], "i": j.get("i", 0), "ch": j["ch"],
                                    "path": j["path"], "ts": int(time.time())})
            changed = True
    if changed:
        save_db()
    return changed


def delete_files(paths):
    paths = set(paths)
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass
    DB["downloads"][:] = [r for r in DB["downloads"] if r.get("path") not in paths]
    save_db()
    for d in {os.path.dirname(p) for p in paths}:          # drop folders the delete left empty
        try:
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
        except OSError:
            pass


def confirm(app, title, text, on_yes, yes="Delete"):
    def ok(e):
        app.page.pop_dialog()
        on_yes()
    app.page.show_dialog(ft.AlertDialog(title=ft.Text(title), content=ft.Text(text),
                                        actions=[ft.TextButton("Cancel", on_click=lambda e: app.page.pop_dialog()),
                                                 ft.FilledButton(yes, on_click=ok)]))


def delete_series_downloads(app, m, after=None):
    chs = local_chapters_any(m)
    if not chs:
        return

    def go():
        delete_files(chs.values())
        app.toast(f"Deleted {len(chs)} chapter file(s)")
        if after:
            after()
    confirm(app, "Delete downloads", f"Delete all {len(chs)} downloaded chapter file(s) of {m.get('title', '?')}?", go)


class DownloadsView:
    TITLE = "Downloads"

    def __init__(self, app):
        self.app = app
        self.tab = "queue"
        self.open_series = set()
        self.list = ft.ListView(expand=True, spacing=6, padding=ft.Padding.only(left=16, right=16, bottom=16))
        self.summary = muted("")
        self.tabs = ft.SegmentedButton(selected=["queue"], show_selected_icon=False,
                                       segments=[ft.Segment(value="queue", label=ft.Text("Queue")),
                                                 ft.Segment(value="disk", label=ft.Text("On disk"))],
                                       on_change=self._tab)
        self.queue_btns = ft.Row([ft.OutlinedButton("Cancel queued", icon=ft.Icons.CANCEL_OUTLINED, on_click=lambda e: self.cancel()),
                                  ft.OutlinedButton("Clear finished", icon=ft.Icons.CLEAR_ALL, on_click=lambda e: self.clear())])
        bar = ft.Row([self.tabs, self.summary, ft.Container(expand=True), self.queue_btns,
                      ft.OutlinedButton("Open folder", icon=ft.Icons.FOLDER_OPEN, on_click=lambda e: open_path(S("dl_dir")))],
                     vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.control = ft.Column([ft.Container(bar, padding=ft.Padding.only(left=16, right=16, bottom=8)), self.list],
                                 spacing=0, expand=True)
        self._loop = False

    def _tab(self, e):
        self.tab = list(e.control.selected)[0]
        self.render()

    def show(self):
        sync_done_jobs()
        self.render()
        if not self._loop:
            self._loop = True
            self.app.page.run_task(self.loop)

    async def loop(self):
        while self.app.cur == "Downloads":
            await asyncio.sleep(1.0)
            sync_done_jobs()
            if self.tab == "queue":
                self.render()
        self._loop = False

    def render(self):
        self.queue_btns.visible = self.tab == "queue"
        if self.tab == "queue":
            self.render_queue()
        else:
            self.render_disk()
        self.app.pump.mark()

    # ----- queue -----
    def render_queue(self):
        rows = []
        active = [j for j in JOBS if j["state"] not in ("done", "cancelled") and not j["state"].startswith("error")]
        self.summary.value = (f"{len(active)} in the queue · one chapter at a time with pauses, so sources don't block you"
                              if JOBS else "Nothing downloading. Tick chapters on a series page and press Download.")
        for j in reversed(JOBS[-200:]):
            st = j["state"]
            frac = (j["done"] / j["total"]) if j.get("total") else None
            icon = (ft.Icons.CHECK_CIRCLE if st == "done" else ft.Icons.ERROR_OUTLINE if st.startswith("error")
                    else ft.Icons.CANCEL if st == "cancelled" else ft.Icons.DOWNLOADING)
            rows.append(ft.Container(ft.Row([
                ft.Icon(icon, color=ft.Colors.PRIMARY if st == "done" else None),
                ft.Column([ft.Text(f"{j['m']['title'][:50]}  ·  {j['ch']['title'][:40]}", max_lines=1,
                                   overflow=ft.TextOverflow.ELLIPSIS),
                           *([ft.ProgressBar(value=frac, bar_height=4, border_radius=2)]
                             if st not in ("done", "cancelled") and not st.startswith("error") else []),
                           muted(f"{j['done']}/{j['total']} pages · {st}" if j.get("total") else st, 11)],
                          spacing=3, expand=True, tight=True),
                ft.IconButton(ft.Icons.FOLDER_OPEN, tooltip="Open folder",
                              on_click=lambda e, p=j["path"]: open_path(os.path.dirname(p))) if st == "done" else
                ft.IconButton(ft.Icons.CLOSE, tooltip="Cancel", on_click=lambda e, j=j: self.cancel_one(j)),
            ], spacing=12), padding=10, border_radius=12, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW))
        self.list.controls = rows

    def cancel_one(self, j):
        if j["state"] != "done":
            j["state"] = "cancelled"
        self.render()

    def cancel(self):
        for j in JOBS:
            if j["state"] == "queued":
                j["state"] = "cancelled"
        self.render()

    def clear(self):
        JOBS[:] = [j for j in JOBS if j["state"] not in ("done", "cancelled") and not j["state"].startswith("error")]
        self.render()

    # ----- on disk -----
    def render_disk(self):
        series = downloaded_manga()
        total = 0
        rows = []
        for m in sorted(series, key=lambda x: x.get("title", "").lower()):
            chs = local_chapters_any(m)
            if not chs:
                continue
            total += len(chs)
            key = (m.get("name"), m.get("title"))
            is_open = key in self.open_series
            size = sum(os.path.getsize(p) for p in chs.values() if os.path.exists(p)) / 1024 / 1024
            head = ft.Container(ft.Row([
                cover_image(m, 44, 62, 6),
                ft.Column([ft.Text(m.get("title", "?"), weight=ft.FontWeight.BOLD, max_lines=1,
                                   overflow=ft.TextOverflow.ELLIPSIS),
                           muted(f"{m.get('name', '')} · {len(chs)} chapter{'s' if len(chs) != 1 else ''} · {size:.0f} MB", 12)],
                          spacing=2, expand=True, tight=True),
                ft.IconButton(ft.Icons.MENU_BOOK, tooltip="Open", on_click=lambda e, m=m: self.app.open_manga(m)),
                ft.IconButton(ft.Icons.FOLDER_OPEN, tooltip="Open folder",
                              on_click=lambda e, p=next(iter(chs.values())): open_path(os.path.dirname(p))),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Delete all chapters of this series",
                              on_click=lambda e, m=m: delete_series_downloads(self.app, m, self.render)),
                ft.Icon(ft.Icons.EXPAND_LESS if is_open else ft.Icons.EXPAND_MORE),
            ], spacing=10), padding=10, border_radius=12, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, ink=True,
                on_click=lambda e, k=key: self.toggle(k))
            rows.append(head)
            if is_open:
                recs = {r.get("path"): r for r in dl_records(m)}
                for i in sorted(chs):
                    p = chs[i]
                    t = ((recs.get(p) or {}).get("ch") or {}).get("title") or os.path.splitext(os.path.basename(p))[0]
                    rows.append(ft.Container(ft.Row([
                        ft.Text(f"{i + 1}", width=46, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text(t, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Delete this chapter file",
                                      on_click=lambda e, p=p, t=t: confirm(self.app, "Delete chapter",
                                                                           f"Delete {t} from disk?",
                                                                           lambda p=p: (delete_files([p]), self.render())))]),
                        padding=ft.Padding.only(left=64, right=10), height=40))
        self.summary.value = f"{total} chapter file(s) in {S('dl_dir')}" if total else "No downloaded chapters yet."
        self.list.controls = rows or [ft.Container(muted("Nothing on disk yet.", 14), padding=40)]

    def toggle(self, key):
        (self.open_series.discard if key in self.open_series else self.open_series.add)(key)
        self.render()
