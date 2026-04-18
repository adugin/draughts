"""Tests for the i18n infrastructure (#40)."""

from __future__ import annotations

import os


def test_identity_when_no_catalog(monkeypatch):
    """With no matching catalog, _() must return the input unchanged."""
    monkeypatch.setenv("DRAUGHTS_LOCALE", "klingon")

    # Reload to pick up the env change.
    import importlib
    import draughts.i18n as i

    importlib.reload(i)

    assert i._("Новая игра") == "Новая игра"


def test_english_catalog_translates(monkeypatch):
    monkeypatch.setenv("DRAUGHTS_LOCALE", "en")

    import importlib
    import draughts.i18n as i

    importlib.reload(i)

    assert i._("Новая игра") == "New game"
    assert i._("Сдаться") == "Resign"
    # Untranslated msgid falls back to msgid itself.
    assert i._("строка отсутствует в каталоге") == "строка отсутствует в каталоге"


def test_runtime_locale_switch():
    import draughts.i18n as i

    i.set_locale("en")
    assert i._("Новая игра") == "New game"
    i.set_locale("ru")
    assert i._("Новая игра") == "Новая игра"


def test_missing_locale_falls_back_to_identity():
    import draughts.i18n as i

    i.set_locale("xx")  # non-existent
    assert i._("Новая игра") == "Новая игра"
