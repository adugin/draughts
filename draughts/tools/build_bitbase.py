"""Build the endgame bitbase (1-3 pieces) for the draughts engine.

Usage::

    python -m draughts.tools.build_bitbase
    python -m draughts.tools.build_bitbase --output draughts/resources/bitbase_3.json
    python -m draughts.tools.build_bitbase --max-iters 100  # cap retrograde passes

Strategy
--------
3-piece retrograde analysis:

1. **Enumerate** all legal placements of 3 pieces on the 32 dark squares
   where one side has 2 pieces and the other has 1.  Each piece can be a
   pawn or king, but pawns cannot be on their own promotion row (they would
   have already promoted).  Both sides-to-move are considered.

2. **Terminal labelling**:
   - No legal moves → LOSS for the side to move (-1)
   - Lone-king vs lone-king positions → DRAW (0) (only truly forced draw)
   - Otherwise: mark as "unknown" for retrograde propagation

3. **Optimised retrograde iteration**:
   All moves for all positions are pre-computed once.  Each pass then
   works entirely with hash lookups — no board copies are needed per pass.
   Converges in under 2 minutes on a modern laptop.
   Fixed-point: any position still unknown → DRAW (neither side can force a result).

4. Save to ``draughts/resources/bitbase_3.json``.

5. Print stats: total positions, wins, draws, losses, file size, time.
"""

from __future__ import annotations

import argparse
import itertools
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: make sure the package root is importable when run as a script
# ---------------------------------------------------------------------------
_PKG_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

import numpy as np

from draughts.config import (
    BLACK,
    BLACK_KING,
    BOARD_SIZE,
    WHITE,
    WHITE_KING,
    Color,
)
from draughts.game.ai.bitbase import DRAW, LOSS, WIN, EndgameBitbase
from draughts.game.ai.moves import _apply_move, _generate_all_moves
from draughts.game.ai.tt import _zobrist_hash
from draughts.game.board import Board

# ---------------------------------------------------------------------------
# Dark-square enumeration (32 playable squares)
# ---------------------------------------------------------------------------

# All (x, y) dark squares on the 8x8 board, sorted for determinism
DARK_SQUARES: list[tuple[int, int]] = sorted(
    (x, y) for y in range(BOARD_SIZE) for x in range(BOARD_SIZE) if x % 2 != y % 2
)

_BLACK_PROMOTE_ROW = BOARD_SIZE - 1  # y=7 — black promotes here
_WHITE_PROMOTE_ROW = 0  # y=0 — white promotes here


def _is_lone_king_vs_lone_king(grid: np.ndarray) -> bool:
    """Return True only for the *exact* 1K vs 1K position.

    This is the sole case that is unconditionally drawn by the rules of
    Russian draughts (two lone kings cannot force a capture).

    IMPORTANT: Do NOT use the broader ``_is_drawn_endgame`` from eval.py here.
    That function returns True for *any* kings-only position (N kings vs M kings,
    no pawns), which is correct as a search heuristic (telling the searcher
    "don't bother going deeper, this will be a draw") but *wrong* for the
    bitbase generator.  In reality, 2K vs 1K is usually a WIN for the stronger
    side — it must be determined by retrograde analysis, not assumed drawn.
    """
    # MED-08 refactor: explicit element-wise comparisons replace the
    # int8→uint8 view trick. Same speed, readable at a glance, no
    # dependence on NumPy's signed/unsigned conversion behaviour.
    from draughts.config import BLACK, BLACK_KING, WHITE, WHITE_KING

    bp = int(np.sum(grid == BLACK))
    wp = int(np.sum(grid == WHITE))
    bk = int(np.sum(grid == BLACK_KING))
    wk = int(np.sum(grid == WHITE_KING))
    return bp == 0 and wp == 0 and bk == 1 and wk == 1


def _can_be_pawn(x: int, y: int, piece_val: int) -> bool:
    """Return True if a pawn of this type can legally stand on (x, y).

    A pawn on its own promotion row would have already been promoted,
    so such placements are illegal.
    """
    if piece_val == int(BLACK):
        return y != _BLACK_PROMOTE_ROW
    if piece_val == int(WHITE):
        return y != _WHITE_PROMOTE_ROW
    return True  # kings can be anywhere


