"""Tests for M9.b — OpeningBook.probe_all + controller.get_book_moves."""

from __future__ import annotations

import pytest
from draughts.config import Color
from draughts.game.ai import DEFAULT_BOOK
from draughts.game.ai.book import OpeningBook
from draughts.game.ai.search import AIMove
from draughts.game.board import Board

# ---------------------------------------------------------------------------
# OpeningBook.probe_all
# ---------------------------------------------------------------------------


def test_probe_all_empty_when_position_unknown():
    """Unknown Zobrist hash → empty result."""
    book = OpeningBook()
    b = Board()
    assert book.probe_all(b, Color.WHITE) == []


def test_probe_all_returns_all_moves_sorted_by_weight():
    """Multiple moves with different weights, sorted best-first."""
    book = OpeningBook()
    from draughts.game.ai.book import _zobrist_hash

    h = _zobrist_hash(Board().grid, Color.WHITE)
    book.add(h, AIMove("move", [(0, 5), (1, 4)]), weight=3)
    book.add(h, AIMove("move", [(2, 5), (3, 4)]), weight=7)
    book.add(h, AIMove("move", [(4, 5), (5, 4)]), weight=1)

    result = book.probe_all(Board(), Color.WHITE)
    assert len(result) == 3
    weights = [w for _, w in result]
    assert weights == [7, 3, 1], "probe_all must sort by descending weight"


def test_probe_all_weights_preserved():
    """The numeric weight is returned verbatim."""
    book = OpeningBook()
    from draughts.game.ai.book import _zobrist_hash

    h = _zobrist_hash(Board().grid, Color.WHITE)
    book.add(h, AIMove("move", [(0, 5), (1, 4)]), weight=42)
    [(mv, w)] = book.probe_all(Board(), Color.WHITE)
    assert w == 42
    assert mv.path == [(0, 5), (1, 4)]


def test_probe_all_default_book_has_start_moves():
    """The bundled opening book covers the starting position."""
    if DEFAULT_BOOK is None:
        pytest.skip("DEFAULT_BOOK is not loaded in this environment")
    moves = DEFAULT_BOOK.probe_all(Board(), Color.WHITE)
    assert len(moves) >= 1, "start position should be in the book"


# ---------------------------------------------------------------------------
# Controller.get_book_moves
# ---------------------------------------------------------------------------


@pytest.fixture
def qt_app():
    import sys

    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def test_get_book_moves_starting_position(qt_app, monkeypatch):
    """Controller wraps probe_all and formats notations correctly."""
    if DEFAULT_BOOK is None:
        pytest.skip("DEFAULT_BOOK is not loaded in this environment")
    from draughts.app.controller import GameController

    monkeypatch.setattr(GameController, "_start_computer_turn", lambda self: None)
    c = GameController()

    moves = c.get_book_moves()
    assert len(moves) >= 1
    for notation, weight, (from_sq, to_sq) in moves:
        assert isinstance(notation, str) and notation
        assert isinstance(weight, int) and weight > 0
        assert len(from_sq) == 2 and len(to_sq) == 2


def test_get_book_moves_disabled_returns_empty(qt_app, monkeypatch):
    """Disabling the book in settings must short-circuit to []."""
    from draughts.app.controller import GameController

    monkeypatch.setattr(GameController, "_start_computer_turn", lambda self: None)
    c = GameController()
    c.settings.use_opening_book = False
    assert c.get_book_moves() == []


def test_get_book_moves_unknown_position_returns_empty(qt_app, monkeypatch):
    """A random post-opening position is almost certainly not in the book."""
    if DEFAULT_BOOK is None:
        pytest.skip("DEFAULT_BOOK is not loaded in this environment")
    from draughts.app.controller import GameController

    monkeypatch.setattr(GameController, "_start_computer_turn", lambda self: None)
    c = GameController()
    # Clear the board — empty board is never in a standard opening book.
    c.board.grid[:] = 0
    c.board.grid[0, 1] = 1  # single black
    c.board.grid[7, 0] = -1  # single white
    assert c.get_book_moves() == []
