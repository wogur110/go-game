"""Sidebar: win/score bar, candidate-move panel, move list, and game controls.

Takes the controller + engine and wires the controls directly; main_window only
assembles board + sidebar and routes analysis updates here and to the board.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

from . import theme
from .engine.coords import to_gtp
from .engine.networks import NETWORKS
from .goban import BLACK, COLOR_LETTER, WHITE
from .game_controller import PlayerKind

RANKS = [f"rank_{i}k" for i in range(20, 0, -1)] + [f"rank_{i}d" for i in range(1, 10)]
ANALYSIS_NETS = [(k, n) for k, n in NETWORKS.items() if n.role == "analysis"]
_MONO = QFont("monospace")
_MONO.setStyleHint(QFont.Monospace)


def _fmt_visits(v: int) -> str:
    if v >= 10000:
        return f"{v / 1000:.0f}k"
    if v >= 1000:
        return f"{v / 1000:.1f}k"
    return str(v)


class WinBar(QWidget):
    """Horizontal Black/White win-probability split with the score lead."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(36)
        self._wr: Optional[float] = None    # Black winrate [0,1]
        self._score = 0.0                   # Black score lead (points)

    def set_value(self, black_winrate: float, black_score: float) -> None:
        self._wr = black_winrate
        self._score = black_score
        self.update()

    def clear(self) -> None:
        self._wr = None
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        if self._wr is None:
            p.fillRect(rect, QColor(theme.BG_PANEL))
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(rect, Qt.AlignCenter, "분석 대기…")
            p.end()
            return
        w, h = rect.width(), rect.height()
        bw = int(w * self._wr)
        p.fillRect(QRectF(0, 0, bw, h), QColor("#111418"))
        p.fillRect(QRectF(bw, 0, w - bw, h), QColor("#e8eaef"))
        f = QFont()
        f.setBold(True)
        f.setPixelSize(13)
        p.setFont(f)
        p.setPen(QColor("#e8eaef"))
        p.drawText(QRectF(8, 0, w / 2, h), Qt.AlignVCenter | Qt.AlignLeft,
                   f"흑 {self._wr * 100:.0f}%")
        p.setPen(QColor("#111418"))
        p.drawText(QRectF(w / 2, 0, w / 2 - 8, h), Qt.AlignVCenter | Qt.AlignRight,
                   f"{(1 - self._wr) * 100:.0f}% 백")
        p.setPen(QColor(theme.ACCENT))
        side = "흑" if self._score >= 0 else "백"
        p.drawText(rect, Qt.AlignCenter, f"{side} {abs(self._score):.1f}집")
        p.end()


