"""Tests for the AI module."""

from draughts.config import BLACK, BLACK_KING, EMPTY, WHITE
from draughts.game.ai import (
    AIMove,
    _action,
    _any_piece_threatened,
    _appreciate,
    _combination,
    _count_pieces,
    _dangerous_position,
    _is_on_board,
    _scan_diagonal,
    _see_beat,
    computer_move,
)
from draughts.game.board import Board

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_board(position_str: str) -> Board:
    """Create a Board from a 32-char position string."""
    b = Board(empty=True)
    b.load_from_position_string(position_str)
    return b


# ---------------------------------------------------------------------------
# Tests: SeeBeat — mandatory captures
# ---------------------------------------------------------------------------


class TestSeeBeat:
    def test_simple_pawn_capture(self):
        """Black pawn at (2,5) can capture white pawn at (3,6) landing at (4,7)."""
        b = Board(empty=True)
        b.place_piece(2, 5, BLACK)
        b.place_piece(3, 6, WHITE)
        move = _see_beat(b, "b", False, None)
        assert move is not None
        assert move.kind == "capture"
        assert move.path[0] == (2, 5)
        assert (4, 7) in move.path

    def test_no_capture_available(self):
        """No captures should return None."""
        b = Board(empty=True)
        b.place_piece(1, 2, BLACK)
        b.place_piece(8, 7, WHITE)
        move = _see_beat(b, "b", False, None)
        assert move is None

    def test_king_capture(self):
        """Black king should find capture."""
        b = Board(empty=True)
        b.place_piece(1, 2, BLACK_KING)
        b.place_piece(3, 4, WHITE)
        move = _see_beat(b, "b", False, None)
        assert move is not None
        assert move.kind == "capture"
        assert move.path[0] == (1, 2)

    def test_multi_jump(self):
        """Black pawn should find multi-jump capture."""
        b = Board(empty=True)
        b.place_piece(1, 2, BLACK)
        b.place_piece(2, 3, WHITE)
        b.place_piece(4, 5, WHITE)
        move = _see_beat(b, "b", False, None)
        assert move is not None
        assert move.kind == "capture"
        assert len(move.path) >= 3

    def test_white_capture(self):
        """AI playing as white should find captures too."""
        b = Board(empty=True)
        b.place_piece(5, 4, WHITE)
        b.place_piece(4, 3, BLACK)
        move = _see_beat(b, "w", False, None)
        assert move is not None
        assert move.kind == "capture"
        assert move.path[0] == (5, 4)


# ---------------------------------------------------------------------------
# Tests: Action — normal moves
# ---------------------------------------------------------------------------


class TestAction:
    def test_initial_board_finds_move(self):
        """On the starting position, black should find a normal move."""
        b = Board()
        move = _action(b, "b", False, None)
        assert move is not None
        assert move.kind == "move"
        assert len(move.path) == 2
        (x1, y1), (x2, y2) = move.path
        assert b.piece_at(x1, y1) == BLACK
        assert b.piece_at(x2, y2) == EMPTY
        assert y2 == y1 + 1

    def test_white_action(self):
        """White should find a normal move on starting position."""
        b = Board()
        move = _action(b, "w", False, None)
        assert move is not None
        assert move.kind == "move"
        (x1, y1), (_x2, y2) = move.path
        assert b.piece_at(x1, y1) == WHITE
        assert y2 == y1 - 1

    def test_king_move(self):
        """King should find a move."""
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK_KING)
        b.place_piece(2, 7, WHITE)
        move = _action(b, "b", False, None)
        assert move is not None
        assert move.kind == "move"
        (x1, y1), (_x2, _y2) = move.path
        assert (x1, y1) == (3, 4)

    def test_no_moves(self):
        """When no moves possible, should return None."""
        b2 = Board(empty=True)
        b2.place_piece(1, 1, WHITE)
        move = _action(b2, "b", False, None)
        assert move is None


# ---------------------------------------------------------------------------
# Tests: Combination
# ---------------------------------------------------------------------------


class TestCombination:
    def test_no_combination_with_single_piece(self):
        """Combination should not fire when only 1 piece remains."""
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK)
        b.place_piece(5, 6, WHITE)
        move = _combination(b, "b", False, None)
        assert move is None

    def test_combination_returns_sacrifice_or_none(self):
        """Combination returns either a sacrifice move or None."""
        b = Board()
        move = _combination(b, "b", False, None)
        if move is not None:
            assert move.kind == "sacrifice"
            assert len(move.path) == 2


