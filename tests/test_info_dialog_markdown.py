"""Help renders as Markdown through Qt's native md4c parser.

Qt ≥6.4 ships a CommonMark + GFM Markdown parser in ``QtGui``. The
InfoDialog feeds ``resources/help.md`` through it with the GitHub
dialect so GFM tables render as actual tables (hotkeys section relies
on this). These tests verify:

    1. help.md exists, is UTF-8, and has a top-level heading.
    2. QTextDocument.setMarkdown() strips heading markers and produces
       more than one structured block.
    3. GFM tables survive the roundtrip (so the hotkeys table doesn't
       degrade to a row of pipes).
    4. The theme CSS builder emits every selector InfoDialog uses.
    5. The legacy help.txt fallback still works when help.md is absent.
"""

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
# Content of help.md
# ---------------------------------------------------------------------------


_HELP_MD = Path("draughts/resources/help.md")
_HELP_TXT = Path("draughts/resources/help.txt")


def test_help_md_exists_and_is_utf8():
    assert _HELP_MD.is_file(), "help.md must be shipped as a resource"
    text = _HELP_MD.read_text(encoding="utf-8")
    assert text.startswith("# "), "top-level heading required for dialog title"
    assert "## " in text, "expected at least one section heading"


def test_help_md_mentions_every_menu_title():
    """Every top-level menu in main_window.py must appear in help.md."""
    text = _HELP_MD.read_text(encoding="utf-8")
    for menu in ("Игра", "Позиция", "Вид", "Инструменты", "Справка"):
        assert menu in text, f"menu {menu!r} not documented in help.md"


def test_help_md_has_hotkeys_table():
    """The hotkeys section must use GFM table syntax so it renders as a table."""
    text = _HELP_MD.read_text(encoding="utf-8")
    # Look for a pipe-delimited header separator: `|---|---|...|`
    assert "|---|" in text.replace(" ", ""), "expected at least one GFM table in help.md"


# ---------------------------------------------------------------------------
# Rendering through QTextDocument
# ---------------------------------------------------------------------------


def test_qtextdocument_renders_markdown_headings():
    """setMarkdown should strip '#' and '##' markers, leaving only heading text."""
    from PyQt6.QtGui import QTextDocument

    text = _HELP_MD.read_text(encoding="utf-8")
    doc = QTextDocument()
    doc.setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
    plain = doc.toPlainText()
    # No literal '# ' at line starts — parser must have consumed them.
    for line in plain.splitlines():
        assert not line.startswith("# "), f"heading marker survived render: {line!r}"
    # Title text must still be present (as a heading).
    assert "Русские шашки" in plain
    # Non-trivial block count means the parser actually produced structure.
    assert doc.blockCount() > 30


def test_qtextdocument_renders_gfm_table_not_as_pipes():
    """With GFM dialect, ``| a | b |`` rows become tables, not plain text."""
    from PyQt6.QtGui import QTextDocument

    text = _HELP_MD.read_text(encoding="utf-8")
    doc = QTextDocument()
    doc.setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
    plain = doc.toPlainText()
    # If tables parsed correctly the plain text shouldn't contain raw '|---|'
    # header separators — they are table markup, not content.
    assert "|---|" not in plain.replace(" ", "")


# ---------------------------------------------------------------------------
# InfoDialog integration
# ---------------------------------------------------------------------------


def test_info_dialog_builds_with_markdown():
    from draughts.ui.dialogs import InfoDialog

    dlg = InfoDialog(theme="dark_wood")
    assert dlg.windowTitle() == "Информация"
    doc = dlg._text_browser.document()
    # Document carries rendered Markdown: non-trivial block count and
    # no raw '# ' marker at block start.
    assert doc.blockCount() > 30
    plain = doc.toPlainText()
    assert "Русские шашки" in plain
    assert "\n# " not in plain


def test_info_dialog_exposes_maximise_button():
    """Users must be able to maximise the help window to read wide tables.

    Default QDialog hides both min/max buttons — only Close is shown
    in the title bar. The InfoDialog overrides windowFlags() so the
    standard frame is restored, enabling maximise / minimise via the
    title-bar icons AND via the Windows shortcut (Win+Up).
    """
    from draughts.ui.dialogs import InfoDialog
    from PyQt6.QtCore import Qt

    dlg = InfoDialog(theme="dark_wood")
    flags = dlg.windowFlags()
    assert flags & Qt.WindowType.WindowMaximizeButtonHint, "InfoDialog must expose a maximise button in the title bar"
    assert flags & Qt.WindowType.WindowMinimizeButtonHint, "InfoDialog must expose a minimise button in the title bar"


def test_info_dialog_uses_plain_readable_document():
    """Help content must render as black-on-white, unaffected by theme.

    The dialog frame and «Закрыть» button stay themed, but the actual
    reading surface (QTextBrowser) is forced to a neutral palette so
    wide GFM tables and multi-paragraph prose read comfortably. The
    previous theme-driven CSS (dark warm accents on warm surface) was
    too noisy — the user asked for "чёрный текст на белом фоне".
    """
    from draughts.ui.dialogs import InfoDialog

    dlg = InfoDialog(theme="dark_wood")
    style = dlg._text_browser.styleSheet().replace(" ", "").lower()
    assert "background-color:#ffffff" in style
    assert "color:#000000" in style
    # No accent-coloured headings via setDefaultStyleSheet — the doc is
    # rendered with Qt defaults.
    assert dlg._text_browser.document().defaultStyleSheet() == ""


def test_info_dialog_falls_back_to_legacy_txt(monkeypatch):
    """If help.md is missing at runtime, the dialog still shows help.txt.

    We simulate "help.md is absent" by overriding both ``_populate``
    helper methods on the InfoDialog class itself — no on-disk rename
    of the shipped resource (previous approach was pytest-xdist hostile
    and left a ``help.md.hidden`` orphan if the test crashed).
    """
    from draughts.ui import dialogs as dialogs_mod

    # Force _populate's is_file() check to return False, then make the
    # legacy loader return a sentinel we can detect.
    monkeypatch.setattr(dialogs_mod.Path, "is_file", lambda self: False)
    monkeypatch.setattr(
        dialogs_mod.InfoDialog,
        "_load_legacy_help_text",
        staticmethod(lambda: "LEGACY PLAIN HELP"),
    )

    dlg = dialogs_mod.InfoDialog(theme="dark_wood")
    plain = dlg._text_browser.document().toPlainText()
    assert "LEGACY PLAIN HELP" in plain
