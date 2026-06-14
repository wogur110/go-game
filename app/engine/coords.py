"""Go coordinate helpers: convert between internal (x, y) points and GTP vertices.

Internal coords: ``x`` = column ``0..size-1`` (left→right), ``y`` = row
``0..size-1`` (top→bottom), matching the on-screen board layout.

GTP vertices use columns ``A..T`` (the letter ``I`` is skipped) left→right and
rows ``1..size`` counted bottom→top. So on a 19x19 board the top-left point is
``"A19"`` and the bottom-right is ``"T1"``. A pass is the literal ``"pass"``.
"""

from __future__ import annotations

from typing import Optional, Tuple

GTP_COLUMNS = "ABCDEFGHJKLMNOPQRST"  # 'I' is intentionally omitted
PASS = "pass"
RESIGN = "resign"

Point = Tuple[int, int]


def to_gtp(point: Optional[Point], size: int) -> str:
    """Internal ``(x, y)`` point → GTP vertex. ``None`` → ``"pass"``."""
    if point is None:
        return PASS
    x, y = point
    if not (0 <= x < size and 0 <= y < size):
        raise ValueError(f"point {point} out of range for board size {size}")
    return f"{GTP_COLUMNS[x]}{size - y}"


def from_gtp(vertex: str, size: int) -> Optional[Point]:
    """GTP vertex → internal ``(x, y)`` point. ``"pass"``/``"resign"`` → ``None``."""
    v = vertex.strip()
    if v.lower() in (PASS, RESIGN):
        return None
    if not v:
        raise ValueError("empty GTP vertex")   # don't silently coerce "" to a pass
    x = GTP_COLUMNS.index(v[0].upper())
    row = int(v[1:])
    return (x, size - row)
