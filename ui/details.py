"""Series page: cover hero, description, actions and the (fast, lazy) chapter list."""

import os
import re

import flet as ft

from downloads import DL_Q, JOBS, dl_path, next_job_id
from sources import DETAIL_POOL, SOURCES, bg, local_chapters, local_chapters_any
from storage import DB, S, cached_genres, dl_records, pkey, remember_genres

from .core import cover_image, dirty, muted, thumb, thumb_cached

ROW_H = 46


class DetailsView:
    TITLE = ""

    def __init__(self, app):
        self.app = app
        self.m = None
        self.info = None
        self.gen = 0
        self.sel = set()
        self.newest_first = False
        self.desc_open = False
        self.hero = ft.Container(height=0)
        self.cover = ft.Container(width=170, height=242)
        self.name = ft.Text("", size=26, weight=ft.FontWeight.BOLD, max_lines=3)
        self.src = muted("", 13)
        self.genres = ft.Row([], spacing=6, wrap=True, run_spacing=6)
        self.desc = ft.Text("", size=13, max_lines=4, overflow=ft.TextOverflow.ELLIPSIS, selectable=True)
        self.more = ft.TextButton("More", on_click=lambda e: self.toggle_desc())
        self.cont = ft.FilledButton("Start reading", icon=ft.Icons.PLAY_ARROW, disabled=True)
        self.bm = ft.OutlinedButton("Bookmark", icon=ft.Icons.BOOKMARK_ADD_OUTLINED, on_click=lambda e: self.toggle_bm())
        self.rate = ft.OutlinedButton("Rate", icon=ft.Icons.STAR_OUTLINE, on_click=lambda e: self.app.rate(self.m, self.refresh_head))
        self.dl = ft.OutlinedButton("Download", icon=ft.Icons.DOWNLOAD, disabled=True, on_click=lambda e: self.enqueue())
        self.count = muted("")
        self.jump = ft.TextField(hint_text="Go to #", width=110, dense=True, on_submit=self.jump_to,
                                 content_padding=ft.Padding.symmetric(horizontal=10, vertical=8))
        self.list = ft.ListView(expand=True, item_extent=ROW_H, spacing=0)
        head = ft.Row([self.cover, ft.Column([
            self.name, self.src, self.genres, self.desc, self.more,
            ft.Row([self.cont, self.bm, self.rate, self.dl], wrap=True, spacing=8)], spacing=6, expand=True)],
            spacing=22, vertical_alignment=ft.CrossAxisAlignment.START)
        tools = ft.Row([ft.Text("Chapters", size=17, weight=ft.FontWeight.BOLD), self.count, ft.Container(expand=True),
                        self.jump,
                        ft.IconButton(ft.Icons.SWAP_VERT, tooltip="Newest / oldest first", on_click=lambda e: self.flip()),
                        ft.TextButton("Select all", on_click=lambda e: self.select_all(True)),
                        ft.TextButton("None", on_click=lambda e: self.select_all(False))],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER)
        body = ft.Column([
            ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back", on_click=lambda e: self.app.go_back())]),
            ft.Container(head, padding=ft.Padding.only(left=8, right=8)),
            ft.Container(tools, padding=ft.Padding.only(left=8, right=8, top=10)),
            ft.Container(self.list, expand=True, border_radius=14, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                         padding=ft.Padding.symmetric(vertical=4)),
        ], spacing=4, expand=True)
        self.control = ft.Stack([self.hero, ft.Container(body, padding=ft.Padding.only(left=16, right=16, bottom=14),
                                                         expand=True)], expand=True)

    def show(self):
        pass

    # ----- open -----
    def open(self, m, resume=False):
        self.gen += 1
        gen = self.gen
        self.m, self.info, self.sel = dict(m), None, set()
        self.app.show("Details", back=self.app.cur if self.app.cur not in ("Details", "Reader") else None)
        self.name.value = m.get("title", "")
        src = SOURCES.get(m.get("source"))
        self.src.value = src.name if src else m.get("source", "")
        self.desc.value = "Loading…"
        self.genres.controls = []
        self.list.controls = []
        self.count.value = ""
        self.cont.disabled = True
        self.cont.content = "Start reading"
        self.dl.disabled = True
        self.set_cover(m)
        self.refresh_head()
        if not src:
            self.loaded(gen, None, RuntimeError("source not available"), resume)
            return
        bg(lambda: src.details(m["url"]), lambda r, e: self.loaded(gen, r, e, resume), pool=DETAIL_POOL)

    def set_cover(self, m):
        self.cover.content = cover_image(m, 170, 242, 14)
        url = m.get("cover")
        tw, th = 255, 363

        def hero(path):
            if path:
                self.hero.content = ft.Image(src=path, fit=ft.BoxFit.COVER, opacity=0.22, expand=True)
                dirty()

        self.hero = self.hero if self.hero else ft.Container()
        self.hero.height = 330
        self.hero.left = self.hero.right = self.hero.top = 0
        self.hero.blur = ft.Blur(28, 28)
        self.hero.content = None
        have = thumb_cached(url, tw, th)
        if have:
            hero(have)
        elif url:
            thumb(SOURCES.get(m.get("source")), url, tw, th, hero)

    def offline_info(self, m):
        local = local_chapters_any(m)
        if not local:
            return None
        recs = {r.get("i"): r for r in dl_records(m)}
        chs = []
        for i in sorted(local):
            c = (recs.get(i) or {}).get("ch") or {}
            t = c.get("title") or re.sub(r"^\d+\s*-\s*", "", os.path.splitext(os.path.basename(local[i]))[0])
            chs.append({"title": t, "url": c.get("url") or f"local:{local[i]}", "i": i})
        return {"title": m.get("title", ""), "cover": m.get("cover", ""), "chapters": chs,
                "description": "(Source unreachable: showing your downloaded chapters only.)"}

    def loaded(self, gen, info, err, resume):
        if gen != self.gen:
            return
        m = self.m
        if err or not info:
            info = self.offline_info(m)
            if not info:
                self.desc.value = f"Couldn't load this series: {str(err)[:160]}"
                return
        self.info = info
        self.m = m = dict(m, title=info.get("title") or m["title"], cover=info.get("cover") or m.get("cover", ""))
        self.name.value = m["title"]
        gs = info.get("genres") or m.get("genres") or cached_genres(m)
        if gs:
            remember_genres(m, gs)
        self.genres.controls = [ft.Container(ft.Text(g, size=11), padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                                             border_radius=12, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH) for g in gs[:10]]
        self.desc.value = info.get("description") or "No description available."
        chs = info["chapters"]
        n = len(chs)
        if n:
            DB["meta"].setdefault("chapter_seen", {})[pkey(m)] = max(n, (DB["meta"].get("chapter_seen") or {}).get(pkey(m), 0))
        self.count.value = f"{n} chapter{'s' if n != 1 else ''}"
        prog = DB["progress"].get(pkey(m), {})
        urls = [c["url"] for c in chs]
        if chs:
            has = prog.get("chapter") in urls
            idx = urls.index(prog["chapter"]) if has else 0
            self.cont.disabled = False
            self.cont.content = f"Continue: {prog.get('title', '')[:28]}" if has else "Start reading"
            self.cont.on_click = lambda e: self.resume(idx)
            if resume and has:
                self.resume(idx)
                return
        self.render_list()

    def refresh_head(self):
        if not self.m:
            return
        on = self.app.find_bm(self.m) is not None
        self.bm.content = "In Library" if on else "Bookmark"
        self.bm.icon = ft.Icons.BOOKMARK if on else ft.Icons.BOOKMARK_ADD_OUTLINED
        r = DB["ratings"].get(pkey(self.m))
        self.rate.content = f"{r['score']}/10" if r else "Rate"
        self.rate.icon = ft.Icons.STAR if r else ft.Icons.STAR_OUTLINE
        self.app.pump.mark()

    def toggle_bm(self):
        if self.m:
            self.app.toggle_bm(self.m)
            self.refresh_head()

    def toggle_desc(self):
        self.desc_open = not self.desc_open
        self.desc.max_lines = None if self.desc_open else 4
        self.more.content = "Less" if self.desc_open else "More"

    # ----- chapter list -----
    def order(self):
        n = len(self.info["chapters"]) if self.info else 0
        return list(range(n - 1, -1, -1)) if self.newest_first else list(range(n))

    def render_list(self):
        if not self.info:
            return
        chs = self.info["chapters"]
        prog = DB["progress"].get(pkey(self.m), {})
        read, cur = set(prog.get("read") or []), prog.get("chapter")
        local = local_chapters(self.m)
        rows = []
        for i in self.order():
            c = chs[i]
            is_cur = c["url"] == cur
            done = c["url"] in read
            rows.append(ft.Container(ft.Row([
                ft.Checkbox(value=i in self.sel, on_change=lambda e, i=i: self.tick(i, e.control.value)),
                ft.Text(f"{i + 1}", width=46, color=ft.Colors.ON_SURFACE_VARIANT, size=12),
                ft.Text(c.get("title") or f"Chapter {i + 1}", expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                        weight=ft.FontWeight.BOLD if is_cur else None,
                        color=ft.Colors.PRIMARY if is_cur else (ft.Colors.ON_SURFACE_VARIANT if done else None)),
                *([ft.Container(ft.Text(f"page {prog.get('page', 0) + 1}", size=11, color="#06211e"), bgcolor="#5fd0c2",
                                border_radius=10, padding=ft.Padding.symmetric(horizontal=8, vertical=2))] if is_cur else []),
                ft.Icon(ft.Icons.DOWNLOAD_DONE, size=16, color=ft.Colors.PRIMARY) if c.get("i", i) in local else ft.Container(width=16),
                ft.Icon(ft.Icons.CHECK, size=16, color=ft.Colors.ON_SURFACE_VARIANT) if done else ft.Container(width=16),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                height=ROW_H, padding=ft.Padding.only(left=4, right=14), ink=True,
                on_click=lambda e, i=i: self.app.open_chapter(self.m, self.info["chapters"], i)))
        self.list.controls = rows
        self.dl.disabled = not self.sel
        self.dl.content = f"Download {len(self.sel)}" if self.sel else "Download"
        if cur:
            urls = [chs[i]["url"] for i in self.order()]
            if cur in urls:
                pos = urls.index(cur)
                self.app.page.run_task(self._scroll_to, max(0, pos - 3) * ROW_H)
        self.app.pump.mark()

    async def _scroll_to(self, off):
        try:
            await self.list.scroll_to(offset=off, duration=0)
        except Exception:
            pass

    def tick(self, i, on):
        (self.sel.add if on else self.sel.discard)(i)
        self.dl.disabled = not self.sel
        self.dl.content = f"Download {len(self.sel)}" if self.sel else "Download"
        self.app.pump.mark()

    def select_all(self, on):
        self.sel = set(range(len(self.info["chapters"]))) if (on and self.info) else set()
        self.render_list()

    def flip(self):
        self.newest_first = not self.newest_first
        self.render_list()

    def jump_to(self, e):
        try:
            n = int(re.sub(r"[^0-9]", "", e.control.value or ""))
        except ValueError:
            return
        if self.info and 1 <= n <= len(self.info["chapters"]):
            self.app.open_chapter(self.m, self.info["chapters"], n - 1)
        else:
            self.app.toast("No chapter with that number")

    # ----- read / download -----
    def resume(self, idx):
        chs = self.info["chapters"]
        p = DB["progress"].get(pkey(self.m), {})
        page = p.get("page", 0) if p.get("chapter") == chs[idx]["url"] else 0
        if not page:
            self.app.open_chapter(self.m, chs, idx)
            return

        def pick(restart):
            self.app.page.pop_dialog()
            self.app.open_chapter(self.m, chs, idx, restart)

        self.app.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Continue where you left off?"),
            content=muted(f"{chs[idx]['title']}, saved at page {page + 1}", 14),
            actions=[ft.TextButton("Start chapter over", on_click=lambda e: pick(True)),
                     ft.FilledButton(f"Resume page {page + 1}", on_click=lambda e: pick(False))]))

    def enqueue(self):
        if not self.info or not self.sel:
            return
        m, chs, n = self.m, self.info["chapters"], 0
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
        self.render_list()
        self.app.toast(f"Queued {n} chapter(s). See Downloads.")
