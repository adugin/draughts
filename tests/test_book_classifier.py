"""Regression tests for the opening-book capture/move classifier.

The pre-audit implementation classified any 2+-square king slide as
"capture" because it looked only at path geometry. When a probe hit a
book entry whose stored kind was "capture" for a quiet king fly, the
mandatory-capture guard in AIEngine.find_move accepted it and the
engine silently skipped a required capture.
"""

from __future__ import annotations

import random

from draughts.config import BLACK, BLACK_KING, Color, WHITE, WHITE_KING
from draughts.game.ai.book import (
    BookEntry,
    OpeningBook,
    _infer_kind,
    _path_is_capture_geometric,
    _path_is_capture_on_board,
)
from draughts.game.ai.search import AIMove
from draughts.game.ai.tt import _zobrist_hash
from draughts.game.board import Board


def _empty_board_with(pieces: list[tuple[int, int, int]]) -> Board:
    b = Board(empty=True)
    for x, y, piece in pieces:
        b.place_piece(x, y, piece)
    return b


def test_quiet_king_fly_is_classified_as_move():
    # White king on c3 (x=2,y=5), diagonal to f6 (x=5,y=2) across an
    # empty board — quiet move, not a capture.
    b = _empty_board_with([(2, 5, int(WHITE_KING))])
    path = ((2, 5), (5, 2))
    assert _path_is_capture_on_board(b, path) is False
    assert _infer_kind(b, path) == "move"


def test_king_capture_over_enemy_is_classified_as_capture():
    # White king on c3 slides to e5 but jumps over a black pawn at d4.
    b = _empty_board_with([
        (2, 5, int(WHITE_KING)),
        (3, 4, int(BLACK)),
    ])
    path = ((2, 5), (4, 3))
    assert _path_is_capture_on_board(b, path) is True
    assert _infer_kind(b, path) == "capture"


def test_pawn_two_square_move_is_always_capture():
    # Pawns never slide 2 squares without capturing — source piece type
    # alone is enough.
    b = _empty_board_with([(2, 5, int(WHITE))])
    path = ((2, 5), (4, 3))
    assert _path_is_capture_on_board(b, path) is True


def test_one_square_move_is_always_quiet():
    b = _empty_board_with([(2, 5, int(WHITE))])
    path = ((2, 5), (3, 4))
    assert _path_is_capture_on_board(b, path) is False


def test_multi_jump_is_always_capture_regardless_of_board():
    # Three waypoints = multi-jump, independent of piece type.
    b = Board(empty=True)
    path = ((0, 0), (2, 2), (4, 4))
    assert _path_is_capture_on_board(b, path) is True


def test_save_does_not_mislabel_king_slide_as_capture(tmp_path):
    # Simulate a quiet king slide added to the book, serialize, then
    # check the JSON kind field is "move" (not "capture" as the old
    # geometric classifier would have written).
    import json

    book = OpeningBook()
    board = _empty_board_with([(2, 5, int(WHITE_KING))])
    zhash = _zobrist_hash(board.grid, Color.WHITE)
    book.add(zhash, AIMove(kind="move", path=[(2, 5), (5, 2)]), weight=1)
    out = tmp_path / "book.json"
    book.save(out)
    raw = json.loads(out.read_text(encoding="utf-8"))
    records = raw[str(zhash)]
    assert len(records) == 1
    assert records[0][0] == "move"


def test_probe_reclassifies_on_load():
    # Even if an older book file stored "capture" for a quiet king
    # slide, probe() must re-classify against the live board so the
    # returned AIMove.kind is correct — otherwise search.find_move's
    # mandatory-capture guard would silently accept an illegal move.
    book = OpeningBook()
    board = _empty_board_with([(2, 5, int(WHITE_KING))])
    # Seed the entry directly, mimicking an old book with a buggy label.
    zhash = _zobrist_hash(board.grid, Color.WHITE)
    book._entries[zhash] = BookEntry(moves=[(((2, 5), (5, 2)), 1)])
    move = book.probe(board, Color.WHITE, rng=random.Random(0))
    assert move is not None
    assert move.kind == "move"


def test_probe_all_reclassifies_consistently():
    book = OpeningBook()
    board = _empty_board_with([
        (2, 5, int(WHITE_KING)),
        (3, 4, int(BLACK)),  # enemy on the diagonal
    ])
    zhash = _zobrist_hash(board.grid, Color.WHITE)
    book._entries[zhash] = BookEntry(moves=[
        (((2, 5), (4, 3)), 1),  # king jumps the pawn → capture
    ])
    entries = book.probe_all(board, Color.WHITE)
    assert len(entries) == 1
    assert entries[0][0].kind == "capture"


def test_geometric_classifier_is_conservative():
    # 2-point paths always "move", ≥3 points always "capture".
    assert _path_is_capture_geometric(((2, 5), (4, 3))) is False
    assert _path_is_capture_geometric(((2, 5), (5, 2))) is False
    assert _path_is_capture_geometric(((0, 0), (2, 2), (4, 4))) is True


def test_empty_source_falls_back_to_permissive():
    # Corrupt entry pointing at an empty square — keep the legacy
    # "assume capture" answer so we never mask a real capture.
    b = Board(empty=True)
    path = ((2, 5), (4, 3))
    assert _path_is_capture_on_board(b, path) is True


def test_black_king_slide_is_quiet():
    # Mirror test for the black side — guard against asymmetric logic.
    b = _empty_board_with([(3, 2, int(BLACK_KING))])
    path = ((3, 2), (6, 5))
    assert _path_is_capture_on_board(b, path) is False
