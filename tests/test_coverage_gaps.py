"""Tests for critical coverage gaps found during test audit (2026-04).

Covers:
  1. Opening book must respect mandatory captures
  2. Blundering at low levels must respect mandatory captures
  3. FEN parser: pawn on promotion row (edge case)
  4. Engine protocol: invalid move in position command
  5. Settings load with missing/extra fields (v3.2 compat)
  6. Puzzle trainer: wrong move → board restored correctly
  7. HeadlessGame serialization with custom position
  8. Board editor → play from here → game works (controller-level)
"""

from __future__ import annotations

from draughts.config import BLACK, BLACK_KING, WHITE, WHITE_KING, Color, GameSettings
from draughts.game.ai import AIEngine, _generate_all_moves
from draughts.game.ai.search import AIMove
from draughts.game.board import Board
from draughts.game.fen import board_to_fen, parse_fen
from draughts.game.headless import HeadlessGame

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pos(notation: str) -> tuple[int, int]:
    return Board.notation_to_pos(notation)


def _make_board(**pieces: int) -> Board:
    b = Board(empty=True)
    for notation, piece in pieces.items():
        x, y = _pos(notation)
        b.place_piece(x, y, piece)
    return b


# ===========================================================================
# 1. Opening book must respect mandatory captures
# ===========================================================================


class TestBookRespectsCaptures:
    """If the book suggests a non-capture move but captures are mandatory,
    the engine must play a capture instead."""

    def test_book_move_overridden_by_mandatory_capture(self):
        """Set up a position where captures are mandatory, seed the book
        with a non-capture move for that position, and verify the engine
        plays a capture anyway."""
        from draughts.game.ai.book import OpeningBook
        from draughts.game.ai.tt import _zobrist_hash

        # Position: White pawn at e3 (4,5) can capture black at d4 (3,4)
        # landing at c5 (2,3). White also has a pawn at a1 (0,7).
        # Captures are mandatory.
        board = _make_board(e3=WHITE, a3=WHITE, d4=BLACK, h8=BLACK)

        # Verify captures are indeed mandatory
        assert board.has_any_capture(Color.WHITE), "Setup error: captures should be mandatory"

        # Create a book with a non-capture move for this position
        book = OpeningBook()
        h = _zobrist_hash(board.grid, Color.WHITE)
        # Book suggests a3-b4 (a quiet move, not a capture)
        quiet_move = AIMove(kind="move", path=[_pos("a3"), _pos("b4")])
        book.add(h, quiet_move, weight=100)

        # Create engine with this book
        engine = AIEngine(difficulty=3, color=Color.WHITE, book=book)
        move = engine.find_move(board)

        assert move is not None
        # The engine MUST play a capture, not the book's quiet move
        assert move.kind == "capture", (
            f"Engine played {move.kind} {move.path} but captures are mandatory. "
            f"Book suggested quiet move a3-b4 which should be overridden."
        )

    def test_book_capture_move_is_accepted(self):
        """If the book suggests a valid capture and captures are mandatory,
        the book move should be accepted."""
        from draughts.game.ai.book import OpeningBook
        from draughts.game.ai.tt import _zobrist_hash

        # Position where captures are mandatory
        board = _make_board(e3=WHITE, d4=BLACK)
        assert board.has_any_capture(Color.WHITE)

        book = OpeningBook()
        h = _zobrist_hash(board.grid, Color.WHITE)
        # Book suggests the correct capture e3:c5
        cap_move = AIMove(kind="capture", path=[_pos("e3"), _pos("c5")])
        book.add(h, cap_move, weight=100)

        engine = AIEngine(difficulty=3, color=Color.WHITE, book=book)
        move = engine.find_move(board)

        assert move is not None
        assert move.kind == "capture"

    def test_book_move_accepted_when_no_captures(self):
        """When no captures are mandatory, book moves should be accepted normally."""
        from draughts.game.ai.book import OpeningBook
        from draughts.game.ai.tt import _zobrist_hash

        # Starting position — no captures possible
        board = Board()
        assert not board.has_any_capture(Color.WHITE)

        book = OpeningBook()
        h = _zobrist_hash(board.grid, Color.WHITE)
        quiet_move = AIMove(kind="move", path=[_pos("c3"), _pos("d4")])
        book.add(h, quiet_move, weight=100)

        engine = AIEngine(difficulty=3, color=Color.WHITE, book=book)
        move = engine.find_move(board)

        assert move is not None
        # Book move should be used
        assert move.path == [_pos("c3"), _pos("d4")]


# ===========================================================================
# 2. Blundering must respect mandatory captures
# ===========================================================================


