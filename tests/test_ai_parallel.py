"""Parallel-search correctness test.

Validates that the SearchContext refactor delivers on the promise of safe
parallelism: two threads each running AIEngine.find_move() on different
boards must both return valid, non-None moves without crashing or corrupting
each other's results.

Before SearchContext (when _tt, _killers, _history, _last_search_score were
module-level globals), this test would be flaky: concurrent writes to those
globals could produce None returns, score corruption, or exceptions.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from draughts.config import Color
from draughts.game.ai import AIEngine
from draughts.game.board import Board
from draughts.game.headless import HeadlessGame


def _run_find_move(engine: AIEngine, board: Board, results: list[Any], idx: int) -> None:
    """Thread target: run find_move and store result in results[idx]."""
    try:
        move = engine.find_move(board)
        results[idx] = move
    except Exception as exc:
        results[idx] = exc


class TestParallelSearch:
    """SearchContext isolation must allow concurrent AIEngine.find_move calls."""

    def _make_engine_and_board(self, color: Color, depth: int = 4):
        engine = AIEngine(difficulty=2, color=color, search_depth=depth)
        game = HeadlessGame(auto_ai=False)
        # Step the game a few plies to get different positions for each thread.
        return engine, game.board.copy()

    def test_two_threads_return_valid_moves(self):
        """Two threads running find_move simultaneously both return non-None moves."""
        engine_a = AIEngine(difficulty=2, color=Color.WHITE, search_depth=4)
        engine_b = AIEngine(difficulty=2, color=Color.BLACK, search_depth=4)

        board_a = Board()
        board_b = Board()

        results: list[Any] = [None, None]

        t1 = threading.Thread(target=_run_find_move, args=(engine_a, board_a, results, 0))
        t2 = threading.Thread(target=_run_find_move, args=(engine_b, board_b, results, 1))

        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        # Neither thread should still be alive (timeout guard)
        assert not t1.is_alive(), "Thread 1 did not finish within 30s"
        assert not t2.is_alive(), "Thread 2 did not finish within 30s"

        # Neither result should be an exception
        assert not isinstance(results[0], Exception), f"Thread 1 raised: {results[0]}"
        assert not isinstance(results[1], Exception), f"Thread 2 raised: {results[1]}"

        # Both should have found a move
        assert results[0] is not None, "Thread 1 (white) returned None"
        assert results[1] is not None, "Thread 2 (black) returned None"

        # Moves must be structurally valid
        for i, move in enumerate(results):
            assert move.kind in ("move", "capture"), f"Thread {i + 1}: invalid kind {move.kind!r}"
            assert len(move.path) >= 2, f"Thread {i + 1}: path too short {move.path}"

    def test_many_threads_no_crash(self):
        """Four threads concurrently searching the same opening position all succeed."""
        n_threads = 4
        results: list[Any] = [None] * n_threads
        threads = []

        for i in range(n_threads):
            color = Color.WHITE if i % 2 == 0 else Color.BLACK
            engine = AIEngine(difficulty=2, color=color, search_depth=3)
            board = Board()
            t = threading.Thread(target=_run_find_move, args=(engine, board, results, i))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        for i, t in enumerate(threads):
            assert not t.is_alive(), f"Thread {i} did not finish within 30s"

        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"Thread {i} raised: {result}"
            assert result is not None, f"Thread {i} returned None"
            assert result.kind in ("move", "capture"), f"Thread {i}: bad kind {result.kind!r}"

    def test_parallel_analysis_via_headless(self):
        """Two HeadlessGame.get_ai_analysis() calls in parallel return valid Analysis."""
        from draughts.game.analysis import get_ai_analysis

        results: list[Any] = [None, None]

        def run_analysis(game: HeadlessGame, idx: int) -> None:
            try:
                results[idx] = get_ai_analysis(game, depth=3)
            except Exception as exc:
                results[idx] = exc

        game_a = HeadlessGame(auto_ai=False)
        game_b = HeadlessGame(auto_ai=False)

        t1 = threading.Thread(target=run_analysis, args=(game_a, 0))
        t2 = threading.Thread(target=run_analysis, args=(game_b, 1))

        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert not t1.is_alive()
        assert not t2.is_alive()

        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"Analysis thread {i} raised: {result}"
            assert result is not None
            assert result.best_move is not None, f"Analysis thread {i}: best_move is None"
            assert result.legal_move_count == 7, f"Analysis thread {i}: wrong move count"
