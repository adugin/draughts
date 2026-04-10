"""Animated splash screen — pixel-level scatter/reassemble.

"Andrey Dugin" (fade-in) → explode → reverse-explode into "presents"
→ explode → reverse-explode into "Шашки" → lightning → shimmer.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import QWidget

_MAX_PIXELS = 8000


@dataclass
class _Dot:
    x: float
    y: float
    start_x: float = 0.0
    start_y: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0


@dataclass
class _LightningBolt:
    points: list[tuple[float, float]]
    alpha: float = 1.0
    width: float = 2.0
    color: QColor | None = None
    branches: list[list[tuple[float, float]]] = field(default_factory=list)


# Phase timing
_T_FADE_IN_END = 0.8
_T_NAME_HOLD = 1.2           # 0.8s fade-in + 0.4s hold

# Transition 1: name → presents
_T_EXPLODE_1_DUR = 0.4
_T_ASSEMBLE_1_DUR = 0.5

_T_PRESENTS_HOLD_DUR = 0.4   # short hold

# Transition 2: presents → title
_T_EXPLODE_2_DUR = 0.4
_T_ASSEMBLE_2_DUR = 0.5

_T_TITLE_HOLD_DUR = 0.5      # hold title before lightning

# Shimmer
_T_SHIMMER_DUR = 3.0
_T_FADEOUT_DUR = 0.8


def _compute_times():
    """Compute absolute timestamps from durations."""
    t = {}
    t["explode_1_start"] = _T_NAME_HOLD
    t["explode_1_end"] = t["explode_1_start"] + _T_EXPLODE_1_DUR
    t["assemble_1_start"] = t["explode_1_end"]  # NO gap
    t["assemble_1_end"] = t["assemble_1_start"] + _T_ASSEMBLE_1_DUR
    t["presents_hold_end"] = t["assemble_1_end"] + _T_PRESENTS_HOLD_DUR

    t["explode_2_start"] = t["presents_hold_end"]
    t["explode_2_end"] = t["explode_2_start"] + _T_EXPLODE_2_DUR
    t["assemble_2_start"] = t["explode_2_end"]  # NO gap
    t["assemble_2_end"] = t["assemble_2_start"] + _T_ASSEMBLE_2_DUR
    t["title_hold_end"] = t["assemble_2_end"] + _T_TITLE_HOLD_DUR

    t["lightning"] = t["title_hold_end"]
    t["shimmer_start"] = t["lightning"] + 0.2
    t["fadeout_start"] = t["shimmer_start"] + _T_SHIMMER_DUR
    t["end"] = t["fadeout_start"] + _T_FADEOUT_DUR
    return t


_T = _compute_times()


class SplashScreen(QWidget):
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

        # Explosion dots (current text flying outward)
        self._explode_dots: list[_Dot] = []
        # Assembly dots (next text flying inward from pre-computed positions)
        self._assemble_dots: list[_Dot] = []

        self._fade_in_alpha = 0.0
        self._static_text: str | None = None

        # Shimmer
        self._title_dot_positions: list[tuple[float, float]] = []
        self._title_dot_colors: list[QColor] = []
        self._shimmer_active = False

        # Lightning
        self._bolts: list[_LightningBolt] = []
        self._flash_alpha = 0.0
        self._fade_alpha = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(self._fps_interval)
        self._timer.timeout.connect(self._tick)

        self._initialized = False
        self._phase_done: set[str] = set()
        self._text_configs: dict[str, tuple[str, int]] = {}

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
            "name": ("Andrey Dugin", int(42 * scale)),
            "presents": ("presents", int(28 * scale)),
            "title": ("Шашки", int(80 * scale)),
        }
        self._static_text = "name"
        self._fade_in_alpha = 0.0
        self._elapsed = 0.0
        self._timer.start()

    def _render_text_pixels(self, text_key: str) -> list[tuple[float, float]]:
        text, font_size = self._text_configs[text_key]
        w = self.width()
        h = self.height()
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 255))
        painter = QPainter(img)
        font = QFont("Georgia", font_size)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()

        pixels = []
        for y in range(h):
            for x in range(w):
                c = img.pixelColor(x, y)
                if c.red() > 30 or c.green() > 30 or c.blue() > 30:
                    pixels.append((float(x), float(y)))

        if len(pixels) > _MAX_PIXELS:
            pixels = random.sample(pixels, _MAX_PIXELS)
        return pixels

    def _compute_exploded_position(self, px: float, py: float) -> tuple[float, float]:
        """Compute where a pixel at (px, py) would end up after radial explosion.

        Flies far beyond screen edges along the radial direction from center.
        """
        cx = self.width() / 2
        cy = self.height() / 2
        dx = px - cx
        dy = py - cy
        dist = math.sqrt(dx * dx + dy * dy) + 1
        # Fly to 2-3x screen diagonal distance
        diag = math.sqrt(self.width() ** 2 + self.height() ** 2)
        factor = diag * random.uniform(1.5, 2.5) / dist
        return (px + dx * factor, py + dy * factor)

    def _create_explode_dots(self, text_key: str) -> list[_Dot]:
        """Create dots for explosion: start at text positions, targets far off-screen."""
        pixels = self._render_text_pixels(text_key)
        dots = []
        for px, py in pixels:
            ex, ey = self._compute_exploded_position(px, py)
            dots.append(_Dot(x=px, y=py, start_x=px, start_y=py, target_x=ex, target_y=ey))
        return dots

    def _create_assemble_dots(self, text_key: str) -> list[_Dot]:
        """Create dots for reverse-explosion: start far off-screen, targets at text positions.

        This is the reverse of an explosion — each pixel of the next text starts from
        where it WOULD HAVE BEEN after exploding, and flies back to its text position.
        """
        pixels = self._render_text_pixels(text_key)
        dots = []
        for px, py in pixels:
            ex, ey = self._compute_exploded_position(px, py)
            dots.append(_Dot(x=ex, y=ey, start_x=ex, start_y=ey, target_x=px, target_y=py))
        return dots

    def _animate_dots(self, dots: list[_Dot], progress: float):
        """Interpolate dots from start to target. progress: 0→1.

        Uses ease-in for explosion (slow start, fast end)
        and ease-out for assembly (fast start, slow landing).
        """
        t = max(0.0, min(progress, 1.0))
        # Ease-in-out quadratic
        if t < 0.5:
            eased = 2 * t * t
        else:
            eased = 1 - (-2 * t + 2) ** 2 / 2

        for dot in dots:
            dot.x = dot.start_x + (dot.target_x - dot.start_x) * eased
            dot.y = dot.start_y + (dot.target_y - dot.start_y) * eased

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

        # === Fade in name ===
        if t < _T_FADE_IN_END:
            self._fade_in_alpha = min(1.0, t / _T_FADE_IN_END)

        # === Transition 1: name → presents ===

        # Explode name
        if t >= _T["explode_1_start"] and "explode_1" not in self._phase_done:
            self._phase_done.add("explode_1")
            self._fire_screenshot("name")
            self._static_text = None
            self._fade_in_alpha = 1.0
            self._explode_dots = self._create_explode_dots("name")
            self._assemble_dots = self._create_assemble_dots("presents")

        if _T["explode_1_start"] <= t < _T["explode_1_end"]:
            progress = (t - _T["explode_1_start"]) / _T_EXPLODE_1_DUR
            self._animate_dots(self._explode_dots, progress)

        # Assemble presents (starts immediately after explode ends)
        if _T["assemble_1_start"] <= t < _T["assemble_1_end"]:
            self._explode_dots.clear()  # explosion done
            progress = (t - _T["assemble_1_start"]) / _T_ASSEMBLE_1_DUR
            self._animate_dots(self._assemble_dots, progress)

        if t >= _T["assemble_1_end"] and "snap_1" not in self._phase_done:
            self._phase_done.add("snap_1")
            self._assemble_dots.clear()
            self._static_text = "presents"
            self._fire_screenshot("presents")

        # === Transition 2: presents → title ===

        if t >= _T["explode_2_start"] and "explode_2" not in self._phase_done:
            self._phase_done.add("explode_2")
            self._static_text = None
            self._explode_dots = self._create_explode_dots("presents")
            self._assemble_dots = self._create_assemble_dots("title")

        if _T["explode_2_start"] <= t < _T["explode_2_end"]:
            progress = (t - _T["explode_2_start"]) / _T_EXPLODE_2_DUR
            self._animate_dots(self._explode_dots, progress)

        if _T["assemble_2_start"] <= t < _T["assemble_2_end"]:
            self._explode_dots.clear()
            progress = (t - _T["assemble_2_start"]) / _T_ASSEMBLE_2_DUR
            self._animate_dots(self._assemble_dots, progress)

        if t >= _T["assemble_2_end"] and "snap_2" not in self._phase_done:
            self._phase_done.add("snap_2")
            self._assemble_dots.clear()
            self._static_text = "title"
            self._title_dot_positions = self._render_text_pixels("title")
            self._title_dot_colors = [QColor(255, 255, 255)] * len(self._title_dot_positions)
            self._fire_screenshot("title")

        # === Lightning ===
        if t >= _T["lightning"] and "lightning" not in self._phase_done:
            self._phase_done.add("lightning")
            for _ in range(3):
                self._bolts.append(self._generate_lightning(self.height() / 2))

        if _T["lightning"] <= t < _T["lightning"] + 0.2:
            self._flash_alpha = min(0.6, (t - _T["lightning"]) * 3.0)
        elif _T["lightning"] + 0.2 <= t < _T["shimmer_start"]:
            self._flash_alpha = max(0.0, 0.6 - (t - _T["lightning"] - 0.2) * 6.0)
        else:
            self._flash_alpha = 0.0

        for bolt in self._bolts:
            bolt.alpha -= dt * 2.0
        self._bolts = [b for b in self._bolts if b.alpha > 0]

        # === Shimmer (drawn over static text — don't clear static_text) ===
        if t >= _T["shimmer_start"] and self._title_dot_positions:
            if not self._shimmer_active:
                self._shimmer_active = True
                # First shimmer frame — fire screenshot after a few iterations
                self._shimmer_frame_count = 0
            self._shimmer_frame_count = getattr(self, '_shimmer_frame_count', 0) + 1
            if self._shimmer_frame_count == 30:  # ~0.5s of shimmer
                self._fire_screenshot("shimmer")
            n = len(self._title_dot_positions)
            for _ in range(max(1, n // 7)):
                idx = random.randint(0, n - 1)
                self._title_dot_colors[idx] = QColor(
                    random.randint(100, 255),
                    random.randint(100, 255),
                    random.randint(100, 255),
                )

        # === Fade out ===
        if t >= _T["fadeout_start"]:
            self._fade_alpha = min(1.0, (t - _T["fadeout_start"]) / _T_FADEOUT_DUR)

        if t >= _T["end"]:
            self._timer.stop()
            self.finished.emit()
            self.close()
            return

        self.update()

    def paintEvent(self, event):
        if not self._initialized:
            return
        painter = QPainter(self)
        w = self.width()
        h = self.height()

        painter.fillRect(self.rect(), QColor(0, 0, 0))

        # Static text (always drawn when set — shimmer overlays on top)
        if self._static_text is not None:
            text, font_size = self._text_configs[self._static_text]
            font = QFont("Georgia", font_size)
            font.setBold(True)
            painter.setFont(font)
            alpha = self._fade_in_alpha if self._static_text == "name" and self._elapsed < _T_FADE_IN_END + 0.5 else 1.0
            color = QColor(255, 255, 255)
            color.setAlphaF(alpha)
            painter.setPen(color)
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, text)

        # Explosion + assembly dots
        all_dots = self._explode_dots + self._assemble_dots
        if all_dots:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            for dot in all_dots:
                ix, iy = int(dot.x), int(dot.y)
                if 0 <= ix < w and 0 <= iy < h:
                    painter.drawRect(ix, iy, 1, 1)

        # Shimmer — draw 2x2 dots to compensate for pixel sampling
        if self._shimmer_active and self._title_dot_positions:
            painter.setPen(Qt.PenStyle.NoPen)
            for i, (x, y) in enumerate(self._title_dot_positions):
                painter.setBrush(self._title_dot_colors[i])
                painter.drawRect(int(x), int(y), 2, 2)

        # Lightning
        for bolt in self._bolts:
            self._draw_bolt(painter, bolt)

        if self._flash_alpha > 0:
            flash = QColor(100, 255, 100)
            flash.setAlphaF(self._flash_alpha)
            painter.fillRect(self.rect(), flash)

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
