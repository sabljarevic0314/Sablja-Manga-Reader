Add-Type -AssemblyName System.Drawing
$p = "$env:LOCALAPPDATA\Programs\SabljaReader\SabljaReader.exe"
$i = [System.Drawing.Icon]::ExtractAssociatedIcon($p)
$i.ToBitmap().Save('C:\Coding Projects\Sablja-Manga-Reader\_installed_icon.png')
Write-Host "saved from $p"
