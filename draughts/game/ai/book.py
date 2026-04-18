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
        # Re-classify capture/move against the live board: the stored
        # kind in older books is unreliable because the pre-audit
        # geometric classifier marked any 2+-square king slide as a
        # capture. A wrong "capture" label would defeat the mandatory-
        # capture guard in search.find_move and silently play a quiet
        # king fly when a capture is required.
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
            # Re-classify against the live board for the same reason as
            # probe(): stored kind is advisory only.
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

        The stored *kind* is advisory: probe() always re-classifies with
        board context. We only label a path as "capture" when its shape
        is unambiguous (>= 3 waypoints = multi-jump).
        """
        data: dict[str, list] = {}
        for h, entry in self._entries.items():
            moves_json = []
            for path_tuple, w in entry.moves:
                path_list = [list(xy) for xy in path_tuple]
                kind_str = "capture" if _path_is_capture_geometric(path_tuple) else "move"
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
    """Infer 'capture' or 'move' for *path* evaluated against *board*.

    Board context is required because a two-point path with distance > 1
    is ambiguous on its own: a pawn can only move that far by capturing,
    but a king can slide freely along an empty diagonal. The previous
    geometry-only classifier labelled every 2+-square king slide as
    "capture", which falsely satisfied the mandatory-capture guard in
    AIEngine.find_move and let the engine play a quiet king fly when a
    real capture was required.
    """
    return "capture" if _path_is_capture_on_board(board, path) else "move"


def _path_is_capture_on_board(board: Board, path: tuple[tuple[int, int], ...]) -> bool:
    """Board-aware capture classifier for a stored book path.

    Rules:
      - A path with ≥ 3 waypoints is always a multi-jump capture (a
        plain move has exactly two endpoints).
      - A 2-point path with distance == 1 is always a quiet move.
      - A 2-point path with distance > 1 is a capture iff the source
        square on *board* is a pawn, OR the source is a king and at
        least one intermediate square is occupied (a quiet king fly
        requires all intermediate squares to be empty).
    """
    if len(path) >= 3:
        return True
    if len(path) != 2:
        return False
    (x1, y1), (x2, y2) = path[0], path[1]
    dist = abs(x2 - x1)
    if dist <= 1:
        return False
    source_piece = board.piece_at(x1, y1)
    # Unknown source (empty square, corrupt book entry): fall back to
    # the permissive geometric answer to preserve prior behaviour.
    if source_piece == 0:
        return True
    if not Board.is_king(source_piece):
        # Pawns only reach a 2-square target via a single capture.
        return True
    # King: quiet fly iff every intermediate square is empty.
    dx = 1 if x2 > x1 else -1
    dy = 1 if y2 > y1 else -1
    cx, cy = x1 + dx, y1 + dy
    while (cx, cy) != (x2, y2):
        if board.piece_at(cx, cy) != 0:
            return True
        cx += dx
        cy += dy
    return False


def _path_is_capture_geometric(path: tuple[tuple[int, int], ...]) -> bool:
    """Board-free heuristic used only by :py:meth:`OpeningBook.save`.

    Conservative: only a path with ≥ 3 waypoints is confidently a
    capture (multi-jump). Two-point paths are written as "move" — the
    stored kind is advisory because probe() always re-classifies with
    board context, so under-labelling is harmless while over-labelling
    would bake the quiet-king-fly bug back into the shipped book.
    """
    return len(path) >= 3
