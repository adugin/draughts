"""GameController._hint_qualifier — textual labels for hint messages.

ROADMAP #32 asked for a "textual reason" on top of the PV line. The
implementation is intentionally conservative: only labels that can be
derived unambiguously from the move geometry are produced. Labels like
"жертва" or "позиционное давление" would need a multi-ply tactical
re-search and risk being confidently wrong — opted out.

The labels that ARE produced:
    * "N взятие/взятия/взятий" for multi-captures (≥ 2 pieces taken),
      with Russian plural agreement (2-4 → взятия, else взятий/взятие).
    * "в дамки!" when a non-king piece lands on the promote row.
"""

from __future__ import annotations

import pytest


class _StubMove:
    """Minimal AIMove-like duck: only .kind and .path are needed."""

    def __init__(self, kind: str, path: list[tuple[int, int]]) -> None:
        self.kind = kind
        self.path = path


def _make_controller(board) -> object:
    """Build a GameController with its board swapped for ``board``.

    We avoid the full constructor (which sets up timers, signals, the
    audio engine, etc.) by instantiating through the normal path, then
    replacing the board. The qualifier is pure over (board, move) so
    this is enough.
    """
    from draughts.app.controller import GameController

    c = GameController()
    c.board = board
    return c


@pytest.fixture
def empty_board():
    from draughts.game.board import Board

    return Board(empty=True)


# ---------------------------------------------------------------------------
# Multi-capture labels
# ---------------------------------------------------------------------------


class TestCaptureQualifier:
    def test_single_capture_has_no_qualifier(self, empty_board):
        """Single-piece capture is obvious from notation (:) — no qualifier."""
        from draughts.config import WHITE, BLACK
        empty_board.grid[5, 2] = WHITE
        empty_board.grid[4, 3] = BLACK
        c = _make_controller(empty_board)
        # c3 × e5 — single jump, path length = 2.
        mv = _StubMove("capture", [(2, 5), (4, 3)])
        assert c._hint_qualifier(mv) == ""

    def test_two_captures(self, empty_board):
        c = _make_controller(empty_board)
        # Path = 3 points → 2 jumps.
        mv = _StubMove("capture", [(2, 5), (4, 3), (6, 1)])
        assert c._hint_qualifier(mv) == "2 взятия"

    def test_three_captures_plural(self, empty_board):
        c = _make_controller(empty_board)
        mv = _StubMove("capture", [(0, 0), (2, 2), (4, 4), (6, 6)])
        assert c._hint_qualifier(mv) == "3 взятия"

    def test_four_captures_plural(self, empty_board):
        c = _make_controller(empty_board)
        mv = _StubMove("capture", [(0, 0), (2, 2), (4, 4), (6, 6), (7, 7)])
        assert c._hint_qualifier(mv) == "4 взятия"

    def test_five_captures_genitive(self, empty_board):
        """5+ takes the "взятий" form (genitive plural)."""
        c = _make_controller(empty_board)
        path = [(0, 0), (2, 2), (4, 4), (6, 6), (4, 6), (2, 4)]
        mv = _StubMove("capture", path)
        assert c._hint_qualifier(mv) == "5 взятий"


# ---------------------------------------------------------------------------
# Promotion labels
# ---------------------------------------------------------------------------


class TestPromotionQualifier:
    def test_white_pawn_promotion_on_row_0(self, empty_board):
        """White pawn on row 1 → move to row 0 is a promotion."""
        from draughts.config import WHITE

        empty_board.grid[1, 2] = WHITE   # c7
        c = _make_controller(empty_board)
        # c7-b8 (x, y): (2, 1) → (1, 0)
        mv = _StubMove("move", [(2, 1), (1, 0)])
        assert c._hint_qualifier(mv) == "в дамки!"

    def test_black_pawn_promotion_on_row_7(self, empty_board):
        """Black pawn on row 6 → move to row 7 is a promotion."""
        from draughts.config import BLACK

        empty_board.grid[6, 3] = BLACK   # d2
        c = _make_controller(empty_board)
        mv = _StubMove("move", [(3, 6), (2, 7)])
        assert c._hint_qualifier(mv) == "в дамки!"

    def test_non_promoting_quiet_move_has_no_qualifier(self, empty_board):
        from draughts.config import WHITE

        empty_board.grid[5, 2] = WHITE   # c3
        c = _make_controller(empty_board)
        mv = _StubMove("move", [(2, 5), (3, 4)])
        assert c._hint_qualifier(mv) == ""

    def test_king_move_not_labelled_as_promotion(self, empty_board):
        """A king already promoted — landing on back rank does NOT add a label."""
        from draughts.config import WHITE_KING

        empty_board.grid[1, 2] = WHITE_KING  # c7
        c = _make_controller(empty_board)
        mv = _StubMove("move", [(2, 1), (1, 0)])
        assert c._hint_qualifier(mv) == ""

    def test_promotion_via_capture_keeps_capture_label(self, empty_board):
        """Capture takes precedence over promotion — capture qualifier used.

        FMJD Russian rules: a pawn promoted mid-chain becomes a king and
        must continue capturing. The "N взятий" label is more useful
        than "в дамки!" for these; we already announce capture count.
        """
        from draughts.config import WHITE, BLACK

        empty_board.grid[3, 2] = WHITE   # c5
        empty_board.grid[2, 3] = BLACK   # d6
        empty_board.grid[0, 5] = BLACK   # f8
        c = _make_controller(empty_board)
        # c5 x e7 x g not legal geometrically; craft a 2-cap path that
        # lands on white's promote row (row 0).
        mv = _StubMove("capture", [(2, 3), (4, 1), (2, 0)])  # 2 jumps
        assert c._hint_qualifier(mv) == "2 взятия"
