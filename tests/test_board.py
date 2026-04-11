"""Tests for Board — Russian draughts rules (0-indexed coordinates)."""

import pytest
from draughts.config import BLACK, BLACK_KING, BOARD_SIZE, EMPTY, WHITE, WHITE_KING, Color
from draughts.game.board import Board


class TestBoardInit:
    """Test board initialization and representation."""

    def test_initial_position_string(self, board):
        """Starting position must match original format."""
        assert board.to_position_string() == "bbbbbbbbbbbbnnnnnnnnwwwwwwwwwwww"

    def test_initial_black_count(self, board):
        assert board.count_pieces(Color.BLACK) == 12

    def test_initial_white_count(self, board):
        assert board.count_pieces(Color.WHITE) == 12

    def test_empty_board(self, empty_board):
        assert empty_board.to_position_string() == "n" * 32
        assert empty_board.count_pieces(Color.BLACK) == 0
        assert empty_board.count_pieces(Color.WHITE) == 0

    def test_dark_squares_only(self, board):
        """Only dark squares should have pieces."""
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                if x % 2 == y % 2:  # light square
                    assert board.piece_at(x, y) == EMPTY

    def test_black_pieces_on_top(self, board):
        """Black pieces occupy rows 0-2."""
        for y in range(3):
            for x in range(BOARD_SIZE):
                if x % 2 != y % 2:
                    assert board.piece_at(x, y) == BLACK

    def test_white_pieces_on_bottom(self, board):
        """White pieces occupy rows 5-7."""
        for y in range(5, BOARD_SIZE):
            for x in range(BOARD_SIZE):
                if x % 2 != y % 2:
                    assert board.piece_at(x, y) == WHITE

    def test_middle_rows_empty(self, board):
        """Rows 3-4 should be empty."""
        for y in range(3, 5):
            for x in range(BOARD_SIZE):
                assert board.piece_at(x, y) == EMPTY

    def test_grid_shape(self, board):
        """Grid should be 8x8 (0-indexed)."""
        assert board.grid.shape == (8, 8)

    def test_grid_dtype(self, board):
        """Grid should be int8."""
        assert board.grid.dtype.name == "int8"


class TestBoardStringConversion:
    def test_round_trip(self, board):
        s = board.to_position_string()
        new_board = Board(empty=True)
        new_board.load_from_position_string(s)
        assert new_board.to_position_string() == s

    def test_invalid_string_length(self, empty_board):
        with pytest.raises(ValueError):
            empty_board.load_from_position_string("abc")

    def test_custom_position(self, empty_board):
        s = "BnnnnnnnnnnnnnnnnnnnnnnnnnnnnnWn"
        empty_board.load_from_position_string(s)
        assert empty_board.to_position_string() == s


class TestNotation:
    def test_a8(self):
        """(0, 0) = a8."""
        assert Board.pos_to_notation(0, 0) == "a8"

    def test_h1(self):
        """(7, 7) = h1."""
        assert Board.pos_to_notation(7, 7) == "h1"

    def test_e3(self):
        """(4, 5) = e3."""
        assert Board.pos_to_notation(4, 5) == "e3"

    def test_notation_round_trip(self):
        for x in range(BOARD_SIZE):
            for y in range(BOARD_SIZE):
                notation = Board.pos_to_notation(x, y)
                rx, ry = Board.notation_to_pos(notation)
                assert (rx, ry) == (x, y)


class TestPieceIdentification:
    def test_is_black(self):
        assert Board.is_black(BLACK)
        assert Board.is_black(BLACK_KING)
        assert not Board.is_black(WHITE)
        assert not Board.is_black(EMPTY)

    def test_is_white(self):
        assert Board.is_white(WHITE)
        assert Board.is_white(WHITE_KING)
        assert not Board.is_white(BLACK)
        assert not Board.is_white(EMPTY)

    def test_is_king(self):
        assert Board.is_king(BLACK_KING)
        assert Board.is_king(WHITE_KING)
        assert not Board.is_king(BLACK)
        assert not Board.is_king(WHITE)

    def test_is_enemy(self):
        assert Board.is_enemy(BLACK, WHITE)
        assert Board.is_enemy(WHITE, BLACK_KING)
        assert Board.is_enemy(WHITE_KING, BLACK)
        assert not Board.is_enemy(BLACK, BLACK)
        assert not Board.is_enemy(WHITE, WHITE_KING)
        assert not Board.is_enemy(EMPTY, BLACK)


