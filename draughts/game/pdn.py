"""PDN (Portable Draughts Notation) parser and writer.

Supports reading/writing game records in standard PDN format
used by draughts databases worldwide.

PDN format example:
    [Event "Tournament"]
    [White "Player A"]
    [Black "Player B"]
    [Result "1-0"]
    1. 23-19 9-14 2. 27-23 5-9

Note: PDN uses square numbering (1-32 for 8x8 board).
We convert to/from our (x,y) coordinate system.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PDNGame:
    """A single game record in PDN format."""

    headers: dict[str, str] = field(default_factory=dict)
    moves: list[str] = field(default_factory=list)

    @property
    def event(self) -> str:
        return self.headers.get("Event", "?")

    @property
    def white(self) -> str:
        return self.headers.get("White", "?")

    @property
    def black(self) -> str:
        return self.headers.get("Black", "?")

    @property
    def result(self) -> str:
        return self.headers.get("Result", "*")


# ---------------------------------------------------------------------------
# Square numbering for 8x8 Russian draughts board
# Standard numbering: 1-32, left-to-right, top-to-bottom on dark squares
# Our coordinates: (x, y) where x=column (0-7), y=row (0-7)
# ---------------------------------------------------------------------------

# Build conversion tables
_SQUARE_TO_XY: dict[int, tuple[int, int]] = {}
_XY_TO_SQUARE: dict[tuple[int, int], int] = {}

_sq = 1
for _y in range(8):
    for _x in range(8):
        if _x % 2 != _y % 2:  # dark square
            _SQUARE_TO_XY[_sq] = (_x, _y)
            _XY_TO_SQUARE[(_x, _y)] = _sq
            _sq += 1


def square_to_xy(sq: int) -> tuple[int, int]:
    """Convert PDN square number (1-32) to (x, y) coordinates."""
    if sq not in _SQUARE_TO_XY:
        raise ValueError(f"Invalid square number: {sq} (must be 1-32)")
    return _SQUARE_TO_XY[sq]


def xy_to_square(x: int, y: int) -> int:
    """Convert (x, y) coordinates to PDN square number (1-32)."""
    key = (x, y)
    if key not in _XY_TO_SQUARE:
        raise ValueError(f"({x}, {y}) is not a dark square")
    return _XY_TO_SQUARE[key]


def notation_to_pdn_move(notation: str) -> str:
    """Convert our notation (e.g. 'c3-d4' or 'f6:d4:b2') to PDN format.

    'c3-d4' → '22-17' (example numbers)
    'f6:d4:b2' → '11x18x25' (example numbers)
    """
    from draughts.game.board import Board

    sep = ":" if ":" in notation else "-"
    pdn_sep = "x" if sep == ":" else "-"

    parts = notation.split(sep)
    pdn_parts = []
    for part in parts:
        x, y = Board.notation_to_pos(part)
        pdn_parts.append(str(xy_to_square(x, y)))
    return pdn_sep.join(pdn_parts)


def pdn_move_to_notation(pdn_move: str) -> str:
    """Convert PDN move (e.g. '22-17' or '11x18x25') to our notation.

    '22-17' → 'c3-d4' (example)
    '11x18x25' → 'f6:d4:b2' (example)
    """
    from draughts.game.board import Board

    is_capture = "x" in pdn_move
    sep = "x" if is_capture else "-"
    our_sep = ":" if is_capture else "-"

    parts = pdn_move.split(sep)
    notation_parts = []
    for part in parts:
        sq = int(part.strip())
        x, y = square_to_xy(sq)
        notation_parts.append(Board.pos_to_notation(x, y))
    return our_sep.join(notation_parts)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r'\[(\w+)\s+"([^"]*)"\]')
_MOVE_NUM_RE = re.compile(r"\d+\.\s*")
_RESULT_TOKENS = {"1-0", "0-1", "1/2-1/2", "*"}


def parse_pdn(text: str) -> list[PDNGame]:
    """Parse PDN text into list of games.

    Handles multi-game files. Supports standard PDN headers and move text.
    """
    games: list[PDNGame] = []
    current_headers: dict[str, str] = {}
    move_text = ""
    in_moves = False

    for raw_line in text.split("\n"):
        line = raw_line.strip()

        if not line or line.startswith("%"):
            # Blank line after moves signals end of game
            if in_moves and move_text.strip():
                game = _build_game(current_headers, move_text)
                games.append(game)
                current_headers = {}
                move_text = ""
                in_moves = False
            continue

        header_match = _HEADER_RE.match(line)
        if header_match:
            if in_moves and move_text.strip():
                # New headers after moves = new game
                game = _build_game(current_headers, move_text)
                games.append(game)
                current_headers = {}
                move_text = ""
                in_moves = False
            current_headers[header_match.group(1)] = header_match.group(2)
            continue

        # Must be move text
        in_moves = True
        move_text += " " + line

    # Last game
    if move_text.strip():
        game = _build_game(current_headers, move_text)
        games.append(game)

    return games


def _build_game(headers: dict[str, str], move_text: str) -> PDNGame:
    """Build a PDNGame from headers and raw move text."""
    # Strip move numbers and result tokens
    text = _MOVE_NUM_RE.sub("", move_text)
    tokens = text.split()

    moves = []
    for token in tokens:
        token = token.strip(".,;")
        if not token or token in _RESULT_TOKENS:
            continue
        if re.match(r"\d+[x\-]\d+", token):
            moves.append(token)

    return PDNGame(headers=dict(headers), moves=moves)


def load_pdn_file(path: str | Path) -> list[PDNGame]:
    """Load games from a PDN file."""
    text = Path(path).read_text(encoding="utf-8")
    return parse_pdn(text)


def write_pdn(games: list[PDNGame], path: str | Path | None = None) -> str:
    """Write games to PDN format.

    If path is given, writes to file. Always returns PDN string.
    """
    lines = []
    for game in games:
        for key, value in game.headers.items():
            lines.append(f'[{key} "{value}"]')
        lines.append("")

        # Format moves with move numbers
        move_parts = []
        for i, move in enumerate(game.moves):
            if i % 2 == 0:
                move_parts.append(f"{i // 2 + 1}.")
            move_parts.append(move)
        move_parts.append(game.result)
        lines.append(" ".join(move_parts))
        lines.append("")

    text = "\n".join(lines)
    if path:
        Path(path).write_text(text, encoding="utf-8")
    return text
