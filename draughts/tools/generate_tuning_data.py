"""Training data generator for Texel eval tuning (D11).

Runs N self-play games at a fixed depth and records (position_string, game_result)
pairs. Skips the first OPENING_SKIP_PLY plies (opening book territory) and
terminal positions.

Output JSON format: list of {"position": "32-char", "result": 0.0 | 0.5 | 1.0}
where result is from WHITE's perspective:
    1.0 = white win, 0.5 = draw, 0.0 = black win (white loss)

Usage:
    python -m draughts.tools.generate_tuning_data
    python -m draughts.tools.generate_tuning_data --games 100 --depth 5 --output tuning_data.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from draughts.config import Color
from draughts.game.ai import AIEngine
from draughts.game.headless import HeadlessGame

# How many plies from the start to skip (opening territory)
_OPENING_SKIP_PLY = 6

# Hard time limits per game to prevent hanging
_MOVE_TIMEOUT = 1.0  # seconds per AI move
_GAME_TIMEOUT = 30.0  # seconds per complete game
_MAX_PLY = 120  # max half-moves before draw
_QUIET_MOVE_LIMIT = 30  # quiet-move draw rule (middlegame)
_QUIET_MOVE_LIMIT_ENDGAME = 10  # quiet-move draw rule (endgame)


def generate_training_data(
    n_games: int = 200,
    depth: int = 5,
    output: str = "tuning_data.json",
    verbose: bool = True,
) -> list[dict]:
    """Play n_games of self-play, recording every position reached and the
    final game result.

    Positions from the first _OPENING_SKIP_PLY plies are excluded (opening
    book territory). Terminal positions (where one side has no pieces / moves)
    are also excluded since the eval is not meaningful there.

    Args:
        n_games: Number of self-play games to play.
        depth: AI search depth for both sides.
        output: Output file path (JSON). Empty string = do not save.
        verbose: Print progress.

    Returns:
        List of {"position": str, "result": float} dicts.
    """
    engine_black = AIEngine(difficulty=2, color=Color.BLACK, search_depth=depth)
    engine_white = AIEngine(difficulty=2, color=Color.WHITE, search_depth=depth)

    all_samples: list[dict] = []
    seen_positions: set[str] = set()  # deduplicate across all games

    t_start = time.perf_counter()

    for game_num in range(1, n_games + 1):
        # Alternate which color engine_black / engine_white is to remove bias
        # (both engines are identical in strength so this is mostly cosmetic)
        if game_num % 2 == 0:
            b_engine = AIEngine(difficulty=2, color=Color.BLACK, search_depth=depth)
            w_engine = AIEngine(difficulty=2, color=Color.WHITE, search_depth=depth)
        else:
            b_engine = AIEngine(difficulty=2, color=Color.BLACK, search_depth=depth)
            w_engine = AIEngine(difficulty=2, color=Color.WHITE, search_depth=depth)

        game = HeadlessGame(
            black_engine=b_engine,
            white_engine=w_engine,
            auto_ai=True,
        )

        # Collect positions as the game proceeds, track which ply they were at
        positions_this_game: list[tuple[str, int]] = []  # (position_string, ply)

        # Play game with hard limits
        g_start = time.perf_counter()

        while not game.is_over:
            # Check game-level time limit
            if time.perf_counter() - g_start >= _GAME_TIMEOUT:
                break
            if game.ply_count >= _MAX_PLY:
                break

            ply_before = game.ply_count
            pos = game.position_string

            record = game.make_ai_move(move_timeout=_MOVE_TIMEOUT)
            if record is None:
                break

            # Record position BEFORE this move (not terminal since a move was made)
            if ply_before >= _OPENING_SKIP_PLY:
                positions_this_game.append((pos, ply_before))

        # Force-close if still running
        if not game.is_over:
            # Access internal _end_game to terminate
            game._end_game(None, "draw_max_ply")

        result = game.result
        if result is None:
            continue

        # Convert result to a float from white's perspective:
        # 1.0 = white win, 0.5 = draw, 0.0 = black win
        if result.winner is None:
            result_val = 0.5
        elif result.winner == Color.WHITE:
            result_val = 1.0
        else:
            result_val = 0.0

        # Add all non-opening, non-terminal positions from this game
        new_this_game = 0
        for pos_str, _ply in positions_this_game:
            if pos_str not in seen_positions:
                seen_positions.add(pos_str)
                all_samples.append({"position": pos_str, "result": result_val})
                new_this_game += 1

        elapsed = time.perf_counter() - t_start
        if verbose:
            winner_str = "draw" if result.winner is None else str(result.winner)
            print(
                f"  Game {game_num}/{n_games}: {winner_str} "
                f"({result.reason}, {result.ply_count} plies, "
                f"+{new_this_game} pos) — total {len(all_samples)} samples, "
                f"{elapsed:.0f}s elapsed"
            )
            sys.stdout.flush()

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_samples, f, separators=(",", ":"))
        if verbose:
            size_kb = out_path.stat().st_size // 1024
            print(f"\nSaved {len(all_samples)} samples to {out_path} ({size_kb} KB)")

    return all_samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Texel tuning data via self-play")
    parser.add_argument("--games", type=int, default=200, help="Number of self-play games (default: 200)")
    parser.add_argument("--depth", type=int, default=5, help="AI search depth for both sides (default: 5)")
    parser.add_argument(
        "--output", type=str, default="tuning_data.json", help="Output JSON path (default: tuning_data.json)"
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress per-game output")
    args = parser.parse_args()

    print(f"Generating tuning data: {args.games} games at depth {args.depth}")
    print(f"Output: {args.output}")
    print(f"Per-game limits: move={_MOVE_TIMEOUT}s, game={_GAME_TIMEOUT}s, max_ply={_MAX_PLY}")
    print()

    t0 = time.perf_counter()
    samples = generate_training_data(
        n_games=args.games,
        depth=args.depth,
        output=args.output,
        verbose=not args.quiet,
    )
    elapsed = time.perf_counter() - t0

    print(f"\nDone: {len(samples)} unique positions from {args.games} games in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
