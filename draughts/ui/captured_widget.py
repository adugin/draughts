"""Widget displaying captured pieces in two rows — white on top, black on bottom."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtWidgets import QWidget

from draughts.config import COLORS


class CapturedWidget(QWidget):
    """Draws captured pieces as mini-checkers in two rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._white_count = 0
        self._black_count = 0
        self.setMinimumHeight(50)

    def set_counts(self, white_captured: int, black_captured: int):
        """Update the number of captured pieces for each side."""
        self._white_count = white_captured
        self._black_count = black_captured
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Two rows: top = captured white, bottom = captured black
        row_h = h / 2
        max_pieces = 12  # maximum possible captured

        # Piece radius: fit both height and width
        # Height: must fit in row_h with some padding
        # Width: must fit max_pieces across the width
        margin = 4
        available_h = row_h - margin * 2
        available_w = w - margin * 2

        radius_from_h = available_h / 2 * 0.85
        radius_from_w = available_w / (max_pieces * 2) * 0.85
        radius = min(radius_from_h, radius_from_w)
        if radius < 3:
            return

        step = radius * 2.2  # spacing between piece centers
        start_x = margin + radius + 2

        # Draw captured white pieces (top row)
        cy_white = margin + row_h / 2
        self._draw_row(painter, self._white_count, start_x, cy_white,
                       step, radius, is_black=False)

        # Draw captured black pieces (bottom row)
        cy_black = row_h + margin + row_h / 2 - margin
        self._draw_row(painter, self._black_count, start_x, cy_black,
                       step, radius, is_black=True)

        painter.end()

    def _draw_row(self, painter: QPainter, count: int,
                  start_x: float, cy: float, step: float,
                  radius: float, is_black: bool):
        """Draw a row of mini captured pieces."""
        if count <= 0:
            return

        if is_black:
            main_color = QColor(*COLORS['black_piece'])
            ring_color = QColor(*COLORS['black_piece_ring'])
        else:
            main_color = QColor(*COLORS['white_piece'])
            ring_color = QColor(*COLORS['white_piece_ring'])

        for i in range(count):
            cx = start_x + i * step

            # Outer ring
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ring_color)
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

            # Inner fill
            inner_r = radius * 0.75
            painter.setBrush(main_color)
            painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

            # Concentric ring
            ring_r = radius * 0.50
            painter.setPen(QPen(ring_color, max(1, radius * 0.08)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), ring_r, ring_r)
