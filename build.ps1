# Build dist\SabljaMangaReaderApp.exe (the Flet app, one file) and publish sources.json next to it.
#
#   .\build.ps1
#
# Needs: pip install -r requirements.txt pyinstaller flet-cli==1.1.2
# `flet pack` wraps PyInstaller and bundles the Flutter client; it writes a throwaway SabljaMangaReaderApp.spec
# and build\ (both gitignored). The project-root sources.json is the one you edit: it's copied into dist\.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$cfg = Get-Content config.py -Raw
if ($cfg -notmatch '(?m)^APP_VERSION\s*=\s*"([^"]+)"') { throw "Could not read APP_VERSION from config.py" }
$ver = $Matches[1]
Write-Host "Building Sablja Manga Reader App $ver"

$py = if (Test-Path .venv\Scripts\python.exe) { ".venv\Scripts\python.exe" } else { "python" }
& $py -m flet_cli.cli pack main.py -y `
    --name SabljaMangaReaderApp --icon SabljaMangaReaderApp.ico --distpath dist `
    --add-data "assets/gifs:assets/gifs" `
    --hidden-import pystray._win32 `
    --product-name "Sablja Manga Reader App" --file-description "Sablja Manga Reader App" --company-name "Sablja Manga Reader App" `
    --product-version $ver --file-version "$ver.0" --copyright "Sablja Manga Reader App"
if ($LASTEXITCODE -ne 0) { throw "flet pack failed (exit $LASTEXITCODE)" }
Remove-Item SabljaMangaReaderApp.spec -ErrorAction SilentlyContinue

Copy-Item sources.json dist\sources.json -Force

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  exe:  dist\SabljaMangaReaderApp.exe"
Write-Host "  conf: dist\sources.json  (copied from .\sources.json)"
Write-Host "Your library, progress and cache live in dist\data and were left untouched."
