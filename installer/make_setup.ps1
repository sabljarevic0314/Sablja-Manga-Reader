# Build dist\SabljaReader-Setup.exe - a normal Windows installer (NSIS).
# Uses makensis if it is on PATH, otherwise downloads the portable NSIS into installer\tools.
#
#   powershell -ExecutionPolicy Bypass -File installer\make_setup.ps1
param([string]$NsisVersion = "3.10")
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$exe  = Join-Path $root "dist\SabljaReader.exe"
if (-not (Test-Path $exe)) { throw "dist\SabljaReader.exe not found - run .\build.ps1 first." }
if (-not (Test-Path (Join-Path $root "dist\sources.json"))) {
    Copy-Item (Join-Path $root "sources.json") (Join-Path $root "dist\sources.json") -Force
}

function Find-Makensis {
    $c = Get-Command makensis -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($p in @("$PSScriptRoot\tools", "C:\Program Files\NSIS", "C:\Program Files (x86)\NSIS")) {
        $m = Join-Path $p "makensis.exe"
        if (Test-Path $m) { return $m }
    }
    $m = Get-ChildItem "$PSScriptRoot\tools" -Recurse -Filter makensis.exe -ErrorAction SilentlyContinue |
         Select-Object -First 1
    if ($m) { return $m.FullName }
    return $null
}

$mk = Find-Makensis
if (-not $mk) {
    Write-Host "makensis not found - fetching portable NSIS $NsisVersion ..."
    $tools = Join-Path $PSScriptRoot "tools"
    New-Item -ItemType Directory -Path $tools -Force | Out-Null
    $zip = Join-Path $env:TEMP "nsis-$NsisVersion.zip"
    $urls = @("https://downloads.sourceforge.net/project/nsis/NSIS%203/$NsisVersion/nsis-$NsisVersion.zip",
              "https://master.dl.sourceforge.net/project/nsis/NSIS%203/$NsisVersion/nsis-$NsisVersion.zip?viasf=1",
              "https://netcologne.dl.sourceforge.net/project/nsis/NSIS%203/$NsisVersion/nsis-$NsisVersion.zip?viasf=1")
    $ok = $false
    foreach ($u in $urls) {
        try {
            # curl.exe ships with Windows and follows the SourceForge redirects reliably
            & curl.exe -sS -L --max-time 180 -o $zip $u
            if ((Test-Path $zip) -and (Get-Item $zip).Length -gt 1000000) { $ok = $true; Write-Host "  got it from $u"; break }
        } catch { Write-Host "  failed: $u" }
    }
    if (-not $ok) { throw "Could not download NSIS. Install it from https://nsis.sourceforge.io/Download and re-run." }
    Expand-Archive -Path $zip -DestinationPath $tools -Force
    $mk = Find-Makensis
    if (-not $mk) { throw "makensis.exe not found after extracting NSIS." }
}

Write-Host "Using $mk"
Push-Location $PSScriptRoot
try {
    # Keep the installer version in sync with the app: APP_VERSION lives in SabljaReader.py only.
    $appPy = Get-Content (Join-Path $root "SabljaReader.py") -Raw
    if ($appPy -match '(?m)^APP_VERSION\s*=\s*"([^"]+)"') {
        $appVersion = $Matches[1]
    } else {
        throw "Could not read APP_VERSION from SabljaReader.py"
    }
    Write-Host "App version: $appVersion"
    & $mk "/V2" "/DAPP_VERSION=$appVersion" "SabljaReader.nsi"
    if ($LASTEXITCODE -ne 0) { throw "makensis failed (exit $LASTEXITCODE)" }
} finally { Pop-Location }

$out = Join-Path $root "dist\SabljaReader-Setup.exe"
if (-not (Test-Path $out)) { throw "installer was not produced" }
Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  installer: $out  ($([math]::Round((Get-Item $out).Length/1MB,1)) MB)"
Write-Host "  your friend runs it - per-user install, no admin rights, uninstaller included."
