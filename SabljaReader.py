import os, sys, re, time, hashlib, threading, queue, shutil, zipfile, random, io, math, platform, webbrowser, traceback, tempfile, subprocess
from typing import Any, cast
from urllib.parse import urlencode
import requests
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk

from assets import make_icon, make_icon_file
from textures import paper_tile, paper_avg
from config import (BASE, DATA, CACHE, SRC_FILE,
                    CARD_W, CARD_H, SMALL_W, SMALL_H, CARD_CELL,
                    SMALL_CELL, MODES, ZOOMS, PAPERS, APP_VERSION,
                    PAGE_BORDER, PAGE_GAP, REPO_URL, GITHUB_API, UPDATE_ASSET)
from storage import (DB, S, save_db, save_db_soon, log_error, load_update_state,
                     save_update_state, pkey, cached_genres, remember_genres,
                     cache_path, prune_cache, dl_records, backup_db)
from sources import (SOURCES, Source, LOCAL, rebuild_sources, fetch_pages, load_img, bg,
                     cffi, Q, PAGE_POOL, THUMB_CACHE, THUMB_LOCK, cbz_pages, source_hidden,
                     hidden_ids, get_rating, dl_folder_for, local_chapters, local_chapters_any,
                     local_path, downloaded_manga)
from downloads import DL_Q, JOBS, dl_path, next_job_id

# ---------------- theme (silver on graphite) ----------------
# The chrome colours follow the chosen background, so the flat menu areas sit on the
# same surface as the textured sidebar/reader instead of fighting it. theme_pick()
# swaps these when the Background setting changes.
ROLES = ("BG", "SIDE", "PANEL", "CARD", "CARD_HI", "BTN", "BTN_HI", "LINE", "READER_BG",
         "TEXT", "MUTED", "SILVER", "SILVER_HI", "SILVER_DIM", "INK")
_TXT_DARK = {"TEXT": "#e7e9ed", "MUTED": "#8a8f99", "SILVER": "#c5cad3",
             "SILVER_HI": "#e8ebf0", "SILVER_DIM": "#7d838e", "INK": "#14151a"}
_TXT_PAPER = {"TEXT": "#37342c", "MUTED": "#6f6a5d", "SILVER": "#575245",
              "SILVER_HI": "#2a2822", "SILVER_DIM": "#8b8574", "INK": "#f4efe3"}
PALETTES = {
    "Off": {"BG": "#131417", "SIDE": "#0f1012", "PANEL": "#1b1c20", "CARD": "#222428",
            "CARD_HI": "#2d2f36", "BTN": "#2b2d33", "BTN_HI": "#3a3d45", "LINE": "#32353c",
            "READER_BG": "#0c0c0e", **_TXT_DARK},
    "Graphite matte": {"BG": "#1d1e22", "SIDE": "#1c1d21", "PANEL": "#24252a", "CARD": "#2b2d33",
                       "CARD_HI": "#373941", "BTN": "#2d2f35", "BTN_HI": "#3c3f47", "LINE": "#35383f",
                       "READER_BG": "#1a1b1f", **_TXT_DARK},
    "Ink matte": {"BG": "#101113", "SIDE": "#0f1012", "PANEL": "#17181c", "CARD": "#1e2024",
                  "CARD_HI": "#292b31", "BTN": "#202226", "BTN_HI": "#2e3038", "LINE": "#272a30",
                  "READER_BG": "#0e0e10", **_TXT_DARK},
    "Paper": {"BG": "#ded7c6", "SIDE": "#d8d1bf", "PANEL": "#eae3d2", "CARD": "#f4eedd",
              "CARD_HI": "#e2dbc9", "BTN": "#e3dccb", "BTN_HI": "#d3cbb6", "LINE": "#b3aa93",
              "READER_BG": "#8f8878", **_TXT_PAPER},
}
LIGHT_PAPERS = ("Paper",)
BG, SIDE, PANEL, CARD, CARD_HI = "#1d1e22", "#1c1d21", "#24252a", "#2b2d33", "#373941"
BTN, BTN_HI, LINE = "#2d2f35", "#3c3f47", "#35383f"
SILVER, SILVER_HI, SILVER_DIM, INK = "#c5cad3", "#e8ebf0", "#7d838e", "#14151a"
TEXT, MUTED, READER_BG = "#e7e9ed", "#8a8f99", "#1a1b1f"
FONT = ("Segoe UI", 12)



DL_VIEW_CHIP = "__downloaded__"


def theme_pick(paper):
    """Adopt the palette that belongs with a background (chrome + text roles).

    Also flips customtkinter's own appearance mode: CTk resolves every "transparent"
    widget against its theme's window colour, so a light palette needs "light" or the
    scroll areas and menu frames stay dark.
    """
    want = PALETTES.get(paper) or PALETTES["Off"]
    g = globals()
    for r in ROLES:
        g[r] = want[r]
    try:
        ctk.set_appearance_mode("light" if paper in LIGHT_PAPERS else "dark")
    except Exception:
        pass


# ---------------- storage ----------------
def reader_muted():
    """Muted text for overlay labels on the reader's own background."""
    return "#6f6a5d" if S("reader_paper") in LIGHT_PAPERS else "#9aa0ab"


def genre_text(genres, limit=2):
    """Compact label for a card: 'Action · Fantasy +3'."""
    gs = [str(g).strip() for g in (genres or []) if str(g).strip()]
    if not gs:
        return ""
    s = " · ".join(gs[:limit])
    if len(gs) > limit:
        s += f" +{len(gs) - limit}"
    return s


WT_MAX_INFLIGHT = 6        # pages downloading at once in webtoon mode (PAGE_POOL has 6 threads)
WT_AHEAD = 5               # pages kept loaded below the viewport
WT_BEHIND = 1              # ... and above it
WT_KEEP = 1                # extra pages kept before an image is dropped from memory
WT_MAX_PX = 14000000       # cap for one page's Tk image (~56 MB): tall strips are the memory hogs
WT_STRIP = 1000            # tall pages are shown as stacked strips of at most this height
WT_STRIPS_PER_TICK = 2     # strip images built per frame, so a huge page never blocks scrolling
# Middle-click auto-scroll: the pointer's distance from the viewport centre sets direction and
# speed, so a middle click in the lower half starts a slow downward scroll without any dragging.
MMB_DEAD = 26              # px around the viewport centre where the view stands still
MMB_MIN = 55.0             # px/s just outside the dead zone (slow reading speed)
MMB_MAX = 1150.0           # px/s at the top/bottom edge of the viewport
MMB_TICK = 16              # ms between auto-scroll frames
MMB_TAU_UP = 0.16          # s - time constant while speeding up (snappy)
MMB_TAU_DOWN = 0.42        # s - time constant while slowing down (soft landing)
_PH = None


def page_box():
    """A 1x1 transparent image. A label needs an image for width/height to be in pixels, so this is
    what lets a page keep its exact box (and the scroll position) before/after its real image loads."""
    global _PH
    if _PH is None:
        _PH = tk.PhotoImage(width=1, height=1)
    return _PH


def img_size(url):
    """(width, height) of a page without decoding its pixels - cache file or downloaded .cbz member."""
    try:
        if url.startswith("cbz|"):
            _, path, member = url.split("|", 2)
            with zipfile.ZipFile(path) as z:
                with Image.open(io.BytesIO(z.read(member))) as im:
                    return im.size
        p = cache_path(url)
        if os.path.exists(p):
            with Image.open(p) as im:
                return im.size
    except Exception:
        pass
    return (0, 0)



def version_key(v):
    """'v1.4' / '1.4.0' -> (1, 4, 0), so release tags and APP_VERSION compare naturally."""
    nums = [int(n) for n in re.findall(r"\d+", str(v or ""))][:3]
    return tuple(nums + [0] * (3 - len(nums)))


def running_installed():
    """True only for the copy NSIS placed in its registered install folder (not a portable exe)."""
    if not getattr(sys, "frozen", False):
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\SabljaReader") as k:
            folder = str(winreg.QueryValueEx(k, "InstallDir")[0])
        return os.path.normcase(os.path.abspath(folder)) == os.path.normcase(os.path.abspath(BASE))
    except Exception:
        return False


def fetch_latest_release():
    """Latest public GitHub release, as a small dict the UI can render. Runs on a worker thread."""
    r = requests.get(GITHUB_API, timeout=12,
                     headers={"Accept": "application/vnd.github+json",
                              "User-Agent": f"SabljaReader/{APP_VERSION}"})
    r.raise_for_status()
    j = r.json()
    tag = str(j.get("tag_name") or "").strip()
    asset = next((a for a in (j.get("assets") or [])
                  if str(a.get("name") or "").lower() == UPDATE_ASSET.lower()), None)
    return {"tag": tag,
            "page": j.get("html_url") or f"{REPO_URL}/releases/latest",
            "notes": str(j.get("body") or "").strip()[:4000],
            "asset": asset or {}}


