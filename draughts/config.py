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
BOARD_PX = 640  # fixed board widget size in pixels
APP_NAME = "Шашки"  # single source of truth for the window title

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
    "selection_cursor": (0, 255, 0),  # green — start/end position
    "multi_capture": (255, 0, 255),  # magenta — intermediate capture positions
}

# ---------------------------------------------------------------------------
# Game settings (runtime-mutable)
# ---------------------------------------------------------------------------


@dataclass
class GameSettings:
    """Mutable game settings."""

    difficulty: int = 3  # default: Клубный (~1400) — approachable for first-time users
    remind: bool = True  # hint for mandatory captures
    pause: float = 0.5  # animation delay multiplier (snappy, matches competitors)
    invert_color: bool = False  # player plays black instead of white
    search_depth: int = 0  # 0=auto (from difficulty), 1-10=manual override
    # UI extras (D15)
    board_theme: str = "dark_wood"  # "dark_wood" | "classic_light" (D18)
    show_coordinates: bool = True
    highlight_last_move: bool = True  # universally ON in modern platforms
    show_legal_moves_hover: bool = True  # critical for beginners
    # Engine stubs (D15 — wired to UI but TT resize / SMP not implemented yet)
    hash_size_mb: int = 32
    # Opening book (D8)
    use_opening_book: bool = True
    # Endgame bitbase (D9)
    use_endgame_bitbase: bool = True
    # Tuned eval weights (D11 — Texel method)
    use_tuned_eval: bool = True
    # NOTE: DIFFICULTY_NAMES is kept for backward compat; new code uses
    # draughts.game.ai.elo.ELO_LEVELS directly.
    DIFFICULTY_NAMES: dict[int, str] = field(
        default_factory=lambda: {
            1: "Новичок (~800)",
            2: "Любитель (~1100)",
            3: "Клубный (~1400)",
            4: "Сильный клубный (~1700)",
            5: "Кандидат (~2000)",
            6: "Мастер (~2200+)",
        },
        init=False,
        repr=False,
        compare=False,
    )


# ---------------------------------------------------------------------------
# Migration helper — called when loading settings saved with the old
# three-level system (1=Любитель, 2=Нормал, 3=Профессионал).
# ---------------------------------------------------------------------------

_OLD_TO_NEW: dict[int, int] = {1: 3, 2: 4, 3: 5}


def migrate_difficulty(old: int) -> int:
    """Map a legacy 3-level difficulty to the new 6-level scale.

    Old mapping:  1 (Любитель) → 3 (Клубный ~1400)
                  2 (Нормал)   → 4 (Сильный клубный ~1700)
                  3 (Профи)    → 5 (Кандидат ~2000)
    Values already in the new range (1-6) are returned unchanged.
    """
    if old in _OLD_TO_NEW:
        return _OLD_TO_NEW[old]
    # Already a valid new-scale value, or unknown — clamp to [1, 6]
    return max(1, min(6, old))


# ---------------------------------------------------------------------------
# File / data paths
# ---------------------------------------------------------------------------

AUTOSAVE_FILENAME = "autosave.json"
SETTINGS_FILENAME = "settings.json"


def get_data_dir() -> Path:
    """Return (and create if needed) the application data directory."""
    base = Path(os.environ.get("APPDATA", str(Path.home()))) if os.name == "nt" else Path.home() / ".local" / "share"
    data_dir = base / "draughts"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

# Fields that are persisted to settings.json (UI preferences only —
# not game state like invert_color or search_depth which are per-game).
_PERSISTENT_FIELDS = [
    "difficulty", "remind", "pause", "board_theme",
    "show_coordinates", "highlight_last_move", "show_legal_moves_hover",
    "hash_size_mb", "use_opening_book", "use_endgame_bitbase", "use_tuned_eval",
]


def save_settings(settings: GameSettings) -> None:
    """Save user preferences to settings.json in the data directory."""
    import json

    data = {k: getattr(settings, k) for k in _PERSISTENT_FIELDS}
    path = get_data_dir() / SETTINGS_FILENAME
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_settings() -> GameSettings:
    """Load user preferences from settings.json, falling back to defaults.

    Unknown keys are silently ignored (forward compatibility).
    Missing keys use the dataclass defaults (backward compatibility).
    Type mismatches are silently skipped (corrupt or hand-edited file).
    """
    import json

    path = get_data_dir() / SETTINGS_FILENAME
    settings = GameSettings()
    if not path.exists():
        return settings

    # Expected types for type-safe validation
    _FIELD_TYPES: dict[str, type] = {
        "difficulty": int, "remind": bool, "pause": (int, float),
        "board_theme": str, "show_coordinates": bool,
        "highlight_last_move": bool, "show_legal_moves_hover": bool,
        "hash_size_mb": int, "use_opening_book": bool,
        "use_endgame_bitbase": bool, "use_tuned_eval": bool,
    }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in _PERSISTENT_FIELDS:
            if key in data:
                val = data[key]
                expected = _FIELD_TYPES.get(key)
                if expected is not None and not isinstance(val, expected):
                    continue  # skip type-mismatched values
                setattr(settings, key, val)
    except Exception:
        pass  # corrupted file — use defaults
    return settings
