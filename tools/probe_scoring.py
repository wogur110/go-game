"""Verify two-pass game-over uses KataGo's score (needs GPU)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDeadlineTimer, QEventLoop  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.engine.engine_manager import EngineManager  # noqa: E402
from app.game_controller import PlayerKind  # noqa: E402
from app.goban import BLACK, WHITE  # noqa: E402
from app.main_window import MainWindow  # noqa: E402


def _pump(app, predicate, timeout_s):
    d = QDeadlineTimer(int(timeout_s * 1000))
    while not predicate() and not d.hasExpired():
        app.processEvents(QEventLoop.AllEvents, 50)


def main() -> int:
    app = QApplication(sys.argv)
    engine = EngineManager()
    if not engine.available:
        print("missing:", ", ".join(engine.missing()))
        return 1
    win = MainWindow(engine)
    c = win.controller
    state = {"ready": False, "n": 0}
    engine.enginesReady.connect(lambda: state.__setitem__("ready", True))
    c.analysisUpdated.connect(lambda _r: state.__setitem__("n", state["n"] + 1))
    engine.start()
    _pump(app, lambda: state["ready"], 180)

    c.set_player(BLACK, PlayerKind.HUMAN)
    c.set_player(WHITE, PlayerKind.HUMAN)
    for pt in [(3, 3), (15, 15), (15, 3), (3, 15), (9, 9)]:
        c.make_move(pt)
    c.pass_move()      # black pass
    c.pass_move()      # white pass -> two-pass game over

    before = state["n"]
    _pump(app, lambda: state["n"] > before, 60)   # scoring analysis of the terminal position

    print("game_over:", c.game_over)
    print("last_analysis present:", c._last_analysis is not None)
    print("final score (black-rel):", None if c._final_score() is None else round(c._final_score(), 1))
    print("result:", c._result_text())
    print("SGF RE:", c._sgf_result())
    ok = c.game_over and c._last_analysis is not None and "KataGo" in c._result_text()
    engine.shutdown()
    print("\n", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
