# Sablja Reader

A desktop manga / manhwa / webtoon reader for Windows. Silver-on-graphite UI with a warm
*Paper* theme in **Settings → Background**, webtoon (vertical strip),
single, double and right-to-left paged reading, a library with folders and bookmarks, downloads,
a History section and progress tracking — plus a built-in random manga roll (Randomizer).

**It hosts no content.** Sablja Reader is only a client application. It does not host, store,
upload or distribute any manga, and it ships with no copyrighted material. It reads pages from
the sources you enable in `sources.json`, using the official API where one exists (for example
MangaDex and Webtoons). Which sources you enable, and what you read or download from them, is
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

`curl_cffi` (a browser-compatible HTTP client) is included in `requirements.txt` as an optional
extra; the app also runs without it.

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

Chapters can be saved for personal offline reading from the details page (with a configurable delay
between page fetches, to keep the load on the source low); downloaded chapters live in
`<install folder>\data\downloads`. Downloads are for your own personal use only — do not
redistribute them.

---

## Sources

`sources.json` is the one file to edit — a source is described by its listing/search/details/chapter
selectors (or `api: mangadex` / `api: webtoons` for the official APIs). The app hot-reloads it
(*Settings → Reload sources.json*).

**Sablja Reader does not endorse, operate or recommend any particular source.** The sources included
with the app are limited to official public APIs. If you add other sources yourself, you are
responsible for making sure you are allowed to access and read them: check the site's terms of
service and the copyright status of what it offers, and prefer sources that are published with the
rights holders' permission. Please keep your request rate low and respect `robots.txt` and any
access restrictions a site applies.

Some sources may ask you to sign in or supply cookies from your own browser session. Settings for
this are in *Settings → Protected sources*; they are stored per source in `data\db.json` on your
own computer and are never sent anywhere except to that source.

Adding a source from scratch? `autoprobe.py` does a one-shot probe of a listing page and writes
`autoprobe_<host>.txt` with the card / chapter / page selectors it detected - paste the URL as an
argument or run it empty and type it in. Only use it on sites you are permitted to access.

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
