"""Sidebar: win/score bar, candidate-move panel, move list, and game controls.

Takes the controller + engine and wires the controls directly; main_window only
assembles board + sidebar and routes analysis updates here and to the board.
All visible text comes from i18n and is re-applied live by retranslate().
"""

from __future__ import annotations

from typing import List, Optional, Tuple

Point = Tuple[int, int]

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

from . import theme
from .engine.coords import from_gtp, to_gtp
from .engine.networks import NETWORKS
from .game_controller import PlayerKind
from .goban import BLACK, WHITE
from .i18n import I18N, LANG_NAMES, t

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
            p.drawText(rect, Qt.AlignCenter, t("winbar.waiting"))
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
                   t("winbar.black_pct", black=t("color.black"), pct=self._wr * 100))
        p.setPen(QColor("#111418"))
        p.drawText(QRectF(w / 2, 0, w / 2 - 8, h), Qt.AlignVCenter | Qt.AlignRight,
                   t("winbar.white_pct", white=t("color.white"), pct=(1 - self._wr) * 100))
        p.setPen(QColor(theme.ACCENT))
        side = t("color.black") if self._score >= 0 else t("color.white")
        p.drawText(rect, Qt.AlignCenter, t("winbar.score", side=side, score=abs(self._score)))
        p.end()


