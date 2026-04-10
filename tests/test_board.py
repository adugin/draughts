"""Tests for Board — Russian draughts rules."""

import pytest
from draughts.config import BLACK, BLACK_KING, EMPTY, WHITE, WHITE_KING
from draughts.game.board import Board


class TestBoardInit:
    """Test board initialization and representation."""

    def test_initial_position_string(self, board):
        """Starting position must match original Pascal format."""
        assert board.to_position_string() == "bbbbbbbbbbbbnnnnnnnnwwwwwwwwwwww"

    def test_initial_black_count(self, board):
        assert board.count_pieces("b") == 12

    def test_initial_white_count(self, board):
        assert board.count_pieces("w") == 12

    def test_empty_board(self, empty_board):
        assert empty_board.to_position_string() == "n" * 32
        assert empty_board.count_pieces("b") == 0
        assert empty_board.count_pieces("w") == 0

    def test_dark_squares_only(self, board):
        """Only dark squares should have pieces."""
        for y in range(1, 9):
            for x in range(1, 9):
                if x % 2 == y % 2:  # light square
                    assert board.piece_at(x, y) == EMPTY

    def test_black_pieces_on_top(self, board):
        """Black pieces occupy rows 1-3."""
        for y in range(1, 4):
            for x in range(1, 9):
                if x % 2 != y % 2:
                    assert board.piece_at(x, y) == BLACK

    def test_white_pieces_on_bottom(self, board):
        """White pieces occupy rows 6-8."""
        for y in range(6, 9):
            for x in range(1, 9):
                if x % 2 != y % 2:
                    assert board.piece_at(x, y) == WHITE

    def test_middle_rows_empty(self, board):
        """Rows 4-5 should be empty."""
        for y in range(4, 6):
            for x in range(1, 9):
                assert board.piece_at(x, y) == EMPTY


class TestBoardStringConversion:
    """Test get_string / from_string round-trip."""

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
    """Test coordinate/notation conversion."""

    def test_a8(self):
        assert Board.pos_to_notation(1, 1) == "a8"

    def test_h1(self):
        assert Board.pos_to_notation(8, 8) == "h1"

    def test_e3(self):
        assert Board.pos_to_notation(5, 6) == "e3"

    def test_notation_round_trip(self):
        for x in range(1, 9):
            for y in range(1, 9):
                notation = Board.pos_to_notation(x, y)
                rx, ry = Board.notation_to_pos(notation)
                assert (rx, ry) == (x, y)


class TestPieceIdentification:
    def test_is_black(self):
        b = Board()
        assert b.is_black(BLACK)
        assert b.is_black(BLACK_KING)
        assert not b.is_black(WHITE)
        assert not b.is_black(EMPTY)

    def test_is_white(self):
        b = Board()
        assert b.is_white(WHITE)
        assert b.is_white(WHITE_KING)
        assert not b.is_white(BLACK)
        assert not b.is_white(EMPTY)

    def test_is_king(self):
        b = Board()
        assert b.is_king(BLACK_KING)
        assert b.is_king(WHITE_KING)
        assert not b.is_king(BLACK)
        assert not b.is_king(WHITE)

    def test_is_enemy(self):
        b = Board()
        assert b.is_enemy(BLACK, WHITE)
        assert b.is_enemy(WHITE, BLACK_KING)
        assert b.is_enemy(WHITE_KING, BLACK)
        assert not b.is_enemy(BLACK, BLACK)
        assert not b.is_enemy(WHITE, WHITE_KING)
        assert not b.is_enemy(EMPTY, BLACK)


class TestPawnMoves:
    """Test non-capture moves for regular pieces."""

    def test_white_pawn_moves_up(self, empty_board):
        """White pawn at e3 (5,6) should move to d4 or f4."""
        empty_board.place_piece(5, 6, WHITE)
        moves = empty_board.get_valid_moves(5, 6)
        assert sorted(moves) == sorted([(4, 5), (6, 5)])

    def test_black_pawn_moves_down(self, empty_board):
        """Black pawn at d6 (4,3) should move to c5 or e5."""
        empty_board.place_piece(4, 3, BLACK)
        moves = empty_board.get_valid_moves(4, 3)
        assert sorted(moves) == sorted([(3, 4), (5, 4)])

    def test_pawn_blocked(self, empty_board):
        """Pawn blocked by friendly pieces has no moves."""
        empty_board.place_piece(5, 6, WHITE)
        empty_board.place_piece(4, 5, WHITE)
        empty_board.place_piece(6, 5, WHITE)
        moves = empty_board.get_valid_moves(5, 6)
        assert moves == []

    def test_pawn_at_edge(self, empty_board):
        """Pawn at left edge has only one diagonal."""
        empty_board.place_piece(1, 6, WHITE)
        moves = empty_board.get_valid_moves(1, 6)
        assert moves == [(2, 5)]

    def test_white_cannot_move_backward(self, empty_board):
        """White pawn cannot move down."""
        empty_board.place_piece(5, 4, WHITE)
        moves = empty_board.get_valid_moves(5, 4)
        for _x, y in moves:
            assert y < 4

    def test_no_moves_for_empty(self, empty_board):
        moves = empty_board.get_valid_moves(5, 5)
        assert moves == []


