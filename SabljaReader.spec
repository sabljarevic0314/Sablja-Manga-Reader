# -*- mode: python ; coding: utf-8 -*-
# Single-file build: the exe lands in dist\ right next to dist\sources.json and dist\data,
# which is the layout the app (BASE = folder of the exe) and build.ps1 both expect.

a = Analysis(
    ['SabljaReader.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['miniaudio'],   # lofi radio: backend is imported lazily, so pin it
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SabljaReader',
    icon='SabljaReader.ico',   # exe, taskbar and shortcut logo
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no black console window behind the app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
