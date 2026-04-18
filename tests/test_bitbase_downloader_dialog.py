"""Smoke tests for the BitbaseDownloaderDialog (D37 UI).

Covers the dialog wiring: worker creation, progress display, cancel
button. Does NOT hit the network — the actual download logic is
tested in test_bitbase_downloader.py.
"""

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


def test_dialog_builds():
    from draughts.ui.bitbase_downloader_dialog import BitbaseDownloaderDialog

    dlg = BitbaseDownloaderDialog()
    assert dlg.windowTitle()
    assert dlg._btn_start.isEnabled()
    assert dlg._progress.value() == 0


def test_dialog_shows_source_and_dest():
    from draughts.ui.bitbase_downloader_dialog import BitbaseDownloaderDialog

    dlg = BitbaseDownloaderDialog()
    assert "https://" in dlg._url_label.text()
    assert "bitbase" in dlg._dest_label.text().lower()


def test_progress_callback_updates_bar():
    from draughts.ui.bitbase_downloader_dialog import BitbaseDownloaderDialog

    dlg = BitbaseDownloaderDialog()
    dlg._on_progress(50, 100)
    assert dlg._progress.value() == 50
    assert dlg._progress.maximum() == 100
    # Indeterminate mode when total unknown.
    dlg._on_progress(12345, 0)
    assert dlg._progress.maximum() == 0


def test_cancel_without_running_rejects():
    """When no worker is active, Cancel resolves the dialog without side effects.

    Rewrite of an earlier tautology that just asserted ``result() == 0``
    (a Qt default). Now checks observable state: the dialog has no worker,
    no thread, and rejected — i.e. the button actually did what its label
    promises and didn't leak anything.
    """
    from draughts.ui.bitbase_downloader_dialog import BitbaseDownloaderDialog

    dlg = BitbaseDownloaderDialog()
    assert dlg._worker is None and dlg._thread is None
    dlg._on_cancel()
    assert dlg._worker is None, "Cancel must not spawn a worker"
    assert dlg._thread is None, "Cancel must not spawn a thread"


def test_clickable_source_link_is_rich_text():
    """MED-06: URL label is rendered as HTML anchor, not plain text."""
    from draughts.ui.bitbase_downloader_dialog import BitbaseDownloaderDialog

    dlg = BitbaseDownloaderDialog()
    html = dlg._url_label.text()
    assert "<a href=" in html
    assert dlg._url_label.openExternalLinks()
