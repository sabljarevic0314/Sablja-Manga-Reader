# Sablja Manga Reader App

A desktop manga / manhwa / webtoon reader for Windows. Dark by default (with a *White* theme),
webtoon (vertical strip), single, double and right-to-left paged reading, a library with folders,
ratings, history and reading stats, chapter downloads, and a random roll when you don't know what
to read next.

**It hosts no content.** Sablja Manga Reader App is only a client application. It does not host, store,
upload or distribute any manga. It reads pages from the sources you enable in `sources.json`, using
the official API where one exists (for example WEBTOON). Which sources you enable, and what you read
or download from them, is your decision and your responsibility — see [Legal notice](#legal-notice).

---

## Installing — 2 minutes

> **No programming, no Python, no admin rights.** You need exactly one file: `SabljaMangaReaderApp-Setup.exe`.

1. Go to the [Releases](../../releases) page.
2. Open the newest release and under **Assets** download **`SabljaMangaReaderApp-Setup.exe`**.
   *(Ignore the "Source code" entries — those are only for developers.)*
3. Double-click it. If SmartScreen shows *"Windows protected your PC"* (the app is not code-signed),
   click **More info → Run anyway**.
4. The installer finishes by starting the app. It adds a Desktop shortcut, a Start Menu entry and an
   uninstaller (**Apps & features**).

What the installer does:

* installs per user into `%LOCALAPPDATA%\Programs\SabljaReader` — **no admin rights needed**
* keeps your library, progress, cache and downloads in `<install folder>\data`
* never deletes that `data` folder, not on updates and not on uninstall, and backs up `db.json`
  before every install

### Updating

The app checks GitHub for a new version once a day (switch it off in **Settings → Updates**, or press
**Check for updates** there). When there is one you can read what changed and press
**Download & install**: the app downloads the installer, checks its SHA-256 against the release, backs
up `db.json` to `data\backups\`, closes and runs the update. Your library stays where it is.
Downloading the newest `SabljaMangaReaderApp-Setup.exe` by hand and running it does the same.

Coming from 1.x? Just install 2.0 over it (or let 1.x update itself). Everything in `data\` carries over.

---

## Using the app

### Library

Everything you've added, as a grid of covers. Folders are chips along the top (plus *Downloaded*),
and you can filter by title, sort (Recent, Title, Rating, New) and pick the cover size (S / M / L).
A `+N` badge marks series with new chapters, and a thin bar shows how far you've read. Right-click any
cover for: open, continue, add/remove, rate, move to a folder, open on another source, delete downloads.

If the same series is in your library from several sources it shows as one card; right-click it to
open it on a specific source. Turn that off in **Settings → Look**.

### Finding something to read

* **Sources** — browse one source at a time (popular / latest, genre filter where the source has one,
  *Shuffle* for a random page, *Load more*).
* **Search** — searches every enabled source at once.
* **Random** — rolls six random titles, optionally from one source, with your earlier rolls below.

### Reading

Modes (default in **Settings → Reading**, or per series in the reader):

| Mode | Use |
| --- | --- |
| Webtoon (vertical) | long vertical strips, one continuous scroll |
| Single · left→right / right→left | page by page |
| Double · left→right / right→left | two-page spreads |

Keys: **↑ ↓ Space** scroll · **← →** chapters (webtoon) or pages (paged) · **N / P** next / previous
chapter · **C** chapter list · **+ / −** zoom · **H** hide the bar · **Esc** back · **F11** full screen.

* **Auto-scroll (webtoon):** **A** starts and stops it, **,** and **.** change the speed.
* **Middle click** starts browser-style auto-scroll; hold and drag works too.
* The mouse wheel turns pages in the paged modes and moves on to the next chapter at the end.

Your place is saved as you read, and always when you close the window.

### History, ratings and stats

**History** lists everything you've read with the chapter and page you stopped on, how many chapters
you've finished, and the time you spent on each series, plus totals (reading time, last 7 days,
chapters, streak). Reading time only counts while you're actually reading. **Rating** lists the series
you rated, with your notes.

### Downloads

Save chapters for offline reading from a series' page. They download one at a time with a pause
between pages (set it in **Settings → Downloads**) so the source isn't hammered, and are stored as one
`.cbz` per chapter. **Downloads → On disk** lists everything you have and deletes it per chapter or per
series. Downloads are for your own personal use only — don't redistribute them.

### New-chapter notifications (optional)

The Library always shows the `+N` badge. Turn on **Settings → Notifications** to also get a Windows
toast when a Library series gets new chapters: the app checks every 30 minutes **while it is open**
and shows a tray icon for the toasts. Off by default; closing the window still quits the app and
nothing starts with Windows. A series is only announced once the app has seen its chapter count
before, so turning this on never floods you with old chapters.

### Privacy: panic key and PIN

**F12** (changeable) hides the window at once. An optional **PIN** (**Settings → Privacy**) locks the
app when it starts and/or after the panic key; toasts never show titles while it's locked. The PIN
only hides the window — it does not encrypt your library or downloads.

### The GIFs

Goku, Luffy, Naruto and Ichigo take turns at the bottom of the menu, a new one every 20 seconds, and
each says something when it shows up. Right-click it → **Disable GIFs** to turn them off;
**Settings → Look** turns them back on. To add your own, open the GIF folder from there and drop in
transparent `.gif` files named like `luffy3.gif`.

### Reporting a bug

**Settings → Report a bug / request a feature** opens a new GitHub issue in your browser with your
text and a short diagnostics block (app version, Windows version, settings that matter) filled in.
You review it and press Submit; nothing is sent automatically and no reading history is included.

---

## Sources

`sources.json` (next to the exe) is the one file to edit. A source is described by its
listing / search / details / chapter / page selectors, or by an `api:` adapter for sites that need
custom handling (`webtoons`, `fanfox`, `mangahub`). Regular sources keep their file order; every 18+
source is always listed last. **Settings → Sources** shows or hides each one and reloads the file
without restarting.

The bundled list includes WEBTOON (official API) and selector-based sources such as **MangaHub**,
**FanFox**, **MangaDoom**, **ReadManga** and **MangaTown**. Requests are paced per site, and HTTP 429
responses honour `Retry-After`. `curl_cffi` (bundled) gives a browser-like connection for sites that
check it, such as MangaHub. Sites change their HTML regularly; if one stops working, its selectors in
`sources.json` are the first place to look. MangaDex is not bundled (mixed languages, broken entries).

Adding a source from scratch? `python autoprobe.py <listing-url>` probes a page and writes
`autoprobe_<host>.txt` with the selectors it found. Only use it on sites you are allowed to access.

**Sablja Manga Reader App does not endorse, operate or recommend any particular source.** If you add or use a
source, you are responsible for making sure you are allowed to read it: check the site's terms and the
copyright status of what it offers, prefer sources published with the rights holders' permission, keep
your request rate low and respect `robots.txt`.

---

## For developers

### Running from source

You need **Python 3.13+**:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Or double-click **`Test Sablja Manga Reader App.bat`**: it sets up `.venv` the first time and can start you off
with a copy of your installed library (the installed one is never changed). A source checkout keeps
its own `data\` folder in the repo.

### Building the exe and installer

```powershell
pip install pyinstaller flet-cli==1.1.2
.\build.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\make_setup.ps1
```

`build.ps1` runs `flet pack` and writes a single-file `dist\SabljaMangaReaderApp.exe` (with the GIFs inside) plus
`dist\sources.json`. `make_setup.ps1` wraps them into `dist\SabljaMangaReaderApp-Setup.exe` with NSIS (it
downloads a portable NSIS if `makensis` isn't installed).

### Releasing

Bump `APP_VERSION` in `config.py`, add a `CHANGELOG.md` entry, commit, and push a matching tag
(`git tag 2.0.1` then `git push origin 2.0.1`). `.github/workflows/release.yml` builds the installer on
a Windows runner and attaches it to the release, which is what the in-app updater downloads.

---

## Legal notice

* Sablja Manga Reader App is an independent hobby project. It is not affiliated with, endorsed by or sponsored by
  any manga publisher, scanlation group, website or API provider. All trademarks and content belong to
  their respective owners.
* The rail GIFs are fan-made animations of characters from *Dragon Ball*, *One Piece*, *Naruto* and
  *Bleach*, included for fun in a free, non-commercial app. The characters belong to their creators and
  publishers. The lines they say are original to this app.
* The software is provided **"as is"**, without warranty of any kind. You use it at your own risk.
* You are solely responsible for the sources you enable and the content you view or download, and for
  complying with the laws of your country and the terms of the sites you visit.
* If you are a rights holder and believe this repository or its release files infringe your rights,
  please open an issue on this repository or contact the owner through their GitHub profile, and it
  will be looked at promptly.

## License

Proprietary — all rights reserved. Free to install and use for personal, non-commercial purposes;
selling, redistributing or republishing the app (or its source) is not allowed. See [LICENSE](LICENSE).
