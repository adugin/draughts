"""Static evaluation — vectorized position scoring, eval tables, and helpers.

Also contains shared board-scanning utilities used by both eval and move
generation (_find_pieces, _count_pieces, _opponent, _is_on_board,
_max_diagonal_reach, _scan_diagonal, _is_path_clear).
"""

from __future__ import annotations

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

# ---------------------------------------------------------------------------
# Board helpers shared by eval and move generation
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
# Precomputed advancement tables (0-indexed, 8x8)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Endgame / danger constants
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

_OFF_DIAGONAL_PENALTY = 0.5

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
