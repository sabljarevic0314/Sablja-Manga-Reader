# Sablja Reader

A desktop manga / manhwa / webtoon reader for Windows. Silver-on-graphite UI with a warm
*Paper* theme in **Settings → Background**, webtoon (vertical strip),
single, double and right-to-left paged reading, a library with folders and bookmarks, downloads,
a History section and progress tracking — plus a built-in random manga roll (Randomizer).

**It hosts no content.** It is a client: it reads publicly available pages from third-party sources listed
in `sources.json`, using the official API where one exists and plain server-rendered HTML otherwise.

---

## Installing (regular users) — 2 minutes

> **No programming, no Python, no admin rights.** You need exactly one file: `SabljaReader-Setup.exe`.

1. Go to the [Releases](../../releases) page.
2. Open the newest release and under **Assets** download **`SabljaReader-Setup.exe`**.
   *(Ignore the "Source code (zip)" entries — that is only for developers, see below.)*
3. Double-click the downloaded file. Windows may ask *"Do you want to run this file?"* — click **Run**.
   If SmartScreen shows *"Windows protected your PC"* (the app is not code-signed), click
   **More info → Run anyway**.
4. The installer finishes by launching the app. A **Desktop** shortcut and a Start Menu entry
   are created; the app also appears in **Apps & features** like any normal program.

What the installer does for you:

* per-user install into `%LOCALAPPDATA%\Programs\SabljaReader` — **no admin rights needed**
* creates Desktop and Start Menu shortcuts and a proper uninstaller
* library, reading progress, cache and downloads live in `<install folder>\data`
* that `data\` folder **survives both updates and uninstalling**, so you never lose your
  bookmarks, progress or downloaded chapters by accident

Updating later: download the new `SabljaReader-Setup.exe` from the newest Release and run it —
it refreshes the app files and keeps everything in `data\`.

---

## Running from source (only for developers)

Only do this if you want to read or modify the code — otherwise use the installer above.

You need **Python 3.13 or newer** and a few packages:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python SabljaReader.py
```

`curl_cffi` (Chrome/Firefox TLS fingerprint, bypasses many 403s on Cloudflare-protected pages) is
included in `requirements.txt`; the app also runs without it — you just lose that extra.

---

## Building your own exe (optional, for developers)

```powershell
.\build.ps1
```

This produces a single-file `dist\SabljaReader.exe` (with the app icon baked in) and copies
`sources.json` next to it.
Your library, progress and cache in `dist\data` are left untouched.

---

## Using the app

### Library & reading

The left sidebar is your library — titles you have bookmarked, with folders and progress tracking.
Open a chapter and read; your position is remembered per title.

### Reading modes

Switch in Settings or per title in the details page:

| Mode | Use |
| --- | --- |
| Webtoon (vertical) | long vertical strips; pages are laid out as one continuous canvas |
| Single · left→right / right→left | classic page-by-page |
| Double · left→right / right→left | two-page spreads |

### Randomizer

The **Randomizer** in the sidebar opens a random title from your enabled sources on the normal
details page, so you can read, bookmark, rate or download it. *Next random* rolls again,
*Previous* steps back through the ones you've seen — an easy way to find something new
without searching.

### History

The **History** section lists everything you have read, newest first, with the chapter and page you
stopped on — click a card to jump straight back in, right-click to remove a single entry, or use
*Clear history* for all of it. Don't want it in the sidebar? Turn it off in *Settings → Sidebar*
(*Show the History section*); your reading positions are kept either way.

### Downloads

Chapters are downloaded in the background from the details page (with a configurable delay between
page fetches); downloaded chapters live in `<install folder>\data\downloads` and stay readable offline.

---

## Sources

`sources.json` is the one file to edit — add a source by describing its listing/search/details/chapter
selectors (or `api: mangadex` / `api: webtoons` for the official APIs). The app hot-reloads it
(*Settings → Reload sources.json*).

Some sources need cookies (Cloudflare-protected sites). Put them in
*Settings → Cloudflare-protected sources*; they are stored per source in `data\db.json`.

Adding a source from scratch? `autoprobe.py` does a one-shot probe of a listing page and writes
`autoprobe_<host>.txt` with the card / chapter / page selectors it detected - paste the URL as an
argument or run it empty and type it in.

---

## Notes

* Windows 10/11, 64-bit.
* Memory: only pages near the viewport are held in memory; tall strips are capped in resolution
  (`WT_MAX_PX`) so a long chapter cannot grow without bound.
* Webtoon pages show a page-box outline only while a page is loading or failed; once artwork is on
  the canvas the outline is hidden, so long strips butt together seamlessly (no stray hairlines).

## License

Proprietary — all rights reserved. Free to install and use for personal, non-commercial
purposes; selling, redistributing or republishing the app (or its source) is not allowed.
See [LICENSE](LICENSE).
