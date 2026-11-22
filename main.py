"""Sablja Reader (Flet UI) - entry point.

Run:  .venv\\Scripts\\python main.py
"""

import threading

import flet as ft

from storage import prune_cache
from ui.app import main

if __name__ == "__main__":
    threading.Thread(target=prune_cache, daemon=True).start()   # cache trim never blocks the UI
    ft.run(main, assets_dir="assets")
