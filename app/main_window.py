"""Main window: the board plus a compact control panel (M1 — playable game).

The full sidebar (win bar, candidate panel, move list) arrives in M2; this is the
minimum to actually play against the human-net engine.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from .board_widget import BoardWidget
from .game_controller import GameController, PlayerKind
from .goban import BLACK, WHITE

# Human-net ranks, weakest → strongest.
RANKS = [f"rank_{i}k" for i in range(20, 0, -1)] + [f"rank_{i}d" for i in range(1, 10)]


def _rank_label(rank: str) -> str:
    return rank.removeprefix("rank_")


class MainWindow(QWidget):
    def __init__(self, engine, size: int = 19, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Baduk Studio")
        self.resize(1040, 760)

        self.controller = GameController(engine, size=size)
        self.board = BoardWidget(size=size)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        root.addWidget(self.board, 1)
        root.addLayout(self._build_panel())

        self.board.moveRequested.connect(self.controller.make_move)
        self.controller.positionChanged.connect(self._refresh_board)
        self.controller.statusChanged.connect(self.status.setText)
        self._refresh_board()
        self.controller._emit_status()

    # -- panel ----------------------------------------------------------------

    def _build_panel(self) -> QVBoxLayout:
        panel = QVBoxLayout()
        panel.setSpacing(8)

        self.status = QLabel("엔진 로딩 중…")
        self.status.setObjectName("Status")
        self.status.setWordWrap(True)
        panel.addWidget(self.status)
        panel.addSpacing(6)

        self.black_combo = self._player_combo(BLACK, PlayerKind.HUMAN)
        self.white_combo = self._player_combo(WHITE, PlayerKind.AI)
        panel.addWidget(QLabel("● 흑")), panel.addWidget(self.black_combo)
        panel.addWidget(QLabel("○ 백")), panel.addWidget(self.white_combo)

        panel.addSpacing(6)
        panel.addWidget(QLabel("AI 급수 (휴먼넷)"))
        self.rank_combo = QComboBox()
        for r in RANKS:
            self.rank_combo.addItem(_rank_label(r), r)
        self.rank_combo.setCurrentIndex(RANKS.index("rank_5k"))
        self.rank_combo.currentIndexChanged.connect(
            lambda _i: self.controller.set_rank(self.rank_combo.currentData()))
        panel.addWidget(self.rank_combo)

        panel.addSpacing(10)
        for text, slot in (("새 대국", self.controller.new_game),
                           ("착수 패스", self.controller.pass_move),
                           ("기권", self.controller.resign),
                           ("무르기", self.controller.undo)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            panel.addWidget(b)

        panel.addSpacing(8)
        nav = QHBoxLayout()
        prev_b, next_b = QPushButton("◀"), QPushButton("▶")
        prev_b.clicked.connect(lambda: self.controller.step(-1))
        next_b.clicked.connect(lambda: self.controller.step(1))
        nav.addWidget(prev_b), nav.addWidget(next_b)
        panel.addLayout(nav)

        panel.addStretch(1)
        return panel

    def _player_combo(self, color: int, default: PlayerKind) -> QComboBox:
        combo = QComboBox()
        combo.addItem("사람", PlayerKind.HUMAN)
        combo.addItem("AI", PlayerKind.AI)
        combo.setCurrentIndex(0 if default == PlayerKind.HUMAN else 1)
        combo.currentIndexChanged.connect(
            lambda _i, c=color, cb=combo: self.controller.set_player(c, cb.currentData()))
        return combo

    # -- refresh --------------------------------------------------------------

    def _refresh_board(self) -> None:
        b = self.controller.view_board()
        self.board.set_position(b.board, b.size, b.last_move, b.to_move)
        live = self.controller.live_board()
        human_turn = (self.controller.is_live and not self.controller.game_over
                      and self.controller.player(live.to_move) == PlayerKind.HUMAN)
        self.board.set_movable(human_turn)
