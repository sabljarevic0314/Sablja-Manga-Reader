"""Download queue: one CBZ per chapter, slow and polite."""

import os
import queue
import random
import threading
import time
import zipfile

from sources import SOURCES
from storage import S, cache_path, safe

_JOB_ID = [0]


def next_job_id():
    _JOB_ID[0] += 1
    return f"{int(time.time())}-{_JOB_ID[0]}"

def dl_path(m, i, ch):
    src = SOURCES.get(m["source"])
    return os.path.join(S("dl_dir"), safe(src.name if src else m["source"]), safe(m["title"]),
                        f"{i + 1:04d} - {safe(ch['title'])}.cbz")

# ---------------- download manager (one CBZ per chapter, slow + polite) ----------------
DL_Q = queue.Queue()
JOBS = []


def _ext(b):
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[:3] == b"GIF":
        return "gif"
    return "jpg"


def run_job(job):
    src, m, ch = SOURCES[job["m"]["source"]], job["m"], job["ch"]
    job["state"] = "getting pages"
    urls = src.pages(ch["url"])
    job["total"] = len(urls)
    dest = job["path"]
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
            for i, u in enumerate(urls):
                if job["state"] == "cancelled":
                    raise InterruptedError
                job["state"] = "downloading"
                cp, data = cache_path(u), None
                if os.path.exists(cp):
                    data = open(cp, "rb").read()  # already viewed in the reader: no request, no delay
                else:
                    for attempt in range(3):
                        try:
                            data = src.get(u).content
                            break
                        except Exception as e:
                            if attempt == 2:
                                raise
                            time.sleep(15 if "429" in str(e) else 3 * (attempt + 1))
                    time.sleep(S("dl_delay") * random.uniform(0.7, 1.4))
                assert data is not None
                z.writestr(f"{i + 1:03d}.{_ext(data)}", data)
                job["done"] = i + 1
        os.replace(tmp, dest)
        job["state"] = "done"
        time.sleep(max(2.0, S("dl_delay") * 2))  # pause between chapters
    except InterruptedError:
        job["state"] = "cancelled"
        try:
            os.remove(tmp)
        except Exception:
            pass
    except Exception as e:
        job["state"] = "error: " + str(e)[:50]
        try:
            os.remove(tmp)
        except Exception:
            pass


def dl_worker():
    while True:
        job = DL_Q.get()
        if job["state"] == "cancelled":
            continue
        try:
            run_job(job)
        except Exception as e:
            job["state"] = "error: " + str(e)[:50]


threading.Thread(target=dl_worker, daemon=True).start()
