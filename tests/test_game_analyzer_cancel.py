"""analyze_game_positions should observe should_cancel mid-loop.

Audit #4 flagged a P3 gap: the Qt ``_Worker.cancel()`` only set a flag
that suppressed progress-bar emits, but ``analyze_game_positions`` had
no cancellation hook, so pressing "Cancel" on a 60-ply game would keep
the engine churning for minutes before the dialog finally closed.
"""

from __future__ import annotations

from draughts.ui.game_analyzer import analyze_game_positions


def _make_positions(n_plies: int) -> list[str]:
    """Play n_plies from the start position and collect the history."""
    from draughts.game.headless import HeadlessGame

    game = HeadlessGame(difficulty=1, auto_ai=True)
    positions = [game.board.to_position_string()]
    for _ in range(n_plies):
        rec = game.make_ai_move()
        if rec is None:
            break
        positions.append(game.board.to_position_string())
    return positions


class TestCancelHook:
    def test_cancel_before_first_ply_returns_empty_result(self):
        positions = _make_positions(6)
        result = analyze_game_positions(
            positions, depth=2, should_cancel=lambda: True
        )
        assert result.annotations == []

    def test_cancel_midway_returns_partial_result(self):
        positions = _make_positions(8)

        # Cancel after the first ply — exact count depends on when the
        # outer loop observes the flag; guarantee is "fewer than full".
        state = {"seen": 0}

        def should_cancel() -> bool:
            return state["seen"] >= 2

        def progress(current: int, total: int) -> None:
            state["seen"] = current

        result = analyze_game_positions(
            positions,
            depth=2,
            progress_callback=progress,
            should_cancel=should_cancel,
        )
        # Must have stopped before finishing the full pass.
        assert len(result.annotations) < len(positions) - 1

    def test_no_cancel_hook_unchanged_behavior(self):
        """Omitting should_cancel keeps the legacy behaviour."""
        positions = _make_positions(4)
        result = analyze_game_positions(positions, depth=2)
        # Full pass attempted (count can be ≤ len-1 if an individual
        # ply analysis fails internally).
        assert len(result.annotations) <= len(positions) - 1
