# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

ICON = os.path.join(SPECPATH, '..', 'assets', 'icon.icns')

# tkinterdnd2 ships per-platform tkdnd Tcl binaries that must come along, or
# the frozen app silently loses drag-and-drop and falls back to click-to-browse.
dnd_datas, dnd_binaries, dnd_hidden = collect_all('tkinterdnd2')

a = Analysis(
    ['gui.py'],
    pathex=[os.path.join(SPECPATH, '..', 'gcpad'), os.path.join(SPECPATH, 'weather')],
    binaries=dnd_binaries,
    datas=dnd_datas + [(os.path.join(SPECPATH, '..', 'gcpad', 'patches.json'), 'gcpad')],
    hiddenimports=dnd_hidden,
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
    [],
    exclude_binaries=True,
    name='ACCF-Patcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ACCF-Patcher',
)
app = BUNDLE(
    coll,
    name='ACCF-Patcher.app',
    icon=ICON,
    bundle_identifier='net.quatric.accf-sdhc-patcher',
)
