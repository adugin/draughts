"""Import opening moves from one or more PDN files into the OpeningBook.

Item #39 implementation. Full-feature binary book-format readers for
Kingsrow/Scan are not possible without access to those formats' specs;
instead we use the ubiquitous PDN (Portable Draughts Notation) as the
interchange format — every serious draughts engine or collection can
export PDN, and this importer is format-agnostic across sources.

Usage::

    python -m draughts.tools.import_book_from_pdn games.pdn --out book.json
    python -m draughts.tools.import_book_from_pdn *.pdn --plies 20 --merge existing.json

Each game in the input contributes its first ``--plies`` half-moves to
the book. Repeated (position, move) entries accumulate weight, so a
move that appears in 5 source games gets weight 5.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from draughts.config import Color
from draughts.game.ai.book import OpeningBook
from draughts.game.ai.search import AIMove
from draughts.game.ai.tt import _zobrist_hash
from draughts.game.board import Board
from draughts.game.pdn import PDNGame, load_pdn_file, square_to_xy

logger = logging.getLogger("draughts.import_book")


def _parse_pdn_move(move_str: str) -> tuple[str, list[tuple[int, int]]]:
    """Translate a PDN numeric move string into (kind, path).

    Accepts '22-17', '9x18', '9x18x27', etc.
    """
    if "x" in move_str:
        parts = [int(p) for p in move_str.split("x")]
        path = [square_to_xy(p) for p in parts]
        return "capture", path
    parts_simple = [int(p) for p in move_str.split("-")]
    if len(parts_simple) != 2:
        raise ValueError(f"Unrecognized move: {move_str!r}")
    return "move", [square_to_xy(parts_simple[0]), square_to_xy(parts_simple[1])]


def import_games(
    games: list[PDNGame],
    *,
    plies: int = 16,
    book: OpeningBook | None = None,
) -> OpeningBook:
    """Merge opening plies from each game into ``book`` (or a fresh one).

    Returns the same book object so callers can chain import_games() calls.
    """
    if book is None:
        book = OpeningBook()

    for g in games:
        board = Board()
        color = Color.WHITE
        applied = 0
        for move_str in g.moves:
            if applied >= plies:
                break
            try:
                kind, path = _parse_pdn_move(move_str)
            except ValueError:
                logger.warning("Unparseable move %r in game %r", move_str, g.headers.get("Event"))
                break
            zhash = _zobrist_hash(board.grid, color)
            book.add(zhash, AIMove(kind=kind, path=path), weight=1)
            try:
                if kind == "capture":
                    board.execute_capture_path(path)
                else:
                    (x1, y1), (x2, y2) = path
                    board.execute_move(x1, y1, x2, y2)
            except Exception:
                logger.warning("Could not apply %r to board — stopping game import", move_str)
                break
            color = color.opponent
            applied += 1
    return book


def cli() -> int:
    parser = argparse.ArgumentParser(prog="import_book_from_pdn", description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="PDN files to import")
    parser.add_argument("--out", type=Path, required=True, help="output JSON book")
    parser.add_argument(
        "--plies",
        type=int,
        default=16,
        help="first N plies of each game to import (default 16)",
    )
    parser.add_argument("--merge", type=Path, help="start from an existing book.json and add on top")
    args = parser.parse_args()

    book = OpeningBook.load(args.merge) if args.merge else OpeningBook()
    total_games = 0
    for inp in args.inputs:
        games = load_pdn_file(inp)
        import_games(games, plies=args.plies, book=book)
        total_games += len(games)
        print(f"  {inp}: {len(games)} games", file=sys.stderr)

    book.save(args.out)
    print(
        f"Imported {total_games} games → {len(book)} positions, "
        f"{book.total_moves()} (pos,move) pairs → {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(cli())
