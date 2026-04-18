"""Tests for the PDN database browser (#36)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_qt_app = None


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    global _qt_app
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    _qt_app = QApplication.instance() or QApplication(sys.argv)
    yield _qt_app


def _make_pdn(tmp_path: Path, n_games: int) -> Path:
    """Write a PDN file with n_games simple games."""
    parts = []
    for i in range(n_games):
        parts.append(f'[Event "Test {i}"]')
        parts.append('[Site "CI"]')
        parts.append('[Date "2026.04.18"]')
        parts.append('[Round "?"]')
        parts.append(f'[White "Player{i}A"]')
        parts.append(f'[Black "Player{i}B"]')
        parts.append('[Result "*"]')
        parts.append('[GameType "25"]')
        parts.append("")
        parts.append("1. 22-17 *")
        parts.append("")
    path = tmp_path / "multi.pdn"
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def test_browser_loads_multi_game_pdn(tmp_path: Path):
    from draughts.ui.pdn_browser import PDNBrowserDialog

    pdn = _make_pdn(tmp_path, 5)
    dlg = PDNBrowserDialog()
    dlg.load_path(pdn)
    assert dlg._table.rowCount() == 5
    # All 5 Player* entries are present regardless of sort order.
    names = {dlg._table.item(r, 0).text() for r in range(5)}
    assert names == {f"Player{i}A" for i in range(5)}


def test_browser_filter_hides_non_matching(tmp_path: Path):
    from draughts.ui.pdn_browser import PDNBrowserDialog

    pdn = _make_pdn(tmp_path, 4)
    dlg = PDNBrowserDialog()
    dlg.load_path(pdn)
    dlg._filter.setText("Player2")
    visible = [r for r in range(dlg._table.rowCount()) if not dlg._table.isRowHidden(r)]
    assert len(visible) == 1


def test_browser_clear_filter_shows_all(tmp_path: Path):
    from draughts.ui.pdn_browser import PDNBrowserDialog

    pdn = _make_pdn(tmp_path, 3)
    dlg = PDNBrowserDialog()
    dlg.load_path(pdn)
    dlg._filter.setText("nothing")
    dlg._filter.setText("")
    visible = [r for r in range(dlg._table.rowCount()) if not dlg._table.isRowHidden(r)]
    assert len(visible) == 3


def test_browser_emits_game_selected(tmp_path: Path):
    from draughts.ui.pdn_browser import PDNBrowserDialog

    pdn = _make_pdn(tmp_path, 2)
    dlg = PDNBrowserDialog()
    received = []
    dlg.game_selected.connect(received.append)
    dlg.load_path(pdn)
    dlg._table.selectRow(1)
    dlg._on_load_selected()
    assert len(received) == 1
    # Sort order may vary — just assert we received ONE of the two games.
    assert received[0].headers["White"] in {"Player0A", "Player1A"}


def test_browser_handles_empty_file(tmp_path: Path):
    from draughts.ui.pdn_browser import PDNBrowserDialog

    empty = tmp_path / "empty.pdn"
    empty.write_text("", encoding="utf-8")
    dlg = PDNBrowserDialog()
    dlg.load_path(empty)
    assert dlg._table.rowCount() == 0
