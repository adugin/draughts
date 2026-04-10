"""Widget displaying captured pieces in two rows — white on top, black on bottom.

Pieces are drawn with the same function as on the board (piece_painter.draw_piece).
The piece size is calculated to fit within the available panel space while
staying proportional to the board pieces when possible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QWidget

from draughts.ui.piece_painter import draw_piece

if TYPE_CHECKING:
    from draughts.ui.board_widget import BoardWidget


class CapturedWidget(QWidget):
    """Draws captured pieces as checkers in two rows."""

    MAX_PIECES = 12  # max captured per side

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

    def _calc_radius(self) -> float:
        """Calculate piece radius that fits in the available space.

        Uses the board's cell size as the ideal, but clamps to what
        actually fits in this widget's dimensions.
        """
        h = self.height()
        w = self.width()

        # Must fit 2 rows vertically with padding
        padding = 4
        max_radius_from_h = (h - padding * 3) / 4  # 2 diameters + 3 gaps

        # Must fit MAX_PIECES horizontally
        max_radius_from_w = (w - padding * 2) / (self.MAX_PIECES * 2.3)

        # Fit constraint
        fit_radius = min(max_radius_from_h, max_radius_from_w)

        # Ideal: match board piece size
        if self._board_widget:
            board_radius = self._board_widget.get_cell_size() * 0.40
            # Use board size but don't exceed what fits
            return min(board_radius, fit_radius)

        return max(fit_radius, 3)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        radius = self._calc_radius()
        if radius < 3:
            painter.end()
            return

        h = self.height()
        step = radius * 2.3
        start_x = radius + 6

        # Two rows centered vertically
        cy_white = h / 4
        cy_black = h * 3 / 4

        # Draw captured white pieces (top row)
        for i in range(self._white_count):
            cx = start_x + i * step
            draw_piece(painter, cx, cy_white, radius, is_black=False)

        # Draw captured black pieces (bottom row)
        for i in range(self._black_count):
            cx = start_x + i * step
            draw_piece(painter, cx, cy_black, radius, is_black=True)

        painter.end()