# ---------------------------------------------------------------------------
# Board factory helper
# ---------------------------------------------------------------------------


def _make_board(pieces: list[tuple[int, int, int]]) -> Board:
    """Create a Board from a list of (x, y, piece_value) triples."""
    board = Board(empty=True)
    for x, y, pv in pieces:
        board.grid[y, x] = np.int8(pv)
    return board


# ---------------------------------------------------------------------------
# Piece type lists
# ---------------------------------------------------------------------------

_BLACK_PIECE_TYPES = [int(BLACK), int(BLACK_KING)]  # 1, 2
_WHITE_PIECE_TYPES = [int(WHITE), int(WHITE_KING)]  # -1, -2


def _enumerate_lopsided_same_side(
    out: list[tuple[list[tuple[int, int, int]], Color]],
    n: int,
    color_side: str,
) -> None:
    """Enumerate positions with N pieces of one side and 0 of the other.

    Required for retrograde propagation correctness (BITBASE-ENUM fix):
    when a capture removes the opponent's last piece, the resulting child
    position has 0 pieces on that side. If that child isn't in the
    bitbase, the propagation can't learn that the opponent has lost, and
    parent positions get mislabeled DRAW.

    ``color_side`` is "black" for N black pieces / 0 white (or "white"
    for the mirror). Both side-to-move options are emitted for each.
    """
    piece_types = _BLACK_PIECE_TYPES if color_side == "black" else _WHITE_PIECE_TYPES
    sq = DARK_SQUARES
    for combo in itertools.combinations(range(len(sq)), n):
        coords = [sq[i] for i in combo]
        type_options = [
            [p for p in piece_types if _can_be_pawn(x, y, p)]
            for x, y in coords
        ]
        if any(not opts for opts in type_options):
            continue
        for types in itertools.product(*type_options):
            pieces = [(x, y, pt) for (x, y), pt in zip(coords, types, strict=True)]
            for turn_color in (Color.BLACK, Color.WHITE):
                out.append((pieces, turn_color))


