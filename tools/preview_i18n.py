"""Render the main window in Korean and English to PNGs (dev tool, offscreen)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.engine.engine_manager import EngineManager  # noqa: E402
from app.i18n import I18N  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.theme import build_stylesheet  # noqa: E402
from tools.preview_board import sample_position  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())

    engine = EngineManager()           # not started
    win = MainWindow(engine)
    g = sample_position(19)
    win.controller._moves = list(g.moves)
    win.controller._view = len(g.moves)
    win.resize(1180, 820)

    I18N.set_language("ko")
    win._on_position()
    win.controller._emit_status()
    ko = win.grab().save("/tmp/i18n_ko.png", "PNG")

    I18N.set_language("en")            # triggers live retranslate
    win._on_position()
    en = win.grab().save("/tmp/i18n_en.png", "PNG")

    I18N.set_language("ko")            # restore default for this machine
    print(f"ko={ko} en={en}")
    return 0 if (ko and en) else 1


if __name__ == "__main__":
    sys.exit(main())
