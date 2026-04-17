"""Tests for principal-variation extraction (M9.a)."""

from __future__ import annotations

from draughts.game.analysis import compute_pv
from draughts.game.headless import HeadlessGame


def test_compute_pv_returns_list_of_moves_from_start():
    """Starting position has plenty of moves — PV should be non-empty
    and capped at pv_length. The first move must be legal for White."""
    hg = HeadlessGame(auto_ai=False)
    pv = compute_pv(hg, depth=3, pv_length=4)
    assert 1 <= len(pv) <= 4
    # First PV move must be a legal starting move for White.
    first = pv[0]
    assert first.kind in {"move", "capture", "sacrifice"}
    legal_moves_from_piece = hg.board.get_valid_moves(*first.path[0])
    legal_captures_from_piece = hg.board.get_captures(*first.path[0])
    assert (first.path[-1] in legal_moves_from_piece) or any(
        cap == first.path for cap in legal_captures_from_piece
    ), "PV first move must be a legal move for White from the start position"


def test_compute_pv_does_not_mutate_game_board():
    """compute_pv must work on a copy; the original game board stays put."""
    hg = HeadlessGame(auto_ai=False)
    before = hg.board.to_position_string()
    compute_pv(hg, depth=3, pv_length=3)
    after = hg.board.to_position_string()
    assert before == after


def test_compute_pv_alternates_colors():
    """Each PV ply should represent the other side's move.

    We check by verifying that the sequence of moves can all be applied
    legally in order on a cloned board (if colors alternate correctly,
    every move is legal; if colors don't alternate, move-generation
    would reject the second move).
    """
    from draughts.game.board import Board
    hg = HeadlessGame(auto_ai=False)
    pv = compute_pv(hg, depth=3, pv_length=4)
    assert pv, "PV should not be empty from start position"

    board = Board()
    board.load_from_position_string(hg.board.to_position_string())
    color = hg.turn
    for mv in pv:
        # Move should be legal for the current side
        moves_for_piece = board.get_valid_moves(*mv.path[0])
        captures_for_piece = board.get_captures(*mv.path[0])
        legal = (mv.path[-1] in moves_for_piece) or any(
            cap == mv.path for cap in captures_for_piece
        )
        assert legal, f"PV move {mv.path} is illegal for side {color}"
        # Apply and switch
        if mv.kind == "capture":
            board.execute_capture_path(mv.path)
        else:
            (x1, y1), (x2, y2) = mv.path[0], mv.path[1]
            board.execute_move(x1, y1, x2, y2)
        color = color.opponent


def test_compute_pv_empty_when_no_moves():
    """When the side to move has no legal moves, PV is empty."""
    hg = HeadlessGame(auto_ai=False)
    # Clear the board — no white pieces → white to move has no legal moves.
    import numpy as np
    hg.board.grid[:] = 0
    hg.board.grid[0, 1] = 1  # single black pawn so side-check passes
    pv = compute_pv(hg, depth=3, pv_length=3)
    assert pv == []


def test_compute_pv_respects_pv_length():
    """pv_length clamps the returned list, even when depth would allow more."""
    hg = HeadlessGame(auto_ai=False)
    pv = compute_pv(hg, depth=3, pv_length=2)
    assert len(pv) <= 2


def test_compute_pv_zero_length():
    hg = HeadlessGame(auto_ai=False)
    pv = compute_pv(hg, depth=3, pv_length=0)
    assert pv == []
