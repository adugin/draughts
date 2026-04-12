"""Engine text protocol — command parsing and response emitting.

Line-based, stdin→commands, stdout→responses.  ASCII/UTF-8, each line
terminated by \\n.  All output is flushed immediately so the GUI / test
harness sees responses without buffering.

Public surface
--------------
parse_command(line)  → (name, rest_tokens)
emit(stream, *parts) → write one response line and flush
format_move(move)    → algebraic notation string
parse_move(token)    → (kind, path)  from algebraic token
"""

from __future__ import annotations

import re
from typing import IO

from draughts.game.board import Board

# ---------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------


def parse_command(line: str) -> tuple[str, list[str]]:
    """Split a raw protocol line into (command_name, tokens).

    Empty lines and lines that start with '#' (comments) return ('', []).
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return "", []
    tokens = line.split()
    return tokens[0].lower(), tokens[1:]


# ---------------------------------------------------------------------------
# Response emitting
# ---------------------------------------------------------------------------


def emit(stream: IO[str], *parts: str) -> None:
    """Write one protocol response line and flush immediately."""
    stream.write(" ".join(parts) + "\n")
    stream.flush()


# ---------------------------------------------------------------------------
# Move notation helpers
# ---------------------------------------------------------------------------

# Pattern: e.g. "c3-d4" or "c3:e5:g3"
_MOVE_RE = re.compile(
    r"^([a-h][1-8])([-:])([a-h][1-8](?::[a-h][1-8])*)$",
    re.IGNORECASE,
)


def format_move(kind: str, path: list[tuple[int, int]]) -> str:
    """Convert an (kind, path) move to algebraic notation.

    Examples::

        format_move("move",    [(2,5),(3,4)]) -> "c3-d4"
        format_move("capture", [(2,5),(4,3),(6,5)]) -> "c3:e5:g3"
    """
    notations = [Board.pos_to_notation(x, y) for x, y in path]
    sep = ":" if kind == "capture" else "-"
    return sep.join(notations)


def parse_move(token: str) -> tuple[str, list[tuple[int, int]]]:
    """Parse an algebraic move token into (kind, path).

    Accepts both '-' and ':' separators; a single ':' anywhere means capture.

    Raises:
        ValueError: if the token cannot be parsed.
    """
    token = token.strip()

    # Determine separator: if any ':' present it's a capture
    if ":" in token:
        sep = ":"
        kind = "capture"
    elif "-" in token:
        sep = "-"
        kind = "move"
    else:
        raise ValueError(f"Cannot parse move token: {token!r}")

    parts = token.split(sep)
    if len(parts) < 2:
        raise ValueError(f"Move token too short: {token!r}")

    path: list[tuple[int, int]] = []
    for part in parts:
        part = part.strip().lower()
        if len(part) != 2:
            raise ValueError(f"Bad square in move token: {part!r}")
        x = ord(part[0]) - ord("a")
        y = Board.ROWS - int(part[1])
        if not (0 <= x < 8 and 0 <= y < 8):
            raise ValueError(f"Square out of range: {part!r}")
        path.append((x, y))

    return kind, path
