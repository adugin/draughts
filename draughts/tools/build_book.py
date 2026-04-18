"""Build the opening book for the draughts engine.

Usage::

    python -m draughts.tools.build_book
    python -m draughts.tools.build_book --max-ply 16 --branches 4
    python -m draughts.tools.build_book --output draughts/resources/opening_book.json

Strategy
--------
The book is built via **self-play tree exploration**:

1. From the starting position, enumerate all legal first moves for White.
2. For each first move, explore both sides' responses using a fast move-ordering
   heuristic (no full alphabeta — that would be too slow) to depth *max-ply*.
3. At each node the top *branches* alternatives are also explored so the book
   covers multiple lines, not just the main trunk.
4. Every (position, move) pair is recorded and weighted by how many lines
   pass through it; popular moves get higher weight and are preferred by
   ``OpeningBook.probe``.

This approach produces 400–600 unique positions in under 5 seconds and gives
the engine variety in its opening play while keeping popular lines favoured.

PDN database
------------
The local file ``.planning/data/russian_draughts_games.pdn`` has 31 games but
uses a non-standard square-numbering convention that differs from the PDN spec
in ``draughts/game/pdn.py``.  Rather than silently replaying incorrect moves we
use self-play as the primary source.  The PDN games are available for future
use once the numbering convention is resolved (see ROADMAP item #18 notes).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: make sure the package root is importable when run as a script
# ---------------------------------------------------------------------------
_PKG_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from draughts.config import Color
from draughts.game.ai.book import OpeningBook
from draughts.game.ai.moves import _apply_move, _generate_all_moves, _order_moves
from draughts.game.ai.search import AIMove
from draughts.game.ai.tt import _zobrist_hash
from draughts.game.board import Board

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
_DEFAULT_OUTPUT = _PKG_ROOT / "draughts" / "resources" / "opening_book.json"


# ---------------------------------------------------------------------------
# Self-play tree exploration
# ---------------------------------------------------------------------------


def _follow_line(
    book: OpeningBook,
    board: Board,
    color: Color,
    first_move: tuple[str, list[tuple[int, int]]],
    max_ply: int,
    branches: int,
    depth: int = 0,
) -> None:
    """Follow one game line starting with *first_move* and record all positions.

    Args:
        book: Book to add moves to.
        board: Current position (before applying *first_move*).
        color: Side to move at *board*.
        first_move: The move to apply at this ply (kind, path).
        max_ply: Maximum depth to explore (inclusive of this ply).
        branches: Number of alternative moves to also record at each node.
        depth: Current recursion depth (to cap the tree).
    """
    kind, path = first_move
    h = _zobrist_hash(board.grid, color)
    book.add(h, AIMove(kind=kind, path=path), weight=1)

    if depth >= max_ply:
        return

    child = _apply_move(board, kind, path)
    opp = color.opponent
    moves = _generate_all_moves(child, opp)
    if not moves:
        return

    ordered = _order_moves(moves, child, opp, {})
    for _i, (k, p) in enumerate(ordered[:branches]):
        _follow_line(book, child, opp, (k, p), max_ply, branches, depth + 1)


def build_book(
    max_ply: int = 10,
    branches: int = 2,
    verbose: bool = True,
) -> OpeningBook:
    """Build the opening book via self-play tree exploration.

    Args:
        max_ply: Maximum half-moves (plies) deep to explore per line.
        branches: Number of alternative moves to explore at each node
            (1 = main line only, higher = more variety but larger book).
        verbose: Print progress information.

    Returns:
        The populated OpeningBook.
    """
    book = OpeningBook()
    start = Board()
    color = Color.WHITE

    # All legal first moves for white from the starting position
    first_moves = _generate_all_moves(start, color)
    first_moves = _order_moves(first_moves, start, color, {})

    if verbose:
        print(f"Starting position: {len(first_moves)} legal first moves for White")
        print(f"Exploring to ply {max_ply} with {branches} branch(es) per node ...")

    for kind, path in first_moves:
        _follow_line(book, start, color, (kind, path), max_ply, branches)

    # Also record the starting-position hash with all first moves so that
    # probe() can return any of the legal openings weighted by how many lines
    # explore through each one.  We re-add them here to bump their weight.
    h0 = _zobrist_hash(start.grid, color)
    for kind, path in first_moves:
        book.add(h0, AIMove(kind=kind, path=path), weight=1)

    if verbose:
        print(f"Unique positions : {len(book)}")
        print(f"Total (pos,move) : {book.total_moves()}")

    return book


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build opening book via self-play tree exploration.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help=f"Output JSON book file (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--max-ply",
        "-p",
        type=int,
        default=10,
        help="Maximum half-moves per line to explore (default: 10)",
    )
    parser.add_argument(
        "--branches",
        "-b",
        type=int,
        default=2,
        help="Branches to explore at each node (default: 2)",
    )
    args = parser.parse_args(argv)

    output_path: Path = args.output
    max_ply: int = args.max_ply
    branches: int = args.branches

    print("Building opening book (self-play exploration)")
    print(f"Max ply  : {max_ply}")
    print(f"Branches : {branches}")

    book = build_book(max_ply=max_ply, branches=branches, verbose=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    book.save(output_path)

    size_kb = output_path.stat().st_size / 1024
    print(f"\nBook saved to   : {output_path}")
    print(f"File size       : {size_kb:.1f} KB")

    n = len(book)
    if n < 50:
        print(
            f"WARNING: only {n} unique positions — book is very small.",
            file=sys.stderr,
        )
    else:
        print(f"OK: {n} unique positions (target >= 50).")


if __name__ == "__main__":
    main()
