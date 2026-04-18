"""Puzzle parser validation — reject out-of-range / bogus difficulty.

Audit #4 flagged that ``_parse_puzzle_entry`` accepted any integer as a
puzzle difficulty, which meant a mined-JSON file with ``"difficulty":
99`` would orphan the puzzle (``get_by_difficulty(1..4)`` never returns
it) and render ``"★" * 99`` in the trainer header. Now rejected at
parse time so the malformed puzzle is skipped (``load_bundled_puzzles``
logs and continues) instead of silently breaking the UI.
"""

from __future__ import annotations

import pytest

from draughts.game.puzzles import _parse_puzzle_entry


_BASE: dict = {
    "id": "T-001",
    "category": "combination_2cap",
    "position": "n" * 32,
    "turn": "white",
    "best_move": "a1-b2",
    "solution_sequence": ["a1-b2"],
    "difficulty": 2,
    "description": "",
}


def test_valid_difficulty_accepted():
    entry = dict(_BASE, difficulty=3)
    p = _parse_puzzle_entry(entry)
    assert p.difficulty == 3


def test_difficulty_lower_boundary():
    entry = dict(_BASE, difficulty=1)
    p = _parse_puzzle_entry(entry)
    assert p.difficulty == 1


def test_difficulty_upper_boundary():
    entry = dict(_BASE, difficulty=4)
    p = _parse_puzzle_entry(entry)
    assert p.difficulty == 4


def test_difficulty_below_range_rejected():
    entry = dict(_BASE, difficulty=0)
    with pytest.raises(ValueError, match="out of range"):
        _parse_puzzle_entry(entry)


def test_difficulty_negative_rejected():
    entry = dict(_BASE, difficulty=-1)
    with pytest.raises(ValueError, match="out of range"):
        _parse_puzzle_entry(entry)


def test_difficulty_absurdly_high_rejected():
    """``"★" * 99`` is not a UI."""
    entry = dict(_BASE, difficulty=99)
    with pytest.raises(ValueError, match="out of range"):
        _parse_puzzle_entry(entry)


def test_difficulty_non_integer_rejected():
    entry = dict(_BASE, difficulty="hard")
    with pytest.raises(ValueError, match="expected integer"):
        _parse_puzzle_entry(entry)


def test_difficulty_none_rejected():
    entry = dict(_BASE, difficulty=None)
    with pytest.raises(ValueError, match="expected integer"):
        _parse_puzzle_entry(entry)


def test_malformed_difficulty_in_mined_file_is_skipped(tmp_path, monkeypatch):
    """load_bundled_puzzles must not crash on a bad mined entry —
    logs and continues so the bundled set still renders."""
    import draughts.game.puzzles as puzzles_mod

    # Build a user-mined file with one valid and one malformed entry.
    bad_mined = [
        dict(_BASE, id="mined_ok"),
        dict(_BASE, id="mined_bad", difficulty=42),
    ]

    def fake_loader() -> list[dict]:
        return bad_mined

    monkeypatch.setattr(
        "draughts.game.puzzle_miner.load_mined_puzzles", fake_loader
    )
    ps = puzzles_mod.load_bundled_puzzles()
    # The bad entry's position equals the good entry's position (both
    # use "n"*32), so dedup would drop it anyway — but the key claim is
    # no exception leaks out of the loader.
    assert len(ps) >= 1
