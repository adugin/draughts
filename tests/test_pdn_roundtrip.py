"""Tests for PDN 3.0 writer round-trip correctness.

Covers:
- Basic write → parse round-trip
- SetUp/FEN tag support
- Captures (multi-jump with x)
- Mid-game resignation (result without piece exhaustion)
- One game from the real .planning/data/russian_draughts_games.pdn
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from draughts.game.pdn import (
    RUSSIAN_DRAUGHTS_GAMETYPE,
    PDNGame,
    _normalize_date,
    parse_pdn,
    pdngame_to_string,
    write_pdn,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace and strip leading/trailing space."""
    return re.sub(r"\s+", " ", text).strip()


def _games_structurally_equal(a: PDNGame, b: PDNGame) -> bool:
    """Return True if two PDNGames have the same moves and key headers."""
    if a.moves != b.moves:
        return False
    return all(
        a.headers.get(key) == b.headers.get(key)
        for key in ("Result", "White", "Black", "Event", "GameType")
    )


# ---------------------------------------------------------------------------
# Date normalization
# ---------------------------------------------------------------------------


class TestNormalizeDate:
    def test_bare_year(self):
        assert _normalize_date("1949") == "1949.??.??"

    def test_full_date(self):
        assert _normalize_date("1949.01.15") == "1949.01.15"

    def test_unknown_date(self):
        assert _normalize_date("?") == "????.??.??"

    def test_already_unknown_full(self):
        assert _normalize_date("????.??.??") == "????.??.??"

    def test_dash_separated(self):
        assert _normalize_date("2006-03-17") == "2006.03.17"


# ---------------------------------------------------------------------------
# 1. Basic round-trip
# ---------------------------------------------------------------------------


class TestBasicRoundTrip:
    def _make_game(self) -> PDNGame:
        return PDNGame(
            headers={
                "Event": "Test Tournament",
                "Site": "Moscow",
                "Date": "2024.01.01",
                "Round": "1",
                "White": "Ivanov",
                "Black": "Petrov",
                "Result": "1-0",
            },
            moves=["22-17", "11-16", "17-13", "16-21", "23-19"],
        )

    def test_write_contains_headers(self):
        game = self._make_game()
        text = pdngame_to_string(game)
        assert '[Event "Test Tournament"]' in text
        assert '[White "Ivanov"]' in text
        assert '[Black "Petrov"]' in text
        assert '[Result "1-0"]' in text

    def test_write_contains_gametype(self):
        game = self._make_game()
        text = pdngame_to_string(game)
        assert f'[GameType "{RUSSIAN_DRAUGHTS_GAMETYPE}"]' in text

    def test_write_contains_moves(self):
        game = self._make_game()
        text = pdngame_to_string(game)
        assert "22-17" in text
        assert "11-16" in text

    def test_write_contains_result_token(self):
        game = self._make_game()
        text = pdngame_to_string(game)
        # result token must appear in the movetext (not just the header)
        movetext_part = text.split("\n\n", 1)[-1]
        assert "1-0" in movetext_part

    def test_canonical_header_order(self):
        game = self._make_game()
        text = pdngame_to_string(game)
        lines = [ln for ln in text.split("\n") if ln.startswith("[")]
        tags = [re.match(r'\[(\w+)', ln).group(1) for ln in lines]
        canonical = ["Event", "Site", "Date", "Round", "White", "Black", "Result", "GameType"]
        present = [t for t in canonical if t in tags]
        order_in_output = [t for t in tags if t in canonical]
        assert order_in_output == present

    def test_round_trip_moves_preserved(self):
        game = self._make_game()
        text = write_pdn([game])
        [parsed] = parse_pdn(text)
        assert parsed.moves == game.moves

    def test_round_trip_result_preserved(self):
        game = self._make_game()
        text = write_pdn([game])
        [parsed] = parse_pdn(text)
        assert parsed.result == game.result

    def test_multi_game_round_trip(self):
        g1 = self._make_game()
        g2 = PDNGame(
            headers={"White": "A", "Black": "B", "Result": "0-1"},
            moves=["23-18", "10-14", "27-23"],
        )
        text = write_pdn([g1, g2])
        parsed = parse_pdn(text)
        assert len(parsed) == 2
        assert parsed[0].moves == g1.moves
        assert parsed[1].moves == g2.moves