def download_release_asset(info):
    """Download the installer asset into %TEMP%, checking size and SHA-256 when GitHub provides them."""
    asset = info.get("asset") or {}
    url = str(asset.get("browser_download_url") or "")
    if not url.startswith(f"{REPO_URL}/releases/download/"):
        raise RuntimeError("unexpected download URL")
    tag = re.sub(r"[^0-9A-Za-z._-]+", "_", str(info.get("tag") or "latest"))
    dest = os.path.join(tempfile.gettempdir(), f"SabljaReader-Setup-{tag}.exe")
    part = dest + ".part"
    h = hashlib.sha256()
    with requests.get(url, stream=True, timeout=120,
                      headers={"User-Agent": f"SabljaReader/{APP_VERSION}"}) as r:
        r.raise_for_status()
        with open(part, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                if chunk:
                    f.write(chunk)
                    h.update(chunk)
    try:
        size = os.path.getsize(part)
        want = int(asset.get("size") or 0)
        if want and size != want:
            raise RuntimeError("download size does not match the release")
        digest = str(asset.get("digest") or "")
        if digest.startswith("sha256:") and h.hexdigest() != digest.split(":", 1)[1].lower():
            raise RuntimeError("download checksum does not match the release")
        os.replace(part, dest)
    except Exception:
        try:
            os.remove(part)
        except Exception:
            pass
        raise
    return dest


# ---------------- ui helpers ----------------
def clear(f):
    for w in f.winfo_children():
        w.destroy()


def age_str(ts):
    """'just now' / '5 min ago' / '3 h ago' / '2 d ago' for history captions."""
    try:
        d = max(0, int(time.time() - float(ts)))
    except Exception:
        return ""
    if d < 90:
        return "just now"
    if d < 3600:
        return f"{d // 60} min ago"
    if d < 86400:
        return f"{d // 3600} h ago"
    if d < 86400 * 30:
        return f"{d // 86400} d ago"
    return time.strftime("%d %b %Y", time.localtime(float(ts)))


def set_img(widget, im, size=None):
    if im is None:
        return
    try:
        ci = ctk.CTkImage(im, size=size or im.size)
        widget.configure(image=ci, text="")
        widget.image = ci
    except Exception:
        pass


def btn(parent, text, cmd=None, primary=False, **kw):
    if primary:
        kw.setdefault("fg_color", SILVER); kw.setdefault("hover_color", SILVER_HI); kw.setdefault("text_color", INK)
    else:
        kw.setdefault("fg_color", BTN); kw.setdefault("hover_color", BTN_HI); kw.setdefault("text_color", TEXT)
    kw.setdefault("corner_radius", 8); kw.setdefault("height", 34); kw.setdefault("font", FONT)
    return ctk.CTkButton(parent, text=text, command=cmd, **kw)


def menu(parent, values, cmd, **kw):
    kw.setdefault("width", 160)
    return ctk.CTkOptionMenu(parent, values=values, command=cmd, fg_color=BTN, button_color=BTN_HI, button_hover_color=SILVER_DIM,
                             dropdown_fg_color=PANEL, dropdown_hover_color=BTN_HI, text_color=TEXT, dropdown_text_color=TEXT,
                             font=FONT, dropdown_font=FONT, corner_radius=8, height=34, **kw)


def entry(parent, **kw):
    return ctk.CTkEntry(parent, fg_color=CARD, border_color=LINE, text_color=TEXT, placeholder_text_color=MUTED,
                        corner_radius=8, height=36, font=FONT, **kw)


def style_ttk():
    st = ttk.Style()
    try:
        st.theme_use("clam")
    except Exception:
        pass
    st.configure("S.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=34, borderwidth=0,
                 font=("Segoe UI", 11), relief="flat")
    st.map("S.Treeview", background=[("selected", CARD_HI)], foreground=[("selected", SILVER_HI)])
    st.configure("S.Treeview.Heading", background=PANEL, foreground=MUTED, relief="flat", font=("Segoe UI", 10, "bold"))
    st.layout("S.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])


# ---------------- app ----------------
# ---------------- randomizer ----------------
def random_pick(avoid):
    """Worker thread: one random title from a random enabled source (popular listing, random page)."""
    srcs = [s for s in SOURCES.values() if (S("nsfw") or not s.nsfw) and not source_hidden(s.id) and s.kinds()]
    random.shuffle(srcs)
    err = None
    for s in srcs[:6]:
        kind = "popular" if "popular" in s.kinds() else s.kinds()[0]
        top = 100 if s.api == "mangadex" else (len(s.WT_RANKS) if s.api == "webtoons" else 20)
        page = random.randint(1, top)
        while True:
            try:
                items = [x for x in s.listing(kind, page) if x["url"] not in avoid]
            except Exception as e:
                err, items = e, []
                if page == 1:
                    break
            if items:
                return random.choice(items)
            if page == 1:
                break
            page = max(1, page // 2)   # past the last page -> retry closer to the start
    if err:
        raise err
    return None



class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        theme_pick(S("paper"))          # the saved background decides the chrome palette
        self.title("Sablja Reader")
        self.geometry("1280x800")
        self.minsize(1000, 640)
        self._fs = bool(S("start_fullscreen"))
        self._borderless = False
        self._win_geom = "1280x800"
        if self._fs:
            self.after(60, self.start_fullscreen)
        ico = os.path.join(DATA, "sablja2.ico")   # new name so the new logo replaces an old cached icon
        try:
            make_icon_file(ico)
            self.after(300, lambda: self.iconbitmap(ico))  # CTk sets its own icon at ~200ms, so set ours after
        except Exception:
            try:
                self.iconphoto(True, cast(tk.PhotoImage, ImageTk.PhotoImage(make_icon(64))))
            except Exception:
                pass
        style_ttk()
        self.cur, self.back, self.cur_detail = None, "Library", None
        self.reader: dict[str, Any] = {}
        self.b: dict[str, Any] = {}
        self.rtok = self.dtok = self.rgen = 0
        self.lib_folder, self.sel, self.desc, self.desc_full = "All", set(), True, False
        self.genre_map, self.kind_btns, self.zoom_job = {}, {}, None
        self.genre_menu, self.btok = None, 0
        self.stok, self.search_src = 0, None
        self._seen_titles = set()
        self._grid_state: dict[Any, dict[str, Any]] = {}
        self._reflow_jobs: dict[str, Any] = {}
        self._side_job = None
        self._mmb: dict[str, Any] | None = None
        self._mmb_job = None
        self._upd_busy = False
        self._upd_win = None
        self.rand_mode, self._rand_open, self.rdm_tok = False, False, 0
        self.rand_hist, self.rand_i, self.rand_seen = [], -1, set()
        self._fresh, self._fresh_thr, self._fresh_last = {}, None, 0
        self.nav_build()
        rebuild_sources()
        self.bind_all("<MouseWheel>", self.on_wheel, add="+")
        self.bind_all("<Button-2>", self.mmb_press, add="+")
        self.bind_all("<Button-1>", self.mmb_click_stop, add="+")
        self.bind_all("<Button-3>", self.mmb_click_stop, add="+")
        self.bind_all("<Key>", self.on_key, add="+")
        self.bind_all("<F11>", self.toggle_fullscreen, add="+")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.build_ui()
        self.after(60, self.poll)
        self.after(500, self.watch)
        self.after(3000, lambda: self.check_updates())

    def start_fullscreen(self):
        self.set_borderless(True, save_geom=False)

    def toggle_fullscreen(self, _event=None):
        """F11 (or the title-bar button): borderless fullscreen with our own controls."""
        self.set_borderless(not self._borderless)

    def set_borderless(self, on, save_geom=True):
        """Borderless fullscreen = content edge to edge, with the app's own window bar.

        Tk's `-fullscreen` hides the title bar but also ignores the custom bar, which is
        why the app used to end up with either no controls or two sets of them.
        """
        on = bool(on)
        if on == self._borderless:
            self._fs = on
            self.sync_window_controls()
            return
        try:
            if on:
                if not self._borderless and save_geom:
                    self._win_geom = self.geometry()
                self._fs = self._borderless = True
                self.overrideredirect(True)
                w, h = self.winfo_screenwidth(), self.winfo_screenheight()
                self.geometry(f"{w}x{h}+0+0")
                self.lift()
                self.after(20, self.focus_force)
            else:
                self._fs = self._borderless = False
                self.overrideredirect(False)
                geom = self._win_geom or "1280x800"
                if "+" not in geom:
                    try:
                        w, h = (int(v) for v in geom.lower().split("x", 1))
                        geom = f"{w}x{h}+{max(0, (self.winfo_screenwidth() - w) // 2)}+" \
                               f"{max(0, (self.winfo_screenheight() - h) // 2)}"
                    except Exception:
                        geom = "1280x800"
                self.geometry(geom)
                self.deiconify()
            self.sync_window_controls()
            self.after(40, self.paint_side)
        except Exception:
            # Non-Windows fallback if a window manager refuses overrideredirect.
            try:
                self._fs = self._borderless = on
                self.attributes("-fullscreen", on)
                self.sync_window_controls()
            except Exception:
                pass

    def sync_window_controls(self):
        """Show the custom window bar only when the native title bar is gone."""
        try:
            if not hasattr(self, "winbar"):
                return
            if self._borderless:
                kids = [w for w in self.main.pack_slaves() if w is not self.winbar]
                if kids:
                    self.winbar.pack(side="top", fill="x", before=kids[0])
                else:
                    self.winbar.pack(side="top", fill="x")
            else:
                self.winbar.pack_forget()
            if hasattr(self, "win_fs"):
                self.win_fs.configure(text="\u2750" if self._borderless else "\u25a1")
        except Exception:
            pass

    def minimize_window(self):
        """Leave fullscreen first, so a minimized window still has a taskbar entry."""
        try:
            if self._borderless:
                self.set_borderless(False)
            self.iconify()
        except Exception:
            pass

    def build_ui(self):
        """Create the whole window: sidebar canvas, views and every view's widgets.

        Kept separate from __init__ so a theme change can throw the old widgets away and
        rebuild from scratch — recolouring hundreds of live widgets in place kept leaving
        parts of the window (notably scroll areas) on the previous palette.
        """
        self.configure(fg_color=BG)
        style_ttk()                     # ttk treeviews need the palette re-applied after a theme change
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # The sidebar is a canvas, not a frame: that is the only way the paper texture can show
        # through the menu (a CTk frame always paints a flat colour on top of it).
        self.side = tk.Canvas(self, width=210, highlightthickness=0, bd=0, bg=SIDE)
        self.side.grid(row=0, column=0, sticky="ns")
        self.nav, self._nav_items, self._hover, self._logo_img = {}, {}, None, None
        self.side.bind("<Configure>", lambda e: self.sched_paint_side())
        self.after(40, self.paint_side)

        self.main = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")

        # A slim title strip over the content keeps window controls in the usual top-right
        # place - also when the app starts in borderless fullscreen and has no native title bar.
        self.winbar = ctk.CTkFrame(self.main, height=32, fg_color="transparent", corner_radius=0)
        self.winbar.pack(side="top", fill="x")
        self.winbar.pack_propagate(False)
        self.win_close = ctk.CTkButton(self.winbar, text="\u2715", command=self.close, width=30, height=24,
                                       corner_radius=6, fg_color="transparent", hover_color="#a83a3a",
                                       text_color=MUTED, font=("Segoe UI", 11, "bold"))
        self.win_close.pack(side="right", padx=(4, 10), pady=4)
        self.win_fs = ctk.CTkButton(self.winbar, text="\u2750" if self._fs else "\u25a1",
                                    command=self.toggle_fullscreen, width=30, height=24, corner_radius=6,
                                    fg_color="transparent", hover_color=BTN_HI, text_color=MUTED,
                                    font=("Segoe UI", 11, "bold"))
        self.win_fs.pack(side="right", padx=4, pady=4)
        self.win_min = ctk.CTkButton(self.winbar, text="\u2014", command=self.minimize_window, width=30, height=24,
                                     corner_radius=6, fg_color="transparent", hover_color=BTN_HI,
                                     text_color=MUTED, font=("Segoe UI", 11, "bold"))
        self.win_min.pack(side="right", padx=4, pady=4)

        self.views = {n: ctk.CTkFrame(self.main, fg_color="transparent", corner_radius=0)
                      for n in ["Library", "History", "Rating", "Sources", "Search", "Randomizer",
                                "Downloads", "Settings", "Details", "Reader"]}
        self.build_library(); self.build_history(); self.build_rating(); self.build_sources()
        self.build_search(); self.build_downloads()
        self.build_settings(); self.build_details(); self.build_reader()
        self.refresh = {"Library": self.refresh_library, "History": self.refresh_history,
                        "Rating": self.refresh_rating, "Sources": self.refresh_sources,
                        "Settings": self.refresh_settings, "Search": self.refresh_search}
        self.show(self.cur or "Library")
        self.sync_window_controls()      # no duplicate buttons while we have a native title bar

    def rebuild_ui(self):
        """Throw the widgets away and build them again (used by the theme switch)."""
        if getattr(self, "_rebuilding", False):
            return
        self._rebuilding = True
        try:
            keep = self.cur if self.cur in ("Library", "History", "Rating", "Sources",
                                            "Randomizer", "Downloads", "Settings") else "Library"
            for w in self.winfo_children():
                w.destroy()
            self.cur, self.cur_detail = None, None
            self.reader, self.b = {}, {}
            self.rand_mode, self._rand_open = False, False
            self.desc_full, self.desc, self.sel = False, True, set()
            self.nav_build()
            self.build_ui()
            self.show(keep)
        finally:
            self._rebuilding = False

    # ----- plumbing -----
    def poll(self):
        t0, n = time.perf_counter(), 0
        while n < 6 and time.perf_counter() - t0 < 0.015:
            try:
                cb, res = Q.get_nowait()
            except queue.Empty:
                break
            try:
                cb(*res)
            except Exception as e:
                log_error("poll", e)
            n += 1
        self.after(12 if not Q.empty() else 40, self.poll)

    def watch(self):
        """Infinite scroll for Sources + live refresh for Downloads."""
        try:
            b = self.b
            if self.cur == "Sources" and b and b.get("has_more") and not b.get("loading") and not b.get("err"):
                top, bot = self.browse_scroll._parent_canvas.yview()
                if bot > 0.88:
                    self.load_more()
            self.sync_done_jobs()
            if self.cur == "Downloads":
                self.refresh_downloads()
        except Exception:
            pass
        self.after(350, self.watch)

    def close(self):
        if self.cur == "Reader":
            self.save_reader()
        save_db()                    # a pending save_db_soon must not be lost on exit
        self.destroy()

    def show(self, name):
        if self.cur == "Reader" and name != "Reader":
            self.mmb_stop()
            self.save_reader()
            self.rtok += 1
            self.rgen += 1
        if self.cur:
            self.views[self.cur].pack_forget()
        self.cur = name
        self.views[name].pack(fill="both", expand=True)
        self.nav_hl(name)
        if name in self.refresh:
            self.refresh[name]()

    def nav_build(self):
        """Sidebar entries; History can be hidden from Settings."""
        base = ["Library", "History", "Rating", "Sources", "Randomizer", "Downloads", "Settings"]
        self.nav_order = [n for n in base if n != "History" or S("show_history")]

    def set_history_visible(self, on):
        self.setv("show_history", bool(on))
        self.nav_build()
        self.paint_side()
        if not S("show_history") and self.cur == "History":
            self.show("Library")

    # ----- sidebar (canvas so the paper texture shows) -----
    def sched_paint_side(self):
        """Debounce Configure storms (fullscreen switch / window resize)."""
        if self._side_job:
            try:
                self.after_cancel(self._side_job)
            except Exception:
                pass
        self._side_job = self.after(60, self.paint_side)

    def paint_side(self):
        self._side_job = None
        c = self.side
        try:
            w, h = c.winfo_width() or 210, max(c.winfo_height() or 800, 320)
        except Exception:
            return
        c.delete("all")
        paper = S("paper")
        c.configure(bg=paper_avg(paper) or SIDE)
        tile = paper_tile(self, paper)
        if tile:
            ts = tile.width()
            for y in range(0, h + ts, ts):
                for x in range(0, w + ts, ts):
                    c.create_image(x, y, anchor="nw", image=tile)
        try:
            self._logo_img = getattr(self, "_logo42", None)
            if self._logo_img is None:
                self._logo_img = ImageTk.PhotoImage(make_icon(128).resize((42, 42), Image.Resampling.LANCZOS))
                self._logo42 = self._logo_img
            c.create_image(18, 26, anchor="nw", image=self._logo_img)
        except Exception:
            pass
        c.create_text(68, 47, anchor="w", text="Sablja\nReader", fill=SILVER_HI, justify="left",
                      font=("Segoe UI", 15, "bold"))
        self._nav_items = {}
        for i, n in enumerate(self.nav_order):
            y = 122 + i * 44
            tag = f"nav:{n}"
            rect = c.create_rectangle(12, y, w - 12, y + 38, fill="", outline="", tags=(tag,))
            txt = c.create_text(28, y + 19, anchor="w", text=n, fill=MUTED, font=("Segoe UI", 13), tags=(tag,))
            self._nav_items[n] = (rect, txt)
            self.nav[n] = True
            c.tag_bind(tag, "<Button-1>", lambda e, n=n: self.nav_click(n))
            c.tag_bind(tag, "<Enter>", lambda e, n=n: self.nav_hover(n, True))
            c.tag_bind(tag, "<Leave>", lambda e, n=n: self.nav_hover(n, False))
        self.nav_hl(self.cur or "Library")

    def nav_hover(self, n, on):
        self._hover = n if on else None
        try:
            self.side.configure(cursor="hand2" if on else "")
        except Exception:
            pass
        self.nav_hl(self.cur or "Library")

    def nav_hl(self, name):
        if name in ("Details", "Reader") and self.rand_mode:
            name = "Randomizer"
        for n, (rect, txt) in self._nav_items.items():
            on, hov = n == name, n == self._hover
            self.side.itemconfigure(rect, fill=(PANEL if (on or hov) else ""))
            self.side.itemconfigure(txt, fill=SILVER_HI if on else (TEXT if hov else MUTED))

    def title_label(self, parent, text):
        return ctk.CTkLabel(parent, text=text, font=("Segoe UI", 26, "bold"), text_color=SILVER_HI, anchor="w")

    def cols_for(self, extra=0, card=None, host=None, pad=12):
        """How many cards fit. Card sizes are logical px, widget widths are physical px,
        so the DPI scale factor has to be applied or the last column gets clipped."""
        card = card or CARD_CELL
        try:
            sc = float(ctk.ScalingTracker.get_widget_scaling(host or self))
        except Exception:
            sc = 1.0
        width = 0
        if host is not None:
            try:
                host.update_idletasks()
                canvas = getattr(host, "_parent_canvas", None)
                width = canvas.winfo_width() if canvas is not None else host.winfo_width()
            except Exception:
                width = 0
            if width > 1:
                width -= pad + 24            # scrollbar + breathing room
        if width <= 1:
            width = self.main.winfo_width() - extra * sc - 48
        return max(1, int(max(0, width) // (card * sc)))

    # ----- cards -----
    def grid_cards(self, parent, items, cols, cb, start=0, small=False, ctx=None, badge_fn=None,
                   alive=None, append=False):
        """Queue cards for `parent`; a single pump builds them a few at a time.

        append=False starts a fresh render (anything still queued is dropped). append=True adds to the
        running one. Cards are keyed by grid index, so a failed or cancelled batch can't leave a gap."""
        st = self._grid_state.get(parent)
        if st is None or not append:
            st = {"queue": [], "items": {}, "running": False, "retries": 0}
            self._grid_state[parent] = st
        st.update(cols=cols, cb=cb, small=small, ctx=ctx, badge_fn=badge_fn, alive=alive)
        for k, it in enumerate(items):
            st["items"][start + k] = it
            st["queue"].append(start + k)
        if not st["running"]:
            st["running"] = True
            self._grid_pump(parent, st)

    def _grid_pump(self, parent, st):
        try:
            live = bool(parent.winfo_exists()) and self._grid_state.get(parent) is st \
                and (st["alive"] is None or st["alive"]())
        except Exception:
            live = False
        if not live:
            st["running"] = False
            try:
                if not parent.winfo_exists():
                    self._grid_state.pop(parent, None)
            except Exception:
                self._grid_state.pop(parent, None)
            return
        for _ in range(6):
            if not st["queue"]:
                break
            k = st["queue"].pop(0)
            try:
                it = st["items"][k]
                badge = st["badge_fn"](it) if st["badge_fn"] else 0
                self.make_card(parent, it, k, st["cols"], st["cb"], st["small"], st["ctx"], badge)
            except Exception:
                traceback.print_exc()       # one bad card must not take the rest of the page with it
        if st["queue"]:
            self.after(10, lambda: self._grid_pump(parent, st))
            return
        # queue drained: make sure every index really has a card, re-queue any that are missing
        try:
            have = {getattr(w, "grid_idx", -1) for w in parent.winfo_children()}
        except Exception:
            have = set()
        miss = [k for k in sorted(st["items"]) if k not in have]
        if miss and st["retries"] < 3:
            st["retries"] += 1
            st["queue"].extend(miss)
            self.after(10, lambda: self._grid_pump(parent, st))
            return
        st["running"] = False

    # --- re-flow the grid when the window size changes ---
    def reflow(self, parent, cols):
        cards = [w for w in parent.winfo_children() if hasattr(w, "grid_idx")]
        for w in sorted(cards, key=lambda w: getattr(w, "grid_idx")):
            k = getattr(w, "grid_idx")
            w.grid(row=k // cols, column=k % cols)

    def sched_reflow(self, which):
        old = self._reflow_jobs.get(which)
        if old:
            try:
                self.after_cancel(old)
            except Exception:
                pass
        self._reflow_jobs[which] = self.after(180, lambda: self.do_reflow(which))

    def do_reflow(self, which):
        self._reflow_jobs[which] = None
        try:
            if which == "src" and self.cur == "Sources" and self.b and getattr(self, "holder", None):
                cols = self.cols_for(host=self.browse_scroll, pad=24, extra=220)
                if cols != self.b.get("cols"):
                    self.b["cols"] = cols
                    st = self._grid_state.get(self.holder)
                    if st:
                        st["cols"] = cols
                    self.reflow(self.holder, cols)
            elif which == "lib" and self.cur == "Library":
                cols = self.cols_for(host=self.lib_scroll)
                if cols != getattr(self, "lib_cols", cols):
                    self.lib_cols = cols
                    st = self._grid_state.get(self.lib_scroll)
                    if st:
                        st["cols"] = cols
                    self.reflow(self.lib_scroll, cols)
        except Exception:
            pass

    def make_card(self, parent, m, i, cols, cb, small=False, ctx=None, badge=0):
        iw, ih = (SMALL_W, SMALL_H) if small else (CARD_W, CARD_H)
        card = ctk.CTkFrame(parent, width=iw + 12, corner_radius=12, fg_color=CARD)
        setattr(card, "grid_idx", i)       # used by the gap check and by reflow()
        card.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="n")
        img = ctk.CTkLabel(card, text="", width=iw, height=ih, corner_radius=8, fg_color=PANEL)
        img.pack(padx=6, pady=(6, 2))
        if badge and badge > 0:
            ctk.CTkLabel(card, text=f"\U0001f195{badge}", corner_radius=9, fg_color=BTN_HI, text_color=SILVER_HI,
                         font=("Segoe UI", 10, "bold"), width=26, height=18, bg_color=PANEL
                         ).place(relx=1.0, rely=0.0, x=-10, y=8, anchor="ne")
        t = m["title"] if len(m["title"]) < 46 else m["title"][:43] + "…"
        ttl = ctk.CTkLabel(card, text=t, wraplength=iw - 6, height=34 if small else 44, font=("Segoe UI", 11 if small else 12), text_color=TEXT)
        show_genres = S("card_genres")
        genres = (m.get("genres") or cached_genres(m)) if show_genres else []
        reserve = show_genres and bool(genres)
        ttl.pack(padx=6, pady=(0, 2 if reserve else 6))
        clickable = [card, img, ttl]
        if reserve:
            gl = ctk.CTkLabel(card, text=genre_text(genres, 1 if small else 2), wraplength=iw - 8,
                              height=16 if small else 28, font=("Segoe UI", 8 if small else 9),
                              text_color=SILVER_DIM, justify="center")
            gl.pack(padx=6, pady=(0, 5))
            clickable.append(gl)
        for w in clickable:
            w.bind("<Button-1>", lambda e, m=m: cb(m))
            w.bind("<Enter>", lambda e, c=card: c.configure(fg_color=CARD_HI))
            w.bind("<Leave>", lambda e, c=card: c.configure(fg_color=CARD))
            if ctx:
                w.bind("<Button-3>", lambda e, m=m: ctx(e, m))
            w.configure(cursor="hand2")
        load_img(SOURCES.get(m["source"]), m["cover"], lambda im, l=img: set_img(l, im, (iw, ih)), size=(iw, ih))

    # ----- library -----
    def build_library(self):
        v = self.views["Library"]
        top = ctk.CTkFrame(v, fg_color="transparent")
        top.pack(fill="x", padx=28, pady=(24, 6))
        self.title_label(top, "Library").pack(side="left")
        self.cont_btn = btn(top, "", self.continue_reading, primary=True, height=38)
        self.cont_btn.pack(side="right")
        ctk.CTkLabel(v, text="Tip: right-click a cover for folders, bookmarks and more.", anchor="w",
                     text_color=SILVER_DIM, font=("Segoe UI", 11)).pack(fill="x", padx=30, pady=(0, 4))
        self.chip_row = ctk.CTkFrame(v, fg_color="transparent")
        self.chip_row.pack(fill="x", padx=28, pady=(0, 8))
        self.lib_scroll = ctk.CTkScrollableFrame(v, fg_color="transparent")
        self.lib_scroll.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self.lib_scroll._parent_canvas.bind("<Configure>", lambda e: self.sched_reflow("lib"), add="+")

    def popup(self, e, entries):
        mn = tk.Menu(self, tearoff=0, bg=PANEL, fg=TEXT, activebackground=BTN_HI, activeforeground=SILVER_HI, bd=0)
        for lab, fn in entries:
            if lab == "-":
                mn.add_separator()
            elif isinstance(fn, list):
                sub = tk.Menu(mn, tearoff=0, bg=PANEL, fg=TEXT, activebackground=BTN_HI, activeforeground=SILVER_HI, bd=0)
                for l2, f2 in fn:
                    sub.add_command(label=l2, command=f2)
                mn.add_cascade(label=lab, menu=sub)
            else:
                mn.add_command(label=lab, command=fn)
        try:
            mn.tk_popup(e.x_root, e.y_root)
        finally:
            mn.grab_release()

    def refresh_library(self):
        l = DB["last"]
        if l:
            p = DB["progress"].get(l["key"], {})
            self.cont_btn.configure(text=f'▶  Continue: {l["manga"]["title"][:26]} · {p.get("title", "")[:20]}', state="normal")
        else:
            self.cont_btn.configure(text="Nothing read yet", state="disabled")
        bms = DB["bookmarks"]
        if self.lib_folder not in ["All", "Unsorted", DL_VIEW_CHIP] + DB["folders"]:
            self.lib_folder = "All"
        dls = downloaded_manga()
        clear(self.chip_row)
        chips = [("All", f"All ({len(bms)})"), (DL_VIEW_CHIP, f"⬇ Downloaded ({len(dls)})")]
        if DB["folders"]:
            chips.append(("Unsorted", "Unsorted"))
        chips += [(f, f) for f in DB["folders"]]
        for key, label in chips:
            on = key == self.lib_folder
            c = btn(self.chip_row, label, lambda k=key: self.set_folder(k), primary=on, height=30, corner_radius=15, width=20)
            c.pack(side="left", padx=(0, 6))
            if key in DB["folders"]:
                c.bind("<Button-3>", lambda e, k=key: self.popup(e, [("Rename folder", lambda: self.rename_folder(k)),
                                                                      ("Delete folder", lambda: self.delete_folder(k))]))
        btn(self.chip_row, "+ Folder", lambda: self.new_folder(), height=30, corner_radius=15, width=20, fg_color="transparent",
            text_color=SILVER_DIM, hover_color=PANEL).pack(side="left")
        clear(self.lib_scroll)
        if self.lib_folder == "All":
            shown = list(bms)
        elif self.lib_folder == DL_VIEW_CHIP:
            shown = dls
        elif self.lib_folder == "Unsorted":
            shown = [b for b in bms if not b.get("folder")]
        else:
            shown = [b for b in bms if b.get("folder") == self.lib_folder]
        if not shown:
            msg = ("Nothing downloaded yet.\nUse the ⬇ Download button on a manga's page."
                   if self.lib_folder == DL_VIEW_CHIP else
                   "Nothing here yet.\nOpen a manga from Sources and press Bookmark.\n"
                   "Right-click a cover to move it into a folder.")
            ctk.CTkLabel(self.lib_scroll, text=msg, font=("Segoe UI", 14), text_color=MUTED).pack(pady=90)
        else:
            self.lib_cols = self.cols_for(host=self.lib_scroll)
            self.grid_cards(self.lib_scroll, shown, self.lib_cols, self.open_manga,
                            badge_fn=self.new_chapter_count,
                            ctx=self.dl_ctx if self.lib_folder == DL_VIEW_CHIP else self.lib_ctx)
            self.check_new_chapters()

    # ----- history -----
    def build_history(self):
        v = self.views["History"]
        top = ctk.CTkFrame(v, fg_color="transparent")
        top.pack(fill="x", padx=28, pady=(24, 6))
        self.title_label(top, "History").pack(side="left")
        btn(top, "Clear history", self.clear_history, width=120).pack(side="right")
        ctk.CTkLabel(v, text="Everything you have read, newest first — click a card to jump straight back in, "
                             "right-click to remove one. Hide this section in Settings.",
                     anchor="w", text_color=SILVER_DIM, font=("Segoe UI", 11)).pack(fill="x", padx=30, pady=(0, 6))
        self.hist_scroll = ctk.CTkScrollableFrame(v, fg_color="transparent")
        self.hist_scroll.pack(fill="both", expand=True, padx=18, pady=(0, 12))

    def hist_entries(self):
        """Newest-first history rows: (ts, key, manga, progress).

        Entries written before History existed have no stored manga info, so they resolve
        from bookmarks, the last-read record, or finally the URL slug — and they heal
        themselves the next time the chapter is opened."""
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
                title = re.sub(r"[-_]+", " ", tail).strip()[:44] or "Unknown title"
                m = {"source": src_id, "url": url, "title": title.title(), "cover": ""}
            out.append((p.get("ts") or 0, key, m, p))
        out.sort(key=lambda t: t[0], reverse=True)
        return out

    def refresh_history(self):
        clear(self.hist_scroll)
        rows = self.hist_entries()
        if not rows:
            ctk.CTkLabel(self.hist_scroll, text="Nothing read yet.\nOpen a chapter and it shows up here.",
                         font=("Segoe UI", 14), text_color=MUTED, justify="left").pack(pady=90)
            return
        cols = self.cols_for(card=264, host=self.hist_scroll, pad=24)
        for i, (ts, key, m, p) in enumerate(rows):
            self.make_hist_card(self.hist_scroll, key, m, p, i, cols)

    def make_hist_card(self, parent, key, m, p, i, cols):
        iw, ih = 84, 118
        card = ctk.CTkFrame(parent, width=iw + 168, height=ih + 14, corner_radius=12, fg_color=CARD)
        card.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="nw")
        card.grid_propagate(False)
        cov = ctk.CTkLabel(card, text="", width=iw, height=ih, corner_radius=8, fg_color=PANEL)
        cov.pack(side="left", padx=(8, 10), pady=7)
        right = ctk.CTkFrame(card, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=8)
        ctk.CTkLabel(right, text=m.get("title", "?"), font=("Segoe UI", 12, "bold"), text_color=TEXT,
                     wraplength=142, justify="left", anchor="w").pack(fill="x")
        ctk.CTkLabel(right, text=(p.get("title") or "Chapter")[:28], font=("Segoe UI", 11), text_color=SILVER,
                     wraplength=142, justify="left", anchor="w").pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(right, text=f'page {min(p.get("page", 0) + 1, 9999)} · {age_str(p.get("ts"))}',
                     font=("Segoe UI", 10), text_color=MUTED, anchor="w").pack(fill="x", pady=(2, 0))
        for w in (card, cov, right):
            w.bind("<Button-1>", lambda e, m=m: self.open_manga(m, resume=True))
            w.bind("<Enter>", lambda e, k=card: k.configure(fg_color=CARD_HI))
            w.bind("<Leave>", lambda e, k=card: k.configure(fg_color=CARD))
            w.bind("<Button-3>", lambda e, k=key: self.popup(e, [("Remove from history", lambda: self.hist_remove(k))]))
            w.configure(cursor="hand2")
        load_img(SOURCES.get(m.get("source")), m.get("cover"), lambda im, l=cov: set_img(l, im, (iw, ih)), size=(iw, ih))

    def hist_remove(self, key):
        DB["progress"].pop(key, None)
        if DB["last"] and DB["last"].get("key") == key:
            DB["last"] = None
        save_db()
        self.refresh_history()
        self.refresh_library()

    def clear_history(self):
        if not messagebox.askyesno("History", "Remove the reading history for every series?\n\n"
                                              "This forgets the chapter and page each series was left on "
                                              "(bookmarks, ratings and downloaded chapters are kept)."):
            return
        for key in [k for k, p in DB["progress"].items() if p.get("manga") and p.get("chapter")]:
            DB["progress"].pop(key, None)
        DB["last"] = None
        save_db()
        self.refresh_history()
        self.refresh_library()

    # ----- new-chapter check (bookmarks) -----
    def new_chapter_count(self, m):
        try:
            return self._fresh.get(pkey(m), {}).get("n", 0)
        except Exception:
            return 0

    def check_new_chapters(self, force=False):
        """Walk the bookmarked series in one background thread and compare each source's
        latest chapter with this profile's progress; results become 'new' badges in Library.
        Runs at most every 10 minutes."""
        now = time.time()
        thr = getattr(self, "_fresh_thr", None)
        if thr is not None and thr.is_alive():
            return
        if not force and now - getattr(self, "_fresh_last", 0) < 600:
            return
        self._fresh_last = now

        def run():
            out = {}
            for b in list(DB["bookmarks"]):
                src = SOURCES.get(b.get("source"))
                if not src or not b.get("url"):
                    continue
                try:
                    chs = (src.details(b["url"]) or {}).get("chapters") or []
                except Exception:
                    continue
                key = pkey(b)
                prog = DB["progress"].get(key, {})
                seen = set(prog.get("read") or [])
                cur = prog.get("chapter")
                i_last = -1
                for i, c2 in enumerate(chs):
                    if c2.get("url") == cur or c2.get("url") in seen:
                        i_last = i
                if i_last < 0:
                    continue          # bookmarked but never opened: no badge
                n = len(chs) - 1 - i_last
                if n > 0:
                    out[key] = {"n": n}
            Q.put((self.apply_fresh, (out, None)))

        self._fresh_thr = threading.Thread(target=run, daemon=True)
        self._fresh_thr.start()

    def apply_fresh(self, out, _=None):
        old = dict(self._fresh)
        self._fresh = out
        if self.cur == "Library" and old != out:
            self.refresh_library()

    # ----- rating -----
    def build_rating(self):
        v = self.views["Rating"]
        top = ctk.CTkFrame(v, fg_color="transparent")
        top.pack(fill="x", padx=28, pady=(24, 6))
        self.title_label(top, "Rating").pack(side="left")
        self.rate_info = ctk.CTkLabel(top, text="", text_color=MUTED, anchor="e")
        self.rate_info.pack(side="right")
        ctk.CTkLabel(v, text="Right-click a cover (Library, Sources or a manga page) and pick "
                             '"★ Rate / comment" to give it 1-10 and write a note.',
                     anchor="w", text_color=SILVER_DIM, font=("Segoe UI", 11)).pack(fill="x", padx=30, pady=(0, 8))
        self.rate_scroll = ctk.CTkScrollableFrame(v, fg_color="transparent")
        self.rate_scroll.pack(fill="both", expand=True, padx=18, pady=(0, 12))

    def refresh_rating(self):
        clear(self.rate_scroll)
        items = sorted(DB["ratings"].items(), key=lambda kv: (-(kv[1].get("score") or 0),
                                                             (kv[1].get("m") or {}).get("title", "").lower()))
        n = len(items)
        avg = (sum(v.get("score") or 0 for _, v in items) / n) if n else 0
        self.rate_info.configure(text=f"{n} rated · average {avg:.1f}/10" if n else "")
        if not items:
            ctk.CTkLabel(self.rate_scroll, text="Nothing rated yet.\nRight-click a manga and choose "
                                                '"★ Rate / comment".',
                         font=("Segoe UI", 14), text_color=MUTED, justify="left").pack(pady=90)
            return
        cols = self.cols_for(card=268, host=self.rate_scroll, pad=24)
        for i, (key, r) in enumerate(items):
            self.make_rate_card(self.rate_scroll, r, i, cols)

    def make_rate_card(self, parent, r, i, cols):
        m = r.get("m") or {"source": "", "url": "", "title": "?", "cover": ""}
        iw, ih = 104, 146
        card = ctk.CTkFrame(parent, width=iw + 152, corner_radius=12, fg_color=CARD)
        card.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="nw")
        cov = ctk.CTkLabel(card, text="", width=iw, height=ih, corner_radius=8, fg_color=PANEL)
        cov.pack(side="left", padx=(6, 8), pady=6)
        right = ctk.CTkFrame(card, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=6)
        ctk.CTkLabel(right, text=m.get("title", "?"), font=("Segoe UI", 12, "bold"), text_color=TEXT,
                     wraplength=138, justify="left", anchor="w").pack(fill="x")
        ctk.CTkLabel(right, text=f"{r.get('score') or 0}/10", font=("Segoe UI", 20, "bold"), text_color=SILVER_HI,
                     anchor="w").pack(fill="x", pady=(2, 0))
        note = (r.get("note") or "").strip()
        if note:
            ctk.CTkLabel(right, text=note[:150] + ("…" if len(note) > 150 else ""), font=("Segoe UI", 11),
                         text_color=MUTED, wraplength=138, justify="left", anchor="nw").pack(fill="x", pady=(4, 0))
        for w in (card, cov, right):
            w.bind("<Button-1>", lambda e, m=m: self.open_manga(m))
            w.bind("<Enter>", lambda e, c=card: c.configure(fg_color=CARD_HI))
            w.bind("<Leave>", lambda e, c=card: c.configure(fg_color=CARD))
            w.bind("<Button-3>", lambda e, m=m: self.popup(e, [("Open", lambda: self.open_manga(m)),
                                                               ("Change rating", lambda: self.rate_manga(m)),
                                                               ("Remove rating", lambda: self.remove_rating(m))]))
            w.configure(cursor="hand2")
        load_img(SOURCES.get(m.get("source")), m.get("cover", ""), lambda im, l=cov: set_img(l, im, (iw, ih)), size=(iw, ih))

    def rate_manga(self, m):
        cur = get_rating(m) or {}
        win = ctk.CTkToplevel(self)
        win.title("Rate / comment")
        # Windows DPI scaling (125-150%) shrinks the physical window, pushing the
        # Save button off-screen on smaller laptops - multiply the size by CTk's scale.
        try:
            sc = ctk.ScalingTracker.get_widget_scaling(win)
        except Exception:
            sc = 1.0
        win.geometry("%dx%d" % (int(600 * sc), int(500 * sc)))
        win.minsize(int(540 * sc), int(460 * sc))
        win.configure(fg_color=BG)
        # Pack the button row FIRST and pinned to the bottom: whatever the window
        # size or DPI scale, the buttons can no longer be pushed out of view.
        row2 = ctk.CTkFrame(win, fg_color="transparent")
        row2.pack(side="bottom", fill="x", padx=22, pady=(8, 14))
        ctk.CTkLabel(win, text=m.get("title", "?"), font=("Segoe UI", 16, "bold"), text_color=SILVER_HI,
                     wraplength=int(540 * sc), justify="left", anchor="w").pack(fill="x", padx=22, pady=(20, 0))
        ctk.CTkLabel(win, text="Your score (1-10)", text_color=MUTED, anchor="w").pack(fill="x", padx=22, pady=(14, 0))
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(4, 0))
        val = ctk.CTkLabel(row, text="", font=("Segoe UI", 22, "bold"), text_color=SILVER_HI, width=66, anchor="w")
        val.pack(side="left")
        var = tk.IntVar(value=int(cur.get("score") or 7))

        def upd(v):
            var.set(int(round(float(v))))
            val.configure(text=f"{var.get()}/10")

        sl = ctk.CTkSlider(row, from_=1, to=10, number_of_steps=9, width=330, progress_color=SILVER,
                           button_color=SILVER_HI, button_hover_color="white", fg_color=BTN, command=upd)
        sl.pack(side="left", padx=10)
        sl.set(var.get())
        val.configure(text=f"{var.get()}/10")
        ctk.CTkLabel(win, text="Comment (optional)", text_color=MUTED, anchor="w").pack(fill="x", padx=22, pady=(16, 0))
        box = ctk.CTkTextbox(win, fg_color=CARD, border_color=LINE, border_width=1, text_color=TEXT, wrap="word",
                             font=("Segoe UI", 12), corner_radius=8)
        box.pack(fill="both", expand=True, padx=22, pady=(4, 0))
        box.insert("1.0", cur.get("note") or "")

        def save():
            DB["ratings"][pkey(m)] = {"m": {k: m.get(k, "") for k in ("source", "url", "title", "cover")},
                                      "score": var.get(), "note": box.get("1.0", "end").strip(), "ts": int(time.time())}
            save_db()
            win.destroy()
            self.after_rating()

        btn(row2, "Save", save, primary=True, width=110).pack(side="right", padx=(8, 0))
        btn(row2, "Cancel", win.destroy, width=90).pack(side="right")
        if cur:
            btn(row2, "Remove rating", lambda: (self.remove_rating(m), win.destroy()), width=120).pack(side="left")
        win.transient(self)
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()

    def remove_rating(self, m):
        DB["ratings"].pop(pkey(m), None)
        save_db()
        self.after_rating()

    def after_rating(self):
        if self.cur == "Rating":
            self.refresh_rating()
        self.show_details_rating()

    def show_details_rating(self):
        m = (self.cur_detail or (None, None))[0]
        if not m or not hasattr(self, "d_rate"):
            return
        r = get_rating(m) or {}
        self.d_rate.configure(text=f"★ {r['score']}/10" if r.get("score") else "★ Rate")

    def dl_ctx(self, e, m):
        """Right-click menu for the Downloaded view (works even when the manga isn't bookmarked)."""
        entries = [("Open", lambda: self.open_manga(m)), ("Rate / comment…", lambda: self.rate_manga(m))]
        if m.get("url"):
            entries += [("☆ Bookmark", lambda: self.add_bm(m)),
                        ("Move to folder", [("None (Unsorted)", lambda: self.move_to(m, ""))] +
                         [(f, lambda f=f: self.move_to(m, f)) for f in DB["folders"]] +
                         [("New folder…", lambda: self.new_folder(m))])]
        entries += [("-", None),
                    ("Open download folder", lambda: self.open_dir(dl_folder_for(m))),
                    ("Delete downloaded chapters", lambda: self.delete_manga_dl(m))]
        self.popup(e, entries)

    def delete_manga_dl(self, m):
        chs = local_chapters_any(m)
        if not chs:
            return
        if not messagebox.askyesno("Delete downloads",
                                   f"Delete all {len(chs)} downloaded chapter file(s) for\n{m.get('title', '?')}?"):
            return
        paths = set(chs.values())
        for p in paths:
            try:
                os.remove(p)
            except Exception:
                pass
        DB["downloads"][:] = [r for r in DB["downloads"] if r.get("path") not in paths]
        save_db()
        self.refresh_library()

    def set_folder(self, k):
        self.lib_folder = k
        self.refresh_library()

    def lib_ctx(self, e, m):
        moves = [("None (Unsorted)", lambda: self.move_to(m, ""))] + [(f, lambda f=f: self.move_to(m, f)) for f in DB["folders"]]
        moves.append(("New folder…", lambda: self.new_folder(m)))
        self.popup(e, [("Open", lambda: self.open_manga(m)), ("Rate / comment…", lambda: self.rate_manga(m)),
                       ("Move to folder", moves), ("-", None),
                       ("Remove from library", lambda: self.remove_bm(m))])

    def card_ctx(self, e, m):
        """Right-click menu for manga cards in Sources."""
        bm = self.find_bm(m)
        moves = [("None (Unsorted)", lambda: self.move_to(m, ""))]
        moves += [(("· " if bm and bm.get("folder") == f else "") + f, lambda f=f: self.move_to(m, f)) for f in DB["folders"]]
        moves.append(("New folder…", lambda: self.new_folder(m)))
        if bm:
            entries = [("Open", lambda: self.open_manga(m)), ("Rate / comment…", lambda: self.rate_manga(m)),
                       ("Move to folder", moves), ("-", None),
                       ("★ Remove bookmark", lambda: self.remove_bm(m))]
        else:
            entries = [("Open", lambda: self.open_manga(m)), ("Rate / comment…", lambda: self.rate_manga(m)),
                       ("☆ Bookmark", lambda: self.add_bm(m)),
                       ("☆ Bookmark in folder", moves)]
        self.popup(e, entries)

    def find_bm(self, m):
        return next((b for b in DB["bookmarks"] if b["source"] == m["source"] and b["url"] == m["url"]), None)

    def add_bm(self, m, folder=""):
        if self.find_bm(m):
            return
        DB["bookmarks"].append({**{k: m[k] for k in ("source", "url", "title", "cover")}, "folder": folder})
        save_db()
        if self.cur == "Library":
            self.refresh_library()

    def move_to(self, m, folder):
        b = self.find_bm(m)
        if b is None:  # not bookmarked yet: filing it implies adding it
            self.add_bm(m, folder)
            return
        b["folder"] = folder
        save_db()
        if self.cur == "Library":
            self.refresh_library()

    def remove_bm(self, m):
        b = self.find_bm(m)
        if b is not None:
            DB["bookmarks"].remove(b)
            save_db()
            if self.cur == "Library":
                self.refresh_library()

    def new_folder(self, m=None):
        name = ctk.CTkInputDialog(text="Folder name:", title="New folder").get_input()
        name = (name or "").strip()
        if not name or name in ("All", "Unsorted"):
            return
        if name not in DB["folders"]:
            DB["folders"].append(name)
        if m:
            self.move_to(m, name)
        save_db()
        self.refresh_library()

    def rename_folder(self, old):
        name = (ctk.CTkInputDialog(text=f'Rename "{old}" to:', title="Rename folder").get_input() or "").strip()
        if not name or name in DB["folders"] or name in ("All", "Unsorted"):
            return
        DB["folders"][DB["folders"].index(old)] = name
        for b in DB["bookmarks"]:
            if b.get("folder") == old:
                b["folder"] = name
        if self.lib_folder == old:
            self.lib_folder = name
        save_db()
        self.refresh_library()

    def delete_folder(self, name):
        DB["folders"].remove(name)
        for b in DB["bookmarks"]:
            if b.get("folder") == name:
                b["folder"] = ""
        save_db()
        self.refresh_library()

    def continue_reading(self):
        if DB["last"]:
            self.open_manga(DB["last"]["manga"], resume=True)

    # ----- sources -----
    def build_sources(self):
        v = self.views["Sources"]
        v.grid_columnconfigure(1, weight=1)
        v.grid_rowconfigure(0, weight=1)
        self.src_list = ctk.CTkScrollableFrame(v, width=170, fg_color=PANEL, corner_radius=12)
        self.src_list.grid(row=0, column=0, sticky="ns", padx=(18, 10), pady=18)
        right = ctk.CTkFrame(v, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", pady=18, padx=(0, 18))
        self.src_title = ctk.CTkLabel(right, text="Pick a source", font=("Segoe UI", 22, "bold"), text_color=SILVER_HI, anchor="w")
        self.src_title.pack(fill="x", padx=4)
        bar = ctk.CTkFrame(right, fg_color="transparent")
        bar.pack(fill="x", pady=(8, 2))
        self.q_entry = entry(bar, placeholder_text="Search in this source…", width=260)
        self.q_entry.pack(side="left")
        self.q_entry.bind("<Return>", lambda e: self.browse("search"))
        btn(bar, "Search", lambda: self.browse("search"), primary=True, width=80).pack(side="left", padx=8)
        btn(bar, "Shuffle", self.shuffle_cards, width=86).pack(side="left", padx=(0, 8))
        self.filter_row = ctk.CTkFrame(bar, fg_color="transparent")
        self.filter_row.pack(side="left", padx=(10, 0))
        self.bstatus = ctk.CTkLabel(right, text="", text_color=MUTED, anchor="w")
        self.bstatus.pack(fill="x", padx=6)
        ctk.CTkLabel(right, text="Tip: right-click a cover to bookmark or file it.", anchor="w",
                     text_color=SILVER_DIM, font=("Segoe UI", 11)).pack(fill="x", padx=6)
        self.browse_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.browse_scroll.pack(fill="both", expand=True)
        self.browse_scroll._parent_canvas.bind("<Configure>", lambda e: self.sched_reflow("src"), add="+")

    def refresh_sources(self):
        clear(self.src_list)
        shown = [s for s in SOURCES.values() if (S("nsfw") or not s.nsfw) and not source_hidden(s.id)]
        if not shown:
            ctk.CTkLabel(self.src_list, text="No sources.\nCheck sources.json\nor unhide them in Settings", text_color=MUTED,
                         justify="left").pack(pady=20)
        for s in shown:
            b = self.b and self.b["src"] is s
            ctk.CTkButton(self.src_list, text=s.name + ("  18+" if s.nsfw else ""), anchor="w", height=36, corner_radius=8,
                          fg_color=BTN if b else "transparent", text_color=SILVER_HI if b else TEXT, hover_color=BTN_HI,
                          font=FONT, command=lambda s=s: self.select_source(s)).pack(fill="x", pady=1)

    def select_source(self, src, query=""):
        self.btok += 1
        self.b = {"src": src, "tok": 0, "loading": False, "has_more": False, "pool": {}, "shuffle_tok": 0}
        self.src_title.configure(text=src.name + ("   (untested)" if src.d.get("untested") else ""))
        self.q_entry.delete(0, "end")
        if query:
            self.q_entry.insert(0, query)
        clear(self.filter_row)
        self.kind_btns, self.genre_map, self.genre_menu = {}, {}, None
        names = {"popular": "Popular", "latest": "Latest"}
        if len(src.kinds()) > 1:
            for k in src.kinds():
                bt = btn(self.filter_row, names[k], lambda k=k: self.set_kind(k), width=76, height=34)
                bt.pack(side="left", padx=(0, 6))
                self.kind_btns[k] = bt
        self.refresh_sources()
        tok = self.btok
        bg(src.genres, lambda r, e, tok=tok: self.genres_ready(tok, r, e))
        self.browse("search" if query else "popular")

    def genres_ready(self, tok, r, e):
        if e or not r or tok != self.btok or not self.b:
            return
        self.genre_map = dict(r)
        self.genre_menu = menu(self.filter_row, ["All genres"] + [g[0] for g in r], self.on_genre, width=150)
        self.genre_menu.pack(side="left", padx=(6, 0))

    def set_kind(self, k):
        if self.genre_menu:
            self.genre_menu.set("All genres")
        self.q_entry.delete(0, "end")
        self.browse(k)

    def on_genre(self, label):
        g = self.genre_map.get(label, "")
        k = self.b.get("kind", "popular")
        self.q_entry.delete(0, "end")
        self.browse("popular" if k == "search" else k, g)

    def browse(self, kind, genre=""):
        b = self.b
        if not b:
            return
        src = b["src"]
        q = self.q_entry.get().strip() if kind == "search" else ""
        if kind == "search":
            if not src.can_search():
                self.bstatus.configure(text="This source has no search.")
                return
            if not q:
                return
        try:
            self.browse_scroll.update_idletasks()   # real inner width before choosing columns
        except Exception:
            pass
        b.update(kind=kind, query=q, genre=genre, page=1, n=0, tok=b["tok"] + 1, loading=False, has_more=True, err=None,
                 seen=set(), pool={}, cols=self.cols_for(host=self.browse_scroll, pad=24, extra=220), shuffle_tok=b.get("shuffle_tok", 0) + 1,
                 render=b.get("render", 0) + 1)
        for k, bt in self.kind_btns.items():
            on = k == kind
            bt.configure(fg_color=SILVER if on else BTN, text_color=INK if on else TEXT, hover_color=SILVER_HI if on else BTN_HI)
        self.bstatus.configure(text="")
        clear(self.browse_scroll)
        self.reset_browse_scroll()
        self.holder = ctk.CTkFrame(self.browse_scroll, fg_color="transparent")
        self.holder.pack(anchor="w")
        self.footer = ctk.CTkLabel(self.browse_scroll, text="", text_color=MUTED)
        self.footer.pack(pady=16)
        self.load_more()

    def reset_browse_scroll(self):
        """Put the source listing back at the very top (it kept the old yview between sources)."""
        try:
            c = self.browse_scroll._parent_canvas
            c.update_idletasks()
            c.yview_moveto(0.0)
        except Exception:
            pass

    def load_more(self):
        b = self.b
        if b["loading"] or not b["has_more"]:
            return
        b["loading"], tok = True, b["tok"]
        self.footer.configure(text="Loading…")
        bg(lambda: b["src"].listing(b["kind"], b["page"], b["query"], b["genre"]), lambda r, e: self.more_done(b, tok, r, e))

    def more_done(self, b, tok, r, e):
        if b is not self.b or tok != b["tok"]:     # belongs to another source/search: ignore
            return
        b["loading"] = False
        if e:
            b["err"] = True
            self.footer.configure(text=f"Error: {str(e)[:110]}   (click to retry)", cursor="hand2")
            self.footer.bind("<Button-1>", lambda ev: (b.update(err=None), self.load_more()))
            return
        new = [x for x in r if x["url"] not in b["seen"]]
        b["seen"].update(x["url"] for x in new)
        if not new:
            b["has_more"] = False
            self.footer.configure(text="End of results" if b["n"] else "No results")
            return
        b.setdefault("pool", {}).update({x["url"]: x for x in new})
        first = not b["n"]
        rgen = b.get("render", 0)
        self.grid_cards(self.holder, new, b["cols"], self.open_manga, start=b["n"], ctx=self.card_ctx,
                        alive=lambda: self.b is b and b.get("render") == rgen, append=not first)
        b["n"] += len(new)
        b["page"] += 1
        self.footer.configure(text="")
        if first:
            self.after_idle(self.reset_browse_scroll)

    # ----- shuffle -----
    def shuffle_cards(self):
        """Show a fresh random selection from the current source.

        Cards already loaded are shuffled, plus one random listing page is pulled in when the
        source supports pagination - so every press brings a different mix instead of the same
        page in a new order.
        """
        b = self.b
        if not b:
            return
        src, kind = b["src"], b.get("kind", "popular")
        q, genre = b.get("query", ""), b.get("genre", "")
        b["tok"] = b.get("tok", 0) + 1      # cancel any page fetch still in flight
        b["loading"] = False
        b["render"] = b.get("render", 0) + 1  # stop cards from an older grid run being appended
        b["shuffle_tok"] = b.get("shuffle_tok", 0) + 1
        tok = b["shuffle_tok"]
        pool = list((b.get("pool") or {}).values())
        self.bstatus.configure(text="Shuffling…")
        try:
            self.footer.configure(text="")
        except Exception:
            pass

        def work():
            out = list(pool)
            if kind != "search":
                for _ in range(3):
                    try:
                        got = src.listing(kind, random.randint(2, 12), q, genre)
                    except Exception:
                        got = []
                    if got:
                        out.extend(got)
                        break
            random.shuffle(out)
            return out

        bg(work, lambda r, e: self.shuffle_done(tok, r, e))

    def shuffle_done(self, tok, r, e):
        b = self.b
        if not b or tok != b.get("shuffle_tok"):
            return
        if e:
            self.bstatus.configure(text=f"Shuffle failed: {str(e)[:90]}")
            return
        uniq = {}
        for x in r or []:
            uniq.setdefault(x["url"], x)
        items = list(uniq.values())
        if not items:
            self.bstatus.configure(text="Nothing to shuffle — load some cards first.")
            return
        random.shuffle(items)
        b["pool"] = uniq
        b["seen"].update(uniq)
        b["cols"] = self.cols_for(host=self.browse_scroll, pad=24, extra=220)
        b["render"] = b.get("render", 0) + 1
        rgen = b["render"]
        clear(self.holder)
        shown = items[:96]
        self.grid_cards(self.holder, shown, b["cols"], self.open_manga, start=0, ctx=self.card_ctx,
                        alive=lambda: self.b is b and b.get("render") == rgen)
        b["n"] = len(shown)
        self.footer.configure(text="")
        self.bstatus.configure(text=f"Shuffled {len(shown)} cards — press Shuffle again for a new mix")
        self.after_idle(self.reset_browse_scroll)

    # ----- global search -----
    def build_search(self):
        v = self.views["Search"]
        top = ctk.CTkFrame(v, fg_color="transparent")
        top.pack(fill="x", padx=28, pady=(24, 10))
        self.title_label(top, "Search").pack(side="left", padx=(0, 22))
        self.sq = entry(top, placeholder_text="Search every source…", width=340)
        self.sq.pack(side="left")
        self.sq.bind("<Return>", lambda e: self.run_search())
        btn(top, "Search", self.run_search, primary=True, width=90).pack(side="left", padx=8)
        self.search_map = {}
        self.search_pick = menu(top, ["All sources"], self.on_search_src, width=170)
        self.search_pick.pack(side="left", padx=4)
        self.sres = ctk.CTkScrollableFrame(v, fg_color="transparent")
        self.sres.pack(fill="both", expand=True, padx=18, pady=(0, 12))

    def searchable(self):
        return [s for s in SOURCES.values()
                if s.can_search() and (S("nsfw") or not s.nsfw) and not source_hidden(s.id)]

    def refresh_search(self):
        vals = ["All sources"] + sorted(s.name for s in self.searchable())
        self.search_map = {s.name: s.id for s in self.searchable()}
        try:
            self.search_pick.configure(values=vals)
            if self.search_pick.get() not in vals:
                self.search_pick.set("All sources")
        except Exception:
            pass

    def on_search_src(self, _value=""):
        if self.sq.get().strip():
            self.run_search()

    def run_search(self):
        q = self.sq.get().strip()
        if not q:
            return
        clear(self.sres)
        self.stok += 1
        tok = self.stok
        pick = self.search_pick.get() if hasattr(self, "search_pick") else "All sources"
        want = self.search_map.get(pick)
        self._seen_titles = set()
        srcs = [s for s in self.searchable() if not want or s.id == want]
        if not srcs:
            ctk.CTkLabel(self.sres, text="No searchable source selected — check Settings.", text_color=MUTED,
                         font=("Segoe UI", 14)).pack(pady=60)
            return
        for src in srcs:
            sec = ctk.CTkFrame(self.sres, corner_radius=12, fg_color=PANEL)
            sec.pack(fill="x", padx=6, pady=6)
            hd = ctk.CTkLabel(sec, text=f"{src.name}  ·  searching…", font=("Segoe UI", 14, "bold"), text_color=SILVER, anchor="w")
            hd.pack(fill="x", padx=14, pady=(10, 4))
            bg(lambda src=src: src.listing("search", 1, q), lambda r, e, src=src, sec=sec, hd=hd: self.search_done(tok, src, sec, hd, r, e, q))

    def filter_results(self, q, items):
        """Stricter search: every query word must appear in the title, and drop cross-source duplicates."""
        toks = [t for t in re.findall(r"[a-z0-9]+", q.lower()) if len(t) > 1] or [q.lower()]
        out = []
        for x in items:
            t = x["title"].lower()
            if not all(tok in t for tok in toks):
                continue
            key = re.sub(r"[^a-z0-9]+", "", t)
            if key in self._seen_titles:
                continue
            self._seen_titles.add(key)
            out.append(x)
        return out

    def search_done(self, tok, src, sec, hd, r, e, q):
        try:
            if tok != self.stok or not sec.winfo_exists():
                return
            if e:
                hd.configure(text=f"{src.name}  ·  unavailable ({str(e)[:60]})", text_color=MUTED)
                return
            r = self.filter_results(q, r or [])
            if not r:
                hd.configure(text=f"{src.name}  ·  no matching results", text_color=MUTED)
                return
            hd.configure(text=f"{src.name}  ·  {len(r)} results")
            grid = ctk.CTkFrame(sec, fg_color="transparent")
            grid.pack(fill="x", padx=8, pady=(0, 6))
            cols = self.cols_for(card=SMALL_CELL, host=self.sres, pad=48)
            self.grid_cards(grid, r[:cols * 2 if len(r) > cols else cols], cols, self.open_manga, small=True,
                            ctx=self.card_ctx)
            if len(r) > cols:
                btn(sec, "See all in " + src.name + " →", lambda: (self.show("Sources"), self.select_source(src, q)),
                    height=30, width=20, fg_color="transparent", text_color=SILVER, hover_color=BTN).pack(anchor="w", padx=12, pady=(0, 10))
        except Exception:
            pass

    # ----- downloads view -----
    def build_downloads(self):
        v = self.views["Downloads"]
        top = ctk.CTkFrame(v, fg_color="transparent")
        top.pack(fill="x", padx=28, pady=(24, 10))
        self.title_label(top, "Downloads").pack(side="left")
        btn(top, "Open folder", lambda: self.open_dir(S("dl_dir")), width=100).pack(side="right")
        btn(top, "Clear finished", self.clear_jobs, width=110).pack(side="right", padx=8)
        btn(top, "Delete file", self.delete_dl, width=96).pack(side="right", padx=(0, 8))
        btn(top, "Cancel all", self.cancel_jobs, width=90).pack(side="right")
        ctk.CTkLabel(v, text="One .cbz per chapter, kept on disk and remembered between sessions. "
                             "The reader reuses saved chapters instead of downloading them again — even offline. "
                             "Double-click a row to open its folder.",
                     anchor="w", justify="left", wraplength=980, text_color=SILVER_DIM,
                     font=("Segoe UI", 11)).pack(fill="x", padx=28, pady=(0, 6))
        box = ctk.CTkFrame(v, fg_color=CARD, corner_radius=12)
        box.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        self.dtree_dl = ttk.Treeview(box, columns=("m", "c", "s"), show="headings", style="S.Treeview")
        for c, t, w in (("m", "Manga", 320), ("c", "Chapter", 320), ("s", "Status", 200)):
            self.dtree_dl.heading(c, text=t, anchor="w")
            self.dtree_dl.column(c, width=w, anchor="w")
        sb = ctk.CTkScrollbar(box, command=self.dtree_dl.yview)
        self.dtree_dl.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 4), pady=6)
        self.dtree_dl.pack(fill="both", expand=True, padx=6, pady=6)
        self.dtree_dl.bind("<Double-1>", self.dl_open_row)

    def refresh_downloads(self):
        t = self.dtree_dl
        live = set()
        for j in JOBS:
            st = "saved" if j["state"] == "done" else j["state"]
            if j["total"] and j["state"] in ("downloading", "done"):
                st += f"  {j['done']}/{j['total']}"
            iid = f"job:{j['id']}"
            live.add(j["path"])
            vals = (j["m"]["title"], j["ch"]["title"], st)
            if t.exists(iid):
                if t.item(iid, "values") != tuple(map(str, vals)):
                    t.item(iid, values=vals)
            else:
                t.insert("", "end", iid=iid, values=vals)
        for n, r in enumerate(DB["downloads"]):
            if r.get("path") in live:
                continue
            st = "saved" if os.path.exists(r["path"]) else "saved (file missing)"
            iid = f"dl:{n}"
            vals = (r.get("m", {}).get("title", "?"), r.get("ch", {}).get("title", "?"), st)
            if t.exists(iid):
                if t.item(iid, "values") != tuple(map(str, vals)):
                    t.item(iid, values=vals)
            else:
                t.insert("", "end", iid=iid, values=vals)

    def dl_row(self, iid):
        """The download record behind a tree row (live job or saved history)."""
        if not iid:
            return None
        if iid.startswith("dl:"):
            n = int(iid[3:])
            return DB["downloads"][n] if 0 <= n < len(DB["downloads"]) else None
        jid = iid[4:]
        j = next((x for x in JOBS if str(x["id"]) == jid), None)
        if j and j.get("state") == "done":
            return {"path": j["path"], "m": j["m"], "ch": j["ch"]}
        return None

    def dl_open_row(self, e):
        r = self.dl_row(self.dtree_dl.identify_row(e.y))
        if r:
            p = r.get("path", "")
            self.open_dir(os.path.dirname(p) if os.path.isfile(p) else S("dl_dir"))

    def delete_dl(self):
        rows = [r for r in (self.dl_row(i) for i in self.dtree_dl.selection()) if r]
        if not rows:
            return
        names = "\n".join(f'· {r.get("m", {}).get("title", "?")} — {r.get("ch", {}).get("title", "?")}' for r in rows)
        if not messagebox.askyesno("Delete downloads", f"Delete these chapter files from disk?\n\n{names}"):
            return
        for r in rows:
            p = r.get("path")
            if p:
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
                DB["downloads"][:] = [x for x in DB["downloads"] if x.get("path") != p]
        save_db()
        self.dtree_dl.delete(*self.dtree_dl.get_children())
        self.refresh_downloads()

    def cancel_jobs(self):
        for j in JOBS:
            if j["state"] in ("queued", "getting pages", "downloading"):
                j["state"] = "cancelled"

    def clear_jobs(self):
        for j in [j for j in JOBS if j["state"] in ("done", "cancelled") or j["state"].startswith("error")]:
            JOBS.remove(j)
            iid = f"job:{j['id']}"
            if self.dtree_dl.exists(iid):
                self.dtree_dl.delete(iid)

    def sync_done_jobs(self):
        """Fold finished jobs into the persistent download index (offline library)."""
        for j in JOBS:
            if j["state"] != "done" or j.get("recorded"):
                continue
            j["recorded"] = True
            if os.path.exists(j["path"]) and not any(r.get("path") == j["path"] for r in DB["downloads"]):
                DB["downloads"].append({"key": pkey(j["m"]), "m": j["m"], "i": j.get("i", 0), "ch": j["ch"],
                                        "path": j["path"], "ts": int(time.time())})
                save_db()

    def open_dir(self, p):
        os.makedirs(p, exist_ok=True)
        try:
            os.startfile(p)
        except Exception:
            pass

    # ----- settings -----
    def build_settings(self):
        v = self.views["Settings"]
        self.title_label(v, "Settings").pack(anchor="w", padx=28, pady=(24, 12))
        scroll = ctk.CTkScrollableFrame(v, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        def card(title):
            f = ctk.CTkFrame(scroll, fg_color=PANEL, corner_radius=12)
            f.pack(fill="x", padx=28, pady=6)
            ctk.CTkLabel(f, text=title, font=("Segoe UI", 14, "bold"), text_color=SILVER, anchor="w").pack(fill="x", padx=16, pady=(12, 6))
            return f

        def row(f):
            r = ctk.CTkFrame(f, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=5)
            return r

        f = card("Reading")
        r = row(f)
        ctk.CTkLabel(r, text="Default reading mode", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.set_mode = menu(r, MODES, lambda v: self.setv("mode", v), width=220)
        self.set_mode.set(S("mode"))
        self.set_mode.pack(side="left")
        r = row(f)
        ctk.CTkLabel(r, text="Background", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.set_paper = menu(r, PAPERS, self.apply_paper, width=200)
        self.set_paper.set(S("paper"))
        self.set_paper.pack(side="left")
        ctk.CTkLabel(r, text="paper texture behind the pages and the menu", text_color=MUTED,
                     font=("Segoe UI", 11)).pack(side="left", padx=10)
        r = row(f)
        ctk.CTkLabel(r, text="Reader background", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.set_reader_paper = menu(r, PAPERS, self.apply_reader_paper, width=200)
        self.set_reader_paper.set(S("reader_paper"))
        self.set_reader_paper.pack(side="left")
        ctk.CTkLabel(r, text="starts on Graphite matte; independent of the app theme", text_color=MUTED,
                     font=("Segoe UI", 11)).pack(side="left", padx=10)
        r = row(f)
        self.sw_guides = ctk.CTkSwitch(r, text="In paged modes: black page borders, page numbers and the double-page gutter",
                                       progress_color=SILVER, button_color=SILVER_HI, text_color=TEXT,
                                       command=lambda: self.setv("paged_guides", bool(self.sw_guides.get())))
        self.sw_guides.pack(side="left")
        if S("paged_guides"):
            self.sw_guides.select()
        ctk.CTkFrame(f, height=8, fg_color="transparent").pack()

        f = card("Sidebar")
        r = row(f)
        self.sw_hist = ctk.CTkSwitch(r, text="Show the History section (everything you have read)",
                                     progress_color=SILVER, button_color=SILVER_HI, text_color=TEXT,
                                     command=lambda: self.set_history_visible(bool(self.sw_hist.get())))
        self.sw_hist.pack(side="left")
        if S("show_history"):
            self.sw_hist.select()
        ctk.CTkFrame(f, height=8, fg_color="transparent").pack()

        f = card("Window")
        r = row(f)
        self.sw_fs = ctk.CTkSwitch(r, text="Open in borderless fullscreen on start (F11 toggles it any time)",
                                   progress_color=SILVER, button_color=SILVER_HI, text_color=TEXT,
                                   command=lambda: self.setv("start_fullscreen", bool(self.sw_fs.get())))
        self.sw_fs.pack(side="left")
        if S("start_fullscreen"):
            self.sw_fs.select()
        ctk.CTkFrame(f, height=8, fg_color="transparent").pack()

        f = card("Updates")
        r = row(f)
        ctk.CTkLabel(r, text=f"Installed version: {APP_VERSION}", text_color=TEXT, width=190,
                     anchor="w").pack(side="left")
        btn(r, "Check for updates", lambda: self.check_updates(True), width=150).pack(side="left")
        self.upd_status = ctk.CTkLabel(r, text="", text_color=MUTED, anchor="w")
        self.upd_status.pack(side="left", padx=10)
        r = row(f)
        self.sw_upd = ctk.CTkSwitch(r, text="Check for updates automatically on start (once a day)",
                                    progress_color=SILVER, button_color=SILVER_HI, text_color=TEXT,
                                    command=lambda: self.setv("update_auto", bool(self.sw_upd.get())))
        self.sw_upd.pack(side="left")
        if S("update_auto"):
            self.sw_upd.select()
        btn(r, "Release page", lambda: self.open_release({}), width=120).pack(side="left", padx=(18, 0))
        ctk.CTkLabel(f, text="Updates come from this project's GitHub releases. The installer replaces only the "
                             "app files - your library, progress, cache and downloads stay in the data folder, "
                             "and db.json is backed up before every update.",
                     text_color=MUTED, font=("Segoe UI", 11), anchor="w", wraplength=900,
                     justify="left").pack(fill="x", padx=16, pady=(4, 12))

        f = card("Report a bug / request a feature")
        r = row(f)
        ctk.CTkLabel(r, text="Type", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.br_type = menu(r, ["Bug", "Source problem", "Feature request"], lambda v: None, width=180)
        self.br_type.pack(side="left")
        r = row(f)
        ctk.CTkLabel(r, text="Short summary", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.br_title = entry(r, placeholder_text="e.g. Reader freezes when I open chapter 12", width=560)
        self.br_title.pack(side="left", fill="x", expand=True)
        r = row(f)
        ctk.CTkLabel(r, text="What happened?", text_color=TEXT, width=190, anchor="w").pack(side="left", anchor="n")
        self.br_body = ctk.CTkTextbox(r, height=110, fg_color=CARD, border_color=LINE, border_width=1,
                                      text_color=TEXT, font=FONT, corner_radius=8, wrap="word")
        self.br_body.pack(side="left", fill="x", expand=True)
        r = row(f)
        btn(r, "Open GitHub issue", self.report_open, primary=True, width=150).pack(side="left", padx=(190, 8))
        btn(r, "Copy diagnostics", self.report_copy, width=140).pack(side="left")
        self.br_status = ctk.CTkLabel(r, text="", text_color=MUTED, anchor="w")
        self.br_status.pack(side="left", padx=10)
        ctk.CTkLabel(f, text="Opens a new issue on GitHub in your browser with the text and diagnostics filled in — "
                             "you review it and press Submit. Nothing is sent automatically.",
                     text_color=MUTED, font=("Segoe UI", 11), anchor="w", wraplength=900,
                     justify="left").pack(fill="x", padx=16, pady=(4, 12))

        f = card("Downloads (saved as one .cbz per chapter)")
        r = row(f)
        ctk.CTkLabel(r, text="Folder", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.dl_dir_lbl = ctk.CTkLabel(r, text=S("dl_dir"), text_color=MUTED, anchor="w")
        self.dl_dir_lbl.pack(side="left", padx=(0, 10))
        btn(r, "Change…", self.pick_dl_dir, width=80).pack(side="left")
        r = row(f)
        ctk.CTkLabel(r, text="Download order", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.set_order = menu(r, ["Oldest first", "Newest first"], lambda v: self.setv("dl_order", v), width=160)
        self.set_order.set(S("dl_order"))
        self.set_order.pack(side="left")
        r = row(f)
        ctk.CTkLabel(r, text="Delay between images", text_color=TEXT, width=190, anchor="w").pack(side="left")
        self.delay_lbl = ctk.CTkLabel(r, text=f"{S('dl_delay'):.1f} s", text_color=SILVER, width=50)
        sl = ctk.CTkSlider(r, from_=cast(int, 0.3), to=5, number_of_steps=47, width=220, progress_color=SILVER, button_color=SILVER_HI,
                           button_hover_color="white", fg_color=BTN, command=self.set_delay)
        sl.set(S("dl_delay"))
        sl.pack(side="left")
        self.delay_lbl.pack(side="left", padx=8)
        ctk.CTkLabel(f, text="Higher delay = safer against bans. Pages already viewed in the reader are reused without any request.",
                     text_color=MUTED, font=("Segoe UI", 11), anchor="w").pack(fill="x", padx=16, pady=(0, 12))

        f = card("Sources")
        r = row(f)
        btn(r, "Reload sources.json", self.reload_sources, width=150).pack(side="left")
        btn(r, "Open app folder", lambda: self.open_dir(BASE), width=130).pack(side="left", padx=8)
        btn(r, "Clear image cache", self.clear_cache, width=140).pack(side="left")
        r = row(f)
        sw = ctk.CTkSwitch(r, text="Show 18+ sources", progress_color=SILVER, button_color=SILVER_HI, text_color=TEXT,
                           command=lambda: (self.setv("nsfw", bool(sw.get())), self.refresh_sources()))
        sw.pack(side="left")
        if S("nsfw"):
            sw.select()
        r = row(f)
        swg = ctk.CTkSwitch(r, text="Show genres on cards (uses listing genres and genres already cached from details pages)",
                            progress_color=SILVER, button_color=SILVER_HI, text_color=TEXT,
                            command=lambda: (self.setv("card_genres", bool(swg.get())),
                                             self.refresh_card_genres_view()))
        swg.pack(side="left")
        if S("card_genres"):
            swg.select()
        self.repo_status = ctk.CTkLabel(f, text="", text_color=MUTED, anchor="w")
        self.repo_status.pack(fill="x", padx=16)
        ctk.CTkLabel(f, text=f"Config file in use: {SRC_FILE}", text_color=SILVER_DIM, font=("Segoe UI", 11),
                     anchor="w", wraplength=900, justify="left").pack(fill="x", padx=16, pady=(2, 0))
        self.repo_list = ctk.CTkLabel(f, text="", anchor="w", justify="left", text_color=TEXT)
        self.repo_list.pack(fill="x", padx=16, pady=(4, 0))
        ctk.CTkLabel(f, text="Sources shown in the Sources tab - untick any you don't want:", text_color=MUTED,
                     font=("Segoe UI", 11), anchor="w").pack(fill="x", padx=16, pady=(6, 2))
        self.src_grid = ctk.CTkFrame(f, fg_color="transparent")
        self.src_grid.pack(fill="x", padx=16, pady=(0, 14))
        self.build_src_toggles()

    def setv(self, k, v):
        DB["set"][k] = v
        save_db()

    def refresh_card_genres_view(self):
        """Apply the genre switch to the cards that are already on screen."""
        try:
            if self.cur == "Library":
                self.refresh_library()
            elif self.cur == "Sources" and self.b:
                self.browse(self.b.get("kind", "popular"), self.b.get("genre", ""))
        except Exception:
            pass

    def set_delay(self, v):
        v = round(float(v), 1)
        self.delay_lbl.configure(text=f"{v:.1f} s")
        DB["set"]["dl_delay"] = v
        save_db()

    def pick_dl_dir(self):
        d = filedialog.askdirectory(initialdir=S("dl_dir"))
        if d:
            self.setv("dl_dir", d)
            self.dl_dir_lbl.configure(text=d)

    def refresh_settings(self):
        self.update_repo_list()
        hid = hidden_ids()
        for sid, sw in getattr(self, "src_switches", {}).items():
            sw.select() if sid not in hid else sw.deselect()

    def update_repo_list(self):
        if not SOURCES:
            self.repo_list.configure(text="No sources installed.")
            return
        hid = hidden_ids()
        self.repo_list.configure(text="Installed: " + ", ".join(
            s.name + (" (hidden)" if s.id in hid else "") for s in SOURCES.values()))

    def build_src_toggles(self):
        """One on/off switch per source - hidden ones vanish from Sources and Search."""
        clear(self.src_grid)
        self.src_switches = {}
        hid, cols = hidden_ids(), 2
        for i, s in enumerate(SOURCES.values()):
            cell = ctk.CTkFrame(self.src_grid, fg_color="transparent")
            cell.grid(row=i // cols, column=i % cols, sticky="w", padx=(0, 34), pady=2)
            sw = ctk.CTkSwitch(cell, text=s.name + ("  18+" if s.nsfw else ""), progress_color=SILVER,
                               button_color=SILVER_HI, text_color=TEXT, width=220,
                               command=lambda s=s: self.toggle_source(s))
            sw.pack(side="left")
            if s.id not in hid:
                sw.select()
            self.src_switches[s.id] = sw

    def toggle_source(self, s):
        hid = hidden_ids()
        (hid.discard if self.src_switches[s.id].get() else hid.add)(s.id)
        DB["set"]["hidden"] = sorted(hid)
        save_db()
        self.refresh_sources()
        self.refresh_search()
        self.update_repo_list()

    def apply_paper(self, name):
        """Switch the background theme: adopt the palette, then rebuild the window.

        Recolouring the live widget tree in place (the old retint pass) kept leaving pieces
        of the window behind on the previous palette - scroll areas and menus worst of all.
        Recreating the widgets is instant and cannot half-apply.
        """
        if name == S("paper"):
            return
        self.setv("paper", name)
        theme_pick(name)
        self.after(10, self.rebuild_ui)     # let the option-menu callback return before we destroy it

    def apply_reader_paper(self, name):
        self.setv("reader_paper", name)
        if self.cur == "Reader":
            self.build_body()

    def reload_sources(self):
        rebuild_sources()
        self.repo_status.configure(text=f"Loaded {len(SOURCES)} sources from {SRC_FILE}")
        self.build_src_toggles()
        self.refresh_settings()
        self.refresh_sources()
        self.refresh_search()

    def clear_cache(self):
        with THUMB_LOCK:
            THUMB_CACHE.clear()
        shutil.rmtree(CACHE, ignore_errors=True)
        os.makedirs(CACHE, exist_ok=True)
        self.repo_status.configure(text="Image cache cleared")

    # ----- updates -----
    def _upd_status(self, text):
        """Write to the Settings update label if it is still on screen (theme rebuilds replace it)."""
        try:
            w = getattr(self, "upd_status", None)
            if w is not None and w.winfo_exists():
                w.configure(text=text)
        except Exception:
            pass

    def check_updates(self, manual=False):
        """Ask GitHub for the latest release. Manual checks always run; automatic ones once a day."""
        if self._upd_busy:
            return
        if not manual:
            if not S("update_auto"):
                return
            last = float(load_update_state().get("checked") or 0)
            if time.time() - last < 86400:
                return
        self._upd_busy = True
        if manual:
            self._upd_status("Checking GitHub…")
        bg(fetch_latest_release, lambda info, err: self.on_update_info(manual, info, err))

    def on_update_info(self, manual, info, err):
        self._upd_busy = False
        state = load_update_state()
        state["checked"] = time.time()
        save_update_state(state)
        if err or not info:
            if manual:
                self._upd_status(f"Update check failed: {str(err or 'no response')[:110]}")
            return
        tag = str(info.get("tag") or "").strip()
        if not tag:
            if manual:
                self._upd_status("GitHub returned no release tag.")
            return
        if version_key(tag) <= version_key(APP_VERSION):
            if manual:
                self._upd_status(f"You are up to date (version {APP_VERSION}).")
            return
        if not manual and load_update_state().get("skip") == tag:
            return
        self.show_update(info)

    def open_release(self, info=None):
        page = str((info or {}).get("page") or f"{REPO_URL}/releases/latest")
        try:
            webbrowser.open(page)
            self._upd_status("Opened the release page in your browser.")
        except Exception as e:
            self._upd_status(f"Could not open a browser: {str(e)[:80]}")

    def show_update(self, info):
        tag = str(info.get("tag") or "").strip()
        old = self._upd_win
        if old is not None:
            try:
                if old.winfo_exists():
                    old.destroy()
            except Exception:
                pass
        win = tk.Toplevel(self)
        self._upd_win = win
        win.title("Sablja Reader update")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self)
        panel = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=0)
        panel.pack(fill="both", expand=True)
        ctk.CTkLabel(panel, text=f"Version {tag.lstrip('vV')} is available",
                     font=("Segoe UI", 16, "bold"), text_color=SILVER_HI).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(panel, text=f"You have {APP_VERSION}.", text_color=MUTED,
                     font=("Segoe UI", 11)).pack(anchor="w", padx=20)
        notes = (info.get("notes") or "").strip()
        if notes:
            tb = ctk.CTkTextbox(panel, height=150, fg_color=CARD, border_color=LINE, border_width=1,
                                text_color=TEXT, font=("Segoe UI", 11), corner_radius=8, wrap="word")
            tb.pack(fill="both", expand=True, padx=20, pady=10)
            tb.insert("1.0", notes[:3000])
            tb.configure(state="disabled")
        else:
            ctk.CTkLabel(panel, text="See the release page for what changed.",
                         text_color=MUTED).pack(anchor="w", padx=20, pady=10)
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 8))
        frozen = bool(getattr(sys, "frozen", False))
        installed = running_installed()
        can_install = installed and bool((info.get("asset") or {}).get("browser_download_url"))
        if can_install:
            btn(row, "Download & install", lambda: self.update_install(info), primary=True,
                width=160).pack(side="left")
            btn(row, "Release page", lambda: self.open_release(info), width=120).pack(side="left", padx=8)
        else:
            btn(row, "Open release page", lambda: self.open_release(info), primary=True,
                width=160).pack(side="left")
        btn(row, "Later", lambda: self.update_later(info, win), width=90).pack(side="right")
        if can_install:
            note = (f"Your library, progress, cache and downloads stay in {DATA}. "
                    "db.json is backed up to data\\backups before the installer runs.")
        elif not frozen:
            note = ("This is a source checkout, so the updater only opens the release page. "
                    f"Your data folder is {DATA}.")
        elif not installed:
            note = ("This is a portable copy, so it will not overwrite an installed copy. "
                    f"Download the installer from the release page; this data folder stays at {DATA}.")
        else:
            note = "The release has no installer asset; open the release page to download it."
        ctk.CTkLabel(panel, text=note, text_color=MUTED, font=("Segoe UI", 11),
                     wraplength=520, justify="left").pack(fill="x", padx=20, pady=(0, 14))
        win.protocol("WM_DELETE_WINDOW", lambda: self.update_later(info, win))
        win.update_idletasks()
        w, h = 560, max(320, win.winfo_reqheight())
        x = self.winfo_rootx() + max(0, (self.winfo_width() - w) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - h) // 3)
        win.geometry(f"{w}x{h}+{x}+{y}")
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass
        win.grab_set()
        win.lift()
        win.after(60, win.focus_force)
        self._upd_status(f"Version {tag.lstrip('vV')} is available.")

    def update_later(self, info, win):
        tag = str(info.get("tag") or "").strip()
        if tag:
            state = load_update_state()
            state["skip"] = tag
            save_update_state(state)
        try:
            win.destroy()
        except Exception:
            pass
        if self._upd_win is win:
            self._upd_win = None
        self._upd_status("Update skipped. You can check again any time.")

    def update_install(self, info):
        tag = str(info.get("tag") or "").strip().lstrip("vV")
        ok = messagebox.askyesno(
            "Install update",
            f"Download version {tag} and run the installer now?\n\n"
            f"Your library and progress stay in:\n{DATA}\n\n"
            "A backup of db.json is saved to data\\backups first.\n"
            "Sablja Reader will close while the installer runs.")
        if not ok:
            return
        win = self._upd_win
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
            self._upd_win = None
        self._upd_status("Downloading the update…")
        bg(lambda: download_release_asset(info), lambda path, err: self.on_update_downloaded(path, err))

    def on_update_downloaded(self, path, err):
        if err or not path:
            self._upd_status(f"Update download failed: {str(err or 'no file')[:110]}")
            messagebox.showerror("Update failed", f"Could not download the update.\n\n{err or 'no file'}")
            return
        backup = backup_db()
        self._upd_status("Starting the installer…")
        try:
            os.startfile(path)
        except Exception:
            try:
                subprocess.Popen([path])
            except Exception as e:
                self._upd_status(f"Could not start the installer: {str(e)[:100]}")
                messagebox.showerror("Update failed", f"Could not start the installer.\n\n{e}\n\nFile: {path}")
                return
        if os.path.isfile(str(backup)):
            self._upd_status(f"Installer started. Library backup: {backup}")
        else:
            self._upd_status("Installer started; the app will close in a moment.")
        self.after(900, self.close)

    # ----- bug report -----
    def report_diag(self):
        """Technical context the maintainer needs, without any reading history or personal data."""
        active = self.b.get("src") if self.b else None
        src = getattr(active, "name", "none")
        return "\n".join([
            f"App version: {APP_VERSION}",
            f"OS: {platform.platform()}",
            f"Python: {platform.python_version()}" + ("  (frozen exe)" if getattr(sys, "frozen", False) else ""),
            f"Window: {self.winfo_width()}x{self.winfo_height()}  borderless={self._borderless}",
            f"Reading mode: {S('mode')}   Background: {S('paper')}   Reader background: {S('reader_paper')}",
            f"Sources loaded: {len(SOURCES)}   Visible in Sources: "
            f"{len([s for s in SOURCES.values() if (S('nsfw') or not s.nsfw) and not source_hidden(s.id)])}",
            f"Selected source: {src}",
            f"Data folder: {DATA}",
            f"curl_cffi available: {bool(cffi)}",
        ])

    def report_open(self):
        kind = self.br_type.get() if hasattr(self, "br_type") else "Bug"
        title = self.br_title.get().strip() if hasattr(self, "br_title") else ""
        what = self.br_body.get("1.0", "end-1c").strip() if hasattr(self, "br_body") else ""
        if not title and not what:
            self.br_status.configure(text="Add a short summary or describe what happened first.")
            return
        body = f"{what or '(no details given)'}\n\n---\n### Diagnostics\n```\n{self.report_diag()}\n```\n"
        url = f"{REPO_URL}/issues/new?" + urlencode({"title": f"[{kind}] {title or 'Report'}", "body": body})
        try:
            webbrowser.open(url)
            self.br_status.configure(text="Opened GitHub in your browser — review and press Submit.")
        except Exception as e:
            self.br_status.configure(text=f"Could not open a browser: {str(e)[:80]}")

    def report_copy(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.report_diag())
            self.update_idletasks()
            self.br_status.configure(text="Diagnostics copied to the clipboard.")
        except Exception as e:
            self.br_status.configure(text=f"Copy failed: {str(e)[:80]}")

    # ----- details (built once, filled in place: no flicker) -----
    # ----- randomizer -----
    def nav_click(self, n):
        if n == "Randomizer":
            self.rand_roll()
            return
        self.rand_mode = False
        self.rdm_tok += 1
        self.rand_sync()
        self.show(n)

    def go_back(self):
        self.rand_mode = False
        self.rdm_tok += 1
        self.rand_sync()
        self.show(self.back or "Library")

    def rand_sync(self):
        """Previous / Next buttons only exist on the details page while browsing random picks."""
        try:
            self.d_prev.pack_forget()
            self.d_next.pack_forget()
            if self.rand_mode:
                self.d_prev.pack(side="left", padx=(8, 0))
                self.d_next.pack(side="left", padx=8)
                self.d_prev.configure(state="normal" if self.rand_i > 0 else "disabled")
        except Exception:
            pass

    def rand_roll(self):
        self.rand_mode = True
        self.rdm_tok += 1
        tok = self.rdm_tok
        if self.cur not in ("Details", "Reader"):
            self.back = self.cur
        self.dtok += 1
        self.cur_detail = None
        self.show("Details")
        self.rand_sync()
        self.d_title.configure(text="\U0001f3b2 Rolling the dice\u2026")
        self.d_src.configure(text="")
        self.d_desc.configure(text="Picking a random title from your enabled sources\u2026")
        for w in (self.d_more, self.d_count, self.d_status):
            w.configure(text="")
        self.d_cont.configure(text="\u25b6 Start reading", state="disabled")
        self.d_bm.configure(state="disabled", text="\u2606 Bookmark")
        self.dtree.delete(*self.dtree.get_children())
        self.d_cover.configure(image=None, text="")
        bg(lambda: random_pick(self.rand_seen), lambda r, e: self.rand_done(tok, r, e))

    def rand_done(self, tok, r, e):
        if tok != self.rdm_tok or not self.rand_mode:
            return
        if e or not r:
            self.d_title.configure(text="\U0001f3b2 No luck")
            self.d_desc.configure(text="Couldn't fetch a random title (" + (str(e)[:120] if e else "no sources available")
                                  + "). Press Next random to try again.")
            return
        self.rand_seen.add(r["url"])
        del self.rand_hist[self.rand_i + 1:]
        self.rand_hist.append(r)
        self.rand_i = len(self.rand_hist) - 1
        self.rand_open(r)

    def rand_open(self, m):
        self._rand_open = True
        try:
            self.open_manga(m)
        finally:
            self._rand_open = False
        self.rand_sync()

    def rand_prev(self):
        if self.rand_mode and self.rand_i > 0:
            self.rdm_tok += 1
            self.rand_i -= 1
            self.rand_open(self.rand_hist[self.rand_i])

    def build_details(self):
        v = self.views["Details"]
        bar = ctk.CTkFrame(v, fg_color="transparent")
        bar.pack(fill="x", padx=22, pady=(18, 8))
        btn(bar, "← Back", self.go_back, width=80).pack(side="left")
        self.d_prev = btn(bar, "◀ Previous", self.rand_prev, width=110)
        self.d_next = btn(bar, "🎲 Next random", lambda: self.rand_roll(), width=150, primary=True)
        top = ctk.CTkFrame(v, fg_color="transparent")
        top.pack(fill="x", padx=22)
        self.d_cover = ctk.CTkLabel(top, text="", width=190, height=270, corner_radius=12, fg_color=PANEL)
        self.d_cover.pack(side="left", anchor="n")
        right = ctk.CTkFrame(top, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=20)
        self.d_title = ctk.CTkLabel(right, text="", font=("Segoe UI", 25, "bold"), text_color=SILVER_HI, wraplength=760, justify="left", anchor="w")
        self.d_title.pack(fill="x")
        self.d_src = ctk.CTkLabel(right, text="", text_color=MUTED, anchor="w")
        self.d_src.pack(fill="x", pady=(0, 2))
        self.d_genres = ctk.CTkLabel(right, text="", text_color=SILVER_DIM, font=("Segoe UI", 11),
                                     anchor="w", wraplength=760, justify="left")
        self.d_genres.pack(fill="x", pady=(0, 8))
        row = ctk.CTkFrame(right, fg_color="transparent")
        row.pack(fill="x", pady=4)
        self.d_bm = btn(row, "☆ Bookmark", self.toggle_bm, width=130)
        self.d_bm.pack(side="left")
        self.d_cont = btn(row, "▶ Start reading", None, primary=True, width=190)
        self.d_cont.pack(side="left", padx=8)
        self.d_dl = btn(row, "⬇ Download (0)", self.enqueue_downloads, width=140, state="disabled")
        self.d_dl.pack(side="left")
        self.d_rate = btn(row, "★ Rate", lambda: self.cur_detail and self.rate_manga(self.cur_detail[0]), width=110)
        self.d_rate.pack(side="left", padx=8)
        self.d_desc = ctk.CTkLabel(right, text="", wraplength=760, justify="left", anchor="nw", text_color=MUTED, font=("Segoe UI", 12))
        self.d_desc.pack(fill="x", pady=(12, 0))
        self.d_more = ctk.CTkLabel(right, text="", text_color=SILVER, cursor="hand2", anchor="w")
        self.d_more.pack(fill="x")
        self.d_more.bind("<Button-1>", lambda e: self.toggle_desc())
        hdr = ctk.CTkFrame(v, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(14, 4))
        self.d_count = ctk.CTkLabel(hdr, text="", font=("Segoe UI", 15, "bold"), text_color=SILVER_HI)
        self.d_count.pack(side="left")
        self.d_prog = ctk.CTkProgressBar(hdr, width=170, height=8, progress_color=SILVER, fg_color=BTN)
        self.d_prog.set(0)
        self.d_prog.pack(side="left", padx=12)
        self.d_status = ctk.CTkLabel(hdr, text="", text_color=MUTED)
        self.d_status.pack(side="left", padx=14)
        self.d_sort = btn(hdr, "Newest first ↓", self.toggle_sort, width=130, height=30)
        self.d_sort.pack(side="right")
        btn(hdr, "Select none", self.sel_none, width=90, height=30).pack(side="right", padx=6)
        btn(hdr, "Select all", self.sel_all, width=90, height=30).pack(side="right")
        box = ctk.CTkFrame(v, fg_color=CARD, corner_radius=12)
        box.pack(fill="both", expand=True, padx=22, pady=(0, 16))
        t = self.dtree = ttk.Treeview(box, columns=("chk", "title", "st"), show="", style="S.Treeview", selectmode="browse")
        t.column("chk", width=46, anchor="center", stretch=False)
        t.column("title", anchor="w")
        t.column("st", width=150, anchor="e", stretch=False)
        t.tag_configure("read", foreground=MUTED)
        sb = ctk.CTkScrollbar(box, command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 4), pady=6)
        t.pack(fill="both", expand=True, padx=6, pady=6)
        t.bind("<Button-1>", self.tree_click)
        t.bind("<Double-1>", self.tree_open)
        t.bind("<Return>", self.tree_open)

    def open_manga(self, m, resume=False):
        if not self._rand_open:
            self.rand_mode = False
            self.rdm_tok += 1
            self.rand_sync()
        if self.cur not in ("Details", "Reader"):
            self.back = self.cur
        self.dtok += 1
        tok = self.dtok
        self.cur_detail, self.sel, self.desc_full = None, set(), False
        src = SOURCES.get(m["source"])
        self.show("Details")
        self.d_title.configure(text=m["title"])
        self.d_rate.configure(text="★ Rate")
        self.d_src.configure(text=src.name if src else m["source"])
        self.d_genres.configure(text=genre_text(m.get("genres") or cached_genres(m), 8))
        self.d_desc.configure(text="Loading…")
        self.d_more.configure(text="")
        self.d_count.configure(text="")
        self.d_status.configure(text="")
        self.d_cont.configure(text="▶ Start reading", state="disabled")
        self.d_bm.configure(state="disabled", text="☆ Bookmark")
        self.dtree.delete(*self.dtree.get_children())
        self.d_cover.configure(image=None, text="")
        self.update_dl_btn()
        if not src:
            self.d_src.configure(text=m.get("name") or m.get("source") or "Local files")
            info = self.offline_info(m)
            if info:
                self.render_details(tok, m, info, None, resume)
            else:
                self.d_desc.configure(text="This source is no longer installed, and no downloaded chapters were found on disk.")
            return
        load_img(src, m["cover"], lambda im: self.dtok == tok and set_img(self.d_cover, im, (190, 270)), size=(190, 270))
        bg(lambda: src.details(m["url"]), lambda r, e: self.render_details(tok, m, r, e, resume))

    def render_details(self, tok, m, info, err, resume=False):
        if tok != self.dtok:
            return
        if err:
            info = self.offline_info(m)
            if not info:
                self.d_desc.configure(text=f"Failed to load: {str(err)[:160]}")
                return
        chs = info["chapters"]
        prog = DB["progress"].setdefault(pkey(m), {"read": []})
        urls = [c["url"] for c in chs]
        m = dict(m, title=info.get("title") or m["title"], cover=info.get("cover") or m["cover"])
        self.cur_detail = (m, info)
        self.d_title.configure(text=m["title"])
        gs = info.get("genres") or m.get("genres") or cached_genres(m)
        if gs:
            remember_genres(m, gs)
        self.d_genres.configure(text=genre_text(gs, 8))
        self.show_details_rating()
        if m.get("url"):
            self.d_bm.configure(state="normal", text=self.bm_text(m))
        else:
            self.d_bm.configure(state="disabled", text="☆ Bookmark")
        self.full_desc = info.get("description") or "No description available."
        self.render_desc()
        if resume and prog.get("chapter") in urls:
            self.continue_or_restart(m, chs, urls.index(prog["chapter"]))
            return
        if chs:
            has = prog.get("chapter") in urls
            idx = urls.index(prog["chapter"]) if has else 0
            self.d_cont.configure(state="normal", text=f'▶ Continue: {prog["title"][:24]}' if has else "▶ Start reading",
                                  command=lambda: self.continue_or_restart(m, chs, idx))
        else:
            self.d_cont.configure(state="disabled", text="▶ Start reading")
        self.refresh_tree()

    def offline_info(self, m):
        """Rebuild a chapter list from saved .cbz files so an unreachable source still shows what you have."""
        local = local_chapters_any(m)
        if not local:
            return None
        recs = {r.get("i"): r for r in dl_records(m)}
        chs = []
        for i in sorted(local):
            c = (recs.get(i) or {}).get("ch") or {}
            title = c.get("title") or re.sub(r"^\d+\s*-\s*", "", os.path.splitext(os.path.basename(local[i]))[0])
            chs.append({"title": title, "url": c.get("url") or f"local:{local[i]}", "i": i})
        return {"title": m.get("title", ""), "cover": m.get("cover", ""), "chapters": chs,
                "description": "(Source unreachable — showing your downloaded chapters only.)"}

    def continue_or_restart(self, m, chs, idx):
        """Re-entering a manga: ask whether to resume the saved page or start this chapter over."""
        p = DB["progress"].get(pkey(m), {})
        page = p.get("page", 0) if p.get("chapter") == chs[idx]["url"] else 0
        restart = self.ask_resume(chs[idx]["title"], page) if page else False
        self.open_chapter(m, chs, idx, restart=restart)

    def ask_resume(self, chapter, page):
        """Modal: True = start this chapter from the beginning, False = resume the saved page."""
        win = ctk.CTkToplevel(self)
        win.title("Continue reading")
        win.geometry("460x210")
        win.resizable(False, False)
        win.configure(fg_color=BG)
        ans = {"restart": False}

        def pick(restart):
            ans["restart"] = restart
            win.destroy()

        ctk.CTkLabel(win, text="Continue where you left off?", font=("Segoe UI", 17, "bold"),
                     text_color=SILVER_HI).pack(pady=(26, 4))
        ctk.CTkLabel(win, text=f"{chapter} — saved at page {page + 1}", text_color=MUTED).pack()
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(pady=22)
        btn(row, f"▶ Resume page {page + 1}", lambda: pick(False), primary=True, width=180).pack(side="left", padx=6)
        btn(row, "⟲ Start chapter over", lambda: pick(True), width=180).pack(side="left", padx=6)
        win.protocol("WM_DELETE_WINDOW", lambda: pick(False))
        win.bind("<Escape>", lambda e: pick(False))
        win.transient(self)
        win.update_idletasks()
        try:
            x = self.winfo_rootx() + (self.winfo_width() - 460) // 2
            y = self.winfo_rooty() + (self.winfo_height() - 210) // 3
            win.geometry(f"+{max(0, x)}+{max(0, y)}")
            win.grab_set()
        except Exception:
            pass
        self.wait_window(win)
        return ans["restart"]

    def update_progress(self):
        if not self.cur_detail:
            return
        m, info = self.cur_detail
        chs = info["chapters"]
        n = len(chs)
        read = set(DB["progress"].get(pkey(m), {}).get("read", []))
        done = sum(1 for c in chs if c["url"] in read)
        saved = len(local_chapters_any(m))
        pct = int(round(done / n * 100)) if n else 0
        self.d_count.configure(text=f"{n} chapters · {done} read ({pct}% complete)" + (f" · {saved} saved" if saved else ""))
        try:
            self.d_prog.set(done / n if n else 0)
        except Exception:
            pass

    def render_desc(self):
        d = self.full_desc
        if len(d) > 420 and not self.desc_full:
            self.d_desc.configure(text=d[:420].rsplit(" ", 1)[0] + " …")
            self.d_more.configure(text="Show more")
        else:
            self.d_desc.configure(text=d)
            self.d_more.configure(text="Show less" if len(d) > 420 else "")

    def toggle_desc(self):
        self.desc_full = not self.desc_full
        self.render_desc()

    def refresh_tree(self):
        if not self.cur_detail:
            return
        m, info = self.cur_detail
        chs = info["chapters"]
        local = local_chapters(m)
        read = set(DB["progress"].get(pkey(m), {}).get("read", []))
        t = self.dtree
        t.delete(*t.get_children())
        for i in (range(len(chs) - 1, -1, -1) if self.desc else range(len(chs))):
            c = chs[i]
            st = (["Read"] if c["url"] in read else []) + (["Saved"] if c.get("i", i) in local else [])
            t.insert("", "end", iid=str(i), values=("☑" if i in self.sel else "☐", c["title"], " · ".join(st)),
                     tags=("read",) if c["url"] in read else ())
        self.update_progress()

    def toggle_sort(self):
        self.desc = not self.desc
        self.d_sort.configure(text="Newest first ↓" if self.desc else "Oldest first ↑")
        self.refresh_tree()

    def tree_click(self, e):
        t = self.dtree
        if t.identify_region(e.x, e.y) == "cell" and t.identify_column(e.x) == "#1":
            iid = t.identify_row(e.y)
            if iid:
                i = int(iid)
                self.sel.symmetric_difference_update({i})
                t.set(iid, "chk", "☑" if i in self.sel else "☐")
                self.update_dl_btn()
            return "break"

    def tree_open(self, e):
        if not self.cur_detail:
            return
        iid = self.dtree.identify_row(e.y) if e.type == "4" else (self.dtree.selection() or [""])[0]
        if iid and not (e.type == "4" and self.dtree.identify_column(e.x) == "#1"):
            m, info = self.cur_detail
            self.open_chapter(m, info["chapters"], int(iid))

    def sel_all(self):
        if self.cur_detail:
            self.sel = set(range(len(self.cur_detail[1]["chapters"])))
            self.refresh_tree()
            self.update_dl_btn()

    def sel_none(self):
        self.sel = set()
        self.refresh_tree()
        self.update_dl_btn()

    def update_dl_btn(self):
        self.d_dl.configure(text=f"⬇ Download ({len(self.sel)})", state="normal" if self.sel and self.cur_detail else "disabled")

    def enqueue_downloads(self):
        if not self.cur_detail or not self.sel:
            return
        m, info = self.cur_detail
        chs, n = info["chapters"], 0
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
        self.refresh_tree()
        self.update_dl_btn()
        self.d_status.configure(text=f"Queued {n} chapter(s) — see Downloads tab")

    def bm_text(self, m):
        return "★ Bookmarked" if self.find_bm(m) else "☆ Bookmark"

    def toggle_bm(self):
        if self.cur_detail:
            self.toggle_bm_m(self.cur_detail[0])

    def toggle_bm_m(self, m):
        if not m:
            return
        ex = self.find_bm(m)
        if ex:
            DB["bookmarks"].remove(ex)
        else:
            DB["bookmarks"].append({**{k: m[k] for k in ("source", "url", "title", "cover")}, "folder": ""})
        save_db()
        self.d_bm.configure(text=self.bm_text(m))
        try:
            self.r_bm.configure(text=self.bm_text(m))
        except Exception:
            pass

    # ----- reader -----
    def build_reader(self):
        v = self.views["Reader"]
        bar = ctk.CTkFrame(v, height=54, corner_radius=0, fg_color=SIDE)
        bar.pack(fill="x")
        btn(bar, "← Back", self.reader_back, width=76).pack(side="left", padx=(12, 8), pady=10)
        self.r_title = ctk.CTkLabel(bar, text="", font=("Segoe UI", 13, "bold"), text_color=TEXT)
        self.r_title.pack(side="left", padx=8)
        self.r_bm = btn(bar, "☆ Bookmark", lambda: self.toggle_bm_m(self.reader["m"] if self.reader else None), width=118)
        self.r_bm.pack(side="left", padx=(2, 8))
        self.r_page = ctk.CTkLabel(bar, text="", text_color=MUTED)
        self.r_page.pack(side="left", padx=8)
        self.r_next = btn(bar, "Next ▶", lambda: self.chapter_step(1), primary=True, width=76)
        self.r_next.pack(side="right", padx=(6, 12))
        self.r_prev = btn(bar, "◀ Prev", lambda: self.chapter_step(-1), width=76)
        self.r_prev.pack(side="right")
        self.r_chs = btn(bar, "▼  Chapters", self.chs_menu_open, width=150)
        self.r_chs.pack(side="right", padx=8)
        btn(bar, "+", lambda: self.zoom_by(1), width=34).pack(side="right", padx=(6, 12))
        self.r_zoom = ctk.CTkLabel(bar, text="100%", text_color=SILVER, width=48)
        self.r_zoom.pack(side="right")
        btn(bar, "−", lambda: self.zoom_by(-1), width=34).pack(side="right", padx=(12, 0))
        self.r_mode = menu(bar, MODES, self.change_mode, width=190)
        self.r_mode.pack(side="right", padx=8)
        self.rbody = ctk.CTkFrame(v, fg_color=READER_BG, corner_radius=0)
        self.rbody.pack(fill="both", expand=True)

    def is_web(self):
        return self.reader["mode"] == MODES[0]

    def is_rtl(self):
        return "right→left" in self.reader["mode"]

    def is_double(self):
        return self.reader["mode"].startswith("Double")

    def save_reader(self, mark=False):
        r = self.reader
        if not r or r.get("urls") is None:
            return
        p = DB["progress"].setdefault(pkey(r["m"]), {"read": []})
        url = r["chs"][r["idx"]]["url"]
        n = len(r["urls"])
        if not n:
            return
        atend = False
        if self.is_web():
            try:
                bot = r["c"].yview()[1]
            except Exception:
                bot = 0
            # images far from the viewport are dropped on purpose now, so judge "finished" by the last page
            atend = bot >= 0.97 and r.get("page", 0) >= n - 1
        else:
            atend = self.pg_spread(r["page"])[-1] >= n - 1
        if p.get("chapter") == url:
            p["page"] = r.get("page", 0)
        if mark or atend:
            p.setdefault("read", [])
            if url not in p["read"]:
                p["read"].append(url)
        save_db_soon()

    def open_chapter(self, m, chs, idx, nxt=False, restart=False):
        if self.cur == "Reader":
            self.save_reader(mark=nxt)
        ch = chs[idx]
        p = DB["progress"].setdefault(pkey(m), {"read": []})
        page = 0 if restart else (p.get("page", 0) if p.get("chapter") == ch["url"] else 0)
        p.update(chapter=ch["url"], title=ch["title"], page=page,
                 ts=time.time(),          # drives the Continue shelf ordering
                 manga={k: m[k] for k in ("source", "url", "title", "cover")})
        DB["last"] = {"manga": {k: m[k] for k in ("source", "url", "title", "cover")}, "key": pkey(m)}
        save_db()
        self.rtok += 1
        tok = self.rtok
        mode = p.get("mode", S("mode"))
        mode = mode if mode in MODES else MODES[0]
        local = local_path(m, ch.get("i", idx), ch)
        src = LOCAL if local else SOURCES.get(m["source"])
        self.reader = {"m": m, "chs": chs, "idx": idx, "urls": None, "mode": mode, "zoom": 1.0, "page": page, "tok": tok,
                       "restore": page if page > 0 else None, "err": None, "src": src, "local": local}
        self.show("Reader")
        self.r_title.configure(text=f'{m["title"][:34]}  ·  {ch["title"][:30]}')
        self.r_prev.configure(state="normal" if idx > 0 else "disabled")
        self.r_next.configure(state="normal" if idx + 1 < len(chs) else "disabled")
        self.r_bm.configure(text=self.bm_text(m))
        labels, by_label = [], {}
        for i, c2 in enumerate(chs):
            t2 = (c2.get("title") or "").strip()
            lab = f"{i + 1}: {t2[:26]}" if t2 else f"Chapter {i + 1}"
            if lab in by_label:          # duplicate chapter titles stay unique for the menu
                lab = f"{lab}  ({i + 1})"
            labels.append(lab)
            by_label[lab] = i
        self._ch_labels, self._ch_map = labels, by_label
        self.r_chs.configure(text="\u25bc  " + labels[idx])
        self.r_mode.set(mode)
        self.r_zoom.configure(text="100%")
        self.r_page.configure(text="")
        self.build_body()
        if local:
            bg(lambda: cbz_pages(local), lambda res, e: self.pages_ready(tok, res, e))
        elif isinstance(src, Source):
            bg(lambda s=src: fetch_pages(s, ch["url"]), lambda res, e: self.pages_ready(tok, res, e))
        else:
            self.pages_ready(tok, [], "source not found")

    def pages_ready(self, tok, urls, err):
        if tok != self.rtok:
            return
        self.reader["urls"] = urls or []
        self.reader["err"] = str(err)[:120] if err else None
        self.build_body()

    def chapter_step(self, d):
        r = self.reader
        if r and 0 <= r["idx"] + d < len(r["chs"]):
            self.open_chapter(r["m"], r["chs"], r["idx"] + d, nxt=d > 0)

    def reader_ch_jump(self, label):
        """Chapter dropdown in the reader bar: jump straight to the picked chapter."""
        r, idx = self.reader, self._ch_map.get(label)
        if not r or idx is None or idx == r["idx"]:
            return
        self.open_chapter(r["m"], r["chs"], idx, nxt=idx > r["idx"])

    def _chs_pick(self, lab, win):
        try:
            win.destroy()
        except Exception:
            pass
        self.reader_ch_jump(lab)

    @staticmethod
    def _chapter_no(title):
        """Normalised chapter number from a chapter title ('Chapter 1059', 'Ch. 2.5')."""
        t = (title or "").strip()
        m = re.search(r"(?i)(?:chapter|ch\.?|episode|ep\.?)\s*#?\s*(\d+(?:\.\d+)?)", t)
        if m:
            return m.group(1)
        nums = re.findall(r"\d+(?:\.\d+)?", t)
        return nums[-1] if nums else None

    def _chapter_jump_number(self, text, win, err):
        """Jump to a typed chapter number; keep the popup open and show a small error."""
        m = re.fullmatch(r"\s*(?:chapter|ch\.?|#)?\s*(\d+(?:\.\d+)?)\s*", text or "", re.I)
        if not m:
            err.configure(text="Enter a chapter number, e.g. 1059")
            return
        try:
            target = float(m.group(1))
        except ValueError:
            err.configure(text="Enter a chapter number, e.g. 1059")
            return
        r = self.reader
        if not r:
            return
        matches = []
        for i, ch in enumerate(r["chs"]):
            num = self._chapter_no(ch.get("title", ""))
            try:
                if num is not None and abs(float(num) - target) < 1e-6:
                    matches.append(i)
            except (TypeError, ValueError):
                pass
        if not matches:
            err.configure(text=f"No Chapter {m.group(1)} in this title")
            return
        idx = min(matches, key=lambda i: abs(i - r["idx"]))
        self._chs_pick(self._ch_labels[idx], win)

    def chs_menu_open(self):
        """Chapter picker with a direct number entry and a scrollable list."""
        self.mmb_stop()
        labels = getattr(self, "_ch_labels", [])
        r = self.reader
        if not labels or not r:
            return
        cur = r["idx"]
        win = tk.Toplevel(self)
        win.withdraw()  # size/position while hidden; mapping first snapped it to 0,0
        win.overrideredirect(True)
        try:
            win.configure(bg=LINE)
        except Exception:
            pass
        panel = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=8, border_width=1, border_color=LINE)
        panel.pack(fill="both", expand=True, padx=1, pady=1)

        ctk.CTkLabel(panel, text="Jump to chapter", height=28,
                     font=("Segoe UI", 11, "bold"), text_color=MUTED, fg_color=CARD,
                     corner_radius=0).pack(fill="x", padx=(2, 2), pady=(2, 4))
        go = ctk.CTkFrame(panel, fg_color=PANEL)
        go.pack(fill="x", padx=10, pady=(0, 2))
        ctk.CTkLabel(go, text="Chapter", font=("Segoe UI", 11), text_color=TEXT).pack(side="left")
        ent = ctk.CTkEntry(go, width=122, height=30, placeholder_text="number",
                           font=("Segoe UI", 11))
        ent.pack(side="left", padx=6)
        err = ctk.CTkLabel(panel, text="", height=18, anchor="w",
                           font=("Segoe UI", 10), text_color="#e06c75")
        err.pack(fill="x", padx=12, pady=(0, 2))

        def submit():
            self._chapter_jump_number(ent.get(), win, err)
            return "break"

        btn(go, "Go", submit, primary=True, width=48, height=30).pack(side="left")
        ent.bind("<Return>", lambda e: submit())

        body = ctk.CTkFrame(panel, fg_color=PANEL)
        body.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        # A real Listbox, not one button per chapter. Bleach/One Piece have 1000+
        # chapters; building that many CTk widgets blocked Tk for seconds.
        lb = tk.Listbox(body, bg=PANEL, fg=TEXT, selectbackground=BTN_HI, selectforeground=SILVER_HI,
                        highlightthickness=0, borderwidth=0, relief="flat", exportselection=False,
                        activestyle="none", font=("Segoe UI", 11))
        sb = ctk.CTkScrollbar(body, command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 4), pady=2)
        lb.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=2)
        for i, lab in enumerate(labels):
            lb.insert("end", ("\u25cf   " if i == cur else "      ") + lab)
        try:
            lb.selection_set(cur)
            lb.activate(cur)
            lb.see(max(0, cur - 4))
        except Exception:
            pass

        def wheel(e):
            lb.yview_scroll(-1 if e.delta > 0 else 1, "units")
            return "break"

        def pick(e):
            i = lb.nearest(e.y)
            if 0 <= i < len(labels):
                self._chs_pick(labels[i], win)

        lb.bind("<MouseWheel>", wheel)
        lb.bind("<ButtonRelease-1>", pick)
        win.bind("<MouseWheel>", wheel)

        w = 400
        hpx = min(170 + len(labels) * 22, 600)
        self.update_idletasks()
        bx, by = self.r_chs.winfo_rootx(), self.r_chs.winfo_rooty()
        bw = max(self.r_chs.winfo_width(), 150)
        bh = self.r_chs.winfo_height()
        if bx <= 1:  # borderless/fullscreen can report 0 before the first layout pass
            bx = self.winfo_rootx() + self.winfo_width() - w - 60
        x = min(max(bx + bw - w, 8), max(8, self.winfo_screenwidth() - w - 8))
        y = by + bh + 4
        if y + hpx > self.winfo_screenheight() - 8:
            y = max(8, by - hpx - 4)
        win.geometry(f"{w}x{hpx}+{x}+{y}")
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass
        win.deiconify()
        win.lift()
        win.grab_set()
        ent.focus_set()
        ent.icursor("end")
        win.bind("<Escape>", lambda e: win.destroy())

        def outside(e):
            px, py, pw, ph = win.winfo_rootx(), win.winfo_rooty(), win.winfo_width(), win.winfo_height()
            if not (px <= e.x_root < px + pw and py <= e.y_root < py + ph):
                try:
                    win.destroy()
                except Exception:
                    pass
        win.bind("<Button-1>", outside)
        self._chs_open = win

    def reader_back(self):
        self.show("Details")
        self.refresh_tree()

    def change_mode(self, name):
        r = self.reader
        if not r or name == r["mode"]:
            return
        was_web = self.is_web()
        r["mode"] = name
        DB["progress"].setdefault(pkey(r["m"]), {"read": []})["mode"] = name
        save_db()
        if not was_web and self.is_web() and r["page"] > 0:
            r["restore"] = r["page"]
        r["pan"] = [0, 0]
        self.build_body()

    def build_body(self):
        r = self.reader
        self.mmb_stop()
        self.rgen += 1
        r["gen"] = self.rgen
        for k in ("c", "labels", "items", "texts", "photos", "nextbtn", "ys", "total", "cw",
                  "state", "imgs", "dims", "t0", "_wz", "borders", "tex", "tex_items", "tex_cols", "tex_rows"):
            r.pop(k, None)
        clear(self.rbody)
        msg = None
        if r["urls"] is None:
            msg = "Loading chapter…"
        elif r["err"] or not r["urls"]:
            msg = f"Could not load pages: {r['err'] or 'none found'}"
        if msg:
            ctk.CTkLabel(self.rbody, text=msg, font=("Segoe UI", 15), text_color=reader_muted()).pack(pady=80)
            return
        self.update_idletasks()
        self.build_webtoon() if self.is_web() else self.build_paged()

    # --- webtoon (continuous vertical) ---
    def web_width(self):
        return int(max(300, min(900, self.rbody.winfo_width() - 40)) * self.reader["zoom"])

    def wt_dims(self, urls, W):
        """Pixel box for every page: exact when the file is already on disk, estimated otherwise.

        Knowing the sizes up-front keeps the scroll layout correct from the first frame, so resuming at
        page 40 no longer needs pages 1-39 to be downloaded first - and a page can be dropped from
        memory later without the pages below it jumping up.
        """
        raw, ratios = [], []
        for u in urls:
            wh = img_size(u)
            raw.append(wh)
            if wh[0] > 0 and wh[1] > 0:
                ratios.append(wh[1] / float(wh[0]))
        ratios.sort()
        est = ratios[len(ratios) // 2] if ratios else 1.45
        out = []
        for wh in raw:
            r = (wh[1] / float(wh[0])) if wh[0] > 0 and wh[1] > 0 else est
            w, h = W, max(1, int(round(W * r)))
            if w * h > WT_MAX_PX:  # one 1:30 strip must not eat the whole memory budget
                k = (WT_MAX_PX / float(w * h)) ** 0.5
                w, h = max(1, int(w * k)), max(1, int(h * k))
            out.append((w, h))
        return out

    def wt_tops(self, r):
        ys, y = [], 0
        for _w, h in r.get("dims") or []:
            ys.append(y)
            y += h
        return ys, y

    def build_webtoon(self):
        r, gen, n = self.reader, self.reader["gen"], len(self.reader["urls"])
        W = self.web_width()
        dims = self.wt_dims(r["urls"], W)
        c = tk.Canvas(self.rbody, bg=(paper_avg(S("reader_paper")) or READER_BG), highlightthickness=0,
                      yscrollincrement=1, xscrollincrement=1)
        vs = ctk.CTkScrollbar(self.rbody, command=c.yview, fg_color=READER_BG, button_color=BTN_HI, button_hover_color=SILVER_DIM)
        hs = ctk.CTkScrollbar(self.rbody, orientation="horizontal", command=c.xview, fg_color=READER_BG, button_color=BTN_HI,
                              button_hover_color=SILVER_DIM)
        c.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        vs.pack(side="right", fill="y")
        c.pack(side="left", fill="both", expand=True)
        ph = page_box()
        r.update(c=c, hs=hs, dims=dims, state=[0] * n, tries=[0] * n, t0=[0.0] * n, inflight=0, wgen=0,
                 width=W, items=[], texts=[], photos={}, nextbtn=None, ys=[], total=0, cw=W, sreg=0, lastreq=0.0,
                 borders=[], tex=None, tex_items=[], tex_cols=0, tex_rows=0,
                 strips={}, split={}, splitq=[])
        self.wt_make_tex(r, c, c.winfo_width() or W, c.winfo_height() or 800)
        # Pages are canvas ITEMS, never child widgets: Windows refuses to place child windows beyond
        # +-32767 px, so a frame full of labels freezes in place once a chapter is longer than that
        # (the page counter kept going while the screen showed stale pages).
        y = 0
        for i, (w, h) in enumerate(dims):
            x = max(0, (W - w) // 2)
            bd = c.create_rectangle(x - 1, y - 1, x + w + 1, y + h + 1, outline="#000000", width=3)
            it = c.create_image(x, y, anchor="nw", image=ph)
            tx = c.create_text(x + w / 2, y + h / 2, anchor="center", text=f"Page {i + 1}",
                               fill=reader_muted(), font=("Segoe UI", 11))
            c.tag_bind(it, "<Button-1>", lambda e, i=i: self.wt_retry(i))
            c.tag_bind(tx, "<Button-1>", lambda e, i=i: self.wt_retry(i))
            r["borders"].append(bd)
            r["items"].append(it)
            r["texts"].append(tx)
            y += h
        if r["idx"] + 1 < len(r["chs"]):
            rect = c.create_rectangle(0, 0, 0, 0, fill=SILVER, outline="")
            txt = c.create_text(0, 0, text="Next chapter ▶", fill=INK, font=("Segoe UI", 12, "bold"))
            c.tag_bind(rect, "<Button-1>", lambda e: self.chapter_step(1))
            c.tag_bind(txt, "<Button-1>", lambda e: self.chapter_step(1))
            r["nextbtn"] = (rect, txt)
        self.wt_place()
        c.bind("<Configure>", lambda e: (self.wt_place(), self.wt_sched_resize()))
        self.after(80, lambda: self.wt_tick(gen))

    def wt_place(self):
        """Put every page item at its offset and refresh the scroll region.

        Canvas items are drawn by Tk itself, so (unlike child windows) they work at any depth.
        """
        r = self.reader
        try:
            c, dims, items, texts = r["c"], r["dims"], r["items"], r["texts"]
        except Exception:
            return
        borders = r.get("borders") or []
        cw = max(c.winfo_width(), r.get("width") or 0, max((w for w, _ in dims), default=0))
        r["cw"] = cw
        self.wt_make_tex(r, c, cw, c.winfo_height() or 800)
        ys, y = [], 0
        for i, (w, h) in enumerate(dims):
            ys.append(y)
            x = max(0, (cw - w) // 2)
            try:
                # a tall page is several stacked items; strip k sits k*WT_STRIP below the page top
                for k, it in enumerate(self.wt_strip_items(r, i)):
                    c.coords(it, x, y + k * WT_STRIP)
                c.coords(texts[i], x + w / 2, y + h / 2)
                if i < len(borders):
                    c.coords(borders[i], x - 1, y - 1, x + w + 1, y + h + 1)
            except Exception:
                pass
            y += h
        r["ys"], r["total"] = ys, y
        nb = r.get("nextbtn")
        if nb:
            bx, by = cw / 2, y + 24
            c.coords(nb[0], bx - 100, by, bx + 100, by + 40)
            c.coords(nb[1], bx, by + 20)
            y += 88
        r["sreg"] = max(1, y)
        c.configure(scrollregion=(0, 0, cw + 20, y))
        self.wt_paint_tex(r, c)

    def wt_make_tex(self, r, c, cw, ch):
        """(Re)build the pool of paper tiles that sit behind the pages, sized to the viewport."""
        tex = paper_tile(self, S("reader_paper"))
        tiles = []
        if tex:
            ts = tex.width()
            cols, rows = max(1, (int(cw) + ts - 1) // ts + 1), max(1, (int(ch) + ts - 1) // ts + 1)
            tiles = [cols, rows]
        if tex is r.get("tex") and (not tex or (tiles[0] == r.get("tex_cols") and tiles[1] == r.get("tex_rows"))):
            return
        for it in r.get("tex_items") or []:
            try:
                c.delete(it)
            except Exception:
                pass
        r["tex"] = tex
        r["tex_cols"], r["tex_rows"] = (tiles or [0, 0])[0], (tiles or [0, 0])[1]
        r["tex_items"] = []
        if tex:
            r["tex_items"] = [c.create_image(0, 0, anchor="nw", image=tex, tags=("texbg",))
                              for _ in range(r["tex_cols"] * r["tex_rows"])]
            c.tag_lower("texbg")

    def wt_paint_tex(self, r, c):
        """Keep the tiles under the visible part of the chapter while it scrolls."""
        tex, items = r.get("tex"), r.get("tex_items") or []
        if not tex or not items:
            return
        ts, cols = tex.width(), max(1, r.get("tex_cols") or 1)
        top = c.canvasy(0)
        for k, it in enumerate(items):
            try:
                c.coords(it, (k % cols) * ts, top + (k // cols) * ts)
            except Exception:
                return

    def wt_layout(self):
        self.wt_place()

    def wt_sched_resize(self):
        """The window changed size - refit the pages to the new width (debounced)."""
        r = self.reader
        if not r or not self.is_web() or not r.get("items"):
            return
        old = r.get("_wz")
        if old:
            try:
                self.after_cancel(old)
            except Exception:
                pass
        r["_wz"] = self.after(280, self.wt_resize)

    def wt_resize(self):
        r = self.reader
        if r is not None:
            r["_wz"] = None
        if not r or not self.is_web() or not r.get("items") or r.get("c") is None:
            return
        if abs(self.web_width() - r.get("width", 0)) < 24:  # a scrollbar showing up is not a resize
            return
        self.wt_apply_zoom()

    def wt_retry(self, i):
        r = self.reader
        if r and r.get("state") and 0 <= i < len(r["state"]) and r["state"][i] == 3:
            self.wt_clear_strips(i)
            self.wt_reset_page(i)
            r["state"][i], r["tries"][i] = 0, 0

    def wt_tick(self, gen):
        r = self.reader
        if gen != self.rgen or not r or not r.get("items"):
            return
        try:
            c, st = r["c"], r["state"]
            n = len(st)
            ys, _total = self.wt_tops(r)
            ch = max(1, c.winfo_height())
            top = c.canvasy(0)
            k = r.get("restore")
            if k is not None:  # resume: the layout is already right, so one jump is enough
                k = max(0, min(int(k), n - 1))
                r["restore"] = None
                self.wt_place()
                self.update_idletasks()
                c.yview_moveto(max(0.0, (ys[k] - 8) / float(max(1, r["sreg"]))))
                top = c.canvasy(0)
            bot = top + ch
            self.wt_paint_tex(r, c)
            self.wt_split_tick()    # a few strips per frame keeps a tall page from stalling the scroll
            i0 = 0
            for i, y in enumerate(ys):
                if y <= top + 8:
                    i0 = i
                elif y > bot:
                    break
            i1 = i0
            for i in range(i0, n):
                if ys[i] < bot:
                    i1 = i
                else:
                    break
            r["page"] = i0
            self.r_page.configure(text=f"{i0 + 1} / {n}")
            # only pages close to the viewport are downloaded - the rest waits until they are scrolled to
            lo, hi = max(0, i0 - WT_BEHIND), min(n - 1, i1 + WT_AHEAD)
            mid = (top + bot) / 2
            todo = [i for i in range(lo, hi + 1) if st[i] == 0]
            todo.sort(key=lambda i: abs(ys[i] + r["dims"][i][1] / 2.0 - mid))
            now = time.time()
            for i in todo:
                if r["inflight"] >= WT_MAX_INFLIGHT:
                    break
                self.wt_request(i, gen)
            if r["inflight"] and now - (r.get("lastreq") or now) > 30:
                # no answer came back for work that is supposedly running: never allow that to block
                # the whole chapter (a lost callback used to freeze every later page)
                r["inflight"] = 0
                for i in range(n):
                    if st[i] == 1:
                        st[i] = 0
            for i in range(lo, hi + 1):  # watchdog: a page that never answers must not block the queue
                if st[i] == 1 and now - (r["t0"][i] or now) > 90:
                    st[i], r["tries"][i], r["inflight"] = 0, r["tries"][i] + 1, max(0, r["inflight"] - 1)
                elif st[i] == 3 and now - (r["t0"][i] or now) > 20:
                    st[i] = 0  # a transient hiccup must not leave a page blank for the rest of the chapter
            # drop images far from the viewport: without this a long chapter piles up every page
            # in memory (a tall strip is ~40-60 MB as a Tk image) until the whole app crawls
            klo, khi = i0 - WT_BEHIND - WT_KEEP, i1 + WT_AHEAD + WT_KEEP
            for i in range(n):
                if st[i] in (2, 4) and (i < klo or i > khi):
                    if st[i] == 4:
                        self.wt_split_cancel(i)
                    self.wt_reset_page(i)     # placeholder again, for every strip
                    self.wt_border(i, True)   # ... so the page box is visible
                    st[i] = 0
        except Exception as e:
            log_error("wt_tick", e)
        self.after(90, lambda: self.wt_tick(gen))

    def wt_request(self, i, gen):
        r = self.reader
        r["state"][i] = 1
        r["t0"][i] = time.time()
        r["lastreq"] = r["t0"][i]
        wg = r["wgen"]
        ok = load_img(r.get("src"), r["urls"][i], lambda im, i=i, wg=wg: self.wt_loaded(gen, wg, i, im),
                      width=r["dims"][i][0], pool=PAGE_POOL, alive=lambda: gen == self.rgen)
        if ok:
            r["inflight"] += 1  # counted only once the work is really queued
        else:
            r["state"][i] = 3

    def wt_loaded(self, gen, wg, i, im):
        if gen != self.rgen:
            return
        r = self.reader
        r["inflight"] = max(0, r["inflight"] - 1)
        if wg != r["wgen"] or not r.get("items") or i >= len(r["state"]):
            if r.get("state") and i < len(r["state"]):
                r["state"][i] = 0
            return
        c = r["c"]
        if im is None:
            r["tries"][i] += 1
            if r["tries"][i] < 3:
                r["state"][i] = 0
            else:
                r["state"][i] = 3
                c.itemconfigure(r["texts"][i], text=f"Page {i + 1} failed — click to retry")
            return
        self.wt_fix_box(i, im)
        if im.height > WT_STRIP:   # tall page: build its strips over the next few frames
            self.wt_split(i, im)
            return
        self.wt_clear_strips(i)
        try:
            ph = ImageTk.PhotoImage(im)
        except Exception as e:
            log_error("wt_loaded", e)
            r["state"][i], r["tries"][i] = 0, r["tries"][i] + 1
            return
        r["photos"][i] = [ph]  # canvas items do not own their image - keep it alive here
        c.itemconfigure(r["items"][i], image=ph)
        c.itemconfigure(r["texts"][i], text="")
        self.wt_border(i, False)     # artwork is on canvas: no artificial page border
        r["state"][i] = 2

    def wt_strip_items(self, r, i):
        """Every canvas item of one page: the primary item plus any split strips."""
        try:
            return (r.get("strips") or {}).get(i) or [r["items"][i]]
        except Exception:
            return []

    def wt_split(self, i, im):
        """Lay out one canvas item per horizontal strip of a tall page.

        The strip images themselves are made in wt_split_tick(), a couple per frame, so the
        UI thread never uploads a 20 000 px image in one go.
        """
        r = self.reader
        c = r["c"]
        k = max(1, (im.height + WT_STRIP - 1) // WT_STRIP)
        items = list((r.get("strips") or {}).get(i) or [r["items"][i]])
        for it in items[k:]:      # an older, taller load left spare strips behind
            try:
                c.delete(it)
            except Exception:
                pass
        items = items[:k]
        while len(items) < k:     # items are cheap; only the PhotoImages are expensive
            it = c.create_image(0, 0, anchor="nw", image=page_box())
            c.tag_bind(it, "<Button-1>", lambda e, i=i: self.wt_retry(i))
            items.append(it)
        try:
            w, h = r["dims"][i]
            ys = r.get("ys") or self.wt_tops(r)[0]
            y = ys[i] if i < len(ys) else 0
            x = max(0, ((r.get("cw") or r.get("width") or w) - w) // 2)
            for n, it in enumerate(items):
                c.coords(it, x, y + n * WT_STRIP)
        except Exception as e:
            log_error("wt_split", e)
        r.setdefault("strips", {})[i] = items
        r["photos"][i] = []
        r["split"][i] = [im, 0]
        r["state"][i] = 4        # decoded, strips still being built
        if i not in r["splitq"]:
            r["splitq"].append(i)

    def wt_split_tick(self, budget=WT_STRIPS_PER_TICK):
        """Build and show at most `budget` strip images from the queued tall pages."""
        r = self.reader
        q = r.get("splitq") or []
        if not q or not r.get("c"):
            return
        c = r["c"]
        for _ in range(budget):
            while q:
                i = q[0]
                if (not (r.get("split") or {}).get(i) or i >= len(r["state"])
                        or r["state"][i] != 4):
                    q.pop(0)
                    (r.get("split") or {}).pop(i, None)
                    continue
                break
            if not q:
                break
            i = q[0]
            im, k = r["split"][i]
            items = (r.get("strips") or {}).get(i) or [r["items"][i]]
            if k >= len(items):
                q.pop(0)
                r["split"].pop(i, None)
                continue
            part = im.crop((0, k * WT_STRIP, im.width, min(im.height, (k + 1) * WT_STRIP)))
            try:
                ph = ImageTk.PhotoImage(part)
            except Exception as e:
                log_error("wt_split_tick", e)
                q.pop(0)
                self.wt_clear_strips(i)
                self.wt_reset_page(i)
                r["state"][i], r["tries"][i] = 0, r["tries"][i] + 1
                continue
            c.itemconfigure(items[k], image=ph)
            r["photos"].setdefault(i, []).append(ph)
            k += 1
            if k == 1:
                c.itemconfigure(r["texts"][i], text="")
            if k >= len(items):
                q.pop(0)
                r["split"].pop(i, None)
                self.wt_border(i, False)   # whole page is on canvas now
                r["state"][i] = 2
            else:
                r["split"][i][1] = k
        r["splitq"] = q

    def wt_split_cancel(self, i):
        """Forget the pending strips of a page (it scrolled out of reach)."""
        r = self.reader
        (r.get("split") or {}).pop(i, None)
        if r.get("splitq"):
            r["splitq"] = [j for j in r["splitq"] if j != i]

    def wt_clear_strips(self, i):
        """Drop every extra strip item of a page - their images and canvas items."""
        r = self.reader
        try:
            items = (r.get("strips") or {}).pop(i, None) or []
            for it in items[1:]:
                r["c"].delete(it)
            (r.get("photos") or {}).pop(i, None)
            self.wt_split_cancel(i)
        except Exception as e:
            log_error("wt_clear_strips", e)

    def wt_reset_page(self, i):
        """Put a page (all of its strips) back to the placeholder box."""
        r = self.reader
        try:
            ph = page_box()
            for it in self.wt_strip_items(r, i):
                r["c"].itemconfigure(it, image=ph)
            r["c"].itemconfigure(r["texts"][i], text=f"Page {i + 1}")
            r["photos"].pop(i, None)
        except Exception as e:
            log_error("wt_reset_page", e)

    def wt_border(self, i, show=True):
        """Page-box outline: visible only for placeholders/failed pages, hidden once the
        real artwork covers the box (the stacked outline edges at page junctions used to
        read as a random black hairline across the middle of a long strip)."""
        try:
            r = self.reader
            b = r.get("borders") or []
            if r.get("c") is not None and 0 <= i < len(b):
                r["c"].itemconfigure(b[i], state="normal" if show else "hidden")
        except Exception:
            pass

    def wt_fix_box(self, i, im):
        """The page turned out to have a different shape than the estimate - resize its box in place."""
        r = self.reader
        dims = r.get("dims")
        if not dims or i >= len(dims) or not r.get("items"):
            return
        w, h = im.size
        ow, oh = dims[i]
        if (w, h) == (ow, oh):
            return
        c = r["c"]
        top = c.canvasy(0)
        ys = r.get("ys") or self.wt_tops(r)[0]
        y_i = ys[i] if i < len(ys) else 0
        dims[i] = (w, h)
        self.wt_place()
        self.update_idletasks()
        if y_i < top:  # a page above the viewport grew/shrank: keep the text under the user's eyes still
            tot = float(max(1, r["sreg"]))
            c.yview_moveto(min(1.0, max(0.0, (top + h - oh) / tot)))

    def wt_apply_zoom(self):
        r = self.reader
        if not r or not r.get("items") or not self.is_web() or r.get("c") is None:
            return
        c = r["c"]
        ys = r.get("ys") or self.wt_tops(r)[0]
        cur = max(0, min(int(r.get("page", 0)), max(0, len(ys) - 1)))
        off = max(0.0, c.canvasy(0) - ys[cur]) if ys else 0.0
        r["wgen"] += 1
        r["width"] = self.web_width()
        r["dims"] = self.wt_dims(r["urls"], r["width"])
        for i in range(len(r["items"])):
            self.wt_clear_strips(i)   # new width: every strip must be rebuilt
            self.wt_reset_page(i)
            self.wt_border(i, True)
        r["state"] = [0 if s in (1, 2, 4) else s for s in r["state"]]
        r["tries"] = [0] * len(r["state"])
        r["inflight"] = 0
        if r["zoom"] > 1:
            r["hs"].pack(side="bottom", fill="x", before=r["c"])
        else:
            r["hs"].pack_forget()
        self.wt_place()
        self.update_idletasks()
        ys = r["ys"]
        tot = float(max(1, r["sreg"]))
        c.yview_moveto(min(1.0, max(0.0, (ys[cur] + off) / tot)))

    # --- paged (single / double, LTR / RTL) ---
    def build_paged(self):
        r = self.reader
        c = tk.Canvas(self.rbody, bg=(paper_avg(S("reader_paper")) or READER_BG), highlightthickness=0)
        c.pack(fill="both", expand=True)
        r.update(c=c, imgs={}, req=set(), failed=set(), pan=[0, 0], ph=None, rkey=None, drag=None)
        r["restore"] = None
        r["page"] = min(r["page"], len(r["urls"]) - 1)
        c.bind("<Configure>", lambda e: self.pg_sched())
        c.bind("<ButtonPress-1>", self.pg_press)
        c.bind("<B1-Motion>", self.pg_drag)
        c.bind("<ButtonRelease-1>", self.pg_release)
        self.pg_show()

    def pg_spread(self, p):
        n = len(self.reader["urls"])
        if not self.is_double():
            return [p]
        if p == 0:
            return [0]
        s = p if p % 2 == 1 else p - 1
        return [s] + ([s + 1] if s + 1 < n else [])

    def pg_show(self):
        r, gen, n = self.reader, self.reader["gen"], len(self.reader["urls"])
        sp = self.pg_spread(r["page"])
        want = sp + [i for i in range(sp[-1] + 1, min(n, sp[-1] + 5))] + ([sp[0] - 1] if sp[0] > 0 else [])
        for i in want:
            if i in r["imgs"] or i in r["req"]:
                continue
            ok = load_img(r.get("src"), r["urls"][i], lambda im, i=i: self.pg_loaded(gen, i, im), pool=PAGE_POOL,
                          alive=lambda: gen == self.rgen)
            if ok:
                r["req"].add(i)
            else:
                r["failed"].add(i)
        self.pg_render()

    def pg_loaded(self, gen, i, im):
        if gen != self.rgen:
            return
        r = self.reader
        r["req"].discard(i)
        if im is None:
            r["failed"].add(i)
        else:
            r["imgs"][i] = im
            keep = set(self.pg_spread(r["page"])) | set(range(r["page"] - 2, r["page"] + 6))
            while len(r["imgs"]) > 14:
                old = next((k for k in r["imgs"] if k not in keep), None)
                if old is None:
                    break
                r["imgs"].pop(old)
        if i in self.pg_spread(r["page"]):
            self.pg_render()

    def pg_sched(self):
        r = self.reader
        if r.get("_rs"):
            self.after_cancel(r["_rs"])
        r["_rs"] = self.after(120, self.pg_render)

    def pg_render(self):
        r = self.reader
        c = r.get("c")
        if not c or r.get("urls") is None or self.is_web():
            return
        cw, ch = c.winfo_width(), c.winfo_height()
        if cw < 30:
            return
        sp = self.pg_spread(r["page"])
        n = len(r["urls"])
        self.r_page.configure(text=f"{sp[0] + 1}{'–' + str(sp[-1] + 1) if len(sp) > 1 else ''} / {n}")
        ims = [r["imgs"].get(i) for i in sp]
        c.delete("all")
        tile = paper_tile(self, S("reader_paper"))  # paper surface behind the pages
        if tile:
            ts = tile.width()
            for y in range(0, int(ch) + ts, ts):
                for x in range(0, int(cw) + ts, ts):
                    c.create_image(x, y, anchor="nw", image=tile)
        if any(im is None for im in ims):
            failed = any(i in r["failed"] for i in sp)
            c.create_text(cw / 2, ch / 2, text="Page failed to load — click to retry" if failed else "Loading…", fill=reader_muted(), font=("Segoe UI", 14))
            return
        rtl = self.is_rtl()
        pairs = list(zip(sp, ims))
        if rtl and len(pairs) == 2:
            ims = ims[::-1]
            pairs = pairs[::-1]
        gap = PAGE_GAP if len(pairs) == 2 else 0
        key = (tuple(sp), cw, ch, r["zoom"], rtl, gap)
        if r["rkey"] != key:
            H = max(im.height for _, im in pairs)
            tw = sum(im.width * H / im.height for _, im in pairs)
            th = max(1, int(H * min(cw / max(1, tw + gap * (len(pairs) - 1)), ch / H) * r["zoom"]))
            parts = [(pi, im.resize((max(1, int(im.width * th / im.height)), th), Image.Resampling.LANCZOS)) for pi, im in pairs]
            # the spread is laid on black: the gap between the halves becomes the page gutter
            out = Image.new("RGB", (sum(p.width for _, p in parts) + gap * (len(parts) - 1), th), (0, 0, 0))
            x, lays = 0, []
            for pi, p in parts:
                out.paste(p, (x, 0))
                lays.append((pi, x, p.width))
                x += p.width + gap
            r["ph"], r["rkey"], r["size"], r["lays"] = ImageTk.PhotoImage(out), key, out.size, lays
        w, h = r["size"]
        mx, my = max(0, (w - cw) / 2), max(0, (h - ch) / 2)
        r["pan"][0] = max(-mx, min(mx, r["pan"][0]))
        r["pan"][1] = max(-my, min(my, r["pan"][1]))
        cx, cy = cw / 2 + r["pan"][0], ch / 2 + r["pan"][1]
        left, top = cx - w / 2, cy - h / 2
        c.create_image(cx, cy, image=r["ph"])
        if not S("paged_guides"):
            return
        for pi, lx, lw in r["lays"]:  # thick black contour + page number per visible page
            c.create_rectangle(left + lx, top, left + lx + lw, top + h, outline="#000000", width=PAGE_BORDER)
            c.create_text(left + lx + lw / 2, top + h - 14, text=str(pi + 1), fill=reader_muted(), font=("Segoe UI", 11))
        if len(r["lays"]) == 2:  # little binding mark in the middle of the gutter
            _, lx, lw = r["lays"][0]
            gx = left + lx + lw + gap / 2
            c.create_line(gx, top + h / 2 - 30, gx, top + h / 2 + 30, fill=SILVER_DIM, width=3)

    def pg_step(self, d):
        r = self.reader
        n = len(r["urls"])
        sp = self.pg_spread(r["page"])
        if d > 0:
            if sp[-1] + 1 >= n:
                self.chapter_step(1)
                return
            r["page"] = sp[-1] + 1
        else:
            if sp[0] == 0:
                self.chapter_step(-1)
                return
            r["page"] = self.pg_spread(sp[0] - 1)[0]
        r["pan"] = [0, 0]
        self.pg_show()

    def pg_press(self, e):
        self.reader["drag"] = [e.x, e.y, list(self.reader["pan"]), False]

    def pg_drag(self, e):
        r = self.reader
        d = r.get("drag")
        if not d:
            return
        if abs(e.x - d[0]) + abs(e.y - d[1]) > 5:
            d[3] = True
        if d[3] and r["zoom"] > 1:
            r["pan"] = [d[2][0] + e.x - d[0], d[2][1] + e.y - d[1]]
            self.pg_render()

    def pg_release(self, e):
        r = self.reader
        d, r["drag"] = r.get("drag"), None
        if not d or d[3]:
            return
        sp = self.pg_spread(r["page"])
        if any(i in r["failed"] for i in sp):
            r["failed"].difference_update(sp)
            self.pg_show()
            return
        left = e.x < r["c"].winfo_width() / 2
        self.pg_step(1 if (left == self.is_rtl()) else -1)

    # --- zoom / input ---
    def zoom_by(self, d):
        r = self.reader
        if not r:
            return
        z = r["zoom"]
        if d > 0:
            z = next((v for v in ZOOMS if v > z + 1e-6), ZOOMS[-1])
        else:
            z = next((v for v in reversed(ZOOMS) if v < z - 1e-6), ZOOMS[0])
        self.set_zoom(z)

    def set_zoom(self, z):
        r = self.reader
        r["zoom"] = z
        self.r_zoom.configure(text=f"{int(z * 100)}%")
        if self.is_web():
            if self.zoom_job:
                self.after_cancel(self.zoom_job)
            self.zoom_job = self.after(250, self.wt_apply_zoom)
        else:
            r["pan"] = [0, 0]
            self.pg_render()

    def _listbox_open(self):
        w = getattr(self, "_chs_open", None)
        return bool(w and w.winfo_exists())

    def _scroll_canvas_at(self, e):
        """The scrollable canvas under the pointer (CTk scroll frames or the reader)."""
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
        except Exception:
            return None
        while w is not None:
            c = getattr(w, "_parent_canvas", None)
            if c is not None:
                return c
            if isinstance(w, tk.Canvas):
                try:
                    if self.cur == "Reader" and w is (self.reader or {}).get("c"):
                        if self.is_web():
                            return w
                    elif w.cget("yscrollcommand"):
                        return w
                except Exception:
                    pass
            if w is self:
                break
            w = getattr(w, "master", None)
        return None

    def _canvas_metrics(self, c):
        """(scrollregion top, scrollregion height, viewport height) for a canvas."""
        y0 = total = 0.0
        try:
            vals = [float(v) for v in str(c.cget("scrollregion")).split()]
            if len(vals) == 4:
                y0, total = vals[1], vals[3] - vals[1]
        except Exception:
            pass
        if total <= 0:
            try:
                box = c.bbox("all")
            except Exception:
                box = None
            if box:
                y0, total = box[1], box[3] - box[1]
        if total <= 0:
            return None
        return y0, total, max(1, c.winfo_height())

    def _scroll_px(self, c, dy):
        """Scroll a canvas by a pixel amount, independent of the widget's unit settings."""
        if not dy:
            return 0.0
        m = self._canvas_metrics(c)
        if m is None:
            return 0.0
        y0, total, vh = m
        try:
            top = c.canvasy(0) - y0
        except Exception:
            return 0.0
        new = max(0.0, min(max(0.0, total - vh), top + dy))
        if abs(new - top) < 0.01:
            return 0.0
        try:
            c.yview_moveto(new / total)
        except Exception:
            return 0.0
        return new - top

    def mmb_press(self, e):
        """Middle click toggles auto-scroll: no dragging, click again to stop.

        Direction and speed follow the pointer's distance from the viewport centre, so a click
        in the lower half starts a slow downward scroll immediately. Moving further down (or
        up) speeds it up; moving back towards the middle slows it down again.
        """
        if self._mmb:
            self.mmb_stop()
            return "break"
        c = self._scroll_canvas_at(e)
        if c is None:
            return
        m = self._canvas_metrics(c)
        if m is None or m[1] <= m[2] + 1:   # nothing to scroll
            return
        self._mmb = {"c": c, "v": 0.0, "last": time.perf_counter()}
        try:
            c.configure(cursor="sb_v_double_arrow")
        except Exception:
            pass
        self._mmb_job = self.after(MMB_TICK, self.mmb_tick)
        return "break"

    def mmb_click_stop(self, _event=None):
        """A normal click anywhere ends auto-scroll (the button's own action still runs)."""
        if self._mmb:
            self.mmb_stop()

    def mmb_tick(self):
        st = self._mmb
        if not st:
            self._mmb_job = None
            return
        now = time.perf_counter()
        dt = min(0.08, max(0.001, now - st["last"]))
        st["last"] = now
        c = st["c"]
        try:
            if not c.winfo_exists():
                self.mmb_stop()
                return
            ch = max(1, c.winfo_height())
            cy = c.winfo_rooty() + ch / 2.0
            off = self.winfo_pointery() - cy
            half = max(80.0, ch / 2.0)
        except Exception:
            self.mmb_stop()
            return
        if abs(off) <= MMB_DEAD:
            target = 0.0
        else:
            k = min(1.0, (abs(off) - MMB_DEAD) / max(1.0, half - MMB_DEAD))
            target = (MMB_MIN + (MMB_MAX - MMB_MIN) * (k ** 1.7)) * (1.0 if off > 0 else -1.0)
        # Ease towards the target speed: quick to react, gentle when slowing back down, so
        # webtoon pages never jerk to a halt the moment the pointer crosses the centre.
        tau = MMB_TAU_UP if abs(target) > abs(st["v"]) else MMB_TAU_DOWN
        st["v"] += (target - st["v"]) * (1.0 - math.exp(-dt / tau))
        if target == 0.0 and abs(st["v"]) < 0.5:
            st["v"] = 0.0
        self._scroll_px(c, st["v"] * dt)
        self._mmb_job = self.after(MMB_TICK, self.mmb_tick)

    def mmb_stop(self, _event=None):
        st, self._mmb = self._mmb, None
        if self._mmb_job:
            try:
                self.after_cancel(self._mmb_job)
            except Exception:
                pass
            self._mmb_job = None
        if not st:
            return
        c = st.get("c")
        if c is not None:
            try:
                if c.winfo_exists():
                    c.configure(cursor="")
            except Exception:
                pass

    def on_wheel(self, e):
        if self._mmb:
            self.mmb_stop()
        if self._listbox_open():
            return
        r = self.reader
        if self.cur != "Reader" or not r or "c" not in r:
            return
        if e.state & 0x4:  # Ctrl + wheel = zoom
            self.zoom_by(1 if e.delta > 0 else -1)
        elif self.is_web():
            if e.state & 0x1:
                r["c"].xview_scroll(-int(e.delta * 0.9), "units")
            else:
                r["c"].yview_scroll(-int(e.delta * 0.9), "units")
        elif r["zoom"] > 1:
            r["pan"][1] += e.delta * 0.6
            self.pg_render()
        else:
            self.pg_step(1 if e.delta < 0 else -1)

    def on_key(self, e):
        if self._listbox_open():
            if e.keysym == "Escape":
                self._chs_open.destroy()
            return
        if self._mmb:
            self.mmb_stop()          # any keyboard input takes back manual control
            if e.keysym == "Escape":
                return
        r = self.reader
        if self.cur != "Reader" or not r or "c" not in r:
            return
        k = e.keysym
        if k in ("plus", "equal", "KP_Add"):
            self.zoom_by(1)
        elif k in ("minus", "KP_Subtract"):
            self.zoom_by(-1)
        elif k in ("0", "KP_0"):
            self.set_zoom(1.0)
        elif k == "Escape":
            self.reader_back()
        elif self.is_web():
            amt = {"Down": 120, "Up": -120, "space": 650, "Next": 650, "Prior": -650}.get(k)
            if amt:
                r["c"].yview_scroll(amt, "units")
        else:
            fwd = "Left" if self.is_rtl() else "Right"
            back = "Right" if self.is_rtl() else "Left"
            if k in (fwd, "space", "Next", "Down"):
                self.pg_step(1)
            elif k in (back, "Prior", "Up"):
                self.pg_step(-1)


if __name__ == "__main__":
    threading.Thread(target=prune_cache, daemon=True).start()   # cache trim never blocks the UI
    App().mainloop()
