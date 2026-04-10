"""Tests for the AI module."""

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
        b.place_piece(2, 5, 'b')
        b.place_piece(3, 6, 'w')
        move = _see_beat(b, 'b', False, None)
        assert move is not None
        assert move.kind == 'capture'
        assert move.path[0] == (2, 5)
        # Landing should be (4, 7)
        assert (4, 7) in move.path

    def test_no_capture_available(self):
        """No captures should return None."""
        b = Board(empty=True)
        b.place_piece(1, 2, 'b')
        b.place_piece(8, 7, 'w')
        move = _see_beat(b, 'b', False, None)
        assert move is None

    def test_king_capture(self):
        """Black king should find capture."""
        b = Board(empty=True)
        b.place_piece(1, 2, 'B')
        b.place_piece(3, 4, 'w')
        move = _see_beat(b, 'b', False, None)
        assert move is not None
        assert move.kind == 'capture'
        assert move.path[0] == (1, 2)

    def test_multi_jump(self):
        """Black pawn should find multi-jump capture."""
        b = Board(empty=True)
        b.place_piece(1, 2, 'b')
        b.place_piece(2, 3, 'w')
        b.place_piece(4, 5, 'w')
        # b at (1,2) can jump (2,3)->(3,4), then (4,5)->(5,6)
        move = _see_beat(b, 'b', False, None)
        assert move is not None
        assert move.kind == 'capture'
        assert len(move.path) >= 3  # start + at least 2 landings

    def test_white_capture(self):
        """AI playing as white should find captures too."""
        b = Board(empty=True)
        b.place_piece(5, 4, 'w')
        b.place_piece(4, 3, 'b')
        move = _see_beat(b, 'w', False, None)
        assert move is not None
        assert move.kind == 'capture'
        assert move.path[0] == (5, 4)


# ---------------------------------------------------------------------------
# Tests: Action — normal moves
# ---------------------------------------------------------------------------

class TestAction:
    def test_initial_board_finds_move(self):
        """On the starting position, black should find a normal move."""
        b = Board()
        move = _action(b, 'b', False, None)
        assert move is not None
        assert move.kind == 'move'
        assert len(move.path) == 2
        (x1, y1), (x2, y2) = move.path
        # Start piece should be black
        assert b.piece_at(x1, y1) == 'b'
        # Destination should be empty
        assert b.piece_at(x2, y2) == 'n'
        # Should move forward (down for black)
        assert y2 == y1 + 1

    def test_white_action(self):
        """White should find a normal move on starting position."""
        b = Board()
        move = _action(b, 'w', False, None)
        assert move is not None
        assert move.kind == 'move'
        (x1, y1), (x2, y2) = move.path
        assert b.piece_at(x1, y1) == 'w'
        assert y2 == y1 - 1  # white moves up

    def test_king_move(self):
        """King should find a move via Monte Carlo sampling."""
        b = Board(empty=True)
        b.place_piece(3, 4, 'B')  # dark square: 3%2=1 != 4%2=0
        b.place_piece(2, 7, 'w')  # enemy far away, dark square: 2%2=0 != 7%2=1
        move = _action(b, 'b', False, None)
        assert move is not None
        assert move.kind == 'move'
        (x1, y1), (x2, y2) = move.path
        assert (x1, y1) == (3, 4)

    def test_no_moves(self):
        """When no moves possible, should return None."""
        b = Board(empty=True)
        # Black pawn blocked on last row (already a king scenario is odd,
        # but let's test no-move for a pawn boxed in)
        b.place_piece(1, 8, 'b')  # last row — would become king
        # Actually, pawns at edges with no forward moves
        b = Board(empty=True)
        b.place_piece(1, 8, 'B')  # king at corner
        b.place_piece(2, 7, 'w')  # blocked by white
        # The king could still potentially move if other diags are free
        # Let's make a truly blocked scenario
        b2 = Board(empty=True)
        # No black pieces at all
        b2.place_piece(1, 1, 'w')
        move = _action(b2, 'b', False, None)
        assert move is None


# ---------------------------------------------------------------------------
# Tests: Combination
# ---------------------------------------------------------------------------

class TestCombination:
    def test_no_combination_with_single_piece(self):
        """Combination should not fire when only 1 piece remains."""
        b = Board(empty=True)
        b.place_piece(3, 4, 'b')
        b.place_piece(5, 6, 'w')
        move = _combination(b, 'b', False, None)
        assert move is None

    def test_combination_returns_sacrifice_or_none(self):
        """Combination returns either a sacrifice move or None."""
        b = Board()
        move = _combination(b, 'b', False, None)
        if move is not None:
            assert move.kind == 'sacrifice'
            assert len(move.path) == 2


# ---------------------------------------------------------------------------
# Tests: computer_move (main entry point)
# ---------------------------------------------------------------------------

