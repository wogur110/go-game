"""SGF I/O tests for app.sgf_io. Run: python tests/test_sgf.py  (needs sgfmill)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sgfmill import sgf  # noqa: E402

from app.goban import BLACK, WHITE  # noqa: E402
from app.sgf_io import from_sgf, to_sgf  # noqa: E402


def test_roundtrip_moves():
    moves = [(BLACK, (3, 3)), (WHITE, (15, 15)), (BLACK, (15, 3)),
             (WHITE, None), (BLACK, (2, 5))]   # includes a White pass
    data = to_sgf(moves, 19, 7.5, rules="chinese", result="B+3.5")
    info = from_sgf(data)
    assert info["size"] == 19
    assert info["komi"] == 7.5
    assert info["rules"] == "chinese"
    assert info["moves"] == moves


def test_corner_mapping_external():
    # Build an SGF the sgfmill way and confirm we map corners correctly.
    # sgfmill (row, col): row 0 = bottom, col 0 = left.
    game = sgf.Sgf_game(size=19)
    n1 = game.extend_main_sequence()
    n1.set_move("b", (18, 0))    # top-left
    n2 = game.extend_main_sequence()
    n2.set_move("w", (0, 18))    # bottom-right
    info = from_sgf(game.serialise())
    assert info["moves"][0] == (BLACK, (0, 0)), info["moves"][0]       # top-left -> (x0,y0)
    assert info["moves"][1] == (WHITE, (18, 18)), info["moves"][1]     # bottom-right


def test_handicap_setup_roundtrip():
    setup = [(3, 3), (15, 15), (15, 3), (3, 15)]
    data = to_sgf([(WHITE, (9, 9))], 19, 7.5, setup_black=setup)
    info = from_sgf(data)
    assert set(info["setup_black"]) == set(setup)
    assert info["moves"] == [(WHITE, (9, 9))]


def test_komi_default_when_absent():
    game = sgf.Sgf_game(size=19)
    game.extend_main_sequence().set_move("b", (3, 3))
    info = from_sgf(game.serialise())
    assert info["komi"] == 7.5


def test_size_preserved_13():
    moves = [(BLACK, (3, 3)), (WHITE, (9, 9))]
    info = from_sgf(to_sgf(moves, 13, 7.5))
    assert info["size"] == 13
    assert info["moves"] == moves


def test_first_move_on_root_node():
    # Many pro/editor SGFs put the first move on the root node alongside SZ/KM.
    data = b"(;GM[1]FF[4]SZ[19]KM[6.5]B[pd];W[dp];B[pp];W[dd])"
    info = from_sgf(data)
    assert info["komi"] == 6.5
    assert len(info["moves"]) == 4, info["moves"]
    assert info["moves"][0] == (BLACK, (15, 3)), info["moves"][0]  # SGF pd -> (x15,y3)


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
