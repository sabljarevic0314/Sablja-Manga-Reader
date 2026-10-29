"""Paths, defaults and app metadata shared by every module (no imports of app code)."""

import os
import sys

BASE = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
CACHE = os.path.join(DATA, "cache")
DB_FILE = os.path.join(DATA, "db.json")
UPDATE_STATE_FILE = os.path.join(DATA, "update.json")
SRC_FILE = os.path.join(BASE, "sources.json")
os.makedirs(CACHE, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
      "Accept-Language": "en-US,en;q=0.9"}
IMG_ATTRS = ["data-src", "lazy-src", "data-original", "data-lazy-src", "src"]
PAGE_SIZE = 32
# Card sizes (logical px). Bigger covers = fewer widgets on screen = smoother scrolling.
CARD_W, CARD_H = 212, 300
SMALL_W, SMALL_H = 128, 181          # search-result cards
CARD_CELL = CARD_W + 24              # card + frame margin + 2*6 grid padding
SMALL_CELL = SMALL_W + 24
MD_API = "https://api.mangadex.org"

MODES = ["Webtoon (vertical)", "Single · left→right", "Single · right→left", "Double · left→right", "Double · right→left"]
ZOOMS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
# paper textures (the "hardback" look) - the names are what Settings shows
PAPERS = ["Off", "Graphite matte", "Ink matte", "Paper"]
PAGE_BORDER = 5     # black contour drawn around a page in the paged modes
PAGE_GAP = 16       # black gutter between the two halves of a double spread
DEFAULTS = {"mode": MODES[0], "dl_delay": 1.0, "dl_order": "Oldest first",
            "dl_dir": os.path.join(BASE, "downloads"), "nsfw": True,
            "paged_guides": True, "paper": "Graphite matte",
            "reader_paper": "Graphite matte",
            "show_history": True, "start_fullscreen": True, "card_genres": True,
            "update_auto": True}

APP_VERSION = "1.4.1"
REPO_URL = "https://github.com/sabljarevic0314/Sablja-Manga-Reader"
GITHUB_API = "https://api.github.com/repos/sabljarevic0314/Sablja-Manga-Reader/releases/latest"
UPDATE_ASSET = "SabljaReader-Setup.exe"
