"""Scrapers, local .cbz library helpers, listing cache and the image/page workers."""

import html
import json
import os
import queue
import re
import threading
import time
import zipfile
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote_plus, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps

from config import IMG_ATTRS, MD_API, PAGE_SIZE, SRC_FILE, UA
from storage import DB, S, cache_path, dl_records, log_error, pkey, safe

try:  # real Chrome/Firefox TLS fingerprint (bypasses many 403s)
    from curl_cffi import requests as cffi
except Exception:
    cffi = None

def manga_dl_dir(m):
    src = SOURCES.get(m["source"])
    return os.path.join(S("dl_dir"), safe(src.name if src else m["source"]), safe(m["title"]))


def scan_dl_dir(m):
    """Files on disk, keyed by chapter index (from the '0001 - Title.cbz' name). Survives a lost db."""
    out = {}
    d = manga_dl_dir(m)
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            mt = re.match(r"(\d+)\s*-\s*(.*)\.cbz$", fn, re.I)
            if mt:
                out[int(mt.group(1)) - 1] = os.path.join(d, fn)
    return out


def local_chapters(m):
    """{chapter index: absolute .cbz path} - db records first, disk scan as a fallback."""
    out = scan_dl_dir(m)
    for r in dl_records(m):
        p = r.get("path")
        if p and os.path.exists(p):
            out[r.get("i")] = p
    return out


def dl_record(m, i, ch=None):
    recs = dl_records(m)
    if ch:
        u = ch.get("url")
        for r in recs:
            if u and r.get("ch", {}).get("url") == u:
                return r
    return next((r for r in recs if r.get("i") == i), None)


def source_by_name(name):
    return next((s for s in SOURCES.values() if s.name == name), None)


def hidden_ids():
    """Source ids the user switched off in Settings."""
    return set(DB["set"].get("hidden") or [])


def source_hidden(sid):
    return sid in hidden_ids()


def get_rating(m):
    """{'score': 1-10, 'note': str, ...} for a manga, or None."""
    return DB["ratings"].get(pkey(m))


def source_label(m):
    """Human name of a manga's source (falls back to the id stored in a disk folder)."""
    src = SOURCES.get(m.get("source"))
    return src.name if src else (m.get("name") or m.get("source") or "Local")


def dl_folder_for(m):
    return os.path.join(S("dl_dir"), safe(source_label(m)), safe(m.get("title", "untitled")))


def disk_chapters(m):
    """{chapter index: .cbz path} straight from the download folder - no db required."""
    out, d = {}, dl_folder_for(m)
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            mt = re.match(r"(\d+)\s*-\s*(.*)\.cbz$", fn, re.I)
            if mt:
                out[int(mt.group(1)) - 1] = os.path.join(d, fn)
    return out


def local_chapters_any(m):
    """local_chapters, but also works for a manga that was never bookmarked (no url/db key)."""
    out = local_chapters(m)
    return out or disk_chapters(m)


def local_path(m, i, ch=None):
    """The .cbz for chapter index i, whether it is in the db index or only on disk."""
    r = dl_record(m, i, ch)
    if r and r.get("path") and os.path.exists(r["path"]):
        return r["path"]
    p = disk_chapters(m).get(i)
    return p if p and os.path.exists(p) else None


def downloaded_manga():
    """Every manga you have .cbz files for - bookmarked or not (index first, then a disk sweep)."""
    groups = {}
    for r in DB["downloads"]:
        m = r.get("m") or {}
        p = r.get("path") or ""
        if not (m.get("title") and p and os.path.exists(p)):
            continue
        e = groups.setdefault((source_label(m), m["title"]),
                              {"source": m.get("source", ""), "url": m.get("url", ""), "title": m["title"],
                               "cover": m.get("cover", ""), "name": source_label(m)})
        if not e["cover"]:
            e["cover"] = m.get("cover", "")
    root, titles = S("dl_dir"), {t for _, t in groups}
    if os.path.isdir(root):
        for sname in sorted(os.listdir(root)):
            sdir = os.path.join(root, sname)
            if not os.path.isdir(sdir):
                continue
            for title in sorted(os.listdir(sdir)):
                tdir = os.path.join(sdir, title)
                if (sname, title) in groups or title in titles or not os.path.isdir(tdir):
                    continue
                try:
                    if not any(f.lower().endswith(".cbz") for f in os.listdir(tdir)):
                        continue
                except OSError:
                    continue
                src = source_by_name(sname)
                groups[(sname, title)] = {"source": src.id if src else "", "url": "", "title": title,
                                          "cover": "", "name": sname}
    return list(groups.values())


