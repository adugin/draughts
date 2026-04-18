"""Tests for M5.b-mini — controller preserves PDN variation tree
across a load → save round-trip, and clears it on any new move.
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

    monkeypatch.setattr(GameController, "_start_computer_turn", lambda self: None)
    return GameController()


# ---------------------------------------------------------------------------
# Tree storage
# ---------------------------------------------------------------------------


def _write_pdn_with_variation(path: Path) -> None:
    pdn = """[Event "?"]
[Result "*"]
[GameType "25,W,8,8,A1,0"]

1. 23-18 9-13 (1... 12-16 2. 27-23) 2. 18-15 5-9 *
"""
    path.write_text(pdn, encoding="utf-8")


def test_load_pdn_stores_tree(controller, tmp_path):
    """Loading a PDN with variations populates controller._game_tree."""
    p = tmp_path / "variation.pdn"
    _write_pdn_with_variation(p)
    controller.load_game_from_pdn(str(p))
    assert controller._game_tree is not None
    # Variation is preserved
    root_children = [c.move for c in controller._game_tree.root.children]
    assert root_children[0] == "23-18"
    # Second ply under 23-18: main "9-13" + alt "12-16"
    after_w1 = controller._game_tree.root.children[0]
    assert [c.move for c in after_w1.children] == ["9-13", "12-16"]


def test_save_after_load_roundtrips_variations(controller, tmp_path):
    """load → save preserves the variation structure."""
    p = tmp_path / "variation.pdn"
    _write_pdn_with_variation(p)
    controller.load_game_from_pdn(str(p))

    out = tmp_path / "roundtrip.pdn"
    controller.save_game_as_pdn(str(out))
    text = out.read_text(encoding="utf-8")
    compact = " ".join(text.split())
    # The alternative 1... 12-16 2. 27-23 must appear in the output
    assert "12-16" in compact
    assert "27-23" in compact
    # Opening paren present (variation emitted)
    assert "(" in text and ")" in text


def test_tree_cleared_after_new_move(controller, tmp_path):
    """Making a fresh move after load invalidates the imported tree."""
    p = tmp_path / "variation.pdn"
    _write_pdn_with_variation(p)
    controller.load_game_from_pdn(str(p))
    assert controller._game_tree is not None

    # Invoke the handler that finalises a player move (without actually
    # applying a board move — the test only verifies the tree-clearing
    # side effect).
    controller._finish_player_move("x-y")
    assert controller._game_tree is None


def test_new_game_clears_tree(controller, tmp_path):
    """new_game must reset the imported tree so it doesn't leak between games."""
    p = tmp_path / "variation.pdn"
    _write_pdn_with_variation(p)
    controller.load_game_from_pdn(str(p))
    assert controller._game_tree is not None

    controller.new_game()
    assert controller._game_tree is None


def test_save_without_tree_uses_flat_format(controller, tmp_path):
    """Without an imported tree, save falls back to the legacy flat layout
    (no parens, byte-identical to pre-M5 output)."""
    # Play a couple of plies by mutating positions directly.
    from draughts.game.board import Board

    b = Board()
    controller._positions = [b.to_position_string()]
    # Simulate one move: white 23-18 → internal (4,5) to (3,4)
    b.execute_move(4, 5, 3, 4)
    controller._positions.append(b.to_position_string())
    controller._ply_count = 1
    controller._game_tree = None

    out = tmp_path / "flat.pdn"
    controller.save_game_as_pdn(str(out))
    text = out.read_text(encoding="utf-8")
    assert "(" not in text  # no variations
    assert "{" not in text  # no comments
