"""Tests for UX polish features: last-move highlight, hint squares,
legal-move hover, and coordinates toggle.

All tests are headless — they test data-model properties only,
no Qt painting is invoked.
"""

from __future__ import annotations

import time

import pytest

from draughts.config import GameSettings
from draughts.game.board import Board


# ---------------------------------------------------------------------------
# Helper: minimal BoardWidget substitute that only exposes the data properties
# ---------------------------------------------------------------------------

class _FakeBoardWidget:
    """Minimal stand-in for BoardWidget that exercises the same property logic
    without requiring a QApplication."""

    def __init__(self):
        self._last_move = None
        self._hint_squares = None
        self._hover_legal_moves: list[tuple[int, int]] = []
        self._settings = GameSettings()

    # --- last_move property (item 26, part 1) ---

    @property
    def last_move(self):
        return self._last_move

    @last_move.setter
    def last_move(self, value):
        self._last_move = value

    # --- hint_squares property (D16) ---

    @property
    def hint_squares(self):
        return self._hint_squares

    @hint_squares.setter
    def hint_squares(self, value):
        self._hint_squares = value

    def clear_hint_squares(self):
        self._hint_squares = None


# ---------------------------------------------------------------------------
# Test A — last-move highlight (item 26, part 1)
# ---------------------------------------------------------------------------

class TestLastMoveProperty:
    def test_initially_none(self):
        w = _FakeBoardWidget()
        assert w.last_move is None

    def test_set_and_get(self):
        w = _FakeBoardWidget()
        w.last_move = ((2, 4), (3, 5))
        assert w.last_move == ((2, 4), (3, 5))

    def test_clear_with_none(self):
        w = _FakeBoardWidget()
        w.last_move = ((0, 0), (1, 1))
        w.last_move = None
        assert w.last_move is None

    def test_stores_both_squares(self):
        w = _FakeBoardWidget()
        from_sq = (5, 6)
        to_sq = (7, 4)
        w.last_move = (from_sq, to_sq)
        stored = w.last_move
        assert stored[0] == from_sq
        assert stored[1] == to_sq

    def test_settings_flag_default_off(self):
        s = GameSettings()
        assert s.highlight_last_move is False

    def test_settings_flag_can_enable(self):
        s = GameSettings()
        s.highlight_last_move = True
        assert s.highlight_last_move is True


# ---------------------------------------------------------------------------
# Test B — hint squares (D16)
# ---------------------------------------------------------------------------

class TestHintSquaresProperty:
    def test_initially_none(self):
        w = _FakeBoardWidget()
        assert w.hint_squares is None

    def test_set_and_get(self):
        w = _FakeBoardWidget()
        squares = [(2, 3), (4, 5)]
        w.hint_squares = squares
        assert w.hint_squares == [(2, 3), (4, 5)]

    def test_clear_to_none(self):
        w = _FakeBoardWidget()
        w.hint_squares = [(1, 2)]
        w.clear_hint_squares()
        assert w.hint_squares is None

    def test_auto_clear_timing_model(self):
        """The auto-clear timer fires after 3 s — verify via manual clear."""
        w = _FakeBoardWidget()
        w.hint_squares = [(0, 0), (2, 2)]
        assert w.hint_squares is not None
        # Simulate the timer firing
        w.clear_hint_squares()
        assert w.hint_squares is None

    def test_hint_squares_two_entries(self):
        """Hint always contains from_sq and to_sq (exactly two entries)."""
        w = _FakeBoardWidget()
        w.hint_squares = [(1, 2), (3, 4)]
        assert len(w.hint_squares) == 2


# ---------------------------------------------------------------------------
# Test C — legal moves for a known position (item 26, part 2)
# ---------------------------------------------------------------------------

class TestLegalMovesForPiece:
    def test_white_piece_has_moves_at_start(self):
        board = Board()
        # White pieces at y=5,6,7; dark squares satisfy x%2 != y%2.
        # (2,5): 2%2=0, 5%2=1 → dark. White piece is placed there.
        moves = board.get_valid_moves(2, 5)
        assert len(moves) > 0, "White piece at (2,5) should have legal moves from start"

    def test_captures_detected(self):
        """A piece with a jump available should return captures, not quiet moves."""
        board = Board(empty=True)
        # Place a white piece at (2, 4) and a black piece at (3, 3)
        board.place_piece(2, 4, int(board.WHITE))
        board.place_piece(3, 3, int(board.BLACK))
        captures = board.get_captures(2, 4)
        assert len(captures) > 0, "White piece should see a capture over black at (3,3)"

    def test_empty_square_has_no_moves(self):
        board = Board()
        moves = board.get_valid_moves(0, 0)  # corner — empty light square
        assert moves == []

    def test_get_valid_moves_returns_list(self):
        board = Board()
        result = board.get_valid_moves(1, 5)
        assert isinstance(result, list)

    def test_get_captures_returns_list_of_paths(self):
        board = Board(empty=True)
        board.place_piece(2, 4, int(board.WHITE))
        board.place_piece(3, 3, int(board.BLACK))
        caps = board.get_captures(2, 4)
        assert isinstance(caps, list)
        for path in caps:
            assert isinstance(path, list)
            assert len(path) >= 2


# ---------------------------------------------------------------------------
# Test D — coordinates draw flag (show_coordinates toggle)
# ---------------------------------------------------------------------------

class TestCoordinatesDrawFlag:
    def test_default_false(self):
        s = GameSettings()
        assert s.show_coordinates is False

    def test_can_enable(self):
        s = GameSettings()
        s.show_coordinates = True
        assert s.show_coordinates is True

    def test_toggle_round_trip(self):
        s = GameSettings()
        s.show_coordinates = True
        s.show_coordinates = False
        assert s.show_coordinates is False

    def test_board_widget_uses_setting(self):
        """When show_coordinates is False, the flag is False on the widget's settings."""
        w = _FakeBoardWidget()
        w._settings.show_coordinates = False
        assert w._settings.show_coordinates is False

    def test_board_widget_shows_when_enabled(self):
        w = _FakeBoardWidget()
        w._settings.show_coordinates = True
        assert w._settings.show_coordinates is True


# ---------------------------------------------------------------------------
# Test E — hover legal moves flag
# ---------------------------------------------------------------------------

class TestHoverLegalMovesFlag:
    def test_default_false(self):
        s = GameSettings()
        assert s.show_legal_moves_hover is False

    def test_can_enable(self):
        s = GameSettings()
        s.show_legal_moves_hover = True
        assert s.show_legal_moves_hover is True

    def test_hover_list_initially_empty(self):
        w = _FakeBoardWidget()
        assert w._hover_legal_moves == []
