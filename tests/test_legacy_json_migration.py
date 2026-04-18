"""Tests for the startup legacy-JSON → PDN auto-conversion (#31)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    (tmp_path / "subdir").mkdir()
    return tmp_path


def _write_game_save_json(path: Path, positions: list[str]) -> None:
    data = {
        "difficulty": 3,
        "speed": 1,
        "remind": True,
        "sound_effect": False,
        "pause": 0.75,
        "invert_color": False,
        "positions": positions,
        "replay_positions": positions,
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_no_json_files_returns_empty(tmp_data_dir: Path) -> None:
    from main import _auto_convert_legacy_json

    assert _auto_convert_legacy_json(tmp_data_dir) == []


def test_skips_settings_and_autosave(tmp_data_dir: Path) -> None:
    from main import _auto_convert_legacy_json

    (tmp_data_dir / "settings.json").write_text("{}", encoding="utf-8")
    _write_game_save_json(tmp_data_dir / "autosave.json", ["b" * 32, "b" * 32])

    assert _auto_convert_legacy_json(tmp_data_dir) == []
    assert not (tmp_data_dir / "autosave.pdn").exists()


def test_converts_user_save(tmp_data_dir: Path) -> None:
    from main import _auto_convert_legacy_json

    pos0 = "bbbbbbbbbbbbnnnnnnnnwwwwwwwwwwww"
    pos1 = "bbbbbbbbbbnbnbnnnnnnwwwwwwwwwwww"
    _write_game_save_json(tmp_data_dir / "mygame.json", [pos0, pos1])

    result = _auto_convert_legacy_json(tmp_data_dir)
    assert result == ["mygame.json"]
    assert (tmp_data_dir / "mygame.pdn").exists()
    content = (tmp_data_dir / "mygame.pdn").read_text(encoding="utf-8")
    assert "[GameType" in content


def test_idempotent_skips_if_pdn_exists(tmp_data_dir: Path) -> None:
    from main import _auto_convert_legacy_json

    _write_game_save_json(tmp_data_dir / "g.json", ["b" * 32, "b" * 32])
    (tmp_data_dir / "g.pdn").write_text("[existing]", encoding="utf-8")

    assert _auto_convert_legacy_json(tmp_data_dir) == []
    # existing .pdn must not be overwritten
    assert (tmp_data_dir / "g.pdn").read_text(encoding="utf-8") == "[existing]"


def test_skips_non_gamesave_json(tmp_data_dir: Path) -> None:
    from main import _auto_convert_legacy_json

    (tmp_data_dir / "random.json").write_text('{"foo": "bar"}', encoding="utf-8")
    (tmp_data_dir / "array.json").write_text("[1, 2, 3]", encoding="utf-8")

    assert _auto_convert_legacy_json(tmp_data_dir) == []
    assert not (tmp_data_dir / "random.pdn").exists()
    assert not (tmp_data_dir / "array.pdn").exists()


def test_skips_malformed_json(tmp_data_dir: Path) -> None:
    from main import _auto_convert_legacy_json

    (tmp_data_dir / "bad.json").write_text("{not valid json", encoding="utf-8")

    assert _auto_convert_legacy_json(tmp_data_dir) == []


def test_nonexistent_dir(tmp_path: Path) -> None:
    from main import _auto_convert_legacy_json

    assert _auto_convert_legacy_json(tmp_path / "does_not_exist") == []


def test_converts_multiple_files(tmp_data_dir: Path) -> None:
    from main import _auto_convert_legacy_json

    _write_game_save_json(tmp_data_dir / "a.json", ["b" * 32, "b" * 32])
    _write_game_save_json(tmp_data_dir / "b.json", ["b" * 32, "b" * 32])

    result = _auto_convert_legacy_json(tmp_data_dir)
    assert sorted(result) == ["a.json", "b.json"]
    assert (tmp_data_dir / "a.pdn").exists()
    assert (tmp_data_dir / "b.pdn").exists()


def test_json_to_pdn_preserves_captures(tmp_data_dir: Path) -> None:
    """Regression: legacy JSON → PDN used to silently drop captures.

    The old ``_infer_pdn_move`` classified every vanished piece as a
    source, so any capture (single or multi-jump) had ≥2 "sources" and
    the function returned None — the ply was then dropped from the PDN.
    """
    from draughts.config import BLACK, WHITE
    from draughts.game.board import Board
    from draughts.game.pdn import parse_pdn
    from main import _auto_convert_legacy_json

    # Single-jump capture: white pawn at c3 takes d4 and lands at e5.
    b1 = Board(empty=True)
    b1.grid[5, 2] = WHITE  # c3
    b1.grid[4, 3] = BLACK  # d4
    b2 = b1.copy()
    b2.execute_capture_path([(2, 5), (4, 3)])  # c3 x e5

    _write_game_save_json(
        tmp_data_dir / "capgame.json",
        [b1.to_position_string(), b2.to_position_string()],
    )

    result = _auto_convert_legacy_json(tmp_data_dir)
    assert result == ["capgame.json"]
    text = (tmp_data_dir / "capgame.pdn").read_text(encoding="utf-8")
    games = parse_pdn(text)
    assert len(games) == 1
    assert len(games[0].moves) == 1, f"capture was dropped: {games[0].moves!r}"
    assert "x" in games[0].moves[0], f"expected capture, got {games[0].moves[0]!r}"


def test_json_to_pdn_preserves_multijump(tmp_data_dir: Path) -> None:
    """Regression: multi-jump captures used to lose their intermediate landings.

    A 2-jump chain like ``23x14x5`` was either dropped entirely or
    collapsed to ``23x5`` (intermediate lost), which then fails to
    replay cleanly on the opposite side.
    """
    from draughts.config import BLACK, WHITE
    from draughts.game.board import Board
    from draughts.game.pdn import parse_pdn
    from main import _auto_convert_legacy_json

    b1 = Board(empty=True)
    b1.grid[5, 4] = WHITE  # e3
    b1.grid[4, 3] = BLACK  # d4
    b1.grid[2, 1] = BLACK  # b6
    b2 = b1.copy()
    b2.execute_capture_path([(4, 5), (2, 3), (0, 1)])  # e3 x c5 x a7

    _write_game_save_json(
        tmp_data_dir / "mjg.json",
        [b1.to_position_string(), b2.to_position_string()],
    )

    result = _auto_convert_legacy_json(tmp_data_dir)
    assert result == ["mjg.json"]
    text = (tmp_data_dir / "mjg.pdn").read_text(encoding="utf-8")
    games = parse_pdn(text)
    assert len(games) == 1
    assert len(games[0].moves) == 1, f"multi-jump was dropped: {games[0].moves!r}"
    # Two 'x' separators = 3 square tokens = full intermediate preserved.
    assert games[0].moves[0].count("x") == 2, f"intermediate lost: {games[0].moves[0]!r}"
