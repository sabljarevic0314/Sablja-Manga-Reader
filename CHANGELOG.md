# Changelog

All notable changes to Sablja Reader are listed here. The app version is shown in
**Settings → Updates**.

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
