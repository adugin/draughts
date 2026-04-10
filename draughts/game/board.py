"""Board representation and game rules for Russian draughts."""


class Board:
    """Russian draughts board (8x8).

    Coordinate system (matching original Pascal code):
        - field[y][x], y=row (1=top), x=column (1=left)
        - Active cells: x%2 != y%2 (dark squares)
        - Pieces: 'b'=black, 'B'=black king, 'w'=white, 'W'=white king, 'n'=empty
        - Notation: columns a-h, rows 8-1 top to bottom
    """

    ROWS = 8
    COLS = 8

    # Piece constants
    EMPTY = 'n'
    BLACK = 'b'
    BLACK_KING = 'B'
    WHITE = 'w'
    WHITE_KING = 'W'

    # Four diagonal directions: (dy, dx)
    DIAGONAL_DIRECTIONS = [(-1, 1), (1, 1), (1, -1), (-1, -1)]

    def __init__(self, empty=False):
        if empty:
            self.grid = [[self.EMPTY] * (self.COLS + 1) for _ in range(self.ROWS + 1)]
        else:
            self.grid = [[self.EMPTY] * (self.COLS + 1) for _ in range(self.ROWS + 1)]
            self._setup_initial_position()

    def _setup_initial_position(self):
        """Set up standard starting position for Russian draughts."""
        for y in range(1, self.ROWS + 1):
            for x in range(1, self.COLS + 1):
                if self._is_dark(x, y):
                    if y <= 3:
                        self.grid[y][x] = self.BLACK
                    elif y >= 6:
                        self.grid[y][x] = self.WHITE

    @staticmethod
    def _is_dark(x: int, y: int) -> bool:
        """Check if cell (x, y) is a dark square (playable)."""
        return x % 2 != y % 2

    def piece_at(self, x: int, y: int) -> str:
        """Get piece at position (x, y). Returns EMPTY for light squares."""
        if not self._in_bounds(x, y):
            return self.EMPTY
        return self.grid[y][x]

    def place_piece(self, x: int, y: int, piece: str):
        """Place a piece at position (x, y)."""
        if self._in_bounds(x, y):
            self.grid[y][x] = piece

    def _in_bounds(self, x: int, y: int) -> bool:
        """Check if coordinates are within board bounds (1-8)."""
        return 1 <= x <= self.COLS and 1 <= y <= self.ROWS

    def is_black(self, piece: str) -> bool:
        return piece in (self.BLACK, self.BLACK_KING)

    def is_white(self, piece: str) -> bool:
        return piece in (self.WHITE, self.WHITE_KING)

    def is_king(self, piece: str) -> bool:
        return piece in (self.BLACK_KING, self.WHITE_KING)

    def is_enemy(self, piece1: str, piece2: str) -> bool:
        """Check if two pieces belong to opposite sides."""
        return (self.is_black(piece1) and self.is_white(piece2)) or \
               (self.is_white(piece1) and self.is_black(piece2))

    def to_position_string(self) -> str:
        """Get 32-char string representation (dark squares only, row by row).

        Matches original Pascal getstring() function.
        """
        result = []
        for y in range(1, self.ROWS + 1):
            for x in range(1, self.COLS + 1):
                if self._is_dark(x, y):
                    result.append(self.grid[y][x])
        return ''.join(result)

    def load_from_position_string(self, s: str):
        """Load board state from 32-char string."""
        if len(s) != 32:
            raise ValueError(f"Expected 32 characters, got {len(s)}")
        idx = 0
        for y in range(1, self.ROWS + 1):
            for x in range(1, self.COLS + 1):
                if self._is_dark(x, y):
                    self.grid[y][x] = s[idx]
                    idx += 1

    def copy(self) -> 'Board':
        """Create a deep copy of the board."""
        new_board = Board(empty=True)
        for y in range(1, self.ROWS + 1):
            for x in range(1, self.COLS + 1):
                new_board.grid[y][x] = self.grid[y][x]
        return new_board

    def count_pieces(self, color: str) -> int:
        """Count pieces of given color ('b' for black side, 'w' for white side)."""
        count = 0
        for y in range(1, self.ROWS + 1):
            for x in range(1, self.COLS + 1):
                piece = self.grid[y][x]
                if (color == 'b' and self.is_black(piece)) or (color == 'w' and self.is_white(piece)):
                    count += 1
        return count

    # --- Notation ---

    @staticmethod
    def pos_to_notation(x: int, y: int) -> str:
        """Convert (x, y) to chess notation like 'a8', 'h1'."""
        col = chr(ord('a') + x - 1)
        row = str(9 - y)
        return f"{col}{row}"

    @staticmethod
    def notation_to_pos(notation: str) -> tuple[int, int]:
        """Convert notation like 'a8' to (x, y)."""
        x = ord(notation[0]) - ord('a') + 1
        y = 9 - int(notation[1])
        return x, y

    # --- Move validation ---

    def get_valid_moves(self, x: int, y: int) -> list[tuple[int, int]]:
        """Get list of valid non-capture moves for piece at (x, y)."""
        piece = self.piece_at(x, y)
        if piece == self.EMPTY:
            return []

        moves = []
        if self.is_king(piece):
            moves = self._get_king_moves(x, y)
        else:
            moves = self._get_pawn_moves(x, y, piece)
        return moves

    def _get_pawn_moves(self, x: int, y: int, piece: str) -> list[tuple[int, int]]:
        """Get non-capture moves for a regular piece."""
        moves = []
        # White moves up (dy=-1), black moves down (dy=+1)
        dy = -1 if self.is_white(piece) else 1
        for dx in (-1, 1):
            nx, ny = x + dx, y + dy
            if self._in_bounds(nx, ny) and self.piece_at(nx, ny) == self.EMPTY:
                moves.append((nx, ny))
        return moves

    def _get_king_moves(self, x: int, y: int) -> list[tuple[int, int]]:
        """Get non-capture moves for a king (any distance along diagonal)."""
        moves = []
        for dy, dx in self.DIAGONAL_DIRECTIONS:
            nx, ny = x + dx, y + dy
            while self._in_bounds(nx, ny) and self.piece_at(nx, ny) == self.EMPTY:
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
        if piece == self.EMPTY:
            return []

        paths = []
        if self.is_king(piece):
            self._find_king_captures(x, y, piece, [(x, y)], set(), paths)
        else:
            self._find_pawn_captures(x, y, piece, [(x, y)], set(), paths)

        return paths

    def _find_pawn_captures(self, x: int, y: int, piece: str,
                            path: list, captured: set,
                            results: list):
        """Recursively find all capture sequences for a pawn."""
        found = False
        for dy, dx in self.DIAGONAL_DIRECTIONS:
            # Position of enemy piece
            mx, my = x + dx, y + dy
            # Landing position
            lx, ly = x + 2 * dx, y + 2 * dy

            if not self._in_bounds(lx, ly):
                continue

            enemy = self.piece_at(mx, my)
            landing = self.piece_at(lx, ly)

            if (self.is_enemy(piece, enemy) and
                    (mx, my) not in captured and
                    (landing == self.EMPTY or (lx, ly) == path[0])):
                found = True
                new_captured = captured | {(mx, my)}
                new_path = path + [(lx, ly)]

                # Check for promotion
                promoted = False
                if (self.is_white(piece) and ly == 1) or (self.is_black(piece) and ly == self.ROWS):
                    promoted = True

                if promoted:
                    # In Russian draughts, piece promotes and stops
                    results.append(new_path)
                else:
                    self._find_pawn_captures(lx, ly, piece, new_path,
                                             new_captured, results)

        if not found and len(path) > 1:
            results.append(path)

    def _find_king_captures(self, x: int, y: int, piece: str,
                            path: list, captured: set,
                            results: list):
        """Recursively find all capture sequences for a king."""
        found = False
        for dy, dx in self.DIAGONAL_DIRECTIONS:
            # King can fly over empty squares to reach enemy
            nx, ny = x + dx, y + dy
            while self._in_bounds(nx, ny) and self.piece_at(nx, ny) == self.EMPTY:
                nx += dx
                ny += dy

            if not self._in_bounds(nx, ny):
                continue

            enemy = self.piece_at(nx, ny)
            if not self.is_enemy(piece, enemy) or (nx, ny) in captured:
                continue

            # Land on any empty square after the enemy
            lx, ly = nx + dx, ny + dy
            while self._in_bounds(lx, ly) and (self.piece_at(lx, ly) == self.EMPTY or (lx, ly) == path[0]):
                if self.piece_at(lx, ly) == self.EMPTY or (lx, ly) == path[0]:
                    found = True
                    new_captured = captured | {(nx, ny)}
                    new_path = path + [(lx, ly)]
                    self._find_king_captures(lx, ly, piece, new_path,
                                             new_captured, results)
                lx += dx
                ly += dy

        if not found and len(path) > 1:
            results.append(path)

    def has_any_capture(self, color: str) -> bool:
        """Check if given side has any capture available."""
        for y in range(1, self.ROWS + 1):
            for x in range(1, self.COLS + 1):
                piece = self.piece_at(x, y)
                if piece == self.EMPTY:
                    continue
                if (color == 'b' and self.is_black(piece)) or \
                   (color == 'w' and self.is_white(piece)):
                    if self.get_captures(x, y):
                        return True
        return False

    def has_any_move(self, color: str) -> bool:
        """Check if given side has any legal move (capture or regular)."""
        for y in range(1, self.ROWS + 1):
            for x in range(1, self.COLS + 1):
                piece = self.piece_at(x, y)
                if piece == self.EMPTY:
                    continue
                if (color == 'b' and self.is_black(piece)) or \
                   (color == 'w' and self.is_white(piece)):
                    if self.get_captures(x, y) or self.get_valid_moves(x, y):
                        return True
        return False

    def execute_move(self, x1: int, y1: int, x2: int, y2: int):
        """Execute a simple (non-capture) move."""
        piece = self.piece_at(x1, y1)
        self.place_piece(x1, y1, self.EMPTY)

        # Check promotion
        if piece == self.WHITE and y2 == 1:
            piece = self.WHITE_KING
        elif piece == self.BLACK and y2 == self.ROWS:
            piece = self.BLACK_KING

        self.place_piece(x2, y2, piece)

    def execute_capture_path(self, path: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Execute a capture sequence along the given path.

        Returns list of captured piece positions.
        """
        piece = self.piece_at(*path[0])
        captured_positions = []

        for i in range(len(path) - 1):
            x1, y1 = path[i]
            x2, y2 = path[i + 1]

            # Find captured piece between these two positions
            dx = 1 if x2 > x1 else -1
            dy = 1 if y2 > y1 else -1
            cx, cy = x1 + dx, y1 + dy
            while (cx, cy) != (x2, y2):
                if self.piece_at(cx, cy) != self.EMPTY:
                    captured_positions.append((cx, cy))
                    break
                cx += dx
                cy += dy

        # Move piece
        self.place_piece(*path[0], self.EMPTY)

        # Remove captured pieces
        for cx, cy in captured_positions:
            self.place_piece(cx, cy, self.EMPTY)

        # Check promotion
        final_x, final_y = path[-1]
        if piece == self.WHITE and final_y == 1:
            piece = self.WHITE_KING
        elif piece == self.BLACK and final_y == self.ROWS:
            piece = self.BLACK_KING

        self.place_piece(final_x, final_y, piece)
        return captured_positions

    def dangerous_position(self, x: int, y: int, color: str) -> bool:
        """Check if piece at (x, y) is under attack.

        Matches original Pascal DangerousPosition().
        """
        piece = self.piece_at(x, y)
        if piece == self.EMPTY:
            return False

        for dy, dx in self.DIAGONAL_DIRECTIONS:
            # Check for adjacent enemy that can jump over us
            ax, ay = x + dx, y + dy
            bx, by = x - dx, y - dy  # landing square for enemy

            if not self._in_bounds(ax, ay) or not self._in_bounds(bx, by):
                continue

            attacker = self.piece_at(ax, ay)
            landing = self.piece_at(bx, by)

            if self.is_enemy(piece, attacker) and landing == self.EMPTY:
                if self.is_king(attacker):
                    return True
                # Regular piece can only capture forward... but in Russian draughts
                # pieces can capture in any direction
                return True

        # Check for king attacks from distance
        for dy, dx in self.DIAGONAL_DIRECTIONS:
            nx, ny = x + dx, y + dy
            while self._in_bounds(nx, ny) and self.piece_at(nx, ny) == self.EMPTY:
                nx += dx
                ny += dy
            if self._in_bounds(nx, ny):
                attacker = self.piece_at(nx, ny)
                if self.is_enemy(piece, attacker) and self.is_king(attacker):
                    # Check if there's a landing square
                    bx, by = x - dx, y - dy
                    if self._in_bounds(bx, by) and self.piece_at(bx, by) == self.EMPTY:
                        return True

        return False

    def is_diagonal_clear(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        """Check if diagonal path between two squares is clear.

        Matches original Pascal freeway().
        """
        if x1 == x2 and y1 == y2:
            return True
        dx = 1 if x2 > x1 else -1
        dy = 1 if y2 > y1 else -1
        cx, cy = x1 + dx, y1 + dy
        while (cx, cy) != (x2, y2):
            if self.piece_at(cx, cy) != self.EMPTY:
                return False
            cx += dx
            cy += dy
        return True

    def __repr__(self):
        lines = []
        lines.append("  a b c d e f g h")
        for y in range(1, self.ROWS + 1):
            row = [str(9 - y)]
            for x in range(1, self.COLS + 1):
                piece = self.grid[y][x]
                row.append(piece if piece != self.EMPTY else '.')
            lines.append(' '.join(row))
        return '\n'.join(lines)
