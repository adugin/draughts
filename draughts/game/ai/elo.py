"""Elo-based difficulty level definitions.

Maps the six difficulty levels to approximate Elo ratings, search depths,
and human-readable labels.

Calibration notes (#30, 2026-04-18):
    An anchor-only gauntlet vs L4 (6 games per pair, 30 total games)
    produced the following observed ratings — anchored to L4=1700:
        L1: 1509, L2: 1700, L3: 1700, L4: 1700, L5: 1642, L6: 1758
    The spread is much narrower than the labels below suggest. However
    6 games per pair has wide error bars (±~200 Elo at 50% rate), so
    these numbers are directional only. A 100+ game per-pair tournament
    is still needed to finalise authoritative numbers — the labels below
    remain the USER-FACING targets, not the measured strength. Users
    who want a challenge should select L5/L6 expecting depth-driven
    tactical strength, not strict Elo accuracy.
"""

from __future__ import annotations

# Each entry: elo (approximate strength), depth (base search depth),
# label (display string shown in the options dialog).
ELO_LEVELS: dict[int, dict[str, object]] = {
    1: {"elo": 800, "depth": 2, "label": "Новичок (~800)"},
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
    return str(entry["label"])
