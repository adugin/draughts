"""Tests for the AI module (0-indexed coordinates)."""

from draughts.config import BLACK, BLACK_KING, EMPTY, WHITE, Color
from draughts.game.ai import (
    _CONTEMPT,
    AIEngine,
    AIMove,
    _alphabeta,
    _any_piece_threatened,
    _count_pieces,
    _dangerous_position,
    _evaluate_fast,
    _generate_all_moves,
    _is_on_board,
    _scan_diagonal,
    _search_best_move,
    adaptive_depth,
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

    def test_perspective_symmetry_under_v_flip_color_swap(self):
        """The eval must be invariant under the natural 'swap sides' symmetry:
        flip the board vertically AND swap colors. This operation takes a
        position to the equivalent one viewed from the opposite side, so
        eval(b, BLACK) + eval(v_flip(-b), BLACK) must equal 0.

        A regression test: the AI vs AI analysis flagged a suspected first-
        mover bias, and this test protects against anyone accidentally
        introducing a real asymmetry in _evaluate_fast later.
        """
        import numpy as np

        positions = [
            # Starting position
            Board().grid.copy(),
            # Midgame: mixed pawns and kings
            self._make_grid([(2, 3, BLACK), (4, 5, BLACK), (3, 4, BLACK_KING),
                             (5, 2, WHITE), (6, 1, WHITE), (4, 7, WHITE)]),
            # Endgame: kings only
            self._make_grid([(1, 0, BLACK_KING), (3, 6, WHITE), (5, 4, WHITE)]),
            # Asymmetric midgame — the position that originally motivated
            # this test (a black-heavy opening-like position)
            self._make_grid([
                (0, 1, BLACK), (0, 3, BLACK), (0, 5, BLACK), (0, 7, BLACK),
                (1, 0, BLACK), (1, 2, BLACK),
                (7, 0, WHITE), (7, 2, WHITE), (7, 4, WHITE), (7, 6, WHITE),
                (6, 1, WHITE), (6, 3, WHITE),
            ]),
        ]

        for grid in positions:
            mirror = -np.flipud(grid)
            e_orig = _evaluate_fast(grid, Color.BLACK)
            e_mirror = _evaluate_fast(mirror, Color.BLACK)
            # mirror is the same position viewed from the opposite side,
            # so eval-from-BLACK of the mirror should be the negation of
            # the original's eval-from-BLACK.
            assert abs(e_orig + e_mirror) < 1e-5, (
                f"eval asymmetry under v_flip+color_swap: "
                f"orig={e_orig:+.6f}, mirror={e_mirror:+.6f}, "
                f"sum={e_orig + e_mirror:+.6f}"
            )

    @staticmethod
    def _make_grid(placements):
        import numpy as np
        g = np.zeros((8, 8), dtype=np.int8)
        for y, x, piece in placements:
            g[y, x] = piece
        return g


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


class TestAdaptiveDepth:
    def test_crowded_position_caps_at_4(self):
        b = Board()  # 24 pieces
        assert adaptive_depth(5, b) == 4
        assert adaptive_depth(8, b) == 4

    def test_midgame_passthrough(self):
        b = Board(empty=True)
        # 5 black + 5 white = 10 pieces: not crowded (>16), not endgame (<=6)
        for i, (x, y) in enumerate([(1, 0), (3, 0), (5, 0), (7, 0), (0, 1)]):
            b.place_piece(x, y, BLACK)
        for x, y in [(0, 7), (2, 7), (4, 7), (6, 7), (1, 6)]:
            b.place_piece(x, y, WHITE)
        assert adaptive_depth(5, b) == 5
        assert adaptive_depth(7, b) == 7

    def test_endgame_boost_plus_one(self):
        b = Board(empty=True)
        b.place_piece(0, 0, BLACK)
        b.place_piece(2, 2, BLACK)
        b.place_piece(4, 4, WHITE)
        b.place_piece(6, 6, WHITE)
        # 4 pieces — endgame, boost by +1
        assert adaptive_depth(5, b) == 6
        assert adaptive_depth(7, b) == 8
        # Already at the cap — don't boost past 8
        assert adaptive_depth(8, b) == 8

    def test_endgame_boost_respects_hard_cap(self):
        b = Board(empty=True)
        b.place_piece(0, 0, BLACK_KING)
        b.place_piece(7, 7, WHITE)
        # Only 2 pieces — still boost by +1, capped at 8
        assert adaptive_depth(6, b) == 7
        assert adaptive_depth(7, b) == 8
        assert adaptive_depth(9, b) == 9  # >= 8, skip boost entirely


class TestDiagonalDistance:
    def test_same_diagonal_distance_is_chebyshev(self):
        from draughts.game.ai import _diagonal_distance
        # On same diagonal: just max(dx, dy).
        assert _diagonal_distance(0, 0) == 0
        assert _diagonal_distance(1, 1) == 1
        assert _diagonal_distance(7, 7) == 7

    def test_off_diagonal_adds_penalty(self):
        from draughts.game.ai import _diagonal_distance
        # (dx, dy) = (1, 3): max=3, off-diag=2, dist = 3 + 4 = 7.
        assert _diagonal_distance(1, 3) == 7
        # (dx, dy) = (3, 5): max=5, off-diag=2, dist = 5 + 4 = 9.
        assert _diagonal_distance(3, 5) == 9

    def test_h8_vs_b4_is_unreachable_level(self):
        """The canonical bug: king at h8 facing pawn at b4. h8 is not on
        any diagonal with b4, so the heuristic should NOT score this
        pair as 'close' — distance must exceed the 7-square clamp."""
        from draughts.game.ai import _diagonal_distance
        # h8 = (0,7), b4 = (4,1). dx=6, dy=4, off-diag=2, dist = 6+4 = 10.
        assert _diagonal_distance(6, 4) >= 7

    def test_king_distance_prefers_aligned_king(self):
        """King on an attack diagonal to a pawn should score strictly
        better than a king the same Chebyshev distance away but off
        the diagonal."""
        import numpy as np
        from draughts.game.ai import _king_distance_score
        # Pawn at d4 (y=4, x=3)
        base = np.zeros((8, 8), dtype=np.int8)
        base[4, 3] = 1  # BLACK pawn

        aligned = base.copy()
        aligned[7, 0] = -2  # WHITE king at a1 — on the a1-h8 diagonal

        off_diag = base.copy()
        off_diag[7, 6] = -2  # WHITE king at g1 — NOT on any diag with d4
        # a1 vs d4: dx=3 dy=3 -> dist 3 -> bonus 2.0 -> score -2.0
        # g1 vs d4: dx=3 dy=3? Let's check: (7,6) vs (4,3): dx=3, dy=3.
        # Oh, g1 IS on a diagonal with d4 too. Pick a truly off-diagonal
        # square: h2 = (6, 7).
        off_diag[7, 6] = 0
        off_diag[6, 7] = -2  # WHITE king at h2
        # h2 vs d4: dx=4, dy=2 -> off-diag=2 -> dist = 4+4 = 8 -> bonus 0

        s_aligned = _king_distance_score(aligned)
        s_off = _king_distance_score(off_diag)
        # Both are negative (white king approaching black pawn = white's
        # advantage). Aligned should be strictly more negative.
        assert s_aligned < s_off, f"aligned={s_aligned}, off={s_off}"


class TestContempt:
    def test_drawn_endgame_returns_negative_contempt(self):
        """King vs King is a drawn endgame pattern. The minimax score
        should be the contempt bias (slightly negative from root's POV),
        not exactly 0 — the searching side prefers decisive play."""
        b = Board(empty=True)
        b.place_piece(0, 0, BLACK_KING)
        b.place_piece(7, 7, -2)  # WHITE_KING
        score = _alphabeta(
            b, depth=3, alpha=-1000, beta=1000,
            maximizing=True, color=Color.BLACK, root_color=Color.BLACK,
        )
        assert abs(score + _CONTEMPT) < 1e-4

    def test_repetition_returns_negative_contempt(self):
        """When the path already visited the current hash, the
        repetition branch returns the contempt-biased draw score."""
        from draughts.game.ai import _zobrist_hash

        b = Board(empty=True)
        b.place_piece(0, 0, BLACK)
        b.place_piece(3, 3, BLACK)
        b.place_piece(4, 4, WHITE)
        b.place_piece(7, 7, WHITE)
        h = _zobrist_hash(b.grid, Color.BLACK)
        score = _alphabeta(
            b, depth=3, alpha=-1000, beta=1000,
            maximizing=True, color=Color.BLACK, root_color=Color.BLACK,
            path_hashes={h},
        )
        assert abs(score + _CONTEMPT) < 1e-4


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
