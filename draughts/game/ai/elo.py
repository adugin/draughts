"""Elo-based difficulty level definitions.

Maps the six difficulty levels to approximate Elo ratings, search depths,
and human-readable labels.

Calibration methodology — authoritative run 2026-04-19:
    300-game anchor-only gauntlet vs L4 (60 games per pair, alternating
    colours, 4 s/move, max_ply=150, game_timeout=60s). Each non-anchor
    level played 60 games against L4; the anchor was fixed at L4=1700.

    Cross-table (row's score % vs column):
                L4
        L1 →  25.8 %
        L2 →  33.3 %
        L3 →  49.2 %
        L4 →  50.0 %  (anchor)
        L5 →  49.2 %
        L6 →  56.7 %

    Translating to Elo (anchored L4=1700):
        L1: 1517   L2: 1580   L3: 1694
        L4: 1700   L5: 1694   L6: 1747

    Key finding: depth-only scaling produces a COMPRESSED spread —
    ~230 Elo from L1 (d2) to L6 (d8), not the ~1400-Elo spread the
    labels below suggest. L3 (d4), L4 (d5), L5 (d6) all play within
    10 Elo of each other because the tactical ceiling at 4 s/move on
    russian-draughts 8×8 flattens deeper search's payoff. Closing
    this gap would need positional weakening heuristics at low levels,
    not just depth cuts (future milestone — "Elo 2.0").

    The *labels* below remain the user-facing TARGET ratings
    (aspirational, based on the difficulty ladder that beginners
    /amateurs /club players /candidates expect to see); the measured
    numbers above are the honest self-play reality, preserved in the
    ``elo_measured_2026_04_19`` field for logging and future
    regression-tracking.
"""

from __future__ import annotations

# Each entry carries:
#   elo    — target (aspirational) rating shown in the label.
#   elo_measured_2026_04_19 — actual self-play calibration result
#                             (see module docstring).
#   depth  — base alpha-beta depth for that level.
#   label  — display string in the options dialog.
ELO_LEVELS: dict[int, dict[str, object]] = {
    1: {"elo": 800, "elo_measured_2026_04_19": 1517, "depth": 2, "label": "Новичок (~800)"},
    2: {"elo": 1100, "elo_measured_2026_04_19": 1580, "depth": 3, "label": "Любитель (~1100)"},
    3: {"elo": 1400, "elo_measured_2026_04_19": 1694, "depth": 4, "label": "Клубный (~1400)"},
    4: {"elo": 1700, "elo_measured_2026_04_19": 1700, "depth": 5, "label": "Сильный клубный (~1700)"},
    5: {"elo": 2000, "elo_measured_2026_04_19": 1694, "depth": 6, "label": "Кандидат (~2000)"},
    6: {"elo": 2200, "elo_measured_2026_04_19": 1747, "depth": 8, "label": "Мастер (~2200+)"},
}


def level_label(level: int) -> str:
    """Return the display label for a difficulty level (1-6)."""
    entry = ELO_LEVELS.get(level)
    if entry is None:
        return f"Уровень {level}"
    return str(entry["label"])