class Sidebar(QWidget):
    def __init__(self, controller, engine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.controller = controller
        self.engine = engine
        self.setFixedWidth(280)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(7)

        self.status = QLabel("엔진 로딩 중…")
        self.status.setObjectName("Status")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.winbar = WinBar()
        lay.addWidget(self.winbar)

        # Player modes.
        self.black_combo = self._player_combo(BLACK, PlayerKind.HUMAN)
        self.white_combo = self._player_combo(WHITE, PlayerKind.AI)
        row = QHBoxLayout()
        row.addWidget(QLabel("● 흑")), row.addWidget(self.black_combo, 1)
        row.addWidget(QLabel("○ 백")), row.addWidget(self.white_combo, 1)
        lay.addLayout(row)

        # Rank + network selectors.
        sel = QHBoxLayout()
        self.rank_combo = QComboBox()
        for r in RANKS:
            self.rank_combo.addItem(r.removeprefix("rank_"), r)
        self.rank_combo.setCurrentIndex(RANKS.index("rank_5k"))
        self.rank_combo.currentIndexChanged.connect(
            lambda _i: self.controller.set_rank(self.rank_combo.currentData()))
        self.net_combo = QComboBox()
        for key, net in ANALYSIS_NETS:
            self.net_combo.addItem(key, key)
        self.net_combo.currentIndexChanged.connect(self._on_network)
        # Switching nets only takes effect once engines are loaded — gate until ready.
        self.net_combo.setEnabled(False)
        self.engine.enginesReady.connect(lambda: self.net_combo.setEnabled(True))
        sel.addWidget(QLabel("급수")), sel.addWidget(self.rank_combo, 1)
        sel.addWidget(QLabel("분석망")), sel.addWidget(self.net_combo, 1)
        lay.addLayout(sel)

        # Action buttons.
        actions = QHBoxLayout()
        for text, slot in (("새 대국", self.controller.new_game),
                           ("패스", self.controller.pass_move),
                           ("기권", self.controller.resign),
                           ("무르기", self.controller.undo)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            actions.addWidget(b)
        lay.addLayout(actions)

        files = QHBoxLayout()
        save_b, load_b = QPushButton("SGF 저장"), QPushButton("SGF 불러오기")
        save_b.clicked.connect(self._on_save)
        load_b.clicked.connect(self._on_load)
        files.addWidget(save_b), files.addWidget(load_b)
        lay.addLayout(files)

        # Candidate moves.
        lay.addWidget(QLabel("후보수 (승률 · 집 · 방문)"))
        self.candidates = QListWidget()
        self.candidates.setFont(_MONO)
        self.candidates.setFixedHeight(132)
        self.candidates.itemClicked.connect(self._on_candidate)
        lay.addWidget(self.candidates)

        # Move list + navigation.
        nav = QHBoxLayout()
        for text, delta in (("⏮", -9999), ("◀", -1), ("▶", 1), ("⏭", 9999)):
            b = QPushButton(text)
            b.clicked.connect(lambda _c=False, d=delta: self.controller.step(d))
            nav.addWidget(b)
        lay.addLayout(nav)
        self.moves = QListWidget()
        self.moves.setFont(_MONO)
        self.moves.itemClicked.connect(self._on_move_clicked)
        lay.addWidget(self.moves, 1)

    # -- control builders -----------------------------------------------------

    def _player_combo(self, color: int, default: PlayerKind) -> QComboBox:
        combo = QComboBox()
        combo.addItem("사람", PlayerKind.HUMAN)
        combo.addItem("AI", PlayerKind.AI)
        combo.setCurrentIndex(0 if default == PlayerKind.HUMAN else 1)
        combo.currentIndexChanged.connect(
            lambda _i, c=color, cb=combo: self.controller.set_player(c, cb.currentData()))
        return combo

    def _on_network(self, _i: int) -> None:
        key = self.net_combo.currentData()
        if self.engine.set_analysis_network(key):
            self.controller.refresh_analysis()

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "SGF 저장", "game.sgf", "SGF (*.sgf)")
        if path:
            if not path.endswith(".sgf"):
                path += ".sgf"
            self.controller.save_sgf(path)
            self.set_status(f"저장됨: {path}")

    def _on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "SGF 불러오기", "", "SGF (*.sgf)")
        if path and self.controller.load_sgf(path):
            self.set_status(f"불러옴: {path}")

    def _on_candidate(self, item: QListWidgetItem) -> None:
        point = item.data(Qt.UserRole)
        if point is not None:
            self.controller.make_move(tuple(point))

    def _on_move_clicked(self, item: QListWidgetItem) -> None:
        idx = item.data(Qt.UserRole)
        if idx is not None:
            self.controller.navigate(int(idx))

    # -- updates --------------------------------------------------------------

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def clear_analysis(self) -> None:
        self.winbar.clear()
        self.candidates.clear()

    def set_analysis(self, result, to_move: int) -> None:
        black = to_move == BLACK
        self.winbar.set_value(result.root_winrate, result.root_score_lead)
        self.candidates.clear()
        for mi in result.moves[:8]:
            wr = mi.winrate if black else 1.0 - mi.winrate
            sc = mi.score_lead if black else -mi.score_lead
            text = f"{mi.vertex:>4}  {wr * 100:5.1f}%  {sc:+5.1f}  {_fmt_visits(mi.visits):>5}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, mi.point)
            self.candidates.addItem(item)

    def refresh_moves(self) -> None:
        self.moves.clear()
        size = self.controller.size
        for i, (color, mv) in enumerate(self.controller._moves):
            mark = "●" if color == BLACK else "○"
            vtx = to_gtp(mv, size)
            item = QListWidgetItem(f"{i + 1:>3}. {mark} {vtx}")
            item.setData(Qt.UserRole, i + 1)
            self.moves.addItem(item)
        cur = self.controller.view_index - 1
        if 0 <= cur < self.moves.count():
            self.moves.setCurrentRow(cur)
