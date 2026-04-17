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

    moves: list[tuple[tuple[tuple[int, int], ...], int]] = field(default_factory=list)
    # moves[i] = (path_as_tuple_of_xy_pairs, weight)
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
        chosen: tuple[tuple[int, int], ...] = _rng.choices(paths, weights=weights, k=1)[0]
        # Reconstruct the kind from the path length / board state:
        # A move is a capture when any intermediate square differs from
        # the straight line between start and end by more than 1 step.
        kind = _infer_kind(board, chosen)
        return AIMove(kind=kind, path=list(chosen))

    def add(self, zhash: int, move: AIMove, weight: int = 1) -> None:
        """Add *move* at *zhash*, or increment its weight if already present."""
        entry = self._entries.setdefault(zhash, BookEntry())
        path_tuple: tuple[tuple[int, int], ...] = tuple(tuple(p) for p in move.path)  # type: ignore[misc]
        for i, (p, w) in enumerate(entry.moves):
            if p == path_tuple:
                entry.moves[i] = (p, w + weight)
                return
        entry.moves.append((path_tuple, weight))

    def probe_all(
        self,
        board: Board,
        color: Color,
    ) -> list[tuple[AIMove, int]]:
        """Return every book move for this position, with its weight.

        Used by the Opening Explorer UI (M9.b) to let the user see which
        moves are in the book, how often each one is chosen during
        self-play/import, and click one to preview. Empty list if the
        position is not in the book. Sorted by descending weight so the
        most-played move is first.
        """
        h = _zobrist_hash(board.grid, color)
        entry = self._entries.get(h)
        if entry is None or not entry.moves:
            return []
        result: list[tuple[AIMove, int]] = []
        for path_tuple, weight in entry.moves:
            kind = _infer_kind(board, path_tuple)
            result.append((AIMove(kind=kind, path=list(path_tuple)), weight))
        result.sort(key=lambda item: item[1], reverse=True)
        return result

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
    def load(cls, path: str | Path) -> OpeningBook:
        """Load book from JSON produced by :py:meth:`save`."""
        text = Path(path).read_text(encoding="utf-8")
        raw: dict[str, list] = json.loads(text)
        entries: dict[int, BookEntry] = {}
        for h_str, moves_json in raw.items():
            h = int(h_str)
            entry = BookEntry()
            for item in moves_json:
                _kind, path_list, w = item
                path_tuple: tuple[tuple[int, int], ...] = tuple((int(xy[0]), int(xy[1])) for xy in path_list)
                entry.moves.append((path_tuple, int(w)))
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


def _infer_kind(board: Board, path: tuple[tuple[int, int], ...]) -> str:
    """Infer 'capture' or 'move' from the path without searching the board."""
    return "capture" if _path_is_capture(path) else "move"


def _path_is_capture(path: tuple[tuple[int, int], ...]) -> bool:
    """A path is a capture if it has ≥ 3 waypoints, or if the distance
    between consecutive waypoints is > 2 squares diagonally."""
    if len(path) >= 3:
        return True
    if len(path) == 2:
        x1, _y1 = path[0]
        x2, _y2 = path[1]
        # Captures land 2+ squares away; normal moves land 1 square away
        return abs(x2 - x1) > 1
    return False
