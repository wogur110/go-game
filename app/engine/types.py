"""Plain data payloads returned by the KataGo clients.

All winrates/scores are reported from **Black's** perspective (the analysis
config sets ``reportAnalysisWinratesAs = BLACK``) so the eval bar has a fixed
reference, just like Chess Studio reports everything from White's perspective.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

Point = Tuple[int, int]

BLACK = "B"
WHITE = "W"


@dataclass
class MoveInfo:
    """One candidate move from KataGo analysis."""

    vertex: str                  # GTP vertex, e.g. "Q16" or "pass"
    point: Optional[Point]       # internal (x, y), or None for a pass
    winrate: float               # Black win probability in [0, 1]
    score_lead: float            # Black score lead in points (+ = Black ahead)
    visits: int
    prior: float                 # policy prior in [0, 1]
    order: int                   # 0 = best
    pv: List[str] = field(default_factory=list)  # principal variation (GTP vertices)


@dataclass
class AnalysisResult:
    """A complete analysis response for one position."""

    moves: List[MoveInfo]
    root_winrate: float          # Black win probability in [0, 1]
    root_score_lead: float       # Black score lead in points
    board_size: int
    visits: int = 0
    # Flat ownership map, Black-positive in [-1, 1]. Length == board_size**2.
    # NOTE: index→point orientation is verified empirically in M1; treat as opaque for now.
    ownership: Optional[List[float]] = None
