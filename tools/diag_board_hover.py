"""Verify on-board candidate hover -> PV preview (offscreen, no GPU)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.board_widget import BoardWidget  # noqa: E402
from app.engine.coords import from_gtp  # noqa: E402
from app.engine.types import AnalysisResult, MoveInfo  # noqa: E402
from app.goban import BLACK, EMPTY  # noqa: E402
from app.theme import build_stylesheet  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet())
    pv = ["Q16", "D4", "Q4", "C16", "K10", "R6"]
    moves = [
        MoveInfo("Q16", (15, 3), 0.62, 3.0, 3000, 0.2, 0, pv),
        MoveInfo("D16", (3, 3), 0.58, 2.0, 800, 0.1, 1, ["D16", "Q4"]),
    ]
    result = AnalysisResult(moves=moves, root_winrate=0.62, root_score_lead=3.0,
                            board_size=19, visits=4000, ownership=None)
    board = BoardWidget(size=19)
    board.resize(820, 820)
    board.set_position([EMPTY] * 361, 19, None, BLACK)
    board.set_analysis(result)

    at_cand = board._candidate_pv_at((15, 3))            # hovering the Q16 candidate
    at_empty = board._candidate_pv_at((10, 10))
    expect = [from_gtp(v, 19) for v in pv]
    print("pv at candidate:", at_cand)
    print("pv at empty:", at_empty)
    ok = (at_cand == expect and at_empty is None)

    board._pv_preview = at_cand                          # simulate the hover
    board._pv_start_color = BLACK
    saved = board.grab().save("/tmp/board_hover.png", "PNG")
    print("OK" if (ok and saved) else "FAIL")
    return 0 if (ok and saved) else 1


if __name__ == "__main__":
    sys.exit(main())
