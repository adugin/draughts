"""Round-trip tests for _infer_pdn_move_from_boards / _apply_pdn_move.

Audit found that the old inferrer returned None for any multi-jump
capture (couldn't distinguish source from captured squares). Dropped
moves shifted every subsequent ply and corrupted saved PDN files.
"""

from __future__ import annotations

import numpy as np
import pytest

from draughts.app.controller import _apply_pdn_move, _infer_pdn_move_from_boards
from draughts.config import BLACK, BLACK_KING, Color, WHITE, WHITE_KING
from draughts.game.ai import _generate_all_moves
from draughts.game.ai.moves import _apply_move
from draughts.game.board import Board


def _roundtrip(before: Board, after: Board) -> bool:
    """Infer a PDN token from before→after, apply it to before, expect after."""
    mv = _infer_pdn_move_from_boards(before, after)
    if mv is None:
        return False
    replay = before.copy()
    _apply_pdn_move(replay, mv)
    return np.array_equal(replay.grid, after.grid)


# ---------------------------------------------------------------------------
# Simple moves
# ---------------------------------------------------------------------------


def test_simple_white_pawn_move_roundtrip():
    before = Board()
    after = before.copy()
    after.execute_move(6, 5, 7, 4)  # 24-20
    assert _infer_pdn_move_from_boards(before, after) == "24-20"
    assert _roundtrip(before, after)


def test_simple_black_pawn_move_roundtrip():
    before = Board()
    after = before.copy()
    after.execute_move(5, 2, 4, 3)  # 11-15
    assert _infer_pdn_move_from_boards(before, after) == "11-15"
    assert _roundtrip(before, after)


def test_king_simple_long_move():
    """Flying king simple move — 3-step diagonal, no captures."""
    before = Board(empty=True)
    before.grid[7, 0] = BLACK_KING  # a1
    after = before.copy()
    after.execute_move(0, 7, 3, 4)  # a1 → d4
    assert _infer_pdn_move_from_boards(before, after) == "29-18"
    assert _roundtrip(before, after)


# ---------------------------------------------------------------------------
# Simple captures
# ---------------------------------------------------------------------------


def test_single_capture_pawn():
    before = Board(empty=True)
    before.grid[4, 3] = BLACK   # d4 black pawn
    before.grid[5, 2] = WHITE   # c3 white pawn
    after = before.copy()
    after.execute_capture_path([(3, 4), (1, 6)])  # d4:b2
    mv = _infer_pdn_move_from_boards(before, after)
    assert mv is not None
    assert "x" in mv, f"Expected capture, got {mv!r}"
    assert _roundtrip(before, after)


def test_king_single_capture():
    before = Board(empty=True)
    before.grid[7, 0] = BLACK_KING  # a1
    before.grid[2, 5] = WHITE       # f6
    after = before.copy()
    after.execute_capture_path([(0, 7), (6, 1)])  # a1:g7
    mv = _infer_pdn_move_from_boards(before, after)
    assert mv is not None and "x" in mv
    assert _roundtrip(before, after)


# ---------------------------------------------------------------------------
# Multi-jump captures — the bug that started this audit
# ---------------------------------------------------------------------------


def test_king_multi_jump_three_captures():
    """Black king a1 jumps over b2/d4/f6 landing at g7. Old inferrer dropped this."""
    before = Board(empty=True)
    before.grid[7, 0] = BLACK_KING  # a1
    before.grid[6, 1] = WHITE       # b2
    before.grid[4, 3] = WHITE       # d4
    before.grid[2, 5] = WHITE       # f6
    after = before.copy()
    after.execute_capture_path([(0, 7), (2, 5), (4, 3), (6, 1)])  # a1:c3:e5:g7

    mv = _infer_pdn_move_from_boards(before, after)
    assert mv is not None, "Multi-jump must not return None (prev bug)"
    assert mv.count("x") == 3, f"Expected 3 'x' separators for 3-jump, got {mv!r}"
    assert _roundtrip(before, after)