class Sidebar(QWidget):
    viewToggled = Signal(str, bool)   # ("candidates"|"territory"|"order", checked)
    pvPreview = Signal(object)        # (points, start_color) or None

    def __init__(self, controller, engine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.controller = controller
        self.engine = engine
        self._pv_start_color = BLACK
        self.setFixedWidth(300)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(7)

        # Language selector.
        lang_row = QHBoxLayout()
        self.lang_label = QLabel(t("ui.language"))
        self.lang_combo = QComboBox()
        for code, name in LANG_NAMES:
            self.lang_combo.addItem(name, code)
        self.lang_combo.setCurrentIndex(
            next((i for i, (c, _n) in enumerate(LANG_NAMES) if c == I18N.lang), 0))
        self.lang_combo.currentIndexChanged.connect(
            lambda _i: I18N.set_language(self.lang_combo.currentData()))
        lang_row.addWidget(self.lang_label)
        lang_row.addWidget(self.lang_combo, 1)
        lay.addLayout(lang_row)

        # Engine state indicator (model loading / ready / missing / error).
        self._engine_state = "loading" if engine.available else "missing"
        self.engine_status = QLabel()
        self.engine_status.setObjectName("EngineStatus")
        lay.addWidget(self.engine_status)
        self.engine.engineState.connect(self._on_engine_state)
        self.engine.engineError.connect(self._on_engine_error)
        self._render_engine_state()

        self.status = QLabel(t("status.loading"))
        self.status.setObjectName("Status")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.winbar = WinBar()
        lay.addWidget(self.winbar)

        # Player modes.
        self.black_combo = self._player_combo(BLACK, PlayerKind.HUMAN)
        self.white_combo = self._player_combo(WHITE, PlayerKind.AI)
        self.black_label = QLabel(t("ui.black_player"))
        self.white_label = QLabel(t("ui.white_player"))
        row = QHBoxLayout()
        row.addWidget(self.black_label), row.addWidget(self.black_combo, 1)
        row.addWidget(self.white_label), row.addWidget(self.white_combo, 1)
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
        self.net_combo.setEnabled(False)   # gate until engines are loaded
        self.engine.enginesReady.connect(lambda: self.net_combo.setEnabled(True))
        self.rank_label = QLabel(t("ui.rank"))
        self.net_label = QLabel(t("ui.net"))
        sel.addWidget(self.rank_label), sel.addWidget(self.rank_combo, 1)
        sel.addWidget(self.net_label), sel.addWidget(self.net_combo, 1)
        lay.addLayout(sel)

        # Action buttons.
        self.new_btn = QPushButton(t("btn.new"))
        self.pass_btn = QPushButton(t("btn.pass"))
        self.resign_btn = QPushButton(t("btn.resign"))
        self.undo_btn = QPushButton(t("btn.undo"))
        self.new_btn.clicked.connect(self.controller.new_game)
        self.pass_btn.clicked.connect(self.controller.pass_move)
        self.resign_btn.clicked.connect(self.controller.resign)
        self.undo_btn.clicked.connect(self.controller.undo)
        actions = QHBoxLayout()
        for b in (self.new_btn, self.pass_btn, self.resign_btn, self.undo_btn):
            actions.addWidget(b)
        lay.addLayout(actions)

        self.save_btn = QPushButton(t("btn.sgf_save"))
        self.load_btn = QPushButton(t("btn.sgf_load"))
        self.save_btn.clicked.connect(self._on_save)
        self.load_btn.clicked.connect(self._on_load)
        files = QHBoxLayout()
        files.addWidget(self.save_btn), files.addWidget(self.load_btn)
        lay.addLayout(files)

        # View toggles: candidate overlay, territory (형세 판단), move order.
        self.cand_check = QCheckBox(t("ui.show_candidates"))
        self.terr_check = QCheckBox(t("ui.show_territory"))
        self.order_check = QCheckBox(t("ui.show_order"))
        self.cand_check.setChecked(True)
        self.terr_check.setChecked(True)
        self.cand_check.toggled.connect(lambda c: self.viewToggled.emit("candidates", c))
        self.terr_check.toggled.connect(lambda c: self.viewToggled.emit("territory", c))
        self.order_check.toggled.connect(lambda c: self.viewToggled.emit("order", c))
        opts = QHBoxLayout()
        for cb in (self.cand_check, self.terr_check, self.order_check):
            opts.addWidget(cb)
        lay.addLayout(opts)

        # Precise score estimate (deep one-shot analysis).
        self.estimate_btn = QPushButton(t("btn.estimate"))
        self.estimate_btn.clicked.connect(self._on_estimate_click)
        lay.addWidget(self.estimate_btn)
        self.estimate_label = QLabel("")
        self.estimate_label.setObjectName("Estimate")
        self.estimate_label.setWordWrap(True)
        lay.addWidget(self.estimate_label)

        # Candidate moves (hover a row to preview its variation on the board).
        self.cand_label = QLabel(t("ui.candidates"))
        lay.addWidget(self.cand_label)
        self.candidates = QListWidget()
        self.candidates.setFont(_MONO)
        self.candidates.setFixedHeight(132)
        self.candidates.setMouseTracking(True)
        self.candidates.itemClicked.connect(self._on_candidate)
        self.candidates.itemEntered.connect(self._on_candidate_hover)
        self.candidates.viewport().installEventFilter(self)
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
        combo.addItem(t("player.human"), PlayerKind.HUMAN)
        combo.addItem(t("player.ai"), PlayerKind.AI)
        combo.setCurrentIndex(0 if default == PlayerKind.HUMAN else 1)
        combo.currentIndexChanged.connect(
            lambda _i, c=color, cb=combo: self.controller.set_player(c, cb.currentData()))
        return combo

    _STATE_COLOR = {"missing": theme.BAD, "loading": theme.WARN,
                    "ready": theme.GOOD, "error": theme.BAD}

    def _on_engine_state(self, state: str) -> None:
        self._engine_state = state
        self._render_engine_state()

    def _render_engine_state(self) -> None:
        color = self._STATE_COLOR.get(self._engine_state, theme.TEXT_DIM)
        self.engine_status.setText(
            f"<span style='color:{color}'>●</span> {t('engine.' + self._engine_state)}")

    def _on_network(self, _i: int) -> None:
        key = self.net_combo.currentData()
        if self.engine.set_analysis_network(key):
            self.controller.refresh_analysis()

    def _on_estimate_click(self) -> None:
        if self.controller.request_estimate():
            self.estimate_label.setText(t("estimate.computing"))
        else:
            self.estimate_label.setText(t("estimate.not_ready"))

    def _on_engine_error(self, _msg: str) -> None:
        if self.estimate_label.text() == t("estimate.computing"):
            self.estimate_label.setText("")   # don't leave the estimate hanging on an error

    def show_estimate(self, result, to_move: int) -> None:
        own = result.ownership or []
        ba = sum(1 for o in own if o > 0.4)
        wa = sum(1 for o in own if o < -0.4)
        margin = result.root_score_lead
        leader = t("color.black") if margin >= 0 else t("color.white")
        self.estimate_label.setText(
            t("estimate.summary", ba=ba, wa=wa, leader=leader, margin=abs(margin)))

    def clear_estimate(self) -> None:
        self.estimate_label.setText("")

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, t("dlg.save_sgf"), "game.sgf", "SGF (*.sgf)")
        if path:
            if not path.endswith(".sgf"):
                path += ".sgf"
            self.controller.save_sgf(path)
            self.set_status(t("msg.saved", path=path))

    def _on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, t("dlg.load_sgf"), "", "SGF (*.sgf)")
        if path and self.controller.load_sgf(path):
            self.set_status(t("msg.loaded", path=path))

    def _on_candidate(self, item: QListWidgetItem) -> None:
        point = item.data(Qt.UserRole)
        if point is not None:
            self.controller.make_move(tuple(point))

    def _on_candidate_hover(self, item: QListWidgetItem) -> None:
        pv = item.data(Qt.UserRole + 1)
        self.pvPreview.emit((pv, self._pv_start_color) if pv else None)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.candidates.viewport() and event.type() == QEvent.Leave:
            self.pvPreview.emit(None)
        return super().eventFilter(obj, event)

    def _on_move_clicked(self, item: QListWidgetItem) -> None:
        idx = item.data(Qt.UserRole)
        if idx is not None:
            self.controller.navigate(int(idx))

    # -- updates --------------------------------------------------------------

    def retranslate(self) -> None:
        self.lang_label.setText(t("ui.language"))
        self._render_engine_state()
        self.black_label.setText(t("ui.black_player"))
        self.white_label.setText(t("ui.white_player"))
        for combo in (self.black_combo, self.white_combo):
            combo.setItemText(0, t("player.human"))
            combo.setItemText(1, t("player.ai"))
        self.rank_label.setText(t("ui.rank"))
        self.net_label.setText(t("ui.net"))
        self.new_btn.setText(t("btn.new"))
        self.pass_btn.setText(t("btn.pass"))
        self.resign_btn.setText(t("btn.resign"))
        self.undo_btn.setText(t("btn.undo"))
        self.save_btn.setText(t("btn.sgf_save"))
        self.load_btn.setText(t("btn.sgf_load"))
        self.cand_label.setText(t("ui.candidates"))
        self.cand_check.setText(t("ui.show_candidates"))
        self.terr_check.setText(t("ui.show_territory"))
        self.order_check.setText(t("ui.show_order"))
        self.estimate_btn.setText(t("btn.estimate"))
        self.winbar.update()

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def clear_analysis(self) -> None:
        self.winbar.clear()
        self.candidates.clear()

    def set_analysis(self, result, to_move: int) -> None:
        black = to_move == BLACK
        self._pv_start_color = to_move
        size = self.controller.size
        self.winbar.set_value(result.root_winrate, result.root_score_lead)
        self.candidates.clear()
        for mi in result.moves[:8]:
            wr = mi.winrate if black else 1.0 - mi.winrate
            sc = mi.score_lead if black else -mi.score_lead
            text = f"{mi.vertex:>4}  {wr * 100:5.1f}%  {sc:+5.1f}  {_fmt_visits(mi.visits):>5}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, mi.point)
            pv_pts: List[Point] = []
            for v in mi.pv[:10]:
                try:
                    pt = from_gtp(v, size)
                except ValueError:
                    pt = None
                if pt is None:
                    break   # stop at first pass/resign so color parity + numbering stay aligned
                pv_pts.append(pt)
            item.setData(Qt.UserRole + 1, pv_pts)
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
