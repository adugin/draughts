"""Endgame bitbase for Russian draughts (D9).

Keys are Zobrist hashes of (grid, color-to-move), identical to the
transposition-table keying in tt.py.  Values are WLD integers:
    1 = WIN  for the side to move
    0 = DRAW
   -1 = LOSS for the side to move

Serialization format (JSON):
    { "<hash_int>": <result_int>, ... }

Probe is O(1); no search or eval is performed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from draughts.config import Color
from draughts.game.ai.tt import _zobrist_hash
from draughts.game.board import Board

# ---------------------------------------------------------------------------
# Result constants
# ---------------------------------------------------------------------------

WIN = 1
DRAW = 0
LOSS = -1


# ---------------------------------------------------------------------------
# BitbaseEntry — thin wrapper kept for structural parity with book.py
# ---------------------------------------------------------------------------


@dataclass
class BitbaseEntry:
    """WLD result from the side-to-move's perspective."""

    result: int  # WIN=1, DRAW=0, LOSS=-1


# ---------------------------------------------------------------------------
# EndgameBitbase
# ---------------------------------------------------------------------------


class EndgameBitbase:
    """Zobrist-hash-keyed endgame WLD bitbase.

    Usage::

        bb = EndgameBitbase()
        bb.add(zhash, WIN)
        result = bb.probe(board, color)   # None if not in bitbase
        bb.save("bitbase_3.json")
        bb2 = EndgameBitbase.load("bitbase_3.json")
    """

    def __init__(self, entries: dict[int, int] | None = None) -> None:
        # entries maps Zobrist hash → result int (1/0/-1)
        self._entries: dict[int, int] = entries or {}

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def probe(self, board: Board, color: Color) -> int | None:
        """Return 1/0/-1 if the position is in the bitbase, else None.

        O(1) dict lookup.  Never calls eval or search.

        Returns result from *color*'s (side-to-move) perspective:
            1  = color wins with best play
            0  = draw with best play from both sides
           -1  = color loses with best play from both sides
        """
        h = _zobrist_hash(board.grid, color)
        return self._entries.get(h)

    def probe_hash(self, zhash: int) -> int | None:
        """Probe by pre-computed Zobrist hash (used internally by generator)."""
        return self._entries.get(zhash)

    def add(self, zhash: int, result: int) -> None:
        """Store *result* for position identified by *zhash*."""
        self._entries[zhash] = result

    # ------------------------------------------------------------------
    # Persistence (same JSON pattern as book.py)
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Serialize bitbase to JSON.

        Format::

            { "<hash>": <result_int>, ... }
        """
        data = {str(h): r for h, r in self._entries.items()}
        Path(path).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> EndgameBitbase:
        """Load bitbase from JSON (optionally gzip-compressed).

        The 4-piece bitbase is large (~300 MB JSON, ~120 MB gzipped) and
        is typically shipped in .json.gz form. A `.gz` suffix on the path
        triggers streaming gzip decoding.
        """
        p = Path(path)
        if p.suffix == ".gz":
            import gzip

            with gzip.open(p, "rb") as fh:
                raw = json.loads(fh.read().decode("utf-8"))
        else:
            raw = json.loads(p.read_text(encoding="utf-8"))
        entries = {int(h_str): int(r) for h_str, r in raw.items()}
        return cls(entries=entries)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entries)

    def stats(self) -> dict[str, int]:
        """Return counts of wins, draws, and losses."""
        wins = sum(1 for r in self._entries.values() if r == WIN)
        draws = sum(1 for r in self._entries.values() if r == DRAW)
        losses = sum(1 for r in self._entries.values() if r == LOSS)
        return {"total": len(self._entries), "wins": wins, "draws": draws, "losses": losses}
