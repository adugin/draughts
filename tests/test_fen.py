"""Tests for Russian-draughts FEN parse/emit round-trips.

Covers:
- Standard start position FEN
- Custom positions (kings, partial board)
- board_to_fen → parse_fen → board_to_fen round-trips
- Side-to-move encoding
- Error handling for malformed FEN
"""

from __future__ import annotations

import pytest
from draughts.config import BLACK, BLACK_KING, WHITE, WHITE_KING, Color
from draughts.game.board import Board
from draughts.game.fen import START_FEN, board_to_fen, parse_fen

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _board_from_squares(
    white_men: list[int],
    white_kings: list[int],
    black_men: list[int],
    black_kings: list[int],
) -> Board:
    """Build a Board from lists of PDN square numbers for each piece type."""
    from draughts.game.pdn import square_to_xy

    board = Board(empty=True)
    for sq in white_men:
        x, y = square_to_xy(sq)
        board.place_piece(x, y, WHITE)
    for sq in white_kings:
        x, y = square_to_xy(sq)
        board.place_piece(x, y, WHITE_KING)
    for sq in black_men:
        x, y = square_to_xy(sq)
        board.place_piece(x, y, BLACK)
    for sq in black_kings:
        x, y = square_to_xy(sq)
        board.place_piece(x, y, BLACK_KING)
    return board


def _boards_equal(a: Board, b: Board) -> bool:
    """Check that two boards have identical grids."""
    import numpy as np

    return bool(np.array_equal(a.grid, b.grid))


# ---------------------------------------------------------------------------
# 1. Start position
# ---------------------------------------------------------------------------


class TestStartPosition:
    def test_parse_start_fen(self):
        board, _color = parse_fen(START_FEN)
        # White should have 12 men on squares 21-32
        for sq in range(21, 33):
            from draughts.game.pdn import square_to_xy

            x, y = square_to_xy(sq)
            assert board.piece_at(x, y) == WHITE, f"sq{sq} should be WHITE"

    def test_parse_start_fen_black_pieces(self):
        board, _color = parse_fen(START_FEN)
        for sq in range(1, 13):
            from draughts.game.pdn import square_to_xy

            x, y = square_to_xy(sq)
            assert board.piece_at(x, y) == BLACK, f"sq{sq} should be BLACK"

    def test_parse_start_fen_empty_middle(self):
        board, _color = parse_fen(START_FEN)
        for sq in range(13, 21):
            from draughts.game.pdn import square_to_xy

            x, y = square_to_xy(sq)
            assert board.piece_at(x, y) == 0, f"sq{sq} should be empty"

    def test_parse_start_fen_color_white(self):
        _, color = parse_fen(START_FEN)
        assert color == Color.WHITE

    def test_start_position_fen_round_trip(self):
        """Standard board → FEN → board must equal original."""
        original = Board()  # standard setup
        fen = board_to_fen(original, Color.WHITE)
        restored, color = parse_fen(fen)
        assert _boards_equal(original, restored)
        assert color == Color.WHITE

    def test_start_fen_constant_round_trip(self):
        """START_FEN parses to the same board as Board()."""
        board, _color = parse_fen(START_FEN)
        original = Board()
        assert _boards_equal(board, original)


# ---------------------------------------------------------------------------
# 2. Custom positions
# ---------------------------------------------------------------------------