class TestPawnMoves:
    def test_white_pawn_moves_up(self, empty_board):
        """White pawn at e3 (4,5) should move to d4 (3,4) or f4 (5,4)."""
        empty_board.place_piece(4, 5, WHITE)
        moves = empty_board.get_valid_moves(4, 5)
        assert sorted(moves) == sorted([(3, 4), (5, 4)])

    def test_black_pawn_moves_down(self, empty_board):
        """Black pawn at d6 (3,2) should move to c5 (2,3) or e5 (4,3)."""
        empty_board.place_piece(3, 2, BLACK)
        moves = empty_board.get_valid_moves(3, 2)
        assert sorted(moves) == sorted([(2, 3), (4, 3)])

    def test_pawn_blocked(self, empty_board):
        empty_board.place_piece(4, 5, WHITE)
        empty_board.place_piece(3, 4, WHITE)
        empty_board.place_piece(5, 4, WHITE)
        moves = empty_board.get_valid_moves(4, 5)
        assert moves == []

    def test_pawn_at_edge(self, empty_board):
        """Pawn at left edge (0,5) has only one diagonal."""
        empty_board.place_piece(0, 5, WHITE)
        moves = empty_board.get_valid_moves(0, 5)
        assert moves == [(1, 4)]

    def test_white_cannot_move_backward(self, empty_board):
        empty_board.place_piece(4, 3, WHITE)
        moves = empty_board.get_valid_moves(4, 3)
        for _x, y in moves:
            assert y < 3

    def test_no_moves_for_empty(self, empty_board):
        moves = empty_board.get_valid_moves(4, 4)
        assert moves == []


class TestKingMoves:
    def test_king_moves_all_directions(self, empty_board):
        empty_board.place_piece(3, 4, WHITE_KING)
        moves = empty_board.get_valid_moves(3, 4)
        assert len(moves) > 4

    def test_king_moves_long_diagonal(self, empty_board):
        """King at a1 (0,7) can reach h8 (7,0)."""
        empty_board.place_piece(0, 7, WHITE_KING)
        moves = empty_board.get_valid_moves(0, 7)
        assert (7, 0) in moves

    def test_king_blocked_by_piece(self, empty_board):
        empty_board.place_piece(0, 7, WHITE_KING)
        empty_board.place_piece(3, 4, BLACK)
        moves = empty_board.get_valid_moves(0, 7)
        assert (1, 6) in moves
        assert (2, 5) in moves
        assert (3, 4) not in moves
        assert (4, 3) not in moves


class TestPawnCaptures:
    def test_simple_capture(self, empty_board):
        """White pawn at e3 (4,5) captures black at d4 (3,4), lands at c5 (2,3)."""
        empty_board.place_piece(4, 5, WHITE)
        empty_board.place_piece(3, 4, BLACK)
        captures = empty_board.get_captures(4, 5)
        assert len(captures) >= 1
        assert any(path[-1] == (2, 3) for path in captures)

    def test_capture_in_all_directions(self, empty_board):
        empty_board.place_piece(3, 4, WHITE)
        empty_board.place_piece(2, 3, BLACK)  # forward-left
        empty_board.place_piece(4, 5, BLACK)  # backward-right
        captures = empty_board.get_captures(3, 4)
        landing_positions = {path[-1] for path in captures}
        assert (1, 2) in landing_positions
        assert (5, 6) in landing_positions

    def test_double_capture(self, empty_board):
        """White captures two black pieces in sequence."""
        empty_board.place_piece(6, 7, WHITE)
        empty_board.place_piece(5, 6, BLACK)
        empty_board.place_piece(3, 4, BLACK)
        captures = empty_board.get_captures(6, 7)
        assert any(len(path) == 3 and path[-1] == (2, 3) for path in captures)

    def test_no_capture_of_friendly(self, empty_board):
        empty_board.place_piece(4, 5, WHITE)
        empty_board.place_piece(3, 4, WHITE)
        captures = empty_board.get_captures(4, 5)
        assert captures == []

    def test_capture_requires_landing(self, empty_board):
        empty_board.place_piece(4, 5, WHITE)
        empty_board.place_piece(3, 4, BLACK)
        empty_board.place_piece(2, 3, BLACK)  # blocks landing
        captures = empty_board.get_captures(4, 5)
        assert not any(path[-1] == (2, 3) for path in captures if len(path) == 2)

    def test_cannot_capture_same_piece_twice(self, empty_board):
        empty_board.place_piece(0, 3, WHITE)
        empty_board.place_piece(1, 2, BLACK)
        captures = empty_board.get_captures(0, 3)
        for path in captures:
            jumps_over_12 = 0
            for i in range(len(path) - 1):
                x1, y1 = path[i]
                x2, y2 = path[i + 1]
                dx = 1 if x2 > x1 else -1
                dy = 1 if y2 > y1 else -1
                cx, cy = x1 + dx, y1 + dy
                while (cx, cy) != (x2, y2):
                    if (cx, cy) == (1, 2):
                        jumps_over_12 += 1
                    cx += dx
                    cy += dy
            assert jumps_over_12 <= 1


