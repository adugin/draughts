"""Procedural texture generation for the draughts board UI.

Generates wood grain, felt, and piece textures using NumPy + QImage.
All textures are cached and scale-aware.
"""

from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)


def generate_wood_tile(
    size: int, base_color: tuple[int, int, int], grain_color: tuple[int, int, int], seed: int = 0
) -> QPixmap:
    """Generate a square wood-grain texture tile.

    Uses Perlin-like noise to create realistic wood grain patterns.
    """
    rng = np.random.RandomState(seed)
    arr = np.zeros((size, size, 3), dtype=np.uint8)

    br, bg, bb = base_color
    gr, gg, gb = grain_color

    # Create horizontal wood grain pattern (no rings — avoids circle-like artifacts)
    for y in range(size):
        for x in range(size):
            # Primary grain: horizontal lines with gentle wave
            wave = math.sin(x * 0.08 + seed * 0.1) * 4
            grain = math.sin((y + wave) * 0.6) * 0.5 + 0.5

            # Secondary finer grain
            fine = math.sin((y + math.sin(x * 0.15) * 2) * 2.0) * 0.5 + 0.5

            # Subtle noise
            noise = rng.random() * 0.1

            t = grain * 0.55 + fine * 0.35 + noise * 0.1
            t = max(0, min(1, t))

            arr[y, x, 0] = int(br + (gr - br) * t)
            arr[y, x, 1] = int(bg + (gg - bg) * t)
            arr[y, x, 2] = int(bb + (gb - bb) * t)

    # Convert to QPixmap
    h, w, _ch = arr.shape
    img = QImage(arr.data, w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(img.copy())


def generate_felt_texture(
    width: int, height: int, base_color: tuple[int, int, int] = (0, 80, 20), seed: int = 42
) -> QPixmap:
    """Generate a green felt/velvet texture for the captured pieces panel."""
    rng = np.random.RandomState(seed)
    arr = np.zeros((height, width, 3), dtype=np.uint8)

    br, bg, bb = base_color

    for y in range(height):
        for x in range(width):
            # Subtle noise for fabric texture
            noise = rng.random() * 0.12 - 0.06
            # Slight vertical bias (like fabric nap)
            nap = math.sin(y * 0.8 + math.sin(x * 0.3) * 2) * 0.03

            factor = 1.0 + noise + nap
            arr[y, x, 0] = max(0, min(255, int(br * factor)))
            arr[y, x, 1] = max(0, min(255, int(bg * factor)))
            arr[y, x, 2] = max(0, min(255, int(bb * factor)))

    img = QImage(arr.data, width, height, width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(img.copy())


def draw_realistic_piece(painter: QPainter, cx: float, cy: float, radius: float, is_black: bool, is_king: bool = False):
    """Draw a photorealistic checker piece with 3D lighting and shadow.

    Features: drop shadow, radial gradient for dome shape, specular highlight,
    edge rim, concentric rings, and crown for kings.
    """
    # --- Drop shadow ---
    shadow_offset = radius * 0.08
    shadow_color = QColor(0, 0, 0, 60)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(shadow_color)
    painter.drawEllipse(QPointF(cx + shadow_offset, cy + shadow_offset), radius * 1.02, radius * 1.02)

    # --- Main body with radial gradient (3D dome effect) ---
    if is_black:
        center_color = QColor(60, 50, 45)  # warm dark brown center
        edge_color = QColor(15, 12, 10)  # almost black edge
        rim_color = QColor(90, 80, 70)  # subtle rim light
        ring_color = QColor(70, 60, 55)
    else:
        center_color = QColor(255, 245, 230)  # warm ivory center
        edge_color = QColor(200, 185, 165)  # darker ivory edge
        rim_color = QColor(255, 250, 240)  # bright rim
        ring_color = QColor(210, 195, 175)

    # Radial gradient — light from upper-left
    highlight_x = cx - radius * 0.25
    highlight_y = cy - radius * 0.25

    body_grad = QRadialGradient(highlight_x, highlight_y, radius * 1.3)
    body_grad.setColorAt(0.0, center_color)
    body_grad.setColorAt(0.7, edge_color)
    body_grad.setColorAt(1.0, edge_color.darker(120))

    painter.setBrush(body_grad)
    painter.drawEllipse(QPointF(cx, cy), radius, radius)

    # --- Edge rim (subtle light catch) ---
    rim_grad = QConicalGradient(cx, cy, 135)
    rim_light = QColor(rim_color)
    rim_light.setAlpha(80)
    rim_dark = QColor(0, 0, 0, 0)
    rim_grad.setColorAt(0.0, rim_light)
    rim_grad.setColorAt(0.25, rim_dark)
    rim_grad.setColorAt(0.5, rim_dark)
    rim_grad.setColorAt(0.75, rim_light)
    rim_grad.setColorAt(1.0, rim_light)

    pen = QPen(QBrush(rim_grad), max(1, radius * 0.06))
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(cx, cy), radius * 0.95, radius * 0.95)

    # --- Concentric decorative rings ---
    painter.setPen(QPen(ring_color, max(1, radius * 0.04)))
    painter.drawEllipse(QPointF(cx, cy), radius * 0.70, radius * 0.70)
    painter.drawEllipse(QPointF(cx, cy), radius * 0.50, radius * 0.50)

    # --- Specular highlight (glossy spot) ---
    spec_x = cx - radius * 0.2
    spec_y = cy - radius * 0.2
    spec_r = radius * 0.25

    spec_grad = QRadialGradient(spec_x, spec_y, spec_r)
    if is_black:
        spec_grad.setColorAt(0.0, QColor(255, 255, 255, 70))
    else:
        spec_grad.setColorAt(0.0, QColor(255, 255, 255, 120))
    spec_grad.setColorAt(1.0, QColor(255, 255, 255, 0))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(spec_grad)
    painter.drawEllipse(QPointF(spec_x, spec_y), spec_r, spec_r)

    # --- Crown for kings ---
    if is_king:
        _draw_elegant_crown(painter, cx, cy, radius * 0.40, is_black)


def _draw_elegant_crown(painter: QPainter, cx: float, cy: float, size: float, is_black: bool):
    """Draw an elegant crown symbol on a king piece."""
    if is_black:
        crown_color = QColor(218, 165, 32)  # gold
        outline_color = QColor(150, 110, 20)
    else:
        crown_color = QColor(218, 165, 32)  # gold
        outline_color = QColor(180, 140, 40)

    half = size * 0.7
    top = cy - size * 0.5
    bottom = cy + size * 0.35
    mid = (top + bottom) / 2

    path = QPainterPath()
    path.moveTo(cx - half, bottom)
    path.lineTo(cx - half, mid)
    path.lineTo(cx - half * 0.5, top + size * 0.1)
    path.lineTo(cx, mid + size * 0.05)
    path.lineTo(cx + half * 0.5, top + size * 0.1)
    path.lineTo(cx + half, mid)
    path.lineTo(cx + half, bottom)
    path.closeSubpath()

    painter.setPen(QPen(outline_color, max(1, size * 0.08)))
    painter.setBrush(crown_color)
    painter.drawPath(path)

    # Gems
    gem_r = size * 0.1
    gem_color = QColor(220, 20, 60)  # ruby red
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gem_color)
    for gx in [cx - half * 0.5, cx, cx + half * 0.5]:
        painter.drawEllipse(QPointF(gx, top + size * 0.15), gem_r, gem_r)


