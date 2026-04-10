"""Tests for the AI module."""

from draughts.config import BLACK, BLACK_KING, EMPTY, WHITE
from draughts.game.ai import (
    AIMove,
    _any_piece_threatened,
    _count_pieces,
    _dangerous_position,
    _evaluate_fast,
    _generate_all_moves,
    _is_on_board,
    _scan_diagonal,
    _search_best_move,
    computer_move,
    evaluate_position,
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
# Tests: Capture detection (replaces TestSeeBeat)
# ---------------------------------------------------------------------------


class TestCaptures:
    def test_simple_pawn_capture(self):
        """Black pawn at (2,5) can capture white pawn at (3,6) landing at (4,7)."""
        b = Board(empty=True)
        b.place_piece(2, 5, BLACK)
        b.place_piece(3, 6, WHITE)
        move = _search_best_move(b, "b", depth=1)
        assert move is not None
        assert move.kind == "capture"
        assert move.path[0] == (2, 5)
        assert (4, 7) in move.path

    def test_no_capture_available(self):
        """No captures — should find a normal move, not None."""
        b = Board(empty=True)
        b.place_piece(1, 2, BLACK)
        b.place_piece(8, 7, WHITE)
        # Should find a move (not capture)
        move = _search_best_move(b, "b", depth=1)
        assert move is not None
        assert move.kind == "move"

    def test_king_capture(self):
        """Black king should find capture."""
        b = Board(empty=True)
        b.place_piece(1, 2, BLACK_KING)
        b.place_piece(3, 4, WHITE)
        move = _search_best_move(b, "b", depth=1)
        assert move is not None
        assert move.kind == "capture"
        assert move.path[0] == (1, 2)

    def test_multi_jump(self):
        """Black pawn should find multi-jump capture."""
        b = Board(empty=True)
        b.place_piece(1, 2, BLACK)
        b.place_piece(2, 3, WHITE)
        b.place_piece(4, 5, WHITE)
        move = _search_best_move(b, "b", depth=1)
        assert move is not None
        assert move.kind == "capture"
        assert len(move.path) >= 3

    def test_white_capture(self):
        """AI playing as white should find captures too."""
        b = Board(empty=True)
        b.place_piece(5, 4, WHITE)
        b.place_piece(4, 3, BLACK)
        move = _search_best_move(b, "w", depth=1)
        assert move is not None
        assert move.kind == "capture"
        assert move.path[0] == (5, 4)


# ---------------------------------------------------------------------------
# Tests: Normal moves (replaces TestAction)
# ---------------------------------------------------------------------------


class TestNormalMoves:
    def test_initial_board_finds_move(self):
        """On the starting position, black should find a normal move."""
        b = Board()
        move = _search_best_move(b, "b", depth=1)
        assert move is not None
        assert move.kind == "move"
        assert len(move.path) == 2
        (x1, y1), (_x2, y2) = move.path
        assert b.piece_at(x1, y1) == BLACK
        assert b.piece_at(_x2, y2) == EMPTY
        assert y2 == y1 + 1

    def test_white_finds_move(self):
        """White should find a normal move on starting position."""
        b = Board()
        move = _search_best_move(b, "w", depth=1)
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
        move = _search_best_move(b, "b", depth=1)
        assert move is not None
        (x1, y1), (_x2, _y2) = move.path
        assert (x1, y1) == (3, 4)

    def test_no_moves(self):
        """When no moves possible, should return None."""
        b = Board(empty=True)
        b.place_piece(1, 1, WHITE)
        move = _search_best_move(b, "b", depth=1)
        assert move is None


# ---------------------------------------------------------------------------
# Tests: Move generation
# ---------------------------------------------------------------------------


class TestMoveGeneration:
    def test_captures_are_mandatory(self):
        """When captures exist, only captures should be returned."""
        b = Board(empty=True)
        b.place_piece(5, 6, WHITE)
        b.place_piece(4, 5, BLACK)
        b.place_piece(2, 3, BLACK)  # another piece with normal moves
        moves = _generate_all_moves(b, "w")
        assert all(kind == "capture" for kind, _ in moves)

    def test_normal_moves_when_no_captures(self):
        """Normal moves returned when no captures available."""
        b = Board(empty=True)
        b.place_piece(5, 6, WHITE)
        moves = _generate_all_moves(b, "w")
        assert len(moves) > 0
        assert all(kind == "move" for kind, _ in moves)


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

    def test_explicit_depth(self):
        """Explicit depth parameter should work."""
        b = Board()
        move = computer_move(b, difficulty=1, color="b", depth=2)
        assert move is not None

    def test_deep_search(self):
        """Deeper search should still work for simple positions."""
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK_KING)
        b.place_piece(6, 7, WHITE)
        move = computer_move(b, difficulty=3, color="b", depth=6)
        assert move is not None


# ---------------------------------------------------------------------------
# Tests: Evaluation functions
# ---------------------------------------------------------------------------


class TestEvaluation:
    def test_starting_position_balanced(self):
        """Starting position should be roughly balanced."""
        b = Board()
        score = evaluate_position(b.grid, "b")
        assert abs(score) < 2.0  # approximately balanced

    def test_material_advantage(self):
        """More pieces = higher score."""
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK)
        b.place_piece(5, 6, BLACK)
        b.place_piece(7, 8, WHITE)
        score = evaluate_position(b.grid, "b")
        assert score > 0  # black has 2v1

    def test_no_pieces_terminal(self):
        """No pieces for one side = terminal score."""
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK)
        score = evaluate_position(b.grid, "b")
        assert score > 500  # winning (opponent has no pieces)

    def test_fast_eval_consistent(self):
        """Fast eval should agree on sign with full eval."""
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK)
        b.place_piece(5, 6, BLACK)
        b.place_piece(7, 8, WHITE)
        full = evaluate_position(b.grid, "b")
        fast = _evaluate_fast(b.grid, "b")
        # Both should agree black is winning
        assert full > 0 and fast > 0


# ---------------------------------------------------------------------------
# Tests: helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_dangerous_position_under_attack(self):
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK)
        b.place_piece(4, 5, WHITE)
        assert _dangerous_position(3, 4, b.grid, "b") is True

    def test_dangerous_position_safe(self):
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK)
        assert _dangerous_position(3, 4, b.grid, "b") is False

    def test_danger_any_piece(self):
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK)
        b.place_piece(4, 5, WHITE)
        assert _any_piece_threatened("b", b.grid) is True
        assert _any_piece_threatened("w", b.grid) is True

    def test_number_count(self):
        b = Board()
        assert _count_pieces("b", b.grid) == 12
        assert _count_pieces("w", b.grid) == 12

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
        b = Board(empty=True)
        b.place_piece(3, 4, BLACK_KING)
        b.place_piece(6, 7, WHITE)
        move = computer_move(b, difficulty=2, color="b")
        assert move is not None

    def test_king_capture_finds_path(self):
        b = Board(empty=True)
        b.place_piece(1, 2, BLACK_KING)
        b.place_piece(4, 5, WHITE)
        move = _search_best_move(b, "b", depth=1)
        assert move is not None
        assert len(move.path) >= 2
        assert move.path[0] == (1, 2)
