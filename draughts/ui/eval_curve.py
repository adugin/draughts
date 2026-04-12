"""Eval curve widget — simple line chart of evaluation across a game (D12 / ROADMAP #17).

Drawn manually with QPainter; no external chart library needed.
Positive values = white is better; negative = black is better.
Click on a point to emit ``move_selected(ply_index)`` signal.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QSizePolicy, QWidget


class EvalCurveWidget(QWidget):
    """Line chart of eval scores across the game.

    Usage::

        curve = EvalCurveWidget()
        curve.set_evals([0.0, 50.0, -20.0, 120.0, ...])  # one per half-move

    Clicking near a point emits ``move_selected(index)`` where index is the
    0-based position index in the evals list.
    """

    move_selected = pyqtSignal(int)

    # Visual constants
    _MARGIN_L = 36
    _MARGIN_R = 10
    _MARGIN_T = 10
    _MARGIN_B = 18
    _CLIP_SCORE = 600.0  # clamp displayed score to +/-this value
    _WHITE_AREA_COLOR = QColor(255, 255, 200, 40)
    _BLACK_AREA_COLOR = QColor(0, 0, 80, 40)

    def __init__(self, parent=None, theme_name: str = "dark_wood"):
        super().__init__(parent)
        self._evals: list[float] = []
        self._selected_index: int | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(80)
        self.setToolTip("Кривая оценки по ходам. Нажмите для перехода к ходу.")

        # Load colors from theme engine
        from draughts.ui.theme_engine import get_theme_colors

        tc = get_theme_colors(theme_name)
        self._ZERO_LINE_COLOR = QColor(tc["curve_zero_line"])
        self._CURVE_COLOR = QColor(tc["curve_line"])
        self._POINT_COLOR = QColor(tc["curve_point"])
        self._SELECTED_COLOR = QColor(tc["curve_selected"])
        self._BG_COLOR = QColor(tc["curve_bg"])
        self._AXIS_COLOR = QColor(tc["curve_axis"])
        self._LABEL_COLOR = QColor(tc["curve_label"])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_evals(self, evals: list[float]) -> None:
        """Set the eval data and repaint."""
        self._evals = list(evals)
        self._selected_index = None
        self.update()

    def get_evals(self) -> list[float]:
        """Return the current eval list."""
        return list(self._evals)

    def select_move(self, index: int) -> None:
        """Highlight the point at the given index."""
        if 0 <= index < len(self._evals):
            self._selected_index = index
            self.update()

    # ------------------------------------------------------------------
    # Qt paint
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(0, 0, w, h, self._BG_COLOR)

        if not self._evals:
            painter.setPen(QPen(self._LABEL_COLOR))
            font = QFont()
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Нет данных")
            return

        # Drawing area
        dx = self._MARGIN_L
        dy = self._MARGIN_T
        dw = max(1, w - dx - self._MARGIN_R)
        dh = max(1, h - dy - self._MARGIN_B)

        n = len(self._evals)
        clip = self._CLIP_SCORE

        def _to_px(i: int, val: float) -> QPointF:
            xp = dx + (i / max(1, n - 1)) * dw if n > 1 else dx + dw / 2
            # val clamped to [-clip, +clip]; map +clip → top (dy), -clip → bottom (dy+dh)
            clamped = max(-clip, min(clip, val))
            yp = dy + dh / 2 - (clamped / clip) * (dh / 2)
            return QPointF(xp, yp)

        # Zero line
        zero_y = dy + dh / 2
        pen_zero = QPen(self._ZERO_LINE_COLOR)
        pen_zero.setWidth(1)
        painter.setPen(pen_zero)
        painter.drawLine(int(dx), int(zero_y), int(dx + dw), int(zero_y))

        # Shaded areas above/below zero
        if n >= 2:
            # White advantage area (above zero line)
            poly_w = QPolygonF()
            poly_w.append(QPointF(dx, zero_y))
            for i, v in enumerate(self._evals):
                p = _to_px(i, v)
                poly_w.append(QPointF(p.x(), min(p.y(), zero_y)))
            poly_w.append(QPointF(dx + dw, zero_y))
            painter.setBrush(self._WHITE_AREA_COLOR)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(poly_w)

            # Black advantage area (below zero line)
            poly_b = QPolygonF()
            poly_b.append(QPointF(dx, zero_y))
            for i, v in enumerate(self._evals):
                p = _to_px(i, v)
                poly_b.append(QPointF(p.x(), max(p.y(), zero_y)))
            poly_b.append(QPointF(dx + dw, zero_y))
            painter.setBrush(self._BLACK_AREA_COLOR)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(poly_b)

        # Axis labels
        font = QFont()
        font.setPointSize(7)
        painter.setFont(font)
        painter.setPen(QPen(self._LABEL_COLOR))
        painter.drawText(2, int(dy + 8), f"+{int(clip)}")
        painter.drawText(2, int(dy + dh // 2 + 4), "0")
        painter.drawText(2, int(dy + dh), f"-{int(clip)}")

        # Curve line
        if n >= 2:
            pen_curve = QPen(self._CURVE_COLOR)
            pen_curve.setWidth(2)
            painter.setPen(pen_curve)
            for i in range(n - 1):
                p1 = _to_px(i, self._evals[i])
                p2 = _to_px(i + 1, self._evals[i + 1])
                painter.drawLine(p1, p2)

        # Points
        for i, v in enumerate(self._evals):
            p = _to_px(i, v)
            if i == self._selected_index:
                painter.setBrush(self._SELECTED_COLOR)
                painter.setPen(QPen(self._SELECTED_COLOR))
                painter.drawEllipse(p, 5, 5)
            else:
                painter.setBrush(self._POINT_COLOR)
                painter.setPen(QPen(self._POINT_COLOR))
                painter.drawEllipse(p, 3, 3)

        # X-axis move numbers (sparse)
        painter.setPen(QPen(self._LABEL_COLOR))
        font2 = QFont()
        font2.setPointSize(7)
        painter.setFont(font2)
        step = max(1, n // 10)
        for i in range(0, n, step):
            p = _to_px(i, 0.0)
            painter.drawText(int(p.x()) - 8, h - 2, str(i + 1))

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if not self._evals:
            return
        n = len(self._evals)
        w = self.width()
        dx = self._MARGIN_L
        dw = max(1, w - dx - self._MARGIN_R)
        mx = event.position().x()

        # Find nearest point
        best_i = 0
        best_dist = float("inf")
        for i in range(n):
            xp = dx + (i / max(1, n - 1)) * dw if n > 1 else dx + dw / 2
            dist = abs(mx - xp)
            if dist < best_dist:
                best_dist = dist
                best_i = i

        if best_dist < 30:
            self._selected_index = best_i
            self.update()
            self.move_selected.emit(best_i)