def test_pawn_multi_jump():
    """Black pawn d4 → zigzag capture of two whites."""
    before = Board(empty=True)
    before.grid[4, 3] = BLACK   # d4 black pawn
    before.grid[5, 2] = WHITE   # c3 white pawn
    before.grid[5, 4] = WHITE   # e3 white pawn
    # Path: d4 → b2 (jump c3), b2 → d6? Let me use safer path.
    # d4 jumps over c3 landing b2; from b2 no more captures → length 1.
    # Two-jump path: d4 jumps e3 → f2, f2 stuck. Also one-jump.
    # Construct a real 2-jump: place enemies appropriately.
    before2 = Board(empty=True)
    before2.grid[0, 1] = BLACK   # b8 black pawn (about to sweep down)
    before2.grid[1, 2] = WHITE   # c7
    before2.grid[3, 2] = WHITE   # c5
    after2 = before2.copy()
    # b8 jumps c7 → d6; d6 jumps c5 → b4. Path: [(1,0),(3,2),(1,4)]
    after2.execute_capture_path([(1, 0), (3, 2), (1, 4)])

    mv = _infer_pdn_move_from_boards(before2, after2)
    assert mv is not None
    assert mv.count("x") == 2, f"Expected 2 'x' separators for 2-jump, got {mv!r}"
    assert _roundtrip(before2, after2)


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------


def test_simple_move_with_promotion():
    """White pawn reaches row 1 via a simple forward move and promotes."""
    before = Board(empty=True)
    before.grid[1, 0] = WHITE   # a7 white pawn
    after = before.copy()
    after.execute_move(0, 1, 1, 0)  # a7 → b8 (promotes to white king)

    mv = _infer_pdn_move_from_boards(before, after)
    assert mv is not None
    assert _roundtrip(before, after)


def test_capture_with_promotion():
    """White pawn captures and promotes at the same time."""
    before = Board(empty=True)
    before.grid[2, 1] = WHITE   # b6 white pawn
    before.grid[1, 2] = BLACK   # c7 black pawn
    after = before.copy()
    # b6 jumps c7 → d8: [(1,2),(3,0)]
    after.execute_capture_path([(1, 2), (3, 0)])

    mv = _infer_pdn_move_from_boards(before, after)
    assert mv is not None and "x" in mv
    assert _roundtrip(before, after)


# ---------------------------------------------------------------------------
# Full games via PDN writer
# ---------------------------------------------------------------------------


def test_save_then_load_full_game_preserves_plies(tmp_path):
    """Save a synthetic game to PDN, reload, every ply round-trips."""
    from draughts.game.pdn import RUSSIAN_DRAUGHTS_GAMETYPE, PDNGame, load_pdn_file, write_pdn, _today_date_str

    # Play 10 plies via move generator (first legal move each ply).
    import random as _r

    _r.seed(123)
    b = Board()
    positions = [b.to_position_string()]
    color = Color.WHITE
    for _ in range(20):
        moves = list(_generate_all_moves(b, color))
        if not moves:
            break
        kind, path = _r.choice(moves)
        b = _apply_move(b, kind, path)
        positions.append(b.to_position_string())
        color = color.opponent

    # Infer move tokens between each consecutive pair — our writer's
    # code path.
    moves_tokens: list[str] = []
    prev = Board()
    prev.load_from_position_string(positions[0])
    for pos in positions[1:]:
        curr = Board()
        curr.load_from_position_string(pos)
        tok = _infer_pdn_move_from_boards(prev, curr)
        assert tok is not None, "inferrer must not drop any ply"
        moves_tokens.append(tok)
        prev = curr

    # Write and reload.
    game = PDNGame(
        headers={
            "Event": "?", "Site": "?", "Date": _today_date_str(),
            "Round": "?", "White": "?", "Black": "?", "Result": "*",
            "GameType": RUSSIAN_DRAUGHTS_GAMETYPE,
        },
        moves=moves_tokens,
    )
    out = tmp_path / "roundtrip.pdn"
    write_pdn([game], out)
    loaded = load_pdn_file(out)[0]
    assert loaded.moves == moves_tokens, "loaded PDN must match saved"

    # Re-replay and verify final state matches.
    replay = Board()
    for tok in loaded.moves:
        _apply_pdn_move(replay, tok)
    expected = Board()
    expected.load_from_position_string(positions[-1])
    assert np.array_equal(replay.grid, expected.grid)