class _Resp:
    __slots__ = ("content",)

    def __init__(self, content):
        self.content = content


class LocalZip:
    """Serves page bytes straight from a downloaded .cbz so the reader works offline."""
    name = "Local"
    nsfw = False

    def get(self, url):
        _, path, member = url.split("|", 2)
        with zipfile.ZipFile(path) as z:
            return _Resp(z.read(member))


LOCAL = LocalZip()


def cbz_pages(path):
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
    return [f"cbz|{path}|{n}" for n in sorted(names)]

# ---------------- sources ----------------
def pick(el, sel):
    return el if not sel or sel == "self" else el.select_one(sel)


def txt(el):
    if el is not None and el.name == "meta":
        return str(el.get("content") or "").strip()
    return el.get_text(" ", strip=True) if el else ""


def own_text(el):
    """Only the element's own text nodes (skips <small>, <a class=label>, … children)."""
    if el is None:
        return ""
    return " ".join(str(x).strip() for x in el.find_all(string=True, recursive=False)).strip()


def attr(el, names):
    if el is None:
        return ""
    if el.name == "meta":
        return (el.get("content") or "").strip()
    for n in names:
        v = el.get(n)
        if v and not v.startswith("data:"):
            return v.strip().split(" ")[0] if n == "srcset" else v.strip()
    return ""


def href(el):
    if el is None:
        return ""
    return el.get("href") or (el.find("a").get("href") if el.find("a") else "") or ""


def _js_token(n, a):
    """The 'e(c)' token generator from Dean Edwards' JS packer, in Python."""
    if n >= a:
        return _js_token(n // a, a) + _js_token(n % a, a)
    return chr(n + 29) if n > 35 else "0123456789abcdefghijklmnopqrstuvwxyz"[n]


def _js_unpack(text):
    """Unpack the eval(function(p,a,c,k,e,d){…}) payload FanFox's chapter AJAX returns.

    Returns the text unchanged when it is not packed, so callers can just regex the result.
    """
    m = re.search(r"\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'", text or "", re.S)
    if not m:
        return text or ""
    p, a, c, k = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4).split("|")
    p = p.replace("\\'", "'").replace("\\\\", "\\")
    for i in range(c - 1, -1, -1):
        if i < len(k) and k[i]:
            p = re.sub(r"\b" + re.escape(_js_token(i, a)) + r"\b", lambda _m, v=k[i]: v, p)
    return p


