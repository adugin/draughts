"""Canonical user-data directory layout.

All user-generated / user-downloaded content lives under a single tree
rooted at ``get_data_dir()``, with four well-known subdirectories:

    <data_dir>/
        autosave.json
        settings.json
        bitbase/
            bitbase_4.json.gz        — downloaded 4-piece base (D37)
            bitbase_4.json.gz.sha256
        books/
            book_user.json           — imported via «Инструменты»
        puzzles/
            mined_puzzles.json       — auto-mined via «Инструменты»
        generated/                   — deprecated location (pre-audit);
                                       migrated on first run by
                                       migrate_legacy_paths().

Rationale: before the M6 QA audit user content was scattered across
three locations (`~/.draughts/mined_puzzles.json`,
`<data_dir>/generated/…`, `<data_dir>/bitbase/…`). Only the last was
actually picked up by the engine loaders; the first two silently
accumulated and were ignored. The audit (BLK-01, BLK-02, PO-4)
flagged this as a ship-stopper. This module is the single place any
new "where does this file live" question is answered.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from draughts.config import get_data_dir

logger = logging.getLogger("draughts.user_data")


_BITBASE_SUBDIR = "bitbase"
_BOOKS_SUBDIR = "books"
_PUZZLES_SUBDIR = "puzzles"

#: Stable file-name conventions — engine loaders look for these.
BITBASE_FILENAME = "bitbase_4.json.gz"
USER_BOOK_FILENAME = "book_user.json"
MINED_PUZZLES_FILENAME = "mined_puzzles.json"


def bitbase_dir() -> Path:
    """Directory for downloaded bitbase files. Created on demand."""
    d = Path(get_data_dir()) / _BITBASE_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def books_dir() -> Path:
    """Directory for user opening books (imported / generated)."""
    d = Path(get_data_dir()) / _BOOKS_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def puzzles_dir() -> Path:
    """Directory for user-mined puzzles."""
    d = Path(get_data_dir()) / _PUZZLES_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_book_path() -> Path:
    return books_dir() / USER_BOOK_FILENAME


def mined_puzzles_path() -> Path:
    return puzzles_dir() / MINED_PUZZLES_FILENAME


def migrate_legacy_paths() -> list[tuple[Path, Path]]:
    """Move data from pre-audit locations into the canonical layout.

    Called once at startup (main.py). Idempotent — nothing happens on
    subsequent runs because source files no longer exist. Returns the
    list of (src, dst) pairs that were actually moved, for optional
    one-time notification.

    Legacy locations handled:
      - ~/.draughts/mined_puzzles.json  → <data_dir>/puzzles/mined_puzzles.json
      - <data_dir>/generated/book_user.json → <data_dir>/books/book_user.json
      - <data_dir>/generated/mined_puzzles.json → <data_dir>/puzzles/mined_puzzles.json
    """
    moved: list[tuple[Path, Path]] = []

    # 1. ~/.draughts/mined_puzzles.json — pre-audit puzzle_miner default.
    legacy_home = Path.home() / ".draughts" / "mined_puzzles.json"
    dst = mined_puzzles_path()
    if legacy_home.exists() and not dst.exists():
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy_home), str(dst))
            moved.append((legacy_home, dst))
        except OSError as exc:
            logger.warning("Could not migrate %s → %s: %s", legacy_home, dst, exc)

    # 2. <data_dir>/generated/* — pre-audit D36 generator sinks.
    legacy_gen = Path(get_data_dir()) / "generated"
    if legacy_gen.is_dir():
        migrations = [
            (legacy_gen / "book_user.json", user_book_path()),
            (legacy_gen / "mined_puzzles.json", mined_puzzles_path()),
        ]
        for src, d in migrations:
            if src.exists() and not d.exists():
                try:
                    d.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(d))
                    moved.append((src, d))
                except OSError as exc:
                    logger.warning("Could not migrate %s → %s: %s", src, d, exc)
        # Clean up empty legacy folder silently.
        try:
            if legacy_gen.is_dir() and not any(legacy_gen.iterdir()):
                legacy_gen.rmdir()
        except OSError:
            pass

    for src, dst in moved:
        logger.info("Migrated user data: %s → %s", src, dst)
    return moved
