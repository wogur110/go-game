"""The goban board widget: renders a Go board and turns clicks into moves.

Stones sit ON intersections (not in cells). Click-to-place only — no dragging.
Analysis overlays (candidate moves, ownership heatmap) arrive in M2; this widget
keeps the rendering primitives and a clean ``moveRequested`` signal.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QMouseEvent, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from . import theme
from .engine.coords import GTP_COLUMNS
from .goban import BLACK, EMPTY, WHITE

Point = Tuple[int, int]

_HOSHI = {
    9: [(2, 2), (6, 2), (4, 4), (2, 6), (6, 6)],
    13: [(3, 3), (9, 3), (6, 6), (3, 9), (9, 9)],
    19: [(x, y) for x in (3, 9, 15) for y in (3, 9, 15)],
}


class BoardWidget(QWidget):
    moveRequested = Signal(object)  # (x, y)

    def __init__(self, size: int = 19, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._size = size
        self._board: List[int] = [EMPTY] * (size * size)
        self._last_move: Optional[Point] = None
        self._to_move = BLACK
        self._show_coords = True
        self._movable = True
        self.setMinimumSize(360, 360)
        self.setMouseTracking(True)

    # -- state ----------------------------------------------------------------

    def set_position(self, board: List[int], size: int,
                     last_move: Optional[Point], to_move: int = BLACK) -> None:
        self._board = board
        self._size = size
        self._last_move = last_move
        self._to_move = to_move
        self.update()

    def set_movable(self, movable: bool) -> None:
        self._movable = movable

    def set_show_coords(self, show: bool) -> None:
        self._show_coords = show
        self.update()

    # -- geometry -------------------------------------------------------------

    def _geometry(self) -> Tuple[float, float, float]:
        """Return (origin_x, origin_y, cell) for intersection (0,0) and spacing."""
        n = self._size
        pad = 22.0 if self._show_coords else 10.0
        board_px = min(self.width(), self.height()) - 2 * pad
        cell = board_px / n
        ox = (self.width() - board_px) / 2 + cell / 2
        oy = (self.height() - board_px) / 2 + cell / 2
        return ox, oy, cell

    def _center(self, x: int, y: int) -> QPointF:
        ox, oy, cell = self._geometry()
        return QPointF(ox + x * cell, oy + y * cell)

    def _point_at(self, px: float, py: float) -> Optional[Point]:
        ox, oy, cell = self._geometry()
        if cell <= 0:
            return None
        fx = (px - ox) / cell
        fy = (py - oy) / cell
        x, y = round(fx), round(fy)
        if 0 <= x < self._size and 0 <= y < self._size and abs(fx - x) < 0.5 and abs(fy - y) < 0.5:
            return (x, y)
        return None

    # -- painting -------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(theme.BG_MAIN))

        n = self._size
        ox, oy, cell = self._geometry()
        last = oy + (n - 1) * cell
        right = ox + (n - 1) * cell

        # Wood board.
        board_rect = QRectF(ox - cell / 2, oy - cell / 2, n * cell, n * cell)
        p.fillRect(board_rect, QColor(theme.BOARD_BG))

        # Grid lines.
        line_w = max(1.0, cell * 0.035)
        p.setPen(QPen(QColor(theme.BOARD_LINE), line_w))
        for i in range(n):
            c = oy + i * cell
            p.drawLine(QPointF(ox, c), QPointF(right, c))
            cx = ox + i * cell
            p.drawLine(QPointF(cx, oy), QPointF(cx, last))

        # Star points (hoshi).
        star_r = max(2.0, cell * 0.09)
        p.setBrush(QBrush(QColor(theme.BOARD_STAR)))
        p.setPen(Qt.NoPen)
        for (sx, sy) in _HOSHI.get(n, []):
            p.drawEllipse(self._center(sx, sy), star_r, star_r)

        # Coordinate labels.
        if self._show_coords:
            self._draw_coords(p, ox, oy, cell, n)

        # Stones.
        r = cell * 0.46
        for y in range(n):
            for x in range(n):
                v = self._board[y * n + x]
                if v != EMPTY:
                    self._draw_stone(p, self._center(x, y), r, v)

        # Last-move marker.
        if self._last_move is not None:
            lx, ly = self._last_move
            v = self._board[ly * n + lx]
            marker = QColor("#f4f6fa") if v == BLACK else QColor(theme.BOARD_LINE)
            p.setBrush(QBrush(marker))
            p.setPen(Qt.NoPen)
            mr = r * 0.34
            p.drawEllipse(self._center(lx, ly), mr, mr)

        p.end()

    def _draw_coords(self, p: QPainter, ox: float, oy: float, cell: float, n: int) -> None:
        font = QFont()
        font.setPixelSize(int(max(8, cell * 0.34)))
        p.setFont(font)
        p.setPen(QPen(QColor(theme.COORD_TEXT)))
        last = oy + (n - 1) * cell
        for i in range(n):
            letter = GTP_COLUMNS[i]
            cx = ox + i * cell
            p.drawText(QRectF(cx - cell / 2, last + cell * 0.55, cell, cell * 0.6),
                       Qt.AlignCenter, letter)
            num = str(n - i)
            cy = oy + i * cell
            p.drawText(QRectF(ox - cell * 1.15, cy - cell / 2, cell * 0.7, cell),
                       Qt.AlignVCenter | Qt.AlignRight, num)

    def _draw_stone(self, p: QPainter, center: QPointF, r: float, color: int) -> None:
        hi, lo = ((theme.STONE_BLACK_HI, theme.STONE_BLACK_LO) if color == BLACK
                  else (theme.STONE_WHITE_HI, theme.STONE_WHITE_LO))
        grad = QRadialGradient(center + QPointF(-r * 0.32, -r * 0.32), r * 1.5)
        grad.setColorAt(0.0, QColor(hi))
        grad.setColorAt(1.0, QColor(lo))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(theme.STONE_EDGE), max(0.6, r * 0.05)))
        p.drawEllipse(center, r, r)

    # -- input ----------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._movable or event.button() != Qt.LeftButton:
            return
        pos = event.position()
        pt = self._point_at(pos.x(), pos.y())
        if pt is not None:
            self.moveRequested.emit(pt)

    def sizeHint(self) -> QSize:
        return QSize(640, 640)
