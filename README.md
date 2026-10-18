# Sablja Reader

A desktop manga / manhwa / webtoon reader for Windows. Silver-on-graphite UI, webtoon (vertical strip),
single, double and right-to-left paged reading, a library with folders and bookmarks, downloads and
progress tracking — plus a built-in random manga roll (Randomizer) and a lofi radio for reading in the background.

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

`curl_cffi` (Chrome/Firefox TLS fingerprint, bypasses many 403s on Cloudflare-protected pages) and
`miniaudio` (the lofi radio) are included in `requirements.txt`; the app also runs without them —
you just lose those extras.

---

## Building your own exe (optional, for developers)

```powershell
.\build.ps1
```

This produces a single-file `dist\SabljaReader.exe` (with the app icon baked in and the lofi radio
working — `miniaudio` is pinned in `SabljaReader.spec`) and copies `sources.json` next to it.
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

### Lofi radio

The toggle at the bottom of the sidebar starts the **lofi radio** (⏭ skips to another station).
Stations come from the free [radio-browser.info](https://www.radio-browser.info) directory
(tag `lofi`, MP3), with SomaFM Groove Salad as a fallback. Nothing to pre-install — in both the
packaged exe and a source run with `requirements.txt`, the audio engine (`miniaudio`) is already there.

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
* The lofi radio needs the radio-browser.info directory (a free volunteer service); if it is briefly
  down, the app falls back to SomaFM and shows *No stream – retry* until a station connects.

## License

MIT — see [LICENSE](LICENSE).
