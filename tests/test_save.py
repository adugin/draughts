"""Tests for game save/load and session history."""

import pytest
from draughts.game.save import (
    GameSave,
    autosave,
    load_game,
    load_history,
    save_game,
    save_history,
)

INITIAL_POS = "bbbbbbbbbbbbnnnnnnnnwwwwwwwwwwww"


class TestGameSaveValidation:
    def test_defaults(self):
        gs = GameSave()
        assert gs.difficulty == 1
        assert gs.speed == 1
        assert gs.remind is True
        assert gs.sound_effect is False
        assert gs.pause == 0.75
        assert gs.positions == []
        assert gs.replay_positions == []

    def test_invalid_difficulty(self):
        with pytest.raises(ValueError, match="difficulty"):
            GameSave(difficulty=7)  # valid range is now 1-6

    def test_invalid_speed(self):
        with pytest.raises(ValueError, match="speed"):
            GameSave(speed=0)

    def test_invalid_pause(self):
        with pytest.raises(ValueError, match="pause"):
            GameSave(pause=10.0)

    def test_invalid_position_length(self):
        with pytest.raises(ValueError, match="positions"):
            GameSave(positions=["short"])


class TestSaveLoadRoundTrip:
    def test_round_trip(self, tmp_path):
        gs = GameSave(
            difficulty=2,
            speed=3,
            remind=False,
            sound_effect=True,
            pause=1.5,
            positions=[INITIAL_POS, "bbbbbbbbbbbnnnnnnnnnwwwwwwwwwwww"],
            replay_positions=[INITIAL_POS],
        )
        path = tmp_path / "test.json"
        save_game(path, gs)
        loaded = load_game(path)

        assert loaded.difficulty == 2
        assert loaded.speed == 3
        assert loaded.remind is False
        assert loaded.sound_effect is True
        assert loaded.pause == 1.5
        assert loaded.positions == gs.positions
        assert loaded.replay_positions == gs.replay_positions

    def test_empty_save(self, tmp_path):
        gs = GameSave()
        path = tmp_path / "empty.json"
        save_game(path, gs)
        loaded = load_game(path)
        assert loaded.positions == []
        assert loaded.replay_positions == []

    def test_load_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_game(tmp_path / "does_not_exist.json")

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "save.json"
        gs = GameSave()
        save_game(path, gs)
        loaded = load_game(path)
        assert loaded.difficulty == gs.difficulty


class TestAutosave:
    def test_autosave_round_trip(self, tmp_path):
        gs = GameSave(difficulty=3, speed=2, positions=[INITIAL_POS])
        path = tmp_path / "autosave.json"
        autosave(path, gs)
        loaded = load_game(path)
        assert loaded.difficulty == 3
        assert loaded.speed == 2
        assert loaded.positions == [INITIAL_POS]


class TestHistory:
    def test_history_round_trip(self, tmp_path):
        path = tmp_path / "history.json"
        save_history(path, "my_save.json", 1.25)
        filename, pause = load_history(path)
        assert filename == "my_save.json"
        assert pause == 1.25

    def test_history_load_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_history(tmp_path / "no_such_history.json")
