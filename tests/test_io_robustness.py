"""I/O robustness tests — audit gaps #7, #8, #9, #11, #13.

Covers the "malformed input doesn't crash the program" contract for:
- PDN with unusual characters in comments, NAGs inside RAV, SetUp/FEN.
- Truncated or corrupt opening book / bitbase files.
- Malformed FEN input.

Historical motivation: when the bitbase file at `%APPDATA%/...` got
half-downloaded once and the app failed at import-time. We since added
the downloader's atomic rename, but the LOADER itself should also
gracefully tolerate a bad file.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from draughts.game.ai.bitbase import EndgameBitbase
from draughts.game.ai.book import OpeningBook
from draughts.game.board import Board
from draughts.game.pdn import load_pdn_file, parse_pdn


# ---------------------------------------------------------------------------
# PDN escape / special chars in comments
# ---------------------------------------------------------------------------


def test_pdn_comment_with_braces_and_parens(tmp_path: Path):
    """Comments may contain { } ( ) literally — writer must escape,
    reader must not confuse them for variation markers.
    """
    from draughts.game.pdn import PDNGame, RUSSIAN_DRAUGHTS_GAMETYPE, write_pdn, _today_date_str
    from draughts.game.gametree import GameTree, GameNode

    root = GameNode()
    child = root.add_child("24-20", comment="hello {world} and (parens)")
    child.add_child("11-15")
    tree = GameTree(root=root)

    game = PDNGame(
        headers={
            "Event": "?", "Site": "?", "Date": _today_date_str(),
            "Round": "?", "White": "?", "Black": "?", "Result": "*",
            "GameType": RUSSIAN_DRAUGHTS_GAMETYPE,
        },
        moves=["24-20", "11-15"],
        tree=tree,
    )
    out = tmp_path / "comments.pdn"
    write_pdn([game], out)

    # Re-read and verify the comment survived (possibly with escaped
    # characters, but preserved in intent).
    loaded = load_pdn_file(out)[0]
    assert loaded.tree is not None
    first = loaded.tree.root.children[0]
    assert first.comment, "Comment must survive round-trip"


def test_pdn_comment_with_unicode(tmp_path: Path):
    """Russian text in comments must be preserved."""
    from draughts.game.pdn import PDNGame, RUSSIAN_DRAUGHTS_GAMETYPE, write_pdn, _today_date_str
    from draughts.game.gametree import GameTree, GameNode

    root = GameNode()
    root.add_child("24-20", comment="сомнительный ход").add_child("11-15")
    tree = GameTree(root=root)

    game = PDNGame(
        headers={
            "Event": "?", "Site": "?", "Date": _today_date_str(),
            "Round": "?", "White": "?", "Black": "?", "Result": "*",
            "GameType": RUSSIAN_DRAUGHTS_GAMETYPE,
        },
        moves=["24-20", "11-15"],
        tree=tree,
    )
    out = tmp_path / "unicode.pdn"
    write_pdn([game], out)

    text = out.read_text(encoding="utf-8")
    assert "сомнительный" in text

    loaded = load_pdn_file(out)[0]
    assert loaded.tree.root.children[0].comment.strip() != ""


def test_pdn_nag_inside_rav():
    """Variation with a NAG inside the parentheses parses correctly.

    PDN RAV convention: `(1. 22-18!)` after `22-17!?` means an alternative
    to 22-17 at the same ply — tree-wise they are SIBLINGS sharing the
    same parent (the root), not parent-and-child.
    """
    pdn_text = (
        '[Event "T"]\n[GameType "25"]\n\n'
        "1. 22-17!? (1. 22-18! 11-15) 11-15 *\n"
    )
    games = parse_pdn(pdn_text)
    assert len(games) == 1
    g = games[0]
    assert g.tree is not None
    # Root has two children: main line 22-17 and variation 22-18.
    assert len(g.tree.root.children) == 2, (
        f"Expected root → [main, variation]; got {[c.move for c in g.tree.root.children]}"
    )
    main = g.tree.root.children[0]
    variation = g.tree.root.children[1]
    assert main.move == "22-17"
    assert main.nag == ["$5"], f"Main move NAG should be $5 (=!?), got {main.nag}"
    assert variation.move == "22-18"
    assert variation.nag == ["$1"], f"Variation NAG should be $1 (=!), got {variation.nag}"
    # Both main and variation have a follow-up 11-15.
    assert len(main.children) == 1 and main.children[0].move == "11-15"
    assert len(variation.children) == 1 and variation.children[0].move == "11-15"


def test_pdn_setup_fen_black_to_move_roundtrip(tmp_path: Path):
    """FEN with black-to-move tag survives full save/load/replay."""
    from draughts.app.controller import GameController
    from draughts.config import BLACK_KING, Color, WHITE_KING
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    import sys

    _app = QApplication.instance() or QApplication(sys.argv)

    b = Board(empty=True)
    b.grid[2, 7] = BLACK_KING
    b.grid[5, 0] = WHITE_KING

    pdn_text = (
        '[Event "T"]\n[GameType "25"]\n[SetUp "1"]\n'
        '[FEN "B:W8:B24"]\n\n*\n'
    )
    p = tmp_path / "black_to_move.pdn"
    p.write_text(pdn_text, encoding="utf-8")

    class _BypassAI(GameController):
        def _start_computer_turn(self):
            pass  # stay inert in tests

    c = _BypassAI()
    c.load_game_from_pdn(str(p))
    assert c.current_turn == Color.BLACK, (
        f"Black-to-move FEN must set current_turn to BLACK, got {c.current_turn}"
    )


# ---------------------------------------------------------------------------
# Corrupt bitbase — does not crash on load, falls back
# ---------------------------------------------------------------------------


def test_corrupt_bitbase_raises_cleanly(tmp_path: Path):
    """Garbage in → json.JSONDecodeError (not a crash). Caller handles it."""
    bad = tmp_path / "garbage.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        EndgameBitbase.load(bad)


def test_truncated_gzip_bitbase_raises_cleanly(tmp_path: Path):
    """A half-downloaded .json.gz must not import as an empty bitbase —
    better to raise so the app can reacquire the file.
    """
    # Write a valid gz-start then truncate.
    raw = json.dumps({"1": 1, "2": 0}).encode("utf-8")
    full_path = tmp_path / "real.json.gz"
    with gzip.open(full_path, "wb") as fh:
        fh.write(raw)
    data = full_path.read_bytes()
    truncated = tmp_path / "half.json.gz"
    truncated.write_bytes(data[: len(data) // 2])  # half the bytes
    with pytest.raises(Exception):  # OSError / EOFError from gzip
        EndgameBitbase.load(truncated)


def test_bitbase_load_probe_returns_none_for_unknown_hash(tmp_path: Path):
    """Basic correctness — probe on a hash not in the file returns None."""
    bb = EndgameBitbase(entries={123: 1}, max_pieces=3)
    path = tmp_path / "bb.json"
    bb.save(path)
    loaded = EndgameBitbase.load(path)
    assert loaded.probe_hash(456) is None


# ---------------------------------------------------------------------------
# Corrupt opening book
# ---------------------------------------------------------------------------


def test_corrupt_opening_book_raises_cleanly(tmp_path: Path):
    """Malformed JSON raises decodable error, not silent empty book."""
    bad = tmp_path / "book.json"
    bad.write_text("{not valid", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        OpeningBook.load(bad)


def test_empty_opening_book_loads_successfully(tmp_path: Path):
    """Empty `{}` is a valid empty book (no positions) — not an error."""
    p = tmp_path / "empty_book.json"
    p.write_text("{}", encoding="utf-8")
    book = OpeningBook.load(p)
    assert len(book) == 0


# ---------------------------------------------------------------------------
# Malformed FEN input
# ---------------------------------------------------------------------------


def test_fen_missing_turn_marker_rejected():
    from draughts.game.fen import parse_fen

    with pytest.raises((ValueError, IndexError)):
        parse_fen("")


def test_fen_with_invalid_square_rejected():
    from draughts.game.fen import parse_fen

    with pytest.raises((ValueError, IndexError)):
        parse_fen("W:W99:B1")   # square 99 out of range
