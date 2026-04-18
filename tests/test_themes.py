"""Tests for the classic light board theme (D18)."""

from __future__ import annotations

import sys

import pytest

# ---------------------------------------------------------------------------
# Skip the whole module if PyQt6 is not available (e.g. headless CI without
# a display).  The texture code requires a QApplication to be running before
# QPixmap can be created.
# ---------------------------------------------------------------------------

try:
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication(sys.argv)
    _QT_AVAILABLE = True
except Exception:
    _QT_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _QT_AVAILABLE, reason="PyQt6 not available")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cache(theme: str = "dark_wood"):
    from draughts.ui.textures import TextureCache

    return TextureCache(theme=theme)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTextureCacheTheme:
    """TextureCache produces valid pixmaps for both themes."""

    def test_dark_wood_light_cell_not_null(self):
        cache = _make_cache("dark_wood")
        px = cache.get_light_cell(64)
        assert not px.isNull()

    def test_dark_wood_dark_cell_not_null(self):
        cache = _make_cache("dark_wood")
        px = cache.get_dark_cell(64)
        assert not px.isNull()

    def test_dark_wood_frame_not_null(self):
        cache = _make_cache("dark_wood")
        px = cache.get_frame(512)
        assert not px.isNull()

    def test_classic_light_light_cell_not_null(self):
        cache = _make_cache("classic_light")
        px = cache.get_light_cell(64)
        assert not px.isNull()

    def test_classic_light_dark_cell_not_null(self):
        cache = _make_cache("classic_light")
        px = cache.get_dark_cell(64)
        assert not px.isNull()

    def test_classic_light_frame_not_null(self):
        cache = _make_cache("classic_light")
        px = cache.get_frame(512)
        assert not px.isNull()

    def test_classic_light_cell_correct_size(self):
        cache = _make_cache("classic_light")
        size = 48
        px = cache.get_light_cell(size)
        assert px.width() == size
        assert px.height() == size

    def test_dark_wood_cell_correct_size(self):
        cache = _make_cache("dark_wood")
        size = 48
        px = cache.get_dark_cell(size)
        assert px.width() == size
        assert px.height() == size


class TestThemeSwitch:
    """Switching theme does not crash and invalidates the cache."""

    def test_theme_switch_dark_to_light(self):
        cache = _make_cache("dark_wood")
        # Pre-warm dark_wood cache
        _px1 = cache.get_light_cell(64)
        # Switch theme
        cache.theme = "classic_light"
        # Should return classic_light pixmap without crashing
        px2 = cache.get_light_cell(64)
        assert not px2.isNull()

    def test_theme_switch_light_to_dark(self):
        cache = _make_cache("classic_light")
        _px1 = cache.get_dark_cell(64)
        cache.theme = "dark_wood"
        px2 = cache.get_dark_cell(64)
        assert not px2.isNull()

    def test_invalid_theme_raises(self):
        from draughts.ui.textures import TextureCache

        with pytest.raises(ValueError, match="Unknown theme"):
            cache = TextureCache()
            cache.theme = "neon_pink"

    def test_default_theme_is_dark_wood(self):
        from draughts.ui.textures import TextureCache

        cache = TextureCache()
        assert cache.theme == "dark_wood"

    def test_themes_tuple_contains_both(self):
        from draughts.ui.textures import TextureCache

        assert "dark_wood" in TextureCache.THEMES
        assert "classic_light" in TextureCache.THEMES


class TestSettingsRoundtrip:
    """GameSettings preserves board_theme after construction."""

    def test_default_theme(self):
        from draughts.config import GameSettings

        s = GameSettings()
        assert s.board_theme == "dark_wood"

    def test_set_classic_light(self):
        from draughts.config import GameSettings

        s = GameSettings(board_theme="classic_light")
        assert s.board_theme == "classic_light"

    def test_set_dark_wood_explicit(self):
        from draughts.config import GameSettings

        s = GameSettings(board_theme="dark_wood")
        assert s.board_theme == "dark_wood"

    def test_theme_roundtrip_via_copy(self):
        """Simulate settings dialog round-trip: read → write new GameSettings."""
        from draughts.config import GameSettings

        original = GameSettings(board_theme="classic_light")
        restored = GameSettings(
            difficulty=original.difficulty,
            board_theme=original.board_theme,
        )
        assert restored.board_theme == "classic_light"
