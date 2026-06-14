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

from PySide6.QtCore import QObject, QTimer, Signal

from ..i18n import t
from .analysis_client import AnalysisClient
from .discovery import find_config, find_katago, find_model
from .gtp_client import GtpClient
from .networks import NETWORKS

_STOP = object()

GtpMove = Tuple[str, str]  # (color letter "B"/"W", vertex)

# Lizzie-style continuous analysis: stream partial results and keep deepening
# until the position changes or this many ms elapse (then KataGo is told to stop).
CONTINUOUS_MAX_VISITS = 1_000_000_000
CONTINUOUS_REPORT_EVERY = 0.4
CONTINUOUS_CAP_MS = 180_000          # 3 minutes


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
        self._analysis_query_id: Optional[str] = None   # current continuous query
        self._cap_qid: Optional[str] = None
        self._cap_timer = QTimer(self)                   # single 3-min cap (restarted per request)
        self._cap_timer.setSingleShot(True)
        self._cap_timer.timeout.connect(self._on_cap_timeout)
        self._ready = False
        # Status gating for analysis (re)loads: _restart_seq bumps on every reload;
        # the indicator is "loading" while _ready_seq < _restart_seq and flips to
        # "ready"/"error" only for the latest reload. Guarded by _state_lock so the
        # reader thread's verdict and a concurrent switch can't interleave into a
        # stale "ready". _ready_seq == _restart_seq means the latest reload settled.
        self._restart_seq = 0
        self._ready_seq = 0
        self._spawned_model: Optional[str] = None
        self._state_lock = threading.Lock()

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
            self._spawn_analysis()                 # Popen; the net loads in the background
            self._play = GtpClient(
                self._katago, self._gtp_cfg, self._play_model, self._human,
                board_size=self.board_size, komi=self.komi, rules=self.rules)
            self._play.start()                     # blocks until the play engine is ready
            self._play_thread = threading.Thread(
                target=self._play_loop, name="engine-play", daemon=True)
            self._play_thread.start()
            self._ready = True
            self.enginesReady.emit()               # play works; the net selector can be used
            # Honour a network switch made during the (slow) load, then gate the
            # "ready" light on the analysis net answering — so the dot turns green
            # only once BOTH play and analysis are loaded.
            if self._analysis_model != self._spawned_model:
                self._spawn_analysis()
            self._probe_ready()
        except Exception as exc:  # noqa: BLE001
            with self._state_lock:
                self._ready_seq = self._restart_seq   # mark settled: a late probe can't flip to ready
                self.engineState.emit("error")
            self.engineError.emit(t("err.start_failed", exc=exc))

    def _spawn_analysis(self) -> None:
        """(Re)create the analysis subprocess for the current model and show 'loading'.
        Non-blocking: the old client is stopped on a daemon thread (its proc.wait can
        take up to 3s and must never freeze the GUI on a net switch), and the new net
        loads asynchronously. Readiness is signalled later via _probe_ready. The new
        client's on_exit is stamped with this reload's seq, so a death of the old/
        superseded client can never flip the latest reload's indicator (errors are
        only surfaced, never used to settle the dot)."""
        with self._state_lock:
            self._restart_seq += 1
            seq = self._restart_seq
            self.engineState.emit("loading")
        self._spawned_model = self._analysis_model
        old, self._analysis = self._analysis, None
        self._analysis_query_id = None      # old query belonged to the dead subprocess
        self._cap_timer.stop()
        if old is not None:
            threading.Thread(target=old.stop, name="engine-stop", daemon=True).start()
        client = AnalysisClient(
            self._katago, self._analysis_cfg, self._spawned_model,
            self._on_analysis_result, self.engineError.emit,
            on_exit=lambda s=seq: self._settle(s, "error"))
        self._analysis = client
        client.start()

    def _probe_ready(self) -> None:
        """Hold the status at 'loading' until the (re)loaded analysis net answers a
        tiny warm-up query. KataGo can't analyse until the net is on the GPU, so a
        reply (handled in _on_analysis_result) means it's loaded — only then flip the
        indicator to 'ready'. If the query can't even be queued, fall to 'error' so it
        never hangs on 'loading'."""
        seq = self._restart_seq
        client = self._analysis
        sent = client is not None and client.analyze(
            f"_ready_{seq}", [], board_size=self.board_size, komi=self.komi,
            rules=self.rules, max_visits=2, include_ownership=False)
        if not sent:
            self._settle(seq, "error")

    def _settle(self, seq: int, state: str) -> None:
        """Emit the terminal status for reload ``seq`` (``ready``/``error``) exactly
        once, and only if it is still the latest reload — so a stale probe reply or
        a superseded/dying client's death can't overwrite a newer load's indicator."""
        with self._state_lock:
            if seq == self._restart_seq and self._ready_seq < seq:
                self._ready_seq = seq
                self.engineState.emit(state)

    def _restart_analysis(self) -> None:
        """Swap the analysis engine to the current model (e.g. after a net switch)
        and hold the indicator on 'loading' until the new net is ready."""
        self._spawn_analysis()
        self._probe_ready()

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

    def request_analysis(self, moves: List[GtpMove], generation: int,
                         continuous: bool = True) -> None:
        if not self._ready or not self._analysis:
            return
        # Stop any previous continuous query (and its cap) before the new position.
        if self._analysis_query_id is not None:
            self._analysis.terminate(self._analysis_query_id)
            self._analysis_query_id = None
        self._cap_timer.stop()
        qid = str(generation)
        if continuous:
            self._analysis_query_id = qid
            self._cap_qid = qid
            self._analysis.analyze(
                qid, moves, board_size=self.board_size, komi=self.komi, rules=self.rules,
                max_visits=CONTINUOUS_MAX_VISITS, include_ownership=True,
                report_every=CONTINUOUS_REPORT_EVERY)
            self._cap_timer.start(CONTINUOUS_CAP_MS)
        else:
            self._analysis.analyze(
                qid, moves, board_size=self.board_size, komi=self.komi,
                rules=self.rules, max_visits=self.analysis_visits, include_ownership=True)

    def _on_cap_timeout(self) -> None:
        if self._cap_qid == self._analysis_query_id and self._analysis is not None:
            self._analysis.terminate(self._cap_qid)   # 3-min cap reached; last result stays
            self._analysis_query_id = None

    def stop_analysis(self) -> None:
        """Abort the running continuous analysis (e.g. when analysis is paused)."""
        self._cap_timer.stop()
        if self._analysis_query_id is not None and self._analysis is not None:
            self._analysis.terminate(self._analysis_query_id)
            self._analysis_query_id = None

    def request_estimate(self, moves: List[GtpMove], visits: int = 1500) -> bool:
        """One-shot high-visit analysis (with ownership) for a precise score estimate.
        Returns False if the query could not be sent."""
        if not self._ready or not self._analysis:
            return False
        return self._analysis.analyze(
            "est", moves, board_size=self.board_size, komi=self.komi,
            rules=self.rules, max_visits=visits, include_ownership=True)

    def _on_analysis_result(self, id_str: str, result) -> None:
        if id_str.startswith("_ready_"):        # warm-up probe reply (runs on reader thread)
            try:
                seq = int(id_str[len("_ready_"):])
            except ValueError:
                return
            self._settle(seq, "ready")          # the (re)loaded net answered → ready
            return
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