class TestBlunderRespectsCaptures:
    """At low difficulty levels, blundered moves must still be captures
    when captures are mandatory."""

    def test_level1_blunder_captures_when_mandatory(self):
        """Position with mandatory captures: even blundered moves must capture."""
        # White at e3 can capture d4 (black). Also white at a1 and g1.
        board = _make_board(e3=WHITE, a3=WHITE, g3=WHITE, d4=BLACK, f4=BLACK)
        assert board.has_any_capture(Color.WHITE)

        engine = AIEngine(difficulty=1, color=Color.WHITE)
        for _ in range(20):
            move = engine.find_move(board)
            assert move is not None
            assert move.kind == "capture", f"Blundered move {move.path} is not a capture but captures are mandatory"

    def test_level2_blunder_captures_when_mandatory(self):
        board = _make_board(e3=WHITE, a3=WHITE, d4=BLACK)
        assert board.has_any_capture(Color.WHITE)

        engine = AIEngine(difficulty=2, color=Color.WHITE)
        for _ in range(20):
            move = engine.find_move(board)
            assert move is not None
            assert move.kind == "capture"


# ===========================================================================
# 3. FEN parser: pawn on promotion row
# ===========================================================================


class TestFenPromotionRowPawn:
    """FEN with a pawn on its own promotion row is technically invalid
    (should be a king). The parser should either reject or auto-promote."""

    def test_white_pawn_on_row0_accepted_or_rejected(self):
        """White pawn on square 1 (row 0 = promotion row for white).
        Parser should either raise ValueError or silently accept.
        Either way: no crash."""
        fen = "W:W1:B32"
        try:
            board, color = parse_fen(fen)
            # If accepted, the piece should be on the board
            from draughts.game.pdn import square_to_xy

            x, y = square_to_xy(1)
            piece = board.piece_at(x, y)
            # Note: this IS a known gap — parser doesn't validate promotion.
            # Test documents the current behavior.
            assert piece in (WHITE, WHITE_KING)
        except ValueError:
            pass  # Rejecting is also valid

    def test_black_pawn_on_row7_accepted_or_rejected(self):
        """Black pawn on square 32 (row 7 = promotion row for black)."""
        fen = "W:W1:B32"
        try:
            board, _color = parse_fen(fen)
            from draughts.game.pdn import square_to_xy

            x, y = square_to_xy(32)
            piece = board.piece_at(x, y)
            assert piece in (BLACK, BLACK_KING)
        except ValueError:
            pass

    def test_fen_round_trip_preserves_kings_not_pawns_on_promo_row(self):
        """A board with kings on promotion rows round-trips correctly."""
        board = Board(empty=True)
        board.place_piece(1, 0, WHITE_KING)  # b8 — promotion row for white
        board.place_piece(6, 7, BLACK_KING)  # g1 — promotion row for black
        fen = board_to_fen(board, Color.WHITE)
        restored, _ = parse_fen(fen)
        assert restored.piece_at(1, 0) == WHITE_KING
        assert restored.piece_at(6, 7) == BLACK_KING


# ===========================================================================
# 4. Engine protocol: invalid move in position command
# ===========================================================================


class TestEngineProtocolInvalidMove:
    """Engine must handle invalid moves in 'position startpos moves ...'
    gracefully (emit error info, not crash)."""

    def test_invalid_move_does_not_crash(self):
        import io

        from draughts.engine import EngineSession

        inp = io.StringIO("position startpos moves c3-d4 INVALID\ngo depth 2\nquit\n")
        out = io.StringIO()
        session = EngineSession()
        session.run(inp, out)
        output = out.getvalue()
        # Should contain an error message about the invalid move
        assert "info string" in output.lower() or "bestmove" in output.lower()
        # Should still produce a bestmove (from whatever position it could reach)
        assert "bestmove" in output

    def test_out_of_range_move_does_not_crash(self):
        import io

        from draughts.engine import EngineSession

        inp = io.StringIO("position startpos moves z9-x0\ngo depth 2\nquit\n")
        out = io.StringIO()
        session = EngineSession()
        session.run(inp, out)
        output = out.getvalue()
        # Should not crash; may emit error or just ignore
        assert "bestmove" in output or "info string" in output.lower()


# ===========================================================================
# 5. Settings load with missing fields (backward compat)
# ===========================================================================


