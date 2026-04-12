"""Tests for the Puzzle Trainer feature (D13).

Covers:
  1. load_bundled_puzzles — loads all 30 puzzles
  2. get_by_difficulty — filter works
  3. get_random_returns_puzzle — not None
  4. puzzle_has_valid_position — each puzzle's position string loads into Board
  5. puzzle_best_move_is_legal — best_move is among legal moves for each puzzle
  6. session_save_load_roundtrip — save progress, load, equal
"""

from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from draughts.config import Color
from draughts.game.board import Board
from draughts.game.puzzles import Puzzle, PuzzleSet, load_bundled_puzzles


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _notation_to_path(move_str: str) -> list[tuple[int, int]]:
    """Convert 'c3:e5:g3' or 'c3-e5' to a list of (x, y) board positions."""
    sep = ":" if ":" in move_str else "-"
    return [Board.notation_to_pos(sq) for sq in move_str.split(sep)]


def _get_all_legal_paths(board: Board, turn: Color) -> list[list[tuple[int, int]]]:
    """Return all legal move paths for the given side (captures first)."""
    import numpy as np

    positions = np.argwhere(board.grid > 0) if turn == Color.BLACK else np.argwhere(board.grid < 0)
    captures: list[list[tuple[int, int]]] = []
    simple: list[list[tuple[int, int]]] = []
    for pos in positions:
        y, x = int(pos[0]), int(pos[1])
        caps = board.get_captures(x, y)
        if caps:
            captures.extend(caps)
        else:
            for tx, ty in board.get_valid_moves(x, y):
                simple.append([(x, y), (tx, ty)])
    return captures if captures else simple


# ---------------------------------------------------------------------------
# Test 1: load_bundled_puzzles
# ---------------------------------------------------------------------------

def test_load_bundled_puzzles():
    """All 30 bundled puzzles load without error."""
    ps = load_bundled_puzzles()
    assert len(ps) == 30, f"Expected 30 puzzles, got {len(ps)}"


# ---------------------------------------------------------------------------
# Test 2: get_by_difficulty
# ---------------------------------------------------------------------------

def test_get_by_difficulty():
    """Filtering by difficulty returns only matching puzzles."""
    ps = load_bundled_puzzles()

    for d in range(1, 5):
        subset = ps.get_by_difficulty(d)
        assert all(p.difficulty == d for p in subset), (
            f"Difficulty filter {d} returned puzzles with wrong difficulty"
        )

    # Total across all levels must equal 30
    total = sum(len(ps.get_by_difficulty(d)) for d in range(1, 5))
    assert total == 30, f"Sum of difficulty buckets should be 30, got {total}"


# ---------------------------------------------------------------------------
# Test 3: get_random_returns_puzzle
# ---------------------------------------------------------------------------

def test_get_random_returns_puzzle():
    """get_random returns a Puzzle (not None) for the full set."""
    ps = load_bundled_puzzles()
    rng = random.Random(42)

    result = ps.get_random(rng=rng)
    assert result is not None
    assert isinstance(result, Puzzle)


def test_get_random_with_difficulty_filter():
    """get_random respects difficulty filter."""
    ps = load_bundled_puzzles()
    rng = random.Random(42)

    for d in range(1, 5):
        result = ps.get_random(rng=rng, difficulty=d)
        assert result is not None
        assert result.difficulty == d


def test_get_random_invalid_difficulty_returns_none():
    """get_random returns None for a difficulty with no puzzles."""
    ps = load_bundled_puzzles()
    result = ps.get_random(difficulty=99)
    assert result is None


# ---------------------------------------------------------------------------
# Test 4: puzzle_has_valid_position
# ---------------------------------------------------------------------------

def test_puzzle_has_valid_position():
    """Every puzzle's 32-char position string loads into a Board without error."""
    ps = load_bundled_puzzles()
    for puzzle in ps:
        board = Board(empty=True)
        # Should not raise
        board.load_from_position_string(puzzle.position)
        # Verify it's exactly 32 chars
        assert len(puzzle.position) == 32, (
            f"Puzzle {puzzle.id} position has length {len(puzzle.position)}, expected 32"
        )
        # Verify it round-trips
        assert board.to_position_string() == puzzle.position, (
            f"Puzzle {puzzle.id} position string does not round-trip"
        )


# ---------------------------------------------------------------------------
# Test 5: puzzle_best_move_is_legal
# ---------------------------------------------------------------------------

def test_puzzle_best_move_is_legal():
    """For every puzzle, the best_move is among the legal moves on the given position."""
    ps = load_bundled_puzzles()
    failures = []

    for puzzle in ps:
        board = Board(empty=True)
        board.load_from_position_string(puzzle.position)

        best_path = _notation_to_path(puzzle.best_move)
        legal_paths = _get_all_legal_paths(board, puzzle.turn)

        if best_path not in legal_paths:
            failures.append(
                f"{puzzle.id}: best_move={puzzle.best_move!r} not in legal paths. "
                f"Legal: {[[Board.pos_to_notation(x, y) for x, y in p] for p in legal_paths[:5]]}"
            )

    assert not failures, "Some puzzles have illegal best_move:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# Test 6: session_save_load_roundtrip
# ---------------------------------------------------------------------------

def test_session_save_load_roundtrip(tmp_path):
    """Save progress dict to disk and load it back — values are preserved."""
    from draughts.ui import puzzle_widget as pw

    progress_file = tmp_path / "puzzle_progress.json"
    sample = {
        "solved": ["puzzle_001", "puzzle_005"],
        "streak": 3,
        "best_streak": 7,
        "total_attempts": 42,
        "total_correct": 28,
    }

    # Patch the path used by the module
    with patch.object(pw, "_PROGRESS_PATH", progress_file):
        pw._save_progress(sample)
        loaded = pw._load_progress()

    assert loaded["solved"] == sample["solved"]
    assert loaded["streak"] == sample["streak"]
    assert loaded["best_streak"] == sample["best_streak"]
    assert loaded["total_attempts"] == sample["total_attempts"]
    assert loaded["total_correct"] == sample["total_correct"]


def test_session_load_missing_file_returns_defaults(tmp_path):
    """Loading from a non-existent file returns the default progress dict."""
    from draughts.ui import puzzle_widget as pw

    missing = tmp_path / "nonexistent.json"
    with patch.object(pw, "_PROGRESS_PATH", missing):
        result = pw._load_progress()

    assert result["solved"] == []
    assert result["streak"] == 0
    assert result["best_streak"] == 0
    assert result["total_attempts"] == 0
    assert result["total_correct"] == 0
