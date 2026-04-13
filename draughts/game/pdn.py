"""PDN (Portable Draughts Notation) parser and writer.

Supports reading/writing game records in standard PDN 3.0 format
used by draughts databases worldwide.

PDN format example:
    [Event "Tournament"]
    [White "Player A"]
    [Black "Player B"]
    [Result "1-0"]
    [GameType "25,W,8,8,A1,0"]
    1. 23-19 9-14 2. 27-23 5-9

Note: PDN uses numeric square numbering (1-32 for 8x8 board).
We convert to/from our (x,y) coordinate system as needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from draughts.game.board import Board


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
    """Convert our notation (e.g. 'c3-d4' or 'f6:d4:b2') to PDN numeric format.

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
    """Convert PDN numeric move (e.g. '22-17' or '11x18x25') to our notation.

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
# Canonical tag order for PDN 3.0
# ---------------------------------------------------------------------------

_CANONICAL_TAGS = ["Event", "Site", "Date", "Round", "White", "Black", "Result", "GameType"]
# SetUp / FEN come after these if present
_SETUP_TAGS = ["SetUp", "FEN"]

RUSSIAN_DRAUGHTS_GAMETYPE = "25,W,8,8,A1,0"
_RESULT_TOKENS = {"1-0", "0-1", "1/2-1/2", "*"}


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def pdngame_to_string(game: PDNGame) -> str:
    """Serialize a single PDNGame to a PDN string.

    Emits:
    - Tag pairs in canonical order (Event, Site, Date, Round, White, Black,
      Result, GameType) followed by SetUp/FEN if present, then extras.
    - GameType defaults to Russian 8x8 if not set.
    - Date in YYYY.MM.DD format; bare year converted; unknown → ????.??.??
    - Movetext with move numbers, line-wrapped at ~80 chars.
    - Result token appended after last move.
    """
    lines: list[str] = []

    # Build ordered header
    headers = dict(game.headers)

    # Ensure GameType is set
    if "GameType" not in headers:
        headers["GameType"] = RUSSIAN_DRAUGHTS_GAMETYPE

    # Normalize date
    if "Date" in headers:
        headers["Date"] = _normalize_date(headers["Date"])

    # Emit canonical tags
    emitted: set[str] = set()
    for tag in _CANONICAL_TAGS:
        if tag in headers:
            lines.append(f'[{tag} "{headers[tag]}"]')
            emitted.add(tag)
        elif tag == "GameType":
            # Always emit GameType
            lines.append(f'[{tag} "{RUSSIAN_DRAUGHTS_GAMETYPE}"]')
            emitted.add(tag)

    # SetUp / FEN (in that order)
    for tag in _SETUP_TAGS:
        if tag in headers:
            lines.append(f'[{tag} "{headers[tag]}"]')
            emitted.add(tag)

    # Any remaining extra tags
    for tag, value in headers.items():
        if tag not in emitted:
            lines.append(f'[{tag} "{value}"]')

    lines.append("")

    # Build movetext
    result_token = game.result
    move_parts: list[str] = []
    for i, move in enumerate(game.moves):
        if i % 2 == 0:
            move_parts.append(f"{i // 2 + 1}.")
        move_parts.append(move)
    move_parts.append(result_token)

    movetext = " ".join(move_parts)
    # Wrap at ~80 chars, but don't break tokens
    wrapped = _wrap_movetext(movetext, width=80)
    lines.extend(wrapped)
    lines.append("")

    return "\n".join(lines)


def _normalize_date(d: str) -> str:
    """Normalize a date string to YYYY.MM.DD format.

    Accepts:
      '1949'          → '1949.??.??'
      '1949.01.15'    → '1949.01.15'
      '?'             → '????.??.??'
      '????.??.??'    → '????.??.??'
    """
    if not d or d in ("?", "??", "???"):
        return "????.??.??"
    # Already in correct format
    if re.match(r"^\d{4}\.\d{2}\.\d{2}$", d):
        return d
    if re.match(r"^\d{4}\.\?+\.\?+$", d):
        return d
    # Bare year
    if re.match(r"^\d{4}$", d):
        return f"{d}.??.??"
    # date with dashes
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", d)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return "????.??.??"


def _wrap_movetext(text: str, width: int = 80) -> list[str]:
    """Wrap movetext at word boundaries to stay within `width` chars per line."""
    tokens = text.split()
    lines: list[str] = []
    current = ""
    for token in tokens:
        if not current:
            current = token
        elif len(current) + 1 + len(token) <= width:
            current += " " + token
        else:
            lines.append(current)
            current = token
    if current:
        lines.append(current)
    return lines


def write_pdn(games: list[PDNGame], path: str | Path | None = None) -> str:
    """Write games to PDN 3.0 format.

    If path is given, writes to file. Always returns PDN string.
    Replaces the old minimal writer with full canonical output.
    """
    parts = [pdngame_to_string(g) for g in games]
    text = "\n".join(parts)
    if path:
        Path(path).write_text(text, encoding="utf-8")
    return text


def write_pdn_file(games: list[PDNGame], path: str | Path) -> None:
    """Write games to a PDN file (convenience wrapper)."""
    write_pdn(games, path)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r'\[(\w+)\s+"([^"]*)"\]')
_MOVE_NUM_RE = re.compile(r"\d+\.\s*")


def parse_pdn(text: str) -> list[PDNGame]:
    """Parse PDN text into list of games.

    Handles multi-game files. Supports standard PDN headers and move text.
    Accepts both numeric (22-17, 11x18) and algebraic (c3-d4, f6:d4) notation.
    Algebraic moves are stored as-is; numeric moves are stored as-is.
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
        # Numeric PDN: NN-NN or NNxNN (possibly multi-jump like NNxNNxNN)
        if re.match(r"^\d+[x\-]\d+", token) or re.match(r"^[a-h][1-8][:\-][a-h][1-8]", token):
            moves.append(token)

    return PDNGame(headers=dict(headers), moves=moves)


