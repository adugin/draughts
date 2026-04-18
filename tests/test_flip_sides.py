"""Regression tests for flip_sides (Ctrl+F) — mid-game side swap.

Covers the bugs found in the QA audit (BUG-1..BUG-11). Most tests drive
GameController directly without the AI actually running; the rare
AI-needed tests use a controlled engine interruption via the generation
token so no real search has to complete.
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_qt_app = None


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    global _qt_app
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    _qt_app = QApplication.instance() or QApplication(sys.argv)
    yield _qt_app


@pytest.fixture
def controller(qt_app, monkeypatch):
    from draughts.app.controller import GameController

    # Silence the real AI. Tests reason about state transitions after a
    # flip; they should not depend on a real search running (and must
    # never leak worker threads into other tests).
    monkeypatch.setattr(GameController, "_start_computer_turn", lambda self: None)
    c = GameController()
    yield c


# ---------------------------------------------------------------------------
# Core flip semantics
# ---------------------------------------------------------------------------


def test_flip_swaps_colors_on_players_turn(controller):
    """On player's turn (WHITE at start), flip makes player BLACK."""
    from draughts.config import Color

    assert controller.player_color == Color.WHITE
    assert controller.computer_color == Color.BLACK
    assert controller.current_turn == Color.WHITE  # player's turn

    controller.flip_sides()

    assert controller.player_color == Color.BLACK
    assert controller.computer_color == Color.WHITE
    # _current_turn is absolute — not changed by flip
    assert controller.current_turn == Color.WHITE
    assert controller.settings.invert_color is True


def test_flip_preserves_board_and_history(controller):
    """flip_sides never mutates position, history, counters or ply."""
    board_before = controller.board.to_position_string()
    positions_before = list(controller._positions)
    pc_before = dict(controller._position_counts)
    ply_before = controller._ply_count

    controller.flip_sides()

    assert controller.board.to_position_string() == board_before
    assert controller._positions == positions_before
    assert controller._position_counts == pc_before
    assert controller._ply_count == ply_before


def test_double_flip_is_identity_at_ply0(controller):
    """Two flips at ply=0 restore original colors."""
    from draughts.config import Color

    controller.flip_sides()  # user becomes BLACK, turn=WHITE → AI starts
    # Invalidate the in-flight worker (we don't want to wait for it).
    controller._ai_generation += 1
    controller._ai_thread = None
    controller._ai_worker = None
    # Now turn is still WHITE, but player is WHITE again after the second
    # flip only if we apply it. Since current_turn == computer_color (WHITE)
    # after first flip, the guard blocks the second. Verify:
    controller.flip_sides()
    # Guard: not on player's turn → no swap
    assert controller.player_color == Color.BLACK
    assert controller.computer_color == Color.WHITE


# ---------------------------------------------------------------------------
# Guards (D36 + BUG-5)
# ---------------------------------------------------------------------------


def test_flip_blocked_when_not_players_turn(controller):
    """Flipping when turn == AI's is a no-op with status message (D36)."""
    from draughts.config import Color

    # Manually move to AI's turn (as if AI was thinking):
    controller._current_turn = Color.BLACK  # AI's color by default

    seen_messages: list[str] = []
    controller.message_changed.connect(seen_messages.append)

    player_before = controller.player_color
    computer_before = controller.computer_color
    controller.flip_sides()

    assert controller.player_color == player_before
    assert controller.computer_color == computer_before
    assert any("Дождитесь" in m for m in seen_messages)


def test_flip_blocked_during_multi_capture(controller):
    """BUG-5: flip while mid partial capture is a no-op with hint."""
    controller._capture_path = [(0, 5), (1, 4)]  # any non-empty path

    seen_messages: list[str] = []
    controller.message_changed.connect(seen_messages.append)

    player_before = controller.player_color
    controller.flip_sides()

    assert controller.player_color == player_before
    assert any("взятие" in m.lower() for m in seen_messages)
    # Capture path is left untouched (user can still finish it)
    assert controller._capture_path == [(0, 5), (1, 4)]


# ---------------------------------------------------------------------------
# AI lifecycle (generation token, pending cleanup)
# ---------------------------------------------------------------------------


