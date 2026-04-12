"""Tests for puzzle auto-mining from analyzed games (ROADMAP #22).

Covers:
  1. test_mine_from_blunder_game — one ?? blunder yields one puzzle
  2. test_no_puzzles_from_clean_game — no blunders → empty list
  3. test_difficulty_mapping — delta thresholds map to correct difficulties
  4. test_mined_puzzles_merge_with_bundled — dedup in load_bundled_puzzles
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from draughts.game.puzzle_miner import (
    _delta_to_difficulty,
    append_mined_puzzles,
    load_mined_puzzles,
    mine_puzzles_from_game,
    save_mined_puzzles,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_annotation(
    ply: int,
    annotation: str,
    delta_cp: float = 0.0,
    best_notation: str = "c3:e5",
):
    """Build a lightweight MoveAnnotation-like object for testing."""
    return SimpleNamespace(
        ply=ply,
        annotation=annotation,
        delta_cp=delta_cp,
        best_notation=best_notation,
        notation="d4-e5",
    )


# A valid 32-char position string (standard start position).
_START_POS = "bbbbbbbbbbbbnnnnnnnnwwwwwwwwwwww"

# A second distinct position (minor variation).
_OTHER_POS = "bbbbbbbbbbbbnnnnnnnnnwwwwwwwwwww"


# ---------------------------------------------------------------------------
# 1. mine_from_blunder_game
# ---------------------------------------------------------------------------

class TestMineFromBlunderGame:
    """A game with a single blunder at ply 2 yields exactly one puzzle."""

    def _make_positions(self):
        # 4 positions: plies 0,1,2,3 recorded as pos[0..3]
        return [_START_POS, _START_POS, _OTHER_POS, _START_POS]

    def _make_annotations(self):
        return [
            _make_annotation(0, "!", delta_cp=0.0),
            _make_annotation(1, "", delta_cp=10.0),
            _make_annotation(2, "??", delta_cp=500.0, best_notation="c3:e5"),
            _make_annotation(3, "!", delta_cp=0.0),
        ]

    def test_one_puzzle_extracted(self):
        puzzles = mine_puzzles_from_game(
            self._make_positions(),
            self._make_annotations(),
        )
        assert len(puzzles) == 1

    def test_puzzle_position_is_before_blunder(self):
        positions = self._make_positions()
        annotations = self._make_annotations()
        puzzles = mine_puzzles_from_game(positions, annotations)
        # Ply 2 blunder → position is positions[2]
        assert puzzles[0]["position"] == positions[2]

    def test_solver_is_opponent_of_blunderer(self):
        """Ply 2 → white blundered (even ply) → black solves."""
        puzzles = mine_puzzles_from_game(
            self._make_positions(),
            self._make_annotations(),
        )
        assert puzzles[0]["turn"] == "black"

    def test_best_move_preserved(self):
        puzzles = mine_puzzles_from_game(
            self._make_positions(),
            self._make_annotations(),
        )
        assert puzzles[0]["best_move"] == "c3:e5"

    def test_solution_sequence_contains_best_move(self):
        puzzles = mine_puzzles_from_game(
            self._make_positions(),
            self._make_annotations(),
        )
        assert puzzles[0]["solution_sequence"] == ["c3:e5"]

    def test_source_is_auto_mined(self):
        puzzles = mine_puzzles_from_game(
            self._make_positions(),
            self._make_annotations(),
        )
        assert puzzles[0]["source"] == "auto_mined"

    def test_category_is_combination_for_capture(self):
        puzzles = mine_puzzles_from_game(
            self._make_positions(),
            self._make_annotations(),
        )
        # best_notation contains ":" → combination_2cap
        assert puzzles[0]["category"] == "combination_2cap"

    def test_category_is_endgame_for_quiet_move(self):
        annotations = [
            _make_annotation(2, "??", delta_cp=500.0, best_notation="c3-d4"),
        ]
        positions = self._make_positions()
        puzzles = mine_puzzles_from_game(positions, annotations)
        assert puzzles[0]["category"] == "endgame"

    def test_black_blunder_solver_is_white(self):
        """Ply 1 → black blundered (odd ply) → white solves."""
        positions = [_START_POS, _OTHER_POS, _START_POS]
        annotations = [
            _make_annotation(1, "??", delta_cp=500.0, best_notation="c3:e5"),
        ]
        puzzles = mine_puzzles_from_game(positions, annotations)
        assert puzzles[0]["turn"] == "white"

    def test_duplicate_positions_deduplicated(self):
        """Two blunders on the same position → only one puzzle."""
        positions = [_START_POS, _OTHER_POS, _OTHER_POS, _START_POS]
        annotations = [
            _make_annotation(1, "??", delta_cp=500.0, best_notation="c3:e5"),
            _make_annotation(2, "??", delta_cp=600.0, best_notation="a3:c5"),
        ]
        puzzles = mine_puzzles_from_game(positions, annotations)
        assert len(puzzles) == 1

    def test_no_best_notation_skipped(self):
        """Blunder with no best_notation (dash) is skipped."""
        positions = [_START_POS, _OTHER_POS]
        annotations = [
            _make_annotation(1, "??", delta_cp=500.0, best_notation="—"),
        ]
        puzzles = mine_puzzles_from_game(positions, annotations)
        assert puzzles == []

    def test_empty_best_notation_skipped(self):
        positions = [_START_POS, _OTHER_POS]
        annotations = [
            _make_annotation(1, "??", delta_cp=500.0, best_notation=""),
        ]
        puzzles = mine_puzzles_from_game(positions, annotations)
        assert puzzles == []


# ---------------------------------------------------------------------------
# 2. no_puzzles_from_clean_game
# ---------------------------------------------------------------------------

class TestNoPuzzlesFromCleanGame:
    """Games with no blunders produce no puzzles."""

    def test_empty_positions(self):
        result = mine_puzzles_from_game([], [])
        assert result == []

    def test_no_blunders(self):
        positions = [_START_POS, _OTHER_POS, _START_POS]
        annotations = [
            _make_annotation(0, "!", delta_cp=0.0),
            _make_annotation(1, "?!", delta_cp=80.0),
            _make_annotation(2, "?", delta_cp=200.0),
        ]
        result = mine_puzzles_from_game(positions, annotations)
        assert result == []

    def test_mistake_below_min_delta_skipped(self):
        """A ?? annotation that is below min_delta_cp threshold is skipped."""
        positions = [_START_POS, _OTHER_POS]
        annotations = [
            _make_annotation(1, "??", delta_cp=300.0),
        ]
        # Custom min_delta higher than 300
        result = mine_puzzles_from_game(positions, annotations, min_delta_cp=400)
        assert result == []

    def test_single_position_game(self):
        result = mine_puzzles_from_game([_START_POS], [])
        assert result == []


# ---------------------------------------------------------------------------
# 3. difficulty_mapping
# ---------------------------------------------------------------------------

class TestDifficultyMapping:
    """_delta_to_difficulty maps delta ranges to difficulty levels."""

    def test_400_to_600_is_difficulty_2(self):
        assert _delta_to_difficulty(400) == 2
        assert _delta_to_difficulty(500) == 2
        assert _delta_to_difficulty(599) == 2

    def test_600_to_1000_is_difficulty_3(self):
        assert _delta_to_difficulty(600) == 3
        assert _delta_to_difficulty(800) == 3
        assert _delta_to_difficulty(999) == 3

    def test_above_1000_is_difficulty_4(self):
        assert _delta_to_difficulty(1000) == 4
        assert _delta_to_difficulty(1500) == 4
        assert _delta_to_difficulty(9999) == 4

    def test_puzzle_difficulty_field_matches_delta(self):
        positions = [_START_POS, _OTHER_POS]
        for delta, expected_diff in [(450, 2), (700, 3), (1200, 4)]:
            annotations = [
                _make_annotation(1, "??", delta_cp=float(delta), best_notation="c3:e5"),
            ]
            puzzles = mine_puzzles_from_game(positions, annotations)
            assert len(puzzles) == 1, f"Expected 1 puzzle for delta={delta}"
            assert puzzles[0]["difficulty"] == expected_diff, (
                f"delta={delta} → expected difficulty {expected_diff}, "
                f"got {puzzles[0]['difficulty']}"
            )


# ---------------------------------------------------------------------------
# 4. mined_puzzles_merge_with_bundled
# ---------------------------------------------------------------------------

class TestMinedPuzzlesMergeWithBundled:
    """load_bundled_puzzles() merges bundled + mined and deduplicates."""

    def _fake_mined(self, positions: list[str]) -> list[dict]:
        """Return fake mined puzzle dicts for the given position strings."""
        return [
            {
                "id": f"mined_{i:03d}_{p[:8]}",
                "category": "combination_2cap",
                "position": p,
                "turn": "white",
                "best_move": "c3:e5",
                "solution_sequence": ["c3:e5"],
                "difficulty": 2,
                "source": "auto_mined",
                "description": "Test mined puzzle",
            }
            for i, p in enumerate(positions)
        ]

    def test_unique_mined_puzzles_added(self, tmp_path):
        """Mined puzzles with positions not in the bundled set are included."""
        from draughts.game.puzzles import load_bundled_puzzles

        mined_file = tmp_path / "mined_puzzles.json"
        # Use a position string that is very unlikely to appear in the bundled set.
        unique_pos = "n" * 32
        mined_file.write_text(
            json.dumps(self._fake_mined([unique_pos])), encoding="utf-8"
        )

        with patch("draughts.game.puzzle_miner.MINED_PUZZLES_PATH", mined_file):
            ps = load_bundled_puzzles()

        positions_in_set = {p.position for p in ps}
        assert unique_pos in positions_in_set, (
            "Unique mined puzzle position should be present in merged PuzzleSet"
        )

    def test_duplicate_mined_position_not_added(self, tmp_path):
        """A mined puzzle whose position already exists in bundled is skipped."""
        from draughts.game.puzzles import load_bundled_puzzles

        # Load the real bundled set to find an existing position.
        bundled = load_bundled_puzzles()
        existing_pos = list(bundled)[0].position

        mined_file = tmp_path / "mined_puzzles.json"
        mined_file.write_text(
            json.dumps(self._fake_mined([existing_pos])), encoding="utf-8"
        )

        original_len = len(bundled)

        with patch("draughts.game.puzzle_miner.MINED_PUZZLES_PATH", mined_file):
            ps = load_bundled_puzzles()

        # Should NOT grow — duplicate position was filtered out.
        assert len(ps) == original_len, (
            f"Expected {original_len} puzzles (duplicate skipped), got {len(ps)}"
        )

    def test_no_mined_file_loads_only_bundled(self, tmp_path):
        """When no mined file exists, bundled count is unchanged."""
        from draughts.game.puzzles import load_bundled_puzzles

        nonexistent = tmp_path / "nonexistent_mined.json"

        with patch("draughts.game.puzzle_miner.MINED_PUZZLES_PATH", nonexistent):
            ps = load_bundled_puzzles()

        assert len(ps) == 30

    def test_malformed_mined_file_does_not_crash(self, tmp_path):
        """A malformed mined file is silently ignored; bundled puzzles still load."""
        from draughts.game.puzzles import load_bundled_puzzles

        bad_file = tmp_path / "mined_puzzles.json"
        bad_file.write_text("NOT_VALID_JSON", encoding="utf-8")

        with patch("draughts.game.puzzle_miner.MINED_PUZZLES_PATH", bad_file):
            ps = load_bundled_puzzles()

        assert len(ps) == 30


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

class TestPersistenceHelpers:
    """load/save/append mined puzzles round-trip correctly."""

    def _sample_puzzles(self, count: int = 2) -> list[dict]:
        return [
            {
                "id": f"mined_{i:03d}",
                "category": "combination_2cap",
                "position": "n" * 31 + str(i % 10),
                "turn": "white",
                "best_move": "c3:e5",
                "solution_sequence": ["c3:e5"],
                "difficulty": 2,
                "source": "auto_mined",
                "description": f"Test puzzle {i}",
            }
            for i in range(count)
        ]

    def test_save_and_load_roundtrip(self, tmp_path):
        mined_path = tmp_path / "mined_puzzles.json"
        puzzles = self._sample_puzzles(3)

        with patch("draughts.game.puzzle_miner.MINED_PUZZLES_PATH", mined_path):
            save_mined_puzzles(puzzles)
            loaded = load_mined_puzzles()

        assert len(loaded) == 3
        assert loaded[0]["id"] == puzzles[0]["id"]

    def test_load_missing_returns_empty(self, tmp_path):
        mined_path = tmp_path / "nonexistent.json"
        with patch("draughts.game.puzzle_miner.MINED_PUZZLES_PATH", mined_path):
            result = load_mined_puzzles()
        assert result == []

    def test_append_adds_new_puzzles(self, tmp_path):
        mined_path = tmp_path / "mined_puzzles.json"
        existing = self._sample_puzzles(2)

        with patch("draughts.game.puzzle_miner.MINED_PUZZLES_PATH", mined_path):
            save_mined_puzzles(existing)
            new_puzzle = {
                "id": "mined_NEW",
                "category": "endgame",
                "position": "w" * 32,
                "turn": "black",
                "best_move": "a3-b4",
                "solution_sequence": ["a3-b4"],
                "difficulty": 2,
                "source": "auto_mined",
                "description": "New puzzle",
            }
            added = append_mined_puzzles([new_puzzle])
            loaded = load_mined_puzzles()

        assert added == 1
        assert len(loaded) == 3

    def test_append_deduplicates_by_position(self, tmp_path):
        """Appending a puzzle whose position already exists does not duplicate."""
        mined_path = tmp_path / "mined_puzzles.json"
        existing = self._sample_puzzles(2)

        with patch("draughts.game.puzzle_miner.MINED_PUZZLES_PATH", mined_path):
            save_mined_puzzles(existing)
            # Try to add a puzzle with the same position as existing[0].
            duplicate = {
                **existing[0],
                "id": "mined_DUPE",
                "description": "Duplicate position",
            }
            added = append_mined_puzzles([duplicate])
            loaded = load_mined_puzzles()

        assert added == 0
        assert len(loaded) == 2
