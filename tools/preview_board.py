"""Render a sample goban position to a PNG (dev tool, headless/offscreen).

    QT_QPA_PLATFORM=offscreen python tools/preview_board.py [out.png] [size]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.board_widget import BoardWidget  # noqa: E402
from app.goban import BLACK, WHITE, Goban  # noqa: E402


def sample_position(size: int = 19) -> Goban:
    g = Goban(size=size)
    seq = [
        (BLACK, (3, 3)), (WHITE, (15, 15)), (BLACK, (15, 3)), (WHITE, (3, 15)),
        (BLACK, (5, 2)), (WHITE, (13, 16)), (BLACK, (2, 5)), (WHITE, (16, 13)),
        (BLACK, (9, 9)), (WHITE, (9, 3)), (BLACK, (9, 5)), (WHITE, (11, 3)),
        # A small corner capture: White (0,0) gets surrounded and taken.
        (WHITE, (0, 0)), (BLACK, (1, 0)), (WHITE, (16, 5)), (BLACK, (0, 1)),
    ]
    for color, mv in seq:
        g.play(mv, color)
    return g


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/board_preview.png"
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 19
    app = QApplication(sys.argv)
    g = sample_position(size)
    w = BoardWidget(size=size)
    w.resize(760, 760)
    w.set_position(g.board, g.size, g.last_move, g.to_move)
    pix = w.grab()
    ok = pix.save(out, "PNG")
    print(f"{'saved' if ok else 'FAILED'} {out}  ({pix.width()}x{pix.height()}) "
          f"moves={g.move_number} captures={g.captures}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
