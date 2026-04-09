"""Game constants, default settings, and layout definitions.

All values derived from the original Borland Pascal 7.0 source
(DRAUGHTS.PAS, ~1998-2000). UI coordinates reference the original
640x480 VGA resolution and serve as a base for runtime scaling.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

# ---------------------------------------------------------------------------
# Board constants
# ---------------------------------------------------------------------------

BOARD_SIZE = 8
CELL_SIZE = 40       # original pixel size, used as base for scaling
CELL_BORDER = 2
PIECE_RADIUS = 17    # (CELL_SIZE - CELL_BORDER * 2 - 2) // 2

# Piece characters (matching the Pascal field encoding)
EMPTY = 'n'
BLACK = 'b'
BLACK_KING = 'B'
WHITE = 'w'
WHITE_KING = 'W'

# Four diagonal directions as (dy, dx)
DIRECTIONS = [(-1, 1), (1, 1), (1, -1), (-1, -1)]

# Notation helpers
COLUMN_LETTERS = 'abcdefgh'
ROW_NUMBERS = '87654321'

# ---------------------------------------------------------------------------
# AI constants
# ---------------------------------------------------------------------------

MAX_RND = 1000       # Monte Carlo iterations
DEPTH0 = 1           # lookahead depth
NEED_TO_SAVE = 1     # minimum score change for learning DB write

# ---------------------------------------------------------------------------
# UI Layout — original 640x480 coordinates (reference for scaling)
# ---------------------------------------------------------------------------

SCREEN_W, SCREEN_H = 640, 480

# Board area
BOARD_X, BOARD_Y = 40, 40
BOARD_W = BOARD_SIZE * CELL_SIZE   # 320
BOARD_H = BOARD_SIZE * CELL_SIZE   # 320

# Frame around board
FRAME_RECT = (20, 21, 380, 361)

# Header
HEADER_RECT = (17, 1, 382, 20)

# Right panel
RPANEL_RECT = (385, 1, 639, 383)

# Buttons
BTN_X1, BTN_X2 = 530, 629
BTN_HEIGHT = 30
BTN_LABELS = [
    "Отмена хода", "Открыть", "Сохранить", "Информация",
    "Опции", "Просмотр", "Развитие", "Новая игра", "Выход",
]

# Timer, clock, date areas
TIMER_RECT = (530, 290, 629, 370)
CLOCK_RECT = (530, 395, 629, 427)
DATE_RECT = (530, 437, 629, 469)

# Bottom panel
BPANEL_RECT = (17, 385, 639, 479)
GREEN_AREA_RECT = (27, 395, 520, 469)

# Notation columns
NOTATION_WHITE_RECT = (394, 60, 456, 375)
NOTATION_BLACK_RECT = (460, 60, 521, 375)

# Sample pieces (side-panel indicators)
SAMPLE_WHITE_RECT = (395, 10, 455, 55)
SAMPLE_BLACK_RECT = (460, 10, 520, 55)

# ---------------------------------------------------------------------------
# Colors — original BGI palette converted to RGB
# ---------------------------------------------------------------------------

COLORS: Dict[str, tuple[int, int, int]] = {
    'board_frame':       (255, 255,  88),   # yellow-gold
    'board_bg':          (100,   0,  60),   # dark bordeaux-green
    'light_cell':        (255, 255,   0),   # yellow
    'dark_cell':         (170,  85,   0),   # brown
    'white_piece':       (255, 255, 255),   # white
    'black_piece':       (  0,   0,   0),   # black
    'white_piece_ring':  ( 85,  85,  85),   # darkgray
    'black_piece_ring':  (170, 170, 170),   # lightgray
    'selection_cursor':  (255,   0, 255),   # lightmagenta
    'multi_capture':     (  0, 255,   0),   # lightgreen
    'crown_fill':        (255, 255,   0),   # yellow
    'crown_gems':        (255,   0, 255),   # lightmagenta
    'panel_bg':          (192, 192, 192),   # lightgray
    'bottom_panel_bg':   (  0,  60,   0),   # dark green
    'window_title':      (  0,   0, 170),   # blue
}

# ---------------------------------------------------------------------------
# Game settings (runtime-mutable defaults)
# ---------------------------------------------------------------------------


@dataclass
class GameSettings:
    """Mutable game settings with defaults matching the original Pascal code."""

    difficulty: int = 1         # 1=Amateur, 2=Normal, 3=Professional
    speed: int = 1              # 1=Slow, 2=Medium, 3=Fast
    remind: bool = True         # hint for mandatory captures
    sound_effect: bool = False
    pause: float = 0.75         # animation delay multiplier
    use_base: bool = True       # use learning database
    invert_color: bool = False  # player plays black instead of white

    # Learning flags
    black_win: bool = True
    white_win: bool = True
    black_lose: bool = True
    white_lose: bool = True

    # Class-level lookup tables (not per-instance fields)
    DIFFICULTY_NAMES: Dict[int, str] = field(
        default_factory=lambda: {1: "Любитель", 2: "Нормал", 3: "Профессионал"},
        init=False,
        repr=False,
        compare=False,
    )
    SPEED_NAMES: Dict[int, str] = field(
        default_factory=lambda: {1: "Медленно", 2: "Средне", 3: "Быстро"},
        init=False,
        repr=False,
        compare=False,
    )

    @property
    def period(self) -> int:
        """Timer period in seconds based on speed setting."""
        return {1: 30, 2: 15, 3: 5}[self.speed]


# ---------------------------------------------------------------------------
# File / data paths
# ---------------------------------------------------------------------------

AUTOSAVE_FILENAME = 'autosave.json'
HISTORY_FILENAME = 'history.json'
LEARNING_DB_FILENAME = 'learning.json'


def get_data_dir() -> Path:
    """Return (and create if needed) the directory for saves and learning DB."""
    if os.name == 'nt':
        base = Path(os.environ.get('APPDATA', str(Path.home())))
    else:
        base = Path.home() / '.local' / 'share'
    data_dir = base / 'draughts'
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
