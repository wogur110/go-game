"""Client for ``katago gtp`` with the human-trained network — the rank-based,
human-like opponent. The Go analogue of Chess Studio's strength-limited *play*
engine.

GTP is synchronous request/response, so callers should drive this from a worker
thread (the Qt ``EngineManager`` does). Changing the rank restarts the process
with a new ``humanSLProfile`` (KataGo bakes the profile in at launch).
"""

from __future__ import annotations

import os
import subprocess
import threading
from typing import List, Optional, Tuple

from .env import engine_env


def _popen_kwargs() -> dict:
    kwargs: dict = {"env": engine_env()}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


class GtpClient:
    """Drives a single ``katago gtp`` subprocess running the human SL network."""

    def __init__(
        self,
        katago_path: str,
        config_path: str,
        model_path: str,
        human_model_path: str,
        *,
        board_size: int = 19,
        komi: float = 7.5,
        rules: str = "chinese",
        profile: str = "rank_5k",
    ) -> None:
        self._katago = katago_path
        self._config = config_path
        self._model = model_path
        self._human_model = human_model_path
        self._board_size = board_size
        self._komi = komi
        self._rules = rules
        self._profile = profile
        self._proc: Optional[subprocess.Popen] = None
        self._stderr_reader: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # -- lifecycle --

    def start(self) -> None:
        self._proc = subprocess.Popen(
            [
                self._katago, "gtp",
                "-model", self._model,
                "-human-model", self._human_model,
                "-config", self._config,
                "-override-config", f"humanSLProfile={self._profile}",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            **_popen_kwargs(),
        )
        # Drain stderr so KataGo's model-load / GPU-tuning output can't fill the
        # pipe and deadlock the engine (mirrors AnalysisClient).
        self._stderr_reader = threading.Thread(
            target=self._read_stderr, name="kata-gtp-err", daemon=True)
        self._stderr_reader.start()
        self._send(f"boardsize {self._board_size}")
        self._send(f"komi {self._komi}")
        try:
            self._send(f"kata-set-rules {self._rules}")
        except RuntimeError:
            pass  # older binaries: rules already set via config
        self._send("clear_board")

    def _read_stderr(self) -> None:
        proc = self._proc
        if not proc or not proc.stderr:
            return
        for _line in proc.stderr:   # discard; keeps the pipe from backing up
            pass

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def set_profile(self, profile: str) -> None:
        """Change the imitated rank (restarts the engine if it changed)."""
        if profile == self._profile and self.alive:
            return
        self._profile = profile
        self.stop()
        self.start()

    # -- GTP commands --

    def _send(self, command: str) -> str:
        with self._lock:
            proc = self._proc
            if not proc or not proc.stdin or not proc.stdout:
                raise RuntimeError("KataGo(gtp) 프로세스가 없습니다")
            try:
                proc.stdin.write(command + "\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise RuntimeError(f"KataGo(gtp) 쓰기 실패: {exc}") from exc
            # A GTP response is a status line ('=' ok / '?' error) then lines
            # until a blank line.
            status = proc.stdout.readline()
            while status and not (status.startswith("=") or status.startswith("?")):
                status = proc.stdout.readline()
            if status == "":   # EOF: engine closed stdout (crashed / killed / OOM)
                raise RuntimeError(
                    f"KataGo(gtp) 프로세스가 응답 없이 종료됨 (exit={proc.poll()})")
            body = [status.rstrip("\n")]
            while True:
                ln = proc.stdout.readline()
                if ln == "" or ln.strip() == "":
                    break
                body.append(ln.rstrip("\n"))
            text = "\n".join(body)
            if text.startswith("?"):
                raise RuntimeError(text[1:].strip())
            # Strip the leading "= " (and any response id).
            return text[1:].strip()

    def set_position(self, moves: List[Tuple[str, str]]) -> None:
        """Replay ``[(color, vertex)]`` onto a fresh board."""
        self._send("clear_board")
        for color, vertex in moves:
            self._send(f"play {color} {vertex}")

    def genmove(self, color: str) -> str:
        """Ask the human net to choose ``color``'s move. Returns a GTP vertex,
        ``"pass"`` or ``"resign"``."""
        return self._send(f"genmove {color}").lower()

    def set_komi_rules(self, komi: float, rules: str) -> None:
        self._komi = komi
        self._rules = rules
        self._send(f"komi {komi}")
        try:
            self._send(f"kata-set-rules {rules}")
        except RuntimeError:
            pass

    # -- shutdown --

    def stop(self) -> None:
        with self._lock:                  # don't tear down mid-_send
            proc, self._proc = self._proc, None
        if not proc:
            return
        try:
            if proc.stdin:
                proc.stdin.write("quit\n")
                proc.stdin.flush()
            proc.wait(timeout=3)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