class TestCustomPositions:
    def test_kings_only_position(self):
        fen = "W:WK1:BK32"
        board, color = parse_fen(fen)
        from draughts.game.pdn import square_to_xy

        x1, y1 = square_to_xy(1)
        x32, y32 = square_to_xy(32)
        assert board.piece_at(x1, y1) == WHITE_KING
        assert board.piece_at(x32, y32) == BLACK_KING
        assert color == Color.WHITE

    def test_black_to_move(self):
        fen = "B:W21:B9"
        _, color = parse_fen(fen)
        assert color == Color.BLACK

    def test_mixed_kings_and_men(self):
        fen = "W:WK1,5,15:BK28,32,9"
        board, _color = parse_fen(fen)
        from draughts.game.pdn import square_to_xy

        assert board.piece_at(*square_to_xy(1)) == WHITE_KING
        assert board.piece_at(*square_to_xy(5)) == WHITE
        assert board.piece_at(*square_to_xy(15)) == WHITE
        assert board.piece_at(*square_to_xy(28)) == BLACK_KING
        assert board.piece_at(*square_to_xy(32)) == BLACK
        assert board.piece_at(*square_to_xy(9)) == BLACK

    def test_emit_kings_first(self):
        """board_to_fen emits kings before men for each side."""
        board = _board_from_squares(
            white_men=[21, 22],
            white_kings=[1],
            black_men=[9],
            black_kings=[32],
        )
        fen = board_to_fen(board, Color.WHITE)
        w_part = fen.split(":")[1]  # e.g. 'WK1,21,22'
        b_part = fen.split(":")[2]  # e.g. 'BK32,9'
        assert w_part.startswith("WK"), f"White part should start with WK: {w_part}"
        assert b_part.startswith("BK"), f"Black part should start with BK: {b_part}"

    def test_round_trip_custom_position(self):
        board = _board_from_squares(
            white_men=[21, 23, 25],
            white_kings=[5],
            black_men=[10, 12],
            black_kings=[28],
        )
        fen = board_to_fen(board, Color.BLACK)
        restored, color = parse_fen(fen)
        assert _boards_equal(board, restored)
        assert color == Color.BLACK

    def test_round_trip_single_piece_each(self):
        board = _board_from_squares(
            white_men=[32],
            white_kings=[],
            black_men=[1],
            black_kings=[],
        )
        fen = board_to_fen(board, Color.WHITE)
        restored, _ = parse_fen(fen)
        assert _boards_equal(board, restored)

    def test_empty_side_round_trip(self):
        """One side has no pieces (terminal position)."""
        board = _board_from_squares(
            white_men=[21, 22, 23],
            white_kings=[],
            black_men=[],
            black_kings=[],
        )
        fen = board_to_fen(board, Color.WHITE)
        restored, _ = parse_fen(fen)
        assert _boards_equal(board, restored)


# ---------------------------------------------------------------------------
# 3. FEN string format checks
# ---------------------------------------------------------------------------


class TestFenFormat:
    def test_fen_starts_with_side(self):
        board = Board()
        fen = board_to_fen(board, Color.WHITE)
        assert fen.startswith("W:")

    def test_fen_starts_with_b_for_black(self):
        board = Board()
        fen = board_to_fen(board, Color.BLACK)
        assert fen.startswith("B:")

    def test_fen_three_colon_separated_parts(self):
        board = Board()
        fen = board_to_fen(board, Color.WHITE)
        parts = fen.split(":")
        assert len(parts) == 3

    def test_fen_white_part_starts_with_W(self):
        board = Board()
        fen = board_to_fen(board, Color.WHITE)
        assert fen.split(":")[1].startswith("W")

    def test_fen_black_part_starts_with_B(self):
        board = Board()
        fen = board_to_fen(board, Color.WHITE)
        assert fen.split(":")[2].startswith("B")

    def test_squares_sorted_ascending(self):
        """Square numbers in each FEN list must be sorted."""
        board = _board_from_squares(
            white_men=[32, 21, 25],
            white_kings=[],
            black_men=[12, 1, 9],
            black_kings=[],
        )
        fen = board_to_fen(board, Color.WHITE)
        w_part = fen.split(":")[1][1:]  # strip leading 'W'
        b_part = fen.split(":")[2][1:]  # strip leading 'B'
        w_squares = [int(s) for s in w_part.split(",") if s]
        b_squares = [int(s) for s in b_part.split(",") if s]
        assert w_squares == sorted(w_squares)
        assert b_squares == sorted(b_squares)


# ---------------------------------------------------------------------------
# 4. Error handling
# ---------------------------------------------------------------------------


class TestFenErrors:
    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match=r"[Ee]mpty"):
            parse_fen("")

    def test_invalid_side_raises(self):
        with pytest.raises(ValueError):
            parse_fen("X:W21:B1")

    def test_invalid_square_number_raises(self):
        with pytest.raises(ValueError):
            parse_fen("W:W33:B1")  # square 33 doesn't exist

    def test_invalid_square_token_raises(self):
        with pytest.raises(ValueError):
            parse_fen("W:Wabc:B1")  # non-numeric square


# ---------------------------------------------------------------------------
# 5. Cross-check: position_string ↔ FEN
# ---------------------------------------------------------------------------


class TestPositionStringVsFen:
    def test_start_position_string_matches_fen(self):
        """Board from position_string and Board from FEN must agree."""
        board_from_pos = Board()
        board_from_fen, _ = parse_fen(START_FEN)
        assert _boards_equal(board_from_pos, board_from_fen)

    def test_position_string_round_trip_via_fen(self):
        """pos_string → Board → FEN → Board → pos_string must match."""
        original = Board()
        fen = board_to_fen(original, Color.WHITE)
        restored, _ = parse_fen(fen)
        assert original.to_position_string() == restored.to_position_string()
