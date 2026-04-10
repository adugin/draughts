"""Animated splash screen — pixel-level scatter/reassemble.

Faithful recreation of the original Pascal breaking() algorithm:
  1. Render text to offscreen image, extract pixel positions
  2. Scatter pixels radially outward from center
  3. Pull pixels back toward center (they form a cloud near center)
  4. Clear and show next text, repeat
  5. Final text: lightning strike, then per-pixel color shimmer
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import QWidget

# Maximum number of pixels to track (matching original mas[1..2000])
_MAX_PIXELS = 2000


@dataclass
class _Dot:
    """A single pixel extracted from rendered text."""
    x: float
    y: float
    color: QColor | None = None


@dataclass
class _LightningBolt:
    points: list[tuple[float, float]]
    alpha: float = 1.0
    width: float = 2.0
    color: QColor | None = None
    branches: list[list[tuple[float, float]]] = field(default_factory=list)


# Phase timing
_T_NAME_SHOW = 0.0
_T_NAME_HOLD = 1.5
_T_SCATTER_1_END = 2.8
_T_ASSEMBLE_1_END = 4.1
_T_PRESENTS_HOLD = 5.1
_T_SCATTER_2_END = 6.4
_T_ASSEMBLE_2_END = 7.7
_T_TITLE_HOLD = 8.7
_T_LIGHTNING = 8.7
_T_LIGHTNING_FLASH = 8.9
_T_SHIMMER_START = 9.0
_T_FADEOUT_START = 12.0
_T_END = 12.8


class SplashScreen(QWidget):
    """Full-screen animated splash with pixel scatter/reassemble."""

    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet("background: black;")

        self._elapsed = 0.0
        self._fps_interval = 16

        # Pixel dots for scatter/assemble
        self._dots: list[_Dot] = []

        # Title pixel positions (for shimmer)
        self._title_dot_positions: list[tuple[float, float]] = []
        self._title_dot_colors: list[QColor] = []
        self._shimmer_active = False

        # Static text image (shown when text is fully assembled, not animating)
        self._static_text: str | None = None

        # Lightning
        self._bolts: list[_LightningBolt] = []
        self._flash_alpha = 0.0

        self._fade_alpha = 0.0

        # Timer
        self._timer = QTimer(self)
        self._timer.setInterval(self._fps_interval)
        self._timer.timeout.connect(self._tick)

        self._initialized = False
        self._phase_done: set[str] = set()

        # Text rendering cache
        self._text_configs: dict[str, tuple[str, int, QColor]] = {}

        # Screenshot support
        self._screenshot_callback = None
        self._screenshot_phases_done: set[str] = set()

    def _fire_screenshot(self, phase_name: str):
        if self._screenshot_callback is not None:
            self.update()
            self.repaint()
            self._screenshot_callback(phase_name, self)

    def show_animated(self):
        self.showFullScreen()
        QTimer.singleShot(50, self._begin)

    def _begin(self):
        self._initialized = True
        w = self.width()
        h = self.height()
        scale = min(w / 800, h / 600)

        self._text_configs = {
            "name": ("Andrey Dugin", int(42 * scale), QColor(255, 255, 255)),
            "presents": ("presents", int(28 * scale), QColor(255, 255, 255)),
            "title": ("Шашки", int(80 * scale), QColor(255, 255, 255)),
        }

        # Start with name shown as static text
        self._static_text = "name"
        self._elapsed = 0.0
        self._timer.start()

    def _render_text_to_pixels(self, text_key: str) -> list[tuple[float, float]]:
        """Render text to an offscreen image, extract non-black pixel positions."""
        text, font_size, color = self._text_configs[text_key]
        w = self.width()
        h = self.height()

        # Render to offscreen image
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 255))

        painter = QPainter(img)
        font = QFont("Georgia", font_size)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(
            QRectF(0, 0, w, h),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )
        painter.end()

        # Extract pixel positions where text was drawn
        pixels = []
        for y in range(h):
            for x in range(w):
                c = img.pixelColor(x, y)
                if c.red() > 30 or c.green() > 30 or c.blue() > 30:
                    pixels.append((float(x), float(y)))

        # Sample if too many pixels
        if len(pixels) > _MAX_PIXELS:
            pixels = random.sample(pixels, _MAX_PIXELS)

        return pixels

    def _scatter_from_center(self, step: float):
        """Push dots radially outward from screen center.

        Matches original: mas[n] += (mas[n] - center) * random/step
        """
        cx = self.width() / 2
        cy = self.height() / 2
        for dot in self._dots:
            k1 = random.random() / max(step, 0.5)
            k2 = random.random() / max(step, 0.5)
            dx = dot.x - cx
            dy = dot.y - cy
            dot.x = dot.x + dx * k1
            dot.y = dot.y + dy * k2

    def _pull_toward_center(self, step: float):
        """Pull dots toward screen center.

        Matches original: mas[n] -= (mas[n] - center) * random/step
        """
        cx = self.width() / 2
        cy = self.height() / 2
        for dot in self._dots:
            k1 = random.random() / max(step, 0.5)
            k2 = random.random() / max(step, 0.5)
            dx = dot.x - cx
            dy = dot.y - cy
            dot.x = dot.x - dx * k1
            dot.y = dot.y - dy * k2

    def _generate_lightning(self, target_y: float) -> _LightningBolt:
        w = self.width()
        x = w / 2 + random.uniform(-30, 30)
        points = [(x, 0.0)]
        y = 0.0
        segments = random.randint(12, 20)
        for _ in range(segments):
            y += target_y / segments + random.uniform(-5, 5)
            x += random.uniform(-40, 40)
            x = max(50, min(w - 50, x))
            points.append((x, min(y, target_y)))
            if y >= target_y:
                break

        branches = []
        for _ in range(random.randint(2, 4)):
            if len(points) < 3:
                break
            bi = random.randint(1, len(points) - 2)
            bx, by = points[bi]
            bpts = [(bx, by)]
            for _ in range(random.randint(2, 4)):
                bx += random.uniform(-30, 30)
                by += random.uniform(10, 40)
                bpts.append((bx, by))
            branches.append(bpts)

        return _LightningBolt(
            points=points, alpha=1.0,
            width=random.uniform(2.0, 4.0),
            color=QColor(255, 255, 100),
            branches=branches,
        )

    def _tick(self):
        dt = self._fps_interval / 1000.0
        self._elapsed += dt
        t = self._elapsed

        # === Phase: Name visible (0 - 1.5s) ===
        if t >= 1.4 and "name" not in self._screenshot_phases_done:
            self._screenshot_phases_done.add("name")
            self._fire_screenshot("name")

        # === Scatter name (1.5 - 2.8s) ===
        if t >= _T_NAME_HOLD and "init_scatter_1" not in self._phase_done:
            self._phase_done.add("init_scatter_1")
            self._static_text = None
            # Extract pixels from rendered name text
            pixels = self._render_text_to_pixels("name")
            self._dots = [_Dot(x=x, y=y, color=QColor(255, 255, 255)) for x, y in pixels]

        if _T_NAME_HOLD < t < _T_SCATTER_1_END:
            # Scatter step decreases from 100 to 1 (matching original `for a:=1 to 100`)
            total = _T_SCATTER_1_END - _T_NAME_HOLD
            progress = (t - _T_NAME_HOLD) / total
            step = 100.0 * (1.0 - progress) + 1.0
            self._scatter_from_center(step)

        # === Pull toward center → show "presents" (2.8 - 4.1s) ===
        if _T_SCATTER_1_END <= t < _T_ASSEMBLE_1_END:
            total = _T_ASSEMBLE_1_END - _T_SCATTER_1_END
            progress = (t - _T_SCATTER_1_END) / total
            step = 100.0 * (1.0 - progress) + 1.0
            self._pull_toward_center(step)

        if t >= _T_ASSEMBLE_1_END and "show_presents" not in self._phase_done:
            self._phase_done.add("show_presents")
            self._dots.clear()
            self._static_text = "presents"

        if t >= _T_ASSEMBLE_1_END + 0.1 and "presents" not in self._screenshot_phases_done:
            self._screenshot_phases_done.add("presents")
            self._fire_screenshot("presents")

        # === Scatter presents (5.1 - 6.4s) ===
        if t >= _T_PRESENTS_HOLD and "init_scatter_2" not in self._phase_done:
            self._phase_done.add("init_scatter_2")
            self._static_text = None
            pixels = self._render_text_to_pixels("presents")
            self._dots = [_Dot(x=x, y=y, color=QColor(255, 255, 255)) for x, y in pixels]

        if _T_PRESENTS_HOLD < t < _T_SCATTER_2_END:
            total = _T_SCATTER_2_END - _T_PRESENTS_HOLD
            progress = (t - _T_PRESENTS_HOLD) / total
            step = 100.0 * (1.0 - progress) + 1.0
            self._scatter_from_center(step)

        # === Pull toward center → show "Шашки" (6.4 - 7.7s) ===
        if _T_SCATTER_2_END <= t < _T_ASSEMBLE_2_END:
            total = _T_ASSEMBLE_2_END - _T_SCATTER_2_END
            progress = (t - _T_SCATTER_2_END) / total
            step = 100.0 * (1.0 - progress) + 1.0
            self._pull_toward_center(step)

        if t >= _T_ASSEMBLE_2_END and "show_title" not in self._phase_done:
            self._phase_done.add("show_title")
            self._dots.clear()
            self._static_text = "title"
            # Pre-extract title pixels for shimmer
            self._title_dot_positions = self._render_text_to_pixels("title")
            self._title_dot_colors = [QColor(255, 255, 255)] * len(self._title_dot_positions)

        if t >= _T_ASSEMBLE_2_END + 0.1 and "title" not in self._screenshot_phases_done:
            self._screenshot_phases_done.add("title")
            self._fire_screenshot("title")

        # === Lightning (8.7s) ===
        if t >= _T_LIGHTNING and "lightning" not in self._phase_done:
            self._phase_done.add("lightning")
            target_y = self.height() / 2
            for _ in range(3):
                self._bolts.append(self._generate_lightning(target_y))

        if _T_LIGHTNING <= t < _T_LIGHTNING_FLASH:
            self._flash_alpha = min(0.6, (t - _T_LIGHTNING) * 3.0)
        elif _T_LIGHTNING_FLASH <= t < _T_SHIMMER_START:
            self._flash_alpha = max(0.0, 0.6 - (t - _T_LIGHTNING_FLASH) * 6.0)
        else:
            self._flash_alpha = 0.0

        for bolt in self._bolts:
            bolt.alpha -= dt * 2.0
        self._bolts = [b for b in self._bolts if b.alpha > 0]

        # === Shimmer: per-pixel random colors (9.0s+) ===
        if t >= _T_SHIMMER_START and self._title_dot_positions:
            self._shimmer_active = True
            self._static_text = None  # switch from static text to per-pixel drawing
            n = len(self._title_dot_positions)
            # Randomly recolor ~15% of pixels each frame (like original loop)
            for _ in range(max(1, n // 7)):
                idx = random.randint(0, n - 1)
                self._title_dot_colors[idx] = QColor(
                    random.randint(30, 255),
                    random.randint(30, 255),
                    random.randint(30, 255),
                )

        if t >= _T_SHIMMER_START + 0.5 and "subtitle" not in self._screenshot_phases_done:
            self._screenshot_phases_done.add("subtitle")
            self._fire_screenshot("subtitle")

        # === Fade out ===
        if t >= _T_FADEOUT_START:
            self._fade_alpha = min(1.0, (t - _T_FADEOUT_START) / (_T_END - _T_FADEOUT_START))

        if t >= _T_END:
            self._timer.stop()
            self.finished.emit()
            self.close()
            return

        self.update()

    def paintEvent(self, event):
        if not self._initialized:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        # Black background
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        # Draw static text (when not animating)
        if self._static_text is not None and not self._shimmer_active:
            text, font_size, color = self._text_configs[self._static_text]
            font = QFont("Georgia", font_size)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(color)
            painter.drawText(
                QRectF(0, 0, w, h),
                Qt.AlignmentFlag.AlignCenter,
                text,
            )

        # Draw scatter/assemble dots
        if self._dots:
            for dot in self._dots:
                if dot.color:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(dot.color)
                    painter.drawRect(int(dot.x), int(dot.y), 1, 1)

        # Draw shimmer dots
        if self._shimmer_active and self._title_dot_positions:
            for i, (x, y) in enumerate(self._title_dot_positions):
                color = self._title_dot_colors[i]
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRect(int(x), int(y), 1, 1)

        # Lightning
        for bolt in self._bolts:
            self._draw_bolt(painter, bolt)

        # Flash
        if self._flash_alpha > 0:
            flash = QColor(100, 255, 100)
            flash.setAlphaF(self._flash_alpha)
            painter.fillRect(self.rect(), flash)

        # Fade
        if self._fade_alpha > 0:
            overlay = QColor(0, 0, 0)
            overlay.setAlphaF(self._fade_alpha)
            painter.fillRect(self.rect(), overlay)

        painter.end()

    def _draw_bolt(self, painter: QPainter, bolt: _LightningBolt):
        if bolt.alpha <= 0 or len(bolt.points) < 2:
            return
        for width_mult, alpha_mult in [(4.0, 0.15), (2.0, 0.3), (1.0, 1.0)]:
            color = QColor(bolt.color)
            color.setAlphaF(min(1.0, bolt.alpha * alpha_mult))
            pen = QPen(color, bolt.width * width_mult)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            for i in range(len(bolt.points) - 1):
                x1, y1 = bolt.points[i]
                x2, y2 = bolt.points[i + 1]
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            if bolt.branches:
                thinner = QPen(color, bolt.width * width_mult * 0.6)
                thinner.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(thinner)
                for branch in bolt.branches:
                    for i in range(len(branch) - 1):
                        x1, y1 = branch[i]
                        x2, y2 = branch[i + 1]
                        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def keyPressEvent(self, event):
        self._timer.stop()
        self.finished.emit()
        self.close()

    def mousePressEvent(self, event):
        self._timer.stop()
        self.finished.emit()
        self.close()