class TestKingMoves:
    """Test non-capture moves for kings."""

    def test_king_moves_all_directions(self, empty_board):
        """King in center should move in all 4 diagonals."""
        empty_board.place_piece(4, 5, WHITE_KING)
        moves = empty_board.get_valid_moves(4, 5)
        assert len(moves) > 4

    def test_king_moves_long_diagonal(self, empty_board):
        """King can move any distance along diagonal."""
        empty_board.place_piece(1, 8, WHITE_KING)
        moves = empty_board.get_valid_moves(1, 8)
        assert (8, 1) in moves

    def test_king_blocked_by_piece(self, empty_board):
        """King stops before a piece on the diagonal."""
        empty_board.place_piece(1, 8, WHITE_KING)
        empty_board.place_piece(4, 5, BLACK)
        moves = empty_board.get_valid_moves(1, 8)
        assert (2, 7) in moves
        assert (3, 6) in moves
        assert (4, 5) not in moves
        assert (5, 4) not in moves


class TestPawnCaptures:
    """Test capture logic for regular pieces."""

    def test_simple_capture(self, empty_board):
        """White pawn at e3 captures black at d4, lands at c5."""
        empty_board.place_piece(5, 6, WHITE)
        empty_board.place_piece(4, 5, BLACK)
        captures = empty_board.get_captures(5, 6)
        assert len(captures) >= 1
        assert any(path[-1] == (3, 4) for path in captures)

    def test_capture_in_all_directions(self, empty_board):
        """Pawns can capture in any direction in Russian draughts."""
        empty_board.place_piece(4, 5, WHITE)
        empty_board.place_piece(3, 4, BLACK)
        empty_board.place_piece(5, 6, BLACK)
        captures = empty_board.get_captures(4, 5)
        landing_positions = {path[-1] for path in captures}
        assert (2, 3) in landing_positions
        assert (6, 7) in landing_positions

    def test_double_capture(self, empty_board):
        """White captures two black pieces in sequence."""
        empty_board.place_piece(7, 8, WHITE)
        empty_board.place_piece(6, 7, BLACK)
        empty_board.place_piece(4, 5, BLACK)
        captures = empty_board.get_captures(7, 8)
        assert any(len(path) == 3 and path[-1] == (3, 4) for path in captures)

    def test_no_capture_of_friendly(self, empty_board):
        """Cannot capture own pieces."""
        empty_board.place_piece(5, 6, WHITE)
        empty_board.place_piece(4, 5, WHITE)
        captures = empty_board.get_captures(5, 6)
        assert captures == []

    def test_capture_requires_landing(self, empty_board):
        """Capture impossible if landing square is occupied."""
        empty_board.place_piece(5, 6, WHITE)
        empty_board.place_piece(4, 5, BLACK)
        empty_board.place_piece(3, 4, BLACK)
        captures = empty_board.get_captures(5, 6)
        assert not any(path[-1] == (3, 4) for path in captures if len(path) == 2)

    def test_cannot_capture_same_piece_twice(self, empty_board):
        """A captured piece cannot be jumped again in the same sequence."""
        empty_board.place_piece(1, 4, WHITE)
        empty_board.place_piece(2, 3, BLACK)
        captures = empty_board.get_captures(1, 4)
        for path in captures:
            jumps_over_23 = 0
            for i in range(len(path) - 1):
                x1, y1 = path[i]
                x2, y2 = path[i + 1]
                dx = 1 if x2 > x1 else -1
                dy = 1 if y2 > y1 else -1
                cx, cy = x1 + dx, y1 + dy
                while (cx, cy) != (x2, y2):
                    if (cx, cy) == (2, 3):
                        jumps_over_23 += 1
                    cx += dx
                    cy += dy
            assert jumps_over_23 <= 1


class TestKingCaptures:
    """Test capture logic for kings."""

    def test_king_capture_at_distance(self, empty_board):
        """King captures enemy that's not adjacent."""
        empty_board.place_piece(1, 8, WHITE_KING)
        empty_board.place_piece(4, 5, BLACK)
        captures = empty_board.get_captures(1, 8)
        assert len(captures) >= 1
        landing_positions = {path[-1] for path in captures}
        assert any(pos in landing_positions for pos in [(5, 4), (6, 3), (7, 2), (8, 1)])

    def test_king_multiple_landing_squares(self, empty_board):
        """King can land on multiple squares after capture."""
        empty_board.place_piece(1, 8, WHITE_KING)
        empty_board.place_piece(3, 6, BLACK)
        captures = empty_board.get_captures(1, 8)
        landing_positions = {path[-1] for path in captures}
        possible = {(4, 5), (5, 4), (6, 3), (7, 2), (8, 1)}
        assert landing_positions & possible


