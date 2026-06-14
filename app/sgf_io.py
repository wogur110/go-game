"""SGF save/load via sgfmill — the Go equivalent of Chess Studio's PGN I/O.

Coordinate note: our internal point is ``(x, y)`` with ``y=0`` at the **top**.
sgfmill uses ``(row, col)`` with ``row=0`` at the **bottom**, so
``row = size-1-y`` and ``col = x``.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from sgfmill import sgf

from .goban import BLACK, WHITE

Point = Tuple[int, int]
Move = Tuple[int, Optional[Point]]


def _to_rc(point: Point, size: int) -> Tuple[int, int]:
    x, y = point
    return (size - 1 - y, x)


def _from_rc(rc: Tuple[int, int], size: int) -> Point:
    row, col = rc
    return (col, size - 1 - row)


def _colour(color: int) -> str:
    return "b" if color == BLACK else "w"


def _color(colour: str) -> int:
    return BLACK if colour == "b" else WHITE


def to_sgf(moves: List[Move], size: int, komi: float, *, rules: str = "chinese",
           setup_black: Optional[List[Point]] = None,
           setup_white: Optional[List[Point]] = None,
           result: str = "", pb: str = "Human", pw: str = "KataGo") -> bytes:
    game = sgf.Sgf_game(size=size)
    root = game.get_root()
    root.set("KM", komi)
    root.set("RU", rules)
    root.set("PB", pb)
    root.set("PW", pw)
    root.set("AP", ("Baduk Studio", "0.1"))
    if setup_black or setup_white:
        black = [_to_rc(p, size) for p in (setup_black or [])]
        white = [_to_rc(p, size) for p in (setup_white or [])]
        root.set_setup_stones(black, white, [])
        if setup_black and not setup_white:
            root.set("HA", len(setup_black))
    if result:
        root.set("RE", result)
    for color, mv in moves:
        node = game.extend_main_sequence()
        node.set_move(_colour(color), None if mv is None else _to_rc(mv, size))
    return game.serialise()


def from_sgf(data: bytes) -> dict:
    game = sgf.Sgf_game.from_bytes(data)
    size = game.get_size()
    root = game.get_root()

    komi = 7.5
    if root.has_property("KM"):
        try:
            komi = float(root.get("KM"))
        except Exception:  # noqa: BLE001
            pass
    rules = root.get("RU") if root.has_property("RU") else "chinese"

    ab, aw, _ae = root.get_setup_stones()
    setup_black = [_from_rc(rc, size) for rc in ab]
    setup_white = [_from_rc(rc, size) for rc in aw]

    moves: List[Move] = []
    # Iterate the FULL sequence (not [1:]): SGF allows the first move on the root
    # node (common in pro records). The colour-None guard skips a pure setup root.
    for node in game.get_main_sequence():
        colour, mv = node.get_move()
        if colour is None:
            continue
        point = None if mv is None else _from_rc(mv, size)
        moves.append((_color(colour), point))

    return {
        "size": size,
        "komi": komi,
        "rules": rules,
        "moves": moves,
        "setup_black": setup_black,
        "setup_white": setup_white,
    }
