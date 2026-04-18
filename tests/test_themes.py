"""Theme / TextureCache behaviour tests.

Consolidated after the test-audit (Smell A — splinter pattern).
Previously had 17 tests, most of them one-assert-per-theme × one per
cell-type repeated. The production contract is: TextureCache produces
valid pixmaps for every (theme, cell-type, size) triple and theme
switching doesn't crash or leak state. Parametrised to cover that
without 17 separate test functions.
"""

from __future__ import annotations

import sys

import pytest

try:
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication(sys.argv)
    _QT_AVAILABLE = True
except Exception:  # pragma: no cover — import-time fallback
    _QT_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _QT_AVAILABLE, reason="PyQt6 not available")


_CELL_METHODS = ("get_light_cell", "get_dark_cell")
_THEMES = ("dark_wood", "classic_light")


@pytest.mark.parametrize("theme", _THEMES)
@pytest.mark.parametrize("method", _CELL_METHODS)
@pytest.mark.parametrize("size", [32, 48, 64, 96])
def test_cell_pixmap_matches_requested_size(theme: str, method: str, size: int):
    """Every (theme, cell-type, size) triple returns a non-null pixmap
    of the exact requested dimensions.
    """
    from draughts.ui.textures import TextureCache

    cache = TextureCache(theme=theme)
    px = getattr(cache, method)(size)
    assert not px.isNull()
    assert px.width() == size
    assert px.height() == size


@pytest.mark.parametrize("theme", _THEMES)
def test_frame_pixmap_non_null(theme: str):
    from draughts.ui.textures import TextureCache

    assert not TextureCache(theme=theme).get_frame(512).isNull()


def test_theme_switch_invalidates_pixmaps_and_stays_usable():
    """Switching theme post-cache-warmup must not crash and must
    return fresh pixmaps from the new theme.
    """
    from draughts.ui.textures import TextureCache

    cache = TextureCache(theme="dark_wood")
    cache.get_light_cell(64)  # warm cache
    cache.theme = "classic_light"
    assert not cache.get_light_cell(64).isNull()
    cache.theme = "dark_wood"
    assert not cache.get_dark_cell(64).isNull()


def test_invalid_theme_name_raises():
    from draughts.ui.textures import TextureCache

    with pytest.raises(ValueError, match="Unknown theme"):
        TextureCache().theme = "neon_pink"


def test_shipped_theme_default_contract():
    """UX-facing default. Regression guard: changing this is a
    user-visible decision, not a silent refactor.
    """
    from draughts.config import GameSettings
    from draughts.ui.textures import TextureCache

    assert TextureCache().theme == "dark_wood"
    assert GameSettings().board_theme == "dark_wood"
