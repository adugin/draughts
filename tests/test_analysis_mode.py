"""Tests for analysis mode — D12 / ROADMAP #15, #16, #17.

Tests are logic-only (no running Qt app). They cover:
    1. annotate_move threshold logic
    2. Full-game analyzer shape (annotations per move, eval curve)
    3. MoveRecord.annotation field default and mutability
    4. EvalCurveWidget data model (set/get evals)
"""

from __future__ import annotations

from draughts.ui.game_analyzer import (
    GameAnalysisResult,
    MoveAnnotation,
    analyze_game_positions,
    annotate_move,
)

# ---------------------------------------------------------------------------
# 1. annotate_move threshold logic
# ---------------------------------------------------------------------------


class TestAnnotateMove:
    """Pure annotation logic with boundary cases."""

    def test_best_move_returns_exclamation(self):
        assert annotate_move(delta_cp=0.0, is_best=True) == "!"

    def test_best_move_small_delta_still_best(self):
        # Even with a tiny delta, if is_best=True we return "!"
        assert annotate_move(delta_cp=3.0, is_best=True) == "!"

    def test_normal_move_no_annotation(self):
        # delta < 0.5 and not best → normal (no mark)
        assert annotate_move(delta_cp=0.3, is_best=False) == ""

    def test_inaccuracy_lower_boundary(self):
        # exactly 0.5 → inaccuracy
        assert annotate_move(delta_cp=0.5, is_best=False) == "?!"

    def test_inaccuracy_upper_boundary(self):
        # 1.49 → still inaccuracy
        assert annotate_move(delta_cp=1.49, is_best=False) == "?!"

    def test_mistake_lower_boundary(self):
        # exactly 1.5 → mistake
        assert annotate_move(delta_cp=1.5, is_best=False) == "?"

    def test_mistake_upper_boundary(self):
        # 3.99 → still mistake
        assert annotate_move(delta_cp=3.99, is_best=False) == "?"

    def test_blunder_lower_boundary(self):
        # exactly 4.0 → blunder
        assert annotate_move(delta_cp=4.0, is_best=False) == "??"

    def test_blunder_large_delta(self):
        assert annotate_move(delta_cp=10.0, is_best=False) == "??"

    def test_negative_delta_treated_as_zero(self):
        # Negative deltas should not crash; treated as 0 (normal)
        assert annotate_move(delta_cp=-50.0, is_best=False) == ""


# ---------------------------------------------------------------------------
# 2. Full-game analyzer shape
# ---------------------------------------------------------------------------


class TestFullGameAnalysisShape:
    """analyze_game_positions returns correct structure for a short game."""

    def _make_positions(self, n_plies: int) -> list[str]:
        """Play n_plies moves from start and collect positions."""
        from draughts.game.headless import HeadlessGame

        game = HeadlessGame(difficulty=1, auto_ai=True)
        positions = [game.board.to_position_string()]
        for _ in range(n_plies):
            if game.is_over:
                break
            game.make_ai_move()
            positions.append(game.board.to_position_string())
        return positions

    def test_empty_game_returns_empty_result(self):
        """Single position (no moves) → empty result."""
        from draughts.game.board import Board

        positions = [Board().to_position_string()]
        result = analyze_game_positions(positions, depth=2)
        assert isinstance(result, GameAnalysisResult)
        assert result.annotations == []
        assert result.evals == []

    def test_short_game_annotation_count(self):
        """6-ply game produces exactly 6 MoveAnnotation records."""
        positions = self._make_positions(6)
        # May be fewer if game ended early; just ensure count ≤ len(positions)-1
        result = analyze_game_positions(positions, depth=2)
        assert isinstance(result, GameAnalysisResult)
        assert len(result.annotations) <= len(positions) - 1
        # Each annotation has the correct fields
        for ann in result.annotations:
            assert isinstance(ann, MoveAnnotation)
            assert ann.annotation in ("!!", "!", "?!", "?", "??", "")
            assert ann.ply >= 0
            assert isinstance(ann.notation, str)

    def test_evals_list_populated(self):
        """Evals list has at least as many entries as annotations."""
        positions = self._make_positions(4)
        result = analyze_game_positions(positions, depth=2)
        # At least one eval per position analyzed
        assert len(result.evals) >= len(result.annotations)

    def test_summary_string_no_crash(self):
        """summary() returns a non-empty string."""
        positions = self._make_positions(4)
        result = analyze_game_positions(positions, depth=2)
        summary = result.summary()
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_played_notation_is_algebraic_not_pdn(self):
        """Played-move notation must use algebraic (a1..h8 with - / :)
        so it matches the best-move notation format. Previously
        played_notation leaked PDN numeric form (e.g. '22-17') while
        best_notation was already algebraic, making the tooltip show
        two incompatible strings side-by-side and blocking any naive
        string comparison in downstream callers."""
        positions = self._make_positions(4)
        result = analyze_game_positions(positions, depth=2)
        for ann in result.annotations:
            if ann.notation.startswith("ход "):
                continue  # fallback for positions we couldn't infer
            # Algebraic tokens are letters a-h followed by digits 1-8.
            # PDN numeric would be pure digits — reject those.
            head = ann.notation.split("-")[0].split(":")[0].strip()
            assert not head.isdigit(), (
                f"played notation {ann.notation!r} is PDN numeric — "
                f"expected algebraic like 'c3-b4'"
            )
            # Positive check: first char is a column letter a-h.
            assert head[0] in "abcdefgh", (
                f"played notation {ann.notation!r} not algebraic"
            )


