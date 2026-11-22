"""The reader: webtoon strip and paged modes (single/double, left-to-right/right-to-left).

Webtoon: a lazy ListView; only pages near the viewport are fetched (politely, through the source's
pacing) and decoded, far pages fall back to placeholders that keep their height, and when a page
above you finishes loading the scroll position is corrected so the view never jumps.
Paged: page images with click zones and the direction arrows that show which side goes forward.
"""

import asyncio
import re
import time

import flet as ft

import stats
from config import AUTO_SPEEDS, MODES, ZOOMS
from sources import LOCAL, PAGE_POOL, SOURCES, Source, bg, cbz_pages, fetch_pages, local_path
from storage import DB, S, log_error, pkey, save_db, save_db_soon

from .core import dirty, load_page, muted, pal, setv

BAR_H = 54
BASE_W = 820             # webtoon strip width at 100 %
WINDOW = (2, 7)          # pages kept loaded above / below the current one
KEEP = 14                # images further away than this are released


class ReaderView:
    TITLE = "Reader"

    def __init__(self, app):
        self.app = app
        self.r = {}
        self.gen = 0
        self.auto = None             # auto-scroll speed px/s while running
        self.bar_on = bool(S("reader_bar"))
        self.title = ft.Text("", size=14, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                             expand=True)
        self.page_lbl = muted("", 12)
        self.bm = ft.IconButton(ft.Icons.BOOKMARK_ADD_OUTLINED, tooltip="Bookmark", on_click=lambda e: self.toggle_bm())
        self.mode = ft.Dropdown(options=[ft.DropdownOption(x) for x in MODES], dense=True, width=210,
                                on_select=lambda e: self.change_mode(e.control.value))
        self.zoom_lbl = ft.Text("100%", width=46, text_align=ft.TextAlign.CENTER, size=12)
        self.auto_btn = ft.IconButton(ft.Icons.SLOW_MOTION_VIDEO, tooltip="Auto-scroll (A)  ,  slower  .  faster",
                                      on_click=lambda e: self.auto_toggle())
        self.prev = ft.IconButton(ft.Icons.SKIP_PREVIOUS, tooltip="Previous chapter (P)", on_click=lambda e: self.step_chapter(-1))
        self.next = ft.FilledButton("Next", icon=ft.Icons.SKIP_NEXT, on_click=lambda e: self.step_chapter(1))
        self.chs_btn = ft.OutlinedButton("Chapters", icon=ft.Icons.LIST, on_click=lambda e: self.picker())
        self.bar = ft.Container(ft.Row([
            ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back (Esc)", on_click=lambda e: self.app.go_back()),
            self.title, self.page_lbl, self.bm,
            self.mode,
            ft.IconButton(ft.Icons.REMOVE, tooltip="Zoom out (-)", on_click=lambda e: self.zoom_by(-1)), self.zoom_lbl,
            ft.IconButton(ft.Icons.ADD, tooltip="Zoom in (+)", on_click=lambda e: self.zoom_by(1)),
            self.auto_btn, self.chs_btn, self.prev, self.next,
            ft.IconButton(ft.Icons.FULLSCREEN, tooltip="Full screen (F11)", on_click=lambda e: self.app.toggle_full()),
            ft.IconButton(ft.Icons.VERTICAL_ALIGN_TOP, tooltip="Hide this bar (H)", on_click=lambda e: self.toggle_bar()),
        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=BAR_H, padding=ft.Padding.symmetric(horizontal=8), bgcolor=ft.Colors.SURFACE_CONTAINER_LOW)
        self.body = ft.Container(expand=True)
        self.hint = ft.Container(ft.Text("", color="#ffffff", size=13), bgcolor="#cc000000", border_radius=20,
                                 padding=ft.Padding.symmetric(horizontal=14, vertical=8), opacity=0, animate_opacity=300)
        self.hint_wrap = ft.Container(ft.Row([self.hint], alignment=ft.MainAxisAlignment.CENTER), top=12, left=0, right=0)
        self.show_bar_btn = ft.Container(ft.IconButton(ft.Icons.EXPAND_MORE, tooltip="Show the bar (H)",
                                                       on_click=lambda e: self.toggle_bar(), icon_color="#ffffff",
                                                       bgcolor="#66000000"), top=6, right=8, visible=False)
        self.anchor = ft.Container(ft.Icon(ft.Icons.UNFOLD_MORE, color="#ffffff", size=22), width=34, height=34,
                                   border_radius=17, bgcolor="#99000000", alignment=ft.Alignment(0, 0), visible=False,
                                   left=0, top=0)
        self.control = ft.Column([self.bar, ft.Stack([self.body, self.hint_wrap, self.show_bar_btn, self.anchor],
                                                     expand=True)], spacing=0, expand=True)
        self._hint_until = 0.0
        self.mmb = None              # middle-button autoscroll: {"y0", "v", "t0", "gen"}
        self._wheel_t = 0.0

    # ----- shell hooks -----
    def show(self):
        self.bar.visible = self.bar_on
        self.show_bar_btn.visible = not self.bar_on

    def leave(self):
        self.auto = None
        self.mmb_stop()
        self.save(final=True)
        self.gen += 1

    def on_resize(self):
        if self.r.get("urls") is not None:
            if self.is_web():
                self.web_relayout()
            else:
                self.pg_render()

    # ----- open / save -----
    def is_web(self):
        return self.r.get("mode") == MODES[0]

    def is_rtl(self):
        return "right→left" in (self.r.get("mode") or "")

    def is_double(self):
        return (self.r.get("mode") or "").startswith("Double")

    def open(self, m, chs, idx, restart=False):
        if self.r and self.app.cur == "Reader":
            self.save()
        self.gen += 1
        gen = self.gen
        self.auto = None
        ch = chs[idx]
        key = pkey(m)
        p = DB["progress"].setdefault(key, {"read": []})
        page = 0 if restart else (p.get("page", 0) if p.get("chapter") == ch["url"] else 0)
        p.update(chapter=ch["url"], title=ch["title"], page=page, ts=time.time(),
                 manga={k: m.get(k, "") for k in ("source", "url", "title", "cover")})
        DB["last"] = {"manga": {k: m.get(k, "") for k in ("source", "url", "title", "cover")}, "key": key}
        save_db_soon(0.5)
        mode = p.get("mode", S("mode"))
        local = local_path(m, ch.get("i", idx), ch)
        src = LOCAL if local else SOURCES.get(m["source"])
        self.r = {"m": m, "chs": chs, "idx": idx, "key": key, "urls": None, "mode": mode if mode in MODES else MODES[0],
                  "zoom": float(S("reader_zoom") or 1.0), "page": page, "restore": page, "src": src, "local": local,
                  "items": [], "h": [], "parts": {}, "state": {}, "done": False, "maxpg": page - 1 if page else -1}
        self.app.show("Reader")
        self.title.value = f"{m['title'][:40]}  ·  {ch['title'][:40]}"
        self.prev.disabled = idx <= 0
        self.next.disabled = idx + 1 >= len(chs)
        self.mode.value = self.r["mode"]
        self.zoom_lbl.value = f"{int(self.r['zoom'] * 100)}%"
        self.page_lbl.value = ""
        self.bm_icon()
        self.body.content = ft.Container(ft.Column([ft.ProgressRing(), muted("Loading pages…")],
                                                   horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
                                         alignment=ft.Alignment(0, 0), expand=True, bgcolor=pal()["reader"])
        if local:
            bg(lambda: cbz_pages(local), lambda r, e: self.pages_ready(gen, r, e), pool=PAGE_POOL)
        elif isinstance(src, Source):
            bg(lambda: fetch_pages(src, ch["url"]), lambda r, e: self.pages_ready(gen, r, e), pool=PAGE_POOL)
        else:
            self.pages_ready(gen, None, RuntimeError("source not found"))
        self.app.pump.mark()

    def pages_ready(self, gen, urls, err):
        if gen != self.gen:
            return
        r = self.r
        if err or not urls:
            self.body.content = ft.Container(ft.Column([
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=40), ft.Text("Couldn't load this chapter"),
                muted(str(err)[:160] if err else "The source returned no pages."),
                ft.FilledButton("Retry", on_click=lambda e: self.open(r["m"], r["chs"], r["idx"]))],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True), alignment=ft.Alignment(0, 0), expand=True)
            return
        r["urls"] = urls
        r["page"] = min(r["page"], len(urls) - 1)
        r["restore"] = min(r["restore"], len(urls) - 1)
        self.build_body()
        self.flash_hint()

    def save(self, final=False, mark=False):
        r = self.r
        if not r or r.get("urls") is None:
            return
        p = DB["progress"].setdefault(r["key"], {"read": []})
        url = r["chs"][r["idx"]]["url"]
        if p.get("chapter") == url:
            p["page"] = r.get("page", 0)
        if mark:
            self.mark_read()
        (save_db if final else save_db_soon)()

    def mark_read(self):
        r = self.r
        if r.get("done"):
            return
        r["done"] = True
        p = DB["progress"].setdefault(r["key"], {"read": []})
        url = r["chs"][r["idx"]]["url"]
        if url not in p.setdefault("read", []):
            p["read"].append(url)
            stats.add(r["key"], ch=1)
        save_db_soon()

    def set_page(self, i):
        r = self.r
        if i == r.get("page") or not r.get("urls"):
            return
        r["page"] = i
        if i > r["maxpg"]:
            stats.add(r["key"], pg=i - max(r["maxpg"], i - 1) if r["maxpg"] >= 0 else 1)
            r["maxpg"] = i
        self.page_lbl.value = f"{i + 1} / {len(r['urls'])}"
        save_db_soon()
        if r["page"] >= len(r["urls"]) - 1 and not self.is_web():
            self.mark_read()

    async def ticker(self):
        """Reading time: counted in 15 s steps while you are active in the reader (or auto-scrolling)."""
        while True:
            await asyncio.sleep(15)
            try:
                if self.app.cur == "Reader" and self.r.get("urls") and not self.app.hidden():
                    if self.auto or time.time() - self.app.last_activity() < 120:
                        stats.add(self.r["key"], sec=15)
            except Exception as ex:
                log_error("read ticker", ex)

    # ----- body -----
    def build_body(self):
        if self.is_web():
            self.web_build()
        else:
            self.pg_build()
        self.page_lbl.value = f"{self.r['page'] + 1} / {len(self.r['urls'])}"
        self.app.pump.mark()

    def change_mode(self, mode):
        r = self.r
        if not r or mode not in MODES:
            return
        r["mode"] = mode
        self.mode.value = mode
        DB["progress"].setdefault(r["key"], {"read": []})["mode"] = mode
        save_db_soon()
        r["restore"] = r.get("page", 0)
        self.gen += 1
        r["state"], r["parts"] = {}, {}
        if r.get("urls"):
            self.build_body()
            self.flash_hint()

    def zoom_by(self, d):
        r = self.r
        z = r.get("zoom", 1.0)
        i = min(range(len(ZOOMS)), key=lambda k: abs(ZOOMS[k] - z))
        i = max(0, min(len(ZOOMS) - 1, i + d))
        r["zoom"] = ZOOMS[i]
        setv("reader_zoom", r["zoom"])
        self.zoom_lbl.value = f"{int(r['zoom'] * 100)}%"
        if r.get("urls"):
            if self.is_web():
                self.web_relayout()
            else:
                self.pg_render()
        self.app.pump.mark()

    def toggle_bar(self):
        self.bar_on = not self.bar_on
        setv("reader_bar", self.bar_on)
        self.show()
        self.app.pump.mark()

    def bm_icon(self):
        on = self.r and self.app.find_bm(self.r["m"]) is not None
        self.bm.icon = ft.Icons.BOOKMARK if on else ft.Icons.BOOKMARK_ADD_OUTLINED

    def toggle_bm(self):
        if self.r:
            self.app.toggle_bm(self.r["m"])
            self.bm_icon()
            self.app.pump.mark()

    def hint_text(self):
        if self.is_web():
            return "Scroll down to read  ·  A auto-scroll  ·  N next chapter  ·  H hide bar"
        if self.is_rtl():
            return "Right → left: click the LEFT side (or ←) for the next page"
        return "Left → right: click the RIGHT side (or →) for the next page"

    def flash_hint(self, text=None, secs=3.0):
        self.hint.content.value = text or self.hint_text()
        self.hint.opacity = 1
        self._hint_until = time.time() + secs
        if not self.is_web():
            self.pg_arrows(True)

        async def off():
            await asyncio.sleep(secs + 0.05)
            if time.time() >= self._hint_until:
                self.hint.opacity = 0
                if not self.is_web():
                    self.pg_arrows(False)
                self.app.pump.mark()
        self.app.page.run_task(off)
        self.app.pump.mark()

    # ===================== webtoon =====================
    def web_w(self):
        avail = max(320, self.app.width() - 24)
        return int(min(avail, BASE_W * self.r.get("zoom", 1.0)))

    def est_h(self, W):
        known = [h / w for (w, h) in self.r.get("dims", {}).values() if w]
        ratio = sorted(known)[len(known) // 2] if known else 1.45
        return int(W * ratio)

    def web_build(self):
        r = self.r
        n = len(r["urls"])
        W = self.web_w()
        r.setdefault("dims", {})
        r["h"] = [self.page_h(i, W) for i in range(n)]
        r["items"] = [ft.Container(height=r["h"][i], width=W, content=self.placeholder(i), alignment=ft.Alignment(0, -1))
                      for i in range(n)]
        end = ft.Container(ft.Column([
            muted("End of chapter", 13),
            ft.FilledButton("Next chapter", icon=ft.Icons.SKIP_NEXT, on_click=lambda e: self.step_chapter(1),
                            disabled=r["idx"] + 1 >= len(r["chs"])),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True, spacing=8), padding=40, alignment=ft.Alignment(0, 0))
        rows = [ft.Row([it], alignment=ft.MainAxisAlignment.CENTER, spacing=0) for it in r["items"]] + [end]
        self.lv = ft.ListView(rows, expand=True, spacing=0, on_scroll=self.web_scroll, scroll_interval=90,
                              cache_extent=2500,
                              scroll=ft.Scrollbar(thumb_visibility=True, interactive=True, thickness=14, radius=7))
        self.body.content = ft.GestureDetector(
            ft.Container(self.lv, expand=True, bgcolor=pal()["reader"]),
            on_tertiary_tap_down=self.mmb_down, on_tertiary_tap_up=self.mmb_up, on_hover=self.mmb_move,
            on_tap_down=lambda e: self.mmb_stop(), on_secondary_tap_down=lambda e: self.mmb_stop(), expand=True)
        r["offset"] = 0.0
        r["vh"] = max(200, self.app.height() - (BAR_H if self.bar_on else 0))
        k = r.get("restore", 0)
        r["page"] = k
        if k > 0:
            self.app.page.run_task(self.web_jump, k)
        self.web_load()

    def page_h(self, i, W):
        d = self.r["dims"].get(i)
        return int(W * d[1] / d[0]) if d and d[0] else self.est_h(W)

    def placeholder(self, i):
        st = self.r["state"].get(i)
        if st == "fail":
            return ft.Container(ft.Column([muted(f"Page {i + 1} failed to load"),
                                           ft.TextButton("Retry", on_click=lambda e, i=i: self.web_retry(i))],
                                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
                                alignment=ft.Alignment(0, 0), expand=True)
        return ft.Container(muted(f"{i + 1}", 22), alignment=ft.Alignment(0, 0), expand=True)

    async def web_jump(self, k):
        await asyncio.sleep(0.05)
        try:
            await self.lv.scroll_to(offset=sum(self.r["h"][:k]), duration=0)
        except Exception:
            pass

    def tops(self):
        out, y = [], 0
        for h in self.r["h"]:
            out.append(y)
            y += h
        return out

    def web_scroll(self, e: ft.OnScrollEvent):
        r = self.r
        if not r.get("items"):
            return
        self.app.note_activity()
        r["offset"], r["vh"] = e.pixels, e.viewport_dimension or r.get("vh", 800)
        probe = e.pixels + r["vh"] * 0.35
        tops = self.tops()
        i = 0
        lo, hi = 0, len(tops) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if tops[mid] <= probe:
                i, lo = mid, mid + 1
            else:
                hi = mid - 1
        self.set_page(i)
        if e.max_scroll_extent and e.pixels >= e.max_scroll_extent - 60 and i >= len(tops) - 1:
            self.mark_read()
        self.web_load()

    def web_load(self):
        """Fetch the pages around the current one; release images far away."""
        r = self.r
        n, cur, gen = len(r["urls"]), r.get("page", 0), self.gen
        want = list(range(cur, min(n, cur + WINDOW[1] + 1))) + list(range(cur - 1, max(-1, cur - WINDOW[0] - 1), -1))
        busy = sum(1 for s in r["state"].values() if s == "loading")
        for i in want:
            if busy >= 4:
                break
            if r["state"].get(i) in (None,):
                r["state"][i] = "loading"
                busy += 1
                load_page(r["src"], r["urls"][i], lambda parts, err, i=i: self.web_loaded(gen, i, parts, err),
                          alive=lambda: gen == self.gen)
        for i, st in list(r["state"].items()):
            if st == "shown" and abs(i - cur) > KEEP:
                r["state"][i] = None
                r["items"][i].content = self.placeholder(i)

    def web_loaded(self, gen, i, parts, err):
        if gen != self.gen:
            return
        r = self.r
        if err or not parts:
            r["state"][i] = "fail"
            r["items"][i].content = self.placeholder(i)
            self.app.pump.mark()
            return
        r["state"][i] = "shown"
        w = parts[0][1]
        h = sum(p[2] for p in parts)
        first_dims = not r["dims"]
        r["dims"][i] = (w, h)
        r["parts"][i] = parts
        W = self.web_w()
        new_h = int(W * h / w) if w else r["h"][i]
        delta = new_h - r["h"][i]
        r["h"][i] = new_h
        self.fill(i, W)
        if first_dims:
            for j in range(len(r["h"])):          # better estimate for the pages not loaded yet
                if j not in r["dims"]:
                    r["h"][j] = self.est_h(W)
                    r["items"][j].height = r["h"][j]
        tops = self.tops()
        if delta and tops[i] + new_h - delta <= r.get("offset", 0) + 2:
            self.app.page.run_task(self._shift, delta)      # page above the viewport grew: stay put
        self.web_load()
        self.app.pump.mark()

    async def _shift(self, delta):
        try:
            await self.lv.scroll_to(delta=delta, duration=0)
        except Exception:
            pass

    def fill(self, i, W):
        r = self.r
        parts = r["parts"].get(i) or []
        tot = sum(p[2] for p in parts) or 1
        H = r["h"][i]
        imgs = [ft.Image(src=pth, width=W, height=H * ph / tot, fit=ft.BoxFit.FILL, gapless_playback=True,
                         cache_width=int(W * 1.6), filter_quality=ft.FilterQuality.MEDIUM)
                for pth, pw, ph in parts]
        it = r["items"][i]
        it.width, it.height = W, H
        it.content = imgs[0] if len(imgs) == 1 else ft.Column(imgs, spacing=0)

    def web_retry(self, i):
        self.r["state"][i] = None
        self.web_load()

    def web_relayout(self):
        r = self.r
        if not r.get("items"):
            return
        old_tops = self.tops()
        cur = r.get("page", 0)
        frac = (r.get("offset", 0) - old_tops[cur]) / max(1, r["h"][cur])
        W = self.web_w()
        for i, it in enumerate(r["items"]):
            r["h"][i] = self.page_h(i, W)
            if r["state"].get(i) == "shown":
                self.fill(i, W)
            else:
                it.width, it.height = W, r["h"][i]
        target = sum(r["h"][:cur]) + frac * r["h"][cur]
        self.app.page.run_task(self._goto, target)
        self.app.pump.mark()

    async def _goto(self, off):
        await asyncio.sleep(0.03)
        try:
            await self.lv.scroll_to(offset=max(0, off), duration=0)
        except Exception:
            pass

    def web_scroll_by(self, px, ms=140):
        async def go():
            try:
                await self.lv.scroll_to(delta=px, duration=ms, curve=ft.AnimationCurve.EASE_OUT)
            except Exception:
                pass
        self.app.page.run_task(go)

    # ----- middle-button autoscroll (browser style) -----
    def mmb_down(self, e):
        """Middle click: scroll at a speed set by how far the mouse is from the click point. Click again (or
        release after holding and dragging) to stop."""
        self.app.note_activity()
        if not self.is_web():
            return
        if self.mmb:
            self.mmb_stop()
            return
        if self.auto:
            self.auto_toggle()
        y = e.local_position.y if e.local_position else 0
        x = e.local_position.x if e.local_position else 0
        self.mmb = {"y0": y, "v": 0.0, "t0": time.time(), "moved": False, "gen": self.gen}
        self.anchor.left, self.anchor.top, self.anchor.visible = x - 17, y - 17, True
        self.app.page.run_task(self._mmb_loop, self.gen)
        dirty()

    def mmb_up(self, e):
        m = self.mmb
        if m and m["moved"] and time.time() - m["t0"] > 0.35:     # held and dragged: stop on release
            self.mmb_stop()

    def mmb_move(self, e):
        m = self.mmb
        if not m or not e.local_position:
            return
        dy = e.local_position.y - m["y0"]
        dead = 14
        if abs(dy) > dead:
            m["moved"] = True
        m["v"] = 0.0 if abs(dy) <= dead else (abs(dy) - dead) * 4.5 * (1 if dy > 0 else -1)
        m["v"] = max(-4000.0, min(4000.0, m["v"]))

    def mmb_stop(self):
        if self.mmb:
            self.mmb = None
            self.anchor.visible = False
            dirty()

    async def _mmb_loop(self, gen):
        dt = 0.05
        while self.mmb and gen == self.gen and self.app.cur == "Reader":
            v = self.mmb["v"]
            if v:
                self.app.note_activity()
                try:
                    await self.lv.scroll_to(delta=v * dt, duration=int(dt * 1000), curve=ft.AnimationCurve.LINEAR)
                except Exception:
                    break
            await asyncio.sleep(dt)
        if gen != self.gen:
            self.mmb = None
            self.anchor.visible = False

    # ----- auto-scroll -----
    def auto_toggle(self):
        if not self.is_web():
            self.flash_hint("Auto-scroll needs the Webtoon (vertical) mode")
            return
        if self.auto:
            self.auto = None
            self.auto_btn.icon = ft.Icons.SLOW_MOTION_VIDEO
            self.flash_hint("Auto-scroll off", 1.5)
            return
        name = S("autoscroll") if S("autoscroll") in AUTO_SPEEDS else "Medium"
        self.auto = AUTO_SPEEDS[name]
        self.auto_btn.icon = ft.Icons.PAUSE_CIRCLE
        self.flash_hint(f"Auto-scroll: {name}   ( , slower   . faster   A stop )", 2.5)
        self.app.page.run_task(self._auto_loop, self.gen)

    def auto_step(self, d):
        names = list(AUTO_SPEEDS)
        cur = S("autoscroll") if S("autoscroll") in AUTO_SPEEDS else "Medium"
        i = max(0, min(len(names) - 1, names.index(cur) + d))
        setv("autoscroll", names[i])
        if self.auto:
            self.auto = AUTO_SPEEDS[names[i]]
        self.flash_hint(f"Auto-scroll: {names[i]}", 1.4)

    async def _auto_loop(self, gen):
        dt = 0.1
        while self.auto and gen == self.gen and self.app.cur == "Reader":
            try:
                await self.lv.scroll_to(delta=self.auto * dt, duration=int(dt * 1000), curve=ft.AnimationCurve.LINEAR)
            except Exception:
                break
            await asyncio.sleep(dt)
            if self.r.get("done") and self.r.get("page", 0) >= len(self.r["urls"]) - 1:
                self.auto = None
                self.auto_btn.icon = ft.Icons.SLOW_MOTION_VIDEO
                self.app.pump.mark()

    # ===================== paged =====================
    def spread(self, p):
        n = len(self.r["urls"])
        if not self.is_double():
            return [p]
        if p == 0:
            return [0]
        s = p if p % 2 == 1 else p - 1
        return [s] + ([s + 1] if s + 1 < n else [])

    def pg_build(self):
        r = self.r
        r["page"] = r.get("restore", 0)
        self.pg_area = ft.Container(expand=True, alignment=ft.Alignment(0, 0))
        arrow = lambda icon, label: ft.Container(
            ft.Column([ft.Icon(icon, size=46, color="#ffffff"), ft.Text(label, color="#ffffff", size=12)],
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True, spacing=2),
            bgcolor="#55000000", border_radius=40, padding=14, opacity=0, animate_opacity=250)
        nxt, prv = "Next", "Back"
        left_lbl, right_lbl = (nxt, prv) if self.is_rtl() else (prv, nxt)
        self.arr_l = arrow(ft.Icons.CHEVRON_LEFT, left_lbl)
        self.arr_r = arrow(ft.Icons.CHEVRON_RIGHT, right_lbl)

        def zone(arr, side):
            return ft.GestureDetector(
                ft.Container(ft.Row([arr], alignment=ft.MainAxisAlignment.START if side < 0 else ft.MainAxisAlignment.END),
                             expand=True, padding=ft.Padding.symmetric(horizontal=18), alignment=ft.Alignment(side, 0),
                             on_hover=lambda e, a=arr: self._arrow_hover(a, e)),
                on_tap=lambda e: self.pg_click(side), mouse_cursor=ft.MouseCursor.CLICK, expand=True)

        self.body.content = ft.GestureDetector(ft.Container(ft.Stack([
            self.pg_area,
            ft.Row([zone(self.arr_l, -1), ft.Container(width=0, expand=True), zone(self.arr_r, 1)], expand=True, spacing=0),
        ], expand=True), bgcolor=pal()["reader"], expand=True), on_scroll=self.pg_wheel,
            on_tertiary_tap_down=lambda e: self.pg_step(1), expand=True)
        self.pg_render()

    def pg_wheel(self, e):
        """Mouse wheel in Single/Double mode turns pages (and moves on to the next chapter at the end)."""
        self.app.note_activity()
        if self.r.get("zoom", 1.0) > 1:
            return                                    # zoomed in: the wheel pans the page instead
        now = time.time()
        if now - self._wheel_t < 0.22:
            return
        dy = e.scroll_delta.y if e.scroll_delta else 0
        if not dy:
            return
        self._wheel_t = now
        self.pg_step(1 if dy > 0 else -1)

    def _arrow_hover(self, arr, e):
        arr.opacity = 1 if e.data in (True, "true") else 0
        dirty()

    def pg_arrows(self, on):
        for a in (getattr(self, "arr_l", None), getattr(self, "arr_r", None)):
            if a is not None:
                a.opacity = 1 if on else 0

    def pg_click(self, side):
        self.app.note_activity()
        forward = (side < 0) == self.is_rtl()
        self.pg_step(1 if forward else -1)

    def pg_step(self, d):
        r = self.r
        n = len(r["urls"])
        sp = self.spread(r["page"])
        if d > 0:
            if sp[-1] + 1 >= n:
                self.mark_read()
                if r["idx"] + 1 < len(r["chs"]):
                    self.step_chapter(1)
                else:
                    self.flash_hint("That's the latest chapter", 2)
                return
            self.set_page(sp[-1] + 1)
        else:
            if sp[0] == 0:
                if r["idx"] > 0:
                    self.step_chapter(-1)
                return
            self.set_page(self.spread(sp[0] - 1)[0])
        self.pg_render()

    def pg_render(self):
        r = self.r
        gen = self.gen
        sp = self.spread(r.get("page", 0))
        if self.is_rtl():
            sp = list(reversed(sp))
        H = max(200, self.app.height() - (BAR_H if self.bar_on else 0) - 24)
        z = r.get("zoom", 1.0)
        imgs, total_w = [], 0
        guides = S("paged_guides")
        for i in sp:
            parts = r["parts"].get(i)
            if not parts:
                imgs.append(ft.Container(ft.ProgressRing() if r["state"].get(i) != "fail" else
                                         ft.TextButton("Page failed. Retry", on_click=lambda e, i=i: self.pg_retry(i)),
                                         width=H * 0.68 * z, height=H * z, alignment=ft.Alignment(0, 0)))
                total_w += H * 0.68 * z
                if r["state"].get(i) is None:
                    r["state"][i] = "loading"
                    load_page(r["src"], r["urls"][i], lambda p, e, i=i: self.pg_loaded(gen, i, p, e))
                continue
            w = parts[0][1]
            h = sum(p[2] for p in parts)
            ih = H * z
            iw = ih * w / h
            col = ft.Column([ft.Image(src=pth, width=iw, height=ih * ph / h, fit=ft.BoxFit.FILL, gapless_playback=True,
                                      cache_height=int(ih * 1.6)) for pth, pw, ph in parts], spacing=0)
            page_box = ft.Container(col, border=ft.Border.all(5, "#000000") if guides else None)
            imgs.append(ft.Column([page_box, *( [muted(str(i + 1), 11)] if guides else [])], spacing=2, tight=True,
                                  horizontal_alignment=ft.CrossAxisAlignment.CENTER))
            total_w += iw
        r["pg_w"] = total_w
        gap = 16 if (len(sp) == 2 and guides) else 0
        row = ft.Row(imgs, spacing=gap, alignment=ft.MainAxisAlignment.CENTER, tight=True)
        if z > 1:
            self.pg_area.content = ft.Column([ft.Row([row], scroll=ft.ScrollMode.AUTO, alignment=ft.MainAxisAlignment.CENTER)],
                                             scroll=ft.ScrollMode.AUTO, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        else:
            self.pg_area.content = row
        self.page_lbl.value = f"{r['page'] + 1} / {len(r['urls'])}"
        for j in range(sp[-1] + 1, min(len(r["urls"]), sp[-1] + 4)):     # preload the next pages
            if r["state"].get(j) is None:
                r["state"][j] = "loading"
                load_page(r["src"], r["urls"][j], lambda p, e, j=j: self.pg_loaded(gen, j, p, e))
        self.app.pump.mark()

    def pg_loaded(self, gen, i, parts, err):
        if gen != self.gen:
            return
        r = self.r
        r["state"][i] = "fail" if (err or not parts) else "shown"
        if parts:
            r["parts"][i] = parts
        if i in self.spread(r.get("page", 0)):
            self.pg_render()

    def pg_retry(self, i):
        self.r["state"][i] = None
        self.pg_render()

    # ----- chapters -----
    def step_chapter(self, d):
        r = self.r
        if r and 0 <= r["idx"] + d < len(r["chs"]):
            if d > 0:
                self.mark_read()
            self.save()
            self.open(r["m"], r["chs"], r["idx"] + d)

    def picker(self):
        r = self.r
        if not r:
            return
        chs, idx = r["chs"], r["idx"]
        prog = DB["progress"].get(r["key"], {})
        read = set(prog.get("read") or [])
        err = ft.Text("", color=ft.Colors.ERROR, size=12)
        num = ft.TextField(label="Chapter number", autofocus=True, dense=True, width=180)

        def go(i):
            self.app.page.pop_dialog()
            self.save()
            self.open(r["m"], chs, i)

        def submit(e=None):
            t = (num.value or "").strip()
            target = None
            try:
                v = float(t)
                for i, c in enumerate(chs):           # match the chapter's own number first
                    mt = re.search(r"(\d+(?:\.\d+)?)", c.get("title") or "")
                    if mt and float(mt.group(1)) == v:
                        target = i
                        break
                if target is None and v.is_integer() and 1 <= int(v) <= len(chs):
                    target = int(v) - 1
            except ValueError:
                pass
            if target is None:
                err.value = f"No chapter {t}"
                self.app.pump.mark()
                return
            go(target)

        num.on_submit = submit
        H = 40
        lv = ft.ListView([ft.Container(ft.Row([
            ft.Text(f"{i + 1}", width=50, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text(c.get("title") or f"Chapter {i + 1}", expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                    weight=ft.FontWeight.BOLD if i == idx else None,
                    color=ft.Colors.PRIMARY if i == idx else (ft.Colors.ON_SURFACE_VARIANT if c["url"] in read else None)),
            ft.Icon(ft.Icons.CHECK, size=14, color=ft.Colors.ON_SURFACE_VARIANT) if c["url"] in read else ft.Container(width=14)]),
            height=H, padding=ft.Padding.symmetric(horizontal=10), ink=True, on_click=lambda e, i=i: go(i),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH if i == idx else None) for i, c in enumerate(chs)],
            item_extent=H, height=420, width=460)
        self.app.page.show_dialog(ft.AlertDialog(
            title=ft.Text(f"Chapters ({len(chs)})"),
            content=ft.Column([ft.Row([num, ft.FilledButton("Go", on_click=submit)]), err, lv], tight=True)))

        async def center():
            await asyncio.sleep(0.15)
            try:
                await lv.scroll_to(offset=max(0, idx - 4) * H, duration=0)
            except Exception:
                pass
        self.app.page.run_task(center)

    # ----- keys -----
    def on_key(self, e: ft.KeyboardEvent):
        k = e.key
        r = self.r
        if not r:
            return
        if k == "Escape":
            if self.auto:
                self.auto_toggle()
            else:
                self.app.go_back()
            return
        if k in ("A",):
            self.auto_toggle()
            return
        if k in (",", "[", "Comma", "Bracket Left"):
            self.auto_step(-1)
            return
        if k in (".", "]", "Period", "Bracket Right"):
            self.auto_step(1)
            return
        if k == "H":
            self.toggle_bar()
            return
        if k == "C":
            self.picker()
            return
        if k == "N":
            self.step_chapter(1)
            return
        if k == "P":
            self.step_chapter(-1)
            return
        if k in ("=", "+", "Numpad Add"):
            self.zoom_by(1)
            return
        if k in ("-", "Numpad Subtract"):
            self.zoom_by(-1)
            return
        if not r.get("urls"):
            return
        if self.is_web():
            vh = r.get("vh", 700)
            amt = {"Arrow Down": 140, "Arrow Up": -140, " ": vh * 0.85, "Page Down": vh * 0.85,
                   "Page Up": -vh * 0.85}.get(k)
            if amt:
                if self.auto:
                    self.auto_toggle()
                self.web_scroll_by(amt)
            elif k == "Arrow Right":
                self.step_chapter(1)
            elif k == "Arrow Left":
                self.step_chapter(-1)
        else:
            fwd = "Arrow Left" if self.is_rtl() else "Arrow Right"
            back = "Arrow Right" if self.is_rtl() else "Arrow Left"
            if k in (fwd, " ", "Page Down", "Arrow Down"):
                self.pg_step(1)
            elif k in (back, "Page Up", "Arrow Up"):
                self.pg_step(-1)
