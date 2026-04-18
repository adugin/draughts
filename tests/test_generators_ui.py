"""Smoke tests for the in-app generator dialogs (D36)."""

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


# ---------------------------------------------------------------------------
# GeneratorProgressDialog
# ---------------------------------------------------------------------------


def test_progress_dialog_initial_state():
    from draughts.ui.generators import GeneratorProgressDialog

    dlg = GeneratorProgressDialog(lambda p, c: {"ok": True}, "Test")
    assert dlg.windowTitle() == "Test"
    assert not dlg._btn_cancel.isEnabled()
    assert dlg._btn_close.isEnabled()
    assert dlg._progress.value() == 0


def test_progress_dialog_completes_quick_task(qt_app):
    """Run a trivial generator to success and verify result/slot wiring."""
    from draughts.ui.generators import GeneratorProgressDialog

    def fn(on_progress, should_cancel):
        on_progress(1, 3, "step 1")
        on_progress(2, 3, "step 2")
        on_progress(3, 3, "done")
        return {"value": 42}

    dlg = GeneratorProgressDialog(fn, "Quick")
    received: list = []
    dlg.completed.connect(received.append)
    dlg.start()

    # Spin the Qt event loop until the worker emits finished.
    from PyQt6.QtCore import QDeadlineTimer

    deadline = QDeadlineTimer(3000)
    while not received and not deadline.hasExpired():
        qt_app.processEvents()

    assert received == [{"value": 42}]
    assert dlg.result == {"value": 42}
    assert dlg._progress.value() == 3
    assert dlg._btn_close.isEnabled()
    assert not dlg._btn_cancel.isEnabled()


def test_progress_dialog_error_path(qt_app):
    """Worker raises → error_msg branch, no crash."""
    from draughts.ui.generators import GeneratorProgressDialog

    def fn(on_progress, should_cancel):
        raise ValueError("boom")

    dlg = GeneratorProgressDialog(fn, "Err")
    dlg.start()

    from PyQt6.QtCore import QDeadlineTimer

    deadline = QDeadlineTimer(3000)
    while dlg._thread is not None and not deadline.hasExpired():
        qt_app.processEvents()

    assert dlg._btn_close.isEnabled()
    assert "ValueError" in dlg._log.toPlainText()


def test_progress_dialog_cancel(qt_app):
    """Cancel flag propagates; generator raises cancellation."""
    from draughts.ui.generators import GeneratorProgressDialog, _GeneratorCancelled

    def fn(on_progress, should_cancel):
        for i in range(1_000_000):
            if should_cancel():
                raise _GeneratorCancelled()
            on_progress(i, 0, "")
        return {"finished": True}

    dlg = GeneratorProgressDialog(fn, "Cancellable")
    dlg.start()

    # Let it run briefly then cancel.
    from PyQt6.QtCore import QDeadlineTimer

    for _ in range(20):
        qt_app.processEvents()
    dlg._on_cancel_clicked()

    deadline = QDeadlineTimer(3000)
    while dlg._thread is not None and not deadline.hasExpired():
        qt_app.processEvents()

    assert "отмена" in dlg._log.toPlainText().lower()
    assert dlg._btn_close.isEnabled()


def test_progress_dialog_close_event_while_idle_accepts(qt_app):
    """With no worker running, [X] closes the dialog immediately."""
    from PyQt6.QtGui import QCloseEvent
    from draughts.ui.generators import GeneratorProgressDialog

    dlg = GeneratorProgressDialog(lambda p, c: {}, "Idle")
    evt = QCloseEvent()
    dlg.closeEvent(evt)
    assert evt.isAccepted()
    assert not dlg._close_pending


def test_progress_dialog_close_event_while_running_defers(qt_app):
    """Pressing [X] while the worker is running must cancel and defer close,
    not leak the QThread by ignoring the dismissal."""
    from PyQt6.QtCore import QDeadlineTimer
    from PyQt6.QtGui import QCloseEvent
    from draughts.ui.generators import GeneratorProgressDialog, _GeneratorCancelled

    def fn(on_progress, should_cancel):
        for i in range(1_000_000):
            if should_cancel():
                raise _GeneratorCancelled()
            on_progress(i, 0, "")
        return {}

    dlg = GeneratorProgressDialog(fn, "Running")
    closed_signals: list = []
    dlg.finished.connect(lambda code: closed_signals.append(code))
    dlg.start()

    # Let the worker tick a bit.
    for _ in range(20):
        qt_app.processEvents()

    evt = QCloseEvent()
    dlg.closeEvent(evt)
    assert not evt.isAccepted(), "close must be deferred while worker runs"
    assert dlg._close_pending is True

    # Pump events until _on_finished auto-closes via accept().
    deadline = QDeadlineTimer(3000)
    while dlg.isVisible() is False and dlg._thread is not None and not deadline.hasExpired():
        qt_app.processEvents()
    while dlg._thread is not None and not deadline.hasExpired():
        qt_app.processEvents()
    # Give _on_finished a chance to run.
    for _ in range(10):
        qt_app.processEvents()

    assert dlg._thread is None, "worker thread was not reaped"
    # The dialog must have self-accepted/rejected after cancellation.
    assert closed_signals, "dialog did not emit finished() after cancel-close"


# ---------------------------------------------------------------------------
# Import / Mine dialogs build
# ---------------------------------------------------------------------------


def test_import_book_dialog_builds():
    from draughts.ui.generators import ImportBookFromPdnDialog

    dlg = ImportBookFromPdnDialog()
    assert dlg.windowTitle()
    # OK button disabled until files are selected.
    assert not dlg._btn_ok.isEnabled()
    # Simulate a selection.
    dlg._pdn_paths = [Path("nonexistent.pdn")]
    dlg._btn_ok.setEnabled(True)
    assert dlg._btn_ok.isEnabled()


def test_mine_puzzles_dialog_builds():
    from draughts.ui.generators import MinePuzzlesDialog

    dlg = MinePuzzlesDialog()
    assert dlg.windowTitle()
    assert dlg._games.value() == 30
    assert dlg._seed.value() == 0
    # MED-02: depth selector present with sane default.
    assert dlg._depth.value() >= 4


def test_mine_puzzles_writes_to_canonical_path():
    """BLK-01 invariant: mined puzzles land in data_dir/puzzles/, the
    same directory load_mined_puzzles reads from. No more silent dead-end.
    """
    from draughts.game.puzzle_miner import _mined_puzzles_path
    from draughts.user_data import mined_puzzles_path

    # Whatever the miner writes, the loader reads.
    assert _mined_puzzles_path() == mined_puzzles_path()


def test_imported_book_loader_picks_up_user_file(tmp_path, monkeypatch):
    """BLK-02 invariant: load_default_book reads the book imported via the
    Инструменты dialog — they share user_data.user_book_path().
    """
    from draughts.game.ai import load_default_book
    from draughts.game.ai.book import OpeningBook
    import draughts.user_data

    fake_book = tmp_path / "book_user.json"
    monkeypatch.setattr(draughts.user_data, "user_book_path", lambda: fake_book)

    OpeningBook().save(fake_book)
    book = load_default_book()
    assert book is not None
    assert len(book) == 0

    # Cleanup: monkeypatch auto-reverts user_book_path AFTER the test,
    # but DEFAULT_BOOK is still pointing at the empty loaded state.
    # Register a finalizer that reloads with the un-patched path so
    # later tests in the suite see the real bundled book again.
    def _restore():
        load_default_book()

    monkeypatch.undo()  # revert user_book_path BEFORE reloading
    _restore()
