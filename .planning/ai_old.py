"""AI module for Russian draughts — NumPy engine with alpha-beta minimax.

Architecture:
    1. Static evaluation function (vectorized, fast)
    2. Alpha-beta pruning minimax search at configurable depth
    3. Move ordering for optimal pruning (captures first, then heuristics)

Piece encoding: BLACK=1, BLACK_KING=2, WHITE=-1, WHITE_KING=-2, EMPTY=0
Coordinates: 0-indexed (x=0..7, y=0..7)
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

import numpy as np

from draughts.config import (
    BLACK,
    BLACK_KING,
    BOARD_SIZE,
    DIAGONAL_DIRECTIONS,
    WHITE,
    WHITE_KING,
    Color,
)
from draughts.game.board import Board

# Last valid index (0-indexed board)
_LAST = BOARD_SIZE - 1


class SearchCancelledError(Exception):
    """Raised inside alpha-beta when the search deadline passes."""
    pass


# ---------------------------------------------------------------------------
# SearchContext — per-search mutable state (replaces module-level globals)
# ---------------------------------------------------------------------------
# All five former module-level globals (_tt, _killers, _history,
# _search_deadline, _last_search_score) now live in SearchContext so that
# concurrent HeadlessGame instances (e.g. parallel Tournament) cannot
# interfere with each other's search state.


@dataclass
class SearchContext:
    """Isolated mutable state for one alpha-beta search tree."""

    tt: dict[int, tuple[int, float, int, int]] = field(default_factory=dict)
    killers: dict[int, list[tuple[str, tuple]]] = field(default_factory=dict)
    history: dict[tuple, int] = field(default_factory=dict)
    deadline: float | None = None
    last_score: float = float("nan")

    def clear(self) -> None:
        self.tt.clear()
        self.killers.clear()
        self.history.clear()
        self.last_score = float("nan")


# ---------------------------------------------------------------------------
# Module-level default SearchContext and backward-compatibility aliases
# ---------------------------------------------------------------------------
# _default_ctx is the shared module-level context used by _search_best_move
# when no explicit ctx is passed. This replicates the old behaviour where
# _tt, _killers, _history were module-level globals that persisted across
# calls and were shared between any engines in the same process (e.g. both
# sides in a game). When callers want isolation (parallel tournaments,
# tests) they can pass their own SearchContext explicitly.
#
# _last_search_score and _tt are kept as module-level names so existing
# callers (perf_baseline.py, head2head.py, headless.py) that do
# `ai._tt.clear()` or read `_ai._last_search_score` keep working.
# Both are updated by _search_best_move after every call.

_default_ctx: SearchContext = SearchContext()

# _tt points at the default ctx's tt dict so `ai._tt.clear()` still works.
_tt: dict[int, tuple[int, float, int, int]] = _default_ctx.tt

_last_search_score: float = float("nan")


def _killers_clear() -> None:
    """Backward-compat: clear killers on the default context."""
    _default_ctx.killers.clear()


def _history_clear() -> None:
    """Backward-compat: clear history on the default context."""
    _default_ctx.history.clear()

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
# Transposition table helpers (operate on a ctx.tt dict)
# ---------------------------------------------------------------------------

_TT_EXACT = 0
_TT_LOWER = 1  # score >= beta (fail-high)
_TT_UPPER = 2  # score <= alpha (fail-low)

_TT_MAX = 500_000


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


# ---------------------------------------------------------------------------
# Killer moves helpers (operate on a ctx.killers dict)
# ---------------------------------------------------------------------------


def _record_killer(
    killers: dict[int, list[tuple[str, tuple]]],
    depth: int,
    kind: str,
    path: list,
) -> None:
    key = (kind, tuple(path))
    slot = killers.get(depth)
    if slot is None:
        killers[depth] = [key]
    elif key not in slot:
        slot.insert(0, key)
        if len(slot) > 2:
            slot.pop()


# ---------------------------------------------------------------------------
# History heuristic helpers (operate on a ctx.history dict)
# ---------------------------------------------------------------------------
# Increment is depth*depth so cutoffs near the root (deep subtrees
# eliminated) count more than shallow ones.


def _history_record(
    history: dict[tuple, int],
    kind: str,
    path: list,
    depth: int,
) -> None:
    # Only track quiet moves — captures are already ordered first.
    if kind == "capture":
        return
    key = (kind, tuple(path))
    history[key] = history.get(key, 0) + depth * depth


def _history_score(history: dict[tuple, int], kind: str, path: list) -> int:
    if kind == "capture":
        return 0
    return history.get((kind, tuple(path)), 0)


# Precomputed advancement tables (0-indexed, 8x8)
# Black pawns advance by increasing y; white by decreasing y
_BLACK_ADVANCE = np.zeros((BOARD_SIZE, BOARD_SIZE), dtype=np.float32)
_WHITE_ADVANCE = np.zeros((BOARD_SIZE, BOARD_SIZE), dtype=np.float32)
for _y in range(BOARD_SIZE):
    for _x in range(BOARD_SIZE):
        _BLACK_ADVANCE[_y, _x] = _y / _LAST  # 0.0 at row 0, 1.0 at row 7
        _WHITE_ADVANCE[_y, _x] = (_LAST - _y) / _LAST  # 1.0 at row 0, 0.0 at row 7

# Evaluation weights
_KING_VALUE = 15.0
_PAWN_VALUE = 5.0
_ADVANCE_BONUS = 0.15
_CENTER_BONUS = 0.05
_SAFETY_BONUS = 0.1
_MOBILITY_WEIGHT = 0.02
_THREAT_PENALTY = 0.5
_CONNECTED_BONUS = 0.08  # pawn supported by another pawn diagonally behind
_GOLDEN_CORNER = 0.3  # pieces on a1/h8 are nearly invulnerable in Russian draughts

# Precomputed center mask (0-indexed, 8x8)
_CENTER_MASK = np.zeros((BOARD_SIZE, BOARD_SIZE), dtype=np.float32)
for _y in range(BOARD_SIZE):
    for _x in range(BOARD_SIZE):
        dist = max(abs(_x - 3.5), abs(_y - 3.5))
        _CENTER_MASK[_y, _x] = max(0, (3.5 - dist) / 3.5)

# Pre-flattened tables for dot-product evaluation (avoid temp array allocation)
_BLACK_ADVANCE_FLAT = _BLACK_ADVANCE.ravel().astype(np.float32)
_WHITE_ADVANCE_FLAT = _WHITE_ADVANCE.ravel().astype(np.float32)
_CENTER_FLAT = _CENTER_MASK.ravel().astype(np.float32)

# Promotion rows (0-indexed)
_WHITE_PROMOTE_ROW = 0
_BLACK_PROMOTE_ROW = _LAST


# ---------------------------------------------------------------------------
# Move representation
# ---------------------------------------------------------------------------


class AIMove:
    """Result returned by the AI."""

    def __init__(self, kind: str, path: list[tuple[int, int]]):
        self.kind = kind
        self.path = path

    def __repr__(self) -> str:
        return f"AIMove({self.kind!r}, {self.path})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_on_board(x: int, y: int) -> bool:
    return 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE


def _max_diagonal_reach(x: int, y: int) -> int:
    return max(_LAST - y, y, _LAST - x, x)


def _find_pieces(grid: np.ndarray, color: str | Color) -> list[tuple[int, int]]:
    """Find all piece positions for a color. Returns list of (x, y)."""
    positions = np.argwhere(grid > 0) if color == Color.BLACK else np.argwhere(grid < 0)
    return [(int(p[1]), int(p[0])) for p in positions]


def _count_pieces(color: str | Color, grid: np.ndarray) -> int:
    return int(np.count_nonzero(grid > 0)) if color == Color.BLACK else int(np.count_nonzero(grid < 0))


def _opponent(color: str | Color) -> Color:
    return Color.WHITE if color == Color.BLACK else Color.BLACK


# ---------------------------------------------------------------------------
# Scan diagonal
# ---------------------------------------------------------------------------


def _scan_diagonal(x1: int, y1: int, x2: int, y2: int, color: str | Color, grid: np.ndarray) -> tuple[int, int, int]:
    """Check how many pieces lie on diagonal (x1,y1)->(x2,y2) exclusive."""
    if x2 == x1 or y2 == y1:
        return (0, 0, 0)
    if abs(x2 - x1) != abs(y2 - y1):
        return (0, 0, 0)
    dx = 1 if x2 > x1 else -1
    dy = 1 if y2 > y1 else -1
    cx, cy = x1 + dx, y1 + dy
    n = 0
    bx, by = 0, 0
    ok = False
    while (cx, cy) != (x2, y2):
        if not _is_on_board(cx, cy):
            return (0, 0, 0)
        cell = int(grid[cy, cx])
        if cell != 0:
            n += 1
        if (color == Color.BLACK and cell > 0) or (color == Color.WHITE and cell < 0):
            ok = True
            bx, by = cx, cy
        cx += dx
        cy += dy
    if ok and n == 1:
        return (1, bx, by)
    if n == 0:
        return (0, 0, 0)
    return (2, 0, 0)


def _is_path_clear(x1: int, y1: int, x2: int, y2: int, grid: np.ndarray) -> bool:
    if x1 == x2 and y1 == y2:
        return True
    dx = 1 if x2 > x1 else -1
    dy = 1 if y2 > y1 else -1
    cx, cy = x1 + dx, y1 + dy
    while not (abs(cx - x2) <= 1 and abs(cy - y2) <= 1):
        if grid[cy, cx] != 0:
            return False
        cx += dx
        cy += dy
    return True


# ---------------------------------------------------------------------------
# Danger detection
# ---------------------------------------------------------------------------


def _dangerous_position(x: int, y: int, grid: np.ndarray, color: str | Color) -> bool:
    """Check if piece at (x,y) is under attack."""
    piece = int(grid[y, x])
    if piece == 0:
        return False

    close = [False, False, False, False]

    for rr in range(1, _max_diagonal_reach(x, y) + 1):
        for di in range(4):
            dx, dy = DIAGONAL_DIRECTIONS[di]
            bx, by = x - dx, y - dy
            ax, ay = x + rr * dx, y + rr * dy

            if not _is_on_board(bx, by) or not _is_on_board(ax, ay):
                continue

            if grid[by, bx] != 0:
                continue

            if rr == 1:
                attacker = int(grid[ay, ax])
                if piece * attacker < 0:
                    return True
                if piece * attacker > 0:
                    close[di] = True
            else:
                cell = int(grid[ay, ax])
                enemy_king = WHITE_KING if color == Color.BLACK else BLACK_KING
                if color == Color.BLACK:
                    if cell in (1, 2, -1):
                        close[di] = True
                    elif not close[di] and cell == enemy_king:
                        return True
                else:
                    if cell in (-1, -2, 1):
                        close[di] = True
                    elif not close[di] and cell == enemy_king:
                        return True
    return False


def _any_piece_threatened(color: str | Color, grid: np.ndarray) -> bool:
    return any(_dangerous_position(x, y, grid, color) for x, y in _find_pieces(grid, color))


def _count_threatened(color: str | Color, grid: np.ndarray) -> int:
    return sum(1 for x, y in _find_pieces(grid, color) if _dangerous_position(x, y, grid, color))


# ---------------------------------------------------------------------------
# Position helpers
# ---------------------------------------------------------------------------


def _is_near_edge_or_ally(x: int, y: int, grid: np.ndarray) -> bool:
    for di in range(2, 4):
        dx, dy = DIAGONAL_DIRECTIONS[di]
        nx, ny = x + 2 * dx, y + 2 * dy
        if _is_on_board(nx, ny):
            adj = int(grid[y + dy, x + dx])
            far = int(grid[ny, nx])
            behind = int(grid[y - 2, x]) if _is_on_board(x, y - 2) else 0
            if adj == 0 and (far > 0 or behind > 0):
                return True
    return bool(x in (0, _LAST) or y in (0, _LAST))


def _is_flank_vulnerable(x: int, y: int, grid: np.ndarray) -> bool:
    if y + 2 >= BOARD_SIZE:
        return False
    if x == 1 and int(grid[y + 2, 1]) < 0 and grid[y + 1, 0] == 0:
        return True
    return bool(x == _LAST - 1 and int(grid[y + 2, x]) < 0 and grid[y + 1, _LAST] == 0)


def _has_single_capture_only(grid: np.ndarray) -> bool:
    first = False
    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            if grid[y, x] > 0:
                for di in range(4):
                    dx, dy = DIAGONAL_DIRECTIONS[di]
                    for rr in range(1, _max_diagonal_reach(x, y) + 1):
                        bkx, bky = x - dx, y - dy
                        ax, ay = x + rr * dx, y + rr * dy
                        if not _is_on_board(bkx, bky) or not _is_on_board(ax, ay):
                            continue
                        if grid[bky, bkx] != 0:
                            continue
                        cell = int(grid[ay, ax])
                        if (rr == 1 and cell == WHITE) or (
                            cell == WHITE_KING and (rr == 1 or _is_path_clear(x, y, ax, ay, grid))
                        ):
                            if first:
                                return False
                            first = True
                            break
    return True


# ---------------------------------------------------------------------------
# Endgame pattern detection
# ---------------------------------------------------------------------------

_KING_DISTANCE_WEIGHT = 0.4  # reward kings for approaching opponent pieces

# Contempt factor: a small negative score returned at draw detections
# (repetition and drawn-endgame patterns). Interpreted from root_color's
# perspective, so the searching side treats draws as mildly unfavorable
# and prefers decisive continuations when material is close. Self-play
# baseline measured 45% of games as draw-by-king-dance; this incentive
# nudges the engine toward converting advantages instead of cycling.
# Initially set to 0.25 (1/20th of a pawn). Trap-battery + conversion
# analysis showed the AI still accepted draws too readily when ahead;
# bumped to 0.5 (1/10th of a pawn) which is still well below any real
# material value but strong enough to prefer any non-drawing move with
# even a tiny positional plus.
_CONTEMPT = 0.5


def _is_drawn_endgame(grid: np.ndarray) -> bool:
    """Detect trivially drawn endgame positions."""
    flat = grid.ravel().view(np.uint8)
    counts = np.bincount(flat, minlength=256)
    bp, bk, wp, wk = int(counts[1]), int(counts[2]), int(counts[255]), int(counts[254])
    black_total = bp + bk
    white_total = wp + wk
    # King vs king (no pawns) — always a draw in Russian draughts
    if bp == 0 and wp == 0 and bk >= 1 and wk >= 1:
        return True
    # Lone piece vs lone piece with no captures — likely draw
    return black_total == 1 and white_total == 1 and bk == 1 and wk == 1


_OFF_DIAGONAL_PENALTY = 0.5


def _diagonal_distance(dx: int, dy: int) -> float:
    """Effective distance for a flying king to reach a target.

    Base is the Chebyshev distance (= diagonal walking distance for
    dark-to-dark squares on an 8x8 board). A small off-diagonal penalty
    |dx - dy| biases the metric so targets on an attack diagonal score
    slightly better than targets that would require a reposition first.

    The penalty is deliberately mild: an earlier draft at 2.0 tipped
    the eval heavily against king-distance contributions and regressed
    midgame play measurably (bisect traced a ~19 eval-point drop on a
    10-seed bench to this function). 0.5 keeps the metric close to the
    original Chebyshev signal while still preferring alignment when
    alignment is available.

    Returns a non-negative float; lower = easier to attack.
    """
    return max(dx, dy) + _OFF_DIAGONAL_PENALTY * abs(dx - dy)


def _king_distance_score(grid: np.ndarray) -> float:
    """Score kings for diagonal-aware proximity to opponent pieces.

    Rewards kings for being on (or close to) an attack diagonal against
    an enemy piece. Returns positive if black kings are better placed,
    negative if white kings are. The heuristic is symmetric — mirroring
    the board + swapping colors negates the score exactly.

    Replaces the older Chebyshev-based metric, which over-valued kings
    parked near an enemy but not on any attack diagonal (e.g. a king at
    h8 was scored "close" to a pawn at b4 even though h8 cannot reach
    b4 on any line).
    """
    black_kings = np.argwhere(grid == BLACK_KING)  # (y, x) arrays
    white_kings = np.argwhere(grid == WHITE_KING)
    white_pieces = np.argwhere(grid < 0)
    black_pieces = np.argwhere(grid > 0)

    score = 0.0

    if len(black_kings) > 0 and len(white_pieces) > 0:
        for ky, kx in black_kings:
            min_dist = min(
                _diagonal_distance(abs(int(kx - px)), abs(int(ky - py)))
                for py, px in white_pieces
            )
            # Normalized into [0, 7]: on-diagonal adjacent = 1 -> bonus 6;
            # diagonal across the board = 7 -> bonus 0; far off-diagonal
            # saturates at 0 via the clamp.
            score += max(0.0, 7.0 - min_dist) * 0.5

    if len(white_kings) > 0 and len(black_pieces) > 0:
        for ky, kx in white_kings:
            min_dist = min(
                _diagonal_distance(abs(int(kx - px)), abs(int(ky - py)))
                for py, px in black_pieces
            )
            score -= max(0.0, 7.0 - min_dist) * 0.5

    return score


# ===========================================================================
# STATIC EVALUATION — vectorized position scoring
# ===========================================================================


def evaluate_position(grid: np.ndarray, color: str | Color) -> float:
    """Evaluate board position from perspective of `color`."""
    black_pawns = int(np.count_nonzero(grid == BLACK))
    black_kings = int(np.count_nonzero(grid == BLACK_KING))
    white_pawns = int(np.count_nonzero(grid == WHITE))
    white_kings = int(np.count_nonzero(grid == WHITE_KING))

    black_total = black_pawns + black_kings
    white_total = white_pawns + white_kings
    if black_total == 0:
        return -1000.0 if color == Color.BLACK else 1000.0
    if white_total == 0:
        return 1000.0 if color == Color.BLACK else -1000.0

    material = (black_pawns * _PAWN_VALUE + black_kings * _KING_VALUE) - (
        white_pawns * _PAWN_VALUE + white_kings * _KING_VALUE
    )

    black_pawn_mask = (grid == BLACK).astype(np.float32)
    white_pawn_mask = (grid == WHITE).astype(np.float32)
    advancement = (
        float(np.sum(black_pawn_mask * _BLACK_ADVANCE)) - float(np.sum(white_pawn_mask * _WHITE_ADVANCE))
    ) * _ADVANCE_BONUS

    black_all = (grid > 0).astype(np.float32)
    white_all = (grid < 0).astype(np.float32)
    center = float(np.sum(black_all * _CENTER_MASK) - np.sum(white_all * _CENTER_MASK)) * _CENTER_BONUS

    temp_board = Board(empty=True)
    temp_board.grid = grid
    black_mobility = 0
    white_mobility = 0
    for x, y in _find_pieces(grid, Color.BLACK):
        black_mobility += len(temp_board.get_valid_moves(x, y)) + len(temp_board.get_captures(x, y))
    for x, y in _find_pieces(grid, Color.WHITE):
        white_mobility += len(temp_board.get_valid_moves(x, y)) + len(temp_board.get_captures(x, y))

    if color == Color.BLACK and black_mobility == 0:
        return -1000.0
    if color == Color.WHITE and white_mobility == 0:
        return -1000.0

    mobility = (black_mobility - white_mobility) * _MOBILITY_WEIGHT

    black_threatened = _count_threatened(Color.BLACK, grid)
    white_threatened = _count_threatened(Color.WHITE, grid)
    threats = (white_threatened - black_threatened) * _THREAT_PENALTY

    total = material + advancement + center + mobility + threats
    return total if color == Color.BLACK else -total


def _evaluate_fast(grid: np.ndarray, color: str | Color) -> float:
    """Ultra-fast evaluation — material + advancement + center + structure."""
    # Piece counts via bincount (one call instead of four)
    flat = grid.ravel().view(np.uint8)  # int8 → uint8 view (no copy): -2→254,-1→255,0→0,1→1,2→2
    counts = np.bincount(flat, minlength=256)
    black_pawns = int(counts[1])
    black_kings = int(counts[2])
    white_pawns = int(counts[255])  # -1 as uint8
    white_kings = int(counts[254])  # -2 as uint8

    black_total = black_pawns + black_kings
    white_total = white_pawns + white_kings
    if black_total == 0:
        return -1000.0 if color == Color.BLACK else 1000.0
    if white_total == 0:
        return 1000.0 if color == Color.BLACK else -1000.0

    # Material
    total = (black_pawns * _PAWN_VALUE + black_kings * _KING_VALUE) - (
        white_pawns * _PAWN_VALUE + white_kings * _KING_VALUE
    )

    # Advancement — dot product (no temp array allocation)
    grid_flat = grid.ravel().astype(np.float32)
    bp_mask = (grid_flat == 1.0)
    wp_mask = (grid_flat == -1.0)
    total += (np.dot(bp_mask, _BLACK_ADVANCE_FLAT) - np.dot(wp_mask, _WHITE_ADVANCE_FLAT)) * _ADVANCE_BONUS

    # Center control
    black_mask = (grid_flat > 0)
    white_mask = (grid_flat < 0)
    total += (np.dot(black_mask, _CENTER_FLAT) - np.dot(white_mask, _CENTER_FLAT)) * _CENTER_BONUS

    # Phase-dependent weighting (endgame amplifies positional factors)
    all_pieces = black_total + white_total
    phase = min(1.0, max(0.0, (24 - all_pieces) / 16.0))  # 0=opening, 1=endgame

    # Back rank defense — more important in midgame
    if np.any(grid[_LAST] < 0):
        total += _SAFETY_BONUS * (1.0 - phase)
    if np.any(grid[0] > 0):
        total -= _SAFETY_BONUS * (1.0 - phase)

    # Connected pawns — supported by ally diagonally behind (slicing, no temp alloc)
    if black_pawns > 1 or white_pawns > 1:
        conn = 0
        # Black pawn at (y,x) supported if grid[y-1, x±1] > 0
        bp = grid[1:, :] == 1  # black pawns from row 1 down
        conn += int(np.count_nonzero(bp[:, 1:] & (grid[:-1, :-1] > 0)))
        conn += int(np.count_nonzero(bp[:, :-1] & (grid[:-1, 1:] > 0)))
        # White pawn at (y,x) supported if grid[y+1, x±1] < 0
        wp = grid[:-1, :] == -1  # white pawns from row 0 up
        conn -= int(np.count_nonzero(wp[:, 1:] & (grid[1:, :-1] < 0)))
        conn -= int(np.count_nonzero(wp[:, :-1] & (grid[1:, 1:] < 0)))
        total += conn * _CONNECTED_BONUS

    # Golden corners — a1 (0,7) and h8 (7,0) are strong defensive positions
    if grid[_LAST, 0] > 0:  # a1 = black piece
        total += _GOLDEN_CORNER
    if grid[_LAST, 0] < 0:  # a1 = white piece
        total -= _GOLDEN_CORNER
    if grid[0, _LAST] > 0:  # h8 = black piece
        total += _GOLDEN_CORNER
    if grid[0, _LAST] < 0:  # h8 = white piece
        total -= _GOLDEN_CORNER

    # King centralization bonus in endgame
    if phase > 0.3:
        king_center = 0.0
        bk_mask = (grid_flat == 2.0)
        wk_mask = (grid_flat == -2.0)
        if np.any(bk_mask):
            king_center += float(np.dot(bk_mask, _CENTER_FLAT)) * phase
        if np.any(wk_mask):
            king_center -= float(np.dot(wk_mask, _CENTER_FLAT)) * phase
        total += king_center * 0.3

    # King distance to opponent — kings should approach enemy pieces in endgame
    if phase > 0.3 and (black_kings > 0 or white_kings > 0):
        total += _king_distance_score(grid) * _KING_DISTANCE_WEIGHT * phase

    return total if color == Color.BLACK else -total


# ===========================================================================
# MOVE GENERATION
# ===========================================================================


def _generate_all_moves(board: Board, color: str | Color) -> list[tuple[str, list[tuple[int, int]]]]:
    """Generate all legal moves for a color.

    Captures are mandatory — if any exist, only captures are returned.
    """
    grid = board.grid
    captures = []
    normal_moves = []

    for x, y in _find_pieces(grid, color):
        cap_paths = board.get_captures(x, y)
        for path in cap_paths:
            captures.append(("capture", path))

        if not captures:
            moves = board.get_valid_moves(x, y)
            for nx, ny in moves:
                normal_moves.append(("move", [(x, y), (nx, ny)]))

    if captures:
        return captures
    return normal_moves


def _apply_move(board: Board, kind: str, path: list[tuple[int, int]]) -> Board:
    """Apply a move to a board copy and return the new board."""
    new_board = Board.__new__(Board)
    new_board.grid = board.grid.copy()
    if kind == "capture":
        new_board.execute_capture_path(path)
    else:
        (x1, y1), (x2, y2) = path[0], path[1]
        new_board.execute_move(x1, y1, x2, y2)
    return new_board


# ===========================================================================
# MOVE ORDERING
# ===========================================================================


def _order_moves(
    moves: list[tuple[str, list[tuple[int, int]]]],
    board: Board,
    color: str | Color,
    history: dict[tuple, int] | None = None,
) -> list[tuple[str, list[tuple[int, int]]]]:
    """Order moves to improve alpha-beta pruning."""
    if len(moves) <= 1:
        return moves

    scored = []
    for kind, path in moves:
        priority = 0.0
        if kind == "capture":
            priority = 100.0 + len(path) * 10.0
            for i in range(len(path) - 1):
                x1, y1 = path[i]
                x2, y2 = path[i + 1]
                dx = 1 if x2 > x1 else -1
                dy = 1 if y2 > y1 else -1
                cx, cy = x1 + dx, y1 + dy
                while (cx, cy) != (x2, y2):
                    cap = int(board.grid[cy, cx])
                    if cap != 0:
                        if abs(cap) == 2:
                            priority += 20.0
                        break
                    cx += dx
                    cy += dy
        else:
            (x1, y1), (x2, y2) = path
            piece = int(board.grid[y1, x1])
            promote_row = _BLACK_PROMOTE_ROW if color == Color.BLACK else _WHITE_PROMOTE_ROW
            if y2 == promote_row:
                priority = 50.0
            elif abs(piece) == 2:
                # King move: prioritize approaching opponent pieces
                opp_pieces = np.argwhere(board.grid < 0) if color == Color.BLACK else np.argwhere(board.grid > 0)
                if len(opp_pieces) > 0:
                    min_dist = min(max(abs(x2 - int(px)), abs(y2 - int(py))) for py, px in opp_pieces)
                    priority = 30.0 + (7.0 - min_dist) * 3.0  # closer to enemy = higher priority
                else:
                    priority = float(_CENTER_MASK[y2, x2]) * 10.0
                priority += float(_CENTER_MASK[y2, x2]) * 5.0  # center bonus
            else:
                priority = float(_CENTER_MASK[y2, x2]) * 10.0
        # History bonus: quiet moves that historically caused beta
        # cutoffs get bumped. Small weight so history doesn't override
        # the heuristic priority for obviously strong moves like captures
        # and promotions.
        if history is not None:
            priority += _history_score(history, kind, path) * 0.001
        scored.append((priority, kind, path))

    scored.sort(key=lambda x: -x[0])
    return [(kind, path) for _, kind, path in scored]


# ===========================================================================
# QUIESCENCE SEARCH — resolve captures beyond depth limit
# ===========================================================================

_MAX_QDEPTH = 6


def _quiescence(
    board: Board,
    alpha: float,
    beta: float,
    maximizing: bool,
    color: str | Color,
    root_color: str | Color,
    ctx: SearchContext,
    qdepth: int = 0,
) -> float:
    """Search captures *and* promotion moves to tame horizon effects.

    Captures are the classical quiescence set. Promotion moves are added
    because promoting a pawn to a king swings eval by ~10 material points
    (king_value - pawn_value) in a single ply, so leaving them to stand-pat
    causes the same horizon-blindness quiescence was designed to avoid.
    Self-play profiling (Phase 3 analysis) found that 100% of the
    "quiet-move blunders" with eval-swing >3 were uncovered promotions.
    """
    # Fail-SOFT quiescence. Previously this function returned `alpha` or
    # `beta` at cutoffs (fail-hard), which silently clamped sub-tree
    # values to the caller's window. Combined with the fail-soft
    # _alphabeta above, the clamping caused a real bug: at the root,
    # moves whose true value was below the running alpha all got
    # returned as exactly alpha, tying every "worse" move with the
    # running best and feeding a bag of random blunders to
    # random.choice at the end of _search_best_move. Fail-soft lets the
    # actual sub-tree score propagate.
    stand_pat = _evaluate_fast(board.grid, root_color)
    best = stand_pat

    if maximizing:
        if stand_pat >= beta:
            return stand_pat
        if stand_pat > alpha:
            alpha = stand_pat
    else:
        if stand_pat <= alpha:
            return stand_pat
        if stand_pat < beta:
            beta = stand_pat

    if qdepth >= _MAX_QDEPTH:
        return stand_pat

    moves = _generate_all_moves(board, color)
    tactical = []
    promote_row = _BLACK_PROMOTE_ROW if Color(color) == Color.BLACK else _WHITE_PROMOTE_ROW
    for k, p in moves:
        if k == "capture":
            tactical.append((k, p))
        elif k == "move":
            x1, y1 = p[0]
            _x2, y2 = p[-1]
            start_piece = int(board.grid[y1, x1])
            is_pawn = abs(start_piece) == 1
            if is_pawn and y2 == promote_row:
                tactical.append((k, p))
    if not tactical:
        return best

    opp = _opponent(color)

    if maximizing:
        for kind, path in tactical:
            child = _apply_move(board, kind, path)
            score = _quiescence(child, alpha, beta, False, opp, root_color, ctx, qdepth + 1)
            if score > best:
                best = score
            if score > alpha:
                alpha = score
            if alpha >= beta:
                break
        return best
    else:
        for kind, path in tactical:
            child = _apply_move(board, kind, path)
            score = _quiescence(child, alpha, beta, True, opp, root_color, ctx, qdepth + 1)
            if score < best:
                best = score
            if score < beta:
                beta = score
            if alpha >= beta:
                break
        return best


# ===========================================================================
# ALPHA-BETA MINIMAX with TT + killer moves + quiescence
# ===========================================================================


def _alphabeta(
    board: Board,
    depth: int,
    alpha: float,
    beta: float,
    maximizing: bool,
    color: str | Color,
    root_color: str | Color,
    ctx: SearchContext,
    path_hashes: set[int] | None = None,
) -> float:
    """Alpha-beta pruning minimax with TT, quiescence, LMR, and repetition detection."""
    # Cooperative cancellation: check deadline at depths >= 2 (cheap enough,
    # still bounds wall-clock within ~few ms of any sub-tree at depth 2+).
    if depth >= 2 and ctx.deadline is not None and time.perf_counter() >= ctx.deadline:
        raise SearchCancelledError()

    # Quiescence search at leaf nodes
    if depth <= 0:
        return _quiescence(board, alpha, beta, maximizing, color, root_color, ctx)

    # Transposition table probe
    h = _zobrist_hash(board.grid, color)

    # Repetition detection — draw score with contempt bias.
    # Contempt is always a slight negative from root's perspective so the
    # searching side avoids cycles when better continuations exist.
    if path_hashes is not None and h in path_hashes:
        return -_CONTEMPT

    tt_score, tt_best_idx = _tt_probe(ctx.tt, h, depth, alpha, beta)
    if tt_score is not None:
        return tt_score

    moves = _generate_all_moves(board, color)
    if not moves:
        return -1000.0 if maximizing else 1000.0

    # Endgame pattern: king vs king only = draw (also contempt-biased).
    if _is_drawn_endgame(board.grid):
        return -_CONTEMPT

    # Move ordering: TT best move first, then killers, then heuristic
    moves = _order_moves(moves, board, color, ctx.history)

    # Put TT best move first if available
    if 0 <= tt_best_idx < len(moves):
        best = moves.pop(tt_best_idx)
        moves.insert(0, best)

    # Promote killer moves
    killers = ctx.killers.get(depth)
    if killers:
        for ki in range(len(moves) - 1, 0, -1):
            k, p = moves[ki]
            if (k, tuple(p)) in killers:
                moves.insert(1, moves.pop(ki))

    opp = _opponent(color)
    orig_alpha = alpha
    best_idx = 0

    # Track position for repetition detection
    child_hashes = path_hashes | {h} if path_hashes is not None else {h}

    if maximizing:
        value = -float("inf")
        for i, (kind, path) in enumerate(moves):
            child = _apply_move(board, kind, path)

            # Late Move Reduction: after first 3 moves, reduce depth for non-captures
            if i >= 3 and depth >= 3 and kind != "capture":
                child_val = _alphabeta(child, depth - 2, alpha, beta, False, opp, root_color, ctx, child_hashes)
                if child_val > alpha:
                    child_val = _alphabeta(child, depth - 1, alpha, beta, False, opp, root_color, ctx, child_hashes)
            else:
                child_val = _alphabeta(child, depth - 1, alpha, beta, False, opp, root_color, ctx, child_hashes)

            if child_val > value:
                value = child_val
                best_idx = i
            alpha = max(alpha, value)
            if alpha >= beta:
                _record_killer(ctx.killers, depth, kind, path)
                _history_record(ctx.history, kind, path, depth)
                break
    else:
        value = float("inf")
        for i, (kind, path) in enumerate(moves):
            child = _apply_move(board, kind, path)

            # Late Move Reduction
            if i >= 3 and depth >= 3 and kind != "capture":
                child_val = _alphabeta(child, depth - 2, alpha, beta, True, opp, root_color, ctx, child_hashes)
                if child_val < beta:
                    child_val = _alphabeta(child, depth - 1, alpha, beta, True, opp, root_color, ctx, child_hashes)
            else:
                child_val = _alphabeta(child, depth - 1, alpha, beta, True, opp, root_color, ctx, child_hashes)

            if child_val < value:
                value = child_val
                best_idx = i
            beta = min(beta, value)
            if alpha >= beta:
                _record_killer(ctx.killers, depth, kind, path)
                _history_record(ctx.history, kind, path, depth)
                break

    # Store in transposition table
    if value <= orig_alpha:
        flag = _TT_UPPER
    elif value >= beta:
        flag = _TT_LOWER
    else:
        flag = _TT_EXACT
    _tt_store(ctx.tt, h, depth, value, flag, best_idx)

    return value


def _search_best_move(
    board: Board,
    color: str | Color,
    max_depth: int,
    deadline: float | None = None,
    ctx: SearchContext | None = None,
) -> AIMove | None:
    """Iterative deepening search with alpha-beta minimax.

    If deadline (monotonic perf_counter seconds) is set and elapses mid-search,
    returns the best move from the last fully completed depth iteration.
    A depth-1 sweep is always attempted first to guarantee a legal move.

    Also updates module-level _last_search_score with the minimax value
    of the returned move from `color`'s perspective (backward-compat).
    The same value is stored in ctx.last_score for callers using the new API.

    If ctx is None the module-level _default_ctx is used, which replicates
    the old shared-global behaviour (TT persists across all calls in the
    same process, killers/history are reset per call). Pass an explicit
    SearchContext for isolation (e.g. parallel tournament games).
    """
    global _last_search_score

    # Use module-level default context when none supplied — matches the old
    # behaviour where _tt / _killers / _history were shared module globals.
    if ctx is None:
        ctx = _default_ctx

    ctx.killers.clear()
    ctx.history.clear()
    ctx.deadline = deadline
    ctx.last_score = float("nan")

    moves = _generate_all_moves(board, color)
    if not moves:
        _last_search_score = float("nan")
        return None

    opp = _opponent(color)
    best_kind, best_path = moves[0]
    # Snapshot of the last fully completed depth's best-move set and its
    # backed-up score. Score is from `color`'s (root's) perspective.
    last_complete_best: list[tuple[str, list[tuple[int, int]]]] = [moves[0]]
    last_complete_score: float = float("nan")

    try:
        # Iterative deepening: search at increasing depths
        for depth in range(1, max_depth + 1):
            moves = _order_moves(moves, board, color, ctx.history)

            # Put previous best move first
            for i, (k, p) in enumerate(moves):
                if k == best_kind and p == best_path:
                    if i > 0:
                        moves.insert(0, moves.pop(i))
                    break

            best_score = -float("inf")
            best_moves_at_depth: list[tuple[str, list[tuple[int, int]]]] = []
            alpha = -float("inf")
            beta = float("inf")

            try:
                for kind, path in moves:
                    child = _apply_move(board, kind, path)
                    score = _alphabeta(child, depth - 1, alpha, beta, False, opp, color, ctx)

                    if score > best_score:
                        best_score = score
                        best_moves_at_depth = [(kind, path)]
                        alpha = max(alpha, score)
                    elif score == best_score:
                        best_moves_at_depth.append((kind, path))
            except SearchCancelledError:
                # Discard this partial depth; keep last fully completed result.
                break

            if best_moves_at_depth:
                best_kind, best_path = best_moves_at_depth[0]
                last_complete_best = best_moves_at_depth[:]
                last_complete_score = best_score
    finally:
        ctx.deadline = None

    # Final selection: among moves with the same minimax score from the
    # last fully completed depth, prefer the one the move orderer ranks
    # highest. This gives more purposeful tie-breaking than random.choice
    # (which earlier allowed real blunders to be picked when fail-hard
    # quiescence tied a blunder with the real best move — that underlying
    # bug is fixed, but deterministic ordered tie-break is strictly
    # better even in the clean case). A tiny bit of randomness is kept
    # by shuffling within each priority bucket so repeated self-play
    # still produces variety.
    ctx.last_score = last_complete_score
    _last_search_score = last_complete_score  # backward-compat module alias
    if len(last_complete_best) == 1:
        kind, path = last_complete_best[0]
    else:
        ordered = _order_moves(last_complete_best, board, color, ctx.history)
        # Group by priority (we recompute here lightly; _order_moves is
        # already a stable sort so equal-priority moves preserve their
        # input order — shuffle within groups via random.choice on the
        # top priority group only).
        top_kind, top_path = ordered[0]
        # Find all moves tied at top of ordered list — identify by
        # re-computing priority. Simpler: shuffle top-3 at most to keep
        # variety without risking blunders.
        top_group = ordered[: min(3, len(ordered))]
        kind, path = random.choice(top_group)
    return AIMove(kind, path)


# ===========================================================================
# AI ENGINE
# ===========================================================================

# Difficulty → base search depth mapping
_DIFFICULTY_DEPTH = {1: 3, 2: 5, 3: 7}


class AIEngine:
    """Encapsulates AI search parameters.

    Inner search functions remain module-level for performance
    (no method dispatch overhead in hot paths).

    By default uses the module-level _default_ctx (shared across all
    engines in the same process) to reproduce the original behaviour where
    a single TT was shared by all searches. Pass an explicit ctx to
    find_move / _search_best_move for full isolation (e.g. parallel games).
    """

    def __init__(self, difficulty: int = 2, color: Color = Color.BLACK, search_depth: int = 0):
        self.difficulty = difficulty
        self.color = color
        self.search_depth = search_depth  # 0 = auto (derived from difficulty)

    def find_move(self, board: Board, deadline: float | None = None) -> AIMove | None:
        """Find the best move for the current board state.

        Args:
            board: Position to search.
            deadline: Optional absolute monotonic time (time.perf_counter seconds).
                If set and elapsed during search, returns best move from the
                last fully completed iterative-deepening depth. A depth-1
                sweep is always attempted, so a legal move is always returned
                if any exists.
        """
        base = self.search_depth if self.search_depth > 0 else _DIFFICULTY_DEPTH.get(self.difficulty, 5)
        depth = adaptive_depth(base, board)
        return _search_best_move(board, self.color, depth, deadline=deadline)


def adaptive_depth(base_depth: int, board: Board) -> int:
    """Adjust the requested search depth based on piece count.

    - Crowded positions (>16 pieces): cap at 4. Branching is huge and the
      extra plies pay poorly in the opening.
    - Sparse endgames (<=6 pieces): bump by +1 up to a hard cap of 8.

    The endgame boost was +2 until self-play profiling showed that in
    king-heavy endgames (branching factor ~10 per king) the extra ply
    blew up wall-clock budgets and caused ~3% of endgame moves to hit
    the per-move timeout. +1 is the conservative setting; callers that
    want deeper endgame search can pass a larger base_depth explicitly.
    """
    piece_count = board.count_pieces(Color.BLACK) + board.count_pieces(Color.WHITE)
    if piece_count > 16 and base_depth > 4:
        return 4
    if piece_count <= 6 and base_depth < 8:
        return min(base_depth + 1, 8)
    return base_depth


# ===========================================================================
# MAIN ENTRY POINT (backward-compatible wrapper)
# ===========================================================================


def computer_move(
    board: Board,
    difficulty: int = 2,
    color: str | Color = Color.BLACK,
    depth: int | None = None,
) -> AIMove | None:
    """Compute the AI's move.

    Backward-compatible wrapper around AIEngine. Prefer AIEngine for new code.
    """
    engine = AIEngine(difficulty=difficulty, color=Color(color))
    if depth is not None and depth > 0:
        engine.search_depth = depth
    return engine.find_move(board)
