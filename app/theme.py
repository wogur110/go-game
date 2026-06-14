"""Dark UI palette + goban/stone colours (shared by the board widget and sidebar).

Mirrors Chess Studio's dark theme so the two apps feel like siblings.
"""

from __future__ import annotations

# --- App chrome (dark) --------------------------------------------------------
BG_MAIN = "#15181e"
BG_PANEL = "#1b1f27"
BG_PANEL_LIGHT = "#222734"
TEXT = "#d7dde6"
TEXT_DIM = "#8b93a1"
TEXT_MUTED = "#5b636f"
ACCENT = "#46b1e1"
GOOD = "#2dd4a0"
WARN = "#e5c07b"
BAD = "#e06c75"

# --- Goban --------------------------------------------------------------------
BOARD_BG = "#e3b562"        # wood
BOARD_BG_EDGE = "#caa052"   # subtle vignette toward the edge
BOARD_LINE = "#2e2310"
BOARD_STAR = "#2e2310"
COORD_TEXT = "#6b5631"

# Stones rendered as radial gradients (highlight -> body).
STONE_BLACK_HI = "#5a626d"
STONE_BLACK_LO = "#080a0e"
STONE_WHITE_HI = "#ffffff"
STONE_WHITE_LO = "#c4cad2"
STONE_EDGE = "#0a0c10"

LAST_MOVE = "#e23b3b"        # last-move marker

# --- Analysis overlays (used from M2) ----------------------------------------
OWN_BLACK = "#101216"        # ownership tinted toward Black
OWN_WHITE = "#f2f4f8"        # ownership tinted toward White
CANDIDATE = ("#3fb56b", "#46a1e1", "#9a6cd0")  # top-3 candidate move tints


def build_stylesheet() -> str:
    """Minimal dark Qt stylesheet (sibling to Chess Studio's theme)."""
    return f"""
    QWidget {{ background: {BG_MAIN}; color: {TEXT}; font-size: 13px; }}
    QLabel {{ color: {TEXT_DIM}; }}
    QLabel#Status {{ color: {TEXT}; font-size: 14px; padding: 2px 0; }}
    QLabel#Estimate {{ color: {GOOD}; font-size: 13px; font-weight: bold; }}
    QPushButton {{ background: {BG_PANEL_LIGHT}; border: 1px solid #2c323d;
                   border-radius: 6px; padding: 7px 10px; color: {TEXT}; }}
    QPushButton:hover {{ background: #2a3140; }}
    QPushButton:pressed {{ background: #313a4b; }}
    QPushButton:disabled {{ color: {TEXT_MUTED}; }}
    QComboBox {{ background: {BG_PANEL_LIGHT}; border: 1px solid #2c323d;
                 border-radius: 6px; padding: 5px 8px; color: {TEXT}; }}
    QComboBox QAbstractItemView {{ background: {BG_PANEL}; color: {TEXT};
                 selection-background-color: {ACCENT}; }}
    """
