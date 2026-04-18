"""Tests for PDN → book importer (#39)."""

from __future__ import annotations

from pathlib import Path

from draughts.tools.import_book_from_pdn import _parse_pdn_move, import_games


def _write_pdn(tmp_path: Path, games_moves: list[list[str]]) -> Path:
    parts = []
    for i, moves in enumerate(games_moves):
        parts.append(f'[Event "Game {i}"]')
        parts.append('[Site "Test"]')
        parts.append('[Date "2026.04.18"]')
        parts.append('[Round "1"]')
        parts.append('[White "A"]')
        parts.append('[Black "B"]')
        parts.append('[Result "*"]')
        parts.append('[GameType "25"]')
        parts.append("")
        move_text = ""
        for j in range(0, len(moves), 2):
            move_text += f"{j // 2 + 1}. {moves[j]}"
            if j + 1 < len(moves):
                move_text += f" {moves[j + 1]}"
            move_text += " "
        move_text += "*"
        parts.append(move_text)
        parts.append("")
    p = tmp_path / "in.pdn"
    p.write_text("\n".join(parts), encoding="utf-8")
    return p


def test_parse_simple_move():
    kind, path = _parse_pdn_move("22-17")
    assert kind == "move"
    assert len(path) == 2


def test_parse_capture_chain():
    kind, path = _parse_pdn_move("9x18x27")
    assert kind == "capture"
    assert len(path) == 3


def test_import_single_game_adds_positions(tmp_path: Path):
    from draughts.game.pdn import load_pdn_file

    pdn = _write_pdn(tmp_path, [["22-17", "11-15", "24-19"]])
    games = load_pdn_file(pdn)
    book = import_games(games, plies=10)
    # 3 plies → 3 (position, move) pairs.
    assert book.total_moves() == 3


def test_plies_limit_truncates(tmp_path: Path):
    from draughts.game.pdn import load_pdn_file

    pdn = _write_pdn(tmp_path, [["22-17", "11-15", "24-19", "8-12"]])
    games = load_pdn_file(pdn)
    book = import_games(games, plies=2)
    assert book.total_moves() == 2


def test_repeat_move_accumulates_weight(tmp_path: Path):
    from draughts.game.ai.book import OpeningBook
    from draughts.game.board import Board
    from draughts.config import Color
    from draughts.game.pdn import load_pdn_file

    pdn = _write_pdn(tmp_path, [["22-17"], ["22-17"], ["22-17"]])
    games = load_pdn_file(pdn)
    book = OpeningBook()
    import_games(games, plies=1, book=book)

    # Same starting position — single entry, weight=3.
    from draughts.game.ai.tt import _zobrist_hash

    h = _zobrist_hash(Board().grid, Color.WHITE)
    entry = book._entries[h]
    assert len(entry.moves) == 1
    _path, weight = entry.moves[0]
    assert weight == 3


def test_import_multiple_files_keeps_weights(tmp_path: Path):
    from draughts.game.pdn import load_pdn_file

    pdn = _write_pdn(tmp_path, [["22-17"], ["22-18"]])
    games = load_pdn_file(pdn)
    book = import_games(games, plies=1)
    # Two different first moves from the opening position.
    from draughts.game.ai.tt import _zobrist_hash
    from draughts.game.board import Board
    from draughts.config import Color

    h = _zobrist_hash(Board().grid, Color.WHITE)
    entry = book._entries[h]
    assert len(entry.moves) == 2
