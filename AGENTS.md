# Sablja Reader — project instructions

These rules are non-negotiable. They exist because the same source bugs kept coming back.

## Source implementation checklist

Every new source must pass all of these before it is added to `sources.json`:

1. **Pagination is mandatory.**
   - Never add `"single_page": true` to a listing unless page 2 genuinely has no different
     results. “The first page has enough cards” is not a reason.
   - Verify page 1 and page 2 return **different** titles. Pagination URL shapes differ:
     `?page=2`, `/{page}.htm`, `/popular-manga/{page}`, etc. Use the site’s real shape.
   - The app loads the next page automatically near the bottom (`load_more`). If a source
     says “End of results” after the first screen, pagination was configured wrong.

2. **Test the whole chain live**, not just the listing selectors:
   - listing page 1 and page 2
   - search
   - details page
   - full chapter list (not only recent chapters)
   - chapter page-image URLs (download the first image and check HTTP 200 + an image
     content type)

3. **Cards must be cheap.**
   - Build cards only from the listing page. Never make one request per card for genres,
     descriptions, or details.
   - Use the site’s real cover URL, and prefer a smaller CDN/thumbnail variant when one
     exists. If the listing emits broken local cover paths, use `cover_rewrite` to point at
     the site’s working CDN copy instead of letting every card retry a 404.
   - Covers load through `load_img`/`THUMB_CACHE`; do not bypass that pipeline.

4. **18+ sources always go last.**
   - In `sources.json`, every entry with `"nsfw": true` belongs after every regular source.
   - `rebuild_sources()` also sorts NSFW sources last, so file order cannot break this.

5. **Reader navigation must stay usable on 1,000+ chapter titles.**
   - The chapter picker is a Tk `Listbox` (not one widget per chapter).
   - It must keep a direct “type a chapter number and press Enter” path. If the number does
     not exist, show a small inline error instead of closing the picker.
   - The numeric entry must have focus when the picker opens. Keep the `Toplevel` withdrawn
     until its geometry is set; mapping it first snapped the popup to the top-left corner.
   - Do not reintroduce per-chapter buttons or a blocking synchronous menu build.

6. **Do not re-add MangaDex** to the bundled list. It was removed for broken/empty entries,
   mixed languages, and missing chapters.

### Known pagination shapes

- **MangaDoom:** `/popular-manga?page={page}` (the homepage is not paginated).
- **ReadManga:** `/browse?page={page}` and `/browse/latest-manga?page={page}`
  (`/browse/hot-manga` reshuffles between requests, so page 2 overlaps page 1).
- **MangaTown:** `/hot/romance/{page}.htm` (page 1 is `1.htm`).

## Card grid rules

- `cols_for()` must use the real scroll canvas width minus the scrollbar and a safety
  margin. Guessing from the main window width over-counts columns and clips the last card.
- Page appends must use `grid_cards(..., append=True)`. Bumping the render generation while
  appending cancels the tail of the previous page and leaves holes in the grid.
- The normal card size is **164x232** (grid cell 188 px). Keep the larger size; the user
  prefers fewer, bigger cards over a dense wall.

## Verification commands

```powershell
python -m py_compile SabljaReader.py
python -c "import json; json.load(open('sources.json', encoding='utf-8'))"
```

Live source test (from the repo root):

```powershell
$env:PYTHONPATH=(Get-Location).Path
python -c "import SabljaReader as S; S.rebuild_sources(); print([s.name for s in S.SOURCES.values()])"
```

When a source is changed, test page 1 and page 2 explicitly and compare the returned URLs.

## Build workflow

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\make_setup.ps1
```

`build.ps1` rebuilds the exe and copies `sources.json`. The installer is a separate step;
`dist\SabljaReader-Setup.exe` is not refreshed by `build.ps1` alone.
