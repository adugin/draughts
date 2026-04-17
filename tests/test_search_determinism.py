"""Regression tests for search determinism — same position → same move.

Root cause of non-determinism fixed: ``_search_best_move`` used the
module-level unseeded ``random.choice`` for tie-breaking among moves
with equal minimax score. User-observed symptom: after Ctrl+Z the AI
reliably picked a different "best" move on the same position.
Strong engines (Scan, Kingsrow) are deterministic; we match that.
"""

from __future__ import annotations

import pytest

from draughts.config import Color
from draughts.game.ai import _search_best_move
from draughts.game.ai.state import SearchContext
from draughts.game.board import Board


def _make_board_with_capture_tie() -> Board:
    """Position from `test.pdn` after black plays a7:c5. White has four
    different single-piece captures whose top two (e5:c7 and c1:a3)
    evaluated to identical scores under the previous eval — this was
    the real-world case that exposed the non-determinism."""
    b = Board(empty=True)
    # Black pieces (int8 positive)
    b.grid[0, 7] = 1      # h8
    b.grid[1, 4] = 1      # e7
    b.grid[1, 6] = 1      # g7
    b.grid[2, 3] = 1      # d6
    b.grid[3, 2] = 1      # c5 (the just-moved black pawn)
    b.grid[4, 5] = 1      # f4
    b.grid[4, 7] = 1      # h4
    b.grid[6, 1] = 1      # b2
    # White pieces (int8 negative)
    b.grid[3, 4] = -1     # e5
    b.grid[5, 4] = -1     # e5 neighbour: e3 — actually row y=5
    b.grid[5, 6] = -1     # g3
    b.grid[6, 5] = -1     # f2
    b.grid[7, 0] = -1     # a1
    b.grid[7, 2] = -1     # c1
    b.grid[7, 6] = -1     # g1
    return b


def test_same_position_gives_same_move_at_depth_6():
    """Five consecutive searches on an identical position must return
    the exact same move. Fails prior to the deterministic tie-break fix."""
    b = _make_board_with_capture_tie()
    results = []
    for _ in range(5):
        ctx = SearchContext()
        best = _search_best_move(b, Color.WHITE, 6, ctx=ctx)
        assert best is not None
        results.append((best.kind, tuple(tuple(p) for p in best.path)))
    # All five results must be identical
    assert len(set(results)) == 1, f"Non-deterministic search: {results}"


def test_same_position_gives_same_move_from_start():
    """Trivial start-position sanity check — same move returned across calls."""
    b = Board()
    ctx1 = SearchContext()
    ctx2 = SearchContext()
    m1 = _search_best_move(b, Color.WHITE, 4, ctx=ctx1)
    m2 = _search_best_move(b, Color.WHITE, 4, ctx=ctx2)
    assert m1 is not None and m2 is not None
    assert (m1.kind, m1.path) == (m2.kind, m2.path)


def test_determinism_across_fresh_contexts():
    """Determinism must hold even when the caller uses a fresh
    SearchContext each call — this matches what the live controller does
    via _start_computer_turn (fresh AIEngine per turn)."""
    b = _make_board_with_capture_tie()
    first_ctx = SearchContext()
    first = _search_best_move(b, Color.WHITE, 5, ctx=first_ctx)
    for _ in range(4):
        ctx = SearchContext()
        m = _search_best_move(b, Color.WHITE, 5, ctx=ctx)
        assert m is not None and first is not None
        assert (m.kind, m.path) == (first.kind, first.path)
