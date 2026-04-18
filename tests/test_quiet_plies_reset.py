"""FMJD no-progress counter must reset on pawn moves, not only captures.

The no-progress rule (30 full moves without captures or pawn advances)
tracks _quiet_plies. Prior implementations reset only on captures, so a
long sequence of pawn moves with no captures incorrectly accumulated
toward the 60-half-move threshold and could silently terminate a live
game as a draw.

This module exercises the reset logic for both the headless engine and
the GUI controller without requiring a QApplication.
"""

from __future__ import annotations

import pytest

from draughts.config import BLACK, BLACK_KING, Color, WHITE, WHITE_KING
from draughts.game.board import Board
from draughts.game.headless import HeadlessGame


# ---------------------------------------------------------------------------
# HeadlessGame
# ---------------------------------------------------------------------------


def test_headless_pawn_move_resets_quiet_plies():
    hg = HeadlessGame(auto_ai=False)
    hg._quiet_plies = 40  # artificially high — simulate long king dance
    # First player move from standard position — a pawn moves, so the
    # counter must reset to 0.
    rec = hg.make_move("c3", "b4")
    assert rec is not None
    assert rec.kind == "move"
    assert hg._quiet_plies == 0


def test_headless_king_slide_does_not_reset_quiet_plies():
    """King moves on an otherwise drawable endgame must grow the counter."""
    # 2K vs 2K endgame — avoid Petrov by using 4 kings — positioned so
    # White has a legal quiet move (d6 slides to c7 / e7 / etc).
    b = Board(empty=True)
    b.grid[0, 1] = BLACK_KING   # b8
    b.grid[0, 7] = BLACK_KING   # h8 (dark square: x=7,y=0)
    b.grid[2, 3] = WHITE_KING   # d6
    b.grid[7, 0] = WHITE_KING   # a1

    hg = HeadlessGame(position=b.to_position_string(), auto_ai=False)
    hg._turn = Color.WHITE
    hg._quiet_plies = 10
    before = hg._quiet_plies
    rec = hg.make_move("d6", "c7")
    assert rec is not None, "c7 should be reachable from d6 in this setup"
    assert rec.kind == "move"
    assert hg._quiet_plies == before + 1


def test_headless_capture_resets_quiet_plies():
    b = Board(empty=True)
    b.grid[5, 2] = WHITE   # c3
    b.grid[4, 3] = BLACK   # d4 — enemy directly in capture range
    hg = HeadlessGame(position=b.to_position_string(), auto_ai=False)
    hg._turn = Color.WHITE
    hg._quiet_plies = 40
    rec = hg.make_move("c3", "e5")
    assert rec is not None
    assert rec.kind == "capture"
    assert hg._quiet_plies == 0


# ---------------------------------------------------------------------------
# GameController (headless — via its programmatic API)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    pytest.importorskip("PyQt6.QtCore")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def controller(monkeypatch):
    """Headless controller — never spawns the AI thread."""
    from draughts.app.controller import GameController
    monkeypatch.setattr(GameController, "_start_computer_turn", lambda self: None)
    return GameController()


def test_controller_pawn_move_resets_quiet_plies(controller):
    controller.new_game()
    controller._quiet_plies = 40
    # c3-b4 is legal from the starting position for White.
    sx, sy = Board.notation_to_pos("c3")
    tx, ty = Board.notation_to_pos("b4")
    controller._try_normal_move(sx, sy, tx, ty)
    assert controller._quiet_plies == 0


def test_controller_king_slide_does_not_reset_quiet_plies(controller):
    # 2K vs 2K endgame so kings can slide freely without captures.
    b = Board(empty=True)
    b.grid[0, 1] = BLACK_KING
    b.grid[0, 7] = BLACK_KING
    b.grid[2, 3] = WHITE_KING
    b.grid[7, 0] = WHITE_KING
    controller.board.load_from_position_string(b.to_position_string())
    controller._current_turn = Color.WHITE
    controller._player_color = Color.WHITE
    controller._quiet_plies = 10
    before = controller._quiet_plies

    sx, sy = Board.notation_to_pos("d6")
    tx, ty = Board.notation_to_pos("c7")
    controller._try_normal_move(sx, sy, tx, ty)
    assert controller._quiet_plies == before + 1


def test_controller_capture_resets_quiet_plies(controller):
    b = Board(empty=True)
    b.grid[5, 2] = WHITE   # c3
    b.grid[4, 3] = BLACK   # d4
    controller.board.load_from_position_string(b.to_position_string())
    controller._current_turn = Color.WHITE
    controller._player_color = Color.WHITE
    controller._quiet_plies = 40

    sx, sy = Board.notation_to_pos("c3")
    tx, ty = Board.notation_to_pos("e5")
    controller._try_capture_move(sx, sy, tx, ty)
    assert controller._quiet_plies == 0


# ---------------------------------------------------------------------------
# kings_only_plies — orthogonal counter, confirm it still tracks correctly.
# ---------------------------------------------------------------------------


def test_headless_kings_only_counter_advances_with_no_pawns():
    b = Board(empty=True)
    b.grid[0, 1] = BLACK_KING
    b.grid[0, 7] = BLACK_KING
    b.grid[2, 3] = WHITE_KING
    b.grid[7, 0] = WHITE_KING
    hg = HeadlessGame(position=b.to_position_string(), auto_ai=False)
    hg._turn = Color.WHITE
    hg._kings_only_plies = 5
    rec = hg.make_move("d6", "c7")
    assert rec is not None
    # Kings-only counter increments by one because no pawns were
    # introduced and none existed to begin with.
    assert hg._kings_only_plies == 6


def test_headless_kings_only_counter_resets_when_pawns_present():
    hg = HeadlessGame(auto_ai=False)  # full starting position
    hg._kings_only_plies = 10
    rec = hg.make_move("c3", "b4")
    assert rec is not None
    # Pawns are present → kings-only counter resets.
    assert hg._kings_only_plies == 0
