"""Animated splash screen — pixel-level scatter/reassemble.

Sequence: "Andrey Dugin" (fade-in) → scatter → reassemble as "presents"
→ scatter → reassemble as "Шашки" → lightning → per-pixel shimmer.
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

_MAX_PIXELS = 2000


@dataclass
class _Dot:
    """A pixel with current position, velocity, and target."""
    x: float
    y: float
    target_x: float = 0.0
    target_y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0


@dataclass
class _LightningBolt:
    points: list[tuple[float, float]]
    alpha: float = 1.0
    width: float = 2.0
    color: QColor | None = None
    branches: list[list[tuple[float, float]]] = field(default_factory=list)


# Phase timing (seconds)
_T_FADE_IN_START = 0.0
_T_FADE_IN_END = 1.2
_T_NAME_HOLD = 2.0
_T_EXPLODE_1 = 2.0       # name explodes
_T_OFFSCREEN_1 = 2.6     # all pixels off-screen
_T_ASSEMBLE_1 = 2.6      # start flying back → "presents"
_T_ASSEMBLED_1 = 3.4     # "presents" assembled
_T_PRESENTS_HOLD = 4.2   # hold "presents"
_T_EXPLODE_2 = 4.2       # presents explodes
_T_OFFSCREEN_2 = 4.8
_T_ASSEMBLE_2 = 4.8
_T_ASSEMBLED_2 = 5.6     # "Шашки" assembled
_T_TITLE_HOLD = 6.6      # hold title
_T_LIGHTNING = 6.6
_T_LIGHTNING_FLASH = 6.8
_T_SHIMMER_START = 6.9
_T_FADEOUT_START = 10.0
_T_END = 10.8


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

        self._dots: list[_Dot] = []
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
            "name": ("Andrey Dugin", int(42 * scale)),
            "presents": ("presents", int(28 * scale)),
            "title": ("Шашки", int(80 * scale)),
        }
        self._static_text = "name"
        self._fade_in_alpha = 0.0
        self._elapsed = 0.0
        self._timer.start()

    def _render_text_pixels(self, text_key: str) -> list[tuple[float, float]]:
        """Render text offscreen, extract pixel positions."""
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

    def _explode_dots(self):
        """Give each dot a radial velocity away from center — fast, like an explosion."""
        cx = self.width() / 2
        cy = self.height() / 2
        # Screen diagonal — pixels must fly beyond this distance
        diag = math.sqrt(self.width() ** 2 + self.height() ** 2)
        for dot in self._dots:
            dx = dot.x - cx
            dy = dot.y - cy
            dist = math.sqrt(dx * dx + dy * dy) + 1
            # Normalize direction, apply speed proportional to screen size
            speed = diag * random.uniform(1.5, 3.0)
            dot.vx = (dx / dist) * speed
            dot.vy = (dy / dist) * speed

    def _assign_targets(self, text_key: str):
        """Assign each dot a target position from the next text's pixels.

        Extra dots get random off-screen targets (will be invisible).
        If we need more dots, spawn them from off-screen positions.
        """
        targets = self._render_text_pixels(text_key)
        random.shuffle(targets)
        w = self.width()
        h = self.height()
        diag = math.sqrt(w * w + h * h)

        # Assign targets to existing dots
        for i, dot in enumerate(self._dots):
            if i < len(targets):
                dot.target_x, dot.target_y = targets[i]
            else:
                # Extra dot — target off-screen, will fade
                dot.target_x = -9999
                dot.target_y = -9999

        # Spawn missing dots from off-screen positions
        for i in range(len(self._dots), len(targets)):
            angle = random.uniform(0, 2 * math.pi)
            r = diag * random.uniform(0.6, 1.0)
            sx = w / 2 + math.cos(angle) * r
            sy = h / 2 + math.sin(angle) * r
            tx, ty = targets[i]
            self._dots.append(_Dot(x=sx, y=sy, target_x=tx, target_y=ty))

    def _animate_explosion(self, dt: float):
        """Move dots along their velocity (outward from center)."""
        for dot in self._dots:
            dot.x += dot.vx * dt
            dot.y += dot.vy * dt
            # Acceleration — speed up as they fly out
            dot.vx *= 1.05
            dot.vy *= 1.05

    def _animate_assembly(self, progress: float):
        """Move dots from current position toward targets. progress: 0→1."""
        t = min(progress, 1.0)
        # Ease-in-out: slow start, fast middle, smooth landing
        if t < 0.5:
            eased = 2 * t * t
        else:
            eased = 1 - (-2 * t + 2) ** 2 / 2

        for dot in self._dots:
            if dot.target_x < -9000:
                continue  # skip dead dots
            if not hasattr(dot, '_asm_sx'):
                dot._asm_sx = dot.x
                dot._asm_sy = dot.y
            dot.x = dot._asm_sx + (dot.target_x - dot._asm_sx) * eased
            dot.y = dot._asm_sy + (dot.target_y - dot._asm_sy) * eased

    def _snap_to_targets(self):
        """Snap all dots to their targets."""
        for dot in self._dots:
            if dot.target_x > -9000:
                dot.x = dot.target_x
                dot.y = dot.target_y
            if hasattr(dot, '_asm_sx'):
                del dot._asm_sx
                del dot._asm_sy

    def _is_dot_visible(self, dot: _Dot) -> bool:
        return -10 <= dot.x <= self.width() + 10 and -10 <= dot.y <= self.height() + 10

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

        # === Fade in "Andrey Dugin" (0 - 1.2s) ===
        if t < _T_FADE_IN_END:
            self._fade_in_alpha = min(1.0, t / _T_FADE_IN_END)

        if t >= 1.4 and "name" not in self._screenshot_phases_done:
            self._screenshot_phases_done.add("name")
            self._fire_screenshot("name")

        # === Explode name (2.0s) ===
        if t >= _T_EXPLODE_1 and "explode_1" not in self._phase_done:
            self._phase_done.add("explode_1")
            self._static_text = None
            self._fade_in_alpha = 1.0
            pixels = self._render_text_pixels("name")
            self._dots = [_Dot(x=x, y=y) for x, y in pixels]
            self._explode_dots()

        if _T_EXPLODE_1 < t < _T_OFFSCREEN_1:
            self._animate_explosion(dt)

        # === Assign targets for "presents", fly back (2.6 - 3.4s) ===
        if t >= _T_ASSEMBLE_1 and "target_1" not in self._phase_done:
            self._phase_done.add("target_1")
            self._assign_targets("presents")

        if _T_ASSEMBLE_1 <= t < _T_ASSEMBLED_1:
            progress = (t - _T_ASSEMBLE_1) / (_T_ASSEMBLED_1 - _T_ASSEMBLE_1)
            self._animate_assembly(progress)

        if t >= _T_ASSEMBLED_1 and "snap_1" not in self._phase_done:
            self._phase_done.add("snap_1")
            self._snap_to_targets()
            self._dots.clear()
            self._static_text = "presents"

        if t >= _T_ASSEMBLED_1 + 0.1 and "presents" not in self._screenshot_phases_done:
            self._screenshot_phases_done.add("presents")
            self._fire_screenshot("presents")

        # === Explode presents (4.2s) ===
        if t >= _T_EXPLODE_2 and "explode_2" not in self._phase_done:
            self._phase_done.add("explode_2")
            self._static_text = None
            pixels = self._render_text_pixels("presents")
            self._dots = [_Dot(x=x, y=y) for x, y in pixels]
            self._explode_dots()

        if _T_EXPLODE_2 < t < _T_OFFSCREEN_2:
            self._animate_explosion(dt)

        # === Assign targets for "Шашки", fly back (4.8 - 5.6s) ===
        if t >= _T_ASSEMBLE_2 and "target_2" not in self._phase_done:
            self._phase_done.add("target_2")
            self._assign_targets("title")

        if _T_ASSEMBLE_2 <= t < _T_ASSEMBLED_2:
            progress = (t - _T_ASSEMBLE_2) / (_T_ASSEMBLED_2 - _T_ASSEMBLE_2)
            self._animate_assembly(progress)

        if t >= _T_ASSEMBLED_2 and "snap_2" not in self._phase_done:
            self._phase_done.add("snap_2")
            self._snap_to_targets()
            self._dots.clear()
            self._static_text = "title"
            self._title_dot_positions = self._render_text_pixels("title")
            self._title_dot_colors = [QColor(255, 255, 255)] * len(self._title_dot_positions)

        if t >= _T_ASSEMBLED_2 + 0.1 and "title" not in self._screenshot_phases_done:
            self._screenshot_phases_done.add("title")
            self._fire_screenshot("title")

        # === Lightning (6.6s) ===
        if t >= _T_LIGHTNING and "lightning" not in self._phase_done:
            self._phase_done.add("lightning")
            for _ in range(3):
                self._bolts.append(self._generate_lightning(self.height() / 2))

        if _T_LIGHTNING <= t < _T_LIGHTNING_FLASH:
            self._flash_alpha = min(0.6, (t - _T_LIGHTNING) * 3.0)
        elif _T_LIGHTNING_FLASH <= t < _T_SHIMMER_START:
            self._flash_alpha = max(0.0, 0.6 - (t - _T_LIGHTNING_FLASH) * 6.0)
        else:
            self._flash_alpha = 0.0

        for bolt in self._bolts:
            bolt.alpha -= dt * 2.0
        self._bolts = [b for b in self._bolts if b.alpha > 0]

        # === Shimmer ===
        if t >= _T_SHIMMER_START and self._title_dot_positions:
            self._shimmer_active = True
            self._static_text = None
            n = len(self._title_dot_positions)
            for _ in range(max(1, n // 7)):
                idx = random.randint(0, n - 1)
                self._title_dot_colors[idx] = QColor(
                    random.randint(30, 255),
                    random.randint(30, 255),
                    random.randint(30, 255),
                )

        if t >= _T_SHIMMER_START + 0.5 and "shimmer" not in self._screenshot_phases_done:
            self._screenshot_phases_done.add("shimmer")
            self._fire_screenshot("shimmer")

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
        w = self.width()
        h = self.height()

        # Black background
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        # Static text (with fade-in support)
        if self._static_text is not None and not self._shimmer_active:
            text, font_size = self._text_configs[self._static_text]
            font = QFont("Georgia", font_size)
            font.setBold(True)
            painter.setFont(font)
            color = QColor(255, 255, 255)
            color.setAlphaF(self._fade_in_alpha if self._static_text == "name" and self._elapsed < _T_FADE_IN_END + 0.5 else 1.0)
            painter.setPen(color)
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, text)

        # Scatter/assemble dots
        if self._dots:
            painter.setPen(Qt.PenStyle.NoPen)
            white = QColor(255, 255, 255)
            painter.setBrush(white)
            for dot in self._dots:
                ix, iy = int(dot.x), int(dot.y)
                if -10 <= ix <= w + 10 and -10 <= iy <= h + 10:
                    painter.drawRect(ix, iy, 1, 1)

        # Shimmer
        if self._shimmer_active and self._title_dot_positions:
            painter.setPen(Qt.PenStyle.NoPen)
            for i, (x, y) in enumerate(self._title_dot_positions):
                painter.setBrush(self._title_dot_colors[i])
                painter.drawRect(int(x), int(y), 1, 1)

        # Lightning
        for bolt in self._bolts:
            self._draw_bolt(painter, bolt)

        # Flash
        if self._flash_alpha > 0:
            flash = QColor(100, 255, 100)
            flash.setAlphaF(self._flash_alpha)
            painter.fillRect(self.rect(), flash)

        # Fade overlay
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
