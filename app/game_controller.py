"""Game state, player modes, navigation and engine wiring.

The single source of truth for a game: a flat move list (replayed onto a fresh
:class:`~app.goban.Goban` for any position — replay is cheap), Human/AI per
colour, a generation counter that discards stale engine results, undo and
non-destructive review. It drives the human-net opponent and live analysis.
"""

from __future__ import annotations

from enum import Enum, auto
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

from .engine.coords import from_gtp, to_gtp
from .goban import BLACK, COLOR_LETTER, WHITE, Goban, opponent
from .i18n import t
from .sgf_io import from_sgf, to_sgf

Point = Tuple[int, int]
Move = Tuple[int, Optional[Point]]   # (color, point|None-for-pass)

AI_DELAY_MS = 200
AI_VS_AI_DELAY_MS = 500
AUTO_ANALYZE_DELAY_MS = 550            # pause on each position while auto-analyzing


class PlayerKind(Enum):
    HUMAN = auto()
    AI = auto()


class GameController(QObject):
    positionChanged = Signal()         # board content / view changed
    statusChanged = Signal(str)
    analysisUpdated = Signal(object)   # AnalysisResult for the current view
    estimateReady = Signal(object)     # high-visit AnalysisResult for a score estimate
    analysisEnabledChanged = Signal(bool)
    autoAnalyzeChanged = Signal(bool)

    def __init__(self, engine, size: int = 19, komi: float = 7.5,
                 rules: str = "chinese", parent: Optional[QObject] = None):
        super().__init__(parent)
        self.engine = engine
        self.size = size
        self.komi = komi
        self.rules = rules
        self._moves: List[Move] = []
        self._setup_black: List[Point] = []
        self._setup_white: List[Point] = []
        self._players = {BLACK: PlayerKind.HUMAN, WHITE: PlayerKind.HUMAN}
        self._rank = "rank_9d"
        self._generation = 0
        self._view = 0
        self._thinking = False
        self._resigned: Optional[int] = None
        self._winrate: Optional[float] = None
        self._last_analysis = None
        self._pending_analysis_index = 0   # move-index the in-flight analysis is for
        self._last_analysis_index = -1     # move-index _last_analysis describes
        self._estimate_gen = -1            # generation a score estimate was requested at
        self._winrate_history: dict = {}   # move index -> Black win rate (for the graph)
        self._analysis_enabled = True      # space toggles continuous analysis on/off
        self._auto_analyze = False         # auto-step through the game analysing each move

        engine.moveReady.connect(self._on_engine_move)
        engine.analysisReady.connect(self._on_analysis)
        engine.estimateReady.connect(self._on_estimate)
        engine.enginesReady.connect(self._on_engines_ready)
        engine.engineError.connect(self.statusChanged.emit)

    # -- board reconstruction -------------------------------------------------

    def board_at(self, n: int) -> Goban:
        g = Goban(self.size, self.komi)
        if self._setup_black or self._setup_white:
            g.place_setup(self._setup_black, self._setup_white)
        for color, mv in self._moves[:n]:
            g.play(mv, color)
        return g

    def live_board(self) -> Goban:
        return self.board_at(len(self._moves))

    def view_board(self) -> Goban:
        return self.board_at(self._view)

    @property
    def is_live(self) -> bool:
        return self._view == len(self._moves)

    @property
    def total_moves(self) -> int:
        return len(self._moves)

    @property
    def view_index(self) -> int:
        return self._view

    @property
    def game_over(self) -> bool:
        return self._resigned is not None or self.live_board().is_over

    def player(self, color: int) -> PlayerKind:
        return self._players[color]

    def _gtp_moves(self, n: Optional[int] = None) -> List[Tuple[str, str]]:
        n = len(self._moves) if n is None else n
        return [(COLOR_LETTER[c], to_gtp(mv, self.size)) for c, mv in self._moves[:n]]

    # -- mutations ------------------------------------------------------------

    def new_game(self) -> None:
        self._moves = []
        self._setup_black = []
        self._setup_white = []
        self._view = 0
        self._resigned = None
        self._winrate = None
        self._last_analysis = None
        self._last_analysis_index = -1
        self._winrate_history = {}
        self._refresh()

    def make_move(self, point: Optional[Point]) -> bool:
        """Apply a HUMAN move (``None`` = pass). Returns False if not allowed."""
        if not self.is_live:
            self._moves = self._moves[:self._view]      # branch from the reviewed position
            self._prune_winrate_history()
        live = self.live_board()
        if self._resigned is not None or live.is_over:
            return False
        color = live.to_move
        if self._players[color] != PlayerKind.HUMAN:
            return False
        if point is not None and not live.is_legal(point, color):
            return False
        self._moves.append((color, point))
        self._view = len(self._moves)
        self._refresh()
        return True

    def pass_move(self) -> bool:
        return self.make_move(None)

    def resign(self) -> None:
        if self.game_over:
            return
        self._resigned = self.live_board().to_move
        self._generation += 1
        self._thinking = False
        self.positionChanged.emit()
        self._emit_status()

    def undo(self) -> None:
        if not self._moves:
            return
        self._resigned = None
        self._moves.pop()
        humans = [c for c, k in self._players.items() if k == PlayerKind.HUMAN]
        if len(humans) == 1 and self._moves and self.live_board().to_move != humans[0]:
            self._moves.pop()
        self._view = len(self._moves)
        self._prune_winrate_history()
        self._refresh()

    def navigate(self, index: int) -> None:
        self._view = max(0, min(index, len(self._moves)))
        self._generation += 1
        self._thinking = False   # bumping generation invalidated any in-flight move
        self._winrate = None
        self.positionChanged.emit()
        self._emit_status()
        self._request_analysis()
        self._maybe_ai()         # re-arm the AI if we are back at the live position

    def step(self, delta: int) -> None:
        self.navigate(self._view + delta)

    def set_player(self, color: int, kind: PlayerKind) -> None:
        self._players[color] = kind
        self._refresh()

    def set_rank(self, rank: str) -> None:
        self._rank = rank

    def refresh_analysis(self) -> None:
        """Re-request analysis for the current view (e.g. after switching network)."""
        self._request_analysis()

    def request_estimate(self) -> bool:
        """Ask for a precise (high-visit) score estimate of the current view."""
        if not self.engine.ready:
            return False
        self._estimate_gen = self._generation
        return self.engine.request_estimate(self._gtp_moves(self._view))

    def _on_estimate(self, result) -> None:
        if self._generation != self._estimate_gen:
            return   # position changed since the estimate was requested — drop it
        self.estimateReady.emit(result)

    # -- SGF ------------------------------------------------------------------

    def save_sgf(self, path: str) -> None:
        data = to_sgf(self._moves, self.size, self.komi, rules=self.rules,
                      setup_black=self._setup_black, setup_white=self._setup_white,
                      result=self._sgf_result())
        Path(path).write_bytes(data)

    def load_sgf(self, path: str) -> bool:
        info = from_sgf(Path(path).read_bytes())
        if info["size"] != self.size:
            self.statusChanged.emit(
                t("status.unsupported_size", size=info["size"], n=self.size))
            return False
        self.komi = info["komi"]
        self.rules = info["rules"]
        self.engine.set_rules(self.komi, self.rules)
        self._setup_black = info["setup_black"]
        self._setup_white = info["setup_white"]
        self._moves = info["moves"]
        self._resigned = None
        self._winrate = None
        self._last_analysis = None
        self._last_analysis_index = -1
        self._winrate_history = {}
        self._view = len(self._moves)
        self._refresh()
        return True

    def _sgf_result(self) -> str:
        if self._resigned is not None:
            return "B+R" if opponent(self._resigned) == BLACK else "W+R"
        if not self.live_board().is_over:
            return ""
        score = self._final_score()
        if score is None:
            return ""
        if score > 0:
            return f"B+{score:.1f}"
        if score < 0:
            return f"W+{-score:.1f}"
        return "0"

    # -- engine flow ----------------------------------------------------------

    def _refresh(self) -> None:
        self._generation += 1
        self._thinking = False
        self.positionChanged.emit()
        self._emit_status()
        self._request_analysis()
        self._maybe_ai()

    def _on_engines_ready(self) -> None:
        self._request_analysis()
        self._maybe_ai()
        self._emit_status()

    def _request_analysis(self) -> None:
        # Analyse every position — including a two-pass terminal one, whose
        # rootInfo.scoreLead is KataGo's final score. (Resigned games have no
        # position worth scoring.)
        if self._resigned is not None or not self._analysis_enabled:
            return
        self._pending_analysis_index = self._view
        self.engine.request_analysis(self._gtp_moves(self._view), self._generation)

    def _maybe_ai(self) -> None:
        if not self.is_live or self.game_over or self._thinking:
            return
        to_move = self.live_board().to_move
        if self._players[to_move] != PlayerKind.AI:
            return
        self._thinking = True
        self._emit_status()
        gen = self._generation
        both_ai = all(k == PlayerKind.AI for k in self._players.values())
        delay = AI_VS_AI_DELAY_MS if both_ai else AI_DELAY_MS
        QTimer.singleShot(delay, lambda: self._fire_ai(gen))

    def _fire_ai(self, gen: int) -> None:
        if gen != self._generation or not self.is_live or self.game_over:
            self._thinking = False
            return
        color = COLOR_LETTER[self.live_board().to_move]
        self.engine.request_move(self._gtp_moves(), gen, color, self._rank)

    def _on_engine_move(self, gen: int, vertex: str) -> None:
        if gen != self._generation or not self.is_live:
            self._thinking = False   # stale result dropped — don't leave us "thinking"
            return
        self._thinking = False
        v = vertex.strip().lower()
        if not v:
            self.statusChanged.emit(t("status.empty_move"))
            return
        color = self.live_board().to_move
        if v == "resign":
            self._resigned = color
            self._generation += 1
            self.positionChanged.emit()
            self._emit_status()
            return
        point = None if v == "pass" else from_gtp(vertex, self.size)
        self._moves.append((color, point))
        self._view = len(self._moves)
        self._refresh()

    def _on_analysis(self, gen: int, result) -> None:
        if gen != self._generation:
            return
        self._winrate = result.root_winrate
        self._last_analysis = result
        self._last_analysis_index = self._pending_analysis_index
        self._winrate_history[self._pending_analysis_index] = result.root_winrate
        self.analysisUpdated.emit(result)
        self._emit_status()
        if self._auto_analyze:
            if self._view < len(self._moves):
                gen = self._generation
                QTimer.singleShot(AUTO_ANALYZE_DELAY_MS, lambda: self._auto_advance(gen))
            else:
                self.set_auto_analyze(False)   # reached the end of the game

    def winrate_history(self) -> dict:
        return self._winrate_history

    def _prune_winrate_history(self) -> None:
        """Drop graph entries for positions past the current move list (after undo/branch)."""
        n = len(self._moves)
        for k in [k for k in self._winrate_history if k > n]:
            del self._winrate_history[k]

    # -- analysis on/off + auto-analyze (keyboard: space / 'a') ----------------

    @property
    def analysis_enabled(self) -> bool:
        return self._analysis_enabled

    @property
    def auto_analyzing(self) -> bool:
        return self._auto_analyze

    def set_analysis_enabled(self, enabled: bool) -> None:
        if enabled == self._analysis_enabled:
            return
        self._analysis_enabled = enabled
        self.analysisEnabledChanged.emit(enabled)
        if enabled:
            self._request_analysis()
        elif self._auto_analyze:
            self.set_auto_analyze(False)

    def toggle_analysis(self) -> None:
        self.set_analysis_enabled(not self._analysis_enabled)

    def set_auto_analyze(self, on: bool) -> None:
        if on == self._auto_analyze:
            return
        self._auto_analyze = on
        self.autoAnalyzeChanged.emit(on)
        if on:
            if not self._analysis_enabled:
                self.set_analysis_enabled(True)
            if self._view >= len(self._moves):
                self.navigate(0)          # review the whole game from the start
            else:
                self._request_analysis()  # kick the chain at the current position

    def toggle_auto_analyze(self) -> None:
        self.set_auto_analyze(not self._auto_analyze)

    def _auto_advance(self, gen: int) -> None:
        if gen != self._generation:
            return   # the user navigated since this advance was scheduled — drop it
        if self._auto_analyze and self._view < len(self._moves):
            self.navigate(self._view + 1)

    # -- status ---------------------------------------------------------------

    def _final_score(self) -> Optional[float]:
        """Black-relative final score: KataGo's scoreLead for the LIVE terminal position
        if we have it, else a Tromp-Taylor count (so a reviewed mid-game analysis is
        never mistaken for the result)."""
        if self._last_analysis is not None and self._last_analysis_index == len(self._moves):
            return self._last_analysis.root_score_lead
        return self.live_board().area_score()

    def _score_is_katago(self) -> bool:
        return self._last_analysis is not None and self._last_analysis_index == len(self._moves)

    def _result_text(self) -> str:
        if self._resigned is not None:
            winner = t("color.white") if opponent(self._resigned) == WHITE else t("color.black")
            return t("result.resign", winner=winner)
        score = self._final_score()
        src = t("src.katago") if self._score_is_katago() else t("src.count")
        if score is None:
            return t("result.counting")
        if score > 0:
            return t("result.win_by", winner=t("color.black"), score=score, src=src)
        if score < 0:
            return t("result.win_by", winner=t("color.white"), score=-score, src=src)
        return t("result.jigo", src=src)

    def refresh_status(self) -> None:
        """Re-emit the status line (e.g. after a language change)."""
        self._emit_status()

    def _emit_status(self) -> None:
        if not self.is_live:
            self.statusChanged.emit(
                t("status.reviewing", view=self._view, total=len(self._moves)))
            return
        if self.game_over:
            self.statusChanged.emit(t("status.game_over", result=self._result_text()))
            return
        b = self.live_board()
        turn = t("color.black") if b.to_move == BLACK else t("color.white")
        who = t("player.ai") if self._players[b.to_move] == PlayerKind.AI else t("player.human")
        extra = t("status.thinking") if self._thinking else ""
        wr = (t("status.winrate", black=t("color.black"), pct=self._winrate * 100)
              if self._winrate is not None else "")
        passes = t("status.last_pass") if b.last_was_pass else ""
        self.statusChanged.emit(
            t("status.turn", turn=turn, who=who, extra=extra, passes=passes, wr=wr))
