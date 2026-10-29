"""Persistent state: db.json, reading progress, update state, cache paths and error log."""

import hashlib
import json
import os
import re
import shutil
import threading
import time
import traceback
from typing import Any

from config import APP_VERSION, CACHE, DATA, DB_FILE, DEFAULTS, PAPERS, UPDATE_STATE_FILE

def load_db() -> dict[str, Any]:
    try:
        with open(DB_FILE, encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        db = {}
    for k, v in dict(bookmarks=[], progress={}, last=None, folders=[], set={}, downloads=[], ratings={},
                     meta={}).items():
        db.setdefault(k, v)
    if isinstance(db.get("set"), dict):
        db["set"].pop("headers", None)  # old per-source cookie/User-Agent overrides (feature removed)
    if not isinstance(db.get("meta"), dict):
        db["meta"] = {}
    return db


DB: dict[str, Any] = load_db()


_DB_WRITE_LOCK = threading.Lock()
_SAVE_LOCK = threading.Lock()
_SAVE_TIMER: list[threading.Timer | None] = [None]


def save_db():
    """Write atomically: a crash mid-save must never leave a truncated library behind."""
    tmp = DB_FILE + ".tmp"
    with _DB_WRITE_LOCK:                 # a debounced save must not race the closing write
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(DB, f, ensure_ascii=False)
        os.replace(tmp, DB_FILE)


def _save_db_timer():
    with _SAVE_LOCK:
        _SAVE_TIMER[0] = None
    save_db()


def save_db_soon(delay=1.5):
    """Coalesce bursts of small saves (reading progress) into one write, off the UI thread."""
    with _SAVE_LOCK:
        old = _SAVE_TIMER[0]
        if old is not None:
            old.cancel()
        t = threading.Timer(delay, _save_db_timer)
        t.daemon = True
        _SAVE_TIMER[0] = t
        t.start()


ERR_LOG = os.path.join(DATA, "errors.log")
ERR_LOG_MAX = 1024 * 1024            # ~1 MB, then the oldest half is dropped


def log_error(where, exc):
    """Append timestamp + traceback to data/errors.log (a diagnostic aid, never fatal)."""
    try:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc else ""
        entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {where}: {tb or repr(exc)}\n"
        try:
            if os.path.getsize(ERR_LOG) > ERR_LOG_MAX:
                with open(ERR_LOG, "rb") as f:
                    f.seek(ERR_LOG_MAX // 2)
                    tail = f.read()
                with open(ERR_LOG, "wb") as f:
                    f.write(tail)
        except OSError:
            pass
        with open(ERR_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass


def load_update_state() -> dict:
    """Update-check bookkeeping lives beside the library, not inside db.json."""
    try:
        with open(UPDATE_STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def save_update_state(state: dict):
    try:
        tmp = UPDATE_STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1)
        os.replace(tmp, UPDATE_STATE_FILE)
    except Exception:
        pass

def S(k) -> Any:
    v = DB["set"].get(k, DEFAULTS[k])
    if v == "Paper white":                 # renamed in 1.2 while it was still an experiment
        v = "Paper"
    if k in ("paper", "reader_paper") and v not in PAPERS:  # older builds saved invalid names
        v = DEFAULTS[k]
    return v


def pkey(m):
    return f'{m["source"]}|{m["url"]}'


def cached_genres(m):
    """Genres we already learned for this manga (from a listing or its details page)."""
    if not m.get("url"):
        return []
    e = (DB.get("meta") or {}).get(pkey(m))
    gs = e.get("genres") if isinstance(e, dict) else (e if isinstance(e, list) else [])
    return [str(g).strip() for g in (gs or []) if str(g).strip()]


def remember_genres(m, genres):
    """Cache genres in db.json so cards get labels without fetching the details page again."""
    if not m.get("url"):
        return
    gs = []
    for g in genres or []:
        g = re.sub(r"^#+\s*", "", str(g)).strip()
        if g and g not in gs:
            gs.append(g)
    if not gs or cached_genres(m) == gs[:20]:
        return
    DB.setdefault("meta", {})[pkey(m)] = {"genres": gs[:20]}
    save_db()

def safe(s):
    return re.sub(r'[\\/:*?"<>|]+', "_", s).strip(" .") or "untitled"


def cache_path(url):
    return os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest())


def prune_cache(max_bytes=1.5 * 1024 ** 3):
    """Drop the oldest cached files until the cache folder is back under `max_bytes`.

    Runs from a daemon thread at startup: a multi-GB cache makes every listing slower.
    """
    try:
        files, total = [], 0
        with os.scandir(CACHE) as it:
            for e in it:
                try:
                    if e.is_file():
                        st = e.stat()
                        files.append((st.st_mtime, st.st_size, e.path))
                        total += st.st_size
                except OSError:
                    continue
        if total <= max_bytes:
            return
        files.sort()
        for _mt, size, path in files:
            try:
                os.remove(path)
            except OSError:
                continue
            total -= size
            if total <= max_bytes:
                break
    except Exception as e:
        log_error("prune_cache", e)

def dl_records(m):
    k = pkey(m)
    return [r for r in DB["downloads"] if r.get("key") == k]

def backup_db():
    """Timestamped db.json copy in data\\backups, used before every update install."""
    try:
        bdir = os.path.join(DATA, "backups")
        os.makedirs(bdir, exist_ok=True)
        name = f"db-{time.strftime('%Y%m%d-%H%M%S')}-v{APP_VERSION}.json"
        dest = os.path.join(bdir, name)
        shutil.copy2(DB_FILE, dest)
        return dest
    except Exception as e:
        return str(e)
