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
from .engine.coords import GTP_COLUMNS, from_gtp
from .goban import BLACK, EMPTY, WHITE, opponent

Point = Tuple[int, int]


def _fmt_visits(v: int) -> str:
    if v >= 10000:
        return f"{v / 1000:.0f}k"
    if v >= 1000:
        return f"{v / 1000:.1f}k"
    return str(v)


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
        self._analysis = None            # AnalysisResult for the shown position, or None
        self._show_analysis = True
        self._show_ownership = True
        self._show_order = False         # draw move numbers on stones
        self._move_no: Optional[List[int]] = None   # per-point move number (parallel to _board)
        self._candidate_limit = 8
        self._hover_point: Optional[Point] = None    # for the ghost stone
        self._pv_preview: Optional[List[Point]] = None   # candidate variation to show
        self._pv_start_color = BLACK
        self._territory: Optional[List[float]] = None    # precise score-estimate ownership
        self.setMinimumSize(360, 360)
        self.setMouseTracking(True)

    # -- state ----------------------------------------------------------------

    def set_position(self, board: List[int], size: int, last_move: Optional[Point],
                     to_move: int = BLACK, move_no: Optional[List[int]] = None) -> None:
        self._board = board
        self._size = size
        self._last_move = last_move
        self._to_move = to_move
        self._move_no = move_no
        self._analysis = None            # overlays are stale until new analysis arrives
        self._pv_preview = None
        self._territory = None
        self.update()

    def set_territory(self, ownership: Optional[List[float]]) -> None:
        """Show a precise territory/score estimate (Black-positive ownership), or clear."""
        self._territory = ownership
        self.update()

    def set_analysis(self, result) -> None:
        """Attach an AnalysisResult (candidate moves + ownership) for the shown position."""
        self._analysis = result
        if self._hover_point is not None:        # keep an on-board hover PV fresh while streaming
            pv = self._candidate_pv_at(self._hover_point)
            if pv is not None:
                self._pv_preview = pv
                self._pv_start_color = self._to_move
        self.update()

    def set_show_order(self, show: bool) -> None:
        self._show_order = show
        self.update()

    def set_pv_preview(self, points: Optional[List[Point]], start_color: int = BLACK) -> None:
        """Show a candidate's principal variation as numbered ghost stones (or clear)."""
        self._pv_preview = points or None
        self._pv_start_color = start_color
        self.update()

    def set_movable(self, movable: bool) -> None:
        self._movable = movable

    def set_show_coords(self, show: bool) -> None:
        self._show_coords = show
        self.update()

    def set_show_analysis(self, show: bool) -> None:
        self._show_analysis = show
        self.update()

    def set_show_ownership(self, show: bool) -> None:
        self._show_ownership = show
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

        # Ownership heatmap (under the stones) — hidden while a precise estimate is shown.
        if self._territory is None and self._analysis is not None and self._show_ownership:
            self._draw_ownership(p, n, cell)

        # Stones.
        r = cell * 0.46
        for y in range(n):
            for x in range(n):
                v = self._board[y * n + x]
                if v != EMPTY:
                    self._draw_stone(p, self._center(x, y), r, v)

        # Move-order numbers (option) replace the last-move dot with full numbering.
        if self._show_order and self._move_no is not None:
            self._draw_move_numbers(p, r, n)
        elif self._last_move is not None:
            lx, ly = self._last_move
            v = self._board[ly * n + lx]
            marker = QColor("#f4f6fa") if v == BLACK else QColor(theme.BOARD_LINE)
            p.setBrush(QBrush(marker))
            p.setPen(Qt.NoPen)
            mr = r * 0.34
            p.drawEllipse(self._center(lx, ly), mr, mr)

        # Precise territory / score estimate (solid markers over stones).
        if self._territory is not None:
            self._draw_territory(p, n, cell)

        # A hovered candidate's variation takes over the overlay; else candidate discs.
        if self._pv_preview:
            self._draw_pv_preview(p, r, n)
        elif self._analysis is not None and self._show_analysis:
            self._draw_candidates(p, r, n)

        # Ghost stone at the hovered intersection (next-move preview).
        if (self._pv_preview is None and self._movable
                and self._hover_point is not None
                and self._board[self._hover_point[1] * n + self._hover_point[0]] == EMPTY):
            self._draw_ghost(p, self._center(*self._hover_point), r, self._to_move)

        p.end()

    def _draw_ownership(self, p: QPainter, n: int, cell: float) -> None:
        own = getattr(self._analysis, "ownership", None)
        if not own or len(own) != n * n:
            return
        half = cell * 0.46
        side = half * 2
        p.setPen(Qt.NoPen)
        for y in range(n):
            row = y * n
            for x in range(n):
                v = own[row + x]            # +ve = Black-owned (verified)
                a = abs(v)
                if a < 0.12:
                    continue
                alpha = int(min(0.55, a * 0.55) * 255)
                col = QColor(8, 10, 14, alpha) if v > 0 else QColor(238, 240, 245, alpha)
                p.setBrush(col)
                c = self._center(x, y)
                p.drawRect(QRectF(c.x() - half, c.y() - half, side, side))

    def _draw_territory(self, p: QPainter, n: int, cell: float) -> None:
        """Precise score estimate: solid territory squares on owned empty points, and a
        marker on dead stones (a stone whose point the opponent owns)."""
        own = self._territory
        if not own or len(own) != n * n:
            return
        terr = cell * 0.34
        dead = cell * 0.30
        p.setPen(Qt.NoPen)
        for y in range(n):
            row = y * n
            for x in range(n):
                o = own[row + x]
                if abs(o) < 0.4:
                    continue
                p.setBrush(QColor(16, 18, 24) if o > 0 else QColor(240, 242, 247))
                c = self._center(x, y)
                stone = self._board[row + x]
                if stone == EMPTY:
                    p.drawRect(QRectF(c.x() - terr / 2, c.y() - terr / 2, terr, terr))
                elif (stone == BLACK) != (o > 0):   # stone sitting in opponent's area = dead
                    p.drawRect(QRectF(c.x() - dead / 2, c.y() - dead / 2, dead, dead))

    def _draw_candidates(self, p: QPainter, r: float, n: int) -> None:
        """Lizzie-style: candidates coloured blue (best) → red (worse) by win-rate
        loss, opacity by visit share, win% big and visits small, best move ringed."""
        moves = [m for m in self._analysis.moves[:self._candidate_limit] if m.point is not None]
        if not moves:
            return
        black_to_move = self._to_move == BLACK

        def disp_wr(mi):
            return mi.winrate if black_to_move else 1.0 - mi.winrate

        best_wr = disp_wr(moves[0])
        max_visits = max((m.visits for m in moves), default=1) or 1
        wr_font = QFont()
        wr_font.setPixelSize(int(max(8, r * 0.66)))
        wr_font.setBold(True)
        v_font = QFont()
        v_font.setPixelSize(int(max(7, r * 0.42)))
        for rank, mi in enumerate(moves):
            x, y = mi.point
            if not (0 <= x < n and 0 <= y < n):
                continue
            c = self._center(x, y)
            wr = disp_wr(mi)
            loss = min(1.0, max(0.0, best_wr - wr) / 0.08)   # 0 = best, 1 = >=8% worse
            col = QColor.fromHsv(int(210 * (1.0 - loss)), 200, 230)   # 210 blue -> 0 red
            col.setAlpha(int(110 + 125 * (mi.visits / max_visits) ** 0.5))
            p.setBrush(col)
            if rank == 0:
                p.setPen(QPen(QColor("#f6f8fc"), max(1.4, r * 0.13)))   # highlight the best
            else:
                p.setPen(QPen(QColor(theme.BG_MAIN), max(0.8, r * 0.05)))
            p.drawEllipse(c, r * 0.94, r * 0.94)
            p.setPen(QPen(QColor("#0b0d11")))
            p.setFont(wr_font)
            p.drawText(QRectF(c.x() - r, c.y() - r * 0.96, 2 * r, r * 1.05),
                       Qt.AlignCenter, f"{wr * 100:.0f}")
            p.setFont(v_font)
            p.drawText(QRectF(c.x() - r, c.y() + r * 0.04, 2 * r, r * 0.9),
                       Qt.AlignCenter, _fmt_visits(mi.visits))

    def _label_color(self, stone_color: int) -> QColor:
        return QColor("#f4f6fa") if stone_color == BLACK else QColor("#15181e")

    def _draw_move_numbers(self, p: QPainter, r: float, n: int) -> None:
        font = QFont()
        font.setBold(True)
        for y in range(n):
            row = y * n
            for x in range(n):
                v = self._board[row + x]
                num = self._move_no[row + x] if self._move_no else 0
                if v == EMPTY or num <= 0:
                    continue
                font.setPixelSize(int(max(7, r * (1.05 if num < 100 else 0.78))))
                p.setFont(font)
                p.setPen(QPen(self._label_color(v)))
                c = self._center(x, y)
                p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), Qt.AlignCenter, str(num))

    def _draw_pv_preview(self, p: QPainter, r: float, n: int) -> None:
        font = QFont()
        font.setBold(True)
        for i, (x, y) in enumerate(self._pv_preview[:10]):
            if not (0 <= x < n and 0 <= y < n):
                break   # truncate rather than skip, so color parity / numbering stay aligned
            color = self._pv_start_color if i % 2 == 0 else opponent(self._pv_start_color)
            c = self._center(x, y)
            p.save()
            p.setOpacity(0.9)
            self._draw_stone(p, c, r, color)
            p.restore()
            font.setPixelSize(int(max(7, r * (1.0 if i + 1 < 10 else 0.82))))
            p.setFont(font)
            p.setPen(QPen(self._label_color(color)))
            p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), Qt.AlignCenter, str(i + 1))

    def _draw_ghost(self, p: QPainter, center: QPointF, r: float, color: int) -> None:
        p.save()
        p.setOpacity(0.4)
        self._draw_stone(p, center, r, color)
        p.restore()

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

    def _pv_points(self, pv: List[str]) -> List[Point]:
        pts: List[Point] = []
        for v in pv[:10]:
            try:
                p = from_gtp(v, self._size)
            except ValueError:
                p = None
            if p is None:
                break        # stop at the first pass so colour/number parity stays aligned
            pts.append(p)
        return pts

    def _candidate_pv_at(self, pt: Optional[Point]) -> Optional[List[Point]]:
        """The principal variation of the candidate whose stone is at ``pt`` (or None)."""
        if pt is None or self._analysis is None or not self._show_analysis:
            return None
        for mi in self._analysis.moves[:self._candidate_limit]:
            if mi.point == pt:
                return self._pv_points(mi.pv) or None
        return None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pt = self._point_at(event.position().x(), event.position().y())
        repaint = False
        # Hovering a candidate stone on the board previews its variation (like the list).
        pv = self._candidate_pv_at(pt)
        if pv != self._pv_preview:
            self._pv_preview = pv
            self._pv_start_color = self._to_move
            repaint = True
        if pt != self._hover_point:        # ghost rendering is gated on _movable in paintEvent
            self._hover_point = pt
            repaint = True
        if repaint:
            self.update()

    def leaveEvent(self, _event) -> None:
        if self._hover_point is not None or self._pv_preview is not None:
            self._hover_point = None
            self._pv_preview = None
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(640, 640)
