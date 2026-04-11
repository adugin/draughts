"""Tests for the AI module (0-indexed coordinates)."""

from draughts.config import BLACK, BLACK_KING, EMPTY, WHITE, Color
from draughts.game.ai import (
    AIEngine,
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


def make_board(position_str: str) -> Board:
    b = Board(empty=True)
    b.load_from_position_string(position_str)
    return b


class TestCaptures:
    def test_simple_pawn_capture(self):
        """Black pawn at (1,4) can capture white at (2,5) landing at (3,6)."""
        b = Board(empty=True)
        b.place_piece(1, 4, BLACK)
        b.place_piece(2, 5, WHITE)
        move = _search_best_move(b, Color.BLACK, 1)
        assert move is not None
        assert move.kind == "capture"
        assert move.path[0] == (1, 4)
        assert (3, 6) in move.path

    def test_no_capture_available(self):
        b = Board(empty=True)
        b.place_piece(0, 1, BLACK)
        b.place_piece(7, 6, WHITE)
        move = _search_best_move(b, Color.BLACK, 1)
        assert move is not None
        assert move.kind == "move"

    def test_king_capture(self):
        b = Board(empty=True)
        b.place_piece(0, 1, BLACK_KING)
        b.place_piece(2, 3, WHITE)
        move = _search_best_move(b, Color.BLACK, 1)
        assert move is not None
        assert move.kind == "capture"
        assert move.path[0] == (0, 1)

    def test_multi_jump(self):
        b = Board(empty=True)
        b.place_piece(0, 1, BLACK)
        b.place_piece(1, 2, WHITE)
        b.place_piece(3, 4, WHITE)
        move = _search_best_move(b, Color.BLACK, 1)
        assert move is not None
        assert move.kind == "capture"
        assert len(move.path) >= 3

    def test_white_capture(self):
        b = Board(empty=True)
        b.place_piece(4, 3, WHITE)
        b.place_piece(3, 2, BLACK)
        move = _search_best_move(b, Color.WHITE, 1)
        assert move is not None
        assert move.kind == "capture"
        assert move.path[0] == (4, 3)


class TestNormalMoves:
    def test_initial_board_finds_move(self):
        b = Board()
        move = _search_best_move(b, Color.BLACK, 1)
        assert move is not None
        assert move.kind == "move"
        assert len(move.path) == 2
        (x1, y1), (_x2, y2) = move.path
        assert b.piece_at(x1, y1) == BLACK
        assert b.piece_at(_x2, y2) == EMPTY
        assert y2 == y1 + 1

    def test_white_finds_move(self):
        b = Board()
        move = _search_best_move(b, Color.WHITE, 1)
        assert move is not None
        assert move.kind == "move"
        (x1, y1), (_x2, y2) = move.path
        assert b.piece_at(x1, y1) == WHITE
        assert y2 == y1 - 1

    def test_king_move(self):
        b = Board(empty=True)
        b.place_piece(2, 3, BLACK_KING)
        b.place_piece(1, 6, WHITE)
        move = _search_best_move(b, Color.BLACK, 1)
        assert move is not None
        (x1, y1), (_x2, _y2) = move.path
        assert (x1, y1) == (2, 3)

    def test_no_moves(self):
        b = Board(empty=True)
        b.place_piece(0, 0, WHITE)
        move = _search_best_move(b, Color.BLACK, 1)
        assert move is None


class TestMoveGeneration:
    def test_captures_are_mandatory(self):
        b = Board(empty=True)
        b.place_piece(4, 5, WHITE)
        b.place_piece(3, 4, BLACK)
        b.place_piece(1, 2, BLACK)
        moves = _generate_all_moves(b, Color.WHITE)
        assert all(kind == "capture" for kind, _ in moves)

    def test_normal_moves_when_no_captures(self):
        b = Board(empty=True)
        b.place_piece(4, 5, WHITE)
        moves = _generate_all_moves(b, Color.WHITE)
        assert len(moves) > 0
        assert all(kind == "move" for kind, _ in moves)


class TestComputerMove:
    def test_initial_position(self):
        b = Board()
        move = computer_move(b, difficulty=2, color=Color.BLACK)
        assert move is not None
        assert isinstance(move, AIMove)
        assert len(move.path) >= 2

    def test_capture_prioritized(self):
        b = Board(empty=True)
        b.place_piece(1, 4, BLACK)
        b.place_piece(2, 5, WHITE)
        move = computer_move(b, difficulty=2, color=Color.BLACK)
        assert move is not None
        assert move.kind == "capture"

    def test_no_pieces_returns_none(self):
        b = Board(empty=True)
        b.place_piece(0, 0, WHITE)
        move = computer_move(b, difficulty=2, color=Color.BLACK)
        assert move is None

    def test_difficulty_levels(self):
        for diff in (1, 2, 3):
            b = Board()
            move = computer_move(b, difficulty=diff, color=Color.BLACK)
            assert move is not None, f"Difficulty {diff} returned None"

    def test_white_computer(self):
        b = Board()
        move = computer_move(b, difficulty=2, color=Color.WHITE)
        assert move is not None
        (x1, y1), (_x2, _y2) = move.path[:2]
        piece = b.piece_at(x1, y1)
        assert Board.is_white(piece)

    def test_explicit_depth(self):
        b = Board()
        move = computer_move(b, difficulty=1, color=Color.BLACK, depth=2)
        assert move is not None

    def test_deep_search(self):
        b = Board(empty=True)
        b.place_piece(2, 3, BLACK_KING)
        b.place_piece(5, 6, WHITE)
        move = computer_move(b, difficulty=3, color=Color.BLACK, depth=6)
        assert move is not None


class TestEvaluation:
    def test_starting_position_balanced(self):
        b = Board()
        score = evaluate_position(b.grid, Color.BLACK)
        assert abs(score) < 2.0

    def test_material_advantage(self):
        b = Board(empty=True)
        b.place_piece(2, 3, BLACK)
        b.place_piece(4, 5, BLACK)
        b.place_piece(6, 7, WHITE)
        score = evaluate_position(b.grid, Color.BLACK)
        assert score > 0

    def test_no_pieces_terminal(self):
        b = Board(empty=True)
        b.place_piece(2, 3, BLACK)
        score = evaluate_position(b.grid, Color.BLACK)
        assert score > 500

    def test_fast_eval_consistent(self):
        b = Board(empty=True)
        b.place_piece(2, 3, BLACK)
        b.place_piece(4, 5, BLACK)
        b.place_piece(6, 7, WHITE)
        full = evaluate_position(b.grid, Color.BLACK)
        fast = _evaluate_fast(b.grid, Color.BLACK)
        assert full > 0 and fast > 0


class TestHelpers:
    def test_dangerous_position_under_attack(self):
        b = Board(empty=True)
        b.place_piece(2, 3, BLACK)
        b.place_piece(3, 4, WHITE)
        assert _dangerous_position(2, 3, b.grid, Color.BLACK) is True

    def test_dangerous_position_safe(self):
        b = Board(empty=True)
        b.place_piece(2, 3, BLACK)
        assert _dangerous_position(2, 3, b.grid, Color.BLACK) is False

    def test_danger_any_piece(self):
        b = Board(empty=True)
        b.place_piece(2, 3, BLACK)
        b.place_piece(3, 4, WHITE)
        assert _any_piece_threatened(Color.BLACK, b.grid) is True
        assert _any_piece_threatened(Color.WHITE, b.grid) is True

    def test_number_count(self):
        b = Board()
        assert _count_pieces(Color.BLACK, b.grid) == 12
        assert _count_pieces(Color.WHITE, b.grid) == 12

    def test_is_on_board(self):
        assert _is_on_board(0, 0) is True
        assert _is_on_board(7, 7) is True
        assert _is_on_board(-1, 0) is False
        assert _is_on_board(8, 0) is False

    def test_scan_diagonal_empty(self):
        b = Board(empty=True)
        count, _bx, _by = _scan_diagonal(0, 0, 3, 3, Color.WHITE, b.grid)
        assert count == 0

    def test_scan_diagonal_one_piece(self):
        b = Board(empty=True)
        b.place_piece(2, 2, WHITE)
        count, bx, by = _scan_diagonal(0, 0, 4, 4, Color.WHITE, b.grid)
        assert count == 1
        assert (bx, by) == (2, 2)


class TestEdgeCases:
    def test_endgame_king_vs_pawn(self):
        b = Board(empty=True)
        b.place_piece(2, 3, BLACK_KING)
        b.place_piece(5, 6, WHITE)
        move = computer_move(b, difficulty=2, color=Color.BLACK)
        assert move is not None

    def test_king_capture_finds_path(self):
        b = Board(empty=True)
        b.place_piece(0, 1, BLACK_KING)
        b.place_piece(3, 4, WHITE)
        move = _search_best_move(b, Color.BLACK, 1)
        assert move is not None
        assert len(move.path) >= 2
        assert move.path[0] == (0, 1)


class TestAIEngine:
    """Tests for the AIEngine class."""

    def test_find_move_initial(self):
        engine = AIEngine(difficulty=2, color=Color.BLACK)
        b = Board()
        move = engine.find_move(b)
        assert move is not None
        assert isinstance(move, AIMove)
        assert len(move.path) >= 2

    def test_find_move_white(self):
        engine = AIEngine(difficulty=2, color=Color.WHITE)
        b = Board()
        move = engine.find_move(b)
        assert move is not None
        x1, y1 = move.path[0]
        assert Board.is_white(b.piece_at(x1, y1))

    def test_find_move_capture(self):
        engine = AIEngine(difficulty=2, color=Color.BLACK)
        b = Board(empty=True)
        b.place_piece(1, 4, BLACK)
        b.place_piece(2, 5, WHITE)
        move = engine.find_move(b)
        assert move is not None
        assert move.kind == "capture"

    def test_explicit_search_depth(self):
        engine = AIEngine(difficulty=1, color=Color.BLACK, search_depth=2)
        b = Board()
        move = engine.find_move(b)
        assert move is not None

    def test_no_pieces_returns_none(self):
        engine = AIEngine(difficulty=2, color=Color.BLACK)
        b = Board(empty=True)
        b.place_piece(0, 0, WHITE)
        move = engine.find_move(b)
        assert move is None

    def test_matches_computer_move(self):
        """AIEngine.find_move should produce equivalent results to computer_move."""
        b = Board(empty=True)
        b.place_piece(2, 3, BLACK_KING)
        b.place_piece(5, 6, WHITE)
        engine = AIEngine(difficulty=2, color=Color.BLACK)
        move = engine.find_move(b)
        assert move is not None
        # Both should find a move (specific move may vary due to randomness)
        legacy_move = computer_move(b, difficulty=2, color=Color.BLACK)
        assert legacy_move is not None
