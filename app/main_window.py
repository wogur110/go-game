"""Main window: board + sidebar (M2 — analysis UI).

Routes the controller's analysis updates to both the board (ownership heatmap +
candidate overlays) and the sidebar (win bar, candidate panel, move list).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .board_widget import BoardWidget
from .game_controller import GameController, PlayerKind
from .i18n import I18N, t
from .sidebar import Sidebar
from .winrate_graph import WinrateGraph


class MainWindow(QWidget):
    def __init__(self, engine, size: int = 19, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(t("app.title"))
        self.resize(1280, 940)

        self.engine = engine
        self.controller = GameController(engine, size=size)
        self.board = BoardWidget(size=size)
        self.graph = WinrateGraph()
        self.sidebar = Sidebar(self.controller, engine)

        # Lizzie-style: board + win-rate graph on the left, controls on the right.
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(self.board, 1)
        left.addWidget(self.graph)
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        root.addLayout(left, 1)
        root.addWidget(self.sidebar)

        self.board.moveRequested.connect(self.controller.make_move)
        self.board.undoRequested.connect(self.controller.undo)
        self.controller.positionChanged.connect(self._on_position)
        self.controller.statusChanged.connect(self.sidebar.set_status)
        self.controller.analysisUpdated.connect(self._on_analysis)
        self.sidebar.viewToggled.connect(self._on_view_toggled)
        self.sidebar.pvPreview.connect(self._on_pv_preview)
        self.controller.estimateReady.connect(self._on_estimate)
        self.graph.moveSelected.connect(self.controller.navigate)
        self.controller.analysisEnabledChanged.connect(self._on_analysis_enabled)
        I18N.languageChanged.connect(self._retranslate)

        self._add_shortcuts()
        self._on_position()
        self.controller._emit_status()

    def _add_shortcuts(self) -> None:
        c = self.controller

        def sc(seq, fn):
            s = QShortcut(QKeySequence(seq), self, activated=fn)
            s.setContext(Qt.ApplicationShortcut)   # work regardless of which widget has focus

        sc(Qt.Key_Space, c.toggle_analysis)              # space: analysis on/off
        sc(Qt.Key_Left, lambda: c.step(-1))              # ← / → : navigate
        sc(Qt.Key_Right, lambda: c.step(1))
        sc(Qt.Key_Home, lambda: c.navigate(0))           # start / end
        sc(Qt.Key_End, lambda: c.navigate(c.total_moves))
        sc(Qt.Key_A, c.toggle_auto_analyze)              # a: auto-analyze
        sc(Qt.Key_P, c.pass_move)                        # p: pass
        sc(QKeySequence.Undo, c.undo)                    # Ctrl+Z: undo

    def _retranslate(self) -> None:
        self.setWindowTitle(t("app.title"))
        self.sidebar.retranslate()
        self.controller.refresh_status()

    def _on_view_toggled(self, option: str, checked: bool) -> None:
        if option == "candidates":
            self.board.set_show_analysis(checked)
        elif option == "territory":
            self.board.set_show_ownership(checked)
        elif option == "order":
            self.board.set_show_order(checked)

    def _on_pv_preview(self, data) -> None:
        if data:
            points, start_color = data
            self.board.set_pv_preview(points, start_color)
        else:
            self.board.set_pv_preview(None)

    def _on_estimate(self, result) -> None:
        self.board.set_territory(result.ownership)
        self.sidebar.show_estimate(result, self.controller.view_board().to_move)

    def _on_analysis_enabled(self, enabled: bool) -> None:
        if not enabled:                       # paused: clear the live overlays
            self.board.set_analysis(None)
            self.sidebar.clear_analysis()

    def _on_position(self) -> None:
        b = self.controller.view_board()
        self.board.set_position(b.board, b.size, b.last_move, b.to_move, b.move_no)
        self.sidebar.clear_analysis()
        self.sidebar.clear_estimate()
        self.sidebar.refresh_moves()
        self._refresh_graph()
        human_turn = (self.controller.is_live and not self.controller.game_over
                      and self.controller.player(b.to_move) == PlayerKind.HUMAN)
        self.board.set_movable(human_turn)

    def _on_analysis(self, result) -> None:
        to_move = self.controller.view_board().to_move
        self.board.set_analysis(result)
        self.sidebar.set_analysis(result, to_move)
        self._refresh_graph()

    def _refresh_graph(self) -> None:
        self.graph.set_data(self.controller.winrate_history(),
                            self.controller.total_moves, self.controller.view_index)