class Source:
    def __init__(self, d):
        self.d, self.id, self.name = d, d["id"], d["name"]
        self.api = d.get("api")
        self.base = d.get("base_url", "").rstrip("/")
        self.nsfw = bool(d.get("nsfw"))
        self._tl = threading.local()
        self._genres = None
        # Per-host request pacing. A handful of cover lookups used to fire dozens of
        # requests at once and some sites answered with HTTP 429; this keeps a polite
        # gap between requests to the same host without slowing down CDN images.
        self._rl_lock = threading.Lock()
        self._rl: dict[str, tuple[float, float]] = {}

    # ---- http ----
    def _session(self):
        s = getattr(self._tl, "s", None)
        if s is None:
            s = cffi.Session(impersonate=self.d.get("impersonate", "chrome124")) if cffi else requests.Session()
            self._tl.s = s
        return s

    @staticmethod
    def _host(url):
        try:
            return urlsplit(url).netloc.lower()
        except Exception:
            return ""

    def _throttle(self, host, gap):
        with self._rl_lock:
            nxt, cool = self._rl.get(host, (0.0, 0.0))
            now = time.monotonic()
            wait = max(nxt, cool) - now
            self._rl[host] = (max(now, nxt) + gap, cool)
        if wait > 0:
            time.sleep(min(wait, 15.0))

    def _cool(self, host, seconds):
        with self._rl_lock:
            nxt, cool = self._rl.get(host, (0.0, 0.0))
            self._rl[host] = (nxt, max(cool, time.monotonic() + seconds))

    def get(self, url, referer=None):
        h = dict(UA)
        h["Referer"] = referer or (self.base + "/")
        h.update(self.d.get("headers", {}))
        host, last = self._host(url), None
        image = bool(re.search(r"\.(?:jpe?g|png|webp|gif|avif)(?:\?|$)", url, re.I))
        gap = 0.02 if image else float(self.d.get("request_delay", 0.05))
        for attempt in range(3):
            self._throttle(host, gap)
            try:
                r = self._session().get(url, headers=h, timeout=25)
            except Exception as e:
                last = e
                log_error("Source.get", e)
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise
            if r.status_code == 429:
                # Honour Retry-After when the site sends one, but never stall a
                # worker for minutes. Other requests to the same host wait too.
                try:
                    wait = float(r.headers.get("Retry-After") or 0)
                except Exception:
                    wait = 0.0
                wait = max(wait, 2.0 * (attempt + 1))
                self._cool(host, wait)
                last = requests.HTTPError(f"429 Too Many Requests from {host}", response=r)
                if attempt < 2:
                    time.sleep(min(wait, 8.0))
                    continue
            elif r.status_code in (500, 502, 503, 504) and attempt < 2:
                last = requests.HTTPError(f"{r.status_code} from {host}", response=r)
                time.sleep(0.6 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        raise last or RuntimeError("request failed")


    def soup(self, url):
        text = self.get(url).text
        try:
            return BeautifulSoup(text, "lxml")
        except Exception:            # lxml missing: the stdlib parser still works, only slower
            return BeautifulSoup(text, "html.parser")

    def abs(self, u):
        return urljoin(self.base + "/", u) if u else ""

    # ---- capabilities ----
    def kinds(self):
        if self.api in ("mangadex", "webtoons"):
            return ["popular", "latest"]
        return [k for k in ("popular", "latest") if k in self.d]

    def can_search(self):
        return bool(self.api) or "search" in self.d

    def genres(self):
        """[(label, value)] or []. Called from a worker thread."""
        if self.api == "mangadex":
            if self._genres is None:
                j = requests.get(MD_API + "/manga/tag", headers=UA, timeout=25).json()
                tags = [(t["attributes"]["name"].get("en", "?"), t["id"]) for t in j["data"]
                        if t["attributes"].get("group") in ("genre", "theme")]
                self._genres = sorted(tags)
            return self._genres
        if self.api == "webtoons":
            return [("Trending", "trending"), ("Popular", "popular"),
                    ("Originals", "originals"), ("Canvas", "canvas")]
        return [tuple(g) for g in self.d.get("genres", [])] if "genre" in self.d else []

    def _tag_list(self, scope, sels=None):
        """First selector group that yields text becomes the genre/category list.

        sources.json `tags` entries are selectors for the details page; a listing can also
        carry its own `tags` selectors when the card itself shows genres.
        """
        if sels is None:
            sels = self.d.get("tags") or []
        if isinstance(sels, str):
            sels = [sels]
        for sel in sels:
            out = []
            try:
                els = scope.select(sel)
            except Exception:
                continue
            for e in els:
                t = re.sub(r"^#+\s*", "", txt(e)).strip()
                if t and t not in out:
                    out.append(t)
            if out:
                return out[:20]
        return []

    # ---- listing ----
    def listing(self, kind, page=1, query="", genre=""):
        if self.api == "mangadex":
            return self._md_listing(kind, page, query, genre)
        if self.api == "webtoons":
            return self._wt_listing(kind, page, query, genre)
        key = "genre" if genre and kind != "search" else kind
        c = self.d.get(key)
        if not c:
            return []
        if key in ("latest", "genre"):
            c = {**self.d.get("popular", {}), **c}
        if c.get("single_page") and page > 1:
            return []
        url = self.abs(c["url"].format(page=page, query=quote_plus(query), offset=(page - 1) * PAGE_SIZE, genre=genre))
        ck = (self.id, key, page, query, genre, url)
        hit = listing_cache_get(ck)
        if hit is not None:
            return hit
        out, seen = [], set()
        for it in self.soup(url).select(c["item"]):
            t = pick(it, c.get("title"))
            link = pick(it, c.get("link") or c.get("title"))
            title = str(txt(t) or (t.get("title", "") if t else ""))
            # Listing markup often appends a rank/volume badge inside the link. The
            # link's title attribute is the clean name ("One Piece", not "One Piece 1").
            if c.get("title_attr") and t is not None and t.get(c["title_attr"]):
                title = str(t.get(c["title_attr"]))
            elif title.endswith(("...", "…")) and t is not None and t.get("title"):
                title = str(t.get("title"))
            u = self.abs(href(link))
            if not title or not u or u in seen:
                continue
            seen.add(u)
            cover = self.abs(attr(pick(it, c.get("cover", "img")), c.get("cover_attr", IMG_ATTRS)))
            # Some sites emit a broken local cover path in list markup while the real
            # image lives on their CDN. Rewrites keep card downloads from retrying 404s.
            for pat, rep in c.get("cover_rewrite", []):
                cover = re.sub(pat, rep, cover)
            out.append({"title": title, "url": u, "cover": cover, "source": self.id,
                        "genres": self._tag_list(it, c.get("tags"))})
        listing_cache_put(ck, out)
        return out

    def _chapters(self, soup, c):
        chs, seen = [], set()
        if not c.get("item"):
            return chs
        pat = re.compile(c["title_pattern"]) if c.get("title_pattern") else None
        for it in soup.select(c["item"]):
            u = self.abs(href(it))
            if not u or u in seen:
                continue
            seen.add(u)
            t = txt(it) or it.get("title", "Chapter")
            if pat:
                m = pat.search(t)
                if m and m.group(1).strip():
                    vals = [m.group(0)] + [g.strip() if g else "" for g in m.groups()]
                    t = c.get("title_format", "{1}").format(*vals)
            chs.append({"title": t, "url": u})
        return chs

    def details(self, url):
        if self.api == "mangadex":
            return self._md_details(url)
        if self.api == "webtoons":
            return self._wt_details(url)
        d, soup = self.d.get("details", {}), self.soup(url)
        sel = lambda k: soup.select_one(d[k]) if d.get(k) else None
        cover = self.abs(attr(sel("cover"), d.get("cover_attr", IMG_ATTRS))) if d.get("cover") else ""
        title = own_text(sel("title")) if d.get("title_direct_text") else txt(sel("title"))
        if d.get("title_pattern"):
            mt = re.search(d["title_pattern"], title)
            if mt and mt.group(1).strip():
                title = mt.group(1).strip()
        description = txt(sel("description"))
        genres = self._tag_list(soup)
        c = self.d.get("chapters") or {}
        # The chapter list often lives on a second page. Fetch it while the details
        # page is still being parsed instead of waiting for one request after another.
        fut = None
        if c.get("list_path"):
            fut = DETAIL_POOL.submit(self.soup, url.rstrip("/").rsplit("/", 1)[0] + c["list_path"])
        chs = self._chapters(soup, c)
        if fut is not None:
            try:
                chs = self._chapters(fut.result(), c) or chs
            except Exception:
                pass
        if c.get("newest_first", True):
            chs.reverse()
        return {"title": title, "description": description, "cover": cover, "chapters": chs, "genres": genres}

    def pages(self, url):
        if self.api == "mangadex":
            return self._md_pages(url)
        if self.api == "webtoons":
            return self._wt_pages(url)
        if self.api == "fanfox":
            return self._ff_pages(url)
        p = self.d["pages"]
        if p.get("url_suffix"):
            url = url.rstrip("/") + p["url_suffix"]
        out, seen = [], set()
        if p.get("script_regex"):  # image list stored in a <script> array
            m = re.search(p["script_regex"], self.get(url).text, re.S)
            for u in re.findall(r"""['"](https?://[^'"]+)['"]""", m.group(1)) if m else []:
                if u not in seen:
                    seen.add(u)
                    out.append(u)
            return out
        if p.get("page_urls"):  # one image per page, page URLs listed in a <select>
            urls = []
            for o in self.soup(url).select(p["page_urls"]):
                u = self.abs(o.get("value") or "")
                if u and u not in urls:
                    urls.append(u)

            def one(pu):
                found = []
                for i in self.soup(pu).select(p["image"]):
                    u = self.abs(attr(i, p.get("attr", IMG_ATTRS)))
                    if u and u not in found:
                        found.append(u)
                return found

            if urls:
                with ThreadPoolExecutor(max_workers=min(6, len(urls))) as ex:
                    for part in ex.map(one, urls):
                        for u in part:
                            if u not in seen:
                                seen.add(u)
                                out.append(u)
            return out
        for i in self.soup(url).select(p["image"]):
            u = self.abs(attr(i, p.get("attr", IMG_ATTRS)))
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out

    # ---- MangaDex (official API, no scraping) ----
    def _md(self, path, **params):
        r = requests.get(MD_API + path, params=params, headers=UA, timeout=25)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _md_title(a):
        t = a.get("title") or {}
        if t.get("en"):
            return t["en"]
        for alt in a.get("altTitles") or []:
            if isinstance(alt, dict) and alt.get("en"):
                return alt["en"]
        for key in ("ja-ro", "ko-ro", "zh-ro", "ja", "ko", "zh", "zh-hk"):
            if t.get(key):
                return t[key]
        return next(iter(t.values()), "Untitled")

    @staticmethod
    def _md_tags(a):
        out = []
        for t in a.get("tags") or []:
            ta = t.get("attributes") or {}
            if ta.get("group") not in ("genre", "theme"):
                continue
            name = (ta.get("name") or {}).get("en") or next(iter((ta.get("name") or {}).values()), "")
            if name and name not in out:
                out.append(name)
        return out

    def _md_cover(self, x, size=".256.jpg"):
        for r in x.get("relationships", []):
            if r["type"] == "cover_art" and r.get("attributes"):
                return f"https://uploads.mangadex.org/covers/{x['id']}/{r['attributes']['fileName']}{size}"
        return ""

    def _md_listing(self, kind, page, query, genre):
        p = {"limit": PAGE_SIZE, "offset": (page - 1) * PAGE_SIZE, "includes[]": ["cover_art"],
             "contentRating[]": self._md_ratings(), "hasAvailableChapters": "true",
             "availableTranslatedLanguage[]": ["en"]}
        if kind == "search" and query:
            p["title"] = query
            p["order[relevance]"] = "desc"
        elif kind == "latest":
            p["order[latestUploadedChapter]"] = "desc"
        else:
            p["order[followedCount]"] = "desc"
        if genre:
            p["includedTags[]"] = [genre]
        return [{"title": self._md_title(x["attributes"]), "url": f"https://mangadex.org/title/{x['id']}",
                 "cover": self._md_cover(x), "source": self.id,
                 "genres": self._md_tags(x["attributes"])} for x in self._md("/manga", **p)["data"]]

    def _md_ratings(self):
        return ["safe", "suggestive", "erotica", "pornographic"] if S("nsfw") else ["safe", "suggestive"]

    def _md_feed(self, mid, langs):
        """One pass over a manga's chapter feed. langs=None means 'every language'."""
        found: dict[Any, tuple[int, dict[str, Any]]] = {}
        off = 0
        while True:
            p = {"order[chapter]": "asc", "limit": 500, "offset": off, "includeExternalUrl": 0,
                 "contentRating[]": self._md_ratings()}
            if langs:
                p["translatedLanguage[]"] = langs
            j = self._md(f"/manga/{mid}/feed", **p)
            for c in j["data"]:
                ca = c["attributes"]
                if not ca.get("pages") or ca.get("externalUrl"):
                    continue
                num = ca.get("chapter")
                key = num if num is not None else (None, ca.get("translatedLanguage"), c["id"])
                title = f"Chapter {num}" if num not in (None, "") else "Oneshot"
                if ca.get("title"):
                    title += f" \u2014 {ca['title']}"
                pages = int(ca.get("pages") or 0)
                prev = found.get(key)
                # Several groups can upload the same chapter number. Keep the version
                # with the most pages, so a split/partial upload cannot look incomplete.
                if prev is None or pages > prev[0]:
                    found[key] = (pages, {"title": title, "url": f"https://mangadex.org/chapter/{c['id']}"})
            off += 500
            if off >= j.get("total", 0):
                break
        return [ch for _pages, ch in found.values()]

    def _md_details(self, url):
        mid = url.rstrip("/").split("/")[-1]
        x = self._md(f"/manga/{mid}", **{"includes[]": ["cover_art"]})["data"]
        a = x["attributes"]
        chs = self._md_feed(mid, ["en"])
        desc = (a.get("description") or {}).get("en", "")
        if not chs:
            desc = (desc + "\n\nNo English chapters are available on MangaDex for this title. "
                           "Licensed releases that only exist as external links are skipped.").strip()
        return {"title": self._md_title(a), "description": desc,
                "cover": self._md_cover(x, ".512.jpg"), "chapters": chs, "genres": self._md_tags(a)}

    def _md_pages(self, url):
        j = self._md(f"/at-home/server/{url.rstrip('/').split('/')[-1]}")
        ch = j["chapter"]
        files, folder = (ch["dataSaver"], "data-saver") if ch.get("dataSaver") else (ch["data"], "data")
        return [f"{j['baseUrl']}/{folder}/{ch['hash']}/{f}" for f in files]

    # ---- WEBTOON (official site; listing/viewer are HTML, episodes come from the mobile API) ----
    WT_RANKS = ("trending", "popular", "originals", "canvas")

    @staticmethod
    def _wt_day():
        return ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[time.localtime().tm_wday]

    def _wt_listing(self, kind, page=1, query="", genre=""):
        if genre in self.WT_RANKS:
            if page > 1:
                return []
            url = f"{self.base}/en/ranking/{genre}"
        elif kind == "search":
            if page > 1:
                return []
            url = f"{self.base}/en/search?keyword={quote_plus(query)}"
        elif kind == "latest":
            if page > 1:
                return []
            url = f"{self.base}/en/originals/{self._wt_day()}?sortOrder=UPDATE"
        else:
            if page > len(self.WT_RANKS):
                return []
            url = f"{self.base}/en/ranking/{self.WT_RANKS[page - 1]}"
        out, seen = [], set()
        for a in self.soup(url).select(".webtoon_list li a"):
            u = self.abs(a.get("href"))
            if not u or u in seen:
                continue
            seen.add(u)
            t = a.select_one(".title") or a.select_one(".subj")
            title = txt(t) or a.get("title", "")
            if not title:
                continue
            img = a.select_one("img")
            g = a.select_one(".info_text .genre, .info_text_inner .genre")
            out.append({"title": title, "url": u,
                        "cover": attr(img, ["data-src", "src"]) if img else "", "source": self.id,
                        "genres": [txt(g)] if g and txt(g) else []})
        return out

    def _wt_details(self, url):
        soup = self.soup(url)
        t = soup.select_one("h1.subj") or soup.select_one("h3.subj") or soup.select_one("h1")
        desc = soup.select_one("#_asideDetail p.summary") or soup.select_one("p.summary")
        cov = soup.select_one("meta[property='og:image']")
        return {"title": txt(t), "description": txt(desc), "cover": attr(cov, []) if cov else "",
                "chapters": self._wt_chapters(url), "genres": self._tag_list(soup)}

    def _wt_chapters(self, url):
        m = re.search(r"title_no=(\d+)", url or "")
        if not m:
            return []
        kind = "canvas" if "/canvas/" in url else "webtoon"
        api = f"https://m.webtoons.com/api/v1/{kind}/{m.group(1)}/episodes?pageSize=99999"
        if kind == "canvas":
            api += "&readingLanguageCode=en"
        j = self.get(api, referer="https://m.webtoons.com/").json()
        eps = ((j.get("result") or {}).get("episodeList")) or []
        chs = []
        for e in eps:
            u = e.get("viewerLink") or ""
            if not u:
                continue
            chs.append({"title": html.unescape(e.get("episodeTitle") or "Episode"), "url": self.abs(u)})
        chs.reverse()  # the API returns newest first
        return chs

    def _wt_pages(self, url):
        out, seen = [], set()
        for i in self.soup(url).select("div#_imageList img, #_imageList img"):
            u = attr(i, ["data-url", "data-src", "src"])
            if u and u not in seen:
                seen.add(u)
                out.append(self.abs(u))
        return out

    # ---- FanFox (reader pages are handed out one-by-one by a packed-JS AJAX endpoint) ----
    def _ff_pages(self, url):
        html = self.get(url).text
        mc = re.search(r"var\s+chapterid\s*=\s*(\d+)", html)
        mn = re.search(r"var\s+imagecount\s*=\s*(\d+)", html)
        if not mc:
            return []
        cid = mc.group(1)
        total = int(mn.group(1)) if mn else 0
        base = url.rsplit("/", 1)[0]
        ref = url

        def one(i):
            try:
                raw = _js_unpack(self.get(f"{base}/chapterfun.ashx?cid={cid}&page={i}", referer=ref).text)
                pix = re.search(r'var\s+pix\s*=\s*"([^"]+)"', raw)
                img = re.search(r'"(/[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', raw, re.I)
                if not (pix and img):
                    return ""
                host = pix.group(1).replace("\\/", "/")
                if host.startswith("//"):
                    host = "https:" + host
                return host + img.group(1).replace("\\/", "/")
            except Exception:
                return ""

        if not total:
            return []
        # FanFox needs one request per page; a few in parallel keeps a 20-page chapter quick.
        with ThreadPoolExecutor(max_workers=4) as ex:
            urls = list(ex.map(one, range(1, total + 1)))
        return [u for u in urls if u]


SOURCES = {}
# Listing pages are reused when the user bounces between sources. Without this, every
# source switch re-downloaded the same HTML and rebuilt the same 20-30 cards.
LIST_CACHE: "OrderedDict[tuple[Any, ...], tuple[float, list[dict[str, Any]]]]" = OrderedDict()
LIST_LOCK = threading.Lock()
LIST_TTL = 180.0
LIST_MAX = 240


def listing_cache_get(key):
    now = time.time()
    with LIST_LOCK:
        hit = LIST_CACHE.get(key)
        if hit is None:
            return None
        ts, items = hit
        if now - ts > LIST_TTL:
            LIST_CACHE.pop(key, None)
            return None
        LIST_CACHE.move_to_end(key)
        return [{**x, "genres": list(x.get("genres") or [])} for x in items]


def listing_cache_put(key, items):
    with LIST_LOCK:
        LIST_CACHE[key] = (time.time(), [dict(x) for x in items])
        LIST_CACHE.move_to_end(key)
        while len(LIST_CACHE) > LIST_MAX:
            LIST_CACHE.popitem(last=False)


def rebuild_sources():
    SOURCES.clear()
    with LIST_LOCK:
        LIST_CACHE.clear()
    if not os.path.exists(SRC_FILE):
        with open(SRC_FILE, "w", encoding="utf-8") as f:
            json.dump({"sources": []}, f, indent=2)
    try:
        with open(SRC_FILE, encoding="utf-8") as f:
            data = json.load(f).get("sources", [])
    except Exception:
        data = []
    # 18+ sources always sort after the regular ones, regardless of JSON order.
    for d in sorted(data, key=lambda x: bool(x.get("nsfw"))):
        try:
            SOURCES[d["id"]] = Source(d)
        except Exception:
            pass

# ---------------- background work ----------------
Q = queue.Queue()
NET_POOL = ThreadPoolExecutor(4)
DETAIL_POOL = ThreadPoolExecutor(4)   # details page + its separate chapter-list page, in parallel
IMG_POOL = ThreadPoolExecutor(12)
PAGE_POOL = ThreadPoolExecutor(6)
# Decoded card thumbnails (memory only). Without this every section change decoded the
# same covers from disk again, which is what made scrolling and menu switches feel rough.
THUMB_CACHE: "OrderedDict[tuple[Any, ...], Image.Image]" = OrderedDict()
THUMB_LOCK = threading.Lock()
THUMB_MAX = 600

def bg(fn, cb, pool=None):
    def w():
        try:
            res = (fn(), None)
        except Exception as e:
            res = (None, e)
        Q.put((cb, res))
    (pool or NET_POOL).submit(w)

def fetch_pages(src, url):
    """Fetch a chapter's page list. Source.get already retries 429/5xx, so one extra
    attempt here is enough - stacking two long retry loops made failures feel frozen."""
    last = None
    for attempt in range(2):
        try:
            pages = src.pages(url)
            if pages:
                return pages
        except Exception as e:
            last = e
        if attempt < 1:
            time.sleep(0.6)
    if last:
        raise last
    return []


def load_img(src, url, cb, size=None, width=None, height=None, pool=None, alive=None):
    """Download (cached) + decode + resize in a worker; cb(PIL image or None) runs on the UI thread.

    Returns True when the work was actually queued - callers count in-flight jobs from this, so a
    request that cannot be made never leaves a slot occupied forever.
    """
    if not src or not url:
        return False
    ck = (url, width, height, tuple(size) if size else None)
    cacheable = bool(size)

    def cached_image():
        if not cacheable:
            return None
        with THUMB_LOCK:
            im = THUMB_CACHE.get(ck)
            if im is not None:
                THUMB_CACHE.move_to_end(ck)
            return im

    def remember(im):
        if not cacheable or im is None:
            return
        with THUMB_LOCK:
            THUMB_CACHE[ck] = im
            THUMB_CACHE.move_to_end(ck)
            while len(THUMB_CACHE) > THUMB_MAX:
                THUMB_CACHE.popitem(last=False)

    def w():
        if alive and not alive():
            return
        hit = cached_image()
        if hit is not None:
            Q.put((lambda r, e: cb(r), (hit, None)))
            return
        im = None
        try:
            p = cache_path(url)
            if not os.path.exists(p):
                data, last = None, None
                for attempt in range(2):
                    if alive and not alive():
                        return
                    try:
                        data = src.get(url).content
                        if data:
                            break
                        last = RuntimeError("empty image response")
                    except Exception as e:
                        last = e
                        resp = getattr(e, "response", None)
                        if resp is not None and 400 <= getattr(resp, "status_code", 0) < 500:
                            break  # 404/403 will not fix itself; don't stall the cover queue
                    if attempt < 1:
                        time.sleep(0.35)
                if not data:
                    raise last or RuntimeError("image download failed")
                tmp = f"{p}.{threading.get_ident()}.part"  # two pages of the same url must not share a temp file
                try:
                    with open(tmp, "wb") as f:
                        f.write(data)
                    os.replace(tmp, p)
                finally:
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
            if alive and not alive():
                return
            im = Image.open(p)
            if width:
                th = height or max(1, int(im.height * width / float(im.width)))
                try:
                    im.draft("RGB", (width * 2, th * 2))
                except Exception:
                    pass
                im = im.convert("RGB")
                im = im.resize((width, th), Image.Resampling.BICUBIC)
            elif size:
                try:
                    im.draft("RGB", (size[0] * 2, size[1] * 2))
                except Exception:
                    pass
                im = ImageOps.fit(im.convert("RGB"), size)
            else:
                im = im.convert("RGB")
        except Exception as e:
            log_error("load_img", e)
            im = None
            try:  # a broken/HTML download must not sit in the cache and fail forever
                if os.path.exists(cache_path(url)):
                    os.remove(cache_path(url))
            except OSError:
                pass
        remember(im)
        Q.put((lambda r, e: cb(r), (im, None)))

    (pool or IMG_POOL).submit(w)
    return True
