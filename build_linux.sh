#!/usr/bin/env bash
# Build the Baduk Studio Linux bundle -> dist/BadukStudio/
# (PyInstaller can't cross-compile; run build_windows.bat on Windows for the .exe.)
set -euo pipefail
cd "$(dirname "$0")"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

python -m PyInstaller --noconfirm baduk_studio.spec

echo
echo "Built: dist/BadukStudio/BadukStudio"
echo "Fetch the engine once next to it:  dist/BadukStudio/BadukStudio --download"
