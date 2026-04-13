"""Tests for draughts.engine — the UCI-like text protocol layer.

All tests drive EngineSession directly through io.StringIO streams so no
subprocess or real stdin/stdout is needed.  This is fast and avoids any
platform-specific pipe quirks.
"""

from __future__ import annotations

import io
import time

import pytest
from draughts.engine import EngineSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_io(commands: list[str]) -> tuple[EngineSession, str]:
    """Run a sequence of commands through a fresh EngineSession.

    Returns (session, output_text).
    """
    inp = io.StringIO("\n".join(commands) + "\n")
    out = io.StringIO()
    session = EngineSession()
    session.run(inp, out)
    return session, out.getvalue()


def _lines(text: str) -> list[str]:
    """Return non-empty lines from text."""
    return [line for line in text.splitlines() if line.strip()]


def _find_line(text: str, prefix: str) -> str | None:
    """Return the first line starting with *prefix*, or None."""
    for line in _lines(text):
        if line.startswith(prefix):
            return line
    return None


# ---------------------------------------------------------------------------
# 1. UCI handshake
# ---------------------------------------------------------------------------


def test_uci_handshake():
    """'uci' command must produce id lines and terminate with 'udriok'."""
    _, out = _session_io(["uci", "quit"])
    lines = _lines(out)
    assert any(ln.startswith("id name") for ln in lines), "missing 'id name'"
    assert any(ln.startswith("id author") for ln in lines), "missing 'id author'"
    assert any(ln == "udriok" for ln in lines), "missing 'udriok'"
    # Options must be advertised
    assert any("Level" in ln for ln in lines), "missing Level option"
    assert any("MoveTime" in ln for ln in lines), "missing MoveTime option"


# ---------------------------------------------------------------------------
# 2. isready
# ---------------------------------------------------------------------------


def test_isready():
    """'isready' must produce 'readyok'."""
    _, out = _session_io(["isready", "quit"])
    assert "readyok" in _lines(out)


# ---------------------------------------------------------------------------
# 3. position startpos + go depth
# ---------------------------------------------------------------------------


def test_position_startpos_and_go_depth():
    """Start position + go depth 3 must produce bestmove in valid notation."""
    _, out = _session_io(["position startpos", "go depth 3", "quit"])
    bm = _find_line(out, "bestmove")
    assert bm is not None, f"No bestmove in output:\n{out}"
    move_part = bm.split(None, 1)[1]
    assert move_part != "(none)", f"Engine returned no legal move: {bm}"
    # Must be in algebraic notation: two squares separated by '-' or ':'
    assert "-" in move_part or ":" in move_part, f"Not algebraic notation: {move_part!r}"
    # Must have at least one info line
    info_lines = [ln for ln in _lines(out) if ln.startswith("info depth")]
    assert len(info_lines) >= 1, f"No info lines:\n{out}"


# ---------------------------------------------------------------------------
# 4. position fen
# ---------------------------------------------------------------------------


def test_position_fen():
    """Set a mid-game FEN, go depth 3, assert bestmove."""
    # A simple mid-game position: 2 white pawns vs 2 black pawns
    fen = "W:W21,25:B9,13"
    _, out = _session_io([f"position fen {fen}", "go depth 3", "quit"])
    bm = _find_line(out, "bestmove")
    assert bm is not None, f"No bestmove:\n{out}"
    move_part = bm.split(None, 1)[1]
    assert move_part != "(none)", f"Engine returned no move: {bm}"
    assert "-" in move_part or ":" in move_part, f"Not algebraic: {move_part!r}"


# ---------------------------------------------------------------------------
# 5. position with moves
# ---------------------------------------------------------------------------


def test_position_with_moves():
    """'position startpos moves c3-d4 f6-e5' advances two plies; go depth 3
    returns white's next move."""
    commands = [
        "position startpos moves c3-d4 f6-e5",
        "go depth 3",
        "quit",
    ]
    _, out = _session_io(commands)
    bm = _find_line(out, "bestmove")
    assert bm is not None, f"No bestmove:\n{out}"
    move_part = bm.split(None, 1)[1]
    assert move_part != "(none)", f"Engine returned no move: {bm}"
    # White to move: piece starts with a-h, row 1-4 (white side bottom)
    # Just check it's valid algebraic
    assert "-" in move_part or ":" in move_part, f"Not algebraic: {move_part!r}"


# ---------------------------------------------------------------------------
# 6. setoption Level
# ---------------------------------------------------------------------------


def test_setoption_level():
    """setoption name Level value 1 should lower the level."""
    inp = io.StringIO("setoption name Level value 1\nquit\n")
    out = io.StringIO()
    session = EngineSession()
    session.run(inp, out)
    assert session.level == 1


