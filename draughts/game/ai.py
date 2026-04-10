"""AI module for Russian draughts — NumPy-based engine with deterministic enumeration.

Replaces the original Monte Carlo random sampling with exhaustive capture/move
enumeration and vectorized scoring. Three priority levels:
1. SeeBeat  — mandatory captures (deterministic best-path selection)
2. Combination — tactical sacrifices
3. Action — normal moves (heuristic scoring)

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

LOOKAHEAD_DEPTH = 1
LEARNING_SCORE_THRESHOLD = 1

# Board slice for the active 8x8 area (1-indexed grid is 9x9)
_BOARD_SLICE = (slice(1, BOARD_SIZE + 1), slice(1, BOARD_SIZE + 1))


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
    """Maximum diagonal distance from (x, y) to any board edge."""
    return max(BOARD_SIZE - y, y - 1, BOARD_SIZE - x, x - 1)


def _find_pieces(grid: np.ndarray, color: str) -> list[tuple[int, int]]:
    """Find all piece positions for a color. Returns list of (x, y)."""
    positions = np.argwhere(grid > 0) if color == "b" else np.argwhere(grid < 0)
    return [(int(p[1]), int(p[0])) for p in positions]


def _count_pieces(color: str, grid: np.ndarray) -> int:
    board_area = grid[_BOARD_SLICE]
    if color == "b":
        return int(np.count_nonzero(board_area > 0))
    return int(np.count_nonzero(board_area < 0))


# ---------------------------------------------------------------------------
# Scan diagonal — count pieces on path between two squares
# ---------------------------------------------------------------------------


def _scan_diagonal(x1: int, y1: int, x2: int, y2: int, color: str, grid: np.ndarray) -> tuple[int, int, int]:
    """Check how many pieces lie on diagonal (x1,y1)->(x2,y2) exclusive.

    Args:
        color: 'b' or 'w' — the side whose piece we look for.

    Returns:
        (count, bx, by) — count of non-empty cells on path,
        bx/by is position of found *color* piece (if exactly one).
    """
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
    """Check if diagonal path between two squares is clear."""
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
                if piece * attacker < 0:  # enemy
                    return True
                if piece * attacker > 0:  # friend
                    close[di] = True
            else:
                cell = int(grid[ay, ax])
                enemy_king = WHITE_KING if color == "b" else BLACK_KING
                if color == "b":
                    if cell in (1, 2, -1):  # black pawn, black king, white pawn — block
                        close[di] = True
                    elif not close[di] and cell == enemy_king:
                        return True
                else:
                    if cell in (-1, -2, 1):  # white pawn, white king, black pawn — block
                        close[di] = True
                    elif not close[di] and cell == enemy_king:
                        return True
    return False


def _is_unsafe_after_capture(
    x1: int, y1: int, x2: int, y2: int, bx: int, by: int, grid: np.ndarray, color: str
) -> bool:
    """Check if piece landing at (x2,y2) after capturing at (bx,by) is under attack."""
    enemy_king = WHITE_KING if color == "b" else BLACK_KING

    close = [False, False, False, False]

    for rr in range(1, _max_diagonal_reach(x2, y2) + 1):
        for di in range(4):
            dx, dy = DIAGONAL_DIRECTIONS[di]
            ax, ay = x2 + rr * dx, y2 + rr * dy
            ex, ey = x2 - rr * dx, y2 - rr * dy

            if not _is_on_board(ax, ay) or not _is_on_board(ex, ey):
                continue

            if rr == 1:
                attacker = int(grid[ay, ax])
                landing = int(grid[ey, ex])
                landing_free = landing == 0 or (ex == bx and ey == by)
                # Check if attacker is enemy
                piece_sign = 1 if color == "b" else -1
                if attacker * piece_sign < 0 and landing_free:
                    return True
            else:
                cell = int(grid[ay, ax])
                if cell != enemy_king and cell != 0 and not (ax == bx and ay == by):
                    close[di] = True
                elif not close[di] and cell == enemy_king:
                    landing = int(grid[y2 - dy, x2 - dx])
                    landing_free = landing == 0 or (x2 - dx == bx and y2 - dy == by)
                    if landing_free:
                        return True
    return False


def _any_piece_threatened(color: str, grid: np.ndarray) -> bool:
    """Check if any piece of given color is under attack."""
    return any(_dangerous_position(x, y, grid, color) for x, y in _find_pieces(grid, color))


# ---------------------------------------------------------------------------
# Position helpers
# ---------------------------------------------------------------------------


def _is_near_edge_or_ally(x: int, y: int, grid: np.ndarray) -> bool:
    """Check if position is near edge or friendly piece."""
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
    """Check if pawn on column 2 or 7 is vulnerable to flank attack."""
    if y + 2 > BOARD_SIZE:
        return False
    if x == 2 and int(grid[y + 2, 2]) < 0 and grid[y + 1, 1] == 0:
        return True
    return bool(x == BOARD_SIZE - 1 and int(grid[y + 2, x]) < 0 and grid[y + 1, BOARD_SIZE] == 0)


def _has_single_capture_only(grid: np.ndarray) -> bool:
    """Return True if white has at most one capturable piece (for Combination)."""
    first = False
    for y in range(1, BOARD_SIZE + 1):
        for x in range(1, BOARD_SIZE + 1):
            if grid[y, x] > 0:  # black piece
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


# ---------------------------------------------------------------------------
# Capture path scoring
# ---------------------------------------------------------------------------


def _evaluate_capture_path(
    board: Board,
    path: list[tuple[int, int]],
    color: str,
    use_base: bool,
    learning_db: LearningDB | None,
) -> float:
    """Score a capture path by simulating it on a board copy.

    Scoring:
        +1 per captured piece
        +2 for capturing a king
        +2 for promotion
        +1 for safe landing
        +3/-3 for learning DB
    """
    sim = board.copy()
    piece = sim.grid[path[0][1], path[0][0]]
    score = 0.0

    # Execute capture and count what was taken
    captured = sim.execute_capture_path(path)
    for cx, cy in captured:
        cap_piece = board.grid[cy, cx]  # read from original board
        score += 1.0
        if abs(int(cap_piece)) == 2:  # king
            score += 2.0

    # Promotion bonus
    final_x, final_y = path[-1]
    final_piece = sim.grid[final_y, final_x]
    if abs(int(final_piece)) == 2 and abs(int(piece)) == 1:
        score += 2.0

    # Safety of landing position
    if not _dangerous_position(final_x, final_y, sim.grid, color):
        score += 1.0

    # Learning DB
    if use_base:
        pos_str = sim.to_position_string()
        db_result = _lookup_position(learning_db, pos_str)
        if db_result == "good":
            score += 3.0
        elif db_result == "bad":
            score -= 3.0

    return score


# ---------------------------------------------------------------------------
# Virtual captures — deterministic best capture for lookahead
# ---------------------------------------------------------------------------


def _virtual_capture(grid: np.ndarray, color: str, use_base: bool, learning_db: LearningDB | None) -> int:
    """Find and execute the best capture for a color on a grid copy.

    Modifies grid in-place. Returns score of best capture, 0 if none.
    """
    board = Board(empty=True)
    board.grid = grid  # share reference — we'll modify in place

    best_score = 0.0
    best_path = None

    for x, y in _find_pieces(grid, color):
        paths = board.get_captures(x, y)
        for path in paths:
            # Score without modifying grid — use a temp copy
            temp_board = Board(empty=True)
            temp_board.grid = grid.copy()
            score = _evaluate_capture_path(temp_board, path, color, use_base, learning_db)
            if score > best_score:
                best_score = score
                best_path = path

    if best_path is not None:
        # Execute on the shared grid
        board.execute_capture_path(best_path)

    return int(best_score)


# ===========================================================================
# SEEBEAT — mandatory captures with deterministic enumeration
# ===========================================================================


def _see_beat(board: Board, color: str, use_base: bool, learning_db: LearningDB | None) -> AIMove | None:
    """Find the best mandatory capture using exhaustive enumeration.

    Enumerates ALL capture paths for all pieces, scores each,
    and returns the highest-scored path.
    """
    grid = board.grid
    best_score = -100.0
    best_path = None

    for x, y in _find_pieces(grid, color):
        paths = board.get_captures(x, y)
        for path in paths:
            score = _evaluate_capture_path(board, path, color, use_base, learning_db)
            if score > best_score:
                best_score = score
                best_path = path

    if best_path is None:
        return None
    return AIMove("capture", best_path)


# ===========================================================================
# COMBINATION — tactical sacrifices
# ===========================================================================


def _combination(board: Board, color: str, use_base: bool, learning_db: LearningDB | None) -> AIMove | None:
    """Find a profitable sacrifice move.

    Only considers regular pieces (not kings), only if we have > 1 piece.
    """
    grid = board.grid
    my_pawn = BLACK if color == "b" else WHITE

    if _count_pieces(color, grid) <= 1:
        return None

    max_score = -100.0
    best_move = None

    forward_dirs = range(0, 2) if color == "b" else range(2, 4)
    enemy_color = "w" if color == "b" else "b"

    for x, y in _find_pieces(grid, color):
        if grid[y, x] != my_pawn:
            continue

        for di in forward_dirs:
            dx, dy = DIAGONAL_DIRECTIONS[di]
            tx, ty = x + dx, y + dy
            ex, ey = x + 2 * dx, y + 2 * dy
            if not _is_on_board(ex, ey) or not _is_on_board(tx, ty):
                continue
            if grid[ty, tx] != 0:
                continue
            enemy_piece = int(grid[ey, ex])
            # Check that piece beyond target is enemy
            if color == "b" and enemy_piece >= 0:
                continue
            if color == "w" and enemy_piece <= 0:
                continue

            # Simulate sacrifice
            sim_grid = grid.copy()
            sim_grid[y, x] = 0
            sim_grid[ty, tx] = my_pawn

            if not _has_single_capture_only(sim_grid):
                continue

            # Lookahead: opponent captures, then we capture
            score = 0.0
            for _depth in range(LOOKAHEAD_DEPTH):
                delta_opp = _virtual_capture(sim_grid, enemy_color, use_base, learning_db)
                if delta_opp == 0:
                    break
                score -= delta_opp
                delta_us = _virtual_capture(sim_grid, color, use_base, learning_db)
                if delta_us == 0:
                    break
                score += delta_us

            if score > max_score:
                max_score = score
                best_move = ((x, y), (tx, ty))

    if best_move is not None and max_score > 2 and _count_pieces(color, grid) > 1:
        return AIMove("sacrifice", [best_move[0], best_move[1]])
    return None


# ===========================================================================
# ACTION — normal move with heuristic scoring
# ===========================================================================


def _action(board: Board, color: str, use_base: bool, learning_db: LearningDB | None) -> AIMove | None:
    """Find the best normal (non-capture) move using heuristic evaluation."""
    grid = board.grid
    my_pawn = BLACK if color == "b" else WHITE
    my_king = BLACK_KING if color == "b" else WHITE_KING
    promote_row = BOARD_SIZE if color == "b" else 1
    enemy_color = "w" if color == "b" else "b"

    max_score = -100.0
    best_move = None
    found = False

    for x, y in _find_pieces(grid, color):
        piece = int(grid[y, x])

        if piece == my_pawn:
            # Pawn: enumerate forward moves
            forward_dirs = range(0, 2) if color == "b" else range(2, 4)

            for di in forward_dirs:
                dx, dy = DIAGONAL_DIRECTIONS[di]
                nx, ny = x + dx, y + dy
                if not _is_on_board(nx, ny) or grid[ny, nx] != 0:
                    continue

                score = 0.0
                sim_grid = grid.copy()

                was_side = _is_flank_vulnerable(x, y, sim_grid)
                was_danger = _any_piece_threatened(color, sim_grid)

                sim_grid[y, x] = 0
                sim_grid[ny, nx] = my_pawn

                if _is_near_edge_or_ally(nx, ny, sim_grid):
                    score += 0.5
                if was_side and not _is_flank_vulnerable(nx, ny, sim_grid):
                    score += 1.0
                if ny == promote_row:
                    score += 2.0
                if was_danger and not _any_piece_threatened(color, sim_grid):
                    score += 1.0
                if not _dangerous_position(nx, ny, sim_grid, color):
                    score += 1.5
                else:
                    score -= 2.0

                if use_base:
                    pos_str = _grid_to_position_string(sim_grid)
                    db_result = _lookup_position(learning_db, pos_str)
                    if db_result == "good":
                        score += 3.0
                    elif db_result == "bad":
                        score -= 3.0

                # Lookahead
                for _depth in range(LOOKAHEAD_DEPTH):
                    look_grid = sim_grid.copy()
                    delta_opp = _virtual_capture(look_grid, enemy_color, use_base, learning_db)
                    if delta_opp == 0:
                        break
                    score -= delta_opp
                    delta_us = _virtual_capture(look_grid, color, use_base, learning_db)
                    if delta_us == 0:
                        break
                    score += delta_us

                if score > max_score or (score == max_score and random.randint(0, 1) == 1):
                    found = True
                    max_score = score
                    best_move = ((x, y), (nx, ny))

        elif piece == my_king:
            # King: enumerate ALL valid moves deterministically
            valid_moves = board.get_valid_moves(x, y)

            for nx, ny in valid_moves:
                score = 0.0
                sim_grid = grid.copy()

                white_danger_before = _any_piece_threatened(enemy_color, sim_grid)
                black_danger_before = _any_piece_threatened(color, sim_grid)

                sim_grid[y, x] = 0
                sim_grid[ny, nx] = my_king

                white_danger_after = _any_piece_threatened(enemy_color, sim_grid)
                black_danger_after = _any_piece_threatened(color, sim_grid)
                new_pos_dangerous = _dangerous_position(nx, ny, sim_grid, color)

                # Heuristic scoring matching original
                if (
                    not white_danger_before and white_danger_after and not new_pos_dangerous and not black_danger_after
                ) or (not white_danger_before and white_danger_after and not new_pos_dangerous):
                    score += 1.0

                if not black_danger_after and not new_pos_dangerous:
                    score += 1.0

                if black_danger_before and not black_danger_after:
                    score += 2.0

                if new_pos_dangerous:
                    score -= 3.0

                if use_base:
                    pos_str = _grid_to_position_string(sim_grid)
                    db_result = _lookup_position(learning_db, pos_str)
                    if db_result == "good":
                        score += 3.0
                    elif db_result == "bad":
                        score -= 3.0

                # Lookahead
                for _depth in range(LOOKAHEAD_DEPTH):
                    look_grid = sim_grid.copy()
                    delta_opp = _virtual_capture(look_grid, enemy_color, use_base, learning_db)
                    if delta_opp == 0:
                        break
                    score -= delta_opp
                    delta_us = _virtual_capture(look_grid, color, use_base, learning_db)
                    if delta_us == 0:
                        break
                    score += delta_us

                if score > max_score:
                    found = True
                    max_score = score
                    best_move = ((x, y), (nx, ny))

    if not found or best_move is None:
        return None
    return AIMove("move", [best_move[0], best_move[1]])


# ===========================================================================
# MAIN ENTRY POINT
# ===========================================================================


def computer_move(
    board: Board,
    difficulty: int = 2,
    use_base: bool = False,
    learning_db: LearningDB | None = None,
    color: str = "b",
) -> AIMove | None:
    """Compute the AI's move.

    Priority:
        1. SeeBeat — mandatory captures (always checked first)
        2. Combination — tactical sacrifices (difficulty >= 2)
        3. Action — normal moves

    Args:
        board: Current board state.
        difficulty: 1=amateur, 2=normal, 3=professional.
        use_base: Whether to use the learning database.
        learning_db: LearningDB instance or None.
        color: 'b' or 'w' — which side the computer plays.

    Returns:
        An AIMove describing the chosen move, or None if no legal move exists.
    """
    # 1. Mandatory captures (SeeBeat)
    move = _see_beat(board, color, use_base, learning_db)
    if move is not None:
        return move

    # 2. Tactical sacrifices (Combination) — only on higher difficulties
    if difficulty >= 2:
        move = _combination(board, color, use_base, learning_db)
        if move is not None:
            return move

    # 3. Normal moves (Action)
    move = _action(board, color, use_base, learning_db)
    if move is not None:
        return move

    return None


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
    """Evaluate how much the position changed in favor of a given color.

    With signed encoding (BLACK=1/2, WHITE=-1/-2), the sum of the board
    directly reflects material balance: positive favors black.
    Kings worth 2, pawns worth 1 — matches the encoding values.
    """
    val1 = int(np.sum(field1[_BOARD_SLICE]))
    val2 = int(np.sum(field2[_BOARD_SLICE]))
    delta = val2 - val1  # positive means black improved
    return delta if color == "b" else -delta
