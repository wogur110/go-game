"""Render the board (heatmap candidates) and win-rate graph at full size with
fabricated data, so the Lizzie look is clearly inspectable (no GPU)."""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.board_widget import BoardWidget  # noqa: E402
from app.engine.coords import to_gtp  # noqa: E402
from app.engine.types import AnalysisResult, MoveInfo  # noqa: E402
from app.goban import BLACK, EMPTY  # noqa: E402
from app.theme import build_stylesheet  # noqa: E402
from app.winrate_graph import WinrateGraph  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet())

    # Fabricated candidates with descending win rates (best -> worst): blue -> red.
    pts = [(15, 3), (3, 3), (15, 15), (3, 15), (9, 9), (16, 5), (2, 13), (13, 16)]
    wrs = [0.62, 0.605, 0.575, 0.55, 0.52, 0.49, 0.46, 0.43]
    vis = [3200, 1500, 700, 400, 220, 130, 70, 40]
    moves = [MoveInfo(vertex=to_gtp(p, 19), point=p, winrate=w, score_lead=(w - 0.5) * 30,
                      visits=v, prior=0.1, order=i, pv=[])
             for i, (p, w, v) in enumerate(zip(pts, wrs, vis))]
    result = AnalysisResult(moves=moves, root_winrate=0.62, root_score_lead=3.6,
                            board_size=19, visits=6000, ownership=None)

    board = BoardWidget(size=19)
    board.resize(820, 820)
    board.set_position([EMPTY] * 361, 19, None, BLACK)
    board.set_analysis(result)
    b = board.grab().save("/tmp/lizzie_board.png", "PNG")

    graph = WinrateGraph()
    graph.resize(900, 120)
    hist = {i: 0.5 + 0.34 * math.sin(i * 0.45) + 0.05 * math.cos(i * 0.2) for i in range(81)}
    graph.set_data(hist, 80, 52)
    g = graph.grab().save("/tmp/lizzie_graph.png", "PNG")

    print(f"board={b} graph={g}")
    return 0 if (b and g) else 1


if __name__ == "__main__":
    sys.exit(main())