class TestComputerMove:
    def test_initial_position(self):
        """computer_move should return a valid move on starting board."""
        b = Board()
        move = computer_move(b, difficulty=2, color='b')
        assert move is not None
        assert isinstance(move, AIMove)
        assert len(move.path) >= 2

    def test_capture_prioritized(self):
        """When captures available, computer_move should return a capture."""
        b = Board(empty=True)
        b.place_piece(2, 5, 'b')
        b.place_piece(3, 6, 'w')
        move = computer_move(b, difficulty=2, color='b')
        assert move is not None
        assert move.kind == 'capture'

    def test_no_pieces_returns_none(self):
        """No pieces of the AI's color should return None."""
        b = Board(empty=True)
        b.place_piece(1, 1, 'w')
        move = computer_move(b, difficulty=2, color='b')
        assert move is None

    def test_difficulty_levels(self):
        """All difficulty levels should produce a move on initial board."""
        for diff in (1, 2, 3):
            b = Board()
            move = computer_move(b, difficulty=diff, color='b')
            assert move is not None, f"Difficulty {diff} returned None"

    def test_white_computer(self):
        """Computer playing white should work."""
        b = Board()
        move = computer_move(b, difficulty=2, color='w')
        assert move is not None
        (x1, y1), (x2, y2) = move.path[:2]
        assert b.piece_at(x1, y1) in ('w', 'W')


# ---------------------------------------------------------------------------
# Tests: scoring and helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_dangerous_position_under_attack(self):
        """Piece adjacent to enemy with open landing should be in danger."""
        b = Board(empty=True)
        b.place_piece(3, 4, 'b')
        b.place_piece(4, 5, 'w')
        # w at (4,5) can jump over b at (3,4) if (2,3) is empty
        assert _dangerous_position(3, 4, b.grid, 'b') is True

    def test_dangerous_position_safe(self):
        """Isolated piece should not be in danger."""
        b = Board(empty=True)
        b.place_piece(3, 4, 'b')
        assert _dangerous_position(3, 4, b.grid, 'b') is False

    def test_danger_any_piece(self):
        """_danger should detect if any piece of a color is under threat."""
        # Use dark squares: (3,4) and (4,5) — 3%2=1 != 4%2=0 -> dark; 4%2=0 != 5%2=1 -> dark
        b = Board(empty=True)
        b.place_piece(3, 4, 'b')
        b.place_piece(4, 5, 'w')
        assert _any_piece_threatened('b', b.grid) is True
        assert _any_piece_threatened('w', b.grid) is True

    def test_number_count(self):
        b = Board()
        assert _count_pieces('b', b.grid) == 12
        assert _count_pieces('w', b.grid) == 12

    def test_appreciate_no_change(self):
        """Same position should have 0 appreciation."""
        b = Board()
        assert _appreciate(b.grid, b.grid, 'b') == 0

    def test_appreciate_captures(self):
        """Removing a white piece should be positive for black."""
        b1 = Board()
        b2 = b1.copy()
        # Remove a white piece
        for y in range(1, 9):
            for x in range(1, 9):
                if b2.piece_at(x, y) == 'w':
                    b2.place_piece(x, y, 'n')
                    break
            else:
                continue
            break
        # For black, capturing a white piece is beneficial
        score = _appreciate(b1.grid, b2.grid, 'b')
        assert score > 0

    def test_is_on_board(self):
        assert _is_on_board(1, 1) is True
        assert _is_on_board(8, 8) is True
        assert _is_on_board(0, 1) is False
        assert _is_on_board(9, 1) is False

    def test_exist_empty_path(self):
        b = Board(empty=True)
        count, bx, by = _scan_diagonal(1, 1, 4, 4, 'w', b.grid)
        assert count == 0

    def test_exist_one_piece(self):
        b = Board(empty=True)
        b.place_piece(3, 3, 'w')
        count, bx, by = _scan_diagonal(1, 1, 5, 5, 'w', b.grid)
        assert count == 1
        assert (bx, by) == (3, 3)


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_endgame_king_vs_pawn(self):
        """King vs single pawn — king should find a move."""
        b = Board(empty=True)
        b.place_piece(3, 4, 'B')  # dark square
        b.place_piece(6, 7, 'w')  # dark square
        move = computer_move(b, difficulty=2, color='b')
        assert move is not None

    def test_king_capture_finds_path(self):
        """King capture should produce a valid path."""
        b = Board(empty=True)
        b.place_piece(1, 2, 'B')
        b.place_piece(4, 5, 'w')
        move = _see_beat(b, 'b', False, None)
        assert move is not None
        assert len(move.path) >= 2
        # Verify path starts at king position
        assert move.path[0] == (1, 2)