def _enumerate_all_positions(max_pieces: int = 3) -> list[tuple[list[tuple[int, int, int]], Color]]:
    """Enumerate all legal positions with 1..max_pieces pieces total.

    Covers EVERY piece-count split (N_black, N_white) with
    N_black + N_white ∈ [1, max_pieces], including lopsided positions
    like "2 black + 0 white" and "3 black + 0 white" — these are
    reachable as children of capture sequences and MUST be in the
    bitbase for retrograde propagation to correctly identify wins
    (BITBASE-ENUM fix, previously only "A vs B" splits with A,B >= 1
    were enumerated, causing mislabelled DRAW entries).

    Each position is represented as (pieces, color_to_move) where:
    - pieces: [(x, y, piece_value), ...]
    - color_to_move: whose turn it is
    """
    positions: list[tuple[list[tuple[int, int, int]], Color]] = []
    sq = DARK_SQUARES

    # --- 1 piece: black only ---
    for bi in range(len(sq)):
        bx, by = sq[bi]
        for bpt in _BLACK_PIECE_TYPES:
            if not _can_be_pawn(bx, by, bpt):
                continue
            for color in (Color.BLACK, Color.WHITE):
                positions.append(([(bx, by, bpt)], color))

    # --- 1 piece: white only ---
    for wi in range(len(sq)):
        wx, wy = sq[wi]
        for wpt in _WHITE_PIECE_TYPES:
            if not _can_be_pawn(wx, wy, wpt):
                continue
            for color in (Color.BLACK, Color.WHITE):
                positions.append(([(wx, wy, wpt)], color))

    # --- N-piece lopsided positions (one side has 0). Required for
    # retrograde correctness (see BITBASE-ENUM fix note above). ---
    for n in range(2, max_pieces + 1):
        _enumerate_lopsided_same_side(positions, n, "black")
        _enumerate_lopsided_same_side(positions, n, "white")

    # --- 2 pieces: 1 black + 1 white ---
    for bi, wi in itertools.product(range(len(sq)), range(len(sq))):
        if bi == wi:
            continue
        bx, by = sq[bi]
        wx, wy = sq[wi]
        for bpt in _BLACK_PIECE_TYPES:
            if not _can_be_pawn(bx, by, bpt):
                continue
            for wpt in _WHITE_PIECE_TYPES:
                if not _can_be_pawn(wx, wy, wpt):
                    continue
                pieces = [(bx, by, bpt), (wx, wy, wpt)]
                for color in (Color.BLACK, Color.WHITE):
                    positions.append((pieces, color))

    # --- 3 pieces: 2 black + 1 white ---
    for (bi1, bi2), wi1 in itertools.product(
        itertools.combinations(range(len(sq)), 2),
        range(len(sq)),
    ):
        if wi1 in (bi1, bi2):
            continue
        bx1, by1 = sq[bi1]
        bx2, by2 = sq[bi2]
        wx1, wy1 = sq[wi1]
        for bpt1 in _BLACK_PIECE_TYPES:
            if not _can_be_pawn(bx1, by1, bpt1):
                continue
            for bpt2 in _BLACK_PIECE_TYPES:
                if not _can_be_pawn(bx2, by2, bpt2):
                    continue
                for wpt1 in _WHITE_PIECE_TYPES:
                    if not _can_be_pawn(wx1, wy1, wpt1):
                        continue
                    pieces = [(bx1, by1, bpt1), (bx2, by2, bpt2), (wx1, wy1, wpt1)]
                    for color in (Color.BLACK, Color.WHITE):
                        positions.append((pieces, color))

    # --- 3 pieces: 1 black + 2 white ---
    for bi1, (wi1, wi2) in itertools.product(
        range(len(sq)),
        itertools.combinations(range(len(sq)), 2),
    ):
        if bi1 in (wi1, wi2):
            continue
        bx1, by1 = sq[bi1]
        wx1, wy1 = sq[wi1]
        wx2, wy2 = sq[wi2]
        for bpt1 in _BLACK_PIECE_TYPES:
            if not _can_be_pawn(bx1, by1, bpt1):
                continue
            for wpt1 in _WHITE_PIECE_TYPES:
                if not _can_be_pawn(wx1, wy1, wpt1):
                    continue
                for wpt2 in _WHITE_PIECE_TYPES:
                    if not _can_be_pawn(wx2, wy2, wpt2):
                        continue
                    pieces = [(bx1, by1, bpt1), (wx1, wy1, wpt1), (wx2, wy2, wpt2)]
                    for color in (Color.BLACK, Color.WHITE):
                        positions.append((pieces, color))

    if max_pieces < 4:
        return positions

    # --- 4 pieces: 2 black + 2 white ---
    for (bi1, bi2), (wi1, wi2) in itertools.product(
        itertools.combinations(range(len(sq)), 2),
        itertools.combinations(range(len(sq)), 2),
    ):
        if bi1 in (wi1, wi2) or bi2 in (wi1, wi2):
            continue
        bx1, by1 = sq[bi1]
        bx2, by2 = sq[bi2]
        wx1, wy1 = sq[wi1]
        wx2, wy2 = sq[wi2]
        for bpt1 in _BLACK_PIECE_TYPES:
            if not _can_be_pawn(bx1, by1, bpt1):
                continue
            for bpt2 in _BLACK_PIECE_TYPES:
                if not _can_be_pawn(bx2, by2, bpt2):
                    continue
                for wpt1 in _WHITE_PIECE_TYPES:
                    if not _can_be_pawn(wx1, wy1, wpt1):
                        continue
                    for wpt2 in _WHITE_PIECE_TYPES:
                        if not _can_be_pawn(wx2, wy2, wpt2):
                            continue
                        pieces = [(bx1, by1, bpt1), (bx2, by2, bpt2), (wx1, wy1, wpt1), (wx2, wy2, wpt2)]
                        for color in (Color.BLACK, Color.WHITE):
                            positions.append((pieces, color))

    # --- 4 pieces: 3 black + 1 white ---
    for (bi1, bi2, bi3), wi1 in itertools.product(
        itertools.combinations(range(len(sq)), 3),
        range(len(sq)),
    ):
        if wi1 in (bi1, bi2, bi3):
            continue
        bx1, by1 = sq[bi1]
        bx2, by2 = sq[bi2]
        bx3, by3 = sq[bi3]
        wx1, wy1 = sq[wi1]
        for bpt1 in _BLACK_PIECE_TYPES:
            if not _can_be_pawn(bx1, by1, bpt1):
                continue
            for bpt2 in _BLACK_PIECE_TYPES:
                if not _can_be_pawn(bx2, by2, bpt2):
                    continue
                for bpt3 in _BLACK_PIECE_TYPES:
                    if not _can_be_pawn(bx3, by3, bpt3):
                        continue
                    for wpt1 in _WHITE_PIECE_TYPES:
                        if not _can_be_pawn(wx1, wy1, wpt1):
                            continue
                        pieces = [(bx1, by1, bpt1), (bx2, by2, bpt2), (bx3, by3, bpt3), (wx1, wy1, wpt1)]
                        for color in (Color.BLACK, Color.WHITE):
                            positions.append((pieces, color))

    # --- 4 pieces: 1 black + 3 white ---
    for bi1, (wi1, wi2, wi3) in itertools.product(
        range(len(sq)),
        itertools.combinations(range(len(sq)), 3),
    ):
        if bi1 in (wi1, wi2, wi3):
            continue
        bx1, by1 = sq[bi1]
        wx1, wy1 = sq[wi1]
        wx2, wy2 = sq[wi2]
        wx3, wy3 = sq[wi3]
        for bpt1 in _BLACK_PIECE_TYPES:
            if not _can_be_pawn(bx1, by1, bpt1):
                continue
            for wpt1 in _WHITE_PIECE_TYPES:
                if not _can_be_pawn(wx1, wy1, wpt1):
                    continue
                for wpt2 in _WHITE_PIECE_TYPES:
                    if not _can_be_pawn(wx2, wy2, wpt2):
                        continue
                    for wpt3 in _WHITE_PIECE_TYPES:
                        if not _can_be_pawn(wx3, wy3, wpt3):
                            continue
                        pieces = [(bx1, by1, bpt1), (wx1, wy1, wpt1), (wx2, wy2, wpt2), (wx3, wy3, wpt3)]
                        for color in (Color.BLACK, Color.WHITE):
                            positions.append((pieces, color))

    if max_pieces < 5:
        return positions

    # --- 5 pieces: enumerate all 5-piece configurations (split 4-1, 3-2, 2-3, 1-4).
    # Same pattern as 4-piece; kept terse to contain line count. 5-piece
    # generation is 100M+ raw configs and is intended for overnight runs.
    # NOTE(#37): code-complete; data generation requires hours of CPU and
    # binary-format storage (JSON would exceed ~500 MB).
    for (bsplit, wsplit) in [(4, 1), (3, 2), (2, 3), (1, 4)]:
        for b_indices in itertools.combinations(range(len(sq)), bsplit):
            for w_indices in itertools.combinations(range(len(sq)), wsplit):
                if set(b_indices) & set(w_indices):
                    continue
                b_coords = [sq[i] for i in b_indices]
                w_coords = [sq[i] for i in w_indices]
                _emit_ptype_combinations(positions, b_coords, w_coords)

    return positions


