"""Baduk Studio — entry point.

    python main.py            # launch the GUI
    python main.py --smoke    # headless human→AI round-trip self-check (CI / no display)
"""

from __future__ import annotations

import sys


def main() -> int:
    if "--smoke" in sys.argv:
        from app.game_smoke import run_smoke
        return run_smoke()

    from PySide6.QtWidgets import QApplication

    from app import APP_NAME
    from app.engine.engine_manager import EngineManager
    from app.main_window import MainWindow
    from app.theme import build_stylesheet

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())

    engine = EngineManager()
    window = MainWindow(engine)
    window.show()
    engine.start()  # loads models on a background thread

    code = app.exec()
    engine.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
