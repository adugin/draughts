"""Puzzle auto-mining from analyzed games (ROADMAP #22).

Scans a game's analysis annotations for blunders (??), then extracts
each blunder position as a puzzle candidate for the opposite side to
solve (find the refutation).

Pure logic module — no Qt imports.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("draughts.puzzle_miner")


def _default_mined_path() -> Path:
    from draughts.user_data import mined_puzzles_path

    return mined_puzzles_path()


# Module-level path — assigned lazily on first access AND directly
# writable by tests via monkey-patch / ``unittest.mock.patch``.
# Kept as a mutable module attribute (not a property) so existing tests
# using ``patch("draughts.game.puzzle_miner.MINED_PUZZLES_PATH", ...)``
# keep working unchanged.
MINED_PUZZLES_PATH: Path = _default_mined_path()


def _mined_puzzles_path() -> Path:
    """Return the currently-configured path (honours test patches)."""
    return MINED_PUZZLES_PATH

# Minimum eval-swing to qualify a position as a puzzle.
# With tuned weights (_PAWN_VALUE ~1.9), losing one pawn ≈ 2 eval units.
# Previous value (400) was calibrated for _PAWN_VALUE=5.0 and never
# triggered after Texel tuning reduced the eval scale.
_DEFAULT_MIN_DELTA = 4.0

# Difficulty mapping by delta magnitude (lower-bound inclusive).
# Ranges: 4-6 → d2, 6-10 → d3, 10+ → d4
_DIFF_THRESHOLDS = [
    (10.0, 4),  # delta ≥ 10 (~5 pawns) → difficulty 4
    (6.0, 3),  # delta ≥ 6  (~3 pawns) → difficulty 3
]


def _delta_to_difficulty(delta_cp: float) -> int:
    """Map eval-swing magnitude to puzzle difficulty (2-4).

    Boundaries are inclusive on the lower bound:
      delta ≥ 1000 → 4
      delta ≥ 600  → 3
      delta ≥ 400  → 2  (minimum for any blunder)
    """
    for threshold, difficulty in _DIFF_THRESHOLDS:
        if delta_cp >= threshold:
            return difficulty
    return 2  # minimum for any blunder (400 ≤ delta < 600)


def _turn_string(ply: int, start_color=None) -> str:
    """Return 'white' or 'black' for the side that moves on *ply*.

    ``start_color`` names the side that moved at ply 0 (games loaded
    from a black-to-move FEN start with Black). Defaults to White for
    backward compat with self-play pipelines that always start with
    the standard opening.
    """
    from draughts.config import Color

    if start_color is None:
        start_color = Color.WHITE

    if start_color == Color.WHITE:
        return "white" if ply % 2 == 0 else "black"
    return "black" if ply % 2 == 0 else "white"


def mine_puzzles_from_game(
    positions: list[str],
    annotations: list,  # list[MoveAnnotation] from game_analyzer
    min_delta_cp: float = _DEFAULT_MIN_DELTA,
    start_color=None,
) -> list[dict]:
    """Extract puzzle candidates from an analyzed game.

    For each blunder (annotation == "??") at ply N:
    - The puzzle position is positions[N] (before the blunder).
    - The side to SOLVE is the OPPONENT of whoever blundered.
    - The best_move is the engine's recommended move stored in the
      annotation's ``best_notation`` field.
    - Difficulty is inferred from the delta magnitude.
    - Category is "combination_2cap" when the best move is a capture
      (contains ":"), otherwise "endgame".

    Args:
        positions: List of 32-char position strings; positions[i] is the
            board state before ply i was played.
        annotations: List of MoveAnnotation objects from
            draughts.ui.game_analyzer.analyze_game_positions().
        min_delta_cp: Minimum eval swing in centipawn units to qualify.
        start_color: Side to move at positions[0]. Defaults to White.
            For FEN-loaded black-to-move games the "turn" field on each
            puzzle would otherwise be inverted, so the trainer would
            prompt the wrong side to solve.

    Returns:
        List of puzzle dicts matching the russian_draughts_puzzles.json
        schema (id, category, position, turn, best_move,
        solution_sequence, difficulty, source, description).
        Returns an empty list if there are no qualifying blunders.
    """
    if not positions or not annotations:
        return []

    puzzles: list[dict] = []
    seen_positions: set[str] = set()  # avoid duplicate positions

    for ann in annotations:
        if ann.annotation != "??":
            continue
        if ann.delta_cp < min_delta_cp:
            continue

        ply = ann.ply
        if ply >= len(positions):
            logger.warning("Annotation ply %d out of range (positions len=%d)", ply, len(positions))
            continue

        pos_str = positions[ply]
        if not pos_str or len(pos_str) != 32:
            logger.warning("Invalid position string at ply %d: %r", ply, pos_str)
            continue

        if pos_str in seen_positions:
            continue
        seen_positions.add(pos_str)

        # The blunderer is the side to move at ply N.
        blunderer_turn = _turn_string(ply, start_color)
        # The solver plays AS the blunderer: the puzzle asks "what should
        # you have played instead?" from the pre-blunder position.  The
        # best_move in the annotation is the engine's recommendation for
        # the side-to-move (the blunderer), so solver_turn must match.
        solver_turn = blunderer_turn

        best_move = ann.best_notation
        if not best_move or best_move == "—":
            # No engine suggestion recorded — skip.
            logger.debug("Ply %d has no best_notation; skipping", ply)
            continue

        # Determine category: capture if ":" appears in the best move notation.
        category = "combination_2cap" if ":" in best_move else "endgame"

        difficulty = _delta_to_difficulty(ann.delta_cp)

        puzzle_id = f"mined_{ply:03d}_{pos_str[:8]}"

        description = (
            f"{'Белые' if solver_turn == 'white' else 'Чёрные'} находят лучший ответ "
            f"на ошибку соперника (потеря {ann.delta_cp:.0f} ед.)."
        )

        puzzle: dict = {
            "id": puzzle_id,
            "category": category,
            "position": pos_str,
            "turn": solver_turn,
            "best_move": best_move,
            "solution_sequence": [best_move],
            "difficulty": difficulty,
            "source": "auto_mined",
            "description": description,
        }
        puzzles.append(puzzle)
        logger.info(
            "Mined puzzle from ply %d: solver=%s delta=%.0f difficulty=%d",
            ply,
            solver_turn,
            ann.delta_cp,
            difficulty,
        )

    return puzzles


# ---------------------------------------------------------------------------
# Persistence helpers (no Qt)
# ---------------------------------------------------------------------------


def load_mined_puzzles() -> list[dict]:
    """Load mined puzzles from the user's personal collection.

    Returns an empty list if the file does not exist or is malformed.
    """
    path = _mined_puzzles_path()
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
        logger.warning("Mined puzzles file has unexpected format; returning []")
        return []
    except Exception:
        logger.exception("Failed to load mined puzzles from %s", path)
        return []


def save_mined_puzzles(puzzles: list[dict]) -> None:
    """Persist the full mined puzzle list to the user's personal collection.

    Args:
        puzzles: Complete list of puzzle dicts to write (overwrites existing).

    Raises:
        OSError: If the directory cannot be created or the file cannot be written.
    """
    path = _mined_puzzles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(puzzles, fh, ensure_ascii=False, indent=2)
    logger.info("Saved %d mined puzzles to %s", len(puzzles), path)


def append_mined_puzzles(new_puzzles: list[dict]) -> int:
    """Append new puzzles to the user's personal collection.

    Deduplicates by position string — a position already in the collection
    is not added again.

    Args:
        new_puzzles: Puzzle dicts to merge in.

    Returns:
        Number of puzzles actually added (after deduplication).
    """
    existing = load_mined_puzzles()
    existing_positions: set[str] = {p.get("position", "") for p in existing}

    added = 0
    for puzzle in new_puzzles:
        pos = puzzle.get("position", "")
        if pos and pos not in existing_positions:
            existing.append(puzzle)
            existing_positions.add(pos)
            added += 1

    if added:
        save_mined_puzzles(existing)

    return added
