"""Render the v0.4.0 board features to PNGs (dev tool, offscreen): move order,
candidate PV preview, hover ghost stone."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.engine.engine_manager import EngineManager  # noqa: E402
from app.goban import BLACK, WHITE  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.theme import build_stylesheet  # noqa: E402
from tools.preview_board import sample_position  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())
    win = MainWindow(EngineManager())
    win.resize(1180, 820)
    g = sample_position(19)
    win.controller._moves = list(g.moves)
    win.controller._view = len(g.moves)
    win._on_position()           # passes move_no to the board

    # 1) move order on
    win.board.set_show_order(True)
    a = win.grab().save("/tmp/v4_order.png", "PNG")
    win.board.set_show_order(False)

    # 2) candidate PV preview (simulate hovering a candidate row)
    pv = [(15, 2), (16, 4), (13, 2), (16, 8), (2, 13), (4, 16), (16, 10)]
    win.board.set_pv_preview(pv, WHITE)   # white to move in the sample
    b = win.grab().save("/tmp/v4_pv.png", "PNG")
    win.board.set_pv_preview(None)

    # 3) hover ghost stone
    win.board.set_movable(True)
    win.board._hover_point = (10, 10)
    win.board.update()
    c = win.grab().save("/tmp/v4_ghost.png", "PNG")

    print(f"order={a} pv={b} ghost={c}")
    return 0 if (a and b and c) else 1


if __name__ == "__main__":
    sys.exit(main())
