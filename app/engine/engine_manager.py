"""Qt wrapper that owns both KataGo clients and marshals results to the GUI.

Mirrors Chess Studio's EngineManager: an *analysis* role (b28, full strength →
eval/overlays) and a *play* role (human-net GTP → rank-based moves). Engines
start on a background thread (model load is slow); the play role runs genmoves on
its own worker thread with a latest-wins queue so stale requests are dropped.
Results come back as Qt signals (queued onto the GUI thread).
"""

from __future__ import annotations

import queue
import threading
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from ..i18n import t
from .analysis_client import AnalysisClient
from .discovery import find_config, find_katago, find_model
from .gtp_client import GtpClient
from .networks import NETWORKS

_STOP = object()

GtpMove = Tuple[str, str]  # (color letter "B"/"W", vertex)


class EngineManager(QObject):
    analysisReady = Signal(int, object)   # generation, AnalysisResult
    moveReady = Signal(int, str)          # generation, vertex ("q16" | "pass" | "resign")
    engineError = Signal(str)
    enginesReady = Signal()
    engineState = Signal(str)             # "missing" | "loading" | "ready" | "error"
    estimateReady = Signal(object)        # high-visit AnalysisResult for a score estimate

    def __init__(self, board_size: int = 19, komi: float = 7.5, rules: str = "chinese",
                 analysis_visits: int = 600, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.board_size = board_size
        self.komi = komi
        self.rules = rules
        self.analysis_visits = analysis_visits
        self._katago = find_katago()
        self._analysis_model = find_model(NETWORKS["b28"].filename)
        self._play_model = self._analysis_model        # human-net play searches with b28
        self._human = find_model(NETWORKS["human"].filename)
        self._analysis_network = "b28"
        self._analysis_cfg = find_config("analysis.cfg")
        self._gtp_cfg = find_config("gtp_human.cfg")
        self._analysis: Optional[AnalysisClient] = None
        self._play: Optional[GtpClient] = None
        self._play_queue: "queue.Queue" = queue.Queue()
        self._play_thread: Optional[threading.Thread] = None
        self._ready = False

    @property
    def available(self) -> bool:
        return all([self._katago, self._analysis_model, self._human,
                    self._analysis_cfg, self._gtp_cfg])

    @property
    def ready(self) -> bool:
        return self._ready

    def rescan(self) -> None:
        """Re-resolve engine/model/config paths (e.g. after an in-app download)."""
        self._katago = find_katago()
        self._analysis_model = find_model(NETWORKS["b28"].filename)
        self._play_model = self._analysis_model
        self._human = find_model(NETWORKS["human"].filename)
        self._analysis_cfg = find_config("analysis.cfg")
        self._gtp_cfg = find_config("gtp_human.cfg")

    def missing(self) -> List[str]:
        items = {"katago": self._katago, "b28": self._analysis_model,
                 "human-net": self._human, "analysis.cfg": self._analysis_cfg,
                 "gtp_human.cfg": self._gtp_cfg}
        return [k for k, v in items.items() if not v]

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        if not self.available:
            self.engineState.emit("missing")
            self.engineError.emit(t("err.missing", items=", ".join(self.missing())))
            return
        self.engineState.emit("loading")
        threading.Thread(target=self._start_engines, name="engine-start", daemon=True).start()

    def _start_engines(self) -> None:
        try:
            started_model = self._analysis_model
            self._analysis = AnalysisClient(
                self._katago, self._analysis_cfg, started_model,
                self._on_analysis_result, self.engineError.emit)
            self._analysis.start()
            self._play = GtpClient(
                self._katago, self._gtp_cfg, self._play_model, self._human,
                board_size=self.board_size, komi=self.komi, rules=self.rules)
            self._play.start()
            self._play_thread = threading.Thread(
                target=self._play_loop, name="engine-play", daemon=True)
            self._play_thread.start()
            self._ready = True
            # A network switch during the (slow) load updated _analysis_model after
            # we captured started_model — honour it now that we're ready.
            if self._analysis_model != started_model:
                self._restart_analysis()
            self.engineState.emit("ready")
            self.enginesReady.emit()
        except Exception as exc:  # noqa: BLE001
            self.engineState.emit("error")
            self.engineError.emit(t("err.start_failed", exc=exc))

    def _restart_analysis(self) -> None:
        if self._analysis:
            self._analysis.stop()
        self._analysis = AnalysisClient(
            self._katago, self._analysis_cfg, self._analysis_model,
            self._on_analysis_result, self.engineError.emit)
        self._analysis.start()

    def set_rules(self, komi: float, rules: str) -> None:
        """Update komi/rules (e.g. after loading an SGF) for analysis and play."""
        self.komi = komi
        self.rules = rules
        if self._play is not None:
            try:
                self._play.set_komi_rules(komi, rules)
            except Exception:  # noqa: BLE001
                pass

    # -- analysis -------------------------------------------------------------

    def request_analysis(self, moves: List[GtpMove], generation: int) -> None:
        if not self._ready or not self._analysis:
            return
        self._analysis.analyze(
            str(generation), moves, board_size=self.board_size, komi=self.komi,
            rules=self.rules, max_visits=self.analysis_visits, include_ownership=True)

    def request_estimate(self, moves: List[GtpMove], visits: int = 1500) -> bool:
        """One-shot high-visit analysis (with ownership) for a precise score estimate.
        Returns False if the query could not be sent."""
        if not self._ready or not self._analysis:
            return False
        return self._analysis.analyze(
            "est", moves, board_size=self.board_size, komi=self.komi,
            rules=self.rules, max_visits=visits, include_ownership=True)

    def _on_analysis_result(self, id_str: str, result) -> None:
        if id_str == "est":
            self.estimateReady.emit(result)
            return
        try:
            gen = int(id_str)
        except (TypeError, ValueError):
            return
        self.analysisReady.emit(gen, result)

    @property
    def analysis_network(self) -> str:
        return self._analysis_network

    def set_analysis_network(self, key: str) -> bool:
        """Switch the analysis network (e.g. b28 <-> b18); restarts that engine."""
        net = NETWORKS.get(key)
        if not net or net.role != "analysis":
            return False
        if key == self._analysis_network and self._analysis is not None:
            return True
        model = find_model(net.filename)
        if not model:
            self.engineError.emit(t("err.net_missing", label=net.label, key=key))
            return False
        self._analysis_model = model
        self._analysis_network = key
        if self._ready:
            self._restart_analysis()      # not ready yet → applied in _start_engines
        return True

    # -- play (human net) -----------------------------------------------------

    def request_move(self, moves: List[GtpMove], generation: int,
                     color: str, profile: str) -> None:
        if not self._ready:
            return
        self._play_queue.put((generation, list(moves), color, profile))

    def _play_loop(self) -> None:
        while True:
            job = self._play_queue.get()
            while True:  # drain to the newest request
                try:
                    nxt = self._play_queue.get_nowait()
                except queue.Empty:
                    break
                job = nxt
            if job is _STOP:
                break
            generation, moves, color, profile = job
            try:
                assert self._play
                self._play.set_profile(profile)
                self._play.set_position(moves)
                vertex = self._play.genmove(color)
                self.moveReady.emit(generation, vertex)
            except Exception as exc:  # noqa: BLE001
                self.engineError.emit(t("err.play", exc=exc))

    # -- shutdown -------------------------------------------------------------

    def shutdown(self) -> None:
        self._ready = False
        self._play_queue.put(_STOP)
        if self._play:
            self._play.stop()
        if self._analysis:
            self._analysis.stop()
