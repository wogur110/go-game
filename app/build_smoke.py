"""Engine-free self-check for the packaged build (CI / no GPU).

    python main.py --build-smoke

Verifies the bundle actually loads and the non-engine half works: PySide6 +
sgfmill import, the main window builds and renders offscreen, the rules engine
captures/passes correctly, and SGF round-trips. The KataGo engine is NOT started
(CI runners have no GPU/binary) — the app must degrade gracefully without it.

Exit 0 on success; writes build_smoke_error.log + exit 1 on failure.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _log_path() -> Path:
    base = (Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False) else Path.cwd())
    return base / "build_smoke_error.log"


def run_build_smoke() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication

        from app.engine.engine_manager import EngineManager
        from app.goban import BLACK, EMPTY, WHITE, Goban
        from app.main_window import MainWindow
        from app.sgf_io import from_sgf, to_sgf
        from app.theme import build_stylesheet

        app = QApplication(sys.argv)
        app.setStyleSheet(build_stylesheet())

        # The window builds without starting the engine (graceful when KataGo absent).
        engine = EngineManager()
        window = MainWindow(engine)
        window.resize(900, 640)
        pix = window.grab()
        assert pix.width() > 0 and pix.height() > 0, "window did not render"

        # Rules sanity: a capture.
        g = Goban(size=5)
        for color, mv in [(BLACK, (0, 0)), (WHITE, (1, 0)), (BLACK, (4, 4))]:
            g.play(mv, color)
        assert g.play((0, 1), WHITE) == [(0, 0)], "capture failed"
        assert g.get((0, 0)) == EMPTY

        # SGF round-trip.
        moves = [(BLACK, (3, 3)), (WHITE, None), (BLACK, (15, 15))]
        info = from_sgf(to_sgf(moves, 19, 7.5))
        assert info["moves"] == moves, "SGF round-trip mismatch"

        print("build smoke OK")
        return 0
    except Exception:
        report = traceback.format_exc()
        try:
            _log_path().write_text(report, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        try:
            sys.stderr.write(report)
        except Exception:  # noqa: BLE001
            pass
        return 1


if __name__ == "__main__":
    sys.exit(run_build_smoke())
