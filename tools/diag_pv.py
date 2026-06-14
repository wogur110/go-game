"""Diagnose the candidate-hover PV chain end-to-end (needs GPU)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDeadlineTimer, QEventLoop, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.engine.engine_manager import EngineManager  # noqa: E402
from app.game_controller import PlayerKind  # noqa: E402
from app.goban import BLACK, WHITE  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from tools.preview_board import sample_position  # noqa: E402


def _pump(app, predicate, timeout_s):
    d = QDeadlineTimer(int(timeout_s * 1000))
    while not predicate() and not d.hasExpired():
        app.processEvents(QEventLoop.AllEvents, 50)


def main() -> int:
    app = QApplication(sys.argv)
    engine = EngineManager()
    if not engine.available:
        print("missing engine")
        return 1
    win = MainWindow(engine)
    win.controller.set_player(BLACK, PlayerKind.HUMAN)
    win.controller.set_player(WHITE, PlayerKind.HUMAN)
    g = sample_position(19)
    win.controller._moves = list(g.moves)
    win.controller._view = len(g.moves)
    win._on_position()

    state = {"ready": False, "an": 0}
    engine.enginesReady.connect(lambda: state.__setitem__("ready", True))
    win.controller.analysisUpdated.connect(lambda _r: state.__setitem__("an", state["an"] + 1))
    engine.start()
    _pump(app, lambda: state["ready"], 180)
    _pump(app, lambda: state["an"] > 0, 60)

    sb = win.sidebar
    print("viewport mouseTracking:", sb.candidates.viewport().hasMouseTracking())
    print("candidates count:", sb.candidates.count())
    if sb.candidates.count():
        it = sb.candidates.item(0)
        pv = it.data(Qt.UserRole + 1)
        print("item0 text:", repr(it.text().strip()))
        print("item0 pv points:", pv[:6] if pv else pv, "...len=", len(pv) if pv else 0)
    res = win.controller._last_analysis
    if res and res.moves:
        print("engine moves[0].pv:", res.moves[0].pv[:8], "len=", len(res.moves[0].pv))

    got = {}
    sb.pvPreview.connect(lambda d: got.__setitem__("d", d))
    if sb.candidates.count():
        sb._on_candidate_hover(sb.candidates.item(0))
    print("hover emitted pvPreview:", "yes" if got.get("d") else "no",
          "points=" + str(len(got["d"][0])) if got.get("d") else "")
    engine.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
