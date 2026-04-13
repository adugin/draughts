"""Game save/load and session history for Russian draughts.

Original Pascal format used plain text .sav files.
This implementation uses JSON for better structure and extensibility.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class GameSave:
    """Represents a saved game state."""

    difficulty: int = 1  # 1-6 (was 1-3 in legacy saves)
    speed: int = 1  # 1-3
    remind: bool = True  # hint for mandatory captures
    sound_effect: bool = False
    pause: float = 0.75  # animation delay multiplier (0.0-5.0)
    invert_color: bool = False  # True = player was playing as black
    positions: list[str] = field(default_factory=list)  # history of 32-char board states
    replay_positions: list[str] = field(default_factory=list)  # same positions for playback

    def __post_init__(self) -> None:
        if not 1 <= self.difficulty <= 6:
            raise ValueError(f"difficulty must be 1-6, got {self.difficulty}")
        if not 1 <= self.speed <= 3:
            raise ValueError(f"speed must be 1-3, got {self.speed}")
        if not 0.0 <= self.pause <= 5.0:
            raise ValueError(f"pause must be 0.0-5.0, got {self.pause}")
        for i, pos in enumerate(self.positions):
            if len(pos) != 32:
                raise ValueError(f"positions[{i}] must be 32 chars, got {len(pos)}")
        for i, pos in enumerate(self.replay_positions):
            if len(pos) != 32:
                raise ValueError(f"replay_positions[{i}] must be 32 chars, got {len(pos)}")


def save_game(filepath: str | Path, game_save: GameSave) -> None:
    """Save game state to a JSON file."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(game_save)
    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_game(filepath: str | Path) -> GameSave:
    """Load game state from a JSON file.

    Raises:
        FileNotFoundError: if the file does not exist.
        json.JSONDecodeError: if the file is not valid JSON.
        ValueError: if the data fails validation.
    """
    filepath = Path(filepath)
    data = json.loads(filepath.read_text(encoding="utf-8"))
    # Backward compatibility: old saves used "movie" key
    if "movie" in data and "replay_positions" not in data:
        data["replay_positions"] = data.pop("movie")
    # Old saves don't have invert_color — default to False
    data.setdefault("invert_color", False)
    return GameSave(**data)


def autosave(filepath: str | Path, game_save: GameSave) -> None:
    """Quick save for auto-recovery. Same format as save_game."""
    save_game(filepath, game_save)


def save_history(filepath: str | Path, last_filename: str, pause: float) -> None:
    """Save session info (replaces original draughts.his).

    Stores the last opened save filename and the pause setting
    so the game can resume where the player left off.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "last_filename": last_filename,
        "pause": pause,
    }
    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_history(filepath: str | Path) -> tuple[str, float]:
    """Load session info.

    Returns:
        (last_filename, pause) tuple.

    Raises:
        FileNotFoundError: if the file does not exist.
    """
    filepath = Path(filepath)
    data = json.loads(filepath.read_text(encoding="utf-8"))
    return data["last_filename"], data["pause"]
