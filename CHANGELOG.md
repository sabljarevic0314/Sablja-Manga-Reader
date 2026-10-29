# Changelog

All notable changes to Sablja Reader are listed here. The app version is shown in
**Settings → Updates**.

## 1.4.1 — 2026-10-29

### Fixed / faster

- **Webtoon scrolling with very tall pages** no longer stutters or spikes memory: a page taller
  than 1,000 px is split into stacked strips, built two per frame, so a huge page never blocks
  the scroll.
- **Page and cover loading** keeps more pages ahead (6 in flight, 5 ahead in webtoon mode), so
  fast scrolling no longer waits on an empty screen.
- **Saving** (`db.json`) is debounced and only writes when something actually changed, which
  removes small freezes while reading, bookmarking and browsing.
- **HTML parsing** uses `lxml` when available, falling back to the built-in parser.
- **Image cache** is trimmed automatically (1.5 GB cap) and failed page loads are logged to
  `data\errors.log` instead of failing silently.

### Changed

- The old unused icon generator was removed; the app icon is built from the bundled logo.
- Internal code split into modules (`config`, `storage`, `sources`, `downloads`, `textures`,
  `assets`). Behaviour is unchanged; `SabljaReader.py` is still the entry point.
- Version bumped to **1.4.1**.

## 1.4.0 — 2026-10-23

### Added

- **Middle-click auto-scroll** in Webtoon mode and all scrollable lists/grids. Click once to
  start, click again to stop. The lower half of the view (or pointer position) scrolls down,
  the upper half scrolls up, and the distance from the middle controls the speed.
- **Built-in updates** under *Settings → Updates*: check GitHub for the latest release, read
  the release notes and download/install the new `SabljaReader-Setup.exe`. Automatic checks
  run at most once a day and can be switched off.
- **Automatic library backup** before every update: `data\backups\db-<timestamp>-v<version>.json`.
  The installer also keeps a `data\backups\db-before-<version>.json` copy for manual installs.
- GitHub Actions release workflow: pushing a version tag builds the exe + installer and
  attaches the installer to the release.

### Changed

- The auto-scroll ring/indicator was removed; only the auto-scroll movement and cursor remain.
- Version bumped to **1.4.0**.

### Safety

- The installer still only replaces `SabljaReader.exe` and `sources.json`. The `data\` folder
  (library, progress, cache, downloads) is never deleted by installing, updating or
  uninstalling.

## 1.3.0

- Stable 1.3 release: paper themes, History section, and the current source/reading features.
