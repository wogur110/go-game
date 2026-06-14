"""Go (Baduk) rules engine — board state, captures, ko, pass and scoring.

Pure Python, no Qt/engine deps, so it is unit-tested headlessly. It gives the UI
instant move legality and capture results; KataGo remains the authority for the
final game-end score (the local :meth:`Goban.area_score` is a Tromp-Taylor area
count used for quick estimates and tests).

Rules: single-stone and multi-stone **suicide is illegal** (Chinese/Japanese),
**simple ko** is always enforced, and **positional superko** is available via
``superko=True``. A move is either an ``(x, y)`` point or ``None`` for a pass;
two consecutive passes end the game.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Set, Tuple

EMPTY, BLACK, WHITE = 0, 1, 2
Point = Tuple[int, int]

COLOR_LETTER = {BLACK: "B", WHITE: "W"}
LETTER_COLOR = {"B": BLACK, "W": WHITE, "b": BLACK, "w": WHITE}


def opponent(color: int) -> int:
    return BLACK if color == WHITE else WHITE


class IllegalMove(Exception):
    """Raised by :meth:`Goban.play` for an illegal move (reason in ``str``)."""


def _neighbors(p: Point, size: int) -> List[Point]:
    x, y = p
    out: List[Point] = []
    if x > 0:
        out.append((x - 1, y))
    if x < size - 1:
        out.append((x + 1, y))
    if y > 0:
        out.append((x, y - 1))
    if y < size - 1:
        out.append((x, y + 1))
    return out


def _group_on(board: List[int], size: int, p: Point) -> Tuple[Set[Point], Set[Point]]:
    """Connected same-colour group containing ``p`` and its set of liberties."""
    color = board[p[1] * size + p[0]]
    stack = [p]
    stones: Set[Point] = {p}
    libs: Set[Point] = set()
    while stack:
        cur = stack.pop()
        for n in _neighbors(cur, size):
            v = board[n[1] * size + n[0]]
            if v == EMPTY:
                libs.add(n)
            elif v == color and n not in stones:
                stones.add(n)
                stack.append(n)
    return stones, libs


def _zobrist_table(size: int) -> List[List[int]]:
    rng = random.Random(0xBADA55 ^ size)
    return [[0, rng.getrandbits(64), rng.getrandbits(64)] for _ in range(size * size)]


class Goban:
    def __init__(self, size: int = 19, komi: float = 7.5, superko: bool = False):
        self.size = size
        self.komi = komi
        self.superko = superko
        self.board: List[int] = [EMPTY] * (size * size)
        self.to_move: int = BLACK
        self.ko: Optional[Point] = None              # simple-ko forbidden point
        self.consecutive_passes = 0
        self.captures: Dict[int, int] = {BLACK: 0, WHITE: 0}  # prisoners taken by colour
        self.move_number = 0
        self.last_move: Optional[Point] = None
        self.last_was_pass = False
        self.moves: List[Tuple[int, Optional[Point]]] = []
        self._ztab = _zobrist_table(size)
        self._history: Set[int] = {self._board_hash(self.board)}

    # -- geometry / queries ---------------------------------------------------

    def _idx(self, p: Point) -> int:
        return p[1] * self.size + p[0]

    def in_bounds(self, p: Point) -> bool:
        return 0 <= p[0] < self.size and 0 <= p[1] < self.size

    def get(self, p: Point) -> int:
        return self.board[self._idx(p)]

    def liberties(self, p: Point) -> int:
        if self.get(p) == EMPTY:
            return 0
        return len(_group_on(self.board, self.size, p)[1])

    def _board_hash(self, board: List[int]) -> int:
        h = 0
        tab = self._ztab
        for i, v in enumerate(board):
            if v:
                h ^= tab[i][v]
        return h

    # -- legality / play ------------------------------------------------------

    def _simulate(self, move: Point, color: int):
        """Return ``(legal, new_board, captured_points)`` for placing ``color`` at ``move``."""
        board = self.board[:]
        board[self._idx(move)] = color
        opp = opponent(color)
        captured: List[Point] = []
        for n in _neighbors(move, self.size):
            if board[self._idx(n)] == opp:
                stones, libs = _group_on(board, self.size, n)
                if not libs:
                    for q in stones:
                        board[self._idx(q)] = EMPTY
                        captured.append(q)
        # Suicide: after resolving captures the placed group must have a liberty.
        if not _group_on(board, self.size, move)[1]:
            return False, None, []
        if self.superko and self._board_hash(board) in self._history:
            return False, None, []
        return True, board, captured

    def is_legal(self, move: Optional[Point], color: Optional[int] = None) -> bool:
        color = self.to_move if color is None else color
        if move is None:
            return True  # a pass is always legal
        if not self.in_bounds(move) or self.board[self._idx(move)] != EMPTY:
            return False
        if move == self.ko:
            return False
        return self._simulate(move, color)[0]

    def play(self, move: Optional[Point], color: Optional[int] = None) -> List[Point]:
        """Apply ``move`` (``None`` = pass). Returns captured points. Raises :class:`IllegalMove`."""
        color = self.to_move if color is None else color
        if move is None:
            self.ko = None
            self.consecutive_passes += 1
            self._commit(color, None, [])
            return []

        if not self.in_bounds(move):
            raise IllegalMove(f"out of bounds: {move}")
        if self.board[self._idx(move)] != EMPTY:
            raise IllegalMove(f"occupied: {move}")
        if move == self.ko:
            raise IllegalMove(f"ko: {move}")

        legal, new_board, captured = self._simulate(move, color)
        if not legal:
            raise IllegalMove(f"suicide/superko: {move}")

        self.board = new_board
        self.captures[color] += len(captured)
        self.consecutive_passes = 0
        # Simple ko: a lone stone that captured exactly one stone and now has one liberty.
        stones, libs = _group_on(self.board, self.size, move)
        self.ko = captured[0] if (len(captured) == 1 and len(stones) == 1 and len(libs) == 1) else None
        self._commit(color, move, captured)
        return captured

    def _commit(self, color: int, move: Optional[Point], captured: List[Point]) -> None:
        self.moves.append((color, move))
        self.move_number += 1
        self.last_move = move
        self.last_was_pass = move is None
        self.to_move = opponent(color)
        self._history.add(self._board_hash(self.board))

    def legal_moves(self, color: Optional[int] = None) -> List[Point]:
        color = self.to_move if color is None else color
        out: List[Point] = []
        for y in range(self.size):
            for x in range(self.size):
                if self.board[y * self.size + x] == EMPTY and self.is_legal((x, y), color):
                    out.append((x, y))
        return out

    # -- game state -----------------------------------------------------------

    @property
    def is_over(self) -> bool:
        return self.consecutive_passes >= 2

    def setup_stones(self, points: List[Point], color: int) -> None:
        """Place stones without capture logic (handicap / SGF setup); sets White to move."""
        for p in points:
            self.board[self._idx(p)] = color
        if points:
            self.to_move = WHITE
        self._history = {self._board_hash(self.board)}

    def place_setup(self, black: List[Point], white: List[Point]) -> None:
        """Place black/white setup stones (handicap or SGF AB/AW). Handicap → White to move."""
        for p in black:
            self.board[self._idx(p)] = BLACK
        for p in white:
            self.board[self._idx(p)] = WHITE
        self.to_move = WHITE if (black and not white) else BLACK
        self._history = {self._board_hash(self.board)}

    def copy(self) -> "Goban":
        g = Goban.__new__(Goban)
        g.size = self.size
        g.komi = self.komi
        g.superko = self.superko
        g.board = self.board[:]
        g.to_move = self.to_move
        g.ko = self.ko
        g.consecutive_passes = self.consecutive_passes
        g.captures = dict(self.captures)
        g.move_number = self.move_number
        g.last_move = self.last_move
        g.last_was_pass = self.last_was_pass
        g.moves = list(self.moves)
        g._ztab = self._ztab
        g._history = set(self._history)
        return g

    # -- scoring (Tromp-Taylor area; KataGo is authoritative in real games) ----

    def area_score(self) -> float:
        """Area score (black - white), komi to White. Positive => Black ahead.

        Assumes dead stones have already been removed from the board.
        """
        size = self.size
        seen = [False] * (size * size)
        black = sum(1 for v in self.board if v == BLACK)
        white = sum(1 for v in self.board if v == WHITE)
        for y in range(size):
            for x in range(size):
                i = y * size + x
                if self.board[i] != EMPTY or seen[i]:
                    continue
                region: List[Point] = []
                borders: Set[int] = set()
                stack = [(x, y)]
                seen[i] = True
                while stack:
                    cur = stack.pop()
                    region.append(cur)
                    for n in _neighbors(cur, size):
                        v = self.board[self._idx(n)]
                        if v == EMPTY:
                            if not seen[self._idx(n)]:
                                seen[self._idx(n)] = True
                                stack.append(n)
                        else:
                            borders.add(v)
                if borders == {BLACK}:
                    black += len(region)
                elif borders == {WHITE}:
                    white += len(region)
        return black - (white + self.komi)
