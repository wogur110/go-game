"""Render the main window WITH live KataGo analysis to a PNG (dev tool, needs GPU).

Starts the engine, plays a short opening (both sides human so the AI doesn't
move), waits for analysis of the final position, then grabs the window — so the
PNG shows the win bar, candidate overlay and ownership heatmap for real.

    python tools/preview_window.py [out.png]
"""

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
from app.theme import build_stylesheet  # noqa: E402

OPENING = [(3, 3), (15, 15), (15, 3), (3, 15), (5, 2), (13, 16), (2, 5), (16, 13)]


def _pump(app, predicate, timeout_s):
    deadline = QDeadlineTimer(int(timeout_s * 1000))
    while not predicate() and not deadline.hasExpired():
        app.processEvents(QEventLoop.AllEvents, 50)


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/window_preview.png"
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())

    engine = EngineManager()
    if not engine.available:
        print("missing:", ", ".join(engine.missing()))
        return 1
    win = MainWindow(engine)
    win.resize(1180, 820)

    state = {"ready": False, "analyses": 0}
    engine.enginesReady.connect(lambda: state.__setitem__("ready", True))
    engine.engineError.connect(lambda m: print("ERR:", m))
    win.controller.analysisUpdated.connect(
        lambda _r: state.__setitem__("analyses", state["analyses"] + 1))

    engine.start()
    _pump(app, lambda: state["ready"], 180)

    # Both sides human so nothing auto-moves while we set up the position.
    win.controller.set_player(BLACK, PlayerKind.HUMAN)
    win.controller.set_player(WHITE, PlayerKind.HUMAN)
    for pt in OPENING:
        win.controller.make_move(pt)

    before = state["analyses"]
    _pump(app, lambda: state["analyses"] > before, 60)   # analysis of the final position
    _pump(app, lambda: False, 1.5)                        # let visits accumulate, then repaint

    pix = win.grab()
    ok = pix.save(out, "PNG")
    print(f"{'saved' if ok else 'FAILED'} {out} ({pix.width()}x{pix.height()}) "
          f"analyses={state['analyses']}")
    engine.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
