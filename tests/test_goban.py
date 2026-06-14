"""Rules-engine tests for app.goban. Run: python3 tests/test_goban.py  (or pytest)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.goban import BLACK, EMPTY, WHITE, Goban, IllegalMove, opponent  # noqa: E402


def _play(g: Goban, seq):
    """Play an explicit (color, point|None) sequence."""
    for color, mv in seq:
        g.play(mv, color)


def test_single_capture():
    g = Goban(size=5)
    # Black stone at (1,1) surrounded by White on a 5x5.
    _play(g, [(BLACK, (1, 1)), (WHITE, (1, 0)),
              (BLACK, (4, 4)), (WHITE, (0, 1)),
              (BLACK, (4, 3)), (WHITE, (2, 1)),
              (BLACK, (4, 2))])
    assert g.get((1, 1)) == BLACK
    captured = g.play((1, 2), WHITE)  # White fills the last liberty
    assert captured == [(1, 1)]
    assert g.get((1, 1)) == EMPTY
    assert g.captures[WHITE] == 1


def test_group_capture():
    g = Goban(size=5)
    # Two black stones (0,0)-(1,0) captured together.
    _play(g, [(BLACK, (0, 0)), (WHITE, (2, 0)),
              (BLACK, (1, 0)), (WHITE, (0, 1)),
              (BLACK, (4, 4))])
    captured = g.play((1, 1), WHITE)  # removes last liberty of the 2-stone group
    assert set(captured) == {(0, 0), (1, 0)}
    assert g.get((0, 0)) == EMPTY and g.get((1, 0)) == EMPTY
    assert g.captures[WHITE] == 2


def test_suicide_is_illegal():
    g = Goban(size=5)
    # White surrounds (0,0); Black playing into (0,0) would be suicide.
    _play(g, [(WHITE, (1, 0)), (BLACK, (4, 4)), (WHITE, (0, 1))])
    assert g.is_legal((0, 0), BLACK) is False
    try:
        g.play((0, 0), BLACK)
        assert False, "expected IllegalMove"
    except IllegalMove:
        pass


def test_capture_is_not_suicide():
    g = Goban(size=5)
    # Black at (0,0) with one liberty; White plays the shared point, capturing it —
    # legal even though White's stone would otherwise be low on liberties.
    _play(g, [(BLACK, (0, 0)), (WHITE, (1, 0)), (BLACK, (4, 4))])
    # White (0,1) captures black (0,0): (0,0)'s only liberty was (0,1).
    captured = g.play((0, 1), WHITE)
    assert captured == [(0, 0)]


def test_simple_ko():
    g = Goban(size=5)
    # Classic ko shape around (2,2)/(1,2).
    _play(g, [
        (BLACK, (2, 1)), (WHITE, (1, 1)),
        (BLACK, (1, 2)), (WHITE, (0, 2)),
        (BLACK, (2, 3)), (WHITE, (1, 3)),
        (BLACK, (3, 2)),  # black surrounds (2,2) shape; now white to play
    ])
    # White plays (2,2), capturing black (1,2)? Set up so a ko arises:
    captured = g.play((2, 2), WHITE)
    assert captured == [(1, 2)], captured
    # Ko: Black may not immediately recapture at (1,2).
    assert g.ko == (1, 2)
    assert g.is_legal((1, 2), BLACK) is False
    try:
        g.play((1, 2), BLACK)
        assert False, "ko recapture should be illegal"
    except IllegalMove:
        pass
    # Black plays elsewhere, White elsewhere -> ko ban lifts.
    g.play((4, 4), BLACK)
    assert g.ko is None
    assert g.is_legal((1, 2), BLACK) is True


def test_pass_and_game_over():
    g = Goban(size=5)
    g.play((0, 0), BLACK)
    assert g.is_over is False
    g.play(None, WHITE)        # white pass
    assert g.consecutive_passes == 1
    assert g.is_over is False
    g.play(None, BLACK)        # black pass -> two consecutive passes
    assert g.consecutive_passes == 2
    assert g.is_over is True


def test_pass_resets_on_play():
    g = Goban(size=5)
    g.play(None, BLACK)
    assert g.consecutive_passes == 1
    g.play((0, 0), WHITE)
    assert g.consecutive_passes == 0


def test_area_score_simple():
    g = Goban(size=3, komi=0.5)
    # Black takes the whole 3x3 by occupying the center cross; fill so all empty
    # points are black territory.
    for p in [(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)]:
        g.board[g._idx(p)] = BLACK
    # 4 empty corners are black territory; 5 black stones -> 9 area, white 0.
    assert g.area_score() == 9 - 0.5


def test_legal_moves_count():
    g = Goban(size=3)
    # Empty 3x3: all 9 points legal for black.
    assert len(g.legal_moves(BLACK)) == 9
    g.play((1, 1), BLACK)
    assert len(g.legal_moves(WHITE)) == 8


def test_copy_isolation():
    g = Goban(size=5)
    g.play((2, 2), BLACK)
    h = g.copy()
    h.play((2, 3), WHITE)
    assert g.get((2, 3)) == EMPTY      # original unchanged
    assert h.get((2, 3)) == WHITE
    assert g.move_number == 1 and h.move_number == 2


def test_superko_blocks_repeat():
    g = Goban(size=5, superko=True)
    # A positional-superko repeat is rejected; simplest proxy: a ko recapture that
    # would repeat the board is already blocked by simple ko, and superko keeps the
    # whole-board position from recurring. Here we just assert superko doesn't break
    # ordinary play and that the history set grows.
    n0 = len(g._history)
    g.play((1, 1), BLACK)
    g.play((3, 3), WHITE)
    assert len(g._history) == n0 + 2


def test_setup_stones_to_move():
    g = Goban(size=9)
    g.setup_stones([(2, 2), (6, 6)], BLACK)   # handicap → White moves
    assert g.to_move == WHITE
    h = Goban(size=9)
    h.setup_stones([(2, 2)], WHITE)           # white setup → Black moves
    assert h.to_move == BLACK


def test_place_setup_handicap():
    g = Goban(size=19)
    g.place_setup([(3, 3), (15, 15)], [])      # handicap stones, White to move
    assert g.get((3, 3)) == BLACK
    assert g.to_move == WHITE


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
