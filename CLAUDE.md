# Sablja Reader — notes for Claude

Windows desktop manga/webtoon reader written in Python (customtkinter + Tk). Current version: **1.4.1**
(`config.py`, `APP_VERSION`). Repo: `sabljarevic0314/Sablja-Manga-Reader`.

**Read `AGENTS.md` before touching any source.** It holds the non-negotiable rules for sources
(pagination, live testing, cheap cards, NSFW ordering, chapter picker, no MangaDex). This file is the map;
AGENTS.md is the law.

## Layout

| File | Role |
|---|---|
| `SabljaReader.py` | Entry point and the whole UI: `App(ctk.CTk)`, reader (webtoon strip mode, page mode), card grid, settings, updates, bug report. About 3,800 lines, 226 functions. |
| `config.py` | Paths (`BASE`, `DATA`, `DB_FILE`), `APP_VERSION`, `REPO_URL`, `UPDATE_ASSET`. |
| `storage.py` | `db.json` load/save (`save_db` writes atomically via `.tmp` + `os.replace`), backups, update state. |
| `sources.py` | `Source` class: HTTP with per-host pacing and 429 backoff, generic selector-based listing/details/chapters/pages, the `api:` adapters (`mangadex`, `webtoons`, `fanfox`, `mangahub`), thread pools (`NET_POOL`, `DETAIL_POOL`, `IMG_POOL`, `PAGE_POOL`), `load_img` / `THUMB_CACHE`, `rebuild_sources()`. |
| `sources.json` | **The only file to edit to add or fix a source.** Hot-reloaded from the app (Settings → Reload sources.json). |
| `downloads.py` | Chapter download to CBZ/folders. |
| `textures.py`, `assets.py` | Theme palettes, paper textures, embedded icons/images. |
| `autoprobe.py` | `python autoprobe.py <listing-url>`: probes a site and suggests selectors for a new source. |
| `build.ps1`, `SabljaReader.spec` | PyInstaller build to `dist\SabljaReader.exe`, copies `sources.json` into `dist\`. |
| `installer\make_setup.ps1`, `installer\SabljaReader.nsi` | NSIS installer `dist\SabljaReader-Setup.exe`. Not refreshed by `build.ps1`. |
| `.github\workflows\` | `ci.yml` (compile + JSON check on push), `release.yml` (tag → exe + installer on the release). |
| `CHANGELOG.md`, `README.md` | Release notes and user docs. Update the changelog for user-visible changes. |

Runtime data lives in `data\` next to the exe (repo: `data\`, built app: `dist\data\`): `db.json`
(library, progress, bookmarks, folders, ratings), `cache\` (images, capped at 1.5 GB), `errors.log`,
`backups\`, `update.json`. **Never delete or rewrite `data\` as part of a fix.** The installer and
updater promise to leave it alone.

## Running and verifying

Run from source: `pip install -r requirements.txt` then `python SabljaReader.py`. `curl_cffi` is
needed for Cloudflare-protected sources (MangaHub). A virtualenv is in `.venv\`.

Checks (same as CI):

```powershell
python -m py_compile SabljaReader.py
python -c "import json; json.load(open('sources.json', encoding='utf-8'))"
```

Live source test (from repo root):

```powershell
$env:PYTHONPATH=(Get-Location).Path
python -c "import SabljaReader as S; S.rebuild_sources(); print([s.name for s in S.SOURCES.values()])"
```

Build (exe, then installer, in that order):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\make_setup.ps1
```

Releasing: bump `APP_VERSION` in `config.py`, add a `CHANGELOG.md` entry, commit, and push a version tag.
The release workflow builds and attaches the installer.

## Sources: quick reference

- Regular sources come first in file order. Every source with `"nsfw": true` goes last. `rebuild_sources()`
  sorts them too, so file order can't break this.
- Selector-based sources: `popular` / `latest` / `search` (listing: `url` with `{page}` / `{query}`, `item`,
  `title`, `link`, `cover`, `cover_attr`, `tags`, `cover_rewrite`), `details`, `chapters` (`item`,
  `newest_first`, `title_pattern`, `title_format`, `list_path`, `single_page`), `pages` (`image`, `attr`,
  `page_urls`, `script_regex`, `url_suffix`). Optional: `request_delay`, `headers`, `impersonate`.
- Known pagination shapes: MangaDoom `/popular-manga?page={page}`; ReadManga `/browse?page={page}`
  and `/browse/latest-manga?page={page}`; MangaTown `/hot/romance/{page}.htm` (page 1 is `1.htm`).
- Cards are built only from listing HTML. No per-card requests. Covers go through `load_img`.

## Open issues

- **MangaHub uses `api: "mangahub"`** (`_mh_*` in `sources.py`). Chapter HTML only carries the first
  3-6 images; the rest come from the GraphQL API `https://api.mghcdn.com/graphql`
  (`chapter(x:m01,slug,number){pages}`, images on `https://imgx.mghcdn.com/`). The API needs the
  `mhub_access` cookie (set by any mangahub.io page, refreshed with `?reloadKey=1`) sent back as the
  `x-mhub-access` header. The full chapter list comes from `manga(x:m01,slug){chapters{number}}`; the
  longer of API vs HTML list wins. If the API fails, pages fall back to the HTML selectors and the
  error goes to `data\errors.log` ("MangaHub pages" / "MangaHub chapters").
  **Not yet verified live**: every MangaHub host returns a Cloudflare challenge from the Claude sandbox
  (don't try to get around it), so it has to be checked from the user's machine.
- Hentai18 was removed (broken). It's gone from `sources.json`. Old library items stay in `db.json`.

## Conventions

- Keep changes small and match the surrounding style, naming and comment density.
- Card size is 164x232 (grid cell 188). Keep it. Column count comes from the real canvas width.
- Page appends use `grid_cards(..., append=True)`.
- Don't add per-chapter widgets to the reader. The chapter picker is a Tk `Listbox` with a number-entry path.
- The app is Windows-only in practice (`os.startfile`, `winreg`, `\` paths in `data\`).
