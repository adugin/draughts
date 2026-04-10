"""AI module for Russian draughts — NumPy engine with alpha-beta minimax.

Architecture:
    1. Static evaluation function (vectorized, fast)
    2. Alpha-beta pruning minimax search at configurable depth
    3. Move ordering for optimal pruning (captures first, then heuristics)
    4. Legacy 3-tier interface preserved: SeeBeat → Combination → Action

Piece encoding: BLACK=1, BLACK_KING=2, WHITE=-1, WHITE_KING=-2, EMPTY=0
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import numpy as np

from draughts.config import (
    BLACK,
    BLACK_KING,
    BOARD_SIZE,
    DIAGONAL_DIRECTIONS,
    INT_TO_CHAR,
    WHITE,
    WHITE_KING,
)
from draughts.game.board import Board

if TYPE_CHECKING:
    from draughts.game.learning import LearningDB

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LEARNING_SCORE_THRESHOLD = 1

# Board slice for the active 8x8 area (1-indexed grid is 9x9)
_BOARD_SLICE = (slice(1, BOARD_SIZE + 1), slice(1, BOARD_SIZE + 1))

# Precomputed: row indices for advancement scoring (0-indexed rows mapped to 1..8)
# Black pawns advance by increasing y; white by decreasing y
_BLACK_ADVANCE = np.zeros((9, 9), dtype=np.float32)
_WHITE_ADVANCE = np.zeros((9, 9), dtype=np.float32)
for _y in range(1, 9):
    for _x in range(1, 9):
        _BLACK_ADVANCE[_y, _x] = (_y - 1) / 7.0  # 0 at row 1, 1 at row 8
        _WHITE_ADVANCE[_y, _x] = (8 - _y) / 7.0  # 1 at row 1, 0 at row 8

# Evaluation weights — material MUST dominate positional bonuses.
# A pawn is worth 5.0; all positional bonuses combined should never
# exceed ~2.0 to prevent the AI from trading pieces for position.
_KING_VALUE = 15.0
_PAWN_VALUE = 5.0
_ADVANCE_BONUS = 0.15  # per-pawn advancement bonus (max ~0.15 per pawn)
_CENTER_BONUS = 0.05  # center control bonus
_SAFETY_BONUS = 0.1  # bonus for safe positions
_MOBILITY_WEIGHT = 0.02  # per-move mobility bonus
_THREAT_PENALTY = 0.5  # penalty per threatened piece

# Precomputed center mask (squares near the center get bonus)
_CENTER_MASK = np.zeros((9, 9), dtype=np.float32)
for _y in range(1, 9):
    for _x in range(1, 9):
        dist = max(abs(_x - 4.5), abs(_y - 4.5))
        _CENTER_MASK[_y, _x] = max(0, (3.5 - dist) / 3.5)


# ---------------------------------------------------------------------------
# Move representation
# ---------------------------------------------------------------------------


class AIMove:
    """Result returned by the AI.

    Attributes:
        kind: 'capture', 'move', or 'sacrifice'
        path: For captures — list of (x,y) positions the piece visits.
              For moves/sacrifices — [(x1,y1), (x2,y2)].
    """

    def __init__(self, kind: str, path: list[tuple[int, int]]):
        self.kind = kind
        self.path = path

    def __repr__(self) -> str:
        return f"AIMove({self.kind!r}, {self.path})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_on_board(x: int, y: int) -> bool:
    return 1 <= x <= BOARD_SIZE and 1 <= y <= BOARD_SIZE


def _max_diagonal_reach(x: int, y: int) -> int:
    return max(BOARD_SIZE - y, y - 1, BOARD_SIZE - x, x - 1)


def _find_pieces(grid: np.ndarray, color: str) -> list[tuple[int, int]]:
    """Find all piece positions for a color. Returns list of (x, y)."""
    positions = np.argwhere(grid > 0) if color == "b" else np.argwhere(grid < 0)
    return [(int(p[1]), int(p[0])) for p in positions]


def _count_pieces(color: str, grid: np.ndarray) -> int:
    board_area = grid[_BOARD_SLICE]
    return int(np.count_nonzero(board_area > 0)) if color == "b" else int(np.count_nonzero(board_area < 0))


def _opponent(color: str) -> str:
    return "w" if color == "b" else "b"


# ---------------------------------------------------------------------------
# Scan diagonal
# ---------------------------------------------------------------------------


def _scan_diagonal(x1: int, y1: int, x2: int, y2: int, color: str, grid: np.ndarray) -> tuple[int, int, int]:
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
        if (color == "b" and cell > 0) or (color == "w" and cell < 0):
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


def _dangerous_position(x: int, y: int, grid: np.ndarray, color: str) -> bool:
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
                enemy_king = WHITE_KING if color == "b" else BLACK_KING
                if color == "b":
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


def _any_piece_threatened(color: str, grid: np.ndarray) -> bool:
    return any(_dangerous_position(x, y, grid, color) for x, y in _find_pieces(grid, color))


def _count_threatened(color: str, grid: np.ndarray) -> int:
    """Count how many pieces of given color are under attack."""
    return sum(1 for x, y in _find_pieces(grid, color) if _dangerous_position(x, y, grid, color))


# ---------------------------------------------------------------------------
# Position helpers (for legacy Combination logic)
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
    return bool(x in (1, BOARD_SIZE) or y in (1, BOARD_SIZE))


def _is_flank_vulnerable(x: int, y: int, grid: np.ndarray) -> bool:
    if y + 2 > BOARD_SIZE:
        return False
    if x == 2 and int(grid[y + 2, 2]) < 0 and grid[y + 1, 1] == 0:
        return True
    return bool(x == BOARD_SIZE - 1 and int(grid[y + 2, x]) < 0 and grid[y + 1, BOARD_SIZE] == 0)


def _has_single_capture_only(grid: np.ndarray) -> bool:
    first = False
    for y in range(1, BOARD_SIZE + 1):
        for x in range(1, BOARD_SIZE + 1):
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
# Position string from raw grid
# ---------------------------------------------------------------------------


def _grid_to_position_string(grid: np.ndarray) -> str:
    from draughts.config import DARK_SQUARES as DS

    return "".join(INT_TO_CHAR[int(grid[y, x])] for y, x in DS)


# ---------------------------------------------------------------------------
# Learning DB lookup
# ---------------------------------------------------------------------------


def _lookup_position(learning_db: LearningDB | None, position: str) -> str | None:
    if learning_db is None:
        return None
    return learning_db.search(position)


# ===========================================================================
# STATIC EVALUATION — vectorized position scoring
# ===========================================================================


def evaluate_position(grid: np.ndarray, color: str) -> float:
    """Evaluate board position from perspective of `color`.

    Uses vectorized NumPy operations for speed:
    - Material count (pawns + kings with different values)
    - Advancement bonus (pawns closer to promotion)
    - Center control
    - Piece safety (threatened pieces penalty)

    Returns positive score if `color` is winning, negative if losing.
    """
    board_area = grid[_BOARD_SLICE]

    # Material (vectorized)
    black_pawns = int(np.count_nonzero(board_area == BLACK))
    black_kings = int(np.count_nonzero(board_area == BLACK_KING))
    white_pawns = int(np.count_nonzero(board_area == WHITE))
    white_kings = int(np.count_nonzero(board_area == WHITE_KING))

    # Terminal states
    black_total = black_pawns + black_kings
    white_total = white_pawns + white_kings
    if black_total == 0:
        return -1000.0 if color == "b" else 1000.0
    if white_total == 0:
        return 1000.0 if color == "b" else -1000.0

    # Material balance
    black_material = black_pawns * _PAWN_VALUE + black_kings * _KING_VALUE
    white_material = white_pawns * _PAWN_VALUE + white_kings * _KING_VALUE
    material = black_material - white_material

    # Advancement bonus (vectorized: multiply grid masks by advancement tables)
    black_pawn_mask = (grid == BLACK).astype(np.float32)
    white_pawn_mask = (grid == WHITE).astype(np.float32)
    black_advance = float(np.sum(black_pawn_mask * _BLACK_ADVANCE)) * _ADVANCE_BONUS
    white_advance = float(np.sum(white_pawn_mask * _WHITE_ADVANCE)) * _ADVANCE_BONUS
    advancement = black_advance - white_advance

    # Center control (vectorized)
    black_all = (grid > 0).astype(np.float32)
    white_all = (grid < 0).astype(np.float32)
    center = float(np.sum(black_all * _CENTER_MASK) - np.sum(white_all * _CENTER_MASK)) * _CENTER_BONUS

    # Mobility (count of available moves)
    temp_board = Board(empty=True)
    temp_board.grid = grid
    black_mobility = 0
    white_mobility = 0
    for x, y in _find_pieces(grid, "b"):
        black_mobility += len(temp_board.get_valid_moves(x, y)) + len(temp_board.get_captures(x, y))
    for x, y in _find_pieces(grid, "w"):
        white_mobility += len(temp_board.get_valid_moves(x, y)) + len(temp_board.get_captures(x, y))

    # No moves = loss
    if color == "b" and black_mobility == 0:
        return -1000.0
    if color == "w" and white_mobility == 0:
        return -1000.0

    mobility = (black_mobility - white_mobility) * _MOBILITY_WEIGHT

    # Threats (count threatened pieces)
    black_threatened = _count_threatened("b", grid)
    white_threatened = _count_threatened("w", grid)
    threats = (white_threatened - black_threatened) * _THREAT_PENALTY

    total = material + advancement + center + mobility + threats

    return total if color == "b" else -total


def _evaluate_fast(grid: np.ndarray, color: str) -> float:
    """Ultra-fast evaluation using integer arithmetic where possible.

    Avoids .astype() conversions — uses np.where() with precomputed weight tables.
    """
    board_area = grid[_BOARD_SLICE]

    # Count pieces using vectorized comparisons (single pass)
    has_black = bool(np.any(board_area > 0))
    has_white = bool(np.any(board_area < 0))

    if not has_black:
        return -1000.0 if color == "b" else 1000.0
    if not has_white:
        return 1000.0 if color == "b" else -1000.0

    # Material: use the signed encoding directly
    # BLACK=1, BLACK_KING=2, WHITE=-1, WHITE_KING=-2
    # For material: pawns=1pt, kings=3pt
    # abs(piece) tells us: 1=pawn, 2=king. Value = 1 + (abs-1)*2 = 2*abs-1
    # Actually: pawn=1, king=3. piece_value = 1 if abs==1 else 3
    # Simpler: iterate with precomputed weight map
    total = 0.0

    # Material score: count each piece type
    black_pawns = int(np.count_nonzero(board_area == 1))
    black_kings = int(np.count_nonzero(board_area == 2))
    white_pawns = int(np.count_nonzero(board_area == -1))
    white_kings = int(np.count_nonzero(board_area == -2))

    material = (black_pawns * _PAWN_VALUE + black_kings * _KING_VALUE) - (
        white_pawns * _PAWN_VALUE + white_kings * _KING_VALUE
    )
    total += material

    # Advancement: use np.where to avoid .astype()
    # Only pawns get advancement bonus; precomputed tables are float32
    total += float(np.sum(np.where(grid == 1, _BLACK_ADVANCE, 0.0))) * _ADVANCE_BONUS
    total -= float(np.sum(np.where(grid == -1, _WHITE_ADVANCE, 0.0))) * _ADVANCE_BONUS

    # Center control: use np.where
    total += float(np.sum(np.where(grid > 0, _CENTER_MASK, 0.0))) * _CENTER_BONUS
    total -= float(np.sum(np.where(grid < 0, _CENTER_MASK, 0.0))) * _CENTER_BONUS

    return total if color == "b" else -total


# ===========================================================================
# MOVE GENERATION — all legal moves for a position
# ===========================================================================


def _generate_all_moves(board: Board, color: str) -> list[tuple[str, list[tuple[int, int]]]]:
    """Generate all legal moves for a color.

    Returns list of (kind, path) tuples.
    Captures are mandatory in Russian draughts — if any exist, only captures are returned.
    """
    grid = board.grid
    captures = []
    normal_moves = []

    for x, y in _find_pieces(grid, color):
        # Captures
        cap_paths = board.get_captures(x, y)
        for path in cap_paths:
            captures.append(("capture", path))

        # Normal moves (only if no captures found)
        if not captures:
            moves = board.get_valid_moves(x, y)
            for nx, ny in moves:
                normal_moves.append(("move", [(x, y), (nx, ny)]))

    # Mandatory capture rule
    if captures:
        return captures
    return normal_moves


def _apply_move(board: Board, kind: str, path: list[tuple[int, int]]) -> Board:
    """Apply a move to a board copy and return the new board.

    Uses direct grid copy to avoid Board.__init__ overhead.
    """
    new_board = Board.__new__(Board)
    new_board.grid = board.grid.copy()
    if kind == "capture":
        new_board.execute_capture_path(path)
    else:
        (x1, y1), (x2, y2) = path[0], path[1]
        new_board.execute_move(x1, y1, x2, y2)
    return new_board


# ===========================================================================
# MOVE ORDERING — sort moves for better alpha-beta pruning
# ===========================================================================


def _order_moves(
    moves: list[tuple[str, list[tuple[int, int]]]],
    board: Board,
    color: str,
) -> list[tuple[str, list[tuple[int, int]]]]:
    """Order moves to improve alpha-beta pruning.

    Priority: captures first (by path length), then moves scored by quick heuristic.
    """
    if len(moves) <= 1:
        return moves

    scored = []
    for kind, path in moves:
        priority = 0.0
        if kind == "capture":
            # Longer capture chains are likely better
            priority = 100.0 + len(path) * 10.0
            # Bonus for capturing kings
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
            # Simple move heuristic: promotion moves first, center moves next
            (x1, y1), (x2, y2) = path
            promote_row = BOARD_SIZE if color == "b" else 1
            priority = 50.0 if y2 == promote_row else float(_CENTER_MASK[y2, x2]) * 10.0
        scored.append((priority, kind, path))

    scored.sort(key=lambda x: -x[0])
    return [(kind, path) for _, kind, path in scored]


# ===========================================================================
# ALPHA-BETA MINIMAX
# ===========================================================================


def _alphabeta(
    board: Board,
    depth: int,
    alpha: float,
    beta: float,
    maximizing: bool,
    color: str,
    root_color: str,
) -> float:
    """Alpha-beta pruning minimax search.

    Args:
        board: Current board state.
        depth: Remaining search depth.
        alpha: Best score for maximizer.
        beta: Best score for minimizer.
        maximizing: True if current player is the maximizing player.
        color: Current player's color ('b' or 'w').
        root_color: The AI's color (for evaluation perspective).

    Returns:
        Evaluation score from root_color's perspective.
    """
    # Terminal depth — use fast evaluation
    if depth <= 0:
        return _evaluate_fast(board.grid, root_color)

    # Generate moves
    moves = _generate_all_moves(board, color)

    # Terminal state — no moves available
    if not moves:
        # Current player has no moves = they lose
        return -1000.0 if maximizing else 1000.0

    # At depth >= 3, use fast eval; at depth < 3, full eval for leaf ordering
    use_ordering = depth >= 2
    if use_ordering:
        moves = _order_moves(moves, board, color)

    opp = _opponent(color)

    if maximizing:
        value = -float("inf")
        for kind, path in moves:
            child = _apply_move(board, kind, path)
            child_val = _alphabeta(child, depth - 1, alpha, beta, False, opp, root_color)
            value = max(value, child_val)
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return value
    else:
        value = float("inf")
        for kind, path in moves:
            child = _apply_move(board, kind, path)
            child_val = _alphabeta(child, depth - 1, alpha, beta, True, opp, root_color)
            value = min(value, child_val)
            beta = min(beta, value)
            if alpha >= beta:
                break
        return value


def _search_best_move(
    board: Board,
    color: str,
    depth: int,
    use_base: bool = False,
    learning_db: LearningDB | None = None,
) -> AIMove | None:
    """Search for the best move using alpha-beta minimax.

    Args:
        board: Current board state.
        color: AI's color.
        depth: Search depth (1 = evaluate immediate positions, etc.)
        use_base: Whether to use learning database for leaf evaluation.
        learning_db: Learning database instance.

    Returns:
        Best AIMove or None.
    """
    moves = _generate_all_moves(board, color)
    if not moves:
        return None

    # Order moves for better pruning
    moves = _order_moves(moves, board, color)

    opp = _opponent(color)
    best_score = -float("inf")
    best_moves: list[tuple[str, list[tuple[int, int]]]] = []

    alpha = -float("inf")
    beta = float("inf")

    for kind, path in moves:
        child = _apply_move(board, kind, path)
        score = _alphabeta(child, depth - 1, alpha, beta, False, opp, color)

        # Penalize moves that allow opponent captures — discourage unnecessary exchanges
        if kind != "capture":
            opp_moves = _generate_all_moves(child, opp)
            if any(k == "capture" for k, _ in opp_moves):
                score -= _PAWN_VALUE * 0.5  # significant penalty for walking into danger

        # Learning DB bonus at root level
        if use_base and learning_db is not None:
            pos_str = child.to_position_string()
            db_result = _lookup_position(learning_db, pos_str)
            if db_result == "good":
                score += 3.0
            elif db_result == "bad":
                score -= 3.0

        if score > best_score:
            best_score = score
            best_moves = [(kind, path)]
            alpha = max(alpha, score)
        elif score == best_score:
            best_moves.append((kind, path))

    # Break ties randomly
    if not best_moves:
        return None
    kind, path = random.choice(best_moves)
    return AIMove(kind, path)


# ===========================================================================
# MAIN ENTRY POINT
# ===========================================================================


def computer_move(
    board: Board,
    difficulty: int = 2,
    use_base: bool = False,
    learning_db: LearningDB | None = None,
    color: str = "b",
    depth: int | None = None,
) -> AIMove | None:
    """Compute the AI's move.

    Args:
        board: Current board state.
        difficulty: 1=amateur, 2=normal, 3=professional.
        use_base: Whether to use the learning database.
        learning_db: LearningDB instance or None.
        color: 'b' or 'w' — which side the computer plays.
        depth: Search depth override. If None, derived from difficulty:
               difficulty 1 → depth 3, difficulty 2 → depth 5, difficulty 3 → depth 7.

    Returns:
        An AIMove describing the chosen move, or None if no legal move exists.
    """
    # Determine search depth — minimum depth=3 so AI always sees opponent responses
    if depth is None:
        depth = {1: 3, 2: 5, 3: 7}.get(difficulty, 5)

    # Adaptive depth: reduce for complex positions to keep response time reasonable
    piece_count = board.count_pieces("b") + board.count_pieces("w")
    if piece_count > 16 and depth > 4:
        depth = 4  # opening positions have too many moves for deep search
    elif piece_count <= 6 and depth < 8:
        depth = min(depth + 2, 10)  # endgames can search deeper

    return _search_best_move(board, color, depth, use_base, learning_db)


# ===========================================================================
# LEARNING: record positions after game outcome
# ===========================================================================


def record_learning(
    learning_db: LearningDB,
    board_before: Board,
    board_after: Board,
    color: str,
    won: bool,
) -> None:
    """Record a position in the learning database after a game outcome."""
    from draughts.game.learning import invert_position

    pos_str = board_after.to_position_string()
    score = _appreciate(board_before.grid, board_after.grid, color)

    if won and score > LEARNING_SCORE_THRESHOLD:
        learning_db.add_good(pos_str)
        learning_db.save()
    elif not won and score < -LEARNING_SCORE_THRESHOLD:
        learning_db.add_bad(invert_position(pos_str))
        learning_db.save()


def _appreciate(field1: np.ndarray, field2: np.ndarray, color: str) -> int:
    """Evaluate how much the position changed in favor of a given color."""
    val1 = int(np.sum(field1[_BOARD_SLICE]))
    val2 = int(np.sum(field2[_BOARD_SLICE]))
    delta = val2 - val1
    return delta if color == "b" else -delta
