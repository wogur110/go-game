"""Headless human→AI integration check (the whole stack on the GPU).

    python main.py --smoke      # or: python -m app.game_smoke

Exits 0 only if: both engines start, a human Black move is accepted, and the
human-net AI replies with a legal White move — driving the real Qt signal path
(engine threads → GUI thread) the GUI uses.
"""

from __future__ import annotations

import os
import sys
import time


def run_smoke(timeout_s: float = 150.0) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QDeadlineTimer, QEventLoop
    from PySide6.QtWidgets import QApplication

    from app.engine.coords import to_gtp
    from app.engine.engine_manager import EngineManager
    from app.game_controller import GameController, PlayerKind
    from app.goban import BLACK, WHITE

    print("대국 통합 점검 (Baduk Studio M1)\n")
    app = QApplication(sys.argv)
    engine = EngineManager()
    if not engine.available:
        print("  ✗ 엔진/네트워크 누락:", ", ".join(engine.missing()))
        return 1

    state: dict = {}
    engine.enginesReady.connect(lambda: state.__setitem__("ready", True))
    engine.engineError.connect(lambda m: state.setdefault("err", m))

    print("[1/3] 엔진 시작 (모델 로딩…)")
    engine.start()
    deadline = QDeadlineTimer(int(timeout_s * 1000))
    while "ready" not in state and "err" not in state and not deadline.hasExpired():
        app.processEvents(QEventLoop.AllEvents, 50)
    if "err" in state:
        print("  ✗", state["err"])
        return 1
    if "ready" not in state:
        print("  ✗ 엔진 시작 시간 초과")
        return 1
    print("  ✓ 엔진 준비 완료")

    controller = GameController(engine)
    controller.set_player(BLACK, PlayerKind.HUMAN)
    controller.set_player(WHITE, PlayerKind.AI)

    print("[2/3] 사람(흑) 4-4 착수 → AI(백) 응수 대기")
    if not controller.make_move((3, 3)):
        print("  ✗ 흑 착수 거부됨")
        return 1
    while controller.total_moves < 2 and not deadline.hasExpired():
        app.processEvents(QEventLoop.AllEvents, 50)
    if controller.total_moves < 2:
        print("  ✗ AI가 응수하지 않음 (시간 초과)")
        return 1

    color, point = controller._moves[-1]
    vtx = to_gtp(point, controller.size)
    assert color == WHITE, color
    print(f"  ✓ AI(백) 응수: {vtx}")

    print("[3/3] 완료 — 사람→AI 대국 왕복 동작 ✓")
    engine.shutdown()
    return 0


def main() -> int:
    start = time.monotonic()
    code = run_smoke()
    print(f"\n({time.monotonic() - start:.1f}s)")
    return code


if __name__ == "__main__":
    sys.exit(main())
