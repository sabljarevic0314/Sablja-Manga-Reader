"""
Usage:  python autoprobe.py <listing-page-url>
        (or run it with no arguments and paste the URL when asked)

Does the whole probe in one go:
  1. loads the listing page and finds the repeated manga cards
  2. opens the first manga and finds its chapter links + description
  3. opens a chapter and finds the page images
Saves a short report to autoprobe_<host>.txt - paste or upload that file.
"""
import sys, re, io, collections
from urllib.parse import urljoin, urlparse
from curl_cffi import requests as cffi
from bs4 import BeautifulSoup

# Windows consoles default to cp1252 and crash on non-latin characters (e.g. "✅").
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

url = sys.argv[1] if len(sys.argv) > 1 else input("Listing page URL: ").strip()
out = []


def say(s=""):
    print(s)
    out.append(s)


def fetch(u, ref=None):
    r = cffi.get(u, impersonate="chrome124", timeout=25, headers={"Referer": ref or u})
    soup = BeautifulSoup(r.text, "html.parser")
    meta = soup.find("meta", attrs={"name": "description"})
    meta = (meta.get("content", "") if meta else "")[:160]
    for t in soup(["script", "style", "svg", "noscript", "iframe"]):
        t.decompose()
    return r, soup, meta


def sig(el):
    c = el.get("class", [])
    return el.name + ("." + ".".join(sorted(c)) if c else "") + (f"#{el['id']}" if el.get("id") else "")


def short(el, n=900):
    s = " ".join(str(el).split())
    return s if len(s) <= n else s[:n] + " ...[cut]"


def header(title, r, soup, u):
    say(f"\n##### {title}: {u}")
    say(f"status {r.status_code} | {len(r.text)} bytes | title: {soup.title.text.strip()[:80] if soup.title else 'none'}")


# ---- 1. listing ----
r, soup, _ = fetch(url)
header("LISTING", r, soup, url)
cards, first = collections.Counter(), {}
for el in soup.find_all(True):
    if el.name in ("a", "img", "html", "body", "head"):
        continue
    if el.find("a", href=True) and el.find("img"):
        s = sig(el)
        cards[s] += 1
        first.setdefault(s, el)
top = cards.most_common(3)
for s, n in top:
    say(f"{n:3d} x {s}")
if not top or top[0][1] < 3:
    say("No repeated cards found (page may be JavaScript-rendered or blocked). Stopping.")
    open("autoprobe_" + urlparse(url).netloc + ".txt", "w", encoding="utf-8").write("\n".join(out))
    sys.exit()
card = first[top[0][0]]
say("Example card:\n" + short(card))
link = card.find("a", href=True)
series_url = urljoin(url, link["href"])

# ---- 2. series page ----
r, soup, meta = fetch(series_url, url)
header("SERIES", r, soup, series_url)
h1 = soup.find("h1")
say(f"h1: {sig(h1)} -> {h1.get_text(' ', strip=True)[:80]}" if h1 else "no h1")
say(f"meta description: {meta}")
say("Description candidates:")
for el in soup.find_all(True, class_=re.compile("desc|summary|synopsis|summery", re.I))[:4] + \
          soup.find_all(True, id=re.compile("desc|summary|synopsis|noidung", re.I))[:3]:
    say(f"  {sig(el)} -> {el.get_text(' ', strip=True)[:90]}")
say("Image groups (cover candidates):")
for s, n in collections.Counter(sig(i) + " <- " + sig(i.parent) for i in soup.find_all("img")).most_common(3):
    say(f"  {n:3d} x {s}")

chs = [a for a in soup.find_all("a", href=True)
       if re.search(r"chapter|chap-|/ch-|/c/|/c\d|-c\d|episode|/read", a["href"], re.I)]
say(f"Chapter links: {len(chs)}")
if not chs:
    say("No chapter links in the HTML (loaded separately?). Stopping.")
    open("autoprobe_" + urlparse(url).netloc + ".txt", "w", encoding="utf-8").write("\n".join(out))
    sys.exit()
groups = collections.Counter(sig(a) + " <- " + sig(a.parent) for a in chs)
for s, n in groups.most_common(3):
    say(f"  {n:3d} x {s}")
say("First chapter link: " + short(chs[0], 300))
say("Last chapter link:  " + short(chs[-1], 300))
chapter_url = urljoin(series_url, chs[len(chs) // 2]["href"])

# ---- 3. chapter page ----
r, soup, _ = fetch(chapter_url, series_url)
header("CHAPTER", r, soup, chapter_url)
imgs = soup.find_all("img")
say(f"Images: {len(imgs)}")
for s, n in collections.Counter(sig(i) + " <- " + sig(i.parent) for i in imgs).most_common(4):
    say(f"  {n:3d} x {s}")
for i in imgs[:3]:
    say(short(i, 350))

path = "autoprobe_" + urlparse(url).netloc + ".txt"
open(path, "w", encoding="utf-8").write("\n".join(out))
say(f"\nSaved to {path}")
