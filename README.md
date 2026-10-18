# Sablja Reader

A desktop manga / manhwa / webtoon reader for Windows. Silver-on-graphite UI, webtoon (vertical strip),
single, double and right-to-left paged reading, a library with folders and bookmarks, downloads and
progress tracking.

**It hosts no content.** It is a client: it reads publicly available pages from third-party sources listed
in `sources.json`, using the official API where one exists and plain server-rendered HTML otherwise.

## Install (for users)

Run `SabljaReader-Setup.exe` from the [Releases](../../releases) page.

* per-user install, **no admin rights needed** (`%LOCALAPPDATA%\Programs\SabljaReader`)
* creates Desktop and Start Menu shortcuts and a proper uninstaller (*Apps & features*)
* library, reading progress, cache and downloads live in `<install folder>\data` and survive updates
* uninstalling keeps `data\` so you never lose your library by accident

## Run from source

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python SabljaReader.py
```

Python 3.13 or newer. `curl_cffi` (better pages compatibility) and `miniaudio` (lofi radio)
are in `requirements.txt`; the app also runs without them, you just lose those extras.

## Build

```powershell
.\build.ps1                        # dist\SabljaReader.exe  + dist\sources.json
powershell -ExecutionPolicy Bypass -File installer\make_setup.ps1   # dist\SabljaReader-Setup.exe
```

`build.ps1` produces a single-file exe; `make_setup.ps1` wraps it in the installer
(NSIS is fetched automatically into `installer\tools` if you don't have it).
`miniaudio` is pinned in `SabljaReader.spec` (`hiddenimports`), so the radio works in the exe.

## Reading modes

| Mode | Use |
| --- | --- |
| Webtoon (vertical) | long vertical strips; pages are laid out as one continuous canvas |
| Single · left→right / right→left | classic page-by-page |
| Double · left→right / right→left | two-page spreads |

## Randomizer and lofi radio

* **Randomizer** (sidebar) opens a random title from your enabled sources on the normal details page, so you can read,
  bookmark, rate or download it. *Next random* rolls again, *Previous* steps back through the ones you've seen.
* **Lofi radio** is the toggle at the bottom of the sidebar (⏭ skips to another station). Stations come from the free
  [radio-browser.info](https://www.radio-browser.info) directory (tag `lofi`, MP3), with SomaFM Groove Salad as a
  fallback. It needs `miniaudio`; if you build the exe, add `--hidden-import miniaudio` to the PyInstaller call.

## Sources

`sources.json` is the one file to edit — add a source by describing its listing/search/details/chapter
selectors (or `api: mangadex` / `api: webtoons` for the official APIs). The app hot-reloads it
(*Settings → Reload sources.json*).

Some sources need cookies (Cloudflare-protected sites). Put them in
*Settings → Cloudflare-protected sources*; they are stored per source in `data\db.json`.

Adding a source from scratch? `autoprobe.py` does a one-shot probe of a listing page and writes
`autoprobe_<host>.txt` with the card / chapter / page selectors it detected - paste the URL as an
argument or run it empty and type it in.

## Notes

* Windows 10/11, 64-bit. Python 3.13 for source runs.
* Memory: only pages near the viewport are held in memory; tall strips are capped in resolution
  (`WT_MAX_PX`) so a long chapter cannot grow without bound.

## License

MIT — see [LICENSE](LICENSE).
