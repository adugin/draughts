"""Puzzle data loader and manager for the Puzzle Trainer mode (D13).

Puzzles are stored as 32-char position strings (same format as
Board.to_position_string / Board.load_from_position_string).
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from draughts.config import Color

# Path to the bundled puzzle database. Primary location is the package
# resources dir (tracked in git, ships with the wheel); fall back to the
# historical dev location under .planning/data for backwards compat.
_RESOURCE_PATH = Path(__file__).parent.parent / "resources" / "russian_draughts_puzzles.json"
_LEGACY_PATH = Path(__file__).parent.parent.parent / ".planning" / "data" / "russian_draughts_puzzles.json"
_BUNDLED_PATH = _RESOURCE_PATH if _RESOURCE_PATH.exists() else _LEGACY_PATH

# Category display names (Russian)
CATEGORY_DISPLAY: dict[str, str] = {
    "combination_2cap": "Комбинация (2 взятия)",
    "combination_3cap": "Комбинация (3+ взятия)",
    "endgame": "Эндшпиль",
    "etude": "Этюд",
}


@dataclass(frozen=True)
class Puzzle:
    """A single tactical puzzle."""

    id: str
    category: str  # combination_2cap | combination_3cap | endgame | etude
    position: str  # 32-char position string
    turn: Color  # Color.WHITE or Color.BLACK
    best_move: str  # algebraic notation like "c3:e5:g3"
    solution_sequence: list[str]
    difficulty: int  # 1–4
    description: str

    @property
    def category_display(self) -> str:
        """Human-readable Russian category name."""
        return CATEGORY_DISPLAY.get(self.category, self.category)

    @property
    def difficulty_stars(self) -> str:
        """Difficulty represented as star characters."""
        return "★" * self.difficulty + "☆" * (4 - self.difficulty)


class PuzzleSet:
    """Container for a collection of puzzles with filtering/selection helpers."""

    def __init__(self, puzzles: list[Puzzle]) -> None:
        self._puzzles: list[Puzzle] = list(puzzles)
        self._by_id: dict[str, Puzzle] = {p.id: p for p in self._puzzles}

    def __len__(self) -> int:
        return len(self._puzzles)

    def __iter__(self) -> Iterator[Puzzle]:
        return iter(self._puzzles)

    def get_by_id(self, puzzle_id: str) -> Puzzle | None:
        """Return puzzle by ID, or None if not found."""
        return self._by_id.get(puzzle_id)

    def get_by_difficulty(self, d: int) -> list[Puzzle]:
        """Return all puzzles with the given difficulty level (1–4)."""
        return [p for p in self._puzzles if p.difficulty == d]

    def get_random(self, rng: random.Random | None = None, difficulty: int | None = None) -> Puzzle | None:
        """Return a random puzzle, optionally filtered by difficulty.

        Args:
            rng: Optional Random instance for reproducible results.
            difficulty: If given, only consider puzzles with this difficulty.

        Returns:
            A random Puzzle, or None if the filtered set is empty.
        """
        pool = self._puzzles if difficulty is None else self.get_by_difficulty(difficulty)
        if not pool:
            return None
        chooser = rng or random
        return chooser.choice(pool)

    def all(self) -> list[Puzzle]:
        """Return all puzzles as a list."""
        return list(self._puzzles)


def _parse_puzzle_entry(entry: dict) -> Puzzle:
    """Parse a single puzzle dict (from bundled or mined JSON) into a Puzzle."""
    turn_str = entry["turn"]
    if turn_str == "white":
        turn = Color.WHITE
    elif turn_str == "black":
        turn = Color.BLACK
    else:
        raise ValueError(f"Unknown turn value {turn_str!r} in puzzle {entry.get('id')}")

    return Puzzle(
        id=entry["id"],
        category=entry["category"],
        position=entry["position"],
        turn=turn,
        best_move=entry["best_move"],
        solution_sequence=list(entry["solution_sequence"]),
        difficulty=int(entry["difficulty"]),
        description=entry.get("description", ""),
    )


def load_bundled_puzzles() -> PuzzleSet:
    """Load puzzles from the bundled JSON database AND any user-mined puzzles.

    The two sets are merged and deduplicated by position string — if the same
    board position appears in both the bundled set and the mined collection,
    only the bundled entry is kept.

    Returns:
        PuzzleSet with all bundled puzzles plus unique mined puzzles.

    Raises:
        FileNotFoundError: If the bundled database is missing.
        ValueError: If the JSON is malformed or a required field is absent.
    """
    if not _BUNDLED_PATH.exists():
        raise FileNotFoundError(f"Bundled puzzle database not found: {_BUNDLED_PATH}")

    with _BUNDLED_PATH.open(encoding="utf-8") as fh:
        raw: list[dict] = json.load(fh)

    puzzles: list[Puzzle] = []
    seen_positions: set[str] = set()

    for entry in raw:
        p = _parse_puzzle_entry(entry)
        puzzles.append(p)
        seen_positions.add(p.position)

    # Merge in user-mined puzzles (silently skip on any error).
    try:
        from draughts.game.puzzle_miner import MINED_PUZZLES_PATH, load_mined_puzzles

        if MINED_PUZZLES_PATH.exists():
            for entry in load_mined_puzzles():
                try:
                    p = _parse_puzzle_entry(entry)
                    if p.position not in seen_positions:
                        puzzles.append(p)
                        seen_positions.add(p.position)
                except (KeyError, ValueError):
                    import logging

                    logging.getLogger("draughts.puzzles").warning(
                        "Skipping malformed mined puzzle entry: %r", entry.get("id")
                    )
    except Exception:
        import logging

        logging.getLogger("draughts.puzzles").exception("Failed to load mined puzzles; continuing with bundled only")

    return PuzzleSet(puzzles)
