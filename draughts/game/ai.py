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

# Precomputed center mask (0-indexed, 8x8)
_CENTER_MASK = np.zeros((BOARD_SIZE, BOARD_SIZE), dtype=np.float32)
for _y in range(BOARD_SIZE):
    for _x in range(BOARD_SIZE):
        dist = max(abs(_x - 3.5), abs(_y - 3.5))
        _CENTER_MASK[_y, _x] = max(0, (3.5 - dist) / 3.5)

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
    """Ultra-fast evaluation — material + advancement + center."""
    has_black = bool(np.any(grid > 0))
    has_white = bool(np.any(grid < 0))

    if not has_black:
        return -1000.0 if color == Color.BLACK else 1000.0
    if not has_white:
        return 1000.0 if color == Color.BLACK else -1000.0

    total = 0.0

    black_pawns = int(np.count_nonzero(grid == 1))
    black_kings = int(np.count_nonzero(grid == 2))
    white_pawns = int(np.count_nonzero(grid == -1))
    white_kings = int(np.count_nonzero(grid == -2))

    material = (black_pawns * _PAWN_VALUE + black_kings * _KING_VALUE) - (
        white_pawns * _PAWN_VALUE + white_kings * _KING_VALUE
    )
    total += material

    total += float(np.sum(np.where(grid == 1, _BLACK_ADVANCE, 0.0))) * _ADVANCE_BONUS
    total -= float(np.sum(np.where(grid == -1, _WHITE_ADVANCE, 0.0))) * _ADVANCE_BONUS

    total += float(np.sum(np.where(grid > 0, _CENTER_MASK, 0.0))) * _CENTER_BONUS
    total -= float(np.sum(np.where(grid < 0, _CENTER_MASK, 0.0))) * _CENTER_BONUS

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
            (_x1, _y1), (x2, y2) = path
            promote_row = _BLACK_PROMOTE_ROW if color == Color.BLACK else _WHITE_PROMOTE_ROW
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
    color: str | Color,
    root_color: str | Color,
) -> float:
    """Alpha-beta pruning minimax search."""
    if depth <= 0:
        return _evaluate_fast(board.grid, root_color)

    moves = _generate_all_moves(board, color)

    if not moves:
        return -1000.0 if maximizing else 1000.0

    if depth >= 2:
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


def _search_best_move(board: Board, color: str | Color, depth: int) -> AIMove | None:
    """Search for the best move using alpha-beta minimax."""
    moves = _generate_all_moves(board, color)
    if not moves:
        return None

    moves = _order_moves(moves, board, color)

    opp = _opponent(color)
    best_score = -float("inf")
    best_moves: list[tuple[str, list[tuple[int, int]]]] = []

    alpha = -float("inf")
    beta = float("inf")

    for kind, path in moves:
        child = _apply_move(board, kind, path)
        score = _alphabeta(child, depth - 1, alpha, beta, False, opp, color)

        if kind != "capture":
            opp_moves = _generate_all_moves(child, opp)
            if any(k == "capture" for k, _ in opp_moves):
                score -= _PAWN_VALUE * 0.5

        if score > best_score:
            best_score = score
            best_moves = [(kind, path)]
            alpha = max(alpha, score)
        elif score == best_score:
            best_moves.append((kind, path))

    if not best_moves:
        return None
    kind, path = random.choice(best_moves)
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
    """

    def __init__(self, difficulty: int = 2, color: Color = Color.BLACK, search_depth: int = 0):
        self.difficulty = difficulty
        self.color = color
        self.search_depth = search_depth  # 0 = auto (derived from difficulty)

    def find_move(self, board: Board) -> AIMove | None:
        """Find the best move for the current board state."""
        depth = self.search_depth if self.search_depth > 0 else _DIFFICULTY_DEPTH.get(self.difficulty, 5)

        piece_count = board.count_pieces(Color.BLACK) + board.count_pieces(Color.WHITE)
        if piece_count > 16 and depth > 4:
            depth = 4
        elif piece_count <= 6 and depth < 8:
            depth = min(depth + 2, 10)

        return _search_best_move(board, self.color, depth)


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
