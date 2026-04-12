"""Tests for the opening book (D8).

Covers:
  1. Empty book returns None
  2. Add + probe exact position
  3. Save / load round-trip
  4. Weighted random choice distribution
  5. Starter book loads and has >= 50 positions
  6. AIEngine plays a book move on the start position
  7. Determinism: same RNG seed -> same probe result
"""

from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path

import pytest

from draughts.config import Color
from draughts.game.ai.book import OpeningBook, BookEntry
from draughts.game.ai.search import AIMove, AIEngine
from draughts.game.ai.tt import _zobrist_hash
from draughts.game.board import Board


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _start_board() -> Board:
    return Board()


def _start_hash() -> int:
    return _zobrist_hash(_start_board().grid, Color.WHITE)


def _dummy_move(x1: int = 0, y1: int = 5, x2: int = 1, y2: int = 4) -> AIMove:
    return AIMove(kind="move", path=[(x1, y1), (x2, y2)])


# ---------------------------------------------------------------------------
# Test 1 — empty book probe returns None
# ---------------------------------------------------------------------------


def test_empty_book_probe_returns_none():
    book = OpeningBook()
    result = book.probe(_start_board(), Color.WHITE)
    assert result is None


# ---------------------------------------------------------------------------
# Test 2 — add a move then probe the same position gets it back
# ---------------------------------------------------------------------------


def test_add_and_probe_exact_position():
    book = OpeningBook()
    board = _start_board()
    move = AIMove(kind="move", path=[(0, 5), (1, 4)])
    h = _zobrist_hash(board.grid, Color.WHITE)
    book.add(h, move, weight=1)

    result = book.probe(board, Color.WHITE)
    assert result is not None
    assert result.kind == "move"
    assert result.path == [(0, 5), (1, 4)]


# ---------------------------------------------------------------------------
# Test 3 — save / load round-trip
# ---------------------------------------------------------------------------


def test_save_load_roundtrip():
    book = OpeningBook()
    board = _start_board()
    h = _zobrist_hash(board.grid, Color.WHITE)

    move1 = AIMove(kind="move", path=[(0, 5), (1, 4)])
    move2 = AIMove(kind="move", path=[(2, 5), (1, 4)])
    book.add(h, move1, weight=3)
    book.add(h, move2, weight=1)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp_path = Path(f.name)

    try:
        book.save(tmp_path)
        book2 = OpeningBook.load(tmp_path)

        assert len(book2) == len(book)
        entry = book2._entries.get(h)
        assert entry is not None
        assert len(entry.moves) == 2

        paths = [tuple(m[0]) for m in entry.moves]
        weights = {m[0]: m[1] for m in entry.moves}
        assert tuple(move1.path) in paths
        assert tuple(move2.path) in paths
        assert weights[tuple(move1.path)] == 3
        assert weights[tuple(move2.path)] == 1
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Test 4 — weighted choice distribution
# ---------------------------------------------------------------------------


def test_weighted_choice():
    """Higher-weight move should be chosen proportionally more often."""
    book = OpeningBook()
    board = _start_board()
    h = _zobrist_hash(board.grid, Color.WHITE)

    heavy = AIMove(kind="move", path=[(0, 5), (1, 4)])
    light = AIMove(kind="move", path=[(2, 5), (1, 4)])
    book.add(h, heavy, weight=9)
    book.add(h, light, weight=1)

    rng = random.Random(12345)
    counts: dict[tuple, int] = {}
    n_trials = 1000
    for _ in range(n_trials):
        m = book.probe(board, Color.WHITE, rng=rng)
        assert m is not None
        key = tuple(m.path)
        counts[key] = counts.get(key, 0) + 1

    heavy_key = tuple(heavy.path)
    light_key = tuple(light.path)
    # Heavy should be chosen roughly 90% of the time; allow ±10% tolerance
    assert counts.get(heavy_key, 0) > 800, f"Heavy move chosen only {counts.get(heavy_key,0)}/1000 times"
    assert counts.get(light_key, 0) > 50, f"Light move chosen only {counts.get(light_key,0)}/1000 times"


# ---------------------------------------------------------------------------
# Test 5 — starter book loads from disk
# ---------------------------------------------------------------------------


def test_starter_book_loads():
    """The pre-built opening book ships with the package and has >= 50 positions."""
    import draughts.game.ai as ai_pkg

    book = ai_pkg.DEFAULT_BOOK
    if book is None:
        # Try loading manually
        import importlib.resources
        try:
            ref = importlib.resources.files("draughts.resources").joinpath("opening_book.json")
            with importlib.resources.as_file(ref) as p:
                book = OpeningBook.load(p)
        except Exception as e:
            pytest.skip(f"opening_book.json not found: {e}")

    assert len(book) >= 50, f"Starter book has only {len(book)} positions (expected >= 50)"


# ---------------------------------------------------------------------------
# Test 6 — AIEngine with starter book plays a book move
# ---------------------------------------------------------------------------


def test_engine_plays_book_move():
    """AIEngine with the default book should play a move that the book knows."""
    import draughts.game.ai as ai_pkg

    book = ai_pkg.DEFAULT_BOOK
    if book is None:
        pytest.skip("opening_book.json not found")

    board = _start_board()
    h = _zobrist_hash(board.grid, Color.WHITE)
    entry = book._entries.get(h)
    if entry is None or not entry.moves:
        pytest.skip("Start position not in book")

    book_paths = {m[0] for m in entry.moves}

    engine = AIEngine(difficulty=2, color=Color.WHITE, book=book)
    move = engine.find_move(board)

    assert move is not None, "Engine returned no move"
    assert tuple(move.path) in book_paths, (
        f"Engine played {move.path} which is not in book paths {book_paths}"
    )


# ---------------------------------------------------------------------------
# Test 7 — determinism: same RNG seed -> same probe result
# ---------------------------------------------------------------------------


def test_book_probe_determinism():
    """Same position + same RNG seed must return the same move."""
    book = OpeningBook()
    board = _start_board()
    h = _zobrist_hash(board.grid, Color.WHITE)

    book.add(h, AIMove(kind="move", path=[(0, 5), (1, 4)]), weight=5)
    book.add(h, AIMove(kind="move", path=[(2, 5), (1, 4)]), weight=5)
    book.add(h, AIMove(kind="move", path=[(2, 5), (3, 4)]), weight=5)

    results = []
    for _ in range(3):
        rng = random.Random(99)  # same seed each time
        m = book.probe(board, Color.WHITE, rng=rng)
        assert m is not None
        results.append(tuple(m.path))

    assert len(set(results)) == 1, f"Non-deterministic results with same seed: {results}"


# ---------------------------------------------------------------------------
# Test 8 — bookless engine still searches normally
# ---------------------------------------------------------------------------


def test_bookless_engine_searches():
    """Passing book=None disables book lookup; engine still returns a legal move."""
    engine = AIEngine(difficulty=2, color=Color.WHITE, book=None)
    board = _start_board()
    move = engine.find_move(board)
    assert move is not None
    assert move.kind in ("move", "capture")