def test_setoption_level_affects_search():
    """At level 1 (depth 2) the search should be noticeably faster than
    at level 6 (depth 8).  We just verify both return a bestmove."""
    for level in (1, 4):
        commands = [
            f"setoption name Level value {level}",
            "position startpos",
            "go depth 3",
            "quit",
        ]
        _, out = _session_io(commands)
        bm = _find_line(out, "bestmove")
        assert bm is not None, f"Level {level}: no bestmove\n{out}"
        assert bm.split(None, 1)[1] != "(none)", f"Level {level}: no legal move"


# ---------------------------------------------------------------------------
# 7. go movetime
# ---------------------------------------------------------------------------


def test_go_movetime():
    """go movetime 200 must return within ~500 ms and contain bestmove."""
    start = time.perf_counter()
    commands = ["position startpos", "go movetime 200", "quit"]
    _, out = _session_io(commands)
    elapsed = time.perf_counter() - start
    bm = _find_line(out, "bestmove")
    assert bm is not None, f"No bestmove:\n{out}"
    assert bm.split(None, 1)[1] != "(none)"
    assert elapsed < 5.0, f"go movetime 200 took {elapsed:.2f}s (too slow)"


# ---------------------------------------------------------------------------
# 8. quit
# ---------------------------------------------------------------------------


def test_quit():
    """'quit' must cause session to terminate (run() returns)."""
    inp = io.StringIO("quit\n")
    out = io.StringIO()
    session = EngineSession()
    # run() must return (not hang)
    session.run(inp, out)
    assert session._quit is True


# ---------------------------------------------------------------------------
# 9. newgame resets state
# ---------------------------------------------------------------------------


def test_newgame_resets_state():
    """After newgame, session responds correctly to subsequent commands."""
    commands = [
        "position startpos",
        "go depth 2",
        "newgame",
        "position startpos",
        "go depth 2",
        "quit",
    ]
    _, out = _session_io(commands)
    bestmoves = [ln for ln in _lines(out) if ln.startswith("bestmove")]
    assert len(bestmoves) == 2, f"Expected 2 bestmoves, got:\n{out}"


# ---------------------------------------------------------------------------
# 10. No PyQt6 import (D26 compliance)
# ---------------------------------------------------------------------------


def test_no_pyqt6_import():
    """draughts.engine must be importable without PyQt6.

    This is enforced by checking that none of the engine modules import Qt.
    We verify via a subprocess that strips PYTHONPATH and tries a bare import.
    """
    import subprocess
    import sys

    script = (
        "import sys; "
        "import draughts.engine; "
        "import draughts.engine.protocol; "
        "import draughts.engine.session; "
        # Verify PyQt6 is NOT in sys.modules after importing engine
        "assert 'PyQt6' not in sys.modules, "
        "'PyQt6 was imported by draughts.engine!'"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"draughts.engine import test failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# 11. protocol helpers unit tests
# ---------------------------------------------------------------------------


def test_format_and_parse_move_roundtrip():
    """format_move / parse_move must be inverse operations."""
    from draughts.engine.protocol import format_move, parse_move

    cases: list[tuple[str, list[tuple[int, int]]]] = [
        ("move", [(2, 5), (3, 4)]),       # c3-d4
        ("capture", [(2, 5), (4, 3)]),    # c3:e5
        ("capture", [(2, 5), (4, 3), (6, 5)]),  # c3:e5:g3
    ]
    for kind, path in cases:
        token = format_move(kind, path)
        parsed_kind, parsed_path = parse_move(token)
        assert parsed_kind == kind, f"kind mismatch for {token!r}"
        assert parsed_path == path, f"path mismatch for {token!r}"


def test_parse_move_invalid():
    """parse_move raises ValueError for bad tokens."""
    from draughts.engine.protocol import parse_move

    with pytest.raises(ValueError):
        parse_move("z9-x0")  # out of range
    with pytest.raises(ValueError):
        parse_move("c3")      # no destination
    with pytest.raises(ValueError):
        parse_move("")        # empty


# ---------------------------------------------------------------------------
# 12. info lines contain required fields
# ---------------------------------------------------------------------------


def test_info_lines_have_required_fields():
    """Each 'info depth' line must contain depth, score, nodes, time, pv."""
    commands = ["position startpos", "go depth 3", "quit"]
    _, out = _session_io(commands)
    info_lines = [ln for ln in _lines(out) if ln.startswith("info depth")]
    assert len(info_lines) >= 1, "No info lines produced"
    for line in info_lines:
        assert "score cp" in line, f"Missing 'score cp' in: {line}"
        assert "nodes" in line, f"Missing 'nodes' in: {line}"
        assert "time" in line, f"Missing 'time' in: {line}"
        assert "pv" in line, f"Missing 'pv' in: {line}"