# ---------------------------------------------------------------------------
# 2. SetUp / FEN tags
# ---------------------------------------------------------------------------


class TestSetUpFen:
    def test_setup_fen_emitted(self):
        game = PDNGame(
            headers={
                "Event": "Puzzle",
                "White": "?",
                "Black": "?",
                "Result": "*",
                "SetUp": "1",
                "FEN": "W:W21,22,23,24,25,26,27,28,29,30,31,32:B1,2,3,4,5,6,7,8,9,10,11,12",
            },
            moves=[],
        )
        text = pdngame_to_string(game)
        assert '[SetUp "1"]' in text
        assert "[FEN" in text

    def test_setup_fen_after_canonical_tags(self):
        game = PDNGame(
            headers={
                "Event": "Puzzle",
                "White": "?",
                "Black": "?",
                "Result": "*",
                "SetUp": "1",
                "FEN": "W:WK1:B32",
            },
            moves=["1-5"],
        )
        text = pdngame_to_string(game)
        lines = [ln for ln in text.split("\n") if ln.startswith("[")]
        tags = [re.match(r'\[(\w+)', ln).group(1) for ln in lines]
        result_idx = tags.index("Result")
        setup_idx = tags.index("SetUp")
        fen_idx = tags.index("FEN")
        assert setup_idx > result_idx
        assert fen_idx > setup_idx

    def test_round_trip_with_fen(self):
        fen = "W:WK1,5:B32,28"
        game = PDNGame(
            headers={
                "White": "?",
                "Black": "?",
                "Result": "1-0",
                "SetUp": "1",
                "FEN": fen,
            },
            moves=["1-6", "32-27"],
        )
        text = write_pdn([game])
        [parsed] = parse_pdn(text)
        assert parsed.headers.get("FEN") == fen
        assert parsed.headers.get("SetUp") == "1"
        assert parsed.moves == game.moves


# ---------------------------------------------------------------------------
# 3. Captures (multi-jump)
# ---------------------------------------------------------------------------


class TestCaptures:
    def test_single_capture_round_trip(self):
        game = PDNGame(
            headers={"White": "A", "Black": "B", "Result": "*"},
            moves=["22-17", "11-16", "17x11"],
        )
        text = write_pdn([game])
        [parsed] = parse_pdn(text)
        assert "17x11" in parsed.moves

    def test_multi_jump_capture_round_trip(self):
        # Multi-jump stored as separate moves in the games list
        game = PDNGame(
            headers={"White": "A", "Black": "B", "Result": "1-0"},
            moves=["22-17", "11-16", "17x8x1"],
        )
        text = write_pdn([game])
        [parsed] = parse_pdn(text)
        assert "17x8x1" in parsed.moves

    def test_capture_preserved_in_movetext(self):
        game = PDNGame(
            headers={"Result": "*"},
            moves=["9x18x27"],
        )
        text = pdngame_to_string(game)
        assert "9x18x27" in text


# ---------------------------------------------------------------------------
# 4. Mid-game resignation (result token without piece exhaustion)
# ---------------------------------------------------------------------------


