"""Elo-based difficulty level definitions.

Maps the six difficulty levels to approximate Elo ratings, search depths,
and human-readable labels.

NOTE: Elo numbers are placeholder calibration to be refined by self-play
tournaments (D6 in DECISIONS.md). Initial values are reasonable estimates
and will be updated after running tournament gauntlets in M1.
"""

from __future__ import annotations

# Each entry: elo (approximate strength), depth (base search depth),
# label (display string shown in the options dialog).
ELO_LEVELS: dict[int, dict] = {
    1: {"elo": 800,  "depth": 2, "label": "Новичок (~800)"},
    2: {"elo": 1100, "depth": 3, "label": "Любитель (~1100)"},
    3: {"elo": 1400, "depth": 4, "label": "Клубный (~1400)"},
    4: {"elo": 1700, "depth": 5, "label": "Сильный клубный (~1700)"},
    5: {"elo": 2000, "depth": 6, "label": "Кандидат (~2000)"},
    6: {"elo": 2200, "depth": 8, "label": "Мастер (~2200+)"},
}


def level_label(level: int) -> str:
    """Return the display label for a difficulty level (1-6)."""
    entry = ELO_LEVELS.get(level)
    if entry is None:
        return f"Уровень {level}"
    return entry["label"]
