"""Headless KataGo round-trip self-check.

Run after ``python download_katago.py``:

    python -m app.engine.smoke

Exits 0 only if KataGo actually loads on your GPU and replies:
  1. the b28 analysis engine returns candidate moves for the empty board, and
  2. the human-net GTP engine generates a move.

CI and you both use this to confirm the engine + weights + GPU work before the
GUI is wired up. First run may take a while (model load + GPU autotune).
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Optional

from .analysis_client import AnalysisClient
from .discovery import find_config, find_katago, find_model
from .gtp_client import GtpClient
from .networks import NETWORKS
from .types import AnalysisResult, BLACK

BOARD_SIZE = 19
KOMI = 7.5
RULES = "chinese"


def _need(label: str, value: Optional[str], hint: str) -> str:
    if not value:
        print(f"  ✗ {label} 없음 — {hint}")
        raise SystemExit(1)
    print(f"  ✓ {label}: {value}")
    return value


def run_smoke(timeout_s: float = 180.0) -> int:
    print("KataGo 연동 점검 (Baduk Studio M0)\n")
    print("[1/4] 바이너리·가중치·설정 탐색")
    katago = _need("katago", find_katago(), "python download_katago.py 를 먼저 실행하세요")
    b28 = _need("b28 네트워크", find_model(NETWORKS['b28'].filename),
                "python download_katago.py --networks-only")
    human = _need("휴먼넷", find_model(NETWORKS['human'].filename),
                  "python download_katago.py --networks-only")
    analysis_cfg = _need("analysis.cfg", find_config("analysis.cfg"), "configs/ 누락")
    gtp_cfg = _need("gtp_human.cfg", find_config("gtp_human.cfg"), "configs/ 누락")

    # --- 2. analysis engine round-trip ---------------------------------------
    print("\n[2/4] 분석 엔진 시작 + 빈 판 분석 (첫 실행은 모델 로딩/튜닝으로 느릴 수 있음)")
    result_box: dict[str, AnalysisResult] = {}
    error_box: dict[str, str] = {}
    done = threading.Event()

    def on_result(query_id: str, result: AnalysisResult) -> None:
        result_box[query_id] = result
        done.set()

    def on_error(message: str) -> None:
        error_box["err"] = message
        done.set()

    analysis = AnalysisClient(katago, analysis_cfg, b28, on_result, on_error)
    if not analysis.start():
        return 1
    analysis.analyze("smoke", [], board_size=BOARD_SIZE, komi=KOMI,
                     rules=RULES, max_visits=200, include_ownership=True)
    if not done.wait(timeout_s):
        print("  ✗ 시간 초과 — 분석 결과가 오지 않음 (GPU/드라이버 확인)")
        analysis.stop()
        return 1
    if "err" in error_box:
        print(f"  ✗ 오류: {error_box['err']}")
        analysis.stop()
        return 1

    result = result_box.get("smoke")
    if not result or not result.moves:
        print("  ✗ 후보 수가 비어 있음")
        analysis.stop()
        return 1
    print(f"  ✓ 흑 승률 {result.root_winrate * 100:.1f}% · "
          f"집 {result.root_score_lead:+.1f} · 방문 {result.visits}")
    print("  상위 후보:")
    for mi in result.moves[:5]:
        print(f"    {mi.vertex:>4}  승률 {mi.winrate * 100:5.1f}%  "
              f"집 {mi.score_lead:+5.1f}  방문 {mi.visits}")
    has_ownership = result.ownership is not None and len(result.ownership) == BOARD_SIZE ** 2
    print(f"  ✓ ownership 맵 {'수신' if has_ownership else '없음(설정 확인)'}")
    analysis.stop()

    # --- 3. human-net GTP genmove --------------------------------------------
    print("\n[3/4] 휴먼넷(GTP) 시작 + genmove (rank_5k)")
    gtp = GtpClient(katago, gtp_cfg, b28, human, board_size=BOARD_SIZE,
                    komi=KOMI, rules=RULES, profile="rank_5k")
    try:
        gtp.start()
        move = gtp.genmove(BLACK.lower())
        print(f"  ✓ 휴먼넷 흑 첫 수: {move}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ GTP 오류: {exc}")
        gtp.stop()
        return 1
    gtp.stop()

    print("\n[4/4] 완료 — KataGo 분석 + 휴먼넷 대국 모두 동작 ✓")
    return 0


def main() -> int:
    start = time.monotonic()
    code = run_smoke()
    print(f"\n({time.monotonic() - start:.1f}s)")
    return code


if __name__ == "__main__":
    sys.exit(main())
