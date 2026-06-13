"""Locate the KataGo binary, network weights and config files.

Mirrors Chess Studio's ``find_stockfish()``: search a list of candidate roots
(PyInstaller ``_MEIPASS`` bundle dir, frozen-exe dir, project root, cwd) and fall
back to a ``katago`` found on ``PATH``.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional


def candidate_roots() -> List[Path]:
    roots: List[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    roots.append(project_root())
    roots.append(Path.cwd())
    return roots


def project_root() -> Path:
    # app/engine/discovery.py -> project root is two parents up from app/.
    return Path(__file__).resolve().parents[2]


def os_subdir() -> str:
    return "windows" if os.name == "nt" else "linux"


def find_katago() -> Optional[str]:
    exe = "katago.exe" if os.name == "nt" else "katago"
    rel = Path("engines") / os_subdir() / exe
    for root in candidate_roots():
        cand = root / rel
        if cand.is_file():
            return str(cand)
    # Fall back to a nested copy (some release archives extract into a subfolder).
    for root in candidate_roots():
        engines = root / "engines" / os_subdir()
        if engines.is_dir():
            nested = next((p for p in engines.rglob(exe) if p.is_file()), None)
            if nested:
                return str(nested)
    return shutil.which("katago")


def models_dir() -> Path:
    return project_root() / "models"


def find_model(filename: str) -> Optional[str]:
    for root in candidate_roots():
        cand = root / "models" / filename
        if cand.is_file():
            return str(cand)
    return None


def find_config(name: str) -> Optional[str]:
    rel = Path("configs") / name
    for root in candidate_roots():
        cand = root / rel
        if cand.is_file():
            return str(cand)
    return None
