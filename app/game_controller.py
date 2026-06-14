"""Game state, player modes, navigation and engine wiring.

The single source of truth for a game: a flat move list (replayed onto a fresh
:class:`~app.goban.Goban` for any position — replay is cheap), Human/AI per
colour, a generation counter that discards stale engine results, undo and
non-destructive review. It drives the human-net opponent and live analysis.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

from .engine.coords import from_gtp, to_gtp
from .goban import BLACK, COLOR_LETTER, WHITE, Goban, opponent

Point = Tuple[int, int]
Move = Tuple[int, Optional[Point]]   # (color, point|None-for-pass)

AI_DELAY_MS = 200
AI_VS_AI_DELAY_MS = 500


class PlayerKind(Enum):
    HUMAN = auto()
    AI = auto()


class GameController(QObject):
    positionChanged = Signal()         # board content / view changed
    statusChanged = Signal(str)
    analysisUpdated = Signal(object)   # AnalysisResult for the current view

    def __init__(self, engine, size: int = 19, komi: float = 7.5,
                 rules: str = "chinese", parent: Optional[QObject] = None):
        super().__init__(parent)
        self.engine = engine
        self.size = size
        self.komi = komi
        self.rules = rules
        self._moves: List[Move] = []
        self._players = {BLACK: PlayerKind.HUMAN, WHITE: PlayerKind.AI}
        self._rank = "rank_5k"
        self._generation = 0
        self._view = 0
        self._thinking = False
        self._resigned: Optional[int] = None
        self._winrate: Optional[float] = None
        self._last_analysis = None

        engine.moveReady.connect(self._on_engine_move)
        engine.analysisReady.connect(self._on_analysis)
        engine.enginesReady.connect(self._on_engines_ready)
        engine.engineError.connect(self.statusChanged.emit)

    # -- board reconstruction -------------------------------------------------

    def board_at(self, n: int) -> Goban:
        g = Goban(self.size, self.komi)
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
        self._view = 0
        self._resigned = None
        self._winrate = None
        self._refresh()

    def make_move(self, point: Optional[Point]) -> bool:
        """Apply a HUMAN move (``None`` = pass). Returns False if not allowed."""
        if not self.is_live:
            self._moves = self._moves[:self._view]      # branch from the reviewed position
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
        self._refresh()

    def navigate(self, index: int) -> None:
        self._view = max(0, min(index, len(self._moves)))
        self._generation += 1
        self.positionChanged.emit()
        self._emit_status()
        self._request_analysis()

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
        if self.view_board().is_over:
            return
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
            return
        self._thinking = False
        v = vertex.strip().lower()
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
        self.analysisUpdated.emit(result)
        self._emit_status()

    # -- status ---------------------------------------------------------------

    def _result_text(self) -> str:
        if self._resigned is not None:
            winner = "백" if opponent(self._resigned) == WHITE else "흑"
            return f"{winner} 불계승 (상대 기권)"
        score = self.live_board().area_score()   # Tromp-Taylor estimate (KataGo scoring in M3)
        if score > 0:
            return f"흑 {score:+.1f}집 (집계산 추정)"
        if score < 0:
            return f"백 {-score:.1f}집 (집계산 추정)"
        return "빅 (무승부 추정)"

    def _emit_status(self) -> None:
        if not self.is_live:
            self.statusChanged.emit(f"검토 중 — {self._view} / {len(self._moves)} 수")
            return
        if self.game_over:
            self.statusChanged.emit("대국 종료 — " + self._result_text())
            return
        b = self.live_board()
        turn = "흑" if b.to_move == BLACK else "백"
        who = "AI" if self._players[b.to_move] == PlayerKind.AI else "사람"
        extra = " · 생각 중…" if self._thinking else ""
        wr = f" · 흑 승률 {self._winrate * 100:.1f}%" if self._winrate is not None else ""
        passes = " · 직전 패스" if b.last_was_pass else ""
        self.statusChanged.emit(f"{turn} 차례 ({who}){extra}{passes}{wr}")
