"""Variation tree side pane — displays the loaded PDN game tree.

M5 item #35: show the tree structure of a loaded PDN game with variations,
annotations (NAGs, comments), and current-position highlighting. Click a
main-line node to jump to that ply; variation nodes are shown but not
navigable yet (requires board replay across branches — future work).

Signals out:
    node_clicked(ply: int) — user clicked a node whose position is in
        the main-line history. Controller uses this to jump.

The widget is a passive viewer: set_tree() redraws from scratch.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDockWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from draughts.game.gametree import GameNode, GameTree, NAG_REVERSE

logger = logging.getLogger("draughts.variation_tree")


class VariationTreePane(QDockWidget):
    """Dockable pane that renders a GameTree with variations."""

    node_clicked = pyqtSignal(int)  # ply index (0..N) on the main line

    def __init__(self, parent=None) -> None:
        super().__init__("Дерево вариантов", parent)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self._tree_widget = QTreeWidget()
        self._tree_widget.setHeaderHidden(True)
        self._tree_widget.setIndentation(16)
        self._tree_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree_widget)

        self._tree: GameTree | None = None
        self._current_ply: int = 0
        # Maps QTreeWidgetItem → GameNode and ply (None if variation).
        self._item_info: dict[int, tuple[GameNode, int | None]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tree(self, tree: GameTree | None) -> None:
        """Replace the displayed tree. None clears the view."""
        self._tree = tree
        self._rebuild()

    def set_current_ply(self, ply: int) -> None:
        """Highlight the main-line node at ply (0 = initial position)."""
        self._current_ply = max(0, int(ply))
        self._refresh_highlight()

    # ------------------------------------------------------------------
    # Rebuild
    # ------------------------------------------------------------------

    def _rebuild(self) -> None:
        self._tree_widget.clear()
        self._item_info.clear()
        if self._tree is None:
            return

        root = self._tree.root
        # Ply of a node = its depth from root (root has no move, so ply 0
        # is the initial position BEFORE any moves).
        self._walk(root, parent_item=None, ply=0)
        self._tree_widget.expandAll()
        self._refresh_highlight()

    def _walk(self, node: GameNode, parent_item: QTreeWidgetItem | None, ply: int) -> None:
        """Pre-order traversal: first child on main line, others as siblings."""
        if not node.children:
            return

        # Main-line child (first) belongs on the SAME indent level as the
        # parent in chess-study conventions — but for a first pass we still
        # show it as a child for clarity.
        for idx, child in enumerate(node.children):
            label = self._format_node(child, ply + 1)
            item = QTreeWidgetItem([label])
            # Tag main-line vs variation visually.
            is_main = idx == 0 and self._is_on_main_line(node)
            if is_main:
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
                child_ply: int | None = ply + 1
            else:
                # Variation — italicized, no ply mapping (can't jump).
                font = item.font(0)
                font.setItalic(True)
                item.setFont(0, font)
                item.setForeground(0, self._tree_widget.palette().dark())
                child_ply = None

            if parent_item is None:
                self._tree_widget.addTopLevelItem(item)
            else:
                parent_item.addChild(item)

            self._item_info[id(item)] = (child, child_ply)

            # Recurse — pass the new child's ply (None if in a variation
            # branch) so descendants also become unreachable to jump.
            next_ply = child_ply if child_ply is not None else ply + 1
            self._walk(child, item, next_ply)

    def _is_on_main_line(self, node: GameNode) -> bool:
        """True if every ancestor (including self) is its parent's first child."""
        cur = node
        while cur.parent is not None:
            if cur.parent.children[0] is not cur:
                return False
            cur = cur.parent
        return True

    @staticmethod
    def _format_node(node: GameNode, ply: int) -> str:
        """Render 'N. move !?' style text for a tree row."""
        move = node.move or "(start)"
        move_num = (ply + 1) // 2
        prefix = f"{move_num}." if ply % 2 == 1 else f"{move_num}..."
        nag_text = ""
        if node.nag:
            glyphs = [NAG_REVERSE.get(n, n) for n in node.nag]
            nag_text = " " + "".join(glyphs)
        comment = f"  {{{node.comment}}}" if node.comment else ""
        return f"{prefix} {move}{nag_text}{comment}"

    # ------------------------------------------------------------------
    # Highlight
    # ------------------------------------------------------------------

    def _refresh_highlight(self) -> None:
        target_ply = self._current_ply
        for i in range(self._tree_widget.topLevelItemCount()):
            self._highlight_recursive(self._tree_widget.topLevelItem(i), target_ply)

    def _highlight_recursive(self, item: QTreeWidgetItem | None, target_ply: int) -> None:
        if item is None:
            return
        info = self._item_info.get(id(item))
        if info is not None:
            _, ply = info
            if ply is not None and ply == target_ply:
                item.setBackground(0, self._tree_widget.palette().highlight())
                item.setForeground(0, self._tree_widget.palette().highlightedText())
            else:
                item.setBackground(0, self._tree_widget.palette().base())
        for j in range(item.childCount()):
            self._highlight_recursive(item.child(j), target_ply)

    # ------------------------------------------------------------------
    # Click routing
    # ------------------------------------------------------------------

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        info = self._item_info.get(id(item))
        if info is None:
            return
        _node, ply = info
        if ply is None:
            return  # variation — not navigable (yet)
        self.node_clicked.emit(ply)
