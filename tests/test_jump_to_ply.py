"""Tests for controller.jump_to_ply — HIGH-01 fix.

The audit found that jump_to_ply hardcoded ``start_color = Color.WHITE``,
which breaks FEN-loaded PDN games where Black moves first. Verified here
for both normal (White-first) and setup-loaded (Black-first) cases.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


_qt_app = None


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    global _qt_app
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    _qt_app = QApplication.instance() or QApplication(sys.argv)
    yield _qt_app


@pytest.fixture
def controller(monkeypatch):
    from draughts.app.controller import GameController

    # Silence the AI thread start so jump_to_ply isn't blocked on is_thinking.
    monkeypatch.setattr(GameController, "_start_computer_turn", lambda self: None)
    return GameController()


def test_new_game_starts_with_white(controller):
    from draughts.config import Color

    assert controller._game_start_color == Color.WHITE
    assert controller.current_turn == Color.WHITE


def test_jump_to_ply_0_on_white_first_game(controller):
    """Sanity check: plain new game starts white-to-move on ply 0."""
    from draughts.config import Color

    controller.jump_to_ply(0)
    assert controller.current_turn == Color.WHITE


def test_jump_preserves_start_color_on_black_first_setup(controller, monkeypatch):
    """FEN-loaded black-to-move PDN: jump to ply 0 must report Black."""
    from draughts.config import Color
    from draughts.game.board import Board

    # Simulate loading a position with Black to move.
    controller.new_game_from_position(Board(), Color.BLACK)
    assert controller._game_start_color == Color.BLACK

    # Pretend a couple of plies were played — jump back to ply 0.
    pos0 = controller.board.to_position_string()
    controller._positions = [pos0, pos0, pos0]
    controller._replay_history = list(controller._positions)

    controller.jump_to_ply(0)
    assert controller.current_turn == Color.BLACK

    controller.jump_to_ply(1)
    assert controller.current_turn == Color.WHITE

    controller.jump_to_ply(2)
    assert controller.current_turn == Color.BLACK


def test_jump_respects_bounds(controller):
    """Clamping to valid ply range."""
    from draughts.config import Color
    from draughts.game.board import Board

    controller.new_game_from_position(Board(), Color.WHITE)
    controller._positions = [controller.board.to_position_string()]
    # Negative and over-size must both clamp, no IndexError.
    controller.jump_to_ply(-5)
    assert controller._ply_count == 0
    controller.jump_to_ply(9999)
    assert controller._ply_count == 0
    assert controller.current_turn == Color.WHITE


def test_load_game_from_pdn_sets_start_color(controller, tmp_path: Path):
    """Loading a PDN with Black-to-move FEN must set _game_start_color."""
    from draughts.config import Color

    pdn_text = (
        '[Event "Test"]\n[Site "?"]\n[Date "?"]\n[Round "?"]\n'
        '[White "A"]\n[Black "B"]\n[Result "*"]\n[GameType "25"]\n'
        '[SetUp "1"]\n'
        '[FEN "B:W24:B1"]\n'  # Black to move
        "\n*\n"
    )
    pdn_path = tmp_path / "black_start.pdn"
    pdn_path.write_text(pdn_text, encoding="utf-8")
    controller.load_game_from_pdn(str(pdn_path))
    assert controller._game_start_color == Color.BLACK
    assert controller.current_turn == Color.BLACK

    # Emulate having played one ply — jump back and forth.
    pos0 = controller.board.to_position_string()
    controller._positions = [pos0, pos0]
    controller._replay_history = list(controller._positions)

    controller.jump_to_ply(0)
    assert controller.current_turn == Color.BLACK

    controller.jump_to_ply(1)
    assert controller.current_turn == Color.WHITE


def test_load_saved_game_resets_start_color_after_black_first_pdn(
    controller, tmp_path: Path
):
    """Regression: loading a JSON save after a black-first PDN must reset
    _game_start_color back to White.

    Previously the controller never cleared _game_start_color on JSON
    load, so a prior black-to-move PDN left it at BLACK and subsequent
    jump_to_ply calls on the JSON game returned wrong colours, which
    in turn corrupted PDN re-export of the loaded game.
    """
    import json

    from draughts.config import Color
    from draughts.game.board import Board

    # 1) Load a black-first PDN to poison _game_start_color.
    pdn_text = (
        '[Event "Test"]\n[Site "?"]\n[Date "?"]\n[Round "?"]\n'
        '[White "A"]\n[Black "B"]\n[Result "*"]\n[GameType "25"]\n'
        '[SetUp "1"]\n'
        '[FEN "B:W24:B1"]\n'
        "\n*\n"
    )
    pdn_path = tmp_path / "bstart.pdn"
    pdn_path.write_text(pdn_text, encoding="utf-8")
    controller.load_game_from_pdn(str(pdn_path))
    assert controller._game_start_color == Color.BLACK

    # 2) Load a legacy JSON save (standard starting position).
    start_board = Board()
    pos0 = start_board.to_position_string()
    data = {
        "difficulty": 2,
        "speed": 1,
        "remind": True,
        "sound_effect": False,
        "pause": 1.0,
        "invert_color": False,
        "positions": [pos0],
        "replay_positions": [pos0],
    }
    json_path = tmp_path / "g.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")
    controller.load_saved_game(str(json_path))

    # _game_start_color must now match the JSON-save convention (White first).
    assert controller._game_start_color == Color.WHITE
    assert controller.current_turn == Color.WHITE
    # And the stale game tree from the PDN must not survive either.
    assert controller._game_tree is None
