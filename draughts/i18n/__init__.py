"""Internationalization (i18n) infrastructure — item #40.

Minimal gettext wrapper so user-visible strings can be wrapped in ``_()``
today and translated later without changing call sites. Source language
is Russian (RU) — English and other locales will be added as .po files.

Usage:
    from draughts.i18n import _

    label = _("Новая игра")

Environment variable ``DRAUGHTS_LOCALE`` selects the active catalog.
Unset or missing catalog → identity translation (returns msgid as-is),
which matches current app behaviour — no breaking changes.

Catalog layout::

    draughts/locale/
        ru/LC_MESSAGES/draughts.po   (source; identity for Russian)
        ru/LC_MESSAGES/draughts.mo   (compiled; generated from .po)
        en/LC_MESSAGES/draughts.po   (English translations)
        en/LC_MESSAGES/draughts.mo

Build .mo from .po::

    python -m draughts.tools.compile_translations
"""

from __future__ import annotations

import gettext
import os
from pathlib import Path

_DOMAIN = "draughts"
_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"


def _resolve_locale() -> str:
    """Pick the active locale. Env var wins; otherwise system default."""
    env = os.environ.get("DRAUGHTS_LOCALE")
    if env:
        return env
    # Fall back to LANG (POSIX) but strip encoding suffix: "ru_RU.UTF-8" → "ru"
    lang = os.environ.get("LANG", "")
    if lang:
        return lang.split("_", 1)[0].split(".", 1)[0]
    return "ru"


def _build_translator() -> gettext.NullTranslations:
    locale = _resolve_locale()
    try:
        return gettext.translation(_DOMAIN, localedir=str(_LOCALE_DIR), languages=[locale])
    except FileNotFoundError:
        return gettext.NullTranslations()


_translator = _build_translator()


def _(msg: str) -> str:
    """Translate a source string through the active catalog.

    Falls back to identity (return ``msg`` unchanged) when no catalog
    is installed — so wrapping calls today is zero-risk.
    """
    return _translator.gettext(msg)


def set_locale(locale: str) -> None:
    """Runtime switch the active catalog. Changes affect subsequent _() calls."""
    global _translator
    try:
        _translator = gettext.translation(_DOMAIN, localedir=str(_LOCALE_DIR), languages=[locale])
    except FileNotFoundError:
        _translator = gettext.NullTranslations()


def current_locale() -> str:
    return _resolve_locale()
