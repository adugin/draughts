"""Benchmark script for draughts AI engine.

Measures computation speed at different search depths and board positions.
Usage: python benchmark.py [--depth MAX_DEPTH] [--profile] [--profile-depth N]
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import time

from draughts.game.ai import computer_move
from draughts.game.board import Board


# ---------------------------------------------------------------------------
# Test positions (various game phases)
# ---------------------------------------------------------------------------

POSITIONS = {
    "opening": {
        "desc": "Starting position (12v12)",
        "position": "bbbbbbbbbbbbnnnnnnnnwwwwwwwwwwww",
        "color": "b",
    },
    "midgame_1": {
        "desc": "Midgame (8v8)",
        "position": "nbnnbnbnbnnnnnnnwnnnnnwnwnnwwwnn",
        "color": "b",
    },
    "midgame_2": {
        "desc": "Midgame with captures (4v4)",
        "position": "nnnnbnnnnnbnnnwnnnnnwnwnnnnnnnnn",  # 32
        "color": "b",
    },
    "endgame_3v3": {
        "desc": "Endgame pawns (3v3)",
        "position": "nnnnnnbnnnwnnbnnwnnnnnnbnwnnnnnn",
        "color": "b",
    },
    "endgame_2v2": {
        "desc": "Endgame kings+pawns (2v2)",
        "position": "BnnnnnnnnnnnnnbnnnnnnnnnnwnnnnnW",
        "color": "b",
    },
    "endgame_1v1": {
        "desc": "King vs pawn",
        "position": "nnnnnnnnnBnnnnnnnnnnnnnwnnnnnnnn",
        "color": "b",
    },
}


def make_board(pos_str: str) -> Board:
    b = Board(empty=True)
    b.load_from_position_string(pos_str)
    return b


def benchmark_position(name: str, pos_info: dict, max_depth: int = 5, runs: int = 3) -> list[dict]:
    """Benchmark a single position at depths 1..max_depth."""
    results = []
    board = make_board(pos_info["position"])
    color = pos_info["color"]

    print(f"\n{'=' * 65}")
    print(f"  {name}: {pos_info['desc']}")
    print(f"  black={board.count_pieces('b')}, white={board.count_pieces('w')}, AI={color}")
    print(f"{'=' * 65}")
    print(f"  {'Depth':>5} | {'Avg ms':>10} | {'Min ms':>10} | {'Max ms':>10} | {'Move':<30}")
    print(f"  {'-' * 5}-+-{'-' * 10}-+-{'-' * 10}-+-{'-' * 10}-+-{'-' * 30}")

    for depth in range(1, max_depth + 1):
        times = []
        move_result = None
        for _ in range(runs):
            t0 = time.perf_counter()
            move_result = computer_move(
                board,
                difficulty=3,
                color=color,
                depth=depth,
            )
            t1 = time.perf_counter()
            times.append((t1 - t0) * 1000)

        avg_ms = sum(times) / len(times)
        min_ms = min(times)
        max_ms = max(times)

        move_str = "None"
        if move_result:
            path = "->".join(Board.pos_to_notation(x, y) for x, y in move_result.path)
            move_str = f"{move_result.kind}: {path}"

        print(f"  {depth:>5} | {avg_ms:>10.1f} | {min_ms:>10.1f} | {max_ms:>10.1f} | {move_str:<30}")
        results.append(
            {
                "position": name,
                "depth": depth,
                "avg_ms": avg_ms,
                "min_ms": min_ms,
                "max_ms": max_ms,
                "move": move_str,
            }
        )

        if avg_ms > 60000:
            print(f"  [Stopping: >60s at depth {depth}]")
            break

    return results


def run_profiling(depth: int = 3):
    """Run cProfile on opening position to find hotspots."""
    board = Board()
    print(f"\n{'=' * 65}")
    print(f"  PROFILING: Starting position, depth={depth}, 3 runs")
    print(f"{'=' * 65}")

    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(3):
        computer_move(board, difficulty=3, color="b", depth=depth)
    profiler.disable()

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(25)
    print(stream.getvalue())

    stream2 = io.StringIO()
    stats2 = pstats.Stats(profiler, stream=stream2)
    stats2.sort_stats("tottime")
    stats2.print_stats(15)
    print("--- By total time (hottest functions) ---")
    print(stream2.getvalue())


def main():
    parser = argparse.ArgumentParser(description="Benchmark draughts AI engine")
    parser.add_argument("--depth", type=int, default=6, help="Max depth to test (default: 6)")
    parser.add_argument("--runs", type=int, default=3, help="Runs per measurement (default: 3)")
    parser.add_argument("--profile", action="store_true", help="Run cProfile analysis")
    parser.add_argument("--profile-depth", type=int, default=3, help="Depth for profiling (default: 3)")
    args = parser.parse_args()

    print("=" * 65)
    print("  DRAUGHTS AI ENGINE BENCHMARK")
    print(f"  Max depth: {args.depth}, Runs per depth: {args.runs}")
    print("=" * 65)

    all_results = []
    for name, pos_info in POSITIONS.items():
        results = benchmark_position(name, pos_info, max_depth=args.depth, runs=args.runs)
        all_results.extend(results)

    # Summary
    print(f"\n{'=' * 65}")
    print("  SUMMARY (avg ms)")
    print(f"{'=' * 65}")
    header = f"  {'Position':<15}"
    for d in range(1, args.depth + 1):
        header += f" | {'D' + str(d):>8}"
    print(header)
    print(f"  {'-' * 15}" + ("-+-" + "-" * 8) * args.depth)

    for name in POSITIONS:
        row = f"  {name:<15}"
        for d in range(1, args.depth + 1):
            match = [r for r in all_results if r["position"] == name and r["depth"] == d]
            if match:
                ms = match[0]["avg_ms"]
                if ms < 1000:
                    row += f" | {ms:>7.1f}ms"[:11]
                else:
                    row += f" | {ms / 1000:>7.1f}s "[:11]
                # Pad to 8+3 chars
                val = f"{ms:.0f}" if ms < 10000 else f"{ms / 1000:.1f}s"
                row += f" | {val:>8}"
            else:
                row += f" | {'—':>8}"
        print(row)

    if args.profile:
        run_profiling(depth=args.profile_depth)


if __name__ == "__main__":
    main()