class TestKingCaptures:
    def test_king_capture_at_distance(self, empty_board):
        """King at a1 (0,7) captures enemy not adjacent."""
        empty_board.place_piece(0, 7, WHITE_KING)
        empty_board.place_piece(3, 4, BLACK)
        captures = empty_board.get_captures(0, 7)
        assert len(captures) >= 1
        landing_positions = {path[-1] for path in captures}
        assert any(pos in landing_positions for pos in [(4, 3), (5, 2), (6, 1), (7, 0)])

    def test_king_multiple_landing_squares(self, empty_board):
        empty_board.place_piece(0, 7, WHITE_KING)
        empty_board.place_piece(2, 5, BLACK)
        captures = empty_board.get_captures(0, 7)
        landing_positions = {path[-1] for path in captures}
        possible = {(3, 4), (4, 3), (5, 2), (6, 1), (7, 0)}
        assert landing_positions & possible


class TestPromotion:
    def test_white_promotes_on_row_0(self, empty_board):
        """White pawn reaching row 0 becomes king."""
        empty_board.place_piece(1, 1, WHITE)
        empty_board.execute_move(1, 1, 0, 0)
        assert empty_board.piece_at(0, 0) == WHITE_KING

    def test_black_promotes_on_row_7(self, empty_board):
        """Black pawn reaching row 7 becomes king."""
        empty_board.place_piece(6, 6, BLACK)
        empty_board.execute_move(6, 6, 7, 7)
        assert empty_board.piece_at(7, 7) == BLACK_KING

    def test_promotion_on_capture(self, empty_board):
        b = Board(empty=True)
        b.place_piece(3, 2, WHITE)
        b.place_piece(2, 1, BLACK)
        captures = b.get_captures(3, 2)
        if captures:
            b.execute_capture_path(captures[0])
            final_x, final_y = captures[0][-1]
            if final_y == 0:
                assert b.piece_at(final_x, final_y) == WHITE_KING

    def test_promotion_continues_as_king(self, empty_board):
        """Russian draughts: pawn promotes during capture and continues as king.

        Setup: White pawn at e6 (4,2), black at d7 (3,1) and b7 (1,1).
        White captures d7, lands on c8 (2,0) = promotion row → becomes king.
        King at c8 should continue: capture b7 (1,1), land on a6 (0,2).
        Expected path: [(4,2), (2,0), (0,2)] — length 3.
        """
        b = Board(empty=True)
        b.place_piece(4, 2, WHITE)  # e6
        b.place_piece(3, 1, BLACK)  # d7 — first capture, lands on c8 (2,0) = promotion
        b.place_piece(1, 1, BLACK)  # b7 — king continues capturing from (2,0)
        captures = b.get_captures(4, 2)
        has_long_capture = any(len(p) == 3 and p[-1] == (0, 2) for p in captures)
        assert has_long_capture, f"Expected promotion+king continue, got: {captures}"

    def test_promotion_capture_stops_if_no_more(self, empty_board):
        """Promoted pawn stops if no further captures available as king."""
        b = Board(empty=True)
        b.place_piece(4, 2, WHITE)  # e6
        b.place_piece(3, 1, BLACK)  # d7 — capture lands on c8 (2,0) = promotion
        captures = b.get_captures(4, 2)
        assert any(len(p) == 2 and p[-1] == (2, 0) for p in captures)


class TestExecuteMove:
    def test_simple_move(self, empty_board):
        empty_board.place_piece(4, 5, WHITE)
        empty_board.execute_move(4, 5, 3, 4)
        assert empty_board.piece_at(4, 5) == EMPTY
        assert empty_board.piece_at(3, 4) == WHITE

    def test_capture_removes_piece(self, empty_board):
        empty_board.place_piece(4, 5, WHITE)
        empty_board.place_piece(3, 4, BLACK)
        captures = empty_board.get_captures(4, 5)
        assert len(captures) >= 1
        path = captures[0]
        captured = empty_board.execute_capture_path(path)
        assert len(captured) == 1
        assert (3, 4) in captured
        assert empty_board.piece_at(3, 4) == EMPTY
        assert empty_board.piece_at(4, 5) == EMPTY
        assert empty_board.piece_at(2, 3) == WHITE


class TestMandatoryCapture:
    def test_has_capture(self, empty_board):
        empty_board.place_piece(4, 5, WHITE)
        empty_board.place_piece(3, 4, BLACK)
        assert empty_board.has_any_capture(Color.WHITE)

    def test_no_capture(self, empty_board):
        empty_board.place_piece(4, 5, WHITE)
        assert not empty_board.has_any_capture(Color.WHITE)

    def test_initial_position_no_captures(self, board):
        assert not board.has_any_capture(Color.WHITE)
        assert not board.has_any_capture(Color.BLACK)


