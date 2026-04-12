"""Move generation and ordering."""

from __future__ import annotations

import numpy as np

from draughts.config import BOARD_SIZE, Color
from draughts.game.ai.eval import (
    _CENTER_MASK,
    _find_pieces,
)
from draughts.game.ai.state import _history_score
from draughts.game.board import Board

# Promotion rows (0-indexed)
_WHITE_PROMOTE_ROW = 0
_BLACK_PROMOTE_ROW = BOARD_SIZE - 1


# ---------------------------------------------------------------------------
# Move generation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Move ordering
# ---------------------------------------------------------------------------


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
