"""Board rendering widget for Russian draughts."""

from __future__ import annotations

import math

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from draughts.config import (
    BLACK,
    BLACK_KING,
    BOARD_SIZE,
    COLORS,
    COLUMN_LETTERS,
    EMPTY,
    ROW_NUMBERS,
    WHITE,
    WHITE_KING,
    Color,
    GameSettings,
)
from draughts.game.board import Board
from draughts.ui.textures import TextureCache, draw_realistic_piece

# Piece cycle order for editor left-click: empty → black → black king → white → white king → empty
_EDITOR_CYCLE = [int(EMPTY), int(BLACK), int(BLACK_KING), int(WHITE), int(WHITE_KING)]


class BoardWidget(QWidget):
    """Custom widget that draws the draughts board and pieces."""

    cell_left_clicked = pyqtSignal(int, int)
    cell_right_clicked = pyqtSignal(int, int)

    # Editor-mode signals (emitted instead of cell_*_clicked when editor_mode is True)
    editor_cell_cycled = pyqtSignal(int, int)   # left-click: cycle piece at (x, y)
    editor_cell_cleared = pyqtSignal(int, int)  # right-click: clear piece at (x, y)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._board: Board | None = None
        self._selection: tuple[int, int] | None = None
        self._destination: tuple[int, int] | None = None
        self._capture_highlights: list[tuple[int, int]] = []
        self._turn_color: Color = Color.WHITE
        self._anim_hidden_cells: set[tuple[int, int]] = set()  # cells hidden during animation
        self._theme: str = "dark_wood"
        self._textures = TextureCache(theme=self._theme)
        self._settings: GameSettings = GameSettings()
        # Board orientation (D22): True = black at bottom (player plays black)
        self._inverted: bool = False

        # Editor mode
        self._editor_mode: bool = False

        # Hint pulse animation (mandatory capture indicator)
        self._hint_cells: list[tuple[int, int]] = []
        self._hint_progress: float = 0.0  # 0..1 animation progress
        self._hint_timer = QTimer(self)
        self._hint_timer.setInterval(25)  # ~40 FPS
        self._hint_timer.timeout.connect(self._hint_tick)
        self._HINT_DURATION = 1.0  # seconds for full pulse cycle

        # Last-move highlight (item 26)
        self._last_move: tuple[tuple[int, int], tuple[int, int]] | None = None

        # Legal-move hover preview (item 26)
        self._hover_legal_moves: list[tuple[int, int]] = []

        # Hint-move overlay (D16)
        self._hint_squares: list[tuple[int, int]] | None = None
        self._hint_clear_timer = QTimer(self)
        self._hint_clear_timer.setSingleShot(True)
        self._hint_clear_timer.timeout.connect(self._clear_hint_squares)

        self.setMinimumSize(240, 240)
        self.setMouseTracking(False)

    # --- Orientation (D22) ---

    @property
    def inverted(self) -> bool:
        """True when the board is flipped so black is at the bottom."""
        return self._inverted

    @inverted.setter
    def inverted(self, value: bool) -> None:
        self._inverted = value
        self.update()

    # --- Settings ---

    def set_settings(self, settings: GameSettings) -> None:
        """Update rendering settings and enable mouse tracking if needed."""
        self._settings = settings
        need_tracking = settings.show_legal_moves_hover
        self.setMouseTracking(need_tracking)
        if not need_tracking:
            self._hover_legal_moves = []
        self.update()

    # --- Last-move highlight ---

    @property
    def last_move(self) -> tuple[tuple[int, int], tuple[int, int]] | None:
        return self._last_move

    @last_move.setter
    def last_move(self, value: tuple[tuple[int, int], tuple[int, int]] | None) -> None:
        self._last_move = value
        self.update()

    # --- Hint squares (D16) ---

    @property
    def hint_squares(self) -> list[tuple[int, int]] | None:
        return self._hint_squares

    @hint_squares.setter
    def hint_squares(self, value: list[tuple[int, int]] | None) -> None:
        self._hint_squares = value
        self._hint_clear_timer.stop()
        if value:
            self._hint_clear_timer.start(3000)
        self.update()

    def _clear_hint_squares(self) -> None:
        self._hint_squares = None
        self.update()

    # --- Editor mode ---

    @property
    def editor_mode(self) -> bool:
        return self._editor_mode

    @editor_mode.setter
    def editor_mode(self, value: bool):
        self._editor_mode = value
        self.update()

    def cycle_piece(self, x: int, y: int) -> None:
        """Cycle the piece at (x, y) through the editor piece sequence.

        Sequence: empty → BLACK → BLACK_KING → WHITE → WHITE_KING → empty.
        Only works on dark squares. No-op on light squares or when board is None.
        """
        if self._board is None:
            return
        if x % 2 == y % 2:  # light square — not playable
            return
        current = int(self._board.piece_at(x, y))
        try:
            idx = _EDITOR_CYCLE.index(current)
        except ValueError:
            idx = 0
        next_piece = _EDITOR_CYCLE[(idx + 1) % len(_EDITOR_CYCLE)]
        self._board.place_piece(x, y, next_piece)
        self.update()

    def clear_piece(self, x: int, y: int) -> None:
        """Remove the piece at (x, y). No-op on light squares or when board is None."""
        if self._board is None:
            return
        if x % 2 == y % 2:
            return
        self._board.place_piece(x, y, int(EMPTY))
        self.update()

    # --- Public API ---

    def set_board(self, board: Board):
        """Update the displayed board and repaint."""
        self._board = board
        self.update()

    def set_selection(self, x: int | None = None, y: int | None = None):
        """Highlight selected piece, or clear if x/y is None."""
        if x is None or y is None:
            self._selection = None
        else:
            self._selection = (x, y)
        self.update()

    def set_destination(self, x: int | None = None, y: int | None = None):
        """Highlight move destination square (green, same style as selection).

        Used by the puzzle trainer to show both start (selection) and
        end (destination) in the same green color simultaneously.
        """
        if x is None or y is None:
            self._destination = None
        else:
            self._destination = (x, y)
        self.update()

    def set_capture_highlights(self, positions: list[tuple[int, int]]):
        """Highlight intermediate capture squares."""
        self._capture_highlights = list(positions) if positions else []
        self.update()

    def set_turn_indicator(self, color: str | Color):
        """Set which side's turn it is."""
        self._turn_color = color
        self.update()

    def set_theme(self, theme: str) -> None:
        """Switch the board texture theme and repaint.

        Args:
            theme: Theme name (e.g. ``"dark_wood"``, ``"catppuccin_mocha"``).
                   The board textures map to the theme's ``board_style``
                   (``"dark_wood"`` or ``"classic_light"``).
                   Unknown names fall back to ``"dark_wood"`` textures.
        """
        from draughts.ui.textures import TextureCache
        from draughts.ui.theme_engine import get_board_style

        board_style = get_board_style(theme)
        if board_style not in TextureCache.THEMES:
            board_style = "dark_wood"
        self._textures.clear()
        self._textures.theme = board_style
        self._theme = theme
        self.update()

    def start_hint_pulse(self, positions: list[tuple[int, int]]):
        """Start a smooth pulse animation on cells that must capture."""
        self._hint_cells = list(positions)
        self._hint_progress = 0.0
        self._hint_timer.start()

    def _hint_tick(self):
        """Advance the hint pulse animation."""
        step = self._hint_timer.interval() / 1000.0 / self._HINT_DURATION
        self._hint_progress += step
        if self._hint_progress >= 1.0:
            self._hint_timer.stop()
            self._hint_cells = []
            self._hint_progress = 0.0
        self.update()

    def get_cell_size(self) -> float:
        """Return the current cell size in pixels (for matching piece sizes)."""
        _, cell_size, _, _ = self._metrics()
        return cell_size

    # --- Geometry helpers ---

    def _metrics(self):
        """Compute layout metrics based on current widget size.

        Returns (margin, cell_size, board_origin_x, board_origin_y).
        The board is drawn with a margin for coordinate labels and frame.
        """
        w = self.width()
        h = self.height()
        side = min(w, h)

        # Reserve space for frame + labels
        margin = max(int(side * 0.06), 16)
        board_side = side - 2 * margin
        cell_size = board_side / BOARD_SIZE

        # Center the board area in the widget
        bx = (w - board_side) / 2
        by = (h - board_side) / 2

        return margin, cell_size, bx, by

    def _cell_rect(self, x: int, y: int, cell_size: float, bx: float, by: float) -> QRectF:
        """Return the rectangle for board cell (x, y) where x,y in 0..7.

        When the board is inverted (black at bottom) both axes are mirrored.

        Pixel coordinates are snapped to integers so adjacent cells share
        exact pixel boundaries — no sub-pixel gaps or dark lines between
        cells caused by float rounding.
        """
        vx = (BOARD_SIZE - 1 - x) if self._inverted else x
        vy = (BOARD_SIZE - 1 - y) if self._inverted else y
        # Snap left/top edge AND right/bottom edge independently to
        # guarantee that cell N's right edge == cell N+1's left edge.
        x0 = round(bx + vx * cell_size)
        y0 = round(by + vy * cell_size)
        x1 = round(bx + (vx + 1) * cell_size)
        y1 = round(by + (vy + 1) * cell_size)
        return QRectF(x0, y0, x1 - x0, y1 - y0)

    def _cell_from_pos(self, pos) -> tuple[int, int] | None:
        """Convert a mouse position to board coordinates (0..7), or None."""
        _, cell_size, bx, by = self._metrics()
        mx = pos.x() - bx
        my = pos.y() - by
        if mx < 0 or my < 0:
            return None
        col = int(mx / cell_size)
        row = int(my / cell_size)
        if 0 <= col < BOARD_SIZE and 0 <= row < BOARD_SIZE:
            if self._inverted:
                col = BOARD_SIZE - 1 - col
                row = BOARD_SIZE - 1 - row
            return col, row
        return None

    # --- Painting ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        _margin, cell_size, bx, by = self._metrics()
        board_side = cell_size * BOARD_SIZE
        cs = max(1, int(cell_size))

        # Background color depends on theme
        _theme = getattr(self, "_theme", "dark_wood")
        if _theme == "classic_light":
            painter.fillRect(self.rect(), QColor(0xC8, 0xAA, 0x8C))
        else:
            # Dark wood: exactly match right panel (#3a2a1a) for seamless look
            painter.fillRect(self.rect(), QColor(0x3A, 0x2A, 0x1A))

        # Board frame texture
        frame_margin = cell_size * 0.65
        frame_rect = QRectF(
            bx - frame_margin, by - frame_margin, board_side + 2 * frame_margin, board_side + 2 * frame_margin
        )
        frame_tex = self._textures.get_frame(max(1, int(board_side + 2 * frame_margin)))
        painter.drawPixmap(frame_rect.toRect(), frame_tex)

        # Subtle frame border
        if _theme == "classic_light":
            painter.setPen(QPen(QColor(0x6B, 0x4A, 0x36), max(1, cell_size * 0.03)))
        else:
            painter.setPen(QPen(QColor(30, 20, 10), max(1, cell_size * 0.03)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(frame_rect)

        # Draw cells — theme-aware
        light_tex = self._textures.get_light_cell(cs)
        dark_tex = self._textures.get_dark_cell(cs)

        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                rect = self._cell_rect(x, y, cell_size, bx, by)
                is_dark = x % 2 != y % 2
                tex = dark_tex if is_dark else light_tex
                painter.drawPixmap(rect.toRect(), tex)

        # Draw highlights (selection / capture)
        if self._selection:
            sx, sy = self._selection
            rect = self._cell_rect(sx, sy, cell_size, bx, by)
            c = COLORS["selection_cursor"]
            pen = QPen(QColor(c[0], c[1], c[2]), max(2, cell_size * 0.08))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

        if self._destination:
            dx, dy = self._destination
            rect = self._cell_rect(dx, dy, cell_size, bx, by)
            c = COLORS["selection_cursor"]
            pen = QPen(QColor(c[0], c[1], c[2]), max(2, cell_size * 0.08))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

        for pos in self._capture_highlights:
            cx, cy = pos
            rect = self._cell_rect(cx, cy, cell_size, bx, by)
            c = COLORS["multi_capture"]
            pen = QPen(QColor(c[0], c[1], c[2]), max(2, cell_size * 0.08))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

        # Draw hint pulse (mandatory capture indicator)
        if self._hint_cells and self._hint_progress > 0:
            # Smooth sine pulse: 0 → 1 → 0
            opacity = math.sin(self._hint_progress * math.pi)
            c = COLORS["selection_cursor"]  # green — matches selection color
            hint_color = QColor(c[0], c[1], c[2], int(opacity * 200))
            pen = QPen(hint_color, max(2, cell_size * 0.08))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for hx, hy in self._hint_cells:
                rect = self._cell_rect(hx, hy, cell_size, bx, by)
                painter.drawRect(rect.adjusted(1, 1, -1, -1))

        # Draw last-move highlight — subtle border instead of filled
        # overlay so the wood texture stays visible underneath.
        if self._last_move is not None and self._settings.highlight_last_move:
            lm_color = QColor(200, 180, 50, 160)
            pen = QPen(lm_color, max(2, cell_size * 0.06))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for lx, ly in self._last_move:
                rect = self._cell_rect(lx, ly, cell_size, bx, by)
                painter.drawRect(rect.adjusted(2, 2, -2, -2))

        # Draw legal-move hover dots (item 26, part 2)
        # Dot color matches the player's piece color for visual consistency
        if self._hover_legal_moves and self._settings.show_legal_moves_hover:
            dot_r = max(4, cell_size * 0.13)
            if self._turn_color == Color.WHITE:
                dot_color = QColor(255, 255, 255, 140)
            else:
                dot_color = QColor(30, 30, 30, 140)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot_color)
            for hx, hy in self._hover_legal_moves:
                rect = self._cell_rect(hx, hy, cell_size, bx, by)
                cx = rect.center().x()
                cy = rect.center().y()
                painter.drawEllipse(QRectF(cx - dot_r, cy - dot_r, dot_r * 2, dot_r * 2))

        # Draw pieces (skip cells hidden by active animations)
        if self._board:
            for y in range(BOARD_SIZE):
                for x in range(BOARD_SIZE):
                    if (x, y) in self._anim_hidden_cells:
                        continue
                    piece = self._board.piece_at(x, y)
                    if piece != EMPTY:
                        self._draw_piece(painter, x, y, piece, cell_size, bx, by)

        # Draw hint-move overlay — bright green borders (D16)
        if self._hint_squares:
            hint_pen = QPen(QColor(0, 230, 80), max(3, cell_size * 0.10))
            painter.setPen(hint_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for hx, hy in self._hint_squares:
                rect = self._cell_rect(hx, hy, cell_size, bx, by)
                painter.drawRect(rect.adjusted(2, 2, -2, -2))

        # Draw coordinate labels
        self._draw_labels(painter, cell_size, bx, by, board_side)

        painter.end()

    def _draw_piece(self, painter: QPainter, x: int, y: int, piece: int, cell_size: float, bx: float, by: float):
        """Draw a single piece (regular or king) at board position (x, y)."""
        rect = self._cell_rect(x, y, cell_size, bx, by)
        cx = rect.center().x()
        cy = rect.center().y()
        radius = cell_size * 0.40
        is_black = piece in (BLACK, BLACK_KING)
        is_king = piece in (BLACK_KING, WHITE_KING)
        draw_realistic_piece(painter, cx, cy, radius, is_black, is_king)

    def _draw_labels(self, painter: QPainter, cell_size: float, bx: float, by: float, board_side: float):
        """Draw column letters (a-h) and row numbers (8-1) around the board.

        Labels are drawn only when settings.show_coordinates is True.
        Labels are centered in the frame margin between the board edge and frame edge.
        """
        if not self._settings.show_coordinates:
            return

        font_size = max(8, int(cell_size * 0.32))
        font = QFont("Georgia", font_size)
        painter.setFont(font)
        painter.setPen(QColor(190, 165, 120))

        # Label strip matches frame margin
        strip = cell_size * 0.65

        for i in range(BOARD_SIZE):
            # Cell center X for column labels
            cell_cx = bx + (i + 0.5) * cell_size
            # When inverted, visual column i corresponds to board column (7-i)
            letter = COLUMN_LETTERS[BOARD_SIZE - 1 - i] if self._inverted else COLUMN_LETTERS[i]

            # Below board — centered in strip between board bottom and frame bottom
            r_bot = QRectF(cell_cx - cell_size / 2, by + board_side, cell_size, strip)
            painter.drawText(r_bot, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, letter)

            # Above board
            r_top = QRectF(cell_cx - cell_size / 2, by - strip, cell_size, strip)
            painter.drawText(r_top, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, letter)

            # Cell center Y for row labels
            cell_cy = by + (i + 0.5) * cell_size
            # When inverted, visual row i corresponds to board row (7-i); ROW_NUMBERS[0]="8", [7]="1"
            number = ROW_NUMBERS[BOARD_SIZE - 1 - i] if self._inverted else ROW_NUMBERS[i]

            # Left of board
            r_left = QRectF(bx - strip, cell_cy - cell_size / 2, strip, cell_size)
            painter.drawText(r_left, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, number)

            # Right of board
            r_right = QRectF(bx + board_side, cell_cy - cell_size / 2, strip, cell_size)
            painter.drawText(r_right, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, number)

    # --- Mouse events ---

    def mousePressEvent(self, event: QMouseEvent):
        cell = self._cell_from_pos(event.position())
        if cell is None:
            return
        x, y = cell
        if self._editor_mode:
            self._handle_editor_click(x, y, event.button())
        else:
            if event.button() == Qt.MouseButton.LeftButton:
                self.cell_left_clicked.emit(x, y)
            elif event.button() == Qt.MouseButton.RightButton:
                self.cell_right_clicked.emit(x, y)

    def _handle_editor_click(self, x: int, y: int, button) -> None:
        """Handle mouse click in editor mode."""
        if button == Qt.MouseButton.LeftButton:
            self.cycle_piece(x, y)
            self.editor_cell_cycled.emit(x, y)
        elif button == Qt.MouseButton.RightButton:
            self.clear_piece(x, y)
            self.editor_cell_cleared.emit(x, y)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Track hover position to show legal-move dots (item 26, part 2)."""
        if not self._settings.show_legal_moves_hover or self._board is None or self._editor_mode:
            return
        cell = self._cell_from_pos(event.position())
        if cell is None:
            self._hover_legal_moves = []
            self.update()
            return
        x, y = cell
        piece = self._board.piece_at(x, y)
        # Determine if piece belongs to current turn's player
        is_player_piece = (
            (self._turn_color == Color.WHITE and self._board.is_white(piece))
            or (self._turn_color == Color.BLACK and self._board.is_black(piece))
        )
        if not is_player_piece:
            if self._hover_legal_moves:
                self._hover_legal_moves = []
                self.update()
            return
        # Compute reachable squares
        # If any piece of this color MUST capture, only show dots for
        # pieces that have captures (mandatory capture rule).
        destinations: list[tuple[int, int]] = []
        captures = self._board.get_captures(x, y)
        if captures:
            for path in captures:
                if len(path) >= 2:
                    destinations.append(path[-1])
        elif not self._board.has_any_capture(self._turn_color):
            destinations = list(self._board.get_valid_moves(x, y))
        # Deduplicate while preserving order
        seen: set[tuple[int, int]] = set()
        unique: list[tuple[int, int]] = []
        for sq in destinations:
            if sq not in seen:
                seen.add(sq)
                unique.append(sq)
        if unique != self._hover_legal_moves:
            self._hover_legal_moves = unique
            self.update()

    def leaveEvent(self, event):
        """Clear hover dots when mouse leaves the widget."""
        if self._hover_legal_moves:
            self._hover_legal_moves = []
            self.update()
        super().leaveEvent(event)