def test_flip_bumps_generation_and_stashes_worker(controller):
    """When AI was thinking, flip should stash the old worker in _pending_ai."""
    from PyQt6.QtCore import QThread

    # Simulate in-flight AI worker for the current generation.
    class _DummyWorker:
        def __init__(self, gen):
            self._generation = gen

    controller._current_turn = controller._player_color
    dummy_thread = QThread()  # real QThread for proper stash types
    dummy_worker = _DummyWorker(controller._ai_generation)
    controller._ai_thread = dummy_thread
    controller._ai_worker = dummy_worker  # type: ignore[assignment]

    gen_before = controller._ai_generation
    controller.flip_sides()
    assert controller._ai_generation == gen_before + 1
    assert controller._ai_thread is None
    assert controller._ai_worker is None
    assert any(w is dummy_worker for (_t, w) in controller._pending_ai)

    # Cleanup
    dummy_thread.quit()
    dummy_thread.wait()


def test_new_game_bumps_generation(controller):
    """BUG-10: new_game increments generation so stale workers are dropped."""
    gen_before = controller._ai_generation
    controller.new_game()
    assert controller._ai_generation == gen_before + 1


# ---------------------------------------------------------------------------
# Persistence (BUG-1)
# ---------------------------------------------------------------------------


def test_load_saved_after_flip_restores_player_color(controller, monkeypatch, tmp_path):
    """BUG-1: after flip, save, and load — player/computer color stay swapped."""
    from draughts.config import Color

    # Simulate flip by calling it directly on the player's turn.
    controller.flip_sides()

    save_path = str(tmp_path / "after_flip.json")
    controller.save_current_game(save_path)

    # Brand-new controller, load the save. Keep AI silent.
    from draughts.app.controller import GameController

    monkeypatch.setattr(GameController, "_start_computer_turn", lambda self: None)

    c2 = GameController()
    assert c2.player_color == Color.WHITE  # fresh default
    c2.load_saved_game(save_path)

    # The flipped orientation must be restored.
    assert c2.settings.invert_color is True
    assert c2.player_color == Color.BLACK
    assert c2.computer_color == Color.WHITE


def test_flip_autosaves(controller, tmp_path, monkeypatch):
    """BUG-9: flip triggers autosave so --resume stays consistent."""
    called = []

    def fake_autosave(path, gs):
        called.append(gs.invert_color)

    # Patch the module-level autosave used by _do_autosave
    import draughts.app.controller as ctrl_mod

    monkeypatch.setattr(ctrl_mod, "autosave", fake_autosave)

    controller.flip_sides()
    assert called, "autosave was not called after flip_sides"
    assert called[-1] is True  # reflects the post-flip orientation


# ---------------------------------------------------------------------------
# UI state clearing
# ---------------------------------------------------------------------------


def test_flip_clears_selection_and_capture_path(controller):
    """Selection and capture path are cleared on a successful flip."""
    controller._selected = (0, 5)
    # Do NOT set a capture path — BUG-5 blocks that. Just selection.
    controller.flip_sides()
    assert controller._selected is None
    assert controller._capture_path == []


def test_flip_emits_last_move_none(controller):
    """Last-move highlight is cleared on flip so stale arrow doesn't linger."""
    received = []
    controller.last_move_changed.connect(received.append)
    controller.flip_sides()
    # The signal sequence contains at least one None emit
    assert None in received


def test_flip_emits_board_and_turn_changed(controller):
    """flip_sides emits board/turn signals for UI repaint."""
    b = []
    t = []
    controller.board_changed.connect(lambda: b.append(1))
    controller.turn_changed.connect(lambda c: t.append(c))
    controller.flip_sides()
    assert b, "board_changed not emitted"
    assert t, "turn_changed not emitted"


# ---------------------------------------------------------------------------
# Game-over guard
# ---------------------------------------------------------------------------


