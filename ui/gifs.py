"""A random transparent GIF in the empty space at the foot of the nav rail; each one says a line in a
small speech bubble when it shows up.

GIFs come from assets/gifs (shipped inside the exe) plus any the user drops into data/gifs.
tools/prep_gifs.py crops them and fixes broken frame timings before they go into assets/gifs.
The character is the file name without its trailing number (luffy3.gif -> luffy); its lines are in
gif_lines.py. Which GIF shows and what it says are random and can't be picked. Right-click turns GIFs off,
Settings → Look turns them back on. The folders are read on every pick, so new files show up without a restart.
"""

import asyncio
import os
import random
import re
import sys
import time

import flet as ft

from config import DATA
from storage import S, log_error

from .core import setv
from .gif_lines import LINES, NAMES

DIR = os.path.join(DATA, "gifs")                     # the user's own GIFs
BUNDLED = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "assets", "gifs")             # the ones that ship (inside the exe when frozen)
SWAP_S = 20                         # another GIF every 20 seconds (never while a line is up); each one says a line


def gif_files():
    out = []
    for d in (BUNDLED, DIR):
        try:
            out += [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(".gif")]
        except OSError:
            pass
    return out


def who(path):
    return re.sub(r"[\d_\- ]+$", "", os.path.splitext(os.path.basename(path))[0]).lower()


class GifSpot:
    def __init__(self, app, w, h):
        self.app = app
        self.w, self.h = w, h
        self.cur = ""
        self._said = []                     # recent lines, so they don't repeat soon
        self._tok = 0
        os.makedirs(DIR, exist_ok=True)
        self.box = ft.Container(width=w, height=h, padding=4, alignment=ft.Alignment(0, 1))
        self.control = ft.GestureDetector(self.box, on_secondary_tap_down=self.menu)
        self.name_t = ft.Text("", size=9, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY)
        self.say_t = ft.Text("", size=11)
        self.bubble = ft.Container(ft.Column([self.name_t, self.say_t], spacing=0, tight=True),
                                   left=w + 2, bottom=40, width=170, padding=ft.Padding.symmetric(horizontal=8, vertical=5),
                                   border_radius=10, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                                   border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                                   shadow=ft.BoxShadow(blur_radius=6, color="#33000000"),
                                   opacity=0, animate_opacity=250, visible=False, on_click=lambda e: self.hush())

    def showing(self):
        return bool(self.cur) and self.app.cur != "Reader" and not self.app.hidden()

    def next(self):
        files = gif_files() if S("gifs") else []
        self.hush()
        if not files:
            self.cur = ""
            self.box.content = None
        else:
            self.cur = random.choice([f for f in files if f != self.cur] or files)
            self.box.content = ft.Image(src=self.cur, width=self.w - 8, height=self.h - 8,
                                        fit=ft.BoxFit.CONTAIN, gapless_playback=True)
        self.app.pump.mark()

    def say(self):
        lines = LINES.get(who(self.cur)) if self.cur else None
        if not lines or not self.showing():
            return
        line = random.choice([x for x in lines if x not in self._said] or lines)
        self._said = (self._said + [line])[-10:]
        self.name_t.value = NAMES.get(who(self.cur), who(self.cur).title())
        self.say_t.value = line
        self.bubble.visible = True
        self.bubble.opacity = 1
        self._tok += 1
        self.app.page.run_task(self._fade, self._tok, 2.5 + len(line) * 0.04)
        self.app.pump.mark()

    def menu(self, e):
        """Right-click: the only control there is, turning GIFs off."""
        if not self.cur:
            return

        def off():
            setv("gifs", False)
            self.next()
            self.app.toast("GIFs off. Settings → Look turns them back on.")
        g = getattr(e, "global_position", None)
        pos = (g.x, g.y) if g is not None else (self.w, self.app.height() - self.h - 60)
        self.app.context_menu(pos, [(ft.Icons.VISIBILITY_OFF, "Disable GIFs", off)],
                              header=NAMES.get(who(self.cur), who(self.cur).title()))

    def hush(self):
        self._tok += 1
        self.bubble.opacity = 0
        self.bubble.visible = False
        self.app.pump.mark()

    async def _fade(self, tok, after):
        await asyncio.sleep(after)
        if tok != self._tok:
            return
        self.bubble.opacity = 0
        self.app.pump.mark()
        await asyncio.sleep(0.3)
        if tok == self._tok:
            self.bubble.visible = False
            self.app.pump.mark()

    async def run(self):
        swap_at, first = time.time() + 3, True          # the first GIF speaks a few seconds after start
        while True:
            await asyncio.sleep(1)
            try:
                now = time.time()
                if now < swap_at or self.bubble.visible or not self.showing():
                    continue
                if not first:
                    self.next()
                first = False
                self.say()
                swap_at = now + SWAP_S
            except Exception as ex:
                log_error("gif loop", ex)