# ---------------------------------------------------------------------------
# Tests: computer_move (main entry point)
# ---------------------------------------------------------------------------


class TestComputerMove:
    def test_initial_position(self):
        """computer_move should return a valid move on starting board."""
        b = Board()
        move = computer_move(b, difficulty=2, color="b")
        assert move is not None
        assert isinstance(move, AIMove)
        assert len(move.path) >= 2

    def test_capture_prioritized(self):
        """When captures available, computer_move should return a capture."""
        b = Board(empty=True)
        b.place_piece(2, 5, BLACK)
        b.place_piece(3, 6, WHITE)
        move = computer_move(b, difficulty=2, color="b")
        assert move is not None
        assert move.kind == "capture"

    def test_no_pieces_returns_none(self):
        """No pieces of the AI's color should return None."""
        b = Board(empty=True)
        b.place_piece(1, 1, WHITE)
        move = computer_move(b, difficulty=2, color="b")
        assert move is None

    def test_difficulty_levels(self):
        """All difficulty levels should produce a move on initial board."""
        for diff in (1, 2, 3):
            b = Board()
            move = computer_move(b, difficulty=diff, color="b")
            assert move is not None, f"Difficulty {diff} returned None"

    def test_white_computer(self):
        """Computer playing white should work."""
        b = Board()
        move = computer_move(b, difficulty=2, color="w")
        assert move is not None
        (x1, y1), (_x2, _y2) = move.path[:2]
        piece = b.piece_at(x1, y1)
        assert Board.is_white(piece)


# ---------------------------------------------------------------------------
# Tests: scoring and helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_dangerous_position_under_attack(self):
        """Piece adjacent to enemy with open landing should be in danger."""
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK)
        b.place_piece(4, 5, WHITE)
        assert _dangerous_position(3, 4, b.grid, "b") is True

    def test_dangerous_position_safe(self):
        """Isolated piece should not be in danger."""
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK)
        assert _dangerous_position(3, 4, b.grid, "b") is False

    def test_danger_any_piece(self):
        """_any_piece_threatened should detect threatened pieces."""
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK)
        b.place_piece(4, 5, WHITE)
        assert _any_piece_threatened("b", b.grid) is True
        assert _any_piece_threatened("w", b.grid) is True

    def test_number_count(self):
        b = Board()
        assert _count_pieces("b", b.grid) == 12
        assert _count_pieces("w", b.grid) == 12

    def test_appreciate_no_change(self):
        """Same position should have 0 appreciation."""
        b = Board()
        assert _appreciate(b.grid, b.grid, "b") == 0

    def test_appreciate_captures(self):
        """Removing a white piece should be positive for black."""
        b1 = Board()
        b2 = b1.copy()
        for y in range(1, 9):
            for x in range(1, 9):
                if b2.piece_at(x, y) == WHITE:
                    b2.place_piece(x, y, EMPTY)
                    break
            else:
                continue
            break
        score = _appreciate(b1.grid, b2.grid, "b")
        assert score > 0

    def test_is_on_board(self):
        assert _is_on_board(1, 1) is True
        assert _is_on_board(8, 8) is True
        assert _is_on_board(0, 1) is False
        assert _is_on_board(9, 1) is False

    def test_exist_empty_path(self):
        b = Board(empty=True)
        count, _bx, _by = _scan_diagonal(1, 1, 4, 4, "w", b.grid)
        assert count == 0

    def test_exist_one_piece(self):
        b = Board(empty=True)
        b.place_piece(3, 3, WHITE)
        count, bx, by = _scan_diagonal(1, 1, 5, 5, "w", b.grid)
        assert count == 1
        assert (bx, by) == (3, 3)


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_endgame_king_vs_pawn(self):
        """King vs single pawn — king should find a move."""
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK_KING)
        b.place_piece(6, 7, WHITE)
        move = computer_move(b, difficulty=2, color="b")
        assert move is not None

    def test_king_capture_finds_path(self):
        """King capture should produce a valid path."""
        b = Board(empty=True)
        b.place_piece(1, 2, BLACK_KING)
        b.place_piece(4, 5, WHITE)
        move = _see_beat(b, "b", False, None)
        assert move is not None
        assert len(move.path) >= 2
        assert move.path[0] == (1, 2)
