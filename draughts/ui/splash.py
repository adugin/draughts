"""Animated splash screen for the draughts game.

Recreates the original Pascal splash sequence:
  Dugin -> Andrew -> presents -> Draughts
with lightning effects and text particle animations.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QFont, QFontMetrics,
    QLinearGradient, QRadialGradient, QPainterPath,
)
from PyQt6.QtWidgets import QWidget


# ---------------------------------------------------------------------------
# Particle system for text scatter/assemble effects
# ---------------------------------------------------------------------------

@dataclass
class _Particle:
    """A single particle that flies from a random position to its target."""
    # Target position (where the particle should end up)
    tx: float
    ty: float
    # Current position
    x: float
    y: float
    # Velocity for scatter phase
    vx: float
    vy: float
    # Appearance
    char: str
    color: QColor
    alpha: float = 0.0
    font_size: int = 24
    settled: bool = False


@dataclass
class _LightningBolt:
    """A single lightning bolt defined as a list of points."""
    points: list[tuple[float, float]]
    alpha: float = 1.0
    width: float = 2.0
    color: QColor | None = None
    branches: list[list[tuple[float, float]]] | None = None

    def __post_init__(self):
        if self.color is None:
            self.color = QColor(180, 200, 255)


# ---------------------------------------------------------------------------
# Splash phases
# ---------------------------------------------------------------------------

_PHASE_DARK = 0           # 0.0 - 0.3s: dark screen
_PHASE_LIGHTNING_1 = 1    # 0.3 - 0.7s: first lightning
_PHASE_NAME = 2           # 0.7 - 1.7s: "Dugin Andrew" assembles
_PHASE_TRANSITION = 3     # 1.7 - 2.0s: fade transition
_PHASE_PRESENTS = 4       # 2.0 - 2.6s: "presents" appears
_PHASE_LIGHTNING_2 = 5    # 2.6 - 3.0s: second lightning
_PHASE_TITLE = 6          # 3.0 - 4.0s: big title assembles
_PHASE_SUBTITLE = 7       # 4.0 - 4.5s: subtitle fades in
_PHASE_FADEOUT = 8        # 4.5 - 5.0s: fade to black, then done

_TOTAL_DURATION = 5.0  # seconds


class SplashScreen(QWidget):
    """Full-screen animated splash with lightning and text effects."""

    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet("background: black;")

        self._elapsed = 0.0  # seconds
        self._fps_interval = 16  # ms (~60fps)

        # Particles for each text phase
        self._name_particles: list[_Particle] = []
        self._presents_particles: list[_Particle] = []
        self._title_particles: list[_Particle] = []
        self._subtitle_alpha = 0.0
        self._fade_alpha = 0.0

        # Lightning
        self._bolts: list[_LightningBolt] = []
        self._bolt_timer = 0.0

        # Timer
        self._timer = QTimer(self)
        self._timer.setInterval(self._fps_interval)
        self._timer.timeout.connect(self._tick)

        self._initialized = False

    def show_animated(self):
        """Start the splash animation."""
        self.showFullScreen()
        # Small delay to let the window fully show before starting
        QTimer.singleShot(50, self._begin)

    def _begin(self):
        self._init_particles()
        self._elapsed = 0.0
        self._timer.start()

    def _init_particles(self):
        """Pre-compute particle targets based on current screen size."""
        self._initialized = True
        w = self.width()
        h = self.height()
        scale = min(w / 800, h / 600)  # reference 800x600

        # "Dugin Andrew"
        self._name_particles = self._text_to_particles(
            "Dugin Andrew",
            font_size=int(42 * scale),
            center_x=w / 2, center_y=h / 2 - 20 * scale,
            color=QColor(255, 255, 220),
        )

        # "presents"
        self._presents_particles = self._text_to_particles(
            "presents",
            font_size=int(28 * scale),
            center_x=w / 2, center_y=h / 2 + 30 * scale,
            color=QColor(200, 200, 200),
        )

        # Main title
        self._title_particles = self._text_to_particles(
            "\u0428\u0430\u0448\u043a\u0438",
            font_size=int(80 * scale),
            center_x=w / 2, center_y=h / 2,
            color=QColor(255, 255, 100),
        )

    def _text_to_particles(
        self, text: str, font_size: int, center_x: float, center_y: float,
        color: QColor,
    ) -> list[_Particle]:
        """Convert a text string into a list of character particles."""
        font = QFont("Georgia", font_size)
        font.setBold(True)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(text)
        text_height = fm.height()

        start_x = center_x - text_width / 2
        baseline_y = center_y + text_height / 4

        particles = []
        x_cursor = start_x
        w = self.width()
        h = self.height()

        for ch in text:
            if ch == ' ':
                x_cursor += fm.horizontalAdvance(' ')
                continue

            char_w = fm.horizontalAdvance(ch)
            tx = x_cursor + char_w / 2
            ty = baseline_y

            # Start from random scattered position
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(200, max(w, h) * 0.6)
            sx = tx + math.cos(angle) * dist
            sy = ty + math.sin(angle) * dist

            particles.append(_Particle(
                tx=tx, ty=ty,
                x=sx, y=sy,
                vx=0, vy=0,
                char=ch,
                color=QColor(color),
                alpha=0.0,
                font_size=font_size,
            ))
            x_cursor += char_w

        return particles

    def _generate_lightning(self, x_start: float | None = None) -> _LightningBolt:
        """Generate a random jagged lightning bolt."""
        w = self.width()
        h = self.height()

        if x_start is None:
            x_start = random.uniform(w * 0.2, w * 0.8)

        points = [(x_start, 0.0)]
        x, y = x_start, 0.0
        segments = random.randint(8, 15)

        for i in range(segments):
            y += h / segments + random.uniform(-10, 10)
            x += random.uniform(-60, 60)
            x = max(20, min(w - 20, x))
            points.append((x, min(y, h)))

        # Generate 1-3 branches
        branches = []
        for _ in range(random.randint(1, 3)):
            if len(points) < 3:
                break
            branch_start = random.randint(1, len(points) - 2)
            bx, by = points[branch_start]
            branch_pts = [(bx, by)]
            for _ in range(random.randint(2, 5)):
                bx += random.uniform(-40, 40)
                by += random.uniform(20, 50)
                branch_pts.append((bx, min(by, h)))
            branches.append(branch_pts)

        bolt_color = random.choice([
            QColor(180, 200, 255),
            QColor(200, 220, 255),
            QColor(160, 180, 255),
        ])

        return _LightningBolt(
            points=points,
            alpha=1.0,
            width=random.uniform(1.5, 3.0),
            color=bolt_color,
            branches=branches,
        )

    def _tick(self):
        dt = self._fps_interval / 1000.0
        self._elapsed += dt
        w = self.width()
        h = self.height()

        # Phase logic
        t = self._elapsed

        # Generate lightning during lightning phases
        if (_phase_active(t, 0.3, 0.7) or _phase_active(t, 2.6, 3.0)):
            self._bolt_timer += dt
            if self._bolt_timer > 0.08:
                self._bolt_timer = 0.0
                self._bolts.append(self._generate_lightning())

        # Decay lightning
        for bolt in self._bolts:
            bolt.alpha -= dt * 4.0
        self._bolts = [b for b in self._bolts if b.alpha > 0]

        # Assemble name particles (0.7 - 1.7)
        if _phase_active(t, 0.5, 1.7):
            phase_t = _phase_progress(t, 0.5, 1.5)
            self._update_particles(self._name_particles, phase_t)

        # Fade out name (1.7 - 2.0)
        if _phase_active(t, 1.7, 2.1):
            fade = _phase_progress(t, 1.7, 2.1)
            for p in self._name_particles:
                p.alpha = max(0, 1.0 - fade)

        # Assemble presents (2.0 - 2.6)
        if _phase_active(t, 1.8, 2.6):
            phase_t = _phase_progress(t, 1.8, 2.5)
            self._update_particles(self._presents_particles, phase_t)

        # Fade out presents (2.6 - 3.0)
        if _phase_active(t, 2.6, 3.1):
            fade = _phase_progress(t, 2.6, 3.1)
            for p in self._presents_particles:
                p.alpha = max(0, 1.0 - fade)

        # Assemble title (3.0 - 4.0)
        if _phase_active(t, 2.9, 4.0):
            phase_t = _phase_progress(t, 2.9, 3.8)
            self._update_particles(self._title_particles, phase_t)

        # Subtitle fade in (4.0 - 4.5)
        if t >= 4.0:
            self._subtitle_alpha = min(1.0, _phase_progress(t, 4.0, 4.4))

        # Final fade out (4.5 - 5.0)
        if t >= 4.5:
            self._fade_alpha = min(1.0, _phase_progress(t, 4.5, 5.0))

        # Done
        if t >= _TOTAL_DURATION:
            self._timer.stop()
            self.finished.emit()
            self.close()
            return

        self.update()

    def _update_particles(self, particles: list[_Particle], progress: float):
        """Move particles toward their targets based on animation progress."""
        # Ease-out cubic
        t = 1.0 - (1.0 - min(progress, 1.0)) ** 3

        for p in particles:
            p.x = p.x + (p.tx - p.x) * min(t * 0.3 + 0.02, 1.0)
            p.y = p.y + (p.ty - p.y) * min(t * 0.3 + 0.02, 1.0)
            p.alpha = min(1.0, t * 1.5)

    def paintEvent(self, event):
        if not self._initialized:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        # Dark background with subtle gradient
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor(5, 5, 20))
        grad.setColorAt(0.5, QColor(10, 10, 35))
        grad.setColorAt(1, QColor(5, 5, 15))
        painter.fillRect(self.rect(), grad)

        # Draw lightning bolts
        for bolt in self._bolts:
            self._draw_bolt(painter, bolt)

        # Draw name particles
        self._draw_particles(painter, self._name_particles)

        # Draw presents particles
        self._draw_particles(painter, self._presents_particles)

        # Draw title particles
        self._draw_particles(painter, self._title_particles)

        # Draw subtitle
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

        # Final fade overlay
        if self._fade_alpha > 0:
            overlay = QColor(0, 0, 0)
            overlay.setAlphaF(self._fade_alpha)
            painter.fillRect(self.rect(), overlay)

        painter.end()

    def _draw_bolt(self, painter: QPainter, bolt: _LightningBolt):
        """Draw a lightning bolt with glow effect."""
        if bolt.alpha <= 0 or len(bolt.points) < 2:
            return

        # Glow pass (wider, more transparent)
        for width_mult, alpha_mult in [(4.0, 0.15), (2.0, 0.3), (1.0, 1.0)]:
            color = QColor(bolt.color)
            color.setAlphaF(min(1.0, bolt.alpha * alpha_mult))
            pen = QPen(color, bolt.width * width_mult)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)

            # Main bolt
            for i in range(len(bolt.points) - 1):
                x1, y1 = bolt.points[i]
                x2, y2 = bolt.points[i + 1]
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

            # Branches
            if bolt.branches:
                thinner = QPen(color, bolt.width * width_mult * 0.6)
                thinner.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(thinner)
                for branch in bolt.branches:
                    for i in range(len(branch) - 1):
                        x1, y1 = branch[i]
                        x2, y2 = branch[i + 1]
                        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Flash at bolt origin
        if bolt.alpha > 0.5:
            ox, oy = bolt.points[0]
            flash_r = 30 * bolt.alpha
            flash_grad = QRadialGradient(ox, oy, flash_r)
            flash_color = QColor(220, 230, 255)
            flash_color.setAlphaF(bolt.alpha * 0.3)
            flash_grad.setColorAt(0, flash_color)
            flash_grad.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(flash_grad)
            painter.drawEllipse(QPointF(ox, oy), flash_r, flash_r)

    def _draw_particles(self, painter: QPainter, particles: list[_Particle]):
        """Draw text particles with glow."""
        for p in particles:
            if p.alpha <= 0.01:
                continue

            font = QFont("Georgia", p.font_size)
            font.setBold(True)
            painter.setFont(font)

            # Glow behind character
            if p.alpha > 0.3:
                glow_color = QColor(p.color)
                glow_color.setAlphaF(p.alpha * 0.2)
                painter.setPen(glow_color)
                offset = p.font_size * 0.03
                for dx, dy in [(-offset, 0), (offset, 0), (0, -offset), (0, offset)]:
                    painter.drawText(QPointF(p.x + dx, p.y + dy), p.char)

            # Main character
            color = QColor(p.color)
            color.setAlphaF(min(1.0, p.alpha))
            painter.setPen(color)
            painter.drawText(QPointF(p.x, p.y), p.char)

    def keyPressEvent(self, event):
        """Allow skipping splash with any key."""
        self._timer.stop()
        self.finished.emit()
        self.close()

    def mousePressEvent(self, event):
        """Allow skipping splash with mouse click."""
        self._timer.stop()
        self.finished.emit()
        self.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _phase_active(t: float, start: float, end: float) -> bool:
    return start <= t < end


def _phase_progress(t: float, start: float, end: float) -> float:
    if end <= start:
        return 1.0
    return max(0.0, min(1.0, (t - start) / (end - start)))
