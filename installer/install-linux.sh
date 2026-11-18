#!/usr/bin/env bash
# Per-user Linux install (no root): copies the built app to ~/.local/share/SabljaReader and adds
# an app-menu entry. Run it from the folder that holds SabljaReader (dist/ or an unpacked release).
#
#   ./install-linux.sh             install or update
#   ./install-linux.sh --uninstall remove the app and menu entry (keeps your data/ folder)
#
# Like the Windows installer, data/ (library, progress, cache, downloads) is never touched.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/SabljaReader"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ENTRY="$APPS/sablja-reader.desktop"

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$ENTRY" "$DEST/SabljaReader" "$DEST/SabljaReader.png" "$DEST/sources.json"
    echo "Removed Sablja Reader. Your data is still in $DEST/data"
    exit 0
fi

[ -x "$SRC/SabljaReader" ] || { echo "SabljaReader not found next to this script (build it with ./build.sh)"; exit 1; }
mkdir -p "$DEST" "$APPS"
if [ -f "$DEST/data/db.json" ]; then
    mkdir -p "$DEST/data/backups"
    cp -f "$DEST/data/db.json" "$DEST/data/backups/db-before-install-$(date +%Y%m%d-%H%M%S).json"
fi
install -m 755 "$SRC/SabljaReader" "$DEST/SabljaReader"
install -m 644 "$SRC/sources.json" "$DEST/sources.json"
[ -f "$SRC/SabljaReader.png" ] && install -m 644 "$SRC/SabljaReader.png" "$DEST/SabljaReader.png"

cat > "$ENTRY" <<DESK
[Desktop Entry]
Type=Application
Name=Sablja Reader
Comment=Manga, manhwa and webtoon reader
Exec="$DEST/SabljaReader"
Icon=$DEST/SabljaReader.png
Terminal=false
Categories=Graphics;Viewer;
StartupWMClass=SabljaReader
DESK
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" >/dev/null 2>&1 || true
echo "Installed to $DEST (data stays in $DEST/data). Look for 'Sablja Reader' in your app menu."
