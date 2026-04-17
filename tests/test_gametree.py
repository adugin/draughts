"""Tests for the GameTree model and PDN RAV round-trip (M5.a)."""

from __future__ import annotations

from draughts.game.gametree import NAG_MAP, GameNode, GameTree
from draughts.game.pdn import PDNGame, parse_pdn, pdngame_to_string


# ---------------------------------------------------------------------------
# GameNode / GameTree core
# ---------------------------------------------------------------------------


def test_empty_tree_has_root():
    tree = GameTree()
    assert tree.root is not None
    assert tree.root.move is None
    assert tree.root.children == []
    assert tree.node_count() == 1


def test_from_moves_linear_spine():
    moves = ["22-17", "9-14", "17x10", "5x14"]
    tree = GameTree.from_moves(moves)
    assert tree.main_line == moves
    assert tree.node_count() == len(moves) + 1  # plus root
    assert not tree.has_variations()


def test_add_variation_creates_sibling():
    tree = GameTree.from_moves(["22-17", "9-14"])
    main_first = tree.root.children[0]
    assert main_first.move == "22-17"
    # Alternative first move for white
    tree.root.add_variation("22-18")
    assert [c.move for c in tree.root.children] == ["22-17", "22-18"]
    assert tree.has_variations()
    # Main line unaffected
    assert tree.main_line == ["22-17", "9-14"]


def test_promote_to_main():
    tree = GameTree()
    tree.root.add_child("22-17")
    alt = tree.root.add_child("22-18")
    alt.promote_to_main()
    assert tree.root.children[0] is alt
    assert tree.main_line == ["22-18"]


def test_delete_subtree():
    tree = GameTree.from_moves(["22-17", "9-14"])
    alt = tree.root.add_child("22-18")
    alt.add_child("10-14")
    alt.delete()
    assert [c.move for c in tree.root.children] == ["22-17"]


def test_depth_and_path_from_root():
    tree = GameTree()
    n1 = tree.root.add_child("22-17")
    n2 = n1.add_child("9-14")
    n3 = n2.add_child("17x10")
    assert tree.root.depth() == 0
    assert n1.depth() == 1
    assert n3.depth() == 3
    path = n3.path_from_root()
    assert [n.move for n in path] == [None, "22-17", "9-14", "17x10"]


def test_iter_all_preorder():
    tree = GameTree.from_moves(["22-17", "9-14"])
    alt = tree.root.add_child("22-18")
    alt.add_child("10-14")
    moves = [n.move for n in tree.root.iter_all()]
    assert None in moves  # root
    # Preorder: root, 22-17, 9-14, 22-18, 10-14
    assert moves == [None, "22-17", "9-14", "22-18", "10-14"]


# ---------------------------------------------------------------------------
# PDN RAV — parser
# ---------------------------------------------------------------------------


def _single_game(text: str) -> PDNGame:
    games = parse_pdn(text)
    assert len(games) == 1
    return games[0]


def test_parse_flat_game_without_variations():
    pdn = """[Event "?"]
[Result "*"]

1. 22-17 9-14 2. 17x10 5x14 *"""
    g = _single_game(pdn)
    assert g.moves == ["22-17", "9-14", "17x10", "5x14"]
    assert g.tree is not None
    assert not g.tree.has_variations()


def test_parse_simple_variation():
    pdn = """[Event "?"]
[Result "*"]

1. 22-17 (1. 22-18) 9-14 *"""
    g = _single_game(pdn)
    # Main line preserved
    assert g.moves == ["22-17", "9-14"]
    # Variation attached as sibling of 22-17
    root = g.tree.root
    assert [c.move for c in root.children] == ["22-17", "22-18"]
    # 22-18 has no children (empty variation)
    assert root.children[1].children == []


def test_parse_variation_with_continuation():
    pdn = """[Event "?"]
[Result "*"]

1. 22-17 9-14 (1... 10-14 2. 25-22) 2. 17x10 5x14 *"""
    g = _single_game(pdn)
    assert g.moves == ["22-17", "9-14", "17x10", "5x14"]
    # 10-14 variation is sibling of 9-14 (under 22-17)
    n_22_17 = g.tree.root.children[0]
    assert [c.move for c in n_22_17.children] == ["9-14", "10-14"]
    # 10-14 has 25-22 as its child
    n_10_14 = n_22_17.children[1]
    assert [c.move for c in n_10_14.children] == ["25-22"]


