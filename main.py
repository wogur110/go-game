"""Baduk Studio — entry point.

    python main.py                # launch the GUI
    python main.py --download     # fetch the KataGo engine + networks (forwards args)
    python main.py --smoke        # headless human→AI round-trip (needs the engine/GPU)
    python main.py --build-smoke  # UI + rules + SGF self-check, NO engine (CI / packaging)
"""

from __future__ import annotations

import sys


def main() -> int:
    if "--download" in sys.argv:
        sys.argv.remove("--download")
        from download_katago import main as download_main
        return download_main()

    if "--build-smoke" in sys.argv:
        from app.build_smoke import run_build_smoke
        return run_build_smoke()

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

    if not engine.available:
        from app.download_dialog import prompt_if_missing
        prompt_if_missing(window, engine)   # first-run: offer to fetch KataGo

    engine.start()  # if still missing, emits engineError; the app runs human-only

    code = app.exec()
    engine.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
