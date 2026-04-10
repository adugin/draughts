"""Animation effects for the draughts game.

Provides piece movement, capture removal, window-open, and TV-off effects
using QPropertyAnimation, QTimer, and custom QPainter overlays.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import (
    QEasingCurve,
    QObject,
    QPointF,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QDialog, QWidget

# ---------------------------------------------------------------------------
# PieceMoveAnimation — smoothly slides a piece between two cells
# ---------------------------------------------------------------------------

class PieceMoveAnimation(QObject):
    """Animates a piece sliding from (x1,y1) to (x2,y2) on the board widget.

    During animation the piece at (x1,y1) is hidden from normal rendering
    and an overlay draws it at the interpolated position.
    """

    finished = pyqtSignal()

    def __init__(
        self,
        board_widget: QWidget,
        x1: int, y1: int,
        x2: int, y2: int,
        duration_ms: int = 250,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._board = board_widget
        self._x1, self._y1 = x1, y1
        self._x2, self._y2 = x2, y2
        self._duration = duration_ms
        self._progress = 0.0
        self._running = False
        self._piece: int = 0

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 fps
        self._timer.timeout.connect(self._tick)
        self._elapsed = 0

    # -- progress property for interpolation --
    @pyqtProperty(float)
    def progress(self) -> float:
        return self._progress

    @progress.setter  # type: ignore[attr-defined]
    def progress(self, val: float):
        self._progress = val

    def start(self):
        """Begin the animation."""
        board = self._board._board
        if board is None:
            self.finished.emit()
            return

        self._piece = board.piece_at(self._x1, self._y1)
        if self._piece == 0:
            self.finished.emit()
            return

        # Store original paint handler and install overlay
        self._orig_paint = self._board.paintEvent
        self._board.paintEvent = self._overlay_paint
        self._board._anim_hidden_cells = getattr(self._board, '_anim_hidden_cells', set())
        self._board._anim_hidden_cells.add((self._x1, self._y1))

        self._running = True
        self._elapsed = 0
        self._progress = 0.0
        self._timer.start()

    def _tick(self):
        self._elapsed += 16
        t = min(self._elapsed / max(self._duration, 1), 1.0)
        # Ease-in-out
        self._progress = self._ease_in_out(t)
        self._board.update()
        if t >= 1.0:
            self._finish()

    @staticmethod
    def _ease_in_out(t: float) -> float:
        if t < 0.5:
            return 2 * t * t
        return 1 - (-2 * t + 2) ** 2 / 2

    def _finish(self):
        self._timer.stop()
        self._running = False
        self._board._anim_hidden_cells.discard((self._x1, self._y1))
        # Restore original paint
        self._board.paintEvent = self._orig_paint
        self._board.update()
        self.finished.emit()

    def _overlay_paint(self, event):
        """Custom paintEvent that draws the moving piece on top."""
        # Call original paint first
        self._orig_paint(event)

        if not self._running:
            return

        _, cell_size, bx, by = self._board._metrics()
        # Compute start and end centers
        r1 = self._board._cell_rect(self._x1, self._y1, cell_size, bx, by)
        r2 = self._board._cell_rect(self._x2, self._y2, cell_size, bx, by)
        cx = r1.center().x() + (r2.center().x() - r1.center().x()) * self._progress
        cy = r1.center().y() + (r2.center().y() - r1.center().y()) * self._progress

        painter = QPainter(self._board)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Draw piece at interpolated position using board's own draw method
        # We use a temporary rect to position the piece
        fake_bx = cx - cell_size / 2 - (1 - 1) * cell_size
        fake_by = cy - cell_size / 2 - (1 - 1) * cell_size
        self._board._draw_piece(painter, 1, 1, self._piece, cell_size, fake_bx, fake_by)
        painter.end()


# ---------------------------------------------------------------------------
# PieceRemoveAnimation — piece fades out / dissolves on capture
# ---------------------------------------------------------------------------

class PieceRemoveAnimation(QObject):
    """Fades a captured piece to transparent with a dissolve effect."""

    finished = pyqtSignal()

    def __init__(
        self,
        board_widget: QWidget,
        x: int, y: int,
        duration_ms: int = 300,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._board = board_widget
        self._x, self._y = x, y
        self._duration = duration_ms
        self._progress = 0.0
        self._running = False
        self._piece: int = 0

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._elapsed = 0

    def start(self):
        board = self._board._board
        if board is None:
            self.finished.emit()
            return

        self._piece = board.piece_at(self._x, self._y)
        if self._piece == 0:
            self.finished.emit()
            return

        self._orig_paint = self._board.paintEvent
        self._board.paintEvent = self._overlay_paint
        self._board._anim_hidden_cells = getattr(self._board, '_anim_hidden_cells', set())
        self._board._anim_hidden_cells.add((self._x, self._y))

        self._running = True
        self._elapsed = 0
        self._progress = 0.0
        self._timer.start()

    def _tick(self):
        self._elapsed += 16
        t = min(self._elapsed / max(self._duration, 1), 1.0)
        self._progress = t
        self._board.update()
        if t >= 1.0:
            self._finish()

    def _finish(self):
        self._timer.stop()
        self._running = False
        self._board._anim_hidden_cells.discard((self._x, self._y))
        self._board.paintEvent = self._orig_paint
        self._board.update()
        self.finished.emit()

    def _overlay_paint(self, event):
        self._orig_paint(event)
        if not self._running:
            return

        _, cell_size, bx, by = self._board._metrics()
        rect = self._board._cell_rect(self._x, self._y, cell_size, bx, by)

        painter = QPainter(self._board)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        opacity = 1.0 - self._progress
        painter.setOpacity(opacity)

        # Scale shrink effect: piece gets smaller as it fades
        scale = 1.0 - self._progress * 0.4
        cx_pos = rect.center().x()
        cy_pos = rect.center().y()
        half = cell_size * scale / 2
        fake_bx = cx_pos - half - (1 - 1) * cell_size * scale
        fake_by = cy_pos - half - (1 - 1) * cell_size * scale

        painter.save()
        painter.translate(cx_pos, cy_pos)
        painter.scale(scale, scale)
        painter.translate(-cx_pos, -cy_pos)
        self._board._draw_piece(painter, self._x, self._y, self._piece, cell_size, bx, by)
        painter.restore()
        painter.end()


# ---------------------------------------------------------------------------
# WindowOpenAnimation — dialog grows from center point
# ---------------------------------------------------------------------------

class WindowOpenAnimation(QObject):
    """Animates a QDialog expanding from a center point to its final geometry."""

    finished = pyqtSignal()

    def __init__(self, dialog: QDialog, duration_ms: int = 200, parent: QObject | None = None):
        super().__init__(parent)
        self._dialog = dialog
        self._duration = duration_ms

    def start(self):
        """Start the window-open animation. The dialog should already have its target geometry set."""
        target = self._dialog.geometry()
        cx = target.center().x()
        cy = target.center().y()
        start_rect = QRect(cx, cy, 0, 0)

        self._anim = QPropertyAnimation(self._dialog, b"geometry", self)
        self._anim.setDuration(self._duration)
        self._anim.setStartValue(start_rect)
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self.finished.emit)
        self._dialog.show()
        self._anim.start()


# ---------------------------------------------------------------------------
# TVSetOffAnimation — exit effect ("TV turning off")
# ---------------------------------------------------------------------------

class TVSetOffAnimation(QObject):
    """Simulates a CRT TV turning off: content compresses to a horizontal line,
    then the line shrinks to a dot and disappears."""

    finished = pyqtSignal()

    def __init__(self, window: QWidget, duration_ms: int = 600, parent: QObject | None = None):
        super().__init__(parent)
        self._window = window
        self._duration = duration_ms
        self._overlay: _TVOverlayWidget | None = None

    def start(self):
        """Capture the window content and start the TV-off effect."""
        # Create an overlay widget that covers the entire window
        self._overlay = _TVOverlayWidget(self._window, self._duration)
        self._overlay.finished.connect(self._on_finished)
        self._overlay.start()

    def _on_finished(self):
        if self._overlay:
            self._overlay.hide()
            self._overlay.deleteLater()
            self._overlay = None
        self.finished.emit()


class _TVOverlayWidget(QWidget):
    """Internal overlay that paints the TV-off effect."""

    finished = pyqtSignal()

    def __init__(self, parent_window: QWidget, duration_ms: int):
        super().__init__(parent_window)
        self._duration = duration_ms
        self._progress = 0.0
        self._parent_window = parent_window

        # Grab current content as pixmap
        self._snapshot = parent_window.grab()

        self.setGeometry(parent_window.rect())
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.raise_()
        self.show()

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._elapsed = 0

    def start(self):
        self._elapsed = 0
        self._progress = 0.0
        self._timer.start()

    def _tick(self):
        self._elapsed += 16
        t = min(self._elapsed / max(self._duration, 1), 1.0)
        self._progress = t
        self.update()
        if t >= 1.0:
            self._timer.stop()
            self.finished.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        w = self.width()
        h = self.height()

        # Fill black
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        if self._progress < 0.7:
            # Phase 1: compress vertically to a horizontal line
            phase = self._progress / 0.7
            # Ease out
            phase_smooth = 1.0 - (1.0 - phase) ** 2
            strip_h = max(2, int(h * (1.0 - phase_smooth)))
            y_off = (h - strip_h) // 2

            # Also slightly narrow horizontally as we compress
            w_shrink = max(int(w * (1.0 - phase_smooth * 0.1)), 4)
            x_off = (w - w_shrink) // 2

            target_rect = QRect(x_off, y_off, w_shrink, strip_h)
            painter.drawPixmap(target_rect, self._snapshot)

            # Add scanline-like brightness boost
            bright = int(phase_smooth * 200)
            painter.setOpacity(phase_smooth * 0.3)
            painter.fillRect(QRect(0, y_off, w, max(strip_h, 1)), QColor(bright, bright, bright))
            painter.setOpacity(1.0)

        elif self._progress < 1.0:
            # Phase 2: horizontal line shrinks to dot
            phase = (self._progress - 0.7) / 0.3
            phase_smooth = phase ** 2
            line_w = max(2, int(w * (1.0 - phase_smooth)))
            x_off = (w - line_w) // 2
            cy = h // 2

            # Draw bright horizontal line
            painter.setPen(Qt.PenStyle.NoPen)
            glow_h = max(1, int(4 * (1.0 - phase_smooth)))
            painter.fillRect(
                QRect(x_off, cy - glow_h, line_w, glow_h * 2),
                QColor(200, 200, 255),
            )

            # Central bright dot glow
            dot_size = max(2, int(8 * (1.0 - phase_smooth)))
            painter.setOpacity(1.0 - phase_smooth * 0.5)
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(QPointF(w / 2, cy), dot_size, dot_size)
            painter.setOpacity(1.0)
        else:
            # Fully black
            pass

        painter.end()


# ---------------------------------------------------------------------------
# Convenience API
# ---------------------------------------------------------------------------

# Keep references alive until animations complete
_active_animations: list[QObject] = []


def animate_piece_move(
    board_widget: QWidget,
    x1: int, y1: int,
    x2: int, y2: int,
    callback: Callable[[], None] | None = None,
    duration_ms: int = 250,
) -> PieceMoveAnimation:
    """Animate a piece sliding from (x1,y1) to (x2,y2).

    Args:
        board_widget: The BoardWidget instance.
        x1, y1: Start cell (1..8).
        x2, y2: End cell (1..8).
        callback: Optional function called when animation finishes.
        duration_ms: Duration in milliseconds.

    Returns:
        The animation object (also kept alive internally).
    """
    anim = PieceMoveAnimation(board_widget, x1, y1, x2, y2, duration_ms)
    _active_animations.append(anim)

    def _cleanup():
        if anim in _active_animations:
            _active_animations.remove(anim)
        if callback:
            callback()

    anim.finished.connect(_cleanup)
    anim.start()
    return anim


def animate_piece_remove(
    board_widget: QWidget,
    x: int, y: int,
    callback: Callable[[], None] | None = None,
    duration_ms: int = 300,
) -> PieceRemoveAnimation:
    """Animate a piece fading out at (x, y).

    Args:
        board_widget: The BoardWidget instance.
        x, y: Cell position (1..8).
        callback: Optional function called when animation finishes.
        duration_ms: Duration in milliseconds.

    Returns:
        The animation object.
    """
    anim = PieceRemoveAnimation(board_widget, x, y, duration_ms)
    _active_animations.append(anim)

    def _cleanup():
        if anim in _active_animations:
            _active_animations.remove(anim)
        if callback:
            callback()

    anim.finished.connect(_cleanup)
    anim.start()
    return anim


def animate_window_open(
    dialog: QDialog,
    callback: Callable[[], None] | None = None,
    duration_ms: int = 200,
) -> WindowOpenAnimation:
    """Animate a dialog expanding from its center.

    Args:
        dialog: The QDialog to animate (geometry must already be set).
        callback: Optional function called when animation finishes.
        duration_ms: Duration in milliseconds.

    Returns:
        The animation object.
    """
    anim = WindowOpenAnimation(dialog, duration_ms)
    _active_animations.append(anim)

    def _cleanup():
        if anim in _active_animations:
            _active_animations.remove(anim)
        if callback:
            callback()

    anim.finished.connect(_cleanup)
    anim.start()
    return anim


def animate_tv_off(
    window: QWidget,
    callback: Callable[[], None] | None = None,
    duration_ms: int = 600,
) -> TVSetOffAnimation:
    """Animate the TV-turn-off exit effect on a window.

    Args:
        window: The main window to apply the effect to.
        callback: Optional function called when the effect finishes.
        duration_ms: Duration in milliseconds.

    Returns:
        The animation object.
    """
    anim = TVSetOffAnimation(window, duration_ms)
    _active_animations.append(anim)

    def _cleanup():
        if anim in _active_animations:
            _active_animations.remove(anim)
        if callback:
            callback()

    anim.finished.connect(_cleanup)
    anim.start()
    return anim