def _emit_ptype_combinations(
    out: list[tuple[list[tuple[int, int, int]], Color]],
    black_coords: list[tuple[int, int]],
    white_coords: list[tuple[int, int]],
) -> None:
    """Cartesian product over piece types (pawn/king) for both sides; append to out."""
    import itertools as _it

    bt_options: list[list[int]] = [
        [p for p in _BLACK_PIECE_TYPES if _can_be_pawn(x, y, p)]
        for x, y in black_coords
    ]
    wt_options: list[list[int]] = [
        [p for p in _WHITE_PIECE_TYPES if _can_be_pawn(x, y, p)]
        for x, y in white_coords
    ]
    if any(not opts for opts in bt_options + wt_options):
        return
    for bts in _it.product(*bt_options):
        for wts in _it.product(*wt_options):
            pieces: list[tuple[int, int, int]] = []
            for (x, y), pt in zip(black_coords, bts, strict=True):
                pieces.append((x, y, pt))
            for (x, y), pt in zip(white_coords, wts, strict=True):
                pieces.append((x, y, pt))
            for color in (Color.BLACK, Color.WHITE):
                out.append((pieces, color))


# ---------------------------------------------------------------------------
# Retrograde analysis — optimised: pre-compute edges, then iterate on hashes
# ---------------------------------------------------------------------------

