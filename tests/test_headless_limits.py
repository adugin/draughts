"""Tests for dev-mode hard limits in HeadlessGame / Tournament.

These exist so the class of bug that once hung an agent for an hour
(infinite AI vs AI endgame + unkillable threaded timeout) cannot recur
silently — every limit below has a dedicated test that must stay green.
"""

from __future__ import annotations

import time

from draughts.config import Color
from draughts.game.ai import AIEngine
from draughts.game.board import Board
from draughts.game.headless import HeadlessGame
from draughts.game.tournament import AIConfig, Tournament

# ---------------------------------------------------------------------------
# Per-move cooperative cancellation
# ---------------------------------------------------------------------------


def test_find_move_respects_past_deadline_and_returns_legal_move():
    """With a deadline already in the past, search must still return a
    legal move (from the completed depth-1 sweep) rather than None."""
    engine = AIEngine(difficulty=3, color=Color.WHITE, search_depth=8)
    board = Board()
    past = time.perf_counter() - 1.0
    move = engine.find_move(board.copy(), deadline=past)
    assert move is not None
    assert move.kind in ("move", "capture")
    assert len(move.path) >= 2


def test_find_move_cancellation_bounds_wall_clock():
    """A very small deadline must bound find_move wall-clock to a small
    multiple of the budget. A depth-1 sweep always completes first, so
    total time is budget + one-depth-1-sweep."""
    engine = AIEngine(difficulty=3, color=Color.WHITE, search_depth=10)
    board = Board()
    t0 = time.perf_counter()
    move = engine.find_move(board.copy(), deadline=time.perf_counter() + 0.05)
    elapsed = time.perf_counter() - t0
    assert move is not None
    # Generous upper bound — depth 1 from the opening is well under 1s.
    assert elapsed < 2.0, f"search overran deadline: {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# HeadlessGame.play_full_game limits
# ---------------------------------------------------------------------------


def test_max_ply_limit_terminates():
    game = HeadlessGame(difficulty=1, depth=3)
    result = game.play_full_game(max_ply=10, move_timeout=5.0)
    assert result is not None
    # Max-ply can be reached, or the game could end earlier on its own.
    assert result.ply_count <= 10
    if result.reason == "draw_max_ply":
        assert result.ply_count == 10


def test_game_timeout_terminates():
    """A pathologically small game_timeout must stop the game fast."""
    game = HeadlessGame(difficulty=2, depth=5)
    t0 = time.perf_counter()
    result = game.play_full_game(
        max_ply=500, move_timeout=5.0, game_timeout=0.3
    )
    elapsed = time.perf_counter() - t0
    assert result is not None
    # Must terminate in well under 5 seconds even though max_ply is huge.
    assert elapsed < 5.0, f"game_timeout did not fire: {elapsed:.2f}s"


def test_quiet_move_limit_terminates_king_dance():
    """Two lone kings on far diagonals will shuffle without capturing.
    The quiet-move counter must fire and end the game as draw_quiet."""
    game = HeadlessGame(difficulty=1, depth=3, auto_ai=False)
    b = Board(empty=True)
    b.place_piece(0, 0, 2)   # BLACK_KING at a8
    b.place_piece(7, 7, -2)  # WHITE_KING at h1
    game._board = b
    game._position_history = [b.to_position_string()]
    game._position_counts = {b.to_position_string(): 1}
    game._engines = {
        Color.BLACK: AIEngine(difficulty=1, color=Color.BLACK, search_depth=3),
        Color.WHITE: AIEngine(difficulty=1, color=Color.WHITE, search_depth=3),
    }

    result = game.play_full_game(
        max_ply=500,
        move_timeout=2.0,
        game_timeout=30.0,
        quiet_move_limit=100,
        quiet_move_limit_endgame=6,  # tight — with 2 kings this must fire
    )
    assert result is not None
    # Either the AI finds a forced repetition first (also fine — draw),
    # or our quiet limit fires. What must NOT happen is running to
    # max_ply=500.
    assert result.reason in ("draw_quiet", "draw_repetition", "draw_max_ply")
    assert result.ply_count < 500
    # The main claim: with a 6-ply endgame quiet limit, we terminate fast.
    assert result.ply_count <= 50


def test_heartbeat_called_every_move():
    calls: list[int] = []

    def hb(game, record):
        calls.append(record.ply)

    game = HeadlessGame(difficulty=1, depth=2)
    result = game.play_full_game(
        max_ply=20, move_timeout=5.0, heartbeat=hb
    )
    assert len(calls) == result.ply_count
    assert calls == list(range(result.ply_count))


def test_heartbeat_exception_does_not_break_game():
    """A broken heartbeat must never take the game down."""
    def hb(game, record):
        raise RuntimeError("boom")

    game = HeadlessGame(difficulty=1, depth=2)
    result = game.play_full_game(
        max_ply=5, move_timeout=5.0, heartbeat=hb
    )
    assert result is not None
    assert result.ply_count > 0


# ---------------------------------------------------------------------------
# Tournament wall-clock
# ---------------------------------------------------------------------------


def test_tournament_wall_clock_stops_scheduling():
    """tournament_timeout must stop scheduling new games when elapsed."""
    t = Tournament(
        config_a=AIConfig(difficulty=1, depth=3, label="A"),
        config_b=AIConfig(difficulty=1, depth=3, label="B"),
        games=100,
        max_ply=30,
        move_timeout=1.0,
        game_timeout=10.0,
        quiet_move_limit=20,
        quiet_move_limit_endgame=6,
        tournament_timeout=2.0,
        verbose=False,
    )
    t0 = time.perf_counter()
    result = t.run()
    elapsed = time.perf_counter() - t0
    # Must not run all 100 games in 2 seconds.
    assert len(result.games) < 100
    # Must stop near the budget. Allow one in-flight game to finish plus
    # some slack for CI and Windows timing variance. 20 s is ~10x the
    # tournament_timeout; any real hang would overshoot by much more.
    assert elapsed < 25.0, f"tournament overran: {elapsed:.2f}s"
