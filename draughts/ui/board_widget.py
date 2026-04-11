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
    WHITE_KING,
    Color,
)
from draughts.game.board import Board
from draughts.ui.textures import TextureCache, draw_realistic_piece


class BoardWidget(QWidget):
    """Custom widget that draws the draughts board and pieces."""

    cell_left_clicked = pyqtSignal(int, int)
    cell_right_clicked = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._board: Board | None = None
        self._selection: tuple[int, int] | None = None
        self._capture_highlights: list[tuple[int, int]] = []
        self._turn_color: Color = Color.WHITE
        self._anim_hidden_cells: set[tuple[int, int]] = set()  # cells hidden during animation
        self._textures = TextureCache()

        # Hint pulse animation (mandatory capture indicator)
        self._hint_cells: list[tuple[int, int]] = []
        self._hint_progress: float = 0.0  # 0..1 animation progress
        self._hint_timer = QTimer(self)
        self._hint_timer.setInterval(25)  # ~40 FPS
        self._hint_timer.timeout.connect(self._hint_tick)
        self._HINT_DURATION = 1.0  # seconds for full pulse cycle

        self.setMinimumSize(240, 240)
        self.setMouseTracking(False)

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

    def set_capture_highlights(self, positions: list[tuple[int, int]]):
        """Highlight intermediate capture squares."""
        self._capture_highlights = list(positions) if positions else []
        self.update()

    def set_turn_indicator(self, color: str | Color):
        """Set which side's turn it is."""
        self._turn_color = color
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
        """Return the rectangle for board cell (x, y) where x,y in 0..7."""
        px = bx + x * cell_size
        py = by + y * cell_size
        return QRectF(px, py, cell_size, cell_size)

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
            return col, row
        return None

    # --- Painting ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        _margin, cell_size, bx, by = self._metrics()
        board_side = cell_size * BOARD_SIZE
        cs = max(1, int(cell_size))

        # Background — exactly match right panel (#3a2a1a) for seamless look
        painter.fillRect(self.rect(), QColor(0x3A, 0x2A, 0x1A))

        # Board frame — dark mahogany wood texture
        frame_margin = cell_size * 0.65
        frame_rect = QRectF(
            bx - frame_margin, by - frame_margin, board_side + 2 * frame_margin, board_side + 2 * frame_margin
        )
        frame_tex = self._textures.get_frame_wood(max(1, int(board_side + 2 * frame_margin)))
        painter.drawPixmap(frame_rect.toRect(), frame_tex)

        # Subtle frame border
        painter.setPen(QPen(QColor(30, 20, 10), max(1, cell_size * 0.03)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(frame_rect)

        # Draw cells with wood textures
        light_tex = self._textures.get_light_wood(cs)
        dark_tex = self._textures.get_dark_wood(cs)

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
            c = COLORS["multi_capture"]  # green — matches capture highlight color
            hint_color = QColor(c[0], c[1], c[2], int(opacity * 200))
            pen = QPen(hint_color, max(2, cell_size * 0.08))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for hx, hy in self._hint_cells:
                rect = self._cell_rect(hx, hy, cell_size, bx, by)
                painter.drawRect(rect.adjusted(1, 1, -1, -1))

        # Draw pieces (skip cells hidden by active animations)
        if self._board:
            for y in range(BOARD_SIZE):
                for x in range(BOARD_SIZE):
                    if (x, y) in self._anim_hidden_cells:
                        continue
                    piece = self._board.piece_at(x, y)
                    if piece != EMPTY:
                        self._draw_piece(painter, x, y, piece, cell_size, bx, by)

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

        Labels are centered in the frame margin between the board edge and frame edge.
        """
        font_size = max(8, int(cell_size * 0.32))
        font = QFont("Georgia", font_size)
        painter.setFont(font)
        painter.setPen(QColor(190, 165, 120))

        # Label strip matches frame margin
        strip = cell_size * 0.65

        for i in range(BOARD_SIZE):
            # Cell center X for column labels
            cell_cx = bx + (i + 0.5) * cell_size
            letter = COLUMN_LETTERS[i]

            # Below board — centered in strip between board bottom and frame bottom
            r_bot = QRectF(cell_cx - cell_size / 2, by + board_side, cell_size, strip)
            painter.drawText(r_bot, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, letter)

            # Above board
            r_top = QRectF(cell_cx - cell_size / 2, by - strip, cell_size, strip)
            painter.drawText(r_top, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, letter)

            # Cell center Y for row labels
            cell_cy = by + (i + 0.5) * cell_size
            number = ROW_NUMBERS[i]

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
        if event.button() == Qt.MouseButton.LeftButton:
            self.cell_left_clicked.emit(x, y)
        elif event.button() == Qt.MouseButton.RightButton:
            self.cell_right_clicked.emit(x, y)