def load_pdn_file(path: str | Path) -> list[PDNGame]:
    """Load games from a PDN file."""
    text = Path(path).read_text(encoding="utf-8")
    return parse_pdn(text)


# ---------------------------------------------------------------------------
# Legacy JSON → PDN converter (D2 migration helper)
# ---------------------------------------------------------------------------


def json_to_pdn(json_path: str | Path, pdn_path: str | Path) -> None:
    """Convert a JSON save file to PDN format.

    Loads a JSON game save, reconstructs board positions, infers moves
    between consecutive positions, and writes a PDN file.

    This is the one-time migration function referenced in D2.
    The resulting PDN uses numeric square notation (1-32).
    """
    from draughts.game.board import Board
    from draughts.game.save import load_game

    gs = load_game(json_path)
    positions = gs.positions
    if len(positions) < 2:
        # Write a minimal PDN with no moves
        game = PDNGame(
            headers={
                "Event": "?",
                "Site": "?",
                "Date": _today_date_str(),
                "Round": "?",
                "White": "?",
                "Black": "?",
                "Result": "*",
                "GameType": RUSSIAN_DRAUGHTS_GAMETYPE,
            },
            moves=[],
        )
        write_pdn([game], pdn_path)
        return

    # Reconstruct moves from consecutive board states
    moves: list[str] = []
    for i in range(len(positions) - 1):
        board_before = Board()
        board_before.load_from_position_string(positions[i])
        board_after = Board()
        board_after.load_from_position_string(positions[i + 1])
        move = _infer_pdn_move(board_before, board_after)
        if move:
            moves.append(move)

    # Determine result from final position
    result = _infer_result_from_position(positions[-1])

    game = PDNGame(
        headers={
            "Event": "?",
            "Site": "?",
            "Date": _today_date_str(),
            "Round": "?",
            "White": "?",
            "Black": "?",
            "Result": result,
            "GameType": RUSSIAN_DRAUGHTS_GAMETYPE,
        },
        moves=moves,
    )
    write_pdn([game], pdn_path)


def _today_date_str() -> str:
    """Return today's date in YYYY.MM.DD format."""
    d = date.today()
    return f"{d.year:04d}.{d.month:02d}.{d.day:02d}"


def _infer_pdn_move(before: Board, after: Board) -> str | None:
    """Try to infer the PDN numeric move between two board states.

    Returns a PDN move string like '22-17' or '11x18' or None if inference fails.
    This is best-effort for migration purposes.
    """
    import numpy as np


    # Find squares that changed
    diff = before.grid != after.grid
    changed_yx = list(zip(*np.where(diff), strict=False))

    if not changed_yx:
        return None

    # Find source (piece disappeared) and dest (piece appeared from empty/different)
    sources = []
    dests = []
    for y, x in changed_yx:
        b_piece = int(before.grid[y, x])
        a_piece = int(after.grid[y, x])
        if b_piece != 0 and a_piece == 0:
            sources.append((x, y))
        elif (b_piece == 0 and a_piece != 0) or (b_piece != 0 and a_piece != 0 and abs(b_piece) != abs(a_piece)):
            dests.append((x, y))

    if len(sources) == 1 and len(dests) == 1:
        sx, sy = sources[0]
        tx, ty = dests[0]
        try:
            src_sq = xy_to_square(sx, sy)
            dst_sq = xy_to_square(tx, ty)
        except ValueError:
            return None
        # Detect capture: if more than 2 cells changed, it was a capture
        is_capture = len(changed_yx) > 2
        sep = "x" if is_capture else "-"
        return f"{src_sq}{sep}{dst_sq}"

    return None


def _infer_result_from_position(pos_str: str) -> str:
    """Best-effort result inference from final position string."""
    has_black = "b" in pos_str or "B" in pos_str
    has_white = "w" in pos_str or "W" in pos_str
    if has_black and not has_white:
        return "0-1"
    if has_white and not has_black:
        return "1-0"
    return "*"
