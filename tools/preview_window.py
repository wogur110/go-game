"""Render the assembled main window (board + control panel) to a PNG (dev tool).

    QT_QPA_PLATFORM=offscreen python tools/preview_window.py [out.png]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.engine.engine_manager import EngineManager  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.theme import build_stylesheet  # noqa: E402
from tools.preview_board import sample_position  # noqa: E402


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/window_preview.png"
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())

    engine = EngineManager()           # not started — we only render
    win = MainWindow(engine)
    g = sample_position(19)
    win.controller._moves = list(g.moves)
    win.controller._view = len(g.moves)
    win.controller._winrate = 0.462
    win._refresh_board()
    win.controller._emit_status()
    win.resize(1040, 760)

    pix = win.grab()
    ok = pix.save(out, "PNG")
    print(f"{'saved' if ok else 'FAILED'} {out} ({pix.width()}x{pix.height()})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
