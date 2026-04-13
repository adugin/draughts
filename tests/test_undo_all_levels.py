"""Tests: undo is available at all difficulty levels (D17).

Verifies that undo_move() and can_undo work regardless of the
difficulty setting -- the old level-1-only gate has been removed.
"""

from __future__ import annotations

import pytest
from draughts.app.controller import GameController
from draughts.game.board import Board


def _make_controller(difficulty: int) -> GameController:
    """Create a GameController with two plies already played."""
    ctrl = GameController()
    ctrl.settings.difficulty = difficulty

    # Make a real move: pick any valid move for white
    b = ctrl.board.copy()
    valid = None
    for y in range(8):
        for x in range(8):
            piece = b.piece_at(x, y)
            if Board.is_white(piece):
                moves = b.get_valid_moves(x, y)
                if moves:
                    tx, ty = moves[0]
                    valid = (x, y, tx, ty)
                    break
        if valid:
            break

    assert valid is not None, "No valid white move found"
    sx, sy, tx, ty = valid
    ctrl.board.execute_move(sx, sy, tx, ty)
    ctrl._positions.append(ctrl.board.to_position_string())
    ctrl._ply_count += 1

    # Simulate a second ply (black move)
    b2 = ctrl.board.copy()
    valid2 = None
    for y in range(8):
        for x in range(8):
            piece = b2.piece_at(x, y)
            if Board.is_black(piece):
                moves = b2.get_valid_moves(x, y)
                if moves:
                    tx2, ty2 = moves[0]
                    valid2 = (x, y, tx2, ty2)
                    break
        if valid2:
            break

    if valid2:
        sx2, sy2, tx2, ty2 = valid2
        ctrl.board.execute_move(sx2, sy2, tx2, ty2)
        ctrl._positions.append(ctrl.board.to_position_string())
        ctrl._ply_count += 1

    return ctrl


@pytest.mark.parametrize("difficulty", [1, 2, 3, 4, 5, 6])
def test_can_undo_at_all_levels(difficulty):
    """can_undo must be True after 2+ plies regardless of difficulty."""
    ctrl = _make_controller(difficulty)
    assert ctrl._ply_count >= 2, f"Setup failed: only {ctrl._ply_count} plies"
    assert ctrl.can_undo is True, f"can_undo False at difficulty={difficulty}"


@pytest.mark.parametrize("difficulty", [1, 2, 3, 4, 5, 6])
def test_undo_move_works_at_all_levels(difficulty):
    """undo_move() must restore the board position at every difficulty level."""
    ctrl = _make_controller(difficulty)
    ply_before = ctrl._ply_count

    ctrl.undo_move()

    assert ctrl._ply_count == ply_before - 2, (
        f"ply_count not decremented by 2 at difficulty={difficulty}"
    )
    # Board must have been rolled back to the earlier position
    assert ctrl.board.to_position_string() == ctrl._positions[-1]


def test_can_undo_false_when_no_plies():
    """can_undo is False when fewer than 2 plies have been played."""
    ctrl = GameController()
    ctrl.settings.difficulty = 1
    assert ctrl.can_undo is False

    ctrl.settings.difficulty = 6
    assert ctrl.can_undo is False


def test_undo_no_op_when_ai_thinking(monkeypatch):
    """undo_move must be a no-op when the AI thread is active."""
    ctrl = _make_controller(difficulty=3)
    # Simulate AI running
    monkeypatch.setattr(ctrl, "_ai_thread", object())
    ply_before = ctrl._ply_count
    ctrl.undo_move()
    assert ctrl._ply_count == ply_before  # unchanged
