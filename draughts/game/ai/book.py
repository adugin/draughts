"""Opening book for the Russian draughts AI.

Keys are Zobrist hashes (board + color-to-move), identical to the
transposition-table keying in tt.py.  Values are weighted move lists;
``probe`` picks a move with probability proportional to weight.

Serialization format (JSON):
    { "<hash_int>": [["kind", [[x1,y1],[x2,y2],...], weight], ...], ... }
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from draughts.config import Color
from draughts.game.ai.search import AIMove
from draughts.game.ai.tt import _zobrist_hash
from draughts.game.board import Board


# ---------------------------------------------------------------------------
# BookEntry  ─ per-position data
# ---------------------------------------------------------------------------


@dataclass
class BookEntry:
    """All known moves for a single hashed position.

    Each entry is ``(move_path_tuple, weight)`` where *move_path_tuple* is a
    tuple of (x, y) pairs (same shape as ``AIMove.path``, stored as a tuple
    for hashability / JSON compactness).
    """

    moves: list[tuple[tuple[int, int, ...], int]] = field(default_factory=list)
    # moves[i] = (path_as_flat_tuple, weight)
    # We store path as a list of [x,y] in JSON; converted to tuple on load.


# ---------------------------------------------------------------------------
# OpeningBook
# ---------------------------------------------------------------------------


class OpeningBook:
    """Zobrist-hash-keyed opening book.

    Usage::

        book = OpeningBook()
        book.add(zhash, ai_move, weight=1)
        move = book.probe(board, color)   # None if not in book
        book.save("opening_book.json")
        book2 = OpeningBook.load("opening_book.json")
    """

    def __init__(self, entries: dict[int, BookEntry] | None = None) -> None:
        self._entries: dict[int, BookEntry] = entries or {}

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def probe(
        self,
        board: Board,
        color: Color,
        rng: random.Random | None = None,
    ) -> AIMove | None:
        """Return a book move for this position, or *None* if not in book.

        Picks among alternatives with probability proportional to weight.
        O(1) dict lookup; never calls eval or search.
        """
        h = _zobrist_hash(board.grid, color)
        entry = self._entries.get(h)
        if entry is None or not entry.moves:
            return None

        paths = [item[0] for item in entry.moves]
        weights = [item[1] for item in entry.moves]

        _rng = rng or random
        chosen = _rng.choices(paths, weights=weights, k=1)[0]
        # Reconstruct the kind from the path length / board state:
        # A move is a capture when any intermediate square differs from
        # the straight line between start and end by more than 1 step.
        kind = _infer_kind(board, chosen)
        return AIMove(kind=kind, path=list(chosen))

    def add(self, zhash: int, move: AIMove, weight: int = 1) -> None:
        """Add *move* at *zhash*, or increment its weight if already present."""
        entry = self._entries.setdefault(zhash, BookEntry())
        path_tuple = tuple(move.path)  # type: ignore[arg-type]
        for i, (p, w) in enumerate(entry.moves):
            if p == path_tuple:
                entry.moves[i] = (p, w + weight)
                return
        entry.moves.append((path_tuple, weight))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Serialize book to JSON.

        Format::

            {
              "<hash>": [["kind", [[x,y],[x,y],...], weight], ...],
              ...
            }

        We derive *kind* from move data at save time so that the JSON is
        self-describing without needing a Board reference.
        """
        data: dict[str, list] = {}
        for h, entry in self._entries.items():
            moves_json = []
            for path_tuple, w in entry.moves:
                path_list = [list(xy) for xy in path_tuple]
                # Detect kind: a capture path has ≥ 3 points OR start/end
                # are more than 1 step apart.
                is_cap = _path_is_capture(path_tuple)
                kind_str = "capture" if is_cap else "move"
                moves_json.append([kind_str, path_list, w])
            data[str(h)] = moves_json

        Path(path).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "OpeningBook":
        """Load book from JSON produced by :py:meth:`save`."""
        text = Path(path).read_text(encoding="utf-8")
        raw: dict[str, list] = json.loads(text)
        entries: dict[int, BookEntry] = {}
        for h_str, moves_json in raw.items():
            h = int(h_str)
            entry = BookEntry()
            for item in moves_json:
                _kind, path_list, w = item
                path_tuple = tuple(tuple(xy) for xy in path_list)
                entry.moves.append((path_tuple, int(w)))  # type: ignore[arg-type]
            entries[h] = entry
        return cls(entries=entries)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entries)

    def total_moves(self) -> int:
        """Total number of (position, move) pairs in the book."""
        return sum(len(e.moves) for e in self._entries.values())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _infer_kind(board: Board, path: tuple) -> str:  # type: ignore[type-arg]
    """Infer 'capture' or 'move' from the path without searching the board."""
    return "capture" if _path_is_capture(path) else "move"


def _path_is_capture(path: tuple) -> bool:  # type: ignore[type-arg]
    """A path is a capture if it has ≥ 3 waypoints, or if the distance
    between consecutive waypoints is > 2 squares diagonally."""
    if len(path) >= 3:
        return True
    if len(path) == 2:
        x1, y1 = path[0]
        x2, y2 = path[1]
        # Captures land 2+ squares away; normal moves land 1 square away
        return abs(x2 - x1) > 1
    return False
