# Build SabljaReader.exe and publish the canonical sources.json next to it.
#
# From now on the project-root sources.json is the one and only file you edit.
# This script copies it into dist\ so the exe always reads exactly what you edited.
#
#   .\build.ps1
#
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m PyInstaller --noconfirm SabljaReader.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }

Copy-Item sources.json dist\sources.json -Force

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  exe:  dist\SabljaReader.exe"
Write-Host "  conf: dist\sources.json  (copied from .\sources.json)"
Write-Host "Your library, progress and cache live in dist\data and were left untouched."
