# PyInstaller spec for Baduk Studio (onedir).
#   pyinstaller --noconfirm baduk_studio.spec   ->   dist/BadukStudio/
#
# Bundles the app + KataGo config files. The KataGo binary and neural-net weights
# are NOT bundled (too big, GPU/OS-specific) — they live in engines/ and models/
# next to the app and are fetched at runtime via `BadukStudio --download`.

import os

block_cipher = None

datas = [("configs", "configs")]

# Trim Qt modules we don't use to keep the bundle smaller.
excludes = [
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore",
    "PySide6.QtMultimedia", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf",
    "tkinter", "numpy", "matplotlib", "PIL",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["download_katago", "sgfmill", "sgfmill.sgf", "sgfmill.boards"],
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BadukStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # windowed (no console flash); --build-smoke uses exit code
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BadukStudio",
)
