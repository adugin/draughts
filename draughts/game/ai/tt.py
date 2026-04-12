"""Transposition table — Zobrist hashing + TT probe/store helpers."""

from __future__ import annotations

import numpy as np

from draughts.config import BOARD_SIZE, Color

# ---------------------------------------------------------------------------
# Zobrist hashing — deterministic random table for position hashing
# ---------------------------------------------------------------------------

_RNG = np.random.RandomState(0xDEAD_BEEF)
# 5 piece types: EMPTY(0), BLACK(1), BLACK_KING(2), WHITE(-1→3), WHITE_KING(-2→4)
_ZOBRIST = _RNG.randint(1, 2**63, size=(BOARD_SIZE, BOARD_SIZE, 5), dtype=np.int64)
_ZOBRIST_SIDE = int(_RNG.randint(1, 2**63, dtype=np.int64))  # XOR when black to move

# Piece value → Zobrist index mapping
_PIECE_TO_ZI = {0: 0, 1: 1, 2: 2, -1: 3, -2: 4}


def _zobrist_hash(grid: np.ndarray, color: Color) -> int:
    """Compute Zobrist hash for a board position."""
    h = np.int64(0)
    for y, x in zip(*np.nonzero(grid), strict=True):
        h ^= _ZOBRIST[y, x, _PIECE_TO_ZI[int(grid[y, x])]]
    h = int(h)
    if color == Color.BLACK:
        h ^= _ZOBRIST_SIDE
    return h


# ---------------------------------------------------------------------------
# Transposition table constants
# ---------------------------------------------------------------------------

_TT_EXACT = 0
_TT_LOWER = 1  # score >= beta (fail-high)
_TT_UPPER = 2  # score <= alpha (fail-low)

_TT_MAX = 500_000


# ---------------------------------------------------------------------------
# Transposition table helpers (operate on a ctx.tt dict)
# ---------------------------------------------------------------------------


def _tt_probe(
    tt: dict[int, tuple[int, float, int, int]],
    h: int,
    depth: int,
    alpha: float,
    beta: float,
) -> tuple[float | None, int]:
    """Probe TT. Returns (score_or_None, best_move_index)."""
    entry = tt.get(h)
    if entry is None:
        return None, -1
    tt_depth, tt_score, tt_flag, tt_best = entry
    if tt_depth >= depth:
        if tt_flag == _TT_EXACT:
            return tt_score, tt_best
        if tt_flag == _TT_LOWER and tt_score >= beta:
            return tt_score, tt_best
        if tt_flag == _TT_UPPER and tt_score <= alpha:
            return tt_score, tt_best
    return None, tt_best  # no score but best move hint


def _tt_store(
    tt: dict[int, tuple[int, float, int, int]],
    h: int,
    depth: int,
    score: float,
    flag: int,
    best_idx: int,
) -> None:
    old = tt.get(h)
    if old is None or old[0] <= depth:
        tt[h] = (depth, score, flag, best_idx)
    if len(tt) > _TT_MAX:
        tt.clear()
