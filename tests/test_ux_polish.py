"""UX-polish tests — real Board operations and shipped setting defaults.

Old version of this file had 20+ tests against a `_FakeBoardWidget`
class written for the test — i.e. it tested the stub, not production
code. The audit flagged the whole pattern (Smell B + C). Rewritten to
keep only the meaningful checks:

- Real Board methods (get_valid_moves, get_captures) behave sensibly.
- Shipped GameSettings defaults are what we promised end-users.
"""

from __future__ import annotations

from draughts.config import GameSettings
from draughts.game.board import Board


class TestRealBoardLegalMoves:
    """Exercise Board.get_valid_moves / get_captures on real positions."""

    def test_white_start_position_has_moves(self):
        moves = Board().get_valid_moves(2, 5)  # f3 — white pawn at start
        assert len(moves) > 0

    def test_empty_square_has_no_moves(self):
        assert Board().get_valid_moves(0, 0) == []

    def test_simple_capture_is_generated(self):
        b = Board(empty=True)
        b.place_piece(2, 4, int(b.WHITE))
        b.place_piece(3, 3, int(b.BLACK))
        caps = b.get_captures(2, 4)
        assert caps and all(len(p) >= 2 and isinstance(p, list) for p in caps)


def test_shipped_ui_defaults_match_contract():
    """Regression guard for user-facing defaults: any change is intentional."""
    s = GameSettings()
    assert s.highlight_last_move is True
    assert s.show_coordinates is True
    assert s.show_legal_moves_hover is True
    assert s.remind is True
