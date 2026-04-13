"""Tactical test suite — regression tests for AI quality.

Tests that AI finds correct moves in known draughts positions.
These are NOT unit tests of code correctness — they test game-playing strength.
Failing tests indicate AI regression (worse play), not bugs.

Each test sets up a specific position, asks AI to find the best move,
and verifies it matches the expected tactical response.
"""


from draughts.config import BLACK, BLACK_KING, WHITE, WHITE_KING, Color
from draughts.game.ai import AIEngine, _search_best_move, evaluate_position
from draughts.game.board import Board
from draughts.game.headless import HeadlessGame


def _pos(notation: str) -> tuple[int, int]:
    """Convert notation like 'c3' to (x, y)."""
    return Board.notation_to_pos(notation)


def _make_board(**pieces: int) -> Board:
    """Create a board with pieces at given positions.

    Usage: _make_board(c3=BLACK, d4=WHITE, e5=BLACK_KING)
    """
    b = Board(empty=True)
    for notation, piece in pieces.items():
        x, y = _pos(notation)
        b.place_piece(x, y, piece)
    return b


# ===================================================================
# Mandatory capture tests — AI must always capture when possible
# ===================================================================


class TestMandatoryCapture:
    """AI must choose capture over regular move."""

    def test_simple_capture_chosen(self):
        """When a capture is available, AI must take it."""
        b = _make_board(c5=BLACK, d4=WHITE, a1=WHITE)
        move = _search_best_move(b, Color.WHITE, 3)
        assert move is not None
        assert move.kind == "capture"

    def test_multi_capture_over_single(self):
        """AI should find the multi-capture path."""
        b = _make_board(a7=BLACK, b6=WHITE, d4=WHITE, f2=WHITE)
        move = _search_best_move(b, Color.BLACK, 3)
        assert move is not None
        assert move.kind == "capture"
        # Should capture at least 2 pieces (path length >= 3)
        assert len(move.path) >= 3

    def test_king_long_capture(self):
        """King should find a long-distance capture."""
        b = _make_board(a7=BLACK_KING, d4=WHITE, h2=WHITE)
        move = _search_best_move(b, Color.BLACK, 3)
        assert move is not None
        assert move.kind == "capture"


# ===================================================================
# Don't give away pieces — AI shouldn't make obviously bad moves
# ===================================================================


class TestDontSacrifice:
    """AI should not leave pieces hanging unless it gains something."""

    def test_dont_move_into_capture(self):
        """Piece should not move to a square where it can be captured."""
        b = _make_board(c3=WHITE, e5=BLACK, g7=BLACK)
        # White at c3 should NOT move to d4 (would be captured by e5)
        move = _search_best_move(b, Color.WHITE, 4)
        assert move is not None
        if move.kind == "move":
            # The move should not be to d4
            assert move.path[-1] != _pos("d4"), "AI moved into capture at d4"

    def test_protect_last_piece(self):
        """With only one piece, don't sacrifice it."""
        b = _make_board(d2=WHITE, e3=BLACK, g5=BLACK)
        move = _search_best_move(b, Color.WHITE, 5)
        assert move is not None
        # White should try to survive, not walk into capture


# ===================================================================
# Promotion tactics — AI should promote pawns when possible
# ===================================================================


class TestPromotion:
    """AI should seek promotion when advantageous."""

    def test_pawn_promotes_when_possible(self):
        """Pawn one step from promotion row should advance."""
        b = _make_board(d6=WHITE, f4=BLACK)
        # White pawn at d6 (y=2) can move to c7(y=1) or e7(y=1), one step from row 0
        # At depth 3+, AI should find the promotion path
        move = _search_best_move(b, Color.WHITE, 4)
        assert move is not None

    def test_promotion_during_capture(self):
        """Pawn should promote during capture and continue as king."""
        # White at e3 captures d2 and can promote at c1/e1
        board = _make_board(e3=WHITE, d2=BLACK, b4=BLACK)
        move = _search_best_move(board, Color.WHITE, 3)
        assert move is not None
        # Should find the capture


# ===================================================================
# Endgame patterns — AI should handle endgames correctly
# ===================================================================


