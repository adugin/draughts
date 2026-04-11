"""Game constants and settings.

Board encoding, piece constants, and runtime-mutable settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Board constants
# ---------------------------------------------------------------------------

BOARD_SIZE = 8

# Piece encoding — signed int8 for NumPy vectorization:
#   positive = black, negative = white, 0 = empty
#   abs(piece) == 2 → king
EMPTY = np.int8(0)
BLACK = np.int8(1)
BLACK_KING = np.int8(2)
WHITE = np.int8(-1)
WHITE_KING = np.int8(-2)

# Conversion tables (for position string serialization)
CHAR_TO_INT: dict[str, int] = {"n": 0, "b": 1, "B": 2, "w": -1, "W": -2}
INT_TO_CHAR: dict[int, str] = {0: "n", 1: "b", 2: "B", -1: "w", -2: "W"}

# Precomputed dark-square coordinates (y, x), 0-indexed, row-major order
DARK_SQUARES: list[tuple[int, int]] = [(y, x) for y in range(BOARD_SIZE) for x in range(BOARD_SIZE) if x % 2 != y % 2]

# Four diagonal directions as (dy, dx)
DIAGONAL_DIRECTIONS = [(-1, 1), (1, 1), (1, -1), (-1, -1)]

# Notation helpers (for board labels)
COLUMN_LETTERS = "abcdefgh"
ROW_NUMBERS = "87654321"


# ---------------------------------------------------------------------------
# Color enum — type-safe replacement for "b"/"w" string tokens
# ---------------------------------------------------------------------------


class Color(StrEnum):
    """Side color. Inherits from str so Color.BLACK == "b" is True."""

    BLACK = "b"
    WHITE = "w"

    @property
    def opponent(self) -> Color:
        """Return the opposite color."""
        return Color.WHITE if self is Color.BLACK else Color.BLACK


# Colors used by board rendering
COLORS: dict[str, tuple[int, int, int]] = {
    "selection_cursor": (255, 0, 255),
    "multi_capture": (0, 255, 0),
}

# ---------------------------------------------------------------------------
# Game settings (runtime-mutable)
# ---------------------------------------------------------------------------


@dataclass
class GameSettings:
    """Mutable game settings."""

    difficulty: int = 1  # 1=Amateur, 2=Normal, 3=Professional
    remind: bool = True  # hint for mandatory captures
    pause: float = 0.75  # animation delay multiplier
    invert_color: bool = False  # player plays black instead of white
    search_depth: int = 0  # 0=auto (from difficulty), 1-10=manual override

    DIFFICULTY_NAMES: dict[int, str] = field(
        default_factory=lambda: {1: "Любитель", 2: "Нормал", 3: "Профессионал"},
        init=False,
        repr=False,
        compare=False,
    )


# ---------------------------------------------------------------------------
# File / data paths
# ---------------------------------------------------------------------------

AUTOSAVE_FILENAME = "autosave.json"


def get_data_dir() -> Path:
    """Return (and create if needed) the application data directory."""
    base = Path(os.environ.get("APPDATA", str(Path.home()))) if os.name == "nt" else Path.home() / ".local" / "share"
    data_dir = base / "draughts"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