class TextureCache:
    """Caches generated textures at specific sizes to avoid regeneration."""

    def __init__(self):
        self._light_wood: dict[int, QPixmap] = {}
        self._dark_wood: dict[int, QPixmap] = {}
        self._felt: QPixmap | None = None
        self._felt_size: tuple[int, int] = (0, 0)
        self._frame_wood: dict[int, QPixmap] = {}

    def get_light_wood(self, cell_size: int) -> QPixmap:
        if cell_size not in self._light_wood:
            self._light_wood[cell_size] = generate_wood_tile(
                cell_size,
                base_color=(230, 200, 150),  # light maple
                grain_color=(210, 175, 120),  # maple grain
                seed=101,
            )
        return self._light_wood[cell_size]

    def get_dark_wood(self, cell_size: int) -> QPixmap:
        if cell_size not in self._dark_wood:
            self._dark_wood[cell_size] = generate_wood_tile(
                cell_size,
                base_color=(120, 70, 35),  # dark walnut
                grain_color=(90, 50, 25),  # walnut grain
                seed=202,
            )
        return self._dark_wood[cell_size]

    def get_felt(self, width: int, height: int) -> QPixmap:
        if self._felt is None or self._felt_size != (width, height):
            self._felt = generate_felt_texture(width, height)
            self._felt_size = (width, height)
        return self._felt

    def get_frame_wood(self, size: int) -> QPixmap:
        if size not in self._frame_wood:
            self._frame_wood[size] = generate_wood_tile(
                size,
                base_color=(80, 45, 20),  # dark mahogany frame
                grain_color=(60, 30, 15),
                seed=303,
            )
        return self._frame_wood[size]

    def clear(self):
        self._light_wood.clear()
        self._dark_wood.clear()
        self._felt = None
        self._frame_wood.clear()
