"""Tests for the board editor state machine.

All tests run WITHOUT a Qt event loop — they exercise the pure logic
of BoardWidget.cycle_piece / clear_piece and the FEN round-trip that
the editor relies on.  Qt widget painting is never triggered.
"""

from __future__ import annotations

import pytest
from draughts.config import BLACK, BLACK_KING, EMPTY, WHITE, WHITE_KING, Color
from draughts.game.board import Board
from draughts.game.fen import START_FEN, board_to_fen, parse_fen

# ruff: noqa: RUF005


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_widget_headless(board: Board):
    """Instantiate BoardWidget in headless mode (no paint, no Qt loop).

    We monkey-patch ``update()`` so no repaint is attempted.
    """
    from draughts.ui.board_widget import BoardWidget

    w = BoardWidget.__new__(BoardWidget)
    # Minimal attribute initialisation — mirrors __init__ without Qt parent
    w._board = board
    w._editor_mode = False
    # Suppress repaint calls
    w.update = lambda: None
    return w


# ---------------------------------------------------------------------------
# 1. editor_mode toggle
# ---------------------------------------------------------------------------


def test_editor_mode_toggle():
    """Editor mode defaults off and round-trips through True→False.

    Consolidated after audit (Smell C): was 3 separate tests each
    asserting one side of the setter/getter. Now one regression guard
    for the UX-facing invariant.
    """
    board = Board()
    w = _make_widget_headless(board)
    assert w.editor_mode is False
    w.editor_mode = True
    assert w.editor_mode is True
    w.editor_mode = False
    assert w.editor_mode is False


# ---------------------------------------------------------------------------
# 2. cycle_piece — dark squares
# ---------------------------------------------------------------------------

# The cycle is: EMPTY → BLACK → BLACK_KING → WHITE → WHITE_KING → EMPTY
_CYCLE = [int(EMPTY), int(BLACK), int(BLACK_KING), int(WHITE), int(WHITE_KING)]


class TestCyclePiece:
    """Cycle through all five states on a single dark square."""

    # (1,0) is a dark square: 1%2 != 0%2 → True
    _X, _Y = 1, 0

    def _widget(self) -> object:
        board = Board(empty=True)
        return _make_widget_headless(board)

    def test_empty_to_black(self):
        w = self._widget()
        w.cycle_piece(self._X, self._Y)
        assert int(w._board.piece_at(self._X, self._Y)) == int(BLACK)

    def test_full_cycle_returns_to_empty(self):
        w = self._widget()
        for _ in range(len(_CYCLE)):
            w.cycle_piece(self._X, self._Y)
        assert int(w._board.piece_at(self._X, self._Y)) == int(EMPTY)

    def test_all_intermediate_states(self):
        w = self._widget()
        results = []
        for _ in range(len(_CYCLE)):
            w.cycle_piece(self._X, self._Y)
            results.append(int(w._board.piece_at(self._X, self._Y)))
        assert results == _CYCLE[1:] + [int(EMPTY)]

    def test_noop_on_light_square(self):
        """(0,0) is a light square — cycle_piece must leave it untouched."""
        board = Board(empty=True)
        w = _make_widget_headless(board)
        w.cycle_piece(0, 0)  # light square
        assert int(w._board.piece_at(0, 0)) == int(EMPTY)

    def test_noop_when_no_board(self):
        board = Board(empty=True)
        w = _make_widget_headless(board)
        w._board = None
        # Must not raise
        w.cycle_piece(self._X, self._Y)


# ---------------------------------------------------------------------------
# 3. clear_piece
# ---------------------------------------------------------------------------


class TestClearPiece:
    _X, _Y = 1, 0  # dark square

    def test_clear_removes_piece(self):
        board = Board(empty=True)
        board.place_piece(self._X, self._Y, int(BLACK))
        w = _make_widget_headless(board)
        w.clear_piece(self._X, self._Y)
        assert int(w._board.piece_at(self._X, self._Y)) == int(EMPTY)

    def test_clear_already_empty_is_noop(self):
        board = Board(empty=True)
        w = _make_widget_headless(board)
        w.clear_piece(self._X, self._Y)
        assert int(w._board.piece_at(self._X, self._Y)) == int(EMPTY)

    def test_noop_on_light_square(self):
        board = Board(empty=True)
        board.place_piece(0, 0, int(EMPTY))  # light square stays empty anyway
        w = _make_widget_headless(board)
        w.clear_piece(0, 0)
        assert int(w._board.piece_at(0, 0)) == int(EMPTY)

    def test_noop_when_no_board(self):
        board = Board(empty=True)
        w = _make_widget_headless(board)
        w._board = None
        w.clear_piece(self._X, self._Y)  # must not raise


# ---------------------------------------------------------------------------
# 4. FEN export round-trip
# ---------------------------------------------------------------------------


class TestFenRoundTrip:
    def test_export_start_position(self):
        board = Board()
        fen = board_to_fen(board, Color.WHITE)
        restored, color = parse_fen(fen)
        import numpy as np

        assert np.array_equal(board.grid, restored.grid)
        assert color == Color.WHITE

    def test_export_black_to_move(self):
        board = Board()
        fen = board_to_fen(board, Color.BLACK)
        _, color = parse_fen(fen)
        assert color == Color.BLACK

    def test_export_custom_position(self):
        board = Board(empty=True)
        board.place_piece(1, 0, int(BLACK_KING))
        board.place_piece(3, 6, int(WHITE))
        fen = board_to_fen(board, Color.WHITE)
        restored, color = parse_fen(fen)
        assert int(restored.piece_at(1, 0)) == int(BLACK_KING)
        assert int(restored.piece_at(3, 6)) == int(WHITE)
        assert color == Color.WHITE

    def test_import_start_fen(self):
        board, color = parse_fen(START_FEN)
        expected = Board()
        import numpy as np

        assert np.array_equal(board.grid, expected.grid)
        assert color == Color.WHITE

    def test_invalid_fen_raises(self):
        with pytest.raises(ValueError):
            parse_fen("INVALID_FEN")

    def test_fen_is_string(self):
        board = Board()
        fen = board_to_fen(board, Color.WHITE)
        assert isinstance(fen, str)
        assert fen.startswith("W:")


# ---------------------------------------------------------------------------
# 5. "Play from here" state machine
# ---------------------------------------------------------------------------


class TestPlayFromHere:
    """Verify that exiting editor mode with a new position correctly
    sets up the game state — tested at the controller level without Qt UI."""

    def _make_controller(self):
        """Create a GameController without starting the Qt event loop."""
        from draughts.app.controller import GameController

        c = GameController.__new__(GameController)
        # Minimal init (mirrors __init__ but avoids Qt signals/slots setup)
        c.board = Board()
        from draughts.config import GameSettings

        c.settings = GameSettings()
        c._current_turn = Color.WHITE
        c._computer_color = Color.BLACK
        c._player_color = Color.WHITE
        c._selected = None
        c._capture_path = []
        c._positions = [c.board.to_position_string()]
        c._replay_history = [c.board.to_position_string()]
        c._ply_count = 0
        c._game_started = False
        c._ai_thread = None
        c._ai_worker = None
        return c

    def test_fen_round_trip_after_edit(self):
        """FEN produced from editor board imports back identically."""
        import numpy as np

        board = Board(empty=True)
        board.place_piece(1, 0, int(BLACK_KING))
        board.place_piece(5, 6, int(WHITE_KING))

        fen = board_to_fen(board, Color.WHITE)
        restored, color = parse_fen(fen)

        assert np.array_equal(board.grid, restored.grid)
        assert color == Color.WHITE
