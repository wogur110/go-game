"""Probe KataGo ownership array orientation + sign (one-off, needs GPU).

Places Black influence in the TOP-LEFT and White in the BOTTOM-RIGHT, then prints
the ownership value at a few known points so we can confirm:
  * index order:  i = y*size + x  with y=0 = top row (GTP row `size`)
  * sign:         positive = Black-owned
"""

from __future__ import annotations

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.engine.analysis_client import AnalysisClient  # noqa: E402
from app.engine.coords import to_gtp  # noqa: E402
from app.engine.discovery import find_config, find_katago, find_model  # noqa: E402
from app.engine.networks import NETWORKS  # noqa: E402

SIZE = 19


def main() -> int:
    katago = find_katago()
    b28 = find_model(NETWORKS["b28"].filename)
    cfg = find_config("analysis.cfg")
    if not all([katago, b28, cfg]):
        print("missing engine/model/config")
        return 1

    done = threading.Event()
    box: dict = {}
    client = AnalysisClient(katago, cfg, b28,
                            lambda i, r: (box.__setitem__("r", r), done.set()),
                            lambda m: (box.__setitem__("e", m), done.set()))
    client.start()

    # Black stones top-left, White stones bottom-right.
    black = [(2, 2), (4, 2), (2, 4)]
    white = [(16, 16), (14, 16), (16, 14)]
    moves = []
    for i in range(max(len(black), len(white))):
        if i < len(black):
            moves.append(["B", to_gtp(black[i], SIZE)])
        if i < len(white):
            moves.append(["W", to_gtp(white[i], SIZE)])

    client.analyze("probe", moves, board_size=SIZE, komi=7.5, rules="chinese",
                   max_visits=300, include_ownership=True)
    if not done.wait(180) or "r" not in box:
        print("no result:", box.get("e"))
        client.stop()
        return 1

    own = box["r"].ownership
    client.stop()
    if not own or len(own) != SIZE * SIZE:
        print("bad ownership length:", None if not own else len(own))
        return 1

    def val(x, y):
        return own[y * SIZE + x]

    tl = val(2, 2)      # near black
    br = val(16, 16)    # near white
    print(f"len={len(own)}")
    print(f"top-left  (2,2)={to_gtp((2,2),SIZE)}: {tl:+.3f}  (Black area)")
    print(f"bot-right (16,16)={to_gtp((16,16),SIZE)}: {br:+.3f}  (White area)")
    print(f"=> i=y*size+x, y=0=top: {'OK' if tl > br else 'FLIPPED'}")
    print(f"=> sign: positive = {'BLACK' if tl > 0 else 'WHITE'}-owned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