class TestResignation:
    def test_resignation_result_in_header(self):
        game = PDNGame(
            headers={
                "Event": "Club Game",
                "White": "Smith",
                "Black": "Jones",
                "Result": "0-1",
            },
            moves=["22-17", "11-16", "17-13", "9-14"],
        )
        text = pdngame_to_string(game)
        assert '[Result "0-1"]' in text

    def test_resignation_result_token_in_movetext(self):
        game = PDNGame(
            headers={"Result": "0-1"},
            moves=["22-17", "11-16"],
        )
        text = pdngame_to_string(game)
        movetext = text.split("\n\n", 1)[-1]
        assert "0-1" in movetext

    def test_asterisk_result_for_ongoing(self):
        game = PDNGame(
            headers={"Result": "*"},
            moves=["22-17"],
        )
        text = pdngame_to_string(game)
        assert '[Result "*"]' in text
        movetext = text.split("\n\n", 1)[-1]
        assert "*" in movetext

    def test_round_trip_resignation(self):
        game = PDNGame(
            headers={"White": "A", "Black": "B", "Result": "0-1"},
            moves=["22-17", "11-16", "23-18"],
        )
        text = write_pdn([game])
        [parsed] = parse_pdn(text)
        assert parsed.result == "0-1"
        assert parsed.moves == game.moves


# ---------------------------------------------------------------------------
# 5. Real game from the data file
# ---------------------------------------------------------------------------


class TestRealGame:
    _DATA_FILE = (
        Path(__file__).parent.parent / ".planning" / "data" / "russian_draughts_games.pdn"
    )

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / ".planning" / "data" / "russian_draughts_games.pdn").exists(),
        reason="Data file not present",
    )
    def test_first_game_round_trip(self):
        """Load first game, write it, parse again — structural equality."""
        games = parse_pdn(self._DATA_FILE.read_text(encoding="utf-8"))
        assert len(games) >= 1
        original = games[0]

        text = write_pdn([original])
        [reparsed] = parse_pdn(text)

        assert reparsed.moves == original.moves, (
            f"Moves differ:\n  original={original.moves}\n  reparsed={reparsed.moves}"
        )
        assert reparsed.result == original.result

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / ".planning" / "data" / "russian_draughts_games.pdn").exists(),
        reason="Data file not present",
    )
    def test_all_games_round_trip(self):
        """All games round-trip structurally."""
        original_games = parse_pdn(self._DATA_FILE.read_text(encoding="utf-8"))
        assert len(original_games) >= 5

        text = write_pdn(original_games)
        reparsed_games = parse_pdn(text)

        assert len(reparsed_games) == len(original_games)
        for i, (orig, rep) in enumerate(zip(original_games, reparsed_games, strict=True)):
            assert orig.moves == rep.moves, f"Game {i}: moves differ"
            assert orig.result == rep.result, f"Game {i}: result differs"


# ---------------------------------------------------------------------------
# 6. Line-wrapping
# ---------------------------------------------------------------------------


class TestLineWrapping:
    def test_long_game_wraps_at_80(self):
        """Movetext lines must not exceed 80 characters."""
        # 40 moves ~ typical game length
        moves = [f"{20 + i}-{19 + i}" for i in range(40)]
        game = PDNGame(
            headers={"Result": "*"},
            moves=moves,
        )
        text = pdngame_to_string(game)
        # Find the movetext section (after the blank line following headers)
        in_headers = True
        for line in text.split("\n"):
            if in_headers:
                if not line.strip():
                    in_headers = False
                continue
            assert len(line) <= 80, f"Line too long ({len(line)}): {line!r}"


# ---------------------------------------------------------------------------
# 7. GameType default injection
# ---------------------------------------------------------------------------


class TestGameType:
    def test_gametype_injected_when_missing(self):
        game = PDNGame(
            headers={"White": "A", "Black": "B", "Result": "*"},
            moves=["22-17"],
        )
        text = pdngame_to_string(game)
        assert f'[GameType "{RUSSIAN_DRAUGHTS_GAMETYPE}"]' in text

    def test_gametype_preserved_when_set(self):
        game = PDNGame(
            headers={"Result": "*", "GameType": RUSSIAN_DRAUGHTS_GAMETYPE},
            moves=[],
        )
        text = pdngame_to_string(game)
        count = text.count("[GameType")
        assert count == 1

    def test_gametype_value_exact(self):
        """The GameType tag must be exactly the Russian 8x8 identifier."""
        assert RUSSIAN_DRAUGHTS_GAMETYPE == "25,W,8,8,A1,0"
