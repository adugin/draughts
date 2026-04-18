"""Game tree for variation support (M5).

A GameTree stores a game as a tree of moves rather than a flat list.
Each GameNode holds one move plus zero or more child nodes; the first
child of any node is the "main line" continuation, additional children
are alternative variations (PDN RAV).

Design goals:
- Linear games (no variations) still trivially supported:
  GameTree.from_moves([...]) → straight spine of first-children.
- Backward compatible: main_line() returns a list of move tokens
  identical to the flat moves list that existed before M5.
- Move tokens are opaque strings in PDN format ("22-17", "9x18x27").
  The tree does NOT validate moves — it only organizes them.
- No coupling to Qt or the Board class — pure data structure so it
  can be shared with headless / engine code paths.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

# PDN 3.0 standardized Numeric Annotation Glyphs relevant to draughts.
# Keys are the textual token, value is the canonical $N form.
NAG_MAP: dict[str, str] = {
    "!": "$1",
    "?": "$2",
    "!!": "$3",
    "??": "$4",
    "!?": "$5",
    "?!": "$6",
}
NAG_REVERSE: dict[str, str] = {v: k for k, v in NAG_MAP.items()}


@dataclass
class GameNode:
    """One ply in a game tree.

    Root node has ``move is None`` and sits above the first ply.
    ``children[0]`` is the main-line continuation; additional children
    are alternative variations.
    """

    move: str | None = None
    parent: GameNode | None = field(default=None, repr=False)
    children: list[GameNode] = field(default_factory=list, repr=False)
    comment: str = ""
    nag: list[str] = field(default_factory=list)

    # --- Tree construction ---

    def add_child(self, move: str, *, comment: str = "", nag: list[str] | None = None) -> GameNode:
        """Append a new child to this node and return it."""
        node = GameNode(move=move, parent=self, comment=comment, nag=list(nag or []))
        self.children.append(node)
        return node

    def add_variation(self, move: str, *, comment: str = "", nag: list[str] | None = None) -> GameNode:
        """Alias for add_child — name emphasises that variations share a parent."""
        return self.add_child(move, comment=comment, nag=nag)

    # --- Traversal ---

    def main_line(self) -> list[GameNode]:
        """Return this node and all first-child descendants (excluding self if root).

        Root-included form: caller inspects ``n.move is None`` to skip.
        Most callers want ``root.main_line()[1:]`` — the move sequence.
        """
        result: list[GameNode] = [self]
        cur = self
        while cur.children:
            cur = cur.children[0]
            result.append(cur)
        return result

    def main_line_moves(self) -> list[str]:
        """Main-line move tokens from THIS node forward (excluding self's own move)."""
        return [n.move for n in self.main_line()[1:] if n.move is not None]

    def depth(self) -> int:
        """Depth from root. Root = 0."""
        d = 0
        cur = self.parent
        while cur is not None:
            d += 1
            cur = cur.parent
        return d

    def path_from_root(self) -> list[GameNode]:
        """Return [root, ..., self] — useful for breadcrumb / navigation."""
        chain: list[GameNode] = []
        cur: GameNode | None = self
        while cur is not None:
            chain.append(cur)
            cur = cur.parent
        chain.reverse()
        return chain

    def iter_all(self) -> Iterator[GameNode]:
        """Pre-order traversal of the whole subtree."""
        yield self
        for c in self.children:
            yield from c.iter_all()

    # --- Mutation ---

    def promote_to_main(self) -> None:
        """Make this node the first child of its parent (i.e. main-line member).

        No-op on root or already-main nodes.
        """
        if self.parent is None:
            return
        siblings = self.parent.children
        if siblings and siblings[0] is self:
            return
        siblings.remove(self)
        siblings.insert(0, self)

    def delete(self) -> None:
        """Detach this node (and its subtree) from its parent."""
        if self.parent is None:
            return
        self.parent.children = [c for c in self.parent.children if c is not self]
        self.parent = None


class GameTree:
    """Thin wrapper around a root GameNode for ergonomic access."""

    def __init__(self, root: GameNode | None = None) -> None:
        self.root = root or GameNode()

    # --- Construction ---

    @classmethod
    def from_moves(cls, moves: list[str]) -> GameTree:
        """Build a linear tree from a flat list of move tokens."""
        tree = cls()
        cur = tree.root
        for mv in moves:
            cur = cur.add_child(mv)
        return tree

    # --- Convenience ---

    @property
    def main_line(self) -> list[str]:
        """Main-line move tokens (excluding the implicit root)."""
        return self.root.main_line_moves()

    def node_count(self) -> int:
        return sum(1 for _ in self.root.iter_all())

    def has_variations(self) -> bool:
        """True if any node has more than one child."""
        return any(len(n.children) > 1 for n in self.root.iter_all())
