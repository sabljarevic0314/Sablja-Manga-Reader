"""Reading log: what was read on which day, for the Today rings, the streak and the stats.

DB["log"] is {"YYYY-MM-DD": {"sec": seconds in the reader, "ch": chapters finished,
"pg": pages turned, "s": [series keys touched]}}. One small row per day, so a year is a few
dozen KB. Nothing here touches the UI.
"""

import datetime as _dt

from storage import DB, S, save_db_soon

ACTIVE_DAY_SEC = 60          # a day counts towards the streak after a minute of reading or one chapter


def day_key(d=None):
    return (d or _dt.date.today()).isoformat()


def day(d=None, create=False):
    log = DB.setdefault("log", {})
    k = day_key(d)
    if create:
        return log.setdefault(k, {"sec": 0, "ch": 0, "pg": 0, "s": []})
    return log.get(k) or {"sec": 0, "ch": 0, "pg": 0, "s": []}


def add(key=None, sec=0, ch=0, pg=0):
    """Record reading activity for today. key is the series key (pkey)."""
    if not (sec or ch or pg or key):
        return
    row = day(create=True)
    row["sec"] = int(row.get("sec", 0) + sec)
    row["ch"] = int(row.get("ch", 0) + ch)
    row["pg"] = int(row.get("pg", 0) + pg)
    if key and key not in row.setdefault("s", []):
        row["s"].append(key)
    if key and sec:                      # lifetime reading time per series, shown in History
        p = DB["progress"].setdefault(key, {"read": []})
        p["sec"] = int(p.get("sec", 0) + sec)
    save_db_soon()


def active(row):
    return row.get("ch", 0) >= 1 or row.get("sec", 0) >= ACTIVE_DAY_SEC


def streak(today=None):
    """(current, best) run of consecutive reading days. Today still counts as 'in progress':
    an empty today does not break yesterday's run."""
    today = today or _dt.date.today()
    log = DB.get("log") or {}
    days = sorted(_dt.date.fromisoformat(k) for k, v in log.items() if active(v))
    best = run = 0
    prev = None
    for d in days:
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, run)
        prev = d
    cur = 0
    d = today if active(day(today)) else today - _dt.timedelta(days=1)
    while active(day(d)):
        cur += 1
        d -= _dt.timedelta(days=1)
    return cur, max(best, cur)


def week(today=None):
    """The last 7 days, oldest first: [(date, row)]."""
    today = today or _dt.date.today()
    return [(today - _dt.timedelta(days=i), day(today - _dt.timedelta(days=i))) for i in range(6, -1, -1)]


def goals():
    return {"ch": max(1, int(S("goal_chapters"))), "sec": max(60, int(S("goal_minutes")) * 60)}


def pace_sec_per_chapter():
    """Your average reading time per finished chapter over the last 30 active days (None if unknown)."""
    log = DB.get("log") or {}
    rows = [log[k] for k in sorted(log)[-30:]]
    sec = sum(r.get("sec", 0) for r in rows)
    ch = sum(r.get("ch", 0) for r in rows)
    return sec / ch if ch >= 3 and sec > 0 else None


def fmt_minutes(sec):
    m = int(sec // 60)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m} min"