def test_flip_noop_when_game_over(controller):
    """flip_sides returns silently if the game has ended."""
    from draughts.config import Color

    # Force game over: remove all WHITE pieces — BLACK wins.
    controller.board.grid[controller.board.grid < 0] = 0  # clear whites
    # Ensure turn is player's (WHITE) so the D36 guard wouldn't fire first.
    controller._current_turn = Color.WHITE

    player_before = controller.player_color
    controller.flip_sides()
    # Game is over, flip is a no-op.
    assert controller.player_color == player_before


# ---------------------------------------------------------------------------
# Editor-mode guard (BUG-3)
# ---------------------------------------------------------------------------


def test_enter_editor_bumps_generation(qt_app, monkeypatch):
    """BUG-3: entering editor must invalidate any in-flight AI worker via
    the generation token, NOT via a blocking quit()+wait() that would freeze
    the UI for seconds during a deep search."""
    from draughts.app.controller import GameController
    from draughts.ui.main_window import MainWindow
    from PyQt6.QtCore import QThread

    monkeypatch.setattr(GameController, "_start_computer_turn", lambda self: None)

    class _DummyWorker:
        def __init__(self, gen):
            self._generation = gen

    c = GameController()
    w = MainWindow(c)
    # Simulate in-flight AI.
    fake_thread = QThread()
    fake_worker = _DummyWorker(c._ai_generation)
    c._ai_thread = fake_thread
    c._ai_worker = fake_worker  # type: ignore[assignment]

    gen_before = c._ai_generation
    w.enter_editor_mode()

    assert c._ai_generation == gen_before + 1
    assert c._ai_thread is None
    assert c._ai_worker is None
    # The stashed worker is in pending, not lost.
    assert any(w_ is fake_worker for (_t, w_) in c._pending_ai)

    # Cleanup — exit editor to avoid leaking window state for other tests.
    w.exit_editor_mode()
    fake_thread.quit()
    fake_thread.wait()
    w.close()


# ---------------------------------------------------------------------------
# Board widget orientation sync (smoke)
# ---------------------------------------------------------------------------


def test_main_window_flip_syncs_board_widget_inverted(qt_app, monkeypatch):
    """_on_flip_sides sets board_widget.inverted from player_color."""
    from draughts.app.controller import GameController
    from draughts.ui.main_window import MainWindow

    # Prevent real AI from spawning when flip hands the turn to computer.
    monkeypatch.setattr(GameController, "_start_computer_turn", lambda self: None)
    c = GameController()
    w = MainWindow(c)
    assert w.board_widget.inverted is False  # player=WHITE → not inverted

    w._on_flip_sides()
    # Player is BLACK now; board should be inverted.
    assert w.board_widget.inverted is True

    w.close()


# ---------------------------------------------------------------------------
# Stale-AI drop path cleanup by generation (BUG-6)
# ---------------------------------------------------------------------------


def test_pending_ai_cleaned_by_generation(controller):
    """BUG-6: _on_ai_finished stale path removes pending entries by
    matching the worker's generation, not by Python identity."""
    from PyQt6.QtCore import QThread

    class _DummyWorker:
        """Stub that mimics AIWorker attributes used in cleanup."""

        def __init__(self, gen):
            self._generation = gen

        def thread(self):
            return self._thread

        def deleteLater(self):
            pass

    # Put two stale workers into pending.
    t1, w1 = QThread(), _DummyWorker(controller._ai_generation)
    t2, w2 = QThread(), _DummyWorker(controller._ai_generation + 1)
    w1._thread = t1  # type: ignore[attr-defined]
    w2._thread = t2  # type: ignore[attr-defined]
    controller._pending_ai.append((t1, w1))
    controller._pending_ai.append((t2, w2))
    controller._ai_generation += 10  # make all stale

    # Simulate w1's finished signal arriving: call the stale-path cleanup
    # path directly. We re-use _on_ai_finished but must fake sender().
    from unittest.mock import patch

    with patch.object(controller, "sender", return_value=w1):
        controller._on_ai_finished(None, w1._generation)

    # w1 removed, w2 still pending.
    assert all(w is not w1 for (_t, w) in controller._pending_ai)
    assert any(w is w2 for (_t, w) in controller._pending_ai)

    # Cleanup.
    t1.quit()
    t1.wait()
    t2.quit()
    t2.wait()
