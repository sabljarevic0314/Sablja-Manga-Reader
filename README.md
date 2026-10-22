# Sablja Reader

A desktop manga / manhwa / webtoon reader for Windows. Graphite UI with a warm
*Paper* theme in **Settings → Background**, webtoon (vertical strip),
single, double and right-to-left paged reading, a library with folders and bookmarks, downloads,
a History section and progress tracking — plus a built-in random manga roll (Randomizer).

**It hosts no content.** Sablja Reader is only a client application. It does not host, store,
upload or distribute any manga, and it ships with no copyrighted material. It reads pages from
the sources you enable in `sources.json`, using the official API where one exists (for example
WEBTOON). Which sources you enable, and what you read or download from them, is
your decision and your responsibility — see [Legal notice](#legal-notice).

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

You can also let the app check for you: **Settings → Updates → Check for updates**. When a newer
release exists you can read its notes and press **Download & install**. Automatic checks run at
most once a day (and can be switched off). Before an update is installed, `db.json` is copied to
`data\backups\`, so a bad update can never take your bookmarks with it. The installer makes its
own `db-before-<version>.json` backup for manual installs too.

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

If PowerShell says *"running scripts is disabled on this system"*, allow local scripts for your
user once and try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

`curl_cffi` (a browser-compatible HTTP client) is included in `requirements.txt` as an optional
extra; the app also runs without it.

A source checkout keeps its **own** `data\` folder next to `SabljaReader.py`. That folder is
separate from an installed copy's `%LOCALAPPDATA%\Programs\SabljaReader\data`, so copy `db.json`
between them if you want both copies to share the same library.

---

## Building your own exe (optional, for developers)

```powershell
pip install pyinstaller
.\build.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\make_setup.ps1
```

`build.ps1` produces a single-file `dist\SabljaReader.exe` (with the app icon baked in) and copies
`sources.json` next to it. `make_setup.ps1` wraps that into `dist\SabljaReader-Setup.exe` (it
downloads a portable NSIS if `makensis` is not already installed).
Your library, progress and cache in `dist\data` are left untouched.

### Releasing on GitHub

The workflow in `.github/workflows/release.yml` builds both files on a Windows runner and attaches
`SabljaReader-Setup.exe` to the release. Bump `APP_VERSION` in `SabljaReader.py` (the setup script
reads it automatically), then push a version tag:

```powershell
git tag 1.4
git push origin 1.4
```

`v1.4` works too. The built-in updater compares the release tag with `APP_VERSION`, so keep the
tag and the app version in sync (`1.4` and `1.4.0` compare as the same version).

---

## Using the app

### Library & reading

The left sidebar is your library — titles you have bookmarked, with folders and progress tracking.
Open a chapter and read; your position is remembered per title.

The window opens in borderless fullscreen by default. Press **F11** to toggle it, or turn
*Settings → Window → Open in borderless fullscreen on start* off if you prefer a normal window.
The custom minimize / fullscreen / close buttons appear only while the native title bar is hidden,
so there are never two sets of controls.

### Reading modes

Switch in Settings or per title in the details page:

| Mode | Use |
| --- | --- |
| Webtoon (vertical) | long vertical strips; pages are laid out as one continuous canvas |
| Single · left→right / right→left | classic page-by-page |
| Double · left→right / right→left | two-page spreads |

**Middle-click auto-scroll:** middle-click anywhere to start scrolling, without holding or
dragging. Click in the lower half to scroll down, the upper half to scroll up; the further
the pointer sits from the middle of the view, the faster it goes, and moving back towards the
middle slows it down smoothly. Middle-click again (or press **Esc**, scroll the wheel, or
click normally) to stop. This is especially handy for long webtoon chapters.

Reader background is its own setting (*Settings > Reading > Reader background*) and starts on
**Graphite matte**, independent of the app's Paper/Graphite theme.

### Shuffle (inside a source)

Every source page has a **Shuffle** button. It mixes the cards already loaded with a random
listing page (where the source has pagination) and shows a fresh random selection; press it
again for a different set. Scroll to the bottom to keep loading the normal listing.

### Genres on cards

Cards show a short genre/category line when the source exposes one directly on the
listing card (WEBTOON, MangaHub, Zazamanga, ReadManga, MangaTown, FanFox's latest list), or when the
genres were already cached from opening that title's details page. Cards never trigger
extra page requests, so scrolling stays fast and sites are not hammered.
Turn this off in *Settings > Sources > Show genres on cards*.

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

### Reporting a bug

*Settings → Report a bug / request a feature* has a short form (type, summary, what happened).
**Open GitHub issue** opens a new issue in your browser with the text and a diagnostics block
already filled in; you review it and press Submit. Nothing is sent automatically, and the
diagnostics contain no library, history or reading data. **Copy diagnostics** puts the same
block on your clipboard if you would rather paste it somewhere else.

### Downloads

Chapters can be saved for personal offline reading from the details page (with a configurable delay
between page fetches, to keep the load on the source low); downloaded chapters live in
`<install folder>\data\downloads`. Downloads are for your own personal use only — do not
redistribute them.

---

## Sources

`sources.json` is the one file to edit — a source is described by its listing/search/details/chapter
selectors (or `api: webtoons` / `api: fanfox` for sources that need a custom
adapter). Regular sources keep their file order in the app; every 18+ source is forced to the
bottom (both in `sources.json` and by `rebuild_sources()`). The app hot-reloads it
(*Settings → Reload sources.json*).

The file ships with worked examples: an official API (WEBTOON) and selector-based
sources including **MangaHub**, **FanFox**, **MangaDoom**, **ReadManga** and **MangaTown**. FanFox
hides chapter pages behind a packed-JS
AJAX endpoint, so its `api: fanfox` adapter asks for each page and unpacks the response.
Keep `curl_cffi` installed so sites that check the TLS fingerprint (such as MangaHub) can be
read with a browser-like connection. A source can also set `request_delay` (seconds between
page requests); HTTP 429 responses honour `Retry-After` and back off automatically. Sources
change their HTML regularly; if one stops working, the selectors in `sources.json` are the
first place to look.

MangaHub paginates its listing and reads the full chapter archive, not only the recent tab.
MangaTown and MangaDoom also paginate their listings and expose their full chapter archives.
MangaTown spreads a chapter
across one URL per page, so its `page_urls` selector reads the page list and fetches those
pages in parallel. Page downloads retry automatically before a failed page is shown.
MangaDex is no longer bundled: its catalogue mixed languages and produced empty or broken
entries, so it was removed from the source list.

A source can define a top-level `tags` selector list for the details page. Listing blocks can
also set their own `tags` selectors when the cards themselves show genres. The first selector
that finds text wins, and the result is shown on the card and details page. If a listing emits
broken local cover paths but the site has a working CDN copy, `cover_rewrite` (a list of
`[regex, replacement]` pairs) fixes the card URL without an extra request.

**Sablja Reader does not endorse, operate or recommend any particular source.** Some bundled
sources are examples that scrape a public website; others use official APIs. If you add or use
a source, you are responsible for making sure you are allowed to access and read it: check the
site's terms of service and the copyright status of what it offers, and prefer sources that are
published with the rights holders' permission. Please keep your request rate low and respect
`robots.txt` and any access restrictions a site applies.

Adding a source from scratch? `autoprobe.py` does a one-shot probe of a listing page and writes
`autoprobe_<host>.txt` with the card / chapter / page selectors it detected - paste the URL as an
argument or run it empty and type it in. Only use it on sites you are permitted to access.

Download-only sites (for example comic DDL blogs that link to `.cbz`/`.cbr` files on file
hosts) do not fit this reader model: they have no page images to page through and no chapter
viewer. They would need a separate download/queue subsystem, and their content is usually not
licensed — so they are not supported.

---

## Notes

* Windows 10/11, 64-bit.
* Memory: only pages near the viewport are held in memory; tall strips are capped in resolution
  (`WT_MAX_PX`) so a long chapter cannot grow without bound.
* Webtoon pages show a page-box outline only while a page is loading or failed; once artwork is on
  the canvas the outline is hidden, so long strips butt together seamlessly (no stray hairlines).

---

## Legal notice

* Sablja Reader is an independent hobby project. It is not affiliated with, endorsed by or
  sponsored by any manga publisher, scanlation group, website or API provider mentioned or used
  by it. All trademarks and content belong to their respective owners.
* The software is provided **"as is"**, without warranty of any kind. You use it at your own risk.
* You are solely responsible for the sources you enable and the content you view or download,
  and for complying with the laws of your country and the terms of the sites you visit.
* If you are a rights holder and believe this repository or its release files infringe your
  rights, please open an issue on this repository or contact the owner through their GitHub
  profile, and the matter will be looked at promptly.

## License

Proprietary — all rights reserved. Free to install and use for personal, non-commercial
purposes; selling, redistributing or republishing the app (or its source) is not allowed.
See [LICENSE](LICENSE).
