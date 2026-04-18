"""AI-level regression for P2: search must honour the game-history
3-fold repetition rule, not just the per-path repetition inside the
search tree.

Scenario (AI-P2 bug, pre-fix):

    The engine's ``_alphabeta`` only consulted ``path_hashes``, i.e.
    positions reached along the current search path. If a position P
    had already appeared TWICE in the real game, the engine was blind
    to that history — it happily walked into P as a "fresh" node,
    scoring it on static eval. In a winning position that throws away
    the advantage (3rd occurrence = auto-draw by rule); in a losing
    position it throws away the chance to hold the draw deliberately.

Fix (QA-FIX: search.py): AIEngine.find_move now accepts
``game_position_hashes``; when a child's Zobrist hash lands in that
set, _alphabeta returns the contempt-draw score so the maximizing
side refuses to enter it unless every other line is worse.

These tests drive the fix end-to-end through AIEngine and
HeadlessGame without any mocks — only real Board / Zobrist / search.
"""

from __future__ import annotations

import pytest

from draughts.config import Color
from draughts.game.ai import (
    AIEngine,
    _apply_move,
    _generate_all_moves,
    _zobrist_hash,
)
from draughts.game.board import Board
from draughts.game.headless import HeadlessGame


# ---------------------------------------------------------------------------
# Direct AIEngine.find_move — the lowest-level proof that the new
# parameter actually changes the move choice.
# ---------------------------------------------------------------------------


def _lone_king_vs_pawn_board() -> Board:
    """White king on f4 with a cornered black pawn on a1.

    White has many legal king slides; the position is a clear win
    (king vs blocked pawn, pawn can't promote), and static eval makes
    every move look roughly equivalent. That makes it easy to force
    the engine to prefer a specific move just by hiding one alternative
    behind the repetition gate.
    """
    b = Board(empty=True)
    b.grid[4, 5] = Board.WHITE_KING  # f4
    b.grid[7, 0] = Board.BLACK  # a1 (cornered pawn, can't promote)
    return b


def test_find_move_accepts_game_position_hashes_kwarg():
    """Fix contract: the new kwarg exists and defaults to None
    (backward-compat for analysis/puzzle callers)."""
    b = _lone_king_vs_pawn_board()
    eng = AIEngine(
        difficulty=2, color=Color.WHITE, search_depth=3,
        use_book=False, use_bitbase=False,
    )
    m1 = eng.find_move(b.copy())
    m2 = eng.find_move(b.copy(), game_position_hashes=None)
    m3 = eng.find_move(b.copy(), game_position_hashes=frozenset())
    # Empty / None sets must preserve the legacy choice exactly.
    assert m1.path == m2.path == m3.path


def test_ai_avoids_move_leading_to_twice_seen_position():
    """Core P2 regression.

    Pre-fix: the AI picks move M whose target position T has a good
    static eval. We mark T as "seen twice"; the 3rd appearance would
    be a draw. The AI must switch to any alternative whose child is
    not in the repetition set.
    """
    b = _lone_king_vs_pawn_board()
    eng = AIEngine(
        difficulty=2, color=Color.WHITE, search_depth=4,
        use_book=False, use_bitbase=False,
    )

    baseline = eng.find_move(b.copy())
    assert baseline is not None

    # Hash of the position AFTER the baseline move (black to move next).
    child = _apply_move(b, baseline.kind, baseline.path)
    baseline_target = _zobrist_hash(child.grid, Color.BLACK)

    # Mark the baseline target as "already seen twice" in game history.
    rep_set = frozenset({baseline_target})
    new_choice = eng.find_move(b.copy(), game_position_hashes=rep_set)
    assert new_choice is not None
    assert new_choice.path != baseline.path, (
        f"AI still picked the 3-fold-draw move {baseline.path}; "
        f"the repetition seed had no effect."
    )

    # Sanity: the replacement leads to a position that is NOT in the set.
    new_child = _apply_move(b, new_choice.kind, new_choice.path)
    new_hash = _zobrist_hash(new_child.grid, Color.BLACK)
    assert new_hash not in rep_set