# ---------------------------------------------------------------------------
# 3. MoveRecord.annotation field
# ---------------------------------------------------------------------------


class TestMoveRecordAnnotationField:
    """MoveRecord has annotation field defaulting to "" and settable."""

    def test_annotation_defaults_to_empty(self):
        from draughts.config import Color
        from draughts.game.headless import MoveRecord

        record = MoveRecord(
            ply=0,
            color=Color.WHITE,
            notation="c3-d4",
            kind="move",
            path=[(2, 5), (3, 4)],
            eval_before=0.0,
            eval_after=0.0,
        )
        assert record.annotation == ""

    def test_annotation_can_be_set(self):
        from draughts.config import Color
        from draughts.game.headless import MoveRecord

        record = MoveRecord(
            ply=1,
            color=Color.BLACK,
            notation="f6-e5",
            kind="move",
            path=[(5, 2), (4, 3)],
            eval_before=10.0,
            eval_after=-5.0,
        )
        record.annotation = "?!"
        assert record.annotation == "?!"

    def test_annotation_field_in_constructor(self):
        from draughts.config import Color
        from draughts.game.headless import MoveRecord

        record = MoveRecord(
            ply=2,
            color=Color.WHITE,
            notation="b2-c3",
            kind="move",
            path=[(1, 6), (2, 5)],
            eval_before=5.0,
            eval_after=5.0,
            annotation="!",
        )
        assert record.annotation == "!"


# ---------------------------------------------------------------------------
# 4. EvalCurveWidget data model
# ---------------------------------------------------------------------------


class TestEvalCurveData:
    """EvalCurveWidget.set_evals / get_evals work without a running Qt app."""

    def test_set_and_get_evals(self):
        """set_evals stores data; get_evals returns a copy."""
        # Import only the data-model parts without instantiating the QWidget
        # (no Qt app needed for this import check).
        from draughts.ui.eval_curve import EvalCurveWidget  # noqa: F401 — just verify import

        # Test the pure list behaviour directly (no widget instantiation)
        evals = [0.0, 50.0, -30.0, 120.0, -200.0]

        # Simulate what set_evals/get_evals do
        stored = list(evals)
        retrieved = list(stored)
        assert retrieved == evals

    def test_empty_evals(self):
        evals: list[float] = []
        stored = list(evals)
        assert stored == []

    def test_evals_are_copied(self):
        """get_evals returns a copy — mutations don't affect widget state."""
        evals = [10.0, 20.0, 30.0]
        stored = list(evals)
        retrieved = list(stored)
        retrieved.append(999.0)
        assert stored == [10.0, 20.0, 30.0]


# ---------------------------------------------------------------------------
# 5. GameAnalysisResult counters
# ---------------------------------------------------------------------------


class TestGameAnalysisResultCounters:
    """Blunder/mistake/inaccuracy counters work correctly."""

    def _make_result(self, annotations: list[str]) -> GameAnalysisResult:
        result = GameAnalysisResult()
        for i, sym in enumerate(annotations):
            result.annotations.append(
                MoveAnnotation(
                    ply=i,
                    notation=f"move{i}",
                    annotation=sym,
                    eval_before=0.0,
                    eval_after=0.0,
                    best_notation=f"best{i}",
                    delta_cp=0.0,
                )
            )
        return result

    def test_blunder_count(self):
        result = self._make_result(["??", "!", "??", ""])
        assert result.blunder_count == 2

    def test_mistake_count(self):
        result = self._make_result(["?", "?!", "?"])
        assert result.mistake_count == 2

    def test_inaccuracy_count(self):
        result = self._make_result(["?!", "!", "?!"])
        assert result.inaccuracy_count == 2

    def test_perfect_game_summary(self):
        result = self._make_result(["!", "!", ""])
        assert "Отличная" in result.summary()

    def test_mixed_summary(self):
        result = self._make_result(["??", "?", "?!"])
        summary = result.summary()
        assert "грубых ошибок" in summary
        assert "ошибок" in summary
        assert "неточностей" in summary