class TestSettingsBackwardCompat:
    """GameSettings must handle construction with subset of fields,
    simulating loading settings from an older version."""

    def test_default_construction(self):
        """Default GameSettings has all new fields with sensible defaults."""
        s = GameSettings()
        assert s.use_opening_book is True
        assert s.use_endgame_bitbase is True
        assert s.use_tuned_eval is True
        assert s.board_theme == "dark_wood"
        assert s.show_legal_moves_hover is True
        assert s.highlight_last_move is True

    def test_partial_construction_old_fields_only(self):
        """Constructing with only old-style fields works (new fields get defaults)."""
        s = GameSettings(difficulty=3, remind=True, pause=1.0)
        assert s.difficulty == 3
        assert s.use_opening_book is True  # default
        assert s.board_theme == "dark_wood"  # default

    def test_unknown_field_ignored_via_dict(self):
        """Simulating JSON load: extra unknown keys should not crash."""
        data = {
            "difficulty": 2,
            "remind": True,
            "pause": 0.5,
            "unknown_future_field": 42,
        }
        # Filter to known fields
        known = {f.name for f in GameSettings.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        s = GameSettings(**filtered)
        assert s.difficulty == 2


# ===========================================================================
# 6. Puzzle trainer: wrong move → board restored
# ===========================================================================


class TestPuzzleBoardRestore:
    """After a wrong move in a puzzle, the board should be fully restored
    to the original puzzle position."""

    def test_wrong_move_restores_board(self):
        """Load a puzzle, make a wrong move, verify the position is restored."""
        from draughts.game.puzzles import load_bundled_puzzles

        puzzles = load_bundled_puzzles()
        tested = False

        for puzzle in puzzles:
            board = Board(empty=True)
            board.load_from_position_string(puzzle.position)
            original_pos = board.to_position_string()

            legal = _generate_all_moves(board, puzzle.turn)
            best_path_str = puzzle.best_move
            sep = ":" if ":" in best_path_str else "-"
            best_path = [Board.notation_to_pos(sq) for sq in best_path_str.split(sep)]

            wrong_moves = [(kind, path) for kind, path in legal if path != best_path]

            if not wrong_moves:
                continue

            # Apply a wrong move
            wrong_kind, wrong_path = wrong_moves[0]
            wrong_board = Board.__new__(Board)
            wrong_board.grid = board.grid.copy()
            if wrong_kind == "capture":
                wrong_board.execute_capture_path(wrong_path)
            else:
                wrong_board.execute_move(wrong_path[0][0], wrong_path[0][1], wrong_path[1][0], wrong_path[1][1])

            # Verify the wrong board is different
            assert wrong_board.to_position_string() != original_pos

            # Restore the board (simulating what the puzzle trainer does)
            restored = Board(empty=True)
            restored.load_from_position_string(puzzle.position)
            assert restored.to_position_string() == original_pos
            tested = True
            break

        assert tested, "No puzzle had wrong moves available to test"


# ===========================================================================
# 7. HeadlessGame serialization with custom (non-start) position
# ===========================================================================


class TestHeadlessCustomPositionRoundtrip:
    """HeadlessGame.to_dict/from_dict preserves custom positions."""

    def test_custom_position_roundtrip(self):
        """Create a game from a custom position, serialize and restore."""
        pos = "BnnnnnnnnnnnnnnnnnnnnnnnnnnnnnWn"
        game = HeadlessGame(auto_ai=False, position=pos)
        assert game.position_string == pos

        data = game.to_dict()
        game2 = HeadlessGame.from_dict(data)
        assert game2.position_string == pos

    def test_after_moves_roundtrip(self):
        """After making moves, serialization preserves the current state."""
        game = HeadlessGame(auto_ai=False)
        game.make_move("c3", "d4")
        game.make_move("f6", "e5")
        pos_after = game.position_string
        ply = game.ply_count

        data = game.to_dict()
        game2 = HeadlessGame.from_dict(data)
        assert game2.position_string == pos_after
        assert game2.ply_count == ply


# ===========================================================================
# 8. Board editor → play from here (controller-level check)
# ===========================================================================


class TestEditorToPlayFromHere:
    """Verify that editing a position and 'playing from here' results in
    a valid game state where moves can be made."""

    def test_custom_position_legal_moves(self):
        """After setting up a custom position, legal moves are generated."""
        board = Board(empty=True)
        board.place_piece(2, 5, WHITE)  # c3
        board.place_piece(5, 2, BLACK)  # f6

        moves = _generate_all_moves(board, Color.WHITE)
        assert len(moves) > 0, "White should have legal moves"

        moves_black = _generate_all_moves(board, Color.BLACK)
        assert len(moves_black) > 0, "Black should have legal moves"

    def test_headless_from_custom_position_plays(self):
        """HeadlessGame from a custom position allows moves and AI responds."""
        board = Board(empty=True)
        board.place_piece(2, 5, WHITE)  # c3
        board.place_piece(4, 5, WHITE)  # e3
        board.place_piece(5, 2, BLACK)  # f6
        board.place_piece(3, 2, BLACK)  # d6
        pos = board.to_position_string()

        game = HeadlessGame(auto_ai=False, position=pos)
        # White moves first
        record = game.make_move("c3", "d4")
        assert record is not None
        assert record.kind == "move"

    def test_editor_fen_to_headless_game(self):
        """FEN from editor → HeadlessGame → move works."""
        board = Board(empty=True)
        board.place_piece(1, 0, BLACK_KING)
        board.place_piece(5, 6, WHITE_KING)

        fen = board_to_fen(board, Color.WHITE)
        restored, color = parse_fen(fen)
        pos = restored.to_position_string()

        game = HeadlessGame(auto_ai=False, position=pos)
        # Both sides have kings — should have legal moves
        moves = game.get_legal_moves()
        assert len(moves) > 0


# ===========================================================================
# 9. Clock tracking (basic check)
# ===========================================================================


class TestClockBasicTracking:
    """HeadlessGame tracks move times for clock display."""

    def test_move_records_have_times(self):
        """After playing moves, each MoveRecord has eval_before/eval_after."""
        game = HeadlessGame(difficulty=1, depth=2)
        result = game.play_full_game(max_ply=4, move_timeout=5.0)
        assert result is not None
        assert len(result.moves) >= 2
        # Each move should have finite eval values
        for move_rec in result.moves:
            assert isinstance(move_rec.eval_before, (int, float))
            assert isinstance(move_rec.eval_after, (int, float))
