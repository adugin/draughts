"""Learning database for Russian draughts AI.

The original Pascal code stored known-good and known-bad positions
in goodbase.dat / badbase.dat as plain text (one 32-char string per line).
This implementation uses a single JSON file per database instance.
"""

from __future__ import annotations

import json
from pathlib import Path


# Translation table for inverting a position string.
# Swaps black <-> white pieces while preserving empty squares.
_INVERT_TABLE = str.maketrans("bBwW", "wWbB")


def invertstr(position: str) -> str:
    """Invert a position string: swap b<->w, B<->W.

    This mirrors the board perspective so the AI can recognise
    symmetrical positions regardless of which side it is evaluating.
    Matches the original Pascal invertstr() function.
    """
    return position.translate(_INVERT_TABLE)


class LearningDB:
    """Persistent database of known-good and known-bad board positions.

    Stores positions as 32-character strings (dark squares only).
    Backed by a JSON file with two lists: ``good`` and ``bad``.
    """

    def __init__(self, filepath: str | Path):
        """Load an existing database or create a new empty one.

        Args:
            filepath: Path to the JSON file. Created on first ``save()``
                      if it does not exist yet.
        """
        self._filepath = Path(filepath)
        self._good: set[str] = set()
        self._bad: set[str] = set()
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, position: str) -> str | None:
        """Look up a position.

        Returns:
            ``'good'`` if the position is in the good base,
            ``'bad'``  if it is in the bad base,
            ``None``   if it is unknown.

        If a position appears in both bases, ``'good'`` takes precedence
        (matching the original Pascal evaluation order).
        """
        if position in self._good:
            return "good"
        if position in self._bad:
            return "bad"
        return None

    def add_good(self, position: str) -> None:
        """Add *position* to the good base."""
        if len(position) != 32:
            raise ValueError(f"Position must be 32 chars, got {len(position)}")
        self._good.add(position)

    def add_bad(self, position: str) -> None:
        """Add *position* to the bad base."""
        if len(position) != 32:
            raise ValueError(f"Position must be 32 chars, got {len(position)}")
        self._bad.add(position)

    def save(self) -> None:
        """Persist the database to disk."""
        self._filepath.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "good": sorted(self._good),
            "bad": sorted(self._bad),
        }
        self._filepath.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load from disk if the file exists; otherwise start empty."""
        if not self._filepath.exists():
            return
        data = json.loads(self._filepath.read_text(encoding="utf-8"))
        self._good = set(data.get("good", []))
        self._bad = set(data.get("bad", []))
