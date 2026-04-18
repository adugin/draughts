"""Board state round-trip invariants — audit gap #4.

Auditor flagged: `Board.execute_move` and `execute_capture_path` have no
inverse operation, so any future AI-side undo in search depends on
position_string serialization round-tripping perfectly. If
`to_position_string` and `load_from_position_string` ever drop a piece
kind, the search engine silently starts producing wrong moves.

This file guards that invariant with exhaustive round-trip tests over
every piece kind and position.
"""

from __future__ import annotations

import numpy as np
import pytest

from draughts.config import BLACK, BLACK_KING, WHITE, WHITE_KING
from draughts.game.ai import _generate_all_moves
from draughts.game.ai.moves import _apply_move
from draughts.game.board import Board
from draughts.config import Color


def test_empty_board_roundtrip():
    b = Board(empty=True)
    s = b.to_position_string()
    b2 = Board(empty=True)
    b2.load_from_position_string(s)
    assert np.array_equal(b.grid, b2.grid)


def test_starting_position_roundtrip():
    b = Board()
    s = b.to_position_string()
    b2 = Board()
    b2.load_from_position_string(s)
    assert np.array_equal(b.grid, b2.grid)


def test_all_four_piece_kinds_roundtrip():
    """Place one of each piece kind; round-trip; identical grid."""
    b = Board(empty=True)
    b.grid[1, 0] = BLACK        # a7
    b.grid[3, 2] = BLACK_KING   # c5
    b.grid[5, 4] = WHITE        # e3
    b.grid[7, 6] = WHITE_KING   # g1
    s = b.to_position_string()
    b2 = Board(empty=True)
    b2.load_from_position_string(s)
    assert np.array_equal(b.grid, b2.grid)


@pytest.mark.parametrize("piece", [BLACK, BLACK_KING, WHITE, WHITE_KING])
def test_single_piece_at_every_dark_square_roundtrips(piece):
    """Every dark square × every piece kind → bit-identical round-trip."""
    for y in range(8):
        for x in range(8):
            if (x % 2) == (y % 2):
                continue  # light squares
            b = Board(empty=True)
            b.grid[y, x] = piece
            s = b.to_position_string()
            b2 = Board(empty=True)
            b2.load_from_position_string(s)
            assert np.array_equal(b.grid, b2.grid), (
                f"Roundtrip failed for piece {piece} at ({x},{y})"
            )


def test_execute_move_then_serialize_is_stable():
    """After a move, positon-string serialize → load → compare grids."""
    b = Board()
    b.execute_move(6, 5, 7, 4)  # 24-20
    s = b.to_position_string()
    b2 = Board(empty=True)
    b2.load_from_position_string(s)
    assert np.array_equal(b.grid, b2.grid)


def test_capture_preserves_only_destination_piece_type():
    """A black pawn capturing a white pawn — after, the destination
    has black pawn, source and captured squares empty.
    """
    b = Board(empty=True)
    b.grid[2, 1] = BLACK         # b6 black pawn
    b.grid[3, 2] = WHITE         # c5 white pawn
    b.execute_capture_path([(1, 2), (3, 4)])  # b6 captures c5, lands d4
    assert int(b.grid[4, 3]) == BLACK    # d4 has black pawn
    assert int(b.grid[2, 1]) == 0        # b6 empty
    assert int(b.grid[3, 2]) == 0        # c5 empty


def test_every_legal_move_produces_serialisable_state():
    """For every legal move from starting position, the resulting
    board must round-trip through position-string without loss.
    """
    b = Board()
    for kind, path in _generate_all_moves(b, Color.WHITE):
        child = _apply_move(b, kind, path)
        s = child.to_position_string()
        child2 = Board(empty=True)
        child2.load_from_position_string(s)
        assert np.array_equal(child.grid, child2.grid), (
            f"Move {kind} {path} produces a non-roundtripping board"
        )


def test_position_string_length_is_32():
    """32 dark squares on 8x8 → position string is always 32 chars."""
    assert len(Board().to_position_string()) == 32
    assert len(Board(empty=True).to_position_string()) == 32


def test_position_string_uses_only_valid_chars():
    """Guard against accidental encoding drift. n/b/B/w/W only."""
    valid = set("nbBwW")
    b = Board()
    assert set(b.to_position_string()) <= valid


def test_load_rejects_wrong_length():
    """Undersized or oversized position string must not silently succeed."""
    b = Board(empty=True)
    with pytest.raises((ValueError, IndexError, KeyError)):
        b.load_from_position_string("n" * 31)
    with pytest.raises((ValueError, IndexError, KeyError)):
        b.load_from_position_string("n" * 33)


def test_load_rejects_unknown_char():
    b = Board(empty=True)
    with pytest.raises((ValueError, KeyError)):
        b.load_from_position_string("x" * 32)
