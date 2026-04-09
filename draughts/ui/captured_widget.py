"""Widget displaying captured pieces in two rows — white on top, black on bottom.

Pieces are drawn with the same function as on the board (piece_painter.draw_piece),
so they look identical. The panel height adjusts to fit two rows of full-size pieces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QWidget

from draughts.ui.piece_painter import draw_piece

if TYPE_CHECKING:
    from draughts.ui.board_widget import BoardWidget


class CapturedWidget(QWidget):
    """Draws captured pieces as full-size checkers in two rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._white_count = 0
        self._black_count = 0
        self._board_widget: BoardWidget | None = None

    def set_board_widget(self, bw: BoardWidget):
        """Link to the board widget to match piece size."""
        self._board_widget = bw

    def set_counts(self, white_captured: int, black_captured: int):
        """Update the number of captured pieces for each side."""
        self._white_count = white_captured
        self._black_count = black_captured
        self.update()

    def _piece_radius(self) -> float:
        """Get the piece radius matching the board's pieces."""
        if self._board_widget:
            cell_size = self._board_widget.get_cell_size()
            return cell_size * 0.40
        # Fallback: derive from own height
        return self.height() / 4 * 0.80

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        radius = self._piece_radius()
        if radius < 3:
            painter.end()
            return

        h = self.height()
        step = radius * 2.3  # spacing = slightly more than diameter
        start_x = radius + 6

        # Two rows centered vertically
        row_h = h / 2
        cy_white = row_h / 2 + 1
        cy_black = row_h + row_h / 2 - 1

        # Draw captured white pieces (top row)
        for i in range(self._white_count):
            cx = start_x + i * step
            draw_piece(painter, cx, cy_white, radius, is_black=False)

        # Draw captured black pieces (bottom row)
        for i in range(self._black_count):
            cx = start_x + i * step
            draw_piece(painter, cx, cy_black, radius, is_black=True)

        painter.end()

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        # Height should accommodate 2 rows of full-size pieces
        radius = self._piece_radius()
        h = int(radius * 2 * 2 + 12)  # 2 pieces vertically + padding
        return QSize(400, max(h, 60))
