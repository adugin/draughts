"""Developer CLI tool for draughts — programmatic testing and analysis.

Usage:
    python dev.py play-game [--games N] [--difficulty D] [--depth N] [--max-ply N] [-v]
    python dev.py analyze [--position POS] [--depth N]
    python dev.py test-move --position POS --expected MOVE [--depth N]
    python dev.py tournament [--games N] [--diff-a D] [--depth-a N] [--diff-b D] [--depth-b N] [-v]
    python dev.py replay FILE [--verbose]
    python dev.py screenshot [--position POS] [--output FILE] [--size N]
    python dev.py validate-rules
    python dev.py play-opening MOVES [--depth N]
    python dev.py pdn-info FILE
"""

from __future__ import annotations

import argparse
import sys
import time

from draughts.config import Color
from draughts.game.board import Board


def _open_heartbeat(path: str | None):
    """Return (heartbeat_fn, close_fn) for the given optional path."""
    if not path:
        return None, lambda: None
    fh = open(path, "a", buffering=1, encoding="utf-8")  # noqa: SIM115 — long-lived handle returned via close_fn
    fh.write(f"# heartbeat open {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    def _hb(game, record):
        fh.write(
            f"ply={record.ply} color={record.color.name} "
            f"{record.kind}:{record.notation} "
            f"eval={record.eval_after:+.2f} "
            f"tmove={game._last_move_time_s:.2f}s "
            f"quiet={game._quiet_plies}\n"
        )

    return _hb, fh.close


def cmd_play_game(args):
    """Play AI vs AI games and report statistics."""
    from draughts.game.headless import HeadlessGame

    wins = {Color.BLACK: 0, Color.WHITE: 0, None: 0}
    reasons: dict[str, int] = {}
    total_ply = 0
    total_time = 0.0

    heartbeat, close_hb = _open_heartbeat(args.heartbeat)

    try:
        for i in range(args.games):
            t0 = time.perf_counter()
            game = HeadlessGame(difficulty=args.difficulty, depth=args.depth)
            result = game.play_full_game(
                max_ply=args.max_ply,
                move_timeout=args.move_timeout,
                game_timeout=args.game_timeout,
                quiet_move_limit=args.quiet_limit,
                quiet_move_limit_endgame=args.quiet_limit_endgame,
                heartbeat=heartbeat,
            )
            dt = time.perf_counter() - t0

            wins[result.winner] += 1
            reasons[result.reason] = reasons.get(result.reason, 0) + 1
            total_ply += result.ply_count
            total_time += dt

            if args.verbose:
                winner_str = "draw" if result.winner is None else result.winner.name
                print(f"  Game {i + 1}/{args.games}: {winner_str} ({result.reason}, {result.ply_count} plies, {dt:.1f}s)")
    finally:
        close_hb()

    print(f"\n{'=' * 50}")
    print(f"  AI vs AI — {args.games} games")
    print(f"  Difficulty: {args.difficulty}, Depth: {args.depth or 'auto'}")
    print(f"{'=' * 50}")
    print(f"  Black wins: {wins[Color.BLACK]} ({wins[Color.BLACK] / args.games:.0%})")
    print(f"  White wins: {wins[Color.WHITE]} ({wins[Color.WHITE] / args.games:.0%})")
    print(f"  Draws:      {wins[None]} ({wins[None] / args.games:.0%})")
    print(f"  Avg length: {total_ply / args.games:.1f} plies")
    print(f"  Total time: {total_time:.1f}s ({total_time / args.games:.1f}s/game)")
    if reasons:
        breakdown = ", ".join(f"{k}={v}" for k, v in sorted(reasons.items()))
        print(f"  Reasons:    {breakdown}")


def cmd_analyze(args):
    """Analyze a position or the starting position."""
    from draughts.game.headless import HeadlessGame

    position = args.position
    game = HeadlessGame(position=position, auto_ai=False)

    print(f"\n  Position: {game.position_string}")
    print(f"  Turn: {game.turn.name}")
    print(f"  Board:\n{game.board}\n")

    t0 = time.perf_counter()
    analysis = game.get_ai_analysis(depth=args.depth)
    dt = time.perf_counter() - t0

    print(f"  Analysis (depth {args.depth}):")
    print(f"  Score: {analysis.score:+.2f}")
    print(f"  Legal moves: {analysis.legal_move_count}")
    if analysis.best_move:
        path_str = "->".join(Board.pos_to_notation(x, y) for x, y in analysis.best_move.path)
        print(f"  Best move: {analysis.best_move.kind} {path_str}")
    else:
        print("  Best move: None (no legal moves)")
    print(f"  Time: {dt * 1000:.1f}ms")


def cmd_test_move(args):
    """Test that AI finds a specific expected move."""
    from draughts.game.ai import _search_best_move

    board = Board(empty=True)
    board.load_from_position_string(args.position)

    color = Color(args.color)
    t0 = time.perf_counter()
    move = _search_best_move(board, color, args.depth)
    dt = time.perf_counter() - t0

    if move is None:
        print(f"  FAIL: No move found ({dt * 1000:.1f}ms)")
        sys.exit(1)

    path_str = ":".join(Board.pos_to_notation(x, y) for x, y in move.path) if move.kind == "capture" else "-".join(Board.pos_to_notation(x, y) for x, y in move.path)
    expected = args.expected

    if path_str == expected:
        print(f"  PASS: AI found {path_str} ({dt * 1000:.1f}ms)")
    else:
        print(f"  FAIL: Expected {expected}, got {path_str} ({dt * 1000:.1f}ms)")
        sys.exit(1)


def cmd_tournament(args):
    """Run a tournament between two AI configurations."""
    from draughts.game.tournament import AIConfig, Tournament

    config_a = AIConfig(difficulty=args.diff_a, depth=args.depth_a, label=args.label_a or f"A(d{args.diff_a})")
    config_b = AIConfig(difficulty=args.diff_b, depth=args.depth_b, label=args.label_b or f"B(d{args.diff_b})")

    print(f"\n  Tournament: {config_a.label} vs {config_b.label}")
    print(
        f"  Games: {args.games}, max_ply: {args.max_ply}, "
        f"move_timeout: {args.move_timeout}s, game_timeout: {args.game_timeout}s, "
        f"quiet: {args.quiet_limit}/{args.quiet_limit_endgame}"
    )
    if args.tournament_timeout:
        print(f"  Tournament wall-clock limit: {args.tournament_timeout}s")
    print()

    heartbeat, close_hb = _open_heartbeat(args.heartbeat)

    try:
        t = Tournament(
            config_a=config_a,
            config_b=config_b,
            games=args.games,
            max_ply=args.max_ply,
            move_timeout=args.move_timeout,
            game_timeout=args.game_timeout,
            quiet_move_limit=args.quiet_limit,
            quiet_move_limit_endgame=args.quiet_limit_endgame,
            tournament_timeout=args.tournament_timeout,
            heartbeat=heartbeat,
            verbose=args.verbose,
        )
        result = t.run()
    finally:
        close_hb()

    print(f"\n{result.summary()}")

    # Termination breakdown
    reasons: dict[str, int] = {}
    for g in result.games:
        reasons[g.reason] = reasons.get(g.reason, 0) + 1
    if reasons:
        breakdown = ", ".join(f"{k}={v}" for k, v in sorted(reasons.items()))
        print(f"  Reasons: {breakdown}")


def cmd_replay(args):
    """Replay a saved game with move-by-move analysis."""
    from draughts.game.ai import evaluate_position
    from draughts.game.save import load_game

    gs = load_game(args.file)
    print(f"\n  Replaying: {args.file}")
    print(f"  Positions: {len(gs.positions)}")
    print()

    for i in range(len(gs.positions)):
        board = Board(empty=True)
        board.load_from_position_string(gs.positions[i])

        turn = Color.WHITE if i % 2 == 0 else Color.BLACK
        score = evaluate_position(board.grid, turn)

        if args.verbose:
            print(f"  Ply {i}: {turn.name}, eval={score:+.2f}")
            if i > 0:
                prev = Board(empty=True)
                prev.load_from_position_string(gs.positions[i - 1])
                # Show what changed
                b_count = board.count_pieces(Color.BLACK)
                w_count = board.count_pieces(Color.WHITE)
                print(f"         Black: {b_count}, White: {w_count}")
        else:
            indicator = "." if abs(score) < 2 else ("+" if score > 0 else "-")
            print(f"  {i:3d} {turn.name[0]} {score:+6.2f} {indicator}")

    print(f"\n  Final: {gs.positions[-1]}")


def cmd_screenshot(args):
    """Render board position to PNG."""
    from draughts.ui.renderer import render_board, render_position

    if args.position:
        img = render_position(args.position, output=args.output, size=args.size)
    else:
        board = Board()
        img = render_board(board, output=args.output, size=args.size)

    print(f"  Saved: {args.output} ({img.size[0]}x{img.size[1]})")


def cmd_validate_rules(args):
    """Run validation tests for Russian draughts rules compliance."""
    from draughts.game.headless import HeadlessGame

    passed = 0
    failed = 0
    tests = []

    # Test 1: Mandatory capture
    def test_mandatory_capture():
        b = Board(empty=True)
        b.place_piece(2, 4, 1)  # BLACK at c4
        b.place_piece(3, 3, -1)  # WHITE at d5
        assert b.has_any_capture(Color.BLACK), "Should detect capture"
        captures = b.get_captures(2, 4)
        assert len(captures) > 0, "Should find capture paths"
        return True

    tests.append(("Mandatory capture detection", test_mandatory_capture))

    # Test 2: Multi-jump
    def test_multi_jump():
        b = Board(empty=True)
        b.place_piece(0, 0, 1)  # BLACK at a8
        b.place_piece(1, 1, -1)  # WHITE at b7
        b.place_piece(3, 3, -1)  # WHITE at d5
        captures = b.get_captures(0, 0)
        has_multi = any(len(p) >= 3 for p in captures)
        assert has_multi, "Should find multi-jump"
        return True

    tests.append(("Multi-jump detection", test_multi_jump))

    # Test 3: King flies
    def test_king_flying():
        b = Board(empty=True)
        b.place_piece(0, 0, 2)  # BLACK_KING at a8
        moves = b.get_valid_moves(0, 0)
        # King should be able to move multiple squares diagonally
        far_moves = [(x, y) for x, y in moves if abs(x) > 1 or abs(y) > 1]
        assert len(far_moves) > 0, "King should fly"
        return True

    tests.append(("King flying moves", test_king_flying))

    # Test 4: Pawn direction
    def test_pawn_direction():
        b = Board(empty=True)
        b.place_piece(3, 5, -1)  # WHITE at d3
        moves = b.get_valid_moves(3, 5)
        assert all(y < 5 for _, y in moves), "White pawns should move up (y decreasing)"
        b2 = Board(empty=True)
        b2.place_piece(3, 2, 1)  # BLACK at d6
        moves2 = b2.get_valid_moves(3, 2)
        assert all(y > 2 for _, y in moves2), "Black pawns should move down (y increasing)"
        return True

    tests.append(("Pawn direction", test_pawn_direction))

    # Test 5: Promotion
    def test_promotion():
        b = Board(empty=True)
        b.place_piece(3, 1, -1)  # WHITE at d7, one step from row 0
        b.execute_move(3, 1, 2, 0)  # Move to c8
        piece = b.piece_at(2, 0)
        assert piece == -2, f"White should promote to king at row 0, got {piece}"
        return True

    tests.append(("Pawn promotion", test_promotion))

    # Test 6: Promotion during capture
    def test_promotion_capture():
        b = Board(empty=True)
        b.place_piece(3, 1, -1)  # WHITE at d7
        b.place_piece(2, 0, 0)  # empty at c8
        b.place_piece(4, 1, 1)  # BLACK at e7 (not directly capturable)
        # Set up: white at e3 captures d2 and promotes
        b2 = Board(empty=True)
        b2.place_piece(5, 6, -1)  # WHITE at f2
        b2.place_piece(4, 7, 0)  # empty at e1 (promotion row for white)
        b2.place_piece(6, 7, 1)  # BLACK at g1
        captures = b2.get_captures(5, 6)
        # Check if any capture leads to promotion (landing on row 0 for white... actually row 7 is bottom)
        # WHITE promotes at row 0
        # f2 (5,6) captures g1 (6,7)? No, landing at (7, 8) would be out of bounds
        # Let's use a cleaner setup
        b3 = Board(empty=True)
        b3.place_piece(1, 2, -1)  # WHITE at b6
        b3.place_piece(2, 1, 1)   # BLACK at c7
        captures = b3.get_captures(1, 2)
        if captures:
            path = captures[0]
            b3.execute_capture_path(path)
            # Should promote at row 0
            fx, fy = path[-1]
            piece = b3.piece_at(fx, fy)
            assert abs(piece) == 2, f"Should promote during capture, got {piece}"
        return True

    tests.append(("Promotion during capture", test_promotion_capture))

    # Test 7: Board boundaries
    def test_boundaries():
        b = Board(empty=True)
        b.place_piece(0, 0, 2)  # BLACK_KING at a8 (corner)
        moves = b.get_valid_moves(0, 0)
        for x, y in moves:
            assert 0 <= x < 8 and 0 <= y < 8, f"Move out of bounds: ({x}, {y})"
        captures = b.get_captures(0, 0)
        for path in captures:
            for x, y in path:
                assert 0 <= x < 8 and 0 <= y < 8, f"Capture out of bounds: ({x}, {y})"
        return True

    tests.append(("Board boundary check", test_boundaries))

    # Test 8: No moves on light squares
    def test_dark_squares_only():
        b = Board()
        for y in range(8):
            for x in range(8):
                if x % 2 == y % 2:  # light square
                    assert b.piece_at(x, y) == 0, f"Piece on light square ({x}, {y})"
        return True

    tests.append(("Pieces only on dark squares", test_dark_squares_only))

    # Test 9: Full game doesn't crash
    def test_full_game():
        game = HeadlessGame(difficulty=1, depth=3)
        result = game.play_full_game(max_ply=100)
        assert result is not None
        assert result.ply_count > 0
        return True

    tests.append(("Full AI game completes", test_full_game))

    # Run all tests
    print(f"\n{'=' * 50}")
    print("  Russian Draughts Rules Validation")
    print(f"{'=' * 50}\n")

    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"  Results: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'=' * 50}")

    if failed > 0:
        sys.exit(1)