def test_parse_nested_variation():
    pdn = """[Event "?"]
[Result "*"]

1. 22-17 (1. 22-18 (1. 23-18)) 9-14 *"""
    g = _single_game(pdn)
    assert g.moves == ["22-17", "9-14"]
    # Three root-level alternatives: 22-17, 22-18, 23-18
    siblings = [c.move for c in g.tree.root.children]
    assert siblings == ["22-17", "22-18", "23-18"]


def test_parse_comment_attached_to_move():
    pdn = """[Event "?"]
[Result "*"]

1. 22-17 {start of game} 9-14 *"""
    g = _single_game(pdn)
    root = g.tree.root
    n = root.children[0]
    assert n.move == "22-17"
    assert n.comment == "start of game"


def test_parse_nag_symbols():
    pdn = """[Event "?"]
[Result "*"]

1. 22-17! 9-14?? 2. 17x10!? 5x14 *"""
    g = _single_game(pdn)
    n1 = g.tree.root.children[0]
    assert n1.nag == [NAG_MAP["!"]]
    n2 = n1.children[0]
    assert n2.nag == [NAG_MAP["??"]]
    n3 = n2.children[0]
    assert n3.nag == [NAG_MAP["!?"]]


def test_parse_dollar_nag():
    pdn = """[Event "?"]
[Result "*"]

1. 22-17 $3 9-14 *"""
    g = _single_game(pdn)
    n = g.tree.root.children[0]
    assert "$3" in n.nag


# ---------------------------------------------------------------------------
# PDN RAV — writer
# ---------------------------------------------------------------------------


def test_write_flat_game_unchanged():
    """A game with no tree / no variations serializes via the legacy path."""
    game = PDNGame(
        headers={"Event": "?", "Result": "*"},
        moves=["22-17", "9-14"],
    )
    text = pdngame_to_string(game)
    # Must NOT contain '(' or '{'
    assert "(" not in text
    assert "{" not in text
    assert "22-17" in text and "9-14" in text


def test_write_game_with_variation_emits_rav():
    tree = GameTree()
    main = tree.root.add_child("22-17")
    main.add_child("9-14")
    tree.root.add_child("22-18")  # variation
    game = PDNGame(
        headers={"Event": "?", "Result": "*"},
        moves=tree.main_line,
        tree=tree,
    )
    text = pdngame_to_string(game)
    # Whitespace inside parens is insignificant in PDN.
    compact = text.replace(" ", "")
    assert "(1.22-18)" in compact


def test_write_game_with_black_variation_has_ellipsis():
    tree = GameTree()
    n1 = tree.root.add_child("22-17")
    n1.add_child("9-14")
    n1.add_child("10-14")  # variation, black's alternative
    game = PDNGame(
        headers={"Event": "?", "Result": "*"},
        moves=tree.main_line,
        tree=tree,
    )
    text = pdngame_to_string(game)
    compact = text.replace(" ", "")
    assert "(1...10-14)" in compact


def test_write_game_with_comment_and_nag():
    tree = GameTree()
    n1 = tree.root.add_child("22-17", comment="book move", nag=[NAG_MAP["!"]])
    n1.add_child("9-14")
    game = PDNGame(
        headers={"Event": "?", "Result": "*"},
        moves=tree.main_line,
        tree=tree,
    )
    text = pdngame_to_string(game)
    assert "22-17" in text
    assert "!" in text  # NAG symbol restored
    assert "{book move}" in text


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_round_trip_with_simple_variation():
    original = """[Event "?"]
[Result "*"]

1. 22-17 (1. 22-18) 9-14 *"""
    g1 = _single_game(original)
    out = pdngame_to_string(g1)
    g2 = _single_game(out)
    # Main line preserved
    assert g1.moves == g2.moves == ["22-17", "9-14"]
    # Variation preserved
    alts1 = [c.move for c in g1.tree.root.children]
    alts2 = [c.move for c in g2.tree.root.children]
    assert alts1 == alts2 == ["22-17", "22-18"]


