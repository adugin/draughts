"""Tests for the Resign feature."""

from __future__ import annotations

import sys

import pytest

_qt_app = None


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    global _qt_app
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    _qt_app = QApplication.instance() or QApplication(sys.argv)
    yield _qt_app


@pytest.fixture
def controller(monkeypatch):
    from draughts.app.controller import GameController
    monkeypatch.setattr(GameController, "_start_computer_turn", lambda self: None)
    return GameController()


def test_resign_emits_game_over_with_loss_message(controller):
    received = []
    controller.game_over.connect(received.append)
    controller.resign()
    assert received, "resign must emit game_over"
    assert "сдались" in received[-1].lower()


def test_resign_invalidates_pending_ai_thread(controller):
    from PyQt6.QtCore import QThread

    class _W:
        def __init__(self, g): self._generation = g

    fake_t = QThread()
    fake_w = _W(controller._ai_generation)
    controller._ai_thread = fake_t
    controller._ai_worker = fake_w  # type: ignore[assignment]

    gen_before = controller._ai_generation
    controller.resign()
    assert controller._ai_generation == gen_before + 1
    assert controller._ai_thread is None
    assert controller._ai_worker is None
    assert any(w is fake_w for (_t, w) in controller._pending_ai)
    fake_t.quit(); fake_t.wait()


def test_resign_no_op_when_game_already_over(controller):
    """If the position is already a loss (no player pieces), resign is a no-op."""
    import numpy as np
    # White player (default) resigns — but we simulate white already gone.
    controller.board.grid[controller.board.grid < 0] = 0
    received = []
    controller.game_over.connect(received.append)
    controller.resign()
    # No game_over emitted from resign because the guard short-circuits.
    assert received == []


def test_resign_clears_selection_and_capture_path(controller):
    controller._selected = (0, 5)
    controller._capture_path = [(0, 5), (1, 4)]
    controller.resign()
    assert controller._selected is None
    assert controller._capture_path == []
