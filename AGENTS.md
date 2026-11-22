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
   - Covers load through the thumbnail pipeline in `ui/core.py`; do not bypass it.

4. **18+ sources always go last.**
   - In `sources.json`, every entry with `"nsfw": true` belongs after every regular source.
   - `rebuild_sources()` also sorts NSFW sources last, so file order cannot break this.

5. **Reader navigation must stay usable on 1,000+ chapter titles.**
   - The chapter picker (C in the reader, `ui/reader.py`) is a lazy `ft.ListView` with a fixed
     `item_extent`, never one heavyweight widget per chapter built up front.
   - It must keep a direct “type a chapter number and press Enter” path, with focus in that field
     when the picker opens. If the number does not exist, show a small inline error instead of
     closing the picker.

6. **Do not re-add MangaDex** to the bundled list. It was removed for broken/empty entries,
   mixed languages, and missing chapters.

### Known pagination shapes

- **MangaDoom:** `/popular-manga?page={page}` (the homepage is not paginated).
- **ReadManga:** `/browse?page={page}` and `/browse/latest-manga?page={page}`
  (`/browse/hot-manga` reshuffles between requests, so page 2 overlaps page 1).
- **MangaTown:** `/hot/romance/{page}.htm` (page 1 is `1.htm`).

## Card grid rules

- Grids are `ft.GridView` with `max_extent` from `DENSITY` (S / M / L) and `child_aspect_ratio=0.69`;
  the column count follows the real width. Don't build fixed-size rows by hand.
- Appending a page adds controls to the existing grid. Never rebuild the whole grid to append, and
  never bump the view's generation counter for an append (that drops the tail of the last page).
- Cards come only from listing HTML; cover thumbnails go through `ui/core.py` (`thumb`, `cover_image`).

## Verification commands

```powershell
.venv\Scripts\python -m compileall -q main.py config.py storage.py sources.py downloads.py desktop.py stats.py updater.py ui
python -c "import json; json.load(open('sources.json', encoding='utf-8'))"
```

Live source test (from the repo root):

```powershell
.venv\Scripts\python -c "import sources as S; S.rebuild_sources(); print([s.name for s in S.SOURCES.values()])"
```

When a source is changed, test page 1 and page 2 explicitly and compare the returned URLs.

## Build workflow

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .uild.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\make_setup.ps1
```

`build.ps1` runs `flet pack` (exe + `sources.json` in `dist\`). The installer is a separate step;
`dist\SabljaReader-Setup.exe` is not refreshed by `build.ps1` alone.