def test_round_trip_with_continuation_variation():
    original = """[Event "?"]
[Result "*"]

1. 22-17 9-14 (1... 10-14 2. 25-22) 2. 17x10 5x14 *"""
    g1 = _single_game(original)
    out = pdngame_to_string(g1)
    g2 = _single_game(out)
    assert g1.moves == g2.moves == ["22-17", "9-14", "17x10", "5x14"]
    n1 = g2.tree.root.children[0]
    assert [c.move for c in n1.children] == ["9-14", "10-14"]
    assert [c.move for c in n1.children[1].children] == ["25-22"]


def test_round_trip_preserves_comments_and_nags():
    tree = GameTree()
    n1 = tree.root.add_child("22-17", comment="opening", nag=[NAG_MAP["!"]])
    n1.add_child("9-14", comment="standard reply")
    game = PDNGame(
        headers={"Event": "?", "Result": "*"},
        moves=tree.main_line,
        tree=tree,
    )
    text = pdngame_to_string(game)
    g2 = _single_game(text)
    assert g2.tree.root.children[0].comment == "opening"
    assert g2.tree.root.children[0].nag == [NAG_MAP["!"]]
    assert g2.tree.root.children[0].children[0].comment == "standard reply"


# ---------------------------------------------------------------------------
# Malformed input — graceful handling
# ---------------------------------------------------------------------------


def test_unmatched_open_paren_does_not_crash():
    pdn = """[Event "?"]
[Result "*"]

1. 22-17 (1. 22-18 9-14 *"""
    g = _single_game(pdn)
    # Just need parse to complete; main line starts with 22-17
    assert g.moves[0] == "22-17"


def test_variation_before_any_move_is_dropped():
    pdn = """[Event "?"]
[Result "*"]

(1. 22-18) 1. 22-17 9-14 *"""
    g = _single_game(pdn)
    assert g.moves == ["22-17", "9-14"]
    # Stray variation should not have created siblings at root
    assert len(g.tree.root.children) == 1


def test_comment_before_move_dropped():
    pdn = """[Event "?"]
[Result "*"]

{stray} 1. 22-17 9-14 *"""
    g = _single_game(pdn)
    assert g.moves == ["22-17", "9-14"]
    # Stray comment should not attach anywhere
    assert g.tree.root.children[0].comment == ""


# ---------------------------------------------------------------------------
# QA-audit regressions (M5.a B1/B2/B4)
# ---------------------------------------------------------------------------


def test_stray_rparen_at_top_level_does_not_truncate():
    """QA-B2: A stray ')' must not drop the remaining movetext."""
    pdn = """[Event "?"]
[Result "*"]

) 1. 22-17 9-14 2. 17x10 5x14 *"""
    g = _single_game(pdn)
    assert g.moves == ["22-17", "9-14", "17x10", "5x14"]


def test_black_to_move_fen_writer_emits_ellipsis():
    """QA-B1: FEN with Black-to-move must start with 'N...'."""
    game = PDNGame(
        headers={
            "Event": "?",
            "Result": "*",
            "SetUp": "1",
            "FEN": "B:W22:B9",
        },
        moves=["9-14", "22-17"],
    )
    text = pdngame_to_string(game)
    compact = " ".join(text.split())
    # Black's first move gets "1..." prefix; white's response is "2."
    assert "1... 9-14" in compact
    assert "2. 22-17" in compact


def test_black_to_move_fen_round_trip_preserves_moves():
    """QA-B1 follow-up: round-trip with black-to-move FEN keeps main line."""
    game = PDNGame(
        headers={
            "Event": "?",
            "Result": "*",
            "SetUp": "1",
            "FEN": "B:W22:B9",
        },
        moves=["9-14", "22-17", "14-18"],
    )
    text = pdngame_to_string(game)
    g2 = _single_game(text)
    assert g2.moves == ["9-14", "22-17", "14-18"]


def test_comment_containing_braces_is_escaped():
    """QA-B4: unmatched '{' or '}' inside a comment would break interop."""
    tree = GameTree()
    n1 = tree.root.add_child("22-17", comment="curly { and } inside")
    game = PDNGame(
        headers={"Event": "?", "Result": "*"},
        moves=tree.main_line,
        tree=tree,
    )
    text = pdngame_to_string(game)
    # Only ONE pair of braces in the output comment (the outer wrapper).
    # Any inner brace must have been replaced with square brackets.
    assert text.count("{") == 1
    assert text.count("}") == 1
    # Round-trip survives (parser does not choke).
    g2 = _single_game(text)
    assert g2.tree.root.children[0].move == "22-17"
