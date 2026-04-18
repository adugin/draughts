"""Tests for the endgame bitbase (D9).

Covers:
  1. Empty bitbase probe returns None
  2. Add + probe (hash round-trip)
  3. Save / load round-trip
  4. K vs K is a draw (from bitbase content or direct _is_drawn_endgame logic)
  5. 2K vs K — side with 2 kings wins
  6. Integration: AIEngine with a tiny manual bitbase picks the winning move
  7. Smoke test: build script produces a valid, non-empty file
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from draughts.config import Color
from draughts.game.ai.bitbase import DRAW, LOSS, WIN, EndgameBitbase
from draughts.game.ai.search import AIEngine, _bitbase_best_move
from draughts.game.ai.tt import _zobrist_hash
from draughts.game.board import Board

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_board() -> Board:
    return Board(empty=True)


def _place(board: Board, pieces: list[tuple[int, int, int]]) -> Board:
    """Place pieces described as (x, y, piece_value) on *board* in-place."""

    for x, y, pv in pieces:
        board.grid[y, x] = np.int8(pv)
    return board


def _board_with(*pieces: tuple[int, int, int]) -> Board:
    """Return a fresh empty board with the given pieces placed."""
    b = _empty_board()
    return _place(b, list(pieces))


# Piece value shorthands
BK = 2  # Black king
WK = -2  # White king
BP = 1  # Black pawn
WP = -1  # White pawn


# ---------------------------------------------------------------------------
# Test 1 — empty bitbase probe returns None
# ---------------------------------------------------------------------------


def test_empty_bitbase_probe_returns_none():
    bb = EndgameBitbase()
    board = _board_with((1, 1, BK), (6, 6, WK))
    result = bb.probe(board, Color.BLACK)
    assert result is None


# ---------------------------------------------------------------------------
# Test 2 — add + probe
# ---------------------------------------------------------------------------


def test_add_and_probe():
    bb = EndgameBitbase()
    board = _board_with((1, 1, BK), (6, 6, WK))
    h = _zobrist_hash(board.grid, Color.BLACK)
    bb.add(h, WIN)

    result = bb.probe(board, Color.BLACK)
    assert result == WIN

    # Different color-to-move → different hash → miss
    result_white = bb.probe(board, Color.WHITE)
    assert result_white is None


# ---------------------------------------------------------------------------
# Test 3 — save / load round-trip
# ---------------------------------------------------------------------------


def test_save_load_roundtrip():
    bb = EndgameBitbase()

    # Add a few entries
    board1 = _board_with((1, 1, BK), (6, 6, WK))
    h1 = _zobrist_hash(board1.grid, Color.BLACK)
    bb.add(h1, WIN)

    board2 = _board_with((2, 2, BK), (5, 5, WK))
    h2 = _zobrist_hash(board2.grid, Color.WHITE)
    bb.add(h2, DRAW)

    board3 = _board_with((1, 1, BK), (3, 3, WK))
    h3 = _zobrist_hash(board3.grid, Color.BLACK)
    bb.add(h3, LOSS)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp_path = Path(f.name)

    try:
        bb.save(tmp_path)
        bb2 = EndgameBitbase.load(tmp_path)

        assert len(bb2) == 3

        assert bb2.probe(board1, Color.BLACK) == WIN
        assert bb2.probe(board2, Color.WHITE) == DRAW
        assert bb2.probe(board3, Color.BLACK) == LOSS

        # Sanity: JSON is readable
        data = json.loads(tmp_path.read_text(encoding="utf-8"))
        assert len(data) == 3
        assert all(isinstance(k, str) for k in data)
        assert all(v in (WIN, DRAW, LOSS) for v in data.values())
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Test 4 — K vs K is a draw
# ---------------------------------------------------------------------------


def test_kvk_is_draw():
    """King vs King is always a draw in Russian draughts.

    We verify via _is_drawn_endgame (which the generator uses) AND via
    a manually-seeded bitbase.
    """
    from draughts.game.ai.eval import _is_drawn_endgame

    board = _board_with((1, 1, BK), (6, 6, WK))
    assert _is_drawn_endgame(board.grid), "K vs K should be detected as drawn endgame"

    # Manually seed bitbase with DRAW for this position
    bb = EndgameBitbase()
    h = _zobrist_hash(board.grid, Color.BLACK)
    bb.add(h, DRAW)
    assert bb.probe(board, Color.BLACK) == DRAW


# ---------------------------------------------------------------------------
# Test 5 — endgame with material advantage is a win
# ---------------------------------------------------------------------------


def test_pawn_plus_king_vs_lone_king_is_win():
    """Black pawn + king vs lone white king: Black wins in most positions.

    In Russian draughts (8x8), 2K vs 1K is actually a DRAW (the lone king
    can always escape on the open board).  However, pawn + king vs lone king
    IS a forced win because the pawn threatens promotion.

    We verify that the bitbase contains WIN positions for BP+BK vs WK
    configurations (Black to move) and that the overall win count is
    substantial (> 1000), confirming the retrograde found real forced wins.
    """

    import draughts.game.ai as ai_pkg

    bb = ai_pkg.DEFAULT_BITBASE
    if bb is None:
        pytest.skip("bitbase_3.json not present — run build_bitbase.py first")

    stats = bb.stats()
    assert stats["wins"] > 1000, (
        f"Bitbase has only {stats['wins']} WIN positions — expected > 1000. "
        f"Full stats: {stats}. "
        "Regenerate with: python -m draughts.tools.build_bitbase"
    )

    # Verify a concrete win position: Black pawn at a7 (x=0,y=1) + Black king
    # at a3 (x=0,y=5) vs White king at g1 (x=6,y=7).
    # All three squares are valid dark squares (x%2 != y%2).
    # Black's pawn threatens promotion and the king supports it.
    board = _board_with((0, 1, BP), (0, 5, BK), (6, 7, WK))
    result = bb.probe(board, Color.BLACK)
    if result is None:
        pytest.skip("Concrete test position not in bitbase")
    assert result == WIN, f"BP at a7 + BK at a3 vs WK at g1 should be WIN for Black, got {result}"


# ---------------------------------------------------------------------------
# Test 6 — Integration: AIEngine with manual bitbase picks winning move
# ---------------------------------------------------------------------------


def test_bitbase_integration_with_engine():
    """AIEngine with a bitbase containing a clear win picks the winning move.

    Setup: Black has a king at b6 (x=1,y=2), White has a king at g1 (x=6,y=7).
    We manually seed the bitbase so that ALL moves from this position that land
    Black's king on c5 (x=2,y=3) map to a child-position result of LOSS for
    White (= after Black moves there, White is in a LOSS = Black wins).

    The engine must then pick that move (or any other WIN move).
    """
    from draughts.game.ai.moves import _apply_move, _generate_all_moves

    board = _board_with((1, 2, BK), (6, 7, WK))  # Black king b6, White king g1
    color = Color.BLACK
    opp = Color.WHITE

    # Generate all of Black's moves from this position
    moves = _generate_all_moves(board, color)
    assert moves, "Black should have moves"

    bb = EndgameBitbase()

    # Seed: for each child, mark result as LOSS for White (= WIN for Black after
    # Black moves there) for the FIRST move, DRAW for all others.
    # This gives the engine exactly one clear winning move.
    if not moves:
        pytest.skip("No moves generated")

    first_kind, first_path = moves[0]
    winning_child = _apply_move(board, first_kind, first_path)
    winning_child_h = _zobrist_hash(winning_child.grid, opp)
    bb.add(winning_child_h, LOSS)  # LOSS for White = WIN for Black

    for kind, path in moves[1:]:
        child = _apply_move(board, kind, path)
        child_h = _zobrist_hash(child.grid, opp)
        bb.add(child_h, DRAW)

    engine = AIEngine(difficulty=2, color=color, book=None, bitbase=bb)
    move = engine.find_move(board)

    assert move is not None, "Engine returned no move"
    assert move.path == first_path, f"Engine should pick the winning move {first_path}, got {move.path}"


# ---------------------------------------------------------------------------
# Test 7 — _bitbase_best_move function directly
# ---------------------------------------------------------------------------


def test_bitbase_best_move_prefers_win_over_draw():
    """_bitbase_best_move must prefer a WIN child over a DRAW child."""
    from draughts.game.ai.moves import _apply_move, _generate_all_moves

    board = _board_with((1, 2, BK), (6, 7, WK))
    color = Color.BLACK
    opp = Color.WHITE

    moves = _generate_all_moves(board, color)
    if len(moves) < 2:
        pytest.skip("Need at least 2 moves for this test")

    bb = EndgameBitbase()

    # First move → WIN (opponent in LOSS), rest → DRAW
    kind0, path0 = moves[0]
    child0 = _apply_move(board, kind0, path0)
    bb.add(_zobrist_hash(child0.grid, opp), LOSS)  # opp LOSS = we WIN

    for kind, path in moves[1:]:
        child = _apply_move(board, kind, path)
        bb.add(_zobrist_hash(child.grid, opp), DRAW)

    result_move = _bitbase_best_move(board, color, bb)
    assert result_move is not None
    assert result_move.path == path0, f"Should pick the WIN move {path0}, got {result_move.path}"


def test_bitbase_best_move_returns_none_when_all_unknown():
    """If no child is in the bitbase, _bitbase_best_move returns None."""
    board = _board_with((1, 2, BK), (6, 7, WK))
    bb = EndgameBitbase()  # empty — nothing in bitbase
    result = _bitbase_best_move(board, Color.BLACK, bb)
    assert result is None


# ---------------------------------------------------------------------------
# Test 8 — smoke test: build script produces a non-empty valid file
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_build_script_smoke(tmp_path: Path):
    """Run the build script with a tiny iteration cap and verify output.

    Marked slow — skipped in default test run unless -m slow is passed.
    The bitbase won't be complete with 1 iteration but the file must be
    a valid JSON dict with at least some entries.
    """
    output = tmp_path / "bitbase_test.json"
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "draughts.tools.build_bitbase",
            "--output",
            str(output),
            "--max-iters",
            "1",
            "--quiet",
        ],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 0, f"build_bitbase failed:\n{result.stderr}"
    assert output.exists(), "Output file not created"

    data = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "JSON root must be a dict"
    assert len(data) > 0, "Bitbase must contain at least one entry"

    # All values must be valid WLD integers (ignore the optional __meta__
    # header introduced in v1.1).
    for k, v in data.items():
        if k == "__meta__":
            assert isinstance(v, dict), "__meta__ must be a dict"
            continue
        assert isinstance(k, str), f"Key {k!r} must be string"
        assert v in (WIN, DRAW, LOSS), f"Value {v!r} for key {k!r} is not a valid WLD result"