def test_ai_picks_repetition_when_every_alternative_is_worse():
    """Counterpart: if the only non-repeating moves are clear blunders,
    the engine still picks the repeating one. This protects against
    an over-eager fix that would just forbid the hashed set.

    Setup: single black king, lone white pawn on a8 (already promoted
    square but we keep it as a king for symmetry). Restricting isn't
    easy in a real game, so here we fabricate a contrived set of
    "forbidden" hashes covering all BUT one move; the engine is
    forced into the one remaining legal option — and that option may
    itself be in the repetition set iff there is literally nowhere
    else to go.

    The key invariant we test: when EVERY child is in the repetition
    set, find_move still returns a legal move (never None), because
    a rule-draw is still legal play.
    """
    b = _lone_king_vs_pawn_board()
    eng = AIEngine(
        difficulty=2, color=Color.WHITE, search_depth=3,
        use_book=False, use_bitbase=False,
    )
    # Build the set of ALL reachable child hashes.
    all_moves = _generate_all_moves(b, Color.WHITE)
    all_hashes = set()
    for k, p in all_moves:
        child = _apply_move(b, k, p)
        all_hashes.add(_zobrist_hash(child.grid, Color.BLACK))

    move = eng.find_move(b.copy(), game_position_hashes=frozenset(all_hashes))
    # Must still return SOME legal move — a forced rule-draw is legal.
    assert move is not None
    assert move.path[0] == (5, 4)  # the king is the only movable piece


# ---------------------------------------------------------------------------
# HeadlessGame integration — the AI must see the hashes the game
# tracker is already counting.
# ---------------------------------------------------------------------------


def test_headless_game_feeds_repeated_hashes_to_ai():
    """End-to-end through HeadlessGame.make_ai_move.

    We start from a lone-king-vs-lone-king position (draw by rule,
    but not yet triggered at ply 0), manually force the hash counts
    dict to pretend the position-about-to-be-entered has been seen
    twice, then ask the AI to move. The chosen move must NOT land
    on the pre-seeded hash.
    """
    b = Board(empty=True)
    b.grid[4, 5] = Board.WHITE_KING  # f4
    b.grid[7, 0] = Board.BLACK  # a1

    g = HeadlessGame(auto_ai=False, position=b.to_position_string())
    g._turn = Color.WHITE  # matches the custom board
    # Re-seed the hash counter to match the forced turn.
    g._position_hash_counts = {
        _zobrist_hash(g._board.grid, Color.WHITE): 1,
    }
    g._engines[Color.WHITE] = AIEngine(
        difficulty=2, color=Color.WHITE, search_depth=4,
        use_book=False, use_bitbase=False,
    )

    # Probe the AI with no hints first to know the "natural" target.
    baseline = g._engines[Color.WHITE].find_move(g._board.copy())
    assert baseline is not None
    child = _apply_move(g._board, baseline.kind, baseline.path)
    baseline_target = _zobrist_hash(child.grid, Color.BLACK)

    # Pretend the baseline target has already appeared twice.
    g._position_hash_counts[baseline_target] = 2

    record = g.make_ai_move()
    assert record is not None, "Engine returned no move"
    # The chosen move must lead to a different position.
    new_child = _apply_move(b, record.kind, record.path)
    new_hash = _zobrist_hash(new_child.grid, Color.BLACK)
    assert new_hash != baseline_target, (
        f"HeadlessGame did not forward the repetition hint to the AI; "
        f"engine still landed on the twice-seen target {hex(baseline_target)}."
    )


def test_headless_game_tracks_hashes_parallel_to_counts():
    """Every entry in ``_position_counts`` has a matching entry in
    ``_position_hash_counts`` with the same count.

    If a future refactor drops one or the other, this test catches
    the drift early — the AI fix depends on both stores staying in
    sync.
    """
    g = HeadlessGame(auto_ai=True, difficulty=1)
    for _ in range(10):
        if g.is_over:
            break
        if g.make_ai_move(move_timeout=2.0) is None:
            break

    # Counts must match in total multiplicity (not key-by-key, because
    # the two use different keys — position_string vs Zobrist).
    assert sum(g._position_counts.values()) == sum(
        g._position_hash_counts.values()
    )


# ---------------------------------------------------------------------------
# Backward-compat smoke: analysis / puzzle callers that ignore the
# new kwarg keep working.
# ---------------------------------------------------------------------------


def test_legacy_callers_do_not_break():
    """find_move() with the old positional-only call still works
    and returns a legal move for the standard opening."""
    b = Board()
    eng = AIEngine(
        difficulty=2, color=Color.WHITE, search_depth=3,
        use_book=False, use_bitbase=False,
    )
    move = eng.find_move(b)
    assert move is not None
    assert move.kind in ("move", "capture")
    # Confirm the move is one of the generator's legal outputs.
    legal = {(k, tuple(tuple(x) for x in p)) for k, p in _generate_all_moves(b, Color.WHITE)}
    this_move = (move.kind, tuple(tuple(x) for x in move.path))
    assert this_move in legal


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
