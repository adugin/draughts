"""Board rendering widget for Russian draughts."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QMouseEvent, QPainterPath
from PyQt6.QtWidgets import QWidget

from draughts.config import (
    BOARD_SIZE, COLORS, COLUMN_LETTERS, ROW_NUMBERS,
    BLACK, BLACK_KING, WHITE, WHITE_KING, EMPTY,
)
from draughts.game.board import Board


class BoardWidget(QWidget):
    """Custom widget that draws the draughts board and pieces."""

    cell_left_clicked = pyqtSignal(int, int)
    cell_right_clicked = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._board: Optional[Board] = None
        self._selection: Optional[tuple[int, int]] = None
        self._capture_highlights: list[tuple[int, int]] = []
        self._turn_color: str = 'w'  # whose turn: 'w' or 'b'

        self.setMinimumSize(240, 240)
        self.setMouseTracking(False)

    # --- Public API ---

    def set_board(self, board: Board):
        """Update the displayed board and repaint."""
        self._board = board
        self.update()

    def set_selection(self, x: Optional[int] = None, y: Optional[int] = None):
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

    def set_turn_indicator(self, color: str):
        """Set which side's turn it is ('w' or 'b')."""
        self._turn_color = color
        self.update()

    # --- Geometry helpers ---

    def _metrics(self):
        """Compute layout metrics based on current widget size.

        Returns (margin, cell_size, board_origin_x, board_origin_y).
        The board is drawn with a margin for coordinate labels and frame.
        """
        w = self.width()
        h = self.height()
        side = min(w, h)

        # Reserve ~8% on each side for labels/frame
        margin = max(int(side * 0.08), 16)
        board_side = side - 2 * margin
        cell_size = board_side / BOARD_SIZE

        # Center the board area in the widget
        bx = (w - board_side) / 2
        by = (h - board_side) / 2

        return margin, cell_size, bx, by

    def _cell_rect(self, x: int, y: int, cell_size: float, bx: float, by: float) -> QRectF:
        """Return the rectangle for board cell (x, y) where x,y in 1..8."""
        px = bx + (x - 1) * cell_size
        py = by + (y - 1) * cell_size
        return QRectF(px, py, cell_size, cell_size)

    def _cell_from_pos(self, pos) -> Optional[tuple[int, int]]:
        """Convert a mouse position to board coordinates (1..8), or None."""
        _, cell_size, bx, by = self._metrics()
        mx = pos.x() - bx
        my = pos.y() - by
        if mx < 0 or my < 0:
            return None
        col = int(mx / cell_size) + 1
        row = int(my / cell_size) + 1
        if 1 <= col <= BOARD_SIZE and 1 <= row <= BOARD_SIZE:
            return col, row
        return None

    # --- Painting ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin, cell_size, bx, by = self._metrics()
        board_side = cell_size * BOARD_SIZE

        # Background fill
        painter.fillRect(self.rect(), QColor(COLORS['panel_bg'][0], COLORS['panel_bg'][1], COLORS['panel_bg'][2]))

        # Board background (dark area behind labels)
        bg = COLORS['board_bg']
        frame_margin = cell_size * 0.15
        painter.fillRect(
            QRectF(bx - frame_margin, by - frame_margin,
                   board_side + 2 * frame_margin, board_side + 2 * frame_margin),
            QColor(bg[0], bg[1], bg[2]),
        )

        # Yellow frame around the board
        frame_c = COLORS['board_frame']
        pen = QPen(QColor(frame_c[0], frame_c[1], frame_c[2]), max(2, cell_size * 0.06))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(bx - frame_margin, by - frame_margin,
                                board_side + 2 * frame_margin, board_side + 2 * frame_margin))

        # Draw cells
        for y in range(1, BOARD_SIZE + 1):
            for x in range(1, BOARD_SIZE + 1):
                rect = self._cell_rect(x, y, cell_size, bx, by)
                is_dark = (x % 2 != y % 2)
                color_key = 'dark_cell' if is_dark else 'light_cell'
                c = COLORS[color_key]
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(c[0], c[1], c[2]))
                painter.drawRect(rect)

        # Draw highlights (selection / capture)
        if self._selection:
            sx, sy = self._selection
            rect = self._cell_rect(sx, sy, cell_size, bx, by)
            c = COLORS['selection_cursor']
            pen = QPen(QColor(c[0], c[1], c[2]), max(2, cell_size * 0.08))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

        for pos in self._capture_highlights:
            cx, cy = pos
            rect = self._cell_rect(cx, cy, cell_size, bx, by)
            c = COLORS['multi_capture']
            pen = QPen(QColor(c[0], c[1], c[2]), max(2, cell_size * 0.08))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

        # Draw pieces
        if self._board:
            for y in range(1, BOARD_SIZE + 1):
                for x in range(1, BOARD_SIZE + 1):
                    piece = self._board.get(x, y)
                    if piece != EMPTY:
                        self._draw_piece(painter, x, y, piece, cell_size, bx, by)

        # Draw coordinate labels
        self._draw_labels(painter, cell_size, bx, by, board_side)

        painter.end()

    def _draw_piece(self, painter: QPainter, x: int, y: int, piece: str,
                    cell_size: float, bx: float, by: float):
        """Draw a single piece (regular or king) at board position (x, y)."""
        rect = self._cell_rect(x, y, cell_size, bx, by)
        cx = rect.center().x()
        cy = rect.center().y()
        radius = cell_size * 0.40

        is_black = piece in (BLACK, BLACK_KING)
        is_king = piece in (BLACK_KING, WHITE_KING)

        # Main piece color
        if is_black:
            main_color = QColor(*COLORS['black_piece'])
            ring_color = QColor(*COLORS['black_piece_ring'])
        else:
            main_color = QColor(*COLORS['white_piece'])
            ring_color = QColor(*COLORS['white_piece_ring'])

        # Outer ring
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ring_color)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # Inner fill
        inner_r = radius * 0.80
        painter.setBrush(main_color)
        painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # Second ring (concentric style from original)
        ring2_r = radius * 0.60
        painter.setPen(QPen(ring_color, max(1, cell_size * 0.03)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), ring2_r, ring2_r)

        # King crown
        if is_king:
            self._draw_crown(painter, cx, cy, radius * 0.45, is_black)

    def _draw_crown(self, painter: QPainter, cx: float, cy: float,
                    size: float, is_black: bool):
        """Draw a simple crown symbol on a king piece."""
        crown_color = QColor(*COLORS['crown_fill'])
        gem_color = QColor(*COLORS['crown_gems'])

        # Draw crown as a simple polygon: base + 3 points
        half = size * 0.7
        top = cy - size * 0.5
        bottom = cy + size * 0.4
        mid = (top + bottom) / 2

        path = QPainterPath()
        path.moveTo(cx - half, bottom)
        path.lineTo(cx - half, mid)
        path.lineTo(cx - half * 0.5, top + size * 0.15)
        path.lineTo(cx, mid)
        path.lineTo(cx + half * 0.5, top + size * 0.15)
        path.lineTo(cx + half, mid)
        path.lineTo(cx + half, bottom)
        path.closeSubpath()

        painter.setPen(QPen(gem_color, max(1, size * 0.1)))
        painter.setBrush(crown_color)
        painter.drawPath(path)

        # Three gems on the crown points
        gem_r = size * 0.12
        for gx in [cx - half * 0.5, cx, cx + half * 0.5]:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gem_color)
            painter.drawEllipse(QPointF(gx, top + size * 0.15), gem_r, gem_r)

    def _draw_labels(self, painter: QPainter, cell_size: float,
                     bx: float, by: float, board_side: float):
        """Draw column letters (a-h) and row numbers (8-1) around the board."""
        font_size = max(8, int(cell_size * 0.28))
        font = QFont("Arial", font_size)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 200))

        label_offset = cell_size * 0.35

        for i in range(BOARD_SIZE):
            # Column letters below
            letter = COLUMN_LETTERS[i]
            lx = bx + (i + 0.5) * cell_size
            ly = by + board_side + label_offset
            r = QRectF(lx - cell_size / 2, ly - font_size / 2, cell_size, font_size * 1.5)
            painter.drawText(r, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, letter)

            # Column letters above
            ly_top = by - label_offset
            r_top = QRectF(lx - cell_size / 2, ly_top - font_size, cell_size, font_size * 1.5)
            painter.drawText(r_top, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, letter)

            # Row numbers left
            number = ROW_NUMBERS[i]
            rx = bx - label_offset
            ry = by + (i + 0.5) * cell_size
            r_left = QRectF(rx - cell_size, ry - cell_size / 2, cell_size, cell_size)
            painter.drawText(r_left, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, number)

            # Row numbers right
            rx_right = bx + board_side + label_offset
            r_right = QRectF(rx_right, ry - cell_size / 2, cell_size, cell_size)
            painter.drawText(r_right, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, number)

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
