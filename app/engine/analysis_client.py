"""Client for ``katago analysis`` — JSON queries on stdin, JSON results on stdout.

This is the Go analogue of Chess Studio's *analysis* engine. KataGo's analysis
engine handles its own queueing and runs the neural net on the GPU; we just send
one query per position change and route results back by query id. Stale results
(an id older than the latest) are ignored by the caller via the id.

The client is Qt-agnostic: results and errors come back through plain callbacks,
which the Qt ``EngineManager`` (added with the GUI) marshals onto the GUI thread.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from typing import Callable, List, Optional, Tuple

from .coords import from_gtp
from .env import engine_env
from .types import AnalysisResult, MoveInfo


def _popen_kwargs() -> dict:
    kwargs: dict = {"env": engine_env()}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


class AnalysisClient:
    """Drives a single ``katago analysis`` subprocess."""

    def __init__(
        self,
        katago_path: str,
        config_path: str,
        model_path: str,
        on_result: Callable[[str, AnalysisResult], None],
        on_error: Callable[[str], None],
    ) -> None:
        self._katago = katago_path
        self._config = config_path
        self._model = model_path
        self._on_result = on_result
        self._on_error = on_error
        self._proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._stderr_reader: Optional[threading.Thread] = None
        self._write_lock = threading.Lock()
        self._sizes: dict[str, int] = {}
        self._alive = False

    # -- lifecycle --

    def start(self) -> bool:
        try:
            self._proc = subprocess.Popen(
                [self._katago, "analysis", "-config", self._config, "-model", self._model],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                **_popen_kwargs(),
            )
        except Exception as exc:  # noqa: BLE001
            self._on_error(f"KataGo(analysis) 시작 실패: {exc}")
            return False
        self._alive = True
        self._reader = threading.Thread(
            target=self._read_stdout, name="kata-analysis-out", daemon=True)
        self._stderr_reader = threading.Thread(
            target=self._read_stderr, name="kata-analysis-err", daemon=True)
        self._reader.start()
        self._stderr_reader.start()
        return True

    @property
    def alive(self) -> bool:
        return self._alive and self._proc is not None and self._proc.poll() is None

    # -- requests --

    def analyze(
        self,
        analysis_id: str,
        moves: List[Tuple[str, str]],
        *,
        board_size: int,
        komi: float,
        rules: str,
        max_visits: int,
        include_ownership: bool = True,
    ) -> None:
        """Queue an analysis of the position reached by ``moves`` (``[(color, vertex)]``)."""
        if not self.alive:
            return
        query = {
            "id": analysis_id,
            "moves": [[c, v] for c, v in moves],
            "rules": rules,
            "komi": komi,
            "boardXSize": board_size,
            "boardYSize": board_size,
            "maxVisits": max_visits,
            "includeOwnership": include_ownership,
            "includePolicy": False,
        }
        line = json.dumps(query) + "\n"
        with self._write_lock:
            self._sizes[analysis_id] = board_size
            try:
                assert self._proc and self._proc.stdin
                self._proc.stdin.write(line)
                self._proc.stdin.flush()
            except Exception as exc:  # noqa: BLE001
                self._on_error(f"KataGo(analysis) 쓰기 실패: {exc}")

    # -- reader threads --

    def _read_stdout(self) -> None:
        proc = self._proc
        assert proc and proc.stdout
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in obj:
                self._on_error(f"KataGo(analysis): {obj['error']}")
                continue
            if obj.get("isDuringSearch"):
                continue  # M0: act only on the final result, not streaming partials
            result = self._parse(obj)
            if result is not None:
                self._on_result(obj.get("id", ""), result)
        self._alive = False

    def _read_stderr(self) -> None:
        proc = self._proc
        assert proc and proc.stderr
        for _line in proc.stderr:
            # KataGo logs model load / GPU tuning here; only surfaced if it dies.
            pass

    def _parse(self, obj: dict) -> Optional[AnalysisResult]:
        size = self._sizes.pop(obj.get("id", ""), 19)
        move_infos: List[MoveInfo] = []
        for mi in obj.get("moveInfos", []):
            vertex = mi.get("move", "")
            move_infos.append(
                MoveInfo(
                    vertex=vertex,
                    point=from_gtp(vertex, size) if vertex else None,
                    winrate=float(mi.get("winrate", 0.0)),
                    score_lead=float(mi.get("scoreLead", 0.0)),
                    visits=int(mi.get("visits", 0)),
                    prior=float(mi.get("prior", 0.0)),
                    order=int(mi.get("order", 0)),
                    pv=list(mi.get("pv", [])),
                )
            )
        move_infos.sort(key=lambda m: m.order)
        root = obj.get("rootInfo", {})
        return AnalysisResult(
            moves=move_infos,
            root_winrate=float(root.get("winrate", 0.0)),
            root_score_lead=float(root.get("scoreLead", 0.0)),
            board_size=size,
            visits=int(root.get("visits", 0)),
            ownership=obj.get("ownership"),
        )

    # -- shutdown --

    def stop(self) -> None:
        self._alive = False
        proc, self._proc = self._proc, None
        if not proc:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
