"""Batch-mine puzzles by generating self-play games and scanning for blunders.

Item #29 driver. Runs a pool of self-play games between two engines (both
at a given difficulty, with blunder injection at the lower-difficulty
side to create mistakes), then mines blunder puzzles from each game.
Resulting puzzles are appended to the shipped puzzle catalog.

Usage::

    python -m draughts.tools.mine_puzzles_batch --games 50 --out .planning/mined.json
    python -m draughts.tools.mine_puzzles_batch --games 30 --merge draughts/resources/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from draughts.config import Color
from draughts.game.ai import AIEngine
from draughts.game.board import Board
from draughts.game.puzzle_miner import mine_puzzles_from_game
from draughts.ui.game_analyzer import analyze_game_positions

logger = logging.getLogger("draughts.mine_puzzles")


def play_selfplay_game(
    depth_strong: int = 5,
    depth_weak: int = 2,
    max_ply: int = 80,
    opening_plies: int = 0,
) -> list[str]:
    """Play a single self-play game and return the list of position strings.

    Asymmetric depths: one side is weaker and blunders more often, producing
    positions suitable for mining. When ``opening_plies > 0`` the first N
    plies are played RANDOMLY by both sides to diversify openings so batch
    mining doesn't produce duplicate games.
    """
    import random as _random

    from draughts.game.ai import _generate_all_moves

    board = Board()
    positions: list[str] = [board.to_position_string()]
    turn = Color.WHITE
    white_engine = AIEngine(difficulty=1, color=Color.WHITE, search_depth=depth_weak, use_book=False, use_bitbase=False)
    black_engine = AIEngine(difficulty=6, color=Color.BLACK, search_depth=depth_strong, use_book=False, use_bitbase=False)

    for ply in range(max_ply):
        if ply < opening_plies:
            moves = _generate_all_moves(board, turn)
            if not moves:
                break
            kind, path = _random.choice(moves)
        else:
            engine = white_engine if turn == Color.WHITE else black_engine
            move = engine.find_move(board.copy())
            if move is None:
                break
            kind, path = move.kind, move.path

        if kind == "capture":
            board.execute_capture_path(path)
        else:
            (x1, y1), (x2, y2) = path[:2]
            board.execute_move(x1, y1, x2, y2)
        positions.append(board.to_position_string())
        turn = turn.opponent

        go = board.check_game_over({}, quiet_plies=0, kings_only_plies=0)
        if go is not None:
            break

    return positions


def mine_from_selfplay(n_games: int, analysis_depth: int = 4, min_delta: float = 2.0, seed: int = 12345) -> list[dict]:
    """Run n_games of self-play and collect puzzles from each.

    ``min_delta`` lowers the miner's eval-swing threshold below the
    default blunder cut-off so "?" (mistake, ≥1.5) positions also qualify.
    Useful for building volume when strict blunders are rare.
    """
    import random as _random

    _random.seed(seed)

    all_puzzles: list[dict] = []
    t_start = time.perf_counter()
    for i in range(n_games):
        # Different number of random opening plies per game for variety.
        opening_plies = (i % 5) + 1  # 1..5
        positions = play_selfplay_game(opening_plies=opening_plies)
        if len(positions) < 4:
            continue
        result = analyze_game_positions(positions, depth=analysis_depth)
        # Include "?" (mistake) annotations too — broaden the net.
        # We inline-duplicate mine_puzzles_from_game's logic with a
        # relaxed annotation set to keep the public API unchanged.
        game_puzzles = mine_puzzles_from_game(positions, result.annotations, min_delta_cp=min_delta)
        # Also harvest mistakes (single "?") — same structure, difficulty=2.
        mistake_anns = [a for a in result.annotations if a.annotation == "?" and a.delta_cp >= min_delta]
        if mistake_anns:
            # Temporarily retag as "??" so mine_puzzles_from_game picks them up.
            for a in mistake_anns:
                a.annotation = "??"
            more = mine_puzzles_from_game(positions, mistake_anns, min_delta_cp=min_delta)
            # Mark them difficulty 2 regardless of delta magnitude — these
            # are "mistakes" not "blunders".
            for p in more:
                p["difficulty"] = min(p.get("difficulty", 2), 2)
            game_puzzles.extend(more)
        all_puzzles.extend(game_puzzles)
        elapsed = time.perf_counter() - t_start
        print(
            f"  game {i + 1}/{n_games}: {len(positions) - 1} plies → "
            f"{len(game_puzzles)} puzzles, total {len(all_puzzles)}, elapsed {elapsed:.1f}s",
            file=sys.stderr,
        )
    return all_puzzles


def dedupe(puzzles: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for p in puzzles:
        key = p.get("position", "")
        if key and key not in seen:
            seen.add(key)
            out.append(p)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(prog="mine_puzzles_batch", description=__doc__)
    parser.add_argument("--games", type=int, default=30, help="number of self-play games (default 30)")
    parser.add_argument("--depth", type=int, default=4, help="analysis depth (default 4)")
    parser.add_argument("--seed", type=int, default=12345, help="random seed for opening variety (change per run)")
    parser.add_argument("--out", type=Path, required=True, help="output JSON file")
    parser.add_argument("--merge", type=Path, help="merge with this existing puzzle file")
    args = parser.parse_args()

    mined = mine_from_selfplay(args.games, analysis_depth=args.depth, seed=args.seed)
    mined = dedupe(mined)
    print(f"Mined {len(mined)} unique puzzles", file=sys.stderr)

    final = list(mined)
    if args.merge and args.merge.exists():
        existing = json.loads(args.merge.read_text(encoding="utf-8"))
        existing_positions = {p.get("position", "") for p in existing}
        for p in mined:
            if p.get("position", "") not in existing_positions:
                existing.append(p)
                existing_positions.add(p.get("position", ""))
        final = existing
        print(f"After merge: {len(final)} total puzzles", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(final)} puzzles → {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