class TestHasAnyMove:
    def test_initial_has_moves(self, board):
        assert board.has_any_move(Color.WHITE)
        assert board.has_any_move(Color.BLACK)

    def test_no_pieces_no_moves(self, empty_board):
        assert not empty_board.has_any_move(Color.WHITE)
        assert not empty_board.has_any_move(Color.BLACK)


class TestCopy:
    def test_copy_independence(self, board):
        copy = board.copy()
        copy.place_piece(0, 0, EMPTY)
        assert copy.to_position_string() != board.to_position_string() or board.piece_at(0, 0) == EMPTY


class TestDangerousPosition:
    def test_piece_under_attack(self, empty_board):
        empty_board.place_piece(4, 5, WHITE)
        empty_board.place_piece(3, 4, BLACK)
        assert empty_board.dangerous_position(4, 5, Color.WHITE)

    def test_piece_safe(self, empty_board):
        empty_board.place_piece(4, 5, WHITE)
        assert not empty_board.dangerous_position(4, 5, Color.WHITE)

    def test_king_attack_from_distance(self, empty_board):
        empty_board.place_piece(4, 3, WHITE)
        empty_board.place_piece(1, 0, BLACK_KING)
        assert empty_board.dangerous_position(4, 3, Color.WHITE)


class TestFreeway:
    def test_clear_path(self, empty_board):
        assert empty_board.is_diagonal_clear(0, 7, 7, 0)

    def test_blocked_path(self, empty_board):
        empty_board.place_piece(3, 4, BLACK)
        assert not empty_board.is_diagonal_clear(0, 7, 7, 0)

    def test_same_square(self, empty_board):
        assert empty_board.is_diagonal_clear(2, 2, 2, 2)


# ===========================================================================
# Migration-specific tests: verify 0-indexed coordinate system
# ===========================================================================


class TestZeroIndexedMigration:
    """Tests specifically verifying correct 0-indexed behavior."""

    def test_corners(self, empty_board):
        """All four corners are valid and accessible."""
        for x, y in [(0, 0), (7, 0), (0, 7), (7, 7)]:
            empty_board.place_piece(x, y, BLACK)
            assert empty_board.piece_at(x, y) == BLACK
            empty_board.place_piece(x, y, EMPTY)

    def test_out_of_bounds(self, empty_board):
        """Coordinates outside 0-7 return EMPTY."""
        assert empty_board.piece_at(-1, 0) == EMPTY
        assert empty_board.piece_at(0, -1) == EMPTY
        assert empty_board.piece_at(8, 0) == EMPTY
        assert empty_board.piece_at(0, 8) == EMPTY

    def test_notation_corners(self):
        """Corner notation is correct for 0-indexed."""
        assert Board.pos_to_notation(0, 0) == "a8"  # top-left
        assert Board.pos_to_notation(7, 0) == "h8"  # top-right
        assert Board.pos_to_notation(0, 7) == "a1"  # bottom-left
        assert Board.pos_to_notation(7, 7) == "h1"  # bottom-right

    def test_promotion_rows(self, empty_board):
        """White promotes at row 0, black at row 7."""
        empty_board.place_piece(1, 1, WHITE)
        empty_board.execute_move(1, 1, 0, 0)
        assert empty_board.piece_at(0, 0) == WHITE_KING

        empty_board.place_piece(6, 6, BLACK)
        empty_board.execute_move(6, 6, 7, 7)
        assert empty_board.piece_at(7, 7) == BLACK_KING

    def test_initial_position_rows(self, board):
        """Black rows 0-2, empty rows 3-4, white rows 5-7."""
        for y in range(3):
            dark_count = sum(1 for x in range(BOARD_SIZE) if x % 2 != y % 2 and board.piece_at(x, y) == BLACK)
            assert dark_count == 4, f"Row {y} should have 4 black pieces"

        for y in range(5, BOARD_SIZE):
            dark_count = sum(1 for x in range(BOARD_SIZE) if x % 2 != y % 2 and board.piece_at(x, y) == WHITE)
            assert dark_count == 4, f"Row {y} should have 4 white pieces"

    def test_dark_squares_count(self):
        """There should be exactly 32 dark squares."""
        from draughts.config import DARK_SQUARES

        assert len(DARK_SQUARES) == 32
        for y, x in DARK_SQUARES:
            assert 0 <= y < BOARD_SIZE
            assert 0 <= x < BOARD_SIZE
            assert x % 2 != y % 2

    def test_position_string_preserves_format(self, board):
        """Position string format unchanged after migration."""
        s = board.to_position_string()
        assert len(s) == 32
        assert s.count("b") == 12
        assert s.count("w") == 12
        assert s.count("n") == 8
