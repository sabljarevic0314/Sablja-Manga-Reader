# Sablja Reader roadmap

Ideas collected on 2026-11-22. Tick them off or move them as they ship.

## Shipped in 2.0 (see CHANGELOG)

- [x] New UI in Flet (same toolkit and layout as Sablja Fitness), dark by default
- [x] Library: compact adaptive grid (S/M/L), filter, sort, new-chapter badge, read-progress bar
- [x] History: current chapter + page, X of Y read, time spent per series, rating, summary strip
- [x] Reader: lazy webtoon loading without jumps, paged direction arrows + hint, H / C / N / P keys
- [x] Reading log (`DB["log"]`) + lifetime time per series
- [x] Rail GIFs (Goku, Luffy, Naruto, Ichigo) with their own lines
- [x] Packaged with `flet pack`; updater, tray toasts and bug report ported; old Tk UI retired
- [ ] Today screen: built, then dropped (owner disliked it, 2026-11-22). Don't bring it back.
- [ ] Mascots: built, then removed (2026-11-22). Don't bring them back.

## Reader ideas (outside the box)

- **Endless webtoon**: reaching the end quietly appends the next chapter, so a binge is one scroll.
- **Dark-paper mode**: invert black-and-white pages (Flutter colour filter, free) so manga reads white-on-black
  at night; a sepia / warm option too.
- **Panel-by-panel guided view** for paged manga: find the panel gutters with PIL and step panel to panel,
  zoomed, with the arrow keys. Great in a small window.
- **Page scrubber**: a thin vertical rail of page thumbnails on the right to jump inside a chapter.
- **Magnifier loupe**: hold Shift to see a 2x lens under the cursor for tiny text.
- **Smart prefetch**: at 80 % of a chapter, fetch the first pages of the next one (politely), so Next is
  instant.
- **Chapter reactions**: one-tap emoji at the end of a chapter; a mood timeline per series and in Wrapped.
- **Focus mode**: hide the cursor after 2 s and dim everything but the strip.

## Next (picked)

1. **Chapter-cleared card**: a workout-style summary at the end of a chapter (time, pages, ring progress)
   with a thumbnail of the next chapter's first page.
2. **Ambient reader glow**: the empty side margins in webtoon mode pick up the current panel's colours.

## Prettier

- Cover hero on the details page: blurred, darkened cover backdrop, accent taken from the cover colour.
- Animated rings and count-up numbers when Today opens.
- Bookshelf view for Library: covers as spines coloured from the cover, vertical titles.
- Accent picker (teal default, or "take it from my favourite cover").
- Paged mode: a quick slide/turn animation between pages.
- Face/saliency crop for small cover thumbnails.

## Unique

- Streaks and badges ("7-day streak", "Finished a 500+ chapter series", "3 sources in a day", "Night owl").
- Mood tags per chapter (hype, sad, funny, shock) → a mood timeline per series.
- Sablja Wrapped: monthly / yearly recap (top genres, longest binge, most re-read, total pages), exportable
  as an image.
- Reading DNA: a generated fingerprint image of your genres, sources and reading hours.
- Insights page: year heatmap (GitHub-style) plus stats.
- Release Radar: guess each series' update day from its chapter dates, show the week on a calendar,
  fade series that look like they're on hiatus (60+ days quiet).
- "Previously on…": after 2+ weeks away, show the last 3 pages you read first (already cached).
- Spoiler shield: blur chapter titles past your progress, click to reveal.
- Focus mode: rail dims, cursor hides, optional Pomodoro.
- Pace-matched auto-scroll: learns your speed, slows on text-heavy panels.
- Panel scrapbook: right-click a panel to crop and save it to a gallery (series + chapter tagged).
- Mood picker for the Randomizer (light ↔ dark, short ↔ long, finished ↔ ongoing).
- "One more chapter" limiter: optional bedtime / session cap.
- Up Next queue across series.
- Night comfort: warm tint and slight dim in the reader after a set hour.
- Smart offline: auto-download the next N unread chapters of Up Next.
- Weekly digest toast on Sunday (only with notifications on).
- Reading statuses: Reading / Plan to read / On hold / Dropped / Completed, each a shelf on Today.
- Import from MyAnimeList / AniList export, matched by searching the sources.

## Sources

- **Source fallback**: if a chapter is missing or broken on one source of a grouped series, try the next.
- Candidates to probe (each must pass the AGENTS.md checklist live first): MangaBuddy, Asura Scans,
  Flame Comics, NatoManga, Tapas. Bato.to is risky (mixed languages, like MangaDex).

## Not doing

- Phone companion / LAN reading (owner's call, 2026-11-22).
- Linux builds (owner no longer uses Linux, 2026-11-22). 1.4.7 was the last.
- Drawn/rendered mascots (sprites, Blender). The rail GIFs replaced them (owner's call, 2026-11-22).
