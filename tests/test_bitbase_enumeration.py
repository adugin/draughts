"""Regression tests for the bitbase enumeration gap (BITBASE-ENUM).

The old enumerator covered splits (A black, B white) with A,B >= 1
only. Lopsided splits like (2 black, 0 white) were reachable as
capture children but not in the bitbase, so propagation stalled and
parent positions got mislabelled DRAW. The shipped 3-piece file had
many such mislabels — most notably positions with 2 kings vs 1 pawn
where the king side could trivially win.

These tests ensure every reachable piece-count split is enumerated
and that the specific mislabels surfaced by user report are gone.
"""

from __future__ import annotations

from collections import Counter

from draughts.config import BLACK_KING, Color, WHITE
from draughts.game.ai import DEFAULT_BITBASE
from draughts.game.ai.bitbase import DRAW, LOSS, WIN
from draughts.game.ai.tt import _zobrist_hash
from draughts.game.board import Board
from draughts.tools.build_bitbase import _enumerate_all_positions


def test_enumeration_covers_all_splits_up_to_3():
    """Every piece-count split (n_black, n_white) with 1 <= total <= 3 is present."""
    positions = _enumerate_all_positions(max_pieces=3)
    counts: Counter[tuple[int, int]] = Counter()
    for pieces, _ in positions:
        nb = sum(1 for (_x, _y, v) in pieces if v > 0)
        nw = sum(1 for (_x, _y, v) in pieces if v < 0)
        counts[(nb, nw)] += 1

    expected_splits = {
        (1, 0), (0, 1),
        (2, 0), (1, 1), (0, 2),
        (3, 0), (2, 1), (1, 2), (0, 3),
    }
    assert set(counts.keys()) == expected_splits, (
        f"Missing or extra splits. Got {sorted(counts.keys())}"
    )
    for split, n in counts.items():
        assert n > 0, f"Split {split} enumerated zero positions"


def test_enumeration_covers_all_splits_up_to_4():
    positions = _enumerate_all_positions(max_pieces=4)
    counts: Counter[tuple[int, int]] = Counter()
    for pieces, _ in positions:
        nb = sum(1 for (_x, _y, v) in pieces if v > 0)
        nw = sum(1 for (_x, _y, v) in pieces if v < 0)
        counts[(nb, nw)] += 1

    expected_splits = {
        (a, b)
        for total in range(1, 5)
        for a in range(total + 1)
        for b in [total - a]
    }
    assert set(counts.keys()) == expected_splits


# ---------------------------------------------------------------------------
# Specific previously-mislabeled positions now labeled correctly.
# ---------------------------------------------------------------------------


def test_lopsided_position_has_a_verdict():
    """2 BK + 0 white pieces with WHITE to move: white has no legal moves,
    so white LOSES. Previously NOT-IN-BASE → parent positions mislabeled DRAW.
    """
    b = Board(empty=True)
    b.grid[1, 2] = BLACK_KING  # c7
    b.grid[2, 7] = BLACK_KING  # h6

    r = DEFAULT_BITBASE.probe_hash(_zobrist_hash(b.grid, Color.WHITE))
    assert r == LOSS, f"2BK vs nothing should be LOSS for white, got {r}"


def test_user_reported_blunder_position_has_correct_verdict():
    """Position from the user bug report: 2 BK (e5, h6) + 1 WP (c5),
    WHITE to move. Black can force capture of the lone pawn → white
    LOSES. Previously mislabeled as DRAW.
    """
    b = Board(empty=True)
    b.grid[3, 4] = BLACK_KING  # e5
    b.grid[2, 7] = BLACK_KING  # h6
    b.grid[3, 2] = WHITE       # c5

    r = DEFAULT_BITBASE.probe_hash(_zobrist_hash(b.grid, Color.WHITE))
    assert r == LOSS, f"2BK+1WP with white-to-move should be LOSS, got {r}"


def test_classic_1k_vs_1p_still_labeled_correctly():
    """1 BK (h6) vs 1 WP (e3), WHITE to move → LOSS (king catches pawn)."""
    b = Board(empty=True)
    b.grid[2, 7] = BLACK_KING
    b.grid[5, 4] = WHITE

    r = DEFAULT_BITBASE.probe_hash(_zobrist_hash(b.grid, Color.WHITE))
    assert r == LOSS


def test_bitbase_max_pieces_metadata_present():
    """Regenerated 3-piece bitbase carries __meta__.max_pieces = 3."""
    assert DEFAULT_BITBASE.max_pieces == 3


def test_bitbase_size_grew_after_fix():
    """Regenerated 3-piece bitbase is larger than old (399K) — now ~536K
    due to lopsided splits being included.
    """
    assert len(DEFAULT_BITBASE) >= 500_000, (
        f"Expected at least 500K entries, got {len(DEFAULT_BITBASE):,}"
    )


def test_bitbase_all_values_are_valid_wdl():
    """No orphan entries with non-WDL values."""
    # Spot-check a sample — iterating 500K is cheap enough.
    for _h, v in list(DEFAULT_BITBASE._entries.items())[:100_000]:
        assert v in (WIN, DRAW, LOSS), f"Invalid WDL value: {v!r}"
