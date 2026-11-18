#!/usr/bin/env bash
# Linux counterpart of build.ps1: build dist/SabljaReader and publish sources.json next to it.
#
#   ./build.sh
#
# Needs: python3 with tkinter (Fedora: python3-tkinter, Debian/Ubuntu: python3-tk),
#        pip install -r requirements.txt pyinstaller
set -euo pipefail
cd "$(dirname "$0")"

python3 -m PyInstaller --noconfirm SabljaReader.spec
cp -f sources.json dist/sources.json
python3 -c "from assets import make_icon; make_icon(256).save('dist/SabljaReader.png')"
cp -f installer/install-linux.sh dist/install-linux.sh

echo
echo "Done."
echo "  app:  dist/SabljaReader"
echo "  conf: dist/sources.json  (copied from ./sources.json)"
echo "Your library, progress and cache live in dist/data and were left untouched."
echo "Run dist/install-linux.sh to add it to your app menu."
