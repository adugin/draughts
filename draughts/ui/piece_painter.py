"""Shared piece drawing functions — used by both board and captured widgets."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen

from draughts.config import COLORS


def draw_piece(painter: QPainter, cx: float, cy: float,
               radius: float, is_black: bool, is_king: bool = False):
    """Draw a single checker piece at the given center coordinates.

    This is the shared rendering function used everywhere — board cells
    and captured-pieces panel. Matches the original Pascal draughtsman().

    Args:
        painter: Active QPainter with antialiasing enabled.
        cx, cy: Center coordinates of the piece.
        radius: Outer radius (original: cell_size * 0.40 ≈ 17px at 40px cells).
        is_black: True for black piece, False for white.
        is_king: True to draw crown on top.
    """
    if is_black:
        main_color = QColor(*COLORS['black_piece'])
        ring_color = QColor(*COLORS['black_piece_ring'])
    else:
        main_color = QColor(*COLORS['white_piece'])
        ring_color = QColor(*COLORS['white_piece_ring'])

    # Outer ring
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ring_color)
    painter.drawEllipse(QPointF(cx, cy), radius, radius)

    # Inner fill
    inner_r = radius * 0.80
    painter.setBrush(main_color)
    painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

    # Concentric ring
    ring2_r = radius * 0.60
    painter.setPen(QPen(ring_color, max(1, radius * 0.06)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(cx, cy), ring2_r, ring2_r)

    # Crown for kings
    if is_king:
        _draw_crown(painter, cx, cy, radius * 0.45)


def _draw_crown(painter: QPainter, cx: float, cy: float, size: float):
    """Draw crown symbol on a king piece."""
    crown_color = QColor(*COLORS['crown_fill'])
    gem_color = QColor(*COLORS['crown_gems'])

    half = size * 0.7
    top = cy - size * 0.5
    bottom = cy + size * 0.4
    mid = (top + bottom) / 2

    path = QPainterPath()
    path.moveTo(cx - half, bottom)
    path.lineTo(cx - half, mid)
    path.lineTo(cx - half * 0.5, top + size * 0.15)
    path.lineTo(cx, mid)
    path.lineTo(cx + half * 0.5, top + size * 0.15)
    path.lineTo(cx + half, mid)
    path.lineTo(cx + half, bottom)
    path.closeSubpath()

    painter.setPen(QPen(gem_color, max(1, size * 0.1)))
    painter.setBrush(crown_color)
    painter.drawPath(path)

    # Three gems
    gem_r = size * 0.12
    for gx in [cx - half * 0.5, cx, cx + half * 0.5]:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gem_color)
        painter.drawEllipse(QPointF(gx, top + size * 0.15), gem_r, gem_r)