def cmd_play_opening(args):
    """Play an opening sequence then let AI continue."""
    from draughts.game.headless import HeadlessGame

    game = HeadlessGame(difficulty=args.difficulty, depth=args.depth, auto_ai=False)

    # Parse moves: "c3-d4 f6-e5 b2-c3"
    move_strs = args.moves.split()
    # Strip move numbers like "1." "2."
    move_strs = [m for m in move_strs if not m.endswith(".")]

    print(f"\n  Playing opening: {' '.join(move_strs)}")
    print(f"  Then AI continues at depth {args.depth or 'auto'}")
    print()

    for move_str in move_strs:
        if game.is_over:
            break

        if ":" in move_str:
            # Capture path
            parts = move_str.split(":")
            positions = [Board.notation_to_pos(p) for p in parts]
            record = game.make_capture(positions)
        elif "-" in move_str:
            parts = move_str.split("-")
            record = game.make_move(parts[0], parts[1])
        else:
            print(f"  ERROR: Cannot parse move '{move_str}'")
            sys.exit(1)

        if record is None:
            print(f"  ERROR: Invalid move '{move_str}' at ply {game.ply_count}")
            sys.exit(1)

        print(f"  {game.ply_count}. {record.color.name}: {record.notation} (eval: {record.eval_after:+.2f})")

    # Switch to AI
    print("\n  --- AI takes over ---\n")
    # Set both engines
    from draughts.game.ai import AIEngine
    game._engines[Color.BLACK] = AIEngine(difficulty=args.difficulty, color=Color.BLACK, search_depth=args.depth)
    game._engines[Color.WHITE] = AIEngine(difficulty=args.difficulty, color=Color.WHITE, search_depth=args.depth)

    while not game.is_over and game.ply_count < args.max_ply:
        record = game.make_ai_move()
        if record is None:
            break
        if args.verbose:
            print(f"  {game.ply_count}. {record.color.name}: {record.notation} (eval: {record.eval_after:+.2f})")

    result = game.result
    if result:
        winner_str = "draw" if result.winner is None else result.winner.name
        print(f"\n  Result: {winner_str} ({result.reason}, {result.ply_count} plies)")
    else:
        print(f"\n  Game stopped at ply {game.ply_count}")


