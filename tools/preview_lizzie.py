"""Render the Lizzie-style UI (heatmap candidates + win-rate graph) on the GPU."""

from __future__ import annotations

import math
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
from app.theme import build_stylesheet  # noqa: E402
from tools.preview_board import sample_position  # noqa: E402


def _pump(app, predicate, timeout_s):
    d = QDeadlineTimer(int(timeout_s * 1000))
    while not predicate() and not d.hasExpired():
        app.processEvents(QEventLoop.AllEvents, 50)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())
    engine = EngineManager()
    if not engine.available:
        print("missing:", ", ".join(engine.missing()))
        return 1
    win = MainWindow(engine)
    win.resize(1280, 940)
    win.controller.set_player(BLACK, PlayerKind.HUMAN)
    win.controller.set_player(WHITE, PlayerKind.HUMAN)
    g = sample_position(19)
    win.controller._moves = list(g.moves)
    win.controller._view = len(g.moves)
    # fabricate a win-rate curve so the bottom graph shows a real-looking line
    total = len(g.moves)
    win.controller._winrate_history = {i: 0.5 + 0.34 * math.sin(i * 0.6) for i in range(total + 1)}
    win._on_position()

    state = {"ready": False, "an": 0}
    engine.enginesReady.connect(lambda: state.__setitem__("ready", True))
    win.controller.analysisUpdated.connect(lambda _r: state.__setitem__("an", state["an"] + 1))
    engine.start()
    _pump(app, lambda: state["ready"], 180)
    _pump(app, lambda: state["an"] > 0, 60)   # one real analysis -> heatmap candidates
    _pump(app, lambda: False, 0.5)

    ok = win.grab().save("/tmp/lizzie.png", "PNG")
    print(f"saved={ok} analyses={state['an']}")
    engine.shutdown()
    return 0 if ok and state["an"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