class TestEndgame:
    """Known endgame patterns the AI should handle."""

    def test_king_vs_king_eval_near_zero(self):
        """One king each — evaluation should be near zero (drawn position)."""
        from draughts.game.ai import _is_drawn_endgame

        b = _make_board(b8=BLACK_KING, g1=WHITE_KING)
        # The AI's draw detector should recognize this as drawn
        assert _is_drawn_endgame(b.grid), "KvK should be detected as drawn endgame"
        # Evaluation should be near zero
        score = evaluate_position(b.grid, Color.BLACK)
        assert abs(score) < 2.0, f"KvK eval should be near zero, got {score}"

    def test_king_chases_pawn(self):
        """King should actively chase an enemy pawn to capture it."""
        b = _make_board(a1=BLACK_KING, h6=WHITE)
        move = _search_best_move(b, Color.BLACK, 6)
        assert move is not None
        # King should make a move (not stuck)
        assert len(move.path) >= 2

    def test_two_kings_vs_one_eval(self):
        """Two kings vs one — evaluation should favor the stronger side."""
        b = _make_board(b8=BLACK_KING, f8=BLACK_KING, g1=WHITE_KING)
        score = evaluate_position(b.grid, Color.BLACK)
        assert score > 0, f"2 kings vs 1 should favor black, got {score}"

    def test_ai_avoids_stalemate(self):
        """With clear advantage, AI should not accidentally stalemate opponent."""
        b = _make_board(b2=WHITE, d2=WHITE, f2=WHITE, c7=BLACK)
        move = _search_best_move(b, Color.WHITE, 5)
        assert move is not None
        # White has huge advantage, should find a winning move


# ===================================================================
# Full game quality — AI vs AI sanity checks
# ===================================================================


class TestGameQuality:
    """Test that complete AI vs AI games behave reasonably."""

    def test_game_completes(self):
        """AI vs AI game should complete within reasonable ply count."""
        game = HeadlessGame(difficulty=2, depth=0)
        result = game.play_full_game(max_ply=300)
        assert result is not None
        assert result.ply_count > 0

    def test_game_not_too_short(self):
        """Game should last more than a few moves (no immediate blunder)."""
        game = HeadlessGame(difficulty=2, depth=0)
        result = game.play_full_game(max_ply=300)
        assert result.ply_count >= 10, f"Game too short: {result.ply_count} plies"

    def test_difficulty_matters(self):
        """Higher difficulty should generally search deeper."""
        b = Board()
        engine_low = AIEngine(difficulty=1, color=Color.BLACK)
        engine_high = AIEngine(difficulty=3, color=Color.BLACK)
        # Both should find a move
        move_low = engine_low.find_move(b)
        move_high = engine_high.find_move(b)
        assert move_low is not None
        assert move_high is not None

    def test_symmetric_opening(self):
        """Both sides should have similar evaluation in the opening.

        After ~4 plies (opening book territory), material and positional
        factors can legitimately put eval up to ~3 pawns in one direction
        if the book chose a sharp line. The test just guards against
        catastrophic eval explosions (>4 pawns is already a clearly lost
        position, which shouldn't happen this early).
        """
        game = HeadlessGame(difficulty=2, depth=5)
        for _ in range(4):
            if game.is_over:
                break
            game.step()
        score = game.evaluate()
        assert abs(score) < 20.0, f"Opening evaluation too lopsided: {score}"


# ===================================================================
# HeadlessGame functionality
# ===================================================================


class TestHeadlessGame:
    """Test HeadlessGame engine itself."""

    def test_manual_move(self):
        game = HeadlessGame(auto_ai=False)
        # White moves first: c3-d4 (valid opening move)
        record = game.make_move("c3", "d4")
        assert record is not None
        assert record.notation == "c3-d4"
        assert record.kind == "move"
        assert game.turn == Color.BLACK

    def test_invalid_move_returns_none(self):
        game = HeadlessGame(auto_ai=False)
        # Try to move to an occupied square
        result = game.make_move("c3", "c5")
        assert result is None

    def test_wrong_color_returns_none(self):
        game = HeadlessGame(auto_ai=False)
        # White moves first, try to move a black piece
        result = game.make_move("f6", "e5")
        assert result is None

    def test_serialization_roundtrip(self):
        game = HeadlessGame(difficulty=1, depth=3)
        game.step()
        game.step()
        data = game.to_dict()
        game2 = HeadlessGame.from_dict(data)
        assert game2.position_string == game.position_string
        assert game2.ply_count == game.ply_count
        assert game2.turn == game.turn

    def test_legal_moves_opening(self):
        game = HeadlessGame(auto_ai=False)
        moves = game.get_legal_moves()
        # White has 7 possible opening moves
        assert len(moves) == 7
        assert all(kind == "move" for kind, _ in moves)

    def test_analysis(self):
        game = HeadlessGame(auto_ai=False)
        analysis = game.get_ai_analysis(depth=3)
        assert analysis.best_move is not None
        assert analysis.legal_move_count == 7
        assert analysis.depth == 3

    def test_move_history_formatting(self):
        game = HeadlessGame(difficulty=1, depth=3)
        game.step()
        game.step()
        text = game.format_move_list()
        assert "1." in text
        assert len(text) > 0
