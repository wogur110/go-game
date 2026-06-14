"""Integration test: analysis on/off + auto-analyze stepping (needs GPU)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDeadlineTimer, QEventLoop  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.engine.engine_manager import EngineManager  # noqa: E402
from app.game_controller import GameController, PlayerKind  # noqa: E402
from app.goban import BLACK, WHITE  # noqa: E402
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
    c = GameController(engine)
    c.set_player(BLACK, PlayerKind.HUMAN)
    c.set_player(WHITE, PlayerKind.HUMAN)
    c._moves = list(sample_position(19).moves)[:5]   # short game so auto reaches the end fast
    c._view = 5

    ready = {"v": False}
    engine.enginesReady.connect(lambda: ready.__setitem__("v", True))
    engine.start()
    _pump(app, lambda: ready["v"], 180)

    # analysis on/off
    c.set_analysis_enabled(False)
    print("after off: analysis_enabled =", c.analysis_enabled)
    c.set_analysis_enabled(True)
    print("after on : analysis_enabled =", c.analysis_enabled)

    # auto-analyze from the start to the end
    c.navigate(0)
    c.set_auto_analyze(True)
    print("auto started; view =", c.view_index)
    _pump(app, lambda: not c.auto_analyzing, 60)
    print("auto finished; view =", c.view_index, "auto =", c.auto_analyzing,
          "history points =", len(c.winrate_history()))
    ok = (c.view_index == 5 and not c.auto_analyzing and len(c.winrate_history()) >= 4)
    engine.shutdown()
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