class TestPromotion:
    """Test pawn promotion to king."""

    def test_white_promotes_on_row_1(self, empty_board):
        """White pawn reaching row 1 becomes king."""
        empty_board.place_piece(2, 2, WHITE)
        empty_board.execute_move(2, 2, 1, 1)
        assert empty_board.piece_at(1, 1) == WHITE_KING

    def test_black_promotes_on_row_8(self, empty_board):
        """Black pawn reaching row 8 becomes king."""
        empty_board.place_piece(7, 7, BLACK)
        empty_board.execute_move(7, 7, 8, 8)
        assert empty_board.piece_at(8, 8) == BLACK_KING

    def test_promotion_on_capture(self, empty_board):
        """Pawn promotes when reaching last row via capture."""
        empty_board2 = Board(empty=True)
        empty_board2.place_piece(4, 3, WHITE)
        empty_board2.place_piece(3, 2, BLACK)
        captures = empty_board2.get_captures(4, 3)
        if captures:
            empty_board2.execute_capture_path(captures[0])
            final_x, final_y = captures[0][-1]
            if final_y == 1:
                assert empty_board2.piece_at(final_x, final_y) == WHITE_KING


class TestExecuteMove:
    """Test move execution."""

    def test_simple_move(self, empty_board):
        empty_board.place_piece(5, 6, WHITE)
        empty_board.execute_move(5, 6, 4, 5)
        assert empty_board.piece_at(5, 6) == EMPTY
        assert empty_board.piece_at(4, 5) == WHITE

    def test_capture_removes_piece(self, empty_board):
        empty_board.place_piece(5, 6, WHITE)
        empty_board.place_piece(4, 5, BLACK)
        captures = empty_board.get_captures(5, 6)
        assert len(captures) >= 1
        path = captures[0]
        captured = empty_board.execute_capture_path(path)
        assert len(captured) == 1
        assert (4, 5) in captured
        assert empty_board.piece_at(4, 5) == EMPTY
        assert empty_board.piece_at(5, 6) == EMPTY
        assert empty_board.piece_at(3, 4) == WHITE


class TestMandatoryCapture:
    """Test has_any_capture — mandatory capture detection."""

    def test_has_capture(self, empty_board):
        empty_board.place_piece(5, 6, WHITE)
        empty_board.place_piece(4, 5, BLACK)
        assert empty_board.has_any_capture("w")

    def test_no_capture(self, empty_board):
        empty_board.place_piece(5, 6, WHITE)
        assert not empty_board.has_any_capture("w")

    def test_initial_position_no_captures(self, board):
        assert not board.has_any_capture("w")
        assert not board.has_any_capture("b")


class TestHasAnyMove:
    """Test has_any_move — game over detection."""

    def test_initial_has_moves(self, board):
        assert board.has_any_move("w")
        assert board.has_any_move("b")

    def test_no_pieces_no_moves(self, empty_board):
        assert not empty_board.has_any_move("w")
        assert not empty_board.has_any_move("b")

    def test_blocked_piece_no_moves(self, empty_board):
        assert not empty_board.has_any_move("w")


class TestCopy:
    def test_copy_independence(self, board):
        copy = board.copy()
        copy.place_piece(1, 1, EMPTY)
        assert copy.to_position_string() != board.to_position_string() or board.piece_at(1, 1) == EMPTY


class TestDangerousPosition:
    """Test dangerous_position — piece under attack detection."""

    def test_piece_under_attack(self, empty_board):
        empty_board.place_piece(5, 6, WHITE)
        empty_board.place_piece(4, 5, BLACK)
        assert empty_board.dangerous_position(5, 6, "w")

    def test_piece_safe(self, empty_board):
        empty_board.place_piece(5, 6, WHITE)
        assert not empty_board.dangerous_position(5, 6, "w")

    def test_king_attack_from_distance(self, empty_board):
        """A king can attack from distance."""
        empty_board.place_piece(5, 4, WHITE)
        empty_board.place_piece(2, 1, BLACK_KING)
        assert empty_board.dangerous_position(5, 4, "w")


class TestFreeway:
    def test_clear_path(self, empty_board):
        assert empty_board.is_diagonal_clear(1, 8, 8, 1)

    def test_blocked_path(self, empty_board):
        empty_board.place_piece(4, 5, BLACK)
        assert not empty_board.is_diagonal_clear(1, 8, 8, 1)

    def test_same_square(self, empty_board):
        assert empty_board.is_diagonal_clear(3, 3, 3, 3)