_UNKNOWN = 2  # sentinel — not WIN/DRAW/LOSS


def _build_bitbase(max_iters: int = 100, verbose: bool = True, max_pieces: int = 3) -> EndgameBitbase:
    """Run the full retrograde analysis and return the completed bitbase.

    ``max_pieces``: 3 (historical) or 4 (full 4-piece bitbase, #27).
    """

    t0 = time.perf_counter()
    if verbose:
        print(f"Enumerating positions up to {max_pieces} pieces...", flush=True)

    raw_positions = _enumerate_all_positions(max_pieces=max_pieces)
    if verbose:
        print(f"  {len(raw_positions):,} raw (piece-config, color) pairs", flush=True)

    # Phase 1: build the position graph and assign initial labels.
    #
    # results[h] = WIN(1) / DRAW(0) / LOSS(-1) / _UNKNOWN(2)
    #
    # For each UNKNOWN position we track:
    #   unresolved[h]  — number of children not yet labelled
    #   win_children[h] — number of children labelled WIN (for the opponent)
    #
    # Propagation rule (from parent's POV, where opponent is the side-to-move
    # at the child):
    #   child == LOSS (opponent loses) → parent = WIN  (we can pick this child)
    #   child == DRAW                  → parent cannot be LOSS (we take the draw)
    #   child == WIN  (opponent wins)  → bad for us, but not decisive alone
    #
    # Parent becomes LOSS only when every child is WIN for the opponent
    # (i.e. unresolved[h]==0 AND win_children[h]==total_children[h]).
    # Parent becomes WIN as soon as any child is LOSS for the opponent.

    if verbose:
        print("Building position graph...", flush=True)

    results: dict[int, int] = {}
    rev_edges: dict[int, set[int]] = {}  # child_h → {parent_h, ...}
    unresolved: dict[int, int] = {}  # h → count of unresolved children
    win_children: dict[int, int] = {}  # h → count of WIN-for-opp children
    total_children: dict[int, int] = {}  # h → total child count

    t_phase1_start = time.perf_counter()

    for pieces, color in raw_positions:
        board = _make_board(pieces)
        h = _zobrist_hash(board.grid, color)

        if h in results:
            continue

        moves = _generate_all_moves(board, color)

        if not moves:
            results[h] = LOSS
            continue

        if _is_lone_king_vs_lone_king(board.grid):
            results[h] = DRAW
            continue

        # Unknown — compute child hashes
        opp = Color.WHITE if color == Color.BLACK else Color.BLACK
        child_hashes = []
        for kind, path in moves:
            child_board = _apply_move(board, kind, path)
            ch = _zobrist_hash(child_board.grid, opp)
            child_hashes.append(ch)

        results[h] = _UNKNOWN
        n = len(child_hashes)
        unresolved[h] = n
        win_children[h] = 0
        total_children[h] = n

        for ch in child_hashes:
            rev_edges.setdefault(ch, set()).add(h)

    t_phase1_end = time.perf_counter()
    total_unique = len(results)
    n_terminals_loss = sum(1 for r in results.values() if r == LOSS)
    n_terminals_draw = sum(1 for r in results.values() if r == DRAW)
    n_unknown = total_unique - n_terminals_loss - n_terminals_draw

    if verbose:
        print(f"  Unique positions : {total_unique:,}  (graph build: {t_phase1_end - t_phase1_start:.1f}s)")
        print(f"  Immediate LOSS   : {n_terminals_loss:,}")
        print(f"  Immediate DRAW   : {n_terminals_draw:,}")
        print(f"  Unknown          : {n_unknown:,}")
        print("Running retrograde propagation...", flush=True)

    # Phase 2: BFS propagation — seed with all resolved positions, propagate
    # outward through reverse edges.

    from collections import deque

    queue: deque[int] = deque()

    for h, r in results.items():
        if r != _UNKNOWN:
            queue.append(h)

    resolved_count = 0

    while queue:
        h = queue.popleft()
        r = results[h]

        for parent_h in rev_edges.get(h, set()):
            if results.get(parent_h, _UNKNOWN) != _UNKNOWN:
                continue  # already resolved — skip

            # r is the result at the child (h) from the OPPONENT's perspective
            # (opponent = the side-to-move at h = the side that doesn't own parent_h).
            if r == LOSS:
                # Opponent loses at this child → parent player wins by choosing it
                results[parent_h] = WIN
                resolved_count += 1
                queue.append(parent_h)
            else:
                # r is WIN or DRAW: this child doesn't immediately give parent a win.
                # Decrement unresolved count for parent.
                ur = unresolved.get(parent_h, 0)
                if ur > 0:
                    unresolved[parent_h] = ur - 1
                    if r == WIN:
                        win_children[parent_h] = win_children.get(parent_h, 0) + 1

                    # If all children resolved and every one is a WIN for opponent → parent LOSES.
                    # If any child is DRAW → parent can choose the draw; leave as _UNKNOWN
                    # (the fixed-point sweep will assign DRAW).
                    if unresolved[parent_h] == 0 and win_children.get(parent_h, 0) == total_children.get(parent_h, 0):
                        # Every child is a WIN for the opponent → parent LOSES
                        results[parent_h] = LOSS
                        resolved_count += 1
                        queue.append(parent_h)

        if verbose and resolved_count % 100000 == 0 and resolved_count > 0:
            unknowns = sum(1 for rv in results.values() if rv == _UNKNOWN)
            print(f"  ... {resolved_count:,} resolved, {unknowns:,} unknown remaining", flush=True)

    # --- Remaining unknowns → DRAW ---
    draw_from_unknown = 0
    for h in results:
        if results[h] == _UNKNOWN:
            results[h] = DRAW
            draw_from_unknown += 1

    t1 = time.perf_counter()

    if verbose and draw_from_unknown:
        print(f"  {draw_from_unknown:,} unresolved positions assigned DRAW.")

    # Persist max_pieces as spec metadata so the engine knows its probe
    # threshold at load time (HIGH-06).
    bb = EndgameBitbase(entries=dict(results.items()), max_pieces=max_pieces)
    s = bb.stats()

    if verbose:
        print()
        print("=== Bitbase stats ===")
        print(f"  Total positions : {s['total']:>10,}")
        print(f"  Wins (to-move)  : {s['wins']:>10,}")
        print(f"  Draws           : {s['draws']:>10,}")
        print(f"  Losses (to-move): {s['losses']:>10,}")
        print(f"  Generation time : {t1 - t0:>8.1f}s")

    return bb


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the 3-piece endgame bitbase for Russian draughts.")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent / "resources" / "bitbase_3.json"),
        help="Output file path (default: draughts/resources/bitbase_3.json)",
    )
    parser.add_argument(
        "--max-iters",
        type=int,
        default=100,
        help="Max retrograde passes (unused in BFS mode, kept for compat)",
    )
    parser.add_argument(
        "--max-pieces",
        type=int,
        default=3,
        choices=[3, 4, 5],
        help="Max pieces (3 = default; 4 = #27 full 4-piece; 5 = #37 full 5-piece — expect hours of compute)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bb = _build_bitbase(max_iters=args.max_iters, verbose=not args.quiet, max_pieces=args.max_pieces)

    print(f"\nSaving to {output_path}...", flush=True)
    bb.save(output_path)
    size_kb = output_path.stat().st_size / 1024
    print(f"Saved. File size: {size_kb:.1f} KB")

    if size_kb > 200 * 1024:
        print("WARNING: file size exceeds 200 MB budget!", file=sys.stderr)


if __name__ == "__main__":
    main()
