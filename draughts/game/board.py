"""Board representation and game rules for Russian draughts.

Uses NumPy int8 array with signed encoding:
    BLACK=1, BLACK_KING=2, WHITE=-1, WHITE_KING=-2, EMPTY=0

Coordinate system (0-indexed):
    - grid[y, x], y=row (0=top), x=column (0=left)
    - Active cells: x%2 != y%2 (dark squares)
    - Notation: columns a-h (x=0..7), rows 8-1 (y=0..7)
    - (0,0)=a8, (7,7)=h1
"""

from __future__ import annotations

import numpy as np

from draughts.config import (
    BLACK,
    BLACK_KING,
    BOARD_SIZE,
    CHAR_TO_INT,
    DARK_SQUARES,
    DIAGONAL_DIRECTIONS,
    EMPTY,
    INT_TO_CHAR,
    WHITE,
    WHITE_KING,
)

# Promotion rows (0-indexed)
_WHITE_PROMOTE_ROW = 0  # white promotes at top row
_BLACK_PROMOTE_ROW = BOARD_SIZE - 1  # black promotes at bottom row


class Board:
    """Russian draughts board (8x8).

    Coordinate system (0-indexed):
        - grid[y, x], y=row (0=top), x=column (0=left)
        - Active cells: x%2 != y%2 (dark squares)
        - Pieces: int8 encoding (see config.py)
        - Notation: columns a-h, rows 8-1 top to bottom
    """

    ROWS = BOARD_SIZE
    COLS = BOARD_SIZE

    EMPTY = EMPTY
    BLACK = BLACK
    BLACK_KING = BLACK_KING
    WHITE = WHITE
    WHITE_KING = WHITE_KING

    DIAGONAL_DIRECTIONS = DIAGONAL_DIRECTIONS

    def __init__(self, empty: bool = False):
        self.grid: np.ndarray = np.zeros((self.ROWS, self.COLS), dtype=np.int8)
        if not empty:
            self._setup_initial_position()

    def _setup_initial_position(self) -> None:
        """Set up standard starting position for Russian draughts."""
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                if x % 2 != y % 2:
                    if y <= 2:
                        self.grid[y, x] = BLACK
                    elif y >= 5:
                        self.grid[y, x] = WHITE

    @staticmethod
    def _is_dark(x: int, y: int) -> bool:
        """Check if cell (x, y) is a dark square (playable)."""
        return x % 2 != y % 2

    def piece_at(self, x: int, y: int) -> int:
        """Get piece at position (x, y). Returns EMPTY for out-of-bounds."""
        if not self._in_bounds(x, y):
            return EMPTY
        return int(self.grid[y, x])

    def place_piece(self, x: int, y: int, piece: int | str) -> None:
        """Place a piece at position (x, y). Accepts int or legacy char."""
        if self._in_bounds(x, y):
            if isinstance(piece, str):
                self.grid[y, x] = CHAR_TO_INT[piece]
            else:
                self.grid[y, x] = piece

    def _in_bounds(self, x: int, y: int) -> bool:
        """Check if coordinates are within board bounds (0-7)."""
        return 0 <= x < self.COLS and 0 <= y < self.ROWS

    @staticmethod
    def is_black(piece: int) -> bool:
        return int(piece) > 0

    @staticmethod
    def is_white(piece: int) -> bool:
        return int(piece) < 0

    @staticmethod
    def is_king(piece: int) -> bool:
        return abs(int(piece)) == 2

    @staticmethod
    def is_enemy(piece1: int, piece2: int) -> bool:
        """Check if two pieces belong to opposite sides."""
        return int(piece1) * int(piece2) < 0

    def to_position_string(self) -> str:
        """Get 32-char string representation (dark squares only, row by row)."""
        return "".join(INT_TO_CHAR[int(self.grid[y, x])] for y, x in DARK_SQUARES)

    def load_from_position_string(self, s: str) -> None:
        """Load board state from 32-char string."""
        if len(s) != 32:
            raise ValueError(f"Expected 32 characters, got {len(s)}")
        for idx, (y, x) in enumerate(DARK_SQUARES):
            self.grid[y, x] = CHAR_TO_INT[s[idx]]

    def copy(self) -> Board:
        """Create a deep copy of the board."""
        new_board = Board(empty=True)
        new_board.grid = self.grid.copy()
        return new_board

    def count_pieces(self, color: str) -> int:
        """Count pieces of given color ('b' for black side, 'w' for white side)."""
        return int(np.count_nonzero(self.grid > 0)) if color == "b" else int(np.count_nonzero(self.grid < 0))

    # --- Notation ---

    @staticmethod
    def pos_to_notation(x: int, y: int) -> str:
        """Convert (x, y) to chess notation like 'a8', 'h1'."""
        col = chr(ord("a") + x)
        row = str(BOARD_SIZE - y)
        return f"{col}{row}"

    @staticmethod
    def notation_to_pos(notation: str) -> tuple[int, int]:
        """Convert notation like 'a8' to (x, y)."""
        x = ord(notation[0]) - ord("a")
        y = BOARD_SIZE - int(notation[1])
        return x, y

    # --- Move validation ---

    def get_valid_moves(self, x: int, y: int) -> list[tuple[int, int]]:
        """Get list of valid non-capture moves for piece at (x, y)."""
        piece = self.piece_at(x, y)
        if piece == EMPTY:
            return []
        if self.is_king(piece):
            return self._get_king_moves(x, y)
        return self._get_pawn_moves(x, y, piece)

    def _get_pawn_moves(self, x: int, y: int, piece: int) -> list[tuple[int, int]]:
        """Get non-capture moves for a regular piece."""
        moves = []
        dy = -1 if self.is_white(piece) else 1
        for dx in (-1, 1):
            nx, ny = x + dx, y + dy
            if self._in_bounds(nx, ny) and self.grid[ny, nx] == EMPTY:
                moves.append((nx, ny))
        return moves

    def _get_king_moves(self, x: int, y: int) -> list[tuple[int, int]]:
        """Get non-capture moves for a king (any distance along diagonal)."""
        moves = []
        for dy, dx in DIAGONAL_DIRECTIONS:
            nx, ny = x + dx, y + dy
            while self._in_bounds(nx, ny) and self.grid[ny, nx] == EMPTY:
                moves.append((nx, ny))
                nx += dx
                ny += dy
        return moves

    # --- Capture logic ---

    def get_captures(self, x: int, y: int) -> list[list[tuple[int, int]]]:
        """Get all possible capture sequences for piece at (x, y).

        Returns list of capture paths. Each path is a list of positions
        the piece visits (including start position).
        """
        piece = self.piece_at(x, y)
        if piece == EMPTY:
            return []

        paths: list[list[tuple[int, int]]] = []
        if self.is_king(piece):
            self._find_king_captures(x, y, piece, [(x, y)], set(), paths)
        else:
            self._find_pawn_captures(x, y, piece, [(x, y)], set(), paths)
        return paths

    def _find_pawn_captures(
        self,
        x: int,
        y: int,
        piece: int,
        path: list,
        captured: set,
        results: list,
    ) -> None:
        """Recursively find all capture sequences for a pawn."""
        found = False
        for dy, dx in DIAGONAL_DIRECTIONS:
            mx, my = x + dx, y + dy
            lx, ly = x + 2 * dx, y + 2 * dy

            if not self._in_bounds(lx, ly):
                continue

            enemy = self.grid[my, mx]
            landing = self.grid[ly, lx]

            if self.is_enemy(piece, enemy) and (mx, my) not in captured and (landing == EMPTY or (lx, ly) == path[0]):
                found = True
                new_captured = captured | {(mx, my)}
                new_path = [*path, (lx, ly)]

                promoted = (self.is_white(piece) and ly == _WHITE_PROMOTE_ROW) or (
                    self.is_black(piece) and ly == _BLACK_PROMOTE_ROW
                )

                if promoted:
                    results.append(new_path)
                else:
                    self._find_pawn_captures(lx, ly, piece, new_path, new_captured, results)

        if not found and len(path) > 1:
            results.append(path)

    def _find_king_captures(
        self,
        x: int,
        y: int,
        piece: int,
        path: list,
        captured: set,
        results: list,
    ) -> None:
        """Recursively find all capture sequences for a king."""
        found = False
        for dy, dx in DIAGONAL_DIRECTIONS:
            nx, ny = x + dx, y + dy
            while self._in_bounds(nx, ny) and self.grid[ny, nx] == EMPTY:
                nx += dx
                ny += dy

            if not self._in_bounds(nx, ny):
                continue

            enemy = self.grid[ny, nx]
            if not self.is_enemy(piece, enemy) or (nx, ny) in captured:
                continue

            lx, ly = nx + dx, ny + dy
            while self._in_bounds(lx, ly) and (self.grid[ly, lx] == EMPTY or (lx, ly) == path[0]):
                if self.grid[ly, lx] == EMPTY or (lx, ly) == path[0]:
                    found = True
                    new_captured = captured | {(nx, ny)}
                    new_path = [*path, (lx, ly)]
                    self._find_king_captures(lx, ly, piece, new_path, new_captured, results)
                lx += dx
                ly += dy

        if not found and len(path) > 1:
            results.append(path)

    def has_any_capture(self, color: str) -> bool:
        """Check if given side has any capture available."""
        positions = np.argwhere(self.grid > 0) if color == "b" else np.argwhere(self.grid < 0)
        for pos in positions:
            y, x = int(pos[0]), int(pos[1])
            if self.get_captures(x, y):
                return True
        return False

    def has_any_move(self, color: str) -> bool:
        """Check if given side has any legal move (capture or regular)."""
        positions = np.argwhere(self.grid > 0) if color == "b" else np.argwhere(self.grid < 0)
        for pos in positions:
            y, x = int(pos[0]), int(pos[1])
            if self.get_captures(x, y) or self.get_valid_moves(x, y):
                return True
        return False

    def execute_move(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """Execute a simple (non-capture) move."""
        piece = self.grid[y1, x1]
        self.grid[y1, x1] = EMPTY

        if piece == WHITE and y2 == _WHITE_PROMOTE_ROW:
            piece = WHITE_KING
        elif piece == BLACK and y2 == _BLACK_PROMOTE_ROW:
            piece = BLACK_KING

        self.grid[y2, x2] = piece

    def execute_capture_path(self, path: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Execute a capture sequence along the given path.

        Returns list of captured piece positions.
        """
        piece = self.grid[path[0][1], path[0][0]]
        captured_positions = []

        for i in range(len(path) - 1):
            x1, y1 = path[i]
            x2, y2 = path[i + 1]

            dx = 1 if x2 > x1 else -1
            dy = 1 if y2 > y1 else -1
            cx, cy = x1 + dx, y1 + dy
            while (cx, cy) != (x2, y2):
                if self.grid[cy, cx] != EMPTY:
                    captured_positions.append((cx, cy))
                    break
                cx += dx
                cy += dy

        self.grid[path[0][1], path[0][0]] = EMPTY

        for cx, cy in captured_positions:
            self.grid[cy, cx] = EMPTY

        final_x, final_y = path[-1]
        if piece == WHITE and final_y == _WHITE_PROMOTE_ROW:
            piece = WHITE_KING
        elif piece == BLACK and final_y == _BLACK_PROMOTE_ROW:
            piece = BLACK_KING

        self.grid[final_y, final_x] = piece
        return captured_positions

    def dangerous_position(self, x: int, y: int, color: str) -> bool:
        """Check if piece at (x, y) is under attack."""
        piece = self.grid[y, x]
        if piece == EMPTY:
            return False

        for dy, dx in DIAGONAL_DIRECTIONS:
            ax, ay = x + dx, y + dy
            bx, by = x - dx, y - dy

            if not self._in_bounds(ax, ay) or not self._in_bounds(bx, by):
                continue

            attacker = self.grid[ay, ax]
            landing = self.grid[by, bx]

            if self.is_enemy(piece, attacker) and landing == EMPTY:
                return True

        for dy, dx in DIAGONAL_DIRECTIONS:
            nx, ny = x + dx, y + dy
            while self._in_bounds(nx, ny) and self.grid[ny, nx] == EMPTY:
                nx += dx
                ny += dy
            if self._in_bounds(nx, ny):
                attacker = self.grid[ny, nx]
                if self.is_enemy(piece, attacker) and self.is_king(attacker):
                    bx, by = x - dx, y - dy
                    if self._in_bounds(bx, by) and self.grid[by, bx] == EMPTY:
                        return True

        return False

    def is_diagonal_clear(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        """Check if diagonal path between two squares is clear."""
        if x1 == x2 and y1 == y2:
            return True
        dx = 1 if x2 > x1 else -1
        dy = 1 if y2 > y1 else -1
        cx, cy = x1 + dx, y1 + dy
        while (cx, cy) != (x2, y2):
            if self.grid[cy, cx] != EMPTY:
                return False
            cx += dx
            cy += dy
        return True

    def __repr__(self) -> str:
        lines = []
        lines.append("  a b c d e f g h")
        for y in range(BOARD_SIZE):
            row = [str(BOARD_SIZE - y)]
            for x in range(BOARD_SIZE):
                piece = int(self.grid[y, x])
                row.append(INT_TO_CHAR.get(piece, "."))
            lines.append(" ".join(row))
        return "\n".join(lines)
