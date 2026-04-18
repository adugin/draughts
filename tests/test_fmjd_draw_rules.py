"""FMJD draw-rule invariants — the auditor flagged these as GAPS.

The existing suite confirms that ``check_game_over`` returns certain
reason strings, but no test FORCES those rules to fire from a
constructed scenario. If a refactor of the counter updates drops the
check (or if the threshold constants drift), all existing tests stay
green but live games would silently fail to terminate.

Coverage added here:
- 3-fold repetition detection fires when a position count hits 3.
- 3-fold: at count 2, game continues (off-by-one guard).
- 15-move kings-only rule fires at exactly 30 half-moves (FMJD).
- 30-move no-progress rule fires at exactly 60 half-moves (FMJD).
- 1K vs 1K — the only unconditional kings-only draw.
- 2K vs 1K — game CONTINUES (not auto-draw); 15-move rule applies.
- Rules do NOT fire prematurely in the presence of pawns.
"""

from __future__ import annotations

from draughts.config import BLACK, BLACK_KING, Color, WHITE, WHITE_KING
from draughts.game.board import Board


def _lone_kings_board() -> Board:
    b = Board(empty=True)
    b.grid[2, 1] = WHITE_KING   # b6
    b.grid[5, 2] = BLACK_KING   # c3
    return b


# ---------------------------------------------------------------------------
# 3-fold repetition
# ---------------------------------------------------------------------------


def test_threefold_repetition_fires_at_count_3():
    b = _lone_kings_board()
    pos = b.to_position_string()
    result = b.check_game_over(position_counts={pos: 3})
    # 1K vs 1K is also an auto-draw; repetition check runs first and wins
    # the race, but either reason is acceptable semantically.
    assert result is not None
    winner, reason = result
    assert winner is None
    assert reason in ("draw_repetition", "draw_endgame")


def test_threefold_does_not_fire_with_pawns_at_count_2():
    """At count=2 game must continue regardless of pawns."""
    b = Board()  # full starting position — lots of pawns, no Petrov rule
    pos = b.to_position_string()
    assert b.check_game_over(position_counts={pos: 2}) is None


def test_threefold_fires_with_pawns_at_count_3():
    """With pawns on board, only 3-fold (not Petrov) can draw."""
    b = Board()
    pos = b.to_position_string()
    result = b.check_game_over(position_counts={pos: 3})
    assert result is not None
    assert result == (None, "draw_repetition")


# ---------------------------------------------------------------------------
# 15-move kings-only rule (FMJD: 30 half-moves)
# ---------------------------------------------------------------------------


def test_kings_only_rule_fires_at_30_half_moves():
    b = _lone_kings_board()
    # Without the Petrov shortcut (board must NOT be 1K-vs-1K), add a 3rd king.
    b.grid[0, 3] = BLACK_KING   # d8 — now 2BK vs 1WK
    # But 2K vs 1K is a Petrov draw; add a 4th king to escape Petrov.
    b.grid[7, 0] = WHITE_KING   # a1
    # Now 2K vs 2K — not in the Petrov list.
    result = b.check_game_over(kings_only_plies=30)
    assert result is not None
    winner, reason = result
    assert winner is None
    assert reason == "draw_kings_only"


def test_kings_only_rule_does_not_fire_at_29_half_moves():
    b = _lone_kings_board()
    b.grid[0, 3] = BLACK_KING
    b.grid[7, 0] = WHITE_KING
    # 2K vs 2K, kings_only_plies=29 — still playing.
    assert b.check_game_over(kings_only_plies=29) is None


def test_kings_only_rule_does_not_fire_with_pawns():
    """Pawns on board → kings-only counter is irrelevant, game continues."""
    b = Board()  # starting position with all pawns
    # Even if we (incorrectly) pass high kings_only_plies, should still play.
    assert b.check_game_over(kings_only_plies=100) is None


# ---------------------------------------------------------------------------
# 30-move no-progress rule (FMJD: 60 half-moves)
# ---------------------------------------------------------------------------


def test_no_progress_rule_fires_at_60_half_moves():
    b = _lone_kings_board()
    b.grid[0, 3] = BLACK_KING
    b.grid[7, 0] = WHITE_KING
    # Ensure kings_only_plies < 30 so we exercise the no_progress branch.
    result = b.check_game_over(kings_only_plies=0, quiet_plies=60)
    assert result is not None
    winner, reason = result
    assert winner is None
    assert reason == "draw_no_progress"


def test_no_progress_rule_does_not_fire_at_59_half_moves():
    b = _lone_kings_board()
    b.grid[0, 3] = BLACK_KING
    b.grid[7, 0] = WHITE_KING
    assert b.check_game_over(kings_only_plies=0, quiet_plies=59) is None


# ---------------------------------------------------------------------------
# Kings-only draw boundaries — per FMJD, only 1K vs 1K is unconditional.
# ---------------------------------------------------------------------------


def test_one_king_vs_one_king_is_auto_draw():
    """1K vs 1K — dead position, no mating material (immediate draw)."""
    b = _lone_kings_board()
    result = b.check_game_over()
    assert result == (None, "draw_endgame")


def test_two_kings_vs_one_king_game_continues():
    """2K vs 1K — NOT auto-draw per FMJD.

    2K vs 1K is usually drawn with correct defence but winnable in
    tactical positions (forks, zugzwang). The rules force a draw via
    the 15-move kings-only rule, not by material count — so the game
    continues until that counter fires.
    """
    b = Board(empty=True)
    b.grid[0, 1] = BLACK_KING   # b8
    b.grid[0, 3] = BLACK_KING   # d8
    b.grid[7, 0] = WHITE_KING   # a1
    assert b.check_game_over() is None
    # After 30 plies of kings-only play, the 15-move rule draws it.
    assert b.check_game_over(kings_only_plies=30) == (None, "draw_kings_only")


def test_one_king_vs_two_kings_game_continues():
    """Mirror of 2K vs 1K — same non-auto-draw rule."""
    b = Board(empty=True)
    b.grid[2, 1] = BLACK_KING
    b.grid[7, 0] = WHITE_KING
    b.grid[7, 2] = WHITE_KING
    assert b.check_game_over() is None
    assert b.check_game_over(kings_only_plies=30) == (None, "draw_kings_only")


def test_three_kings_vs_one_king_game_continues():
    """3K vs 1K must be winnable until the 15-move counter fires."""
    b = Board(empty=True)
    b.grid[0, 1] = BLACK_KING
    b.grid[0, 3] = BLACK_KING
    b.grid[2, 1] = BLACK_KING
    b.grid[7, 0] = WHITE_KING
    assert b.check_game_over() is None
    assert b.check_game_over(kings_only_plies=30) == (None, "draw_kings_only")
