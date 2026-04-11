"""Offline board renderer — PNG output without GUI.

Uses Pillow for rendering. No Qt dependency.

Usage:
    from draughts.game.board import Board
    from draughts.ui.renderer import render_board

    board = Board()
    render_board(board, output="board.png")
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from draughts.config import BOARD_SIZE
from draughts.game.board import Board

# Colors
_LIGHT_SQUARE = (240, 217, 181)  # cream
_DARK_SQUARE = (181, 136, 99)  # brown
_BORDER_COLOR = (101, 67, 33)  # dark wood
_BLACK_PIECE = (40, 40, 40)
_WHITE_PIECE = (230, 230, 230)
_BLACK_KING_MARK = (255, 215, 0)  # gold
_WHITE_KING_MARK = (50, 50, 50)  # dark
_HIGHLIGHT_COLOR = (0, 200, 0, 100)  # semi-transparent green
_ARROW_COLOR = (255, 80, 80, 180)  # red arrows
_COORD_COLOR = (200, 180, 160)


def render_board(
    board: Board,
    output: str | None = None,
    size: int = 480,
    highlights: list[tuple[int, int]] | None = None,
    arrows: list[tuple[tuple[int, int], tuple[int, int]]] | None = None,
    coordinates: bool = True,
    flip: bool = False,
) -> Image.Image:
    """Render board to PIL Image.

    Args:
        board: Board to render.
        output: If given, save to this path (PNG/JPG/etc).
        size: Image size in pixels (square).
        highlights: List of (x, y) cells to highlight (green overlay).
        arrows: List of ((x1,y1), (x2,y2)) arrows to draw.
        coordinates: Show a-h / 1-8 labels.
        flip: Flip board (white at top).

    Returns PIL Image.
    """
    margin = size // 12 if coordinates else 0
    total = size + margin
    cell = size // BOARD_SIZE

    img = Image.new("RGB", (total, total), _BORDER_COLOR)
    draw = ImageDraw.Draw(img, "RGBA")

    # Draw coordinates
    if coordinates:
        try:
            font = ImageFont.truetype("arial.ttf", max(cell // 4, 10))
        except OSError:
            font = ImageFont.load_default()

        for i in range(BOARD_SIZE):
            col_letter = chr(ord("a") + (i if not flip else BOARD_SIZE - 1 - i))
            row_number = str(BOARD_SIZE - (i if not flip else BOARD_SIZE - 1 - i))

            # Column labels (bottom)
            cx = margin + i * cell + cell // 2
            draw.text((cx, total - margin // 2), col_letter, fill=_COORD_COLOR, font=font, anchor="mm")

            # Row labels (left)
            cy = margin + i * cell + cell // 2
            draw.text((margin // 2, cy), row_number, fill=_COORD_COLOR, font=font, anchor="mm")

    # Draw squares
    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            vy = BOARD_SIZE - 1 - y if flip else y
            vx = BOARD_SIZE - 1 - x if flip else x

            px = margin + x * cell
            py = margin + y * cell
            is_dark = vx % 2 != vy % 2
            color = _DARK_SQUARE if is_dark else _LIGHT_SQUARE
            draw.rectangle([px, py, px + cell, py + cell], fill=color)

    # Draw highlights
    if highlights:
        for hx, hy in highlights:
            dx, dy = _board_to_pixel(hx, hy, cell, margin, flip)
            draw.rectangle([dx, dy, dx + cell, dy + cell], fill=_HIGHLIGHT_COLOR)

    # Draw pieces
    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            piece = board.piece_at(x, y)
            if piece == Board.EMPTY:
                continue

            dx, dy = _board_to_pixel(x, y, cell, margin, flip)
            _draw_piece(draw, dx, dy, cell, piece)

    # Draw arrows
    if arrows:
        for (x1, y1), (x2, y2) in arrows:
            px1, py1 = _board_to_pixel(x1, y1, cell, margin, flip)
            px2, py2 = _board_to_pixel(x2, y2, cell, margin, flip)
            cx1 = px1 + cell // 2
            cy1 = py1 + cell // 2
            cx2 = px2 + cell // 2
            cy2 = py2 + cell // 2
            draw.line([(cx1, cy1), (cx2, cy2)], fill=_ARROW_COLOR, width=max(cell // 10, 2))
            # Arrowhead (simple circle at endpoint)
            r = cell // 6
            draw.ellipse([cx2 - r, cy2 - r, cx2 + r, cy2 + r], fill=_ARROW_COLOR)

    if output:
        img.save(output)
    return img


def render_position(
    position: str,
    output: str | None = None,
    size: int = 480,
    **kwargs,
) -> Image.Image:
    """Render a 32-char position string to image.

    Convenience wrapper around render_board.
    """
    board = Board(empty=True)
    board.load_from_position_string(position)
    return render_board(board, output=output, size=size, **kwargs)


def _board_to_pixel(
    x: int, y: int, cell: int, margin: int, flip: bool
) -> tuple[int, int]:
    """Convert board (x, y) to pixel (px, py) top-left of cell."""
    if flip:
        return margin + (BOARD_SIZE - 1 - x) * cell, margin + (BOARD_SIZE - 1 - y) * cell
    return margin + x * cell, margin + y * cell


def _draw_piece(draw: ImageDraw.ImageDraw, px: int, py: int, cell: int, piece: int) -> None:
    """Draw a single piece at pixel position."""
    cx = px + cell // 2
    cy = py + cell // 2
    r = int(cell * 0.38)

    is_white = piece < 0
    is_king = abs(piece) == 2

    base_color = _WHITE_PIECE if is_white else _BLACK_PIECE
    outline_color = (160, 160, 160) if is_white else (80, 80, 80)

    # Main circle
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=base_color,
        outline=outline_color,
        width=max(cell // 20, 1),
    )

    # King mark (inner circle + crown symbol)
    if is_king:
        kr = int(r * 0.55)
        mark_color = _WHITE_KING_MARK if is_white else _BLACK_KING_MARK
        draw.ellipse(
            [cx - kr, cy - kr, cx + kr, cy + kr],
            fill=None,
            outline=mark_color,
            width=max(cell // 12, 2),
        )
        # Small crown dot
        dr = max(cell // 16, 2)
        draw.ellipse([cx - dr, cy - dr, cx + dr, cy + dr], fill=mark_color)
