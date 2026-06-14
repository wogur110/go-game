"""Lizzie-style win-rate graph: Black's win rate across the whole game.

A horizontal strip under the board. The area is split by the win-rate line into a
black region (bottom) and white region (top) at each move, a 50% midline is drawn,
and the current move is marked. Clicking jumps to that move.
"""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from . import theme
from .i18n import t


class WinrateGraph(QWidget):
    moveSelected = Signal(int)   # move index clicked

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(120)
        self.setMouseTracking(True)
        self._history: Dict[int, float] = {}   # move index -> Black win rate [0,1]
        self._total = 0
        self._current = 0

    def set_data(self, history: Dict[int, float], total: int, current: int) -> None:
        self._history = history
        self._total = total
        self._current = current
        self.update()

    def _values(self):
        n = max(self._total, 1)
        vals = []
        last = 0.5
        for i in range(n + 1):
            if i in self._history:
                last = self._history[i]
            vals.append(last)
        return vals

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        p.fillRect(rect, QColor(theme.BG_PANEL))

        m = 6.0
        x0, y0 = m, m
        w = rect.width() - 2 * m
        h = rect.height() - 2 * m
        if w <= 0 or h <= 0:
            p.end()
            return
        n = max(self._total, 1)
        vals = self._values()

        def px(i):
            return x0 + (i / n) * w

        def py(v):
            return y0 + (1.0 - v) * h

        # White region (whole area), then black region (below the line).
        p.fillRect(QRectF(x0, y0, w, h), QColor("#dfe3ea"))
        black_poly = QPolygonF([QPointF(px(i), py(v)) for i, v in enumerate(vals)])
        black_poly.append(QPointF(px(n), y0 + h))
        black_poly.append(QPointF(x0, y0 + h))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#15181e"))
        p.drawPolygon(black_poly)

        # 50% midline.
        p.setPen(QPen(QColor(120, 124, 132, 160), 1, Qt.DashLine))
        p.drawLine(QPointF(x0, py(0.5)), QPointF(x0 + w, py(0.5)))

        # Win-rate line.
        p.setPen(QPen(QColor(theme.ACCENT), 1.6))
        line = QPolygonF([QPointF(px(i), py(v)) for i, v in enumerate(vals)])
        p.drawPolyline(line)

        # Current-move marker.
        cx = px(self._current)
        p.setPen(QPen(QColor("#f4d03f"), 1.4))
        p.drawLine(QPointF(cx, y0), QPointF(cx, y0 + h))
        if 0 <= self._current < len(vals):
            cv = vals[self._current]
            p.setBrush(QColor("#f4d03f"))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, py(cv)), 3.2, 3.2)
            # current Black win rate label
            f = QFont()
            f.setPixelSize(11)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QPen(QColor(theme.TEXT)))
            txt = t("winbar.black_pct", black=t("color.black"), pct=cv * 100)
            p.drawText(QRectF(x0, y0, w, 14), Qt.AlignRight | Qt.AlignTop, txt)
        p.end()

    def mousePressEvent(self, event) -> None:
        m = 6.0
        w = self.width() - 2 * m
        if w <= 0:
            return
        n = max(self._total, 1)
        i = round((event.position().x() - m) / w * n)
        i = max(0, min(i, self._total))
        self.moveSelected.emit(i)
