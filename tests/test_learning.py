"""Tests for the AI learning database."""

import pytest

from draughts.game.learning import LearningDB, invertstr

INITIAL_POS = "bbbbbbbbbbbbnnnnnnnnwwwwwwwwwwww"
MID_GAME_POS = "bbbbbbbbbbbnnnnnnnnnwwwwwwwwwwww"


class TestInvertStr:
    def test_invert_initial(self):
        inverted = invertstr(INITIAL_POS)
        assert inverted == "wwwwwwwwwwwwnnnnnnnnbbbbbbbbbbbb"

    def test_invert_empty(self):
        empty = "n" * 32
        assert invertstr(empty) == empty

    def test_invert_kings(self):
        pos = "BnnnnnnnnnnnnnnnnnnnnnnnnnnnnnWn"
        assert invertstr(pos) == "WnnnnnnnnnnnnnnnnnnnnnnnnnnnnnBn"

    def test_double_invert_is_identity(self):
        assert invertstr(invertstr(INITIAL_POS)) == INITIAL_POS

    def test_invert_mixed(self):
        pos = "bBwWnnnnnnnnnnnnnnnnnnnnnnnnnnnn"
        assert invertstr(pos) == "wWbBnnnnnnnnnnnnnnnnnnnnnnnnnnnn"


class TestLearningDBBasic:
    def test_unknown_returns_none(self, tmp_path):
        db = LearningDB(tmp_path / "learn.json")
        assert db.search(INITIAL_POS) is None

    def test_add_good_and_search(self, tmp_path):
        db = LearningDB(tmp_path / "learn.json")
        db.add_good(INITIAL_POS)
        assert db.search(INITIAL_POS) == "good"

    def test_add_bad_and_search(self, tmp_path):
        db = LearningDB(tmp_path / "learn.json")
        db.add_bad(MID_GAME_POS)
        assert db.search(MID_GAME_POS) == "bad"

    def test_good_takes_precedence(self, tmp_path):
        db = LearningDB(tmp_path / "learn.json")
        db.add_bad(INITIAL_POS)
        db.add_good(INITIAL_POS)
        assert db.search(INITIAL_POS) == "good"

    def test_invalid_position_length(self, tmp_path):
        db = LearningDB(tmp_path / "learn.json")
        with pytest.raises(ValueError):
            db.add_good("short")
        with pytest.raises(ValueError):
            db.add_bad("short")


class TestLearningDBPersistence:
    def test_save_and_reload(self, tmp_path):
        path = tmp_path / "learn.json"
        db = LearningDB(path)
        db.add_good(INITIAL_POS)
        db.add_bad(MID_GAME_POS)
        db.save()

        db2 = LearningDB(path)
        assert db2.search(INITIAL_POS) == "good"
        assert db2.search(MID_GAME_POS) == "bad"
        assert db2.search("n" * 32) is None

    def test_empty_db_creates_no_file(self, tmp_path):
        path = tmp_path / "learn.json"
        LearningDB(path)  # just construct, never save
        assert not path.exists()

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "learn.json"
        db = LearningDB(path)
        db.add_good(INITIAL_POS)
        db.save()

        db2 = LearningDB(path)
        assert db2.search(INITIAL_POS) == "good"

    def test_multiple_positions(self, tmp_path):
        path = tmp_path / "learn.json"
        db = LearningDB(path)
        positions = [
            "bbbbbbbbbbbbnnnnnnnnwwwwwwwwwwww",
            "bbbbbbbbbbbnnnnnnnnnwwwwwwwwwwww",
            "bbbbbbbbbbnnnnnnnnnwwwwwwwwwwwwn",
        ]
        for pos in positions:
            db.add_good(pos)
        db.save()

        db2 = LearningDB(path)
        for pos in positions:
            assert db2.search(pos) == "good"
