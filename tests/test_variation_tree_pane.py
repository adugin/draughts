"""Tests for the Variation Tree pane (#35)."""

from __future__ import annotations

import sys

import pytest

_qt_app = None


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    global _qt_app
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    _qt_app = QApplication.instance() or QApplication(sys.argv)
    yield _qt_app


def test_pane_builds_with_none_tree():
    from draughts.ui.variation_tree import VariationTreePane

    pane = VariationTreePane()
    pane.set_tree(None)
    assert pane._tree_widget.topLevelItemCount() == 0


def test_pane_renders_linear_tree():
    from draughts.game.gametree import GameTree
    from draughts.ui.variation_tree import VariationTreePane

    pane = VariationTreePane()
    tree = GameTree.from_moves(["22-17", "16-21", "24-19"])
    pane.set_tree(tree)
    # Root has 1 top-level child (first move)
    assert pane._tree_widget.topLevelItemCount() == 1
    first = pane._tree_widget.topLevelItem(0)
    # Linear chain: each node has exactly one child until the end
    assert first.childCount() == 1
    second = first.child(0)
    assert second.childCount() == 1


def test_pane_renders_variation():
    from draughts.game.gametree import GameTree
    from draughts.ui.variation_tree import VariationTreePane

    tree = GameTree.from_moves(["22-17", "16-21"])
    # Add a variation after first move
    first_move = tree.root.children[0]  # "22-17"
    first_move.add_child("8-12")  # variation to the main line "16-21"

    pane = VariationTreePane()
    pane.set_tree(tree)
    first_item = pane._tree_widget.topLevelItem(0)  # "22-17"
    # Two children: main "16-21", variation "8-12"
    assert first_item.childCount() == 2


def test_current_ply_highlight_tracks_main_line():
    from draughts.game.gametree import GameTree
    from draughts.ui.variation_tree import VariationTreePane

    pane = VariationTreePane()
    tree = GameTree.from_moves(["22-17", "16-21", "24-19"])
    pane.set_tree(tree)
    pane.set_current_ply(2)
    # Should not raise — purely visual state.


def test_node_click_emits_ply_for_main_line():
    from draughts.game.gametree import GameTree
    from draughts.ui.variation_tree import VariationTreePane

    received: list[int] = []
    pane = VariationTreePane()
    pane.node_clicked.connect(received.append)
    tree = GameTree.from_moves(["22-17", "16-21"])
    pane.set_tree(tree)
    # First top-level item = ply 1 (after 22-17)
    pane._on_item_clicked(pane._tree_widget.topLevelItem(0), 0)
    assert received == [1]


def test_node_click_ignores_variation():
    from draughts.game.gametree import GameTree
    from draughts.ui.variation_tree import VariationTreePane

    tree = GameTree.from_moves(["22-17"])
    tree.root.children[0].add_child("18-15")  # variation at same ply
    pane = VariationTreePane()
    received: list[int] = []
    pane.node_clicked.connect(received.append)
    pane.set_tree(tree)
    first = pane._tree_widget.topLevelItem(0)
    # Clicking a variation child must NOT emit a navigation signal.
    pane._on_item_clicked(first.child(1), 0)
    assert received == []
