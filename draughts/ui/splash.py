"""Animated splash screen for the draughts game.

Recreates the original Pascal splash sequence:
  "Andrey Dugin" → scatter → reassemble as "presents"
  "presents" → scatter → reassemble as "Шашки"
  Lightning strikes "Шашки" → sparkle shimmer effect
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import QWidget


@dataclass
class _Pixel:
    """A single pixel-particle used in scatter/reassemble animations."""
    x: float
    y: float
    target_x: float = 0.0
    target_y: float = 0.0
    char: str = ""
    font_size: int = 24
    color: QColor | None = None
    alpha: float = 1.0
    shimmer_color: QColor | None = None
    dead: bool = False  # extra pixels that should not be drawn


@dataclass
class _LightningBolt:
    points: list[tuple[float, float]]
    alpha: float = 1.0
    width: float = 2.0
    color: QColor | None = None
    branches: list[list[tuple[float, float]]] = field(default_factory=list)

    def __post_init__(self):
        if self.color is None:
            self.color = QColor(255, 255, 100)


# ---------------------------------------------------------------------------
# Phase timing
# ---------------------------------------------------------------------------

# Phase 1: "Andrey Dugin" appears, holds, then scatters → reassembles as "presents"
# Phase 2: "presents" holds, then scatters → reassembles as "Шашки"
# Phase 3: "Шашки" holds, lightning strikes, shimmer effect

_T_SHOW_NAME = 0.0          # name appears instantly
_T_NAME_HOLD = 1.5          # hold name for 1.5s
_T_SCATTER_1_END = 2.5      # scatter takes 1.0s
_T_ASSEMBLE_1_END = 3.5     # reassemble into "presents" takes 1.0s
_T_PRESENTS_HOLD = 4.5      # hold "presents" for 1.0s
_T_SCATTER_2_END = 5.5      # scatter takes 1.0s
_T_ASSEMBLE_2_END = 6.5     # reassemble into "Шашки" takes 1.0s
_T_TITLE_HOLD = 7.5         # hold title for 1.0s
_T_LIGHTNING = 7.5           # lightning strikes at this moment
_T_LIGHTNING_FLASH = 7.7     # green flash
_T_SHIMMER_START = 7.8       # shimmer begins
_T_SUBTITLE_START = 8.0      # subtitle fades in
_T_FADEOUT_START = 10.0      # fade to black
_T_END = 10.8                # done


class SplashScreen(QWidget):
    """Full-screen animated splash with scatter/reassemble and lightning."""

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
        self._fps_interval = 16  # ms (~60fps)

        # Pixel-particles for transitions
        self._pixels: list[_Pixel] = []

        # Title pixels (for shimmer)
        self._title_pixels: list[_Pixel] = []
        self._shimmer_active = False

        # Lightning
        self._bolts: list[_LightningBolt] = []
        self._flash_alpha = 0.0

        # Subtitle
        self._subtitle_alpha = 0.0
        self._fade_alpha = 0.0

        # Text metrics cache
        self._text_positions: dict[str, list[tuple[float, float, str, int]]] = {}

        # Timer
        self._timer = QTimer(self)
        self._timer.setInterval(self._fps_interval)
        self._timer.timeout.connect(self._tick)

        self._initialized = False
        self._phase_done: set[str] = set()

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
        self._init_text_data()
        self._elapsed = 0.0
        # Start with "Andrey Dugin" fully assembled
        self._pixels = self._make_text_pixels("name")
        self._timer.start()

    def _init_text_data(self):
        """Pre-compute character positions for all text phases."""
        self._initialized = True
        w = self.width()
        h = self.height()
        scale = min(w / 800, h / 600)

        self._text_positions["name"] = self._compute_text_layout(
            "Andrey Dugin", int(42 * scale), w / 2, h / 2,
            QColor(255, 255, 220),
        )
        self._text_positions["presents"] = self._compute_text_layout(
            "presents", int(28 * scale), w / 2, h / 2,
            QColor(200, 200, 200),
        )
        self._text_positions["title"] = self._compute_text_layout(
            "Шашки", int(80 * scale), w / 2, h / 2,
            QColor(255, 255, 100),
        )

    def _compute_text_layout(
        self, text: str, font_size: int, center_x: float, center_y: float,
        color: QColor,
    ) -> list[tuple[float, float, str, int, QColor]]:
        """Return list of (x, y, char, font_size, color) for each character."""
        font = QFont("Georgia", font_size)
        font.setBold(True)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(text)
        text_height = fm.height()

        start_x = center_x - text_width / 2
        baseline_y = center_y + text_height / 4
        result = []
        x_cursor = start_x

        for ch in text:
            if ch == ' ':
                x_cursor += fm.horizontalAdvance(' ')
                continue
            char_w = fm.horizontalAdvance(ch)
            result.append((x_cursor, baseline_y, ch, font_size, QColor(color)))
            x_cursor += char_w

        return result

    def _make_text_pixels(self, text_key: str) -> list[_Pixel]:
        """Create pixel list with all chars at their target positions."""
        pixels = []
        for x, y, ch, fs, color in self._text_positions[text_key]:
            pixels.append(_Pixel(
                x=x, y=y,
                target_x=x, target_y=y,
                char=ch, font_size=fs,
                color=QColor(color), alpha=1.0,
            ))
        return pixels

    def _scatter_pixels(self):
        """Push all pixels outward from center (like original breaking)."""
        cx = self.width() / 2
        cy = self.height() / 2
        for p in self._pixels:
            dx = p.x - cx
            dy = p.y - cy
            dist = math.sqrt(dx * dx + dy * dy) + 1
            # Scatter outward with some randomness
            factor = random.uniform(3.0, 6.0)
            p.target_x = p.x + dx * factor + random.uniform(-50, 50)
            p.target_y = p.y + dy * factor + random.uniform(-50, 50)

    def _retarget_pixels_to(self, text_key: str):
        """Set new target positions from a different text layout.

        Reuses existing scattered pixels — assigns each one a new target
        from the destination text. Extra pixels fade out, missing ones spawn.
        """
        targets = list(self._text_positions[text_key])
        # Match existing pixels to new targets
        for i, p in enumerate(self._pixels):
            if i < len(targets):
                tx, ty, ch, fs, color = targets[i]
                p.target_x = tx
                p.target_y = ty
                p.char = ch
                p.font_size = fs
                p.color = QColor(color)
                p.dead = False
            else:
                # Extra pixel — mark as dead
                p.dead = True
                p.alpha = 0.0

        # If we need more pixels than we have, spawn new ones from random positions
        for i in range(len(self._pixels), len(targets)):
            tx, ty, ch, fs, color = targets[i]
            p = _Pixel(
                x=random.uniform(0, self.width()),
                y=random.uniform(0, self.height()),
                target_x=tx, target_y=ty,
                char=ch, font_size=fs,
                color=QColor(color), alpha=0.3,
            )
            self._pixels.append(p)

    def _animate_pixels(self, progress: float):
        """Move pixels toward their targets. progress: 0→1."""
        t = min(progress, 1.0)
        eased = 1.0 - (1.0 - t) ** 3  # ease-out cubic
        for p in self._pixels:
            if p.dead:
                continue
            # Store start pos on first call
            if not hasattr(p, '_anim_sx'):
                p._anim_sx = p.x
                p._anim_sy = p.y
            p.x = p._anim_sx + (p.target_x - p._anim_sx) * eased
            p.y = p._anim_sy + (p.target_y - p._anim_sy) * eased
            p.alpha = min(1.0, 0.3 + eased * 0.7)

    def _snap_pixels_to_targets(self):
        """Ensure all pixels are exactly at their target positions."""
        for p in self._pixels:
            p.x = p.target_x
            p.y = p.target_y
            p.alpha = 1.0
            if hasattr(p, '_anim_sx'):
                del p._anim_sx
                del p._anim_sy

    def _reset_anim_starts(self):
        """Reset animation start positions to current positions."""
        for p in self._pixels:
            if hasattr(p, '_anim_sx'):
                del p._anim_sx
                del p._anim_sy

    def _generate_lightning(self, target_y: float) -> _LightningBolt:
        """Generate lightning bolt from top of screen to target_y."""
        w = self.width()
        x_start = w / 2 + random.uniform(-50, 50)
        points = [(x_start, 0.0)]
        x, y = x_start, 0.0
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

        # === Phase 1: Name visible (0 - 1.5s) ===
        # pixels already set in _begin

        # Screenshot: name assembled
        if t >= 1.4 and "name" not in self._screenshot_phases_done:
            self._screenshot_phases_done.add("name")
            self._fire_screenshot("name")

        # === Scatter name (1.5 - 2.5s) ===
        if t >= _T_NAME_HOLD and "scatter_1" not in self._phase_done:
            self._phase_done.add("scatter_1")
            self._scatter_pixels()
            self._reset_anim_starts()

        if _T_NAME_HOLD <= t < _T_SCATTER_1_END:
            progress = (t - _T_NAME_HOLD) / (_T_SCATTER_1_END - _T_NAME_HOLD)
            self._animate_pixels(progress)
            # Fade out during scatter
            for p in self._pixels:
                p.alpha = max(0.1, 1.0 - progress * 0.7)

        # === Reassemble into "presents" (2.5 - 3.5s) ===
        if t >= _T_SCATTER_1_END and "retarget_1" not in self._phase_done:
            self._phase_done.add("retarget_1")
            self._snap_pixels_to_targets()  # finalize scatter positions
            self._retarget_pixels_to("presents")
            self._reset_anim_starts()

        if _T_SCATTER_1_END <= t < _T_ASSEMBLE_1_END:
            progress = (t - _T_SCATTER_1_END) / (_T_ASSEMBLE_1_END - _T_SCATTER_1_END)
            self._animate_pixels(progress)

        if t >= _T_ASSEMBLE_1_END and "snap_1" not in self._phase_done:
            self._phase_done.add("snap_1")
            self._snap_pixels_to_targets()

        # Screenshot: presents assembled
        if t >= _T_ASSEMBLE_1_END + 0.1 and "presents" not in self._screenshot_phases_done:
            self._screenshot_phases_done.add("presents")
            self._fire_screenshot("presents")

        # === Scatter presents (4.5 - 5.5s) ===
        if t >= _T_PRESENTS_HOLD and "scatter_2" not in self._phase_done:
            self._phase_done.add("scatter_2")
            self._scatter_pixels()
            self._reset_anim_starts()

        if _T_PRESENTS_HOLD <= t < _T_SCATTER_2_END:
            progress = (t - _T_PRESENTS_HOLD) / (_T_SCATTER_2_END - _T_PRESENTS_HOLD)
            self._animate_pixels(progress)
            for p in self._pixels:
                p.alpha = max(0.1, 1.0 - progress * 0.7)

        # === Reassemble into "Шашки" (5.5 - 6.5s) ===
        if t >= _T_SCATTER_2_END and "retarget_2" not in self._phase_done:
            self._phase_done.add("retarget_2")
            self._snap_pixels_to_targets()
            self._retarget_pixels_to("title")
            self._reset_anim_starts()

        if _T_SCATTER_2_END <= t < _T_ASSEMBLE_2_END:
            progress = (t - _T_SCATTER_2_END) / (_T_ASSEMBLE_2_END - _T_SCATTER_2_END)
            self._animate_pixels(progress)

        if t >= _T_ASSEMBLE_2_END and "snap_2" not in self._phase_done:
            self._phase_done.add("snap_2")
            self._snap_pixels_to_targets()
            # Copy to title_pixels for shimmer
            self._title_pixels = list(self._pixels)

        # Screenshot: title assembled
        if t >= _T_ASSEMBLE_2_END + 0.1 and "title" not in self._screenshot_phases_done:
            self._screenshot_phases_done.add("title")
            self._fire_screenshot("title")

        # === Lightning (7.5s) ===
        if t >= _T_LIGHTNING and "lightning" not in self._phase_done:
            self._phase_done.add("lightning")
            target_y = self.height() / 2
            for _ in range(3):
                self._bolts.append(self._generate_lightning(target_y))

        # Flash effect
        if _T_LIGHTNING <= t < _T_LIGHTNING_FLASH:
            self._flash_alpha = min(0.6, (t - _T_LIGHTNING) * 3.0)
        elif _T_LIGHTNING_FLASH <= t < _T_SHIMMER_START:
            self._flash_alpha = max(0.0, 0.6 - (t - _T_LIGHTNING_FLASH) * 6.0)
        else:
            self._flash_alpha = 0.0

        # Decay lightning bolts
        for bolt in self._bolts:
            bolt.alpha -= dt * 2.0
        self._bolts = [b for b in self._bolts if b.alpha > 0]

        # === Shimmer (7.8s+) ===
        if t >= _T_SHIMMER_START:
            self._shimmer_active = True
            for p in self._title_pixels:
                if random.random() < 0.15:
                    p.shimmer_color = QColor(
                        random.randint(50, 255),
                        random.randint(50, 255),
                        random.randint(50, 255),
                    )
                elif random.random() < 0.05:
                    p.shimmer_color = None  # return to original

        # === Subtitle (8.0s+) ===
        if t >= _T_SUBTITLE_START:
            self._subtitle_alpha = min(1.0, (t - _T_SUBTITLE_START) / 0.5)

        # Screenshot: shimmer + subtitle
        if t >= _T_SUBTITLE_START + 0.5 and "subtitle" not in self._screenshot_phases_done:
            self._screenshot_phases_done.add("subtitle")
            self._fire_screenshot("subtitle")

        # === Fade out (10.0 - 10.8s) ===
        if t >= _T_FADEOUT_START:
            self._fade_alpha = min(1.0, (t - _T_FADEOUT_START) / (_T_END - _T_FADEOUT_START))

        # Done
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

        # Dark background
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor(5, 5, 20))
        grad.setColorAt(0.5, QColor(10, 10, 35))
        grad.setColorAt(1, QColor(5, 5, 15))
        painter.fillRect(self.rect(), grad)

        # Draw pixels (scatter/assemble animation or static text)
        if self._shimmer_active:
            self._draw_pixels(painter, self._title_pixels, shimmer=True)
        else:
            self._draw_pixels(painter, self._pixels)

        # Lightning
        for bolt in self._bolts:
            self._draw_bolt(painter, bolt)

        # Lightning flash overlay
        if self._flash_alpha > 0:
            flash = QColor(100, 255, 100)
            flash.setAlphaF(self._flash_alpha)
            painter.fillRect(self.rect(), flash)

        # Subtitle
        if self._subtitle_alpha > 0:
            scale = min(w / 800, h / 600)
            font = QFont("Arial", int(16 * scale))
            painter.setFont(font)
            color = QColor(160, 160, 180)
            color.setAlphaF(self._subtitle_alpha)
            painter.setPen(color)
            rect = QRectF(0, h / 2 + 80 * scale, w, 40 * scale)
            painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                             "Based on original (1998\u20132000)")

        # Fade overlay
        if self._fade_alpha > 0:
            overlay = QColor(0, 0, 0)
            overlay.setAlphaF(self._fade_alpha)
            painter.fillRect(self.rect(), overlay)

        painter.end()

    def _draw_pixels(self, painter: QPainter, pixels: list[_Pixel], shimmer: bool = False):
        for p in pixels:
            if p.dead or p.alpha <= 0.01:
                continue

            font = QFont("Georgia", p.font_size)
            font.setBold(True)
            painter.setFont(font)

            draw_color = p.shimmer_color if (shimmer and p.shimmer_color) else p.color
            if draw_color is None:
                draw_color = QColor(255, 255, 255)

            # Glow
            if p.alpha > 0.3:
                glow = QColor(draw_color)
                glow.setAlphaF(p.alpha * 0.2)
                painter.setPen(glow)
                offset = p.font_size * 0.03
                for dx, dy in [(-offset, 0), (offset, 0), (0, -offset), (0, offset)]:
                    painter.drawText(QPointF(p.x + dx, p.y + dy), p.char)

            # Main char
            color = QColor(draw_color)
            color.setAlphaF(min(1.0, p.alpha))
            painter.setPen(color)
            painter.drawText(QPointF(p.x, p.y), p.char)

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