def cmd_pdn_info(args):
    """Show info about a PDN file."""
    from draughts.game.pdn import load_pdn_file

    games = load_pdn_file(args.file)
    print(f"\n  PDN file: {args.file}")
    print(f"  Games: {len(games)}\n")

    for i, game in enumerate(games):
        print(f"  Game {i + 1}:")
        print(f"    Event: {game.event}")
        print(f"    White: {game.white}")
        print(f"    Black: {game.black}")
        print(f"    Result: {game.result}")
        print(f"    Moves: {len(game.moves)}")
        if game.moves:
            preview = " ".join(game.moves[:6])
            if len(game.moves) > 6:
                preview += " ..."
            print(f"    Preview: {preview}")
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dev",
        description="Developer tools for draughts — testing, analysis, and automation",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # --- play-game ---
    p = sub.add_parser("play-game", help="Run AI vs AI games")
    p.add_argument("--games", "-g", type=int, default=10, help="Number of games (default: 10)")
    p.add_argument("--difficulty", "-d", type=int, default=2, help="AI difficulty 1-3 (default: 2)")
    p.add_argument("--depth", type=int, default=0, help="Search depth (0=auto)")
    p.add_argument("--max-ply", type=int, default=200, help="Max plies per game (default: 200)")
    p.add_argument("--move-timeout", type=float, default=5.0, help="Max seconds per AI move (default: 5, 0=off)")
    p.add_argument("--game-timeout", type=float, default=120.0, help="Max seconds per game wall-clock (default: 120, 0=off)")
    p.add_argument("--quiet-limit", type=int, default=40, help="Draw after N half-moves without capture in middlegame (default: 40, 0=off)")
    p.add_argument("--quiet-limit-endgame", type=int, default=15, help="Same but when <=6 pieces left (default: 15, 0=off)")
    p.add_argument("--heartbeat", default=None, help="Append per-move heartbeat log to this file")
    p.add_argument("--verbose", "-v", action="store_true")

    # --- analyze ---
    p = sub.add_parser("analyze", help="Analyze a position")
    p.add_argument("--position", "-p", default=None, help="32-char position string (default: starting)")
    p.add_argument("--depth", type=int, default=6, help="Search depth (default: 6)")

    # --- test-move ---
    p = sub.add_parser("test-move", help="Verify AI finds expected move")
    p.add_argument("--position", "-p", required=True, help="32-char position string")
    p.add_argument("--expected", "-e", required=True, help="Expected move notation (e.g. c3-d4)")
    p.add_argument("--color", "-c", default="w", choices=["b", "w"], help="Side to move")
    p.add_argument("--depth", type=int, default=6, help="Search depth")

    # --- tournament ---
    p = sub.add_parser("tournament", help="Tournament between two AI configs")
    p.add_argument("--games", "-g", type=int, default=20, help="Number of games")
    p.add_argument("--diff-a", type=int, default=2, help="Difficulty for A")
    p.add_argument("--depth-a", type=int, default=0, help="Depth for A")
    p.add_argument("--diff-b", type=int, default=2, help="Difficulty for B")
    p.add_argument("--depth-b", type=int, default=0, help="Depth for B")
    p.add_argument("--label-a", default="", help="Label for A")
    p.add_argument("--label-b", default="", help="Label for B")
    p.add_argument("--max-ply", type=int, default=200, help="Max plies per game")
    p.add_argument("--move-timeout", type=float, default=5.0, help="Max seconds per AI move (default: 5, 0=off)")
    p.add_argument("--game-timeout", type=float, default=120.0, help="Max seconds per game wall-clock (default: 120, 0=off)")
    p.add_argument("--quiet-limit", type=int, default=40, help="Middlegame quiet-move limit (default: 40, 0=off)")
    p.add_argument("--quiet-limit-endgame", type=int, default=15, help="Endgame quiet-move limit (default: 15, 0=off)")
    p.add_argument("--tournament-timeout", type=float, default=0.0, help="Overall tournament wall-clock limit in seconds (0=off)")
    p.add_argument("--heartbeat", default=None, help="Append per-move heartbeat log to this file")
    p.add_argument("--verbose", "-v", action="store_true")

    # --- replay ---
    p = sub.add_parser("replay", help="Replay a saved game")
    p.add_argument("file", help="JSON save file")
    p.add_argument("--verbose", "-v", action="store_true")

    # --- screenshot ---
    p = sub.add_parser("screenshot", help="Render board to PNG")
    p.add_argument("--position", "-p", default=None, help="32-char position string")
    p.add_argument("--output", "-o", default="board.png", help="Output file (default: board.png)")
    p.add_argument("--size", "-s", type=int, default=480, help="Image size (default: 480)")

    # --- validate-rules ---
    sub.add_parser("validate-rules", help="Validate Russian draughts rules")

    # --- play-opening ---
    p = sub.add_parser("play-opening", help="Play opening then AI continues")
    p.add_argument("moves", help="Opening moves: 'c3-d4 f6-e5 b2-c3'")
    p.add_argument("--difficulty", "-d", type=int, default=2, help="AI difficulty")
    p.add_argument("--depth", type=int, default=0, help="Search depth")
    p.add_argument("--max-ply", type=int, default=200, help="Max plies")
    p.add_argument("--verbose", "-v", action="store_true")

    # --- pdn-info ---
    p = sub.add_parser("pdn-info", help="Show PDN file info")
    p.add_argument("file", help="PDN file path")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "play-game": cmd_play_game,
        "analyze": cmd_analyze,
        "test-move": cmd_test_move,
        "tournament": cmd_tournament,
        "replay": cmd_replay,
        "screenshot": cmd_screenshot,
        "validate-rules": cmd_validate_rules,
        "play-opening": cmd_play_opening,
        "pdn-info": cmd_pdn_info,
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        cmd_fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
