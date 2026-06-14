"""Render the first-run engine-download dialog to a PNG (dev tool, offscreen)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import download_katago  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.download_dialog import DownloadDialog  # noqa: E402
from app.theme import build_stylesheet  # noqa: E402


def main() -> int:
    assert callable(download_katago.download_all)
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dialog_preview.png"
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())
    d = DownloadDialog()
    d._on_progress("kata1-b28c512nbt-...bin.gz  120 / 259 MB", 0.46)
    d.resize(480, 240)
    ok = d.grab().save(out, "PNG")
    print(f"{'saved' if ok else 'FAILED'} {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
