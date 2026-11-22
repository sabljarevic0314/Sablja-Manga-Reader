"""In-app updates from this project's GitHub releases (no UI here; ui/updates.py shows it).

Only the copy NSIS installed (registered in HKCU\\Software\\SabljaReader) installs updates itself; a
source checkout or a portable exe just gets the release page.
"""

import hashlib
import os
import re
import sys
import tempfile

import requests

from config import APP_VERSION, BASE, GITHUB_API, REPO_URL, UPDATE_ASSET


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
        # Never run an installer we could not verify: GitHub publishes a sha256 digest for
        # every release asset, so a missing one means something is off.
        digest = str(asset.get("digest") or "")
        if not digest.startswith("sha256:"):
            raise RuntimeError("the release has no checksum; download it manually from GitHub")
        if h.hexdigest() != digest.split(":", 1)[1].lower():
            raise RuntimeError("download checksum does not match the release")
        os.replace(part, dest)
    except Exception:
        try:
            os.remove(part)
        except Exception:
            pass
        raise
    return dest
