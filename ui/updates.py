"""Update check and install dialog (logic lives in updater.py). Checks once a day on start when
Settings allows it; Settings → Updates has a manual check. The installed copy downloads the installer,
verifies it, backs up db.json and closes so the installer can replace the exe."""

import subprocess
import sys
import time
import webbrowser

import flet as ft

from config import APP_VERSION, DATA, REPO_URL
from sources import bg
from storage import S, backup_db, load_update_state, log_error, save_update_state
from updater import download_release_asset, fetch_latest_release, running_installed, version_key

from .core import muted


class Updates:
    def __init__(self, app):
        self.app = app
        self.busy = False
        self.status = muted("", 12)              # shown in Settings → Updates

    def say(self, text):
        self.status.value = text
        self.app.pump.mark()

    def check(self, manual=False):
        """Ask GitHub for the latest release. Manual checks always run; automatic ones once a day."""
        if self.busy:
            return
        if not manual:
            if not S("update_auto"):
                return
            if time.time() - float(load_update_state().get("checked") or 0) < 86400:
                return
        self.busy = True
        if manual:
            self.say("Checking GitHub…")
        bg(fetch_latest_release, lambda info, err: self.got(manual, info, err))

    def got(self, manual, info, err):
        self.busy = False
        state = load_update_state()
        state["checked"] = time.time()
        save_update_state(state)
        tag = str((info or {}).get("tag") or "").strip()
        if err or not tag:
            if manual:
                self.say(f"Update check failed: {str(err or 'no release found')[:110]}")
            return
        if version_key(tag) <= version_key(APP_VERSION):
            if manual:
                self.say(f"You're up to date (version {APP_VERSION}).")
            return
        if not manual and state.get("skip") == tag:
            return
        self.say(f"Version {tag.lstrip('vV')} is available.")
        self.dialog(info)

    def open_page(self, info=None):
        try:
            webbrowser.open(str((info or {}).get("page") or f"{REPO_URL}/releases/latest"))
        except Exception as ex:
            self.say(f"Couldn't open a browser: {str(ex)[:80]}")

    def dialog(self, info):
        tag = str(info.get("tag") or "").strip()
        page = self.app.page
        can_install = running_installed() and bool((info.get("asset") or {}).get("browser_download_url"))
        if can_install:
            note = (f"Your library, progress, cache and downloads stay in {DATA}. "
                    "db.json is backed up to data\\backups before the installer runs.")
        elif not getattr(sys, "frozen", False):
            note = f"This is a source checkout, so the updater only opens the release page. Data: {DATA}"
        elif not running_installed():
            note = f"This is a portable copy, so download the installer from the release page. Data: {DATA}"
        else:
            note = "The release has no installer attached; open the release page to download it."

        def later(e=None):
            state = load_update_state()
            state["skip"] = tag
            save_update_state(state)
            page.pop_dialog()
            self.say("Update skipped. Check again any time.")

        def release(e=None):
            page.pop_dialog()
            self.open_page(info)

        def install(e=None):
            page.pop_dialog()
            self.confirm(info)

        notes = (info.get("notes") or "").strip() or "See the release page for what changed."
        acts = [ft.TextButton("Later", on_click=later)]
        if can_install:
            acts += [ft.TextButton("Release page", on_click=release),
                     ft.FilledButton("Download & install", on_click=install)]
        else:
            acts += [ft.FilledButton("Open release page", on_click=release)]
        page.show_dialog(ft.AlertDialog(
            title=ft.Text(f"Version {tag.lstrip('vV')} is available"),
            content=ft.Column([muted(f"You have {APP_VERSION}."),
                               ft.Container(ft.Column([ft.Text(notes[:3000], size=12, selectable=True)],
                                                      scroll=ft.ScrollMode.AUTO),
                                            height=200, padding=10, border_radius=8,
                                            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)),
                               muted(note, 12)], tight=True, width=520, spacing=10),
            actions=acts))

    def confirm(self, info):
        page = self.app.page
        tag = str(info.get("tag") or "").strip().lstrip("vV")

        def go(e=None):
            page.pop_dialog()
            self.say("Downloading the update…")
            bg(lambda: download_release_asset(info), self.downloaded)

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Install update"),
            content=ft.Text(f"Download version {tag} and run the installer now?\n\nYour library and progress stay "
                            f"in {DATA}, and db.json is backed up first. Sablja Manga Reader App closes while the "
                            "installer runs."),
            actions=[ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                     ft.FilledButton("Install", on_click=go)]))

    def downloaded(self, path, err):
        if err or not path:
            self.say(f"Update download failed: {str(err or 'no file')[:110]}")
            self.app.toast("Couldn't download the update", error=True)
            return
        backup_db()
        try:
            # Started through a short-lived cmd so the installer isn't in this app's process tree:
            # it tree-kills SabljaMangaReaderApp.exe (/T) and must never take itself down with it.
            subprocess.Popen(["cmd", "/c", "start", "", path], creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as ex:
            log_error("start installer", ex)
            self.say(f"Couldn't start the installer: {str(ex)[:100]} (file: {path})")
            return
        self.say("Installer started; closing…")
        self.app.page.run_task(self.app.quit, 0.9)
