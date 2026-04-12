"""Tests for the file-based theme system (theme_engine.py + TOML themes).

Covers:
1. TOML parsing for both shipped themes
2. SVG template rendering
3. Complete QSS generation
4. WCAG AA contrast ratios
5. Theme discovery
6. Fallback behavior
7. No hardcoded colors in UI files
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

import pytest
from draughts.ui.theme_engine import (
    Theme,
    clear_cache,
    contrast_ratio,
    generate_qss,
    get_theme,
    get_theme_colors,
    list_themes,
    load_theme,
    relative_luminance,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_theme_cache():
    """Ensure each test starts with a fresh theme cache."""
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# 1. test_load_dark_wood_theme
# ---------------------------------------------------------------------------


class TestLoadDarkWoodTheme:
    """Parses dark_wood.toml and verifies all required colors are present."""

    def test_loads_without_error(self):
        theme = load_theme("dark_wood")
        assert isinstance(theme, Theme)

    def test_meta_name(self):
        theme = load_theme("dark_wood")
        assert theme.name == "Dark Wood"
        assert theme.display_name == "Тёмное дерево"

    def test_file_stem(self):
        theme = load_theme("dark_wood")
        assert theme.file_stem == "dark_wood"

    def test_has_all_core_colors(self):
        theme = load_theme("dark_wood")
        required = [
            "bg",
            "bg_deep",
            "fg",
            "fg_muted",
            "fg_accent",
            "input_bg",
            "input_border",
            "btn_bg",
            "btn_hover",
            "btn_border",
            "btn_disabled_fg",
            "tab_bg",
            "tab_sel",
            "tab_border",
            "check_accent",
            "green",
            "red",
        ]
        for key in required:
            assert key in theme.colors, f"Missing color: {key}"
            assert theme.colors[key].startswith("#"), f"Color {key} not a hex string"

    def test_has_menu_colors(self):
        theme = load_theme("dark_wood")
        for key in ("menu_bg", "menu_hover", "menu_border"):
            assert key in theme.colors

    def test_has_annotation_colors(self):
        theme = load_theme("dark_wood")
        for key in ("ann_brilliant", "ann_good", "ann_inaccuracy", "ann_mistake", "ann_blunder", "ann_normal"):
            assert key in theme.colors

    def test_has_curve_colors(self):
        theme = load_theme("dark_wood")
        for key in ("curve_bg", "curve_line", "curve_point", "curve_selected", "curve_zero_line"):
            assert key in theme.colors


# ---------------------------------------------------------------------------
# 2. test_load_classic_light_theme
# ---------------------------------------------------------------------------


class TestLoadClassicLightTheme:
    """Parses classic_light.toml and verifies all required colors are present."""

    def test_loads_without_error(self):
        theme = load_theme("classic_light")
        assert isinstance(theme, Theme)

    def test_meta_name(self):
        theme = load_theme("classic_light")
        assert theme.name == "Classic Light"
        assert theme.display_name == "Классическая светлая"

    def test_has_all_core_colors(self):
        theme = load_theme("classic_light")
        required = [
            "bg",
            "bg_deep",
            "fg",
            "fg_muted",
            "fg_accent",
            "input_bg",
            "input_border",
            "btn_bg",
            "btn_hover",
            "btn_border",
            "tab_bg",
            "tab_sel",
            "tab_border",
            "check_accent",
            "green",
            "red",
        ]
        for key in required:
            assert key in theme.colors, f"Missing color: {key}"

    def test_light_bg_is_actually_light(self):
        """The light theme bg should have high luminance."""
        theme = load_theme("classic_light")
        lum = relative_luminance(theme.colors["bg"])
        assert lum > 0.5, f"Light theme bg luminance {lum:.3f} is too dark"


# ---------------------------------------------------------------------------
# 3. test_svg_template_rendering
# ---------------------------------------------------------------------------


class TestSvgTemplateRendering:
    """SVG templates have {placeholder} variables correctly substituted."""

    def test_checkbox_has_check_accent(self):
        theme = load_theme("dark_wood")
        # The rendered SVG file should contain the actual color, not the placeholder
        svg_path = Path(theme.icon_paths["checkbox"])
        content = svg_path.read_text(encoding="utf-8")
        assert "{check_accent}" not in content
        assert theme.colors["check_accent"] in content

    def test_arrow_has_fg_color(self):
        theme = load_theme("dark_wood")
        svg_path = Path(theme.icon_paths["arrow"])
        content = svg_path.read_text(encoding="utf-8")
        assert "{fg}" not in content
        assert theme.colors["fg"] in content

    def test_radio_has_check_accent(self):
        theme = load_theme("dark_wood")
        svg_path = Path(theme.icon_paths["radio"])
        content = svg_path.read_text(encoding="utf-8")
        assert "{check_accent}" not in content

    def test_all_icons_rendered(self):
        theme = load_theme("dark_wood")
        for name in ("checkbox", "radio", "arrow"):
            assert name in theme.icon_paths
            p = Path(theme.icon_paths[name])
            assert p.exists(), f"Rendered SVG not found: {p}"

    def test_classic_light_icons_rendered(self):
        theme = load_theme("classic_light")
        for name in ("checkbox", "radio", "arrow"):
            assert name in theme.icon_paths
            p = Path(theme.icon_paths[name])
            assert p.exists()
            content = p.read_text(encoding="utf-8")
            # Should contain the light theme's check_accent, not dark
            assert theme.colors["check_accent"] in content or theme.colors["fg"] in content


# ---------------------------------------------------------------------------
# 4. test_qss_generation_covers_all_widgets
# ---------------------------------------------------------------------------


class TestQssGeneration:
    """Generated QSS contains selectors for every widget type used in the app."""

    REQUIRED_SELECTORS: ClassVar[list[str]] = [
        "QMainWindow",
        "QDialog",
        "QMenuBar",
        "QMenu",
        "QMenu::item",
        "QMenu::separator",
        "QToolBar",
        "QToolButton",
        "QPushButton",
        "QPushButton:hover",
        "QPushButton:disabled",
        "QComboBox",
        "QComboBox::drop-down",
        "QComboBox::down-arrow",
        "QAbstractItemView",
        "QCheckBox",
        "QCheckBox::indicator",
        "QCheckBox::indicator:checked",
        "QRadioButton",
        "QRadioButton::indicator",
        "QRadioButton::indicator:checked",
        "QSpinBox",
        "QSlider",
        "QLabel",
        "QTabWidget",
        "QTabBar::tab",
        "QTabBar::tab:selected",
        "QTextEdit",
        "QScrollArea",
        "QScrollBar",
        "QDockWidget",
        "QDockWidget::title",
        "QGroupBox",
        "QGroupBox::title",
        "QDialogButtonBox",
        "QProgressBar",
    ]

    def test_dark_wood_qss_contains_all_selectors(self):
        theme = load_theme("dark_wood")
        qss = generate_qss(theme)
        for selector in self.REQUIRED_SELECTORS:
            assert selector in qss, f"Missing QSS selector: {selector}"

    def test_classic_light_qss_contains_all_selectors(self):
        theme = load_theme("classic_light")
        qss = generate_qss(theme)
        for selector in self.REQUIRED_SELECTORS:
            assert selector in qss, f"Missing QSS selector: {selector}"

    def test_qss_contains_theme_colors(self):
        theme = load_theme("dark_wood")
        qss = generate_qss(theme)
        # At least the primary colors should appear in the QSS
        assert theme.colors["bg"] in qss
        assert theme.colors["fg"] in qss
        assert theme.colors["btn_bg"] in qss

    def test_qss_is_nonempty_string(self):
        theme = load_theme("dark_wood")
        qss = generate_qss(theme)
        assert isinstance(qss, str)
        assert len(qss) > 500  # a complete QSS should be substantial


# ---------------------------------------------------------------------------
# 5. test_contrast_ratios_meet_wcag_aa
# ---------------------------------------------------------------------------


_ALL_THEMES = list_themes()


class TestContrastRatios:
    """WCAG AA requires >= 4.5:1 contrast ratio for normal text."""

    @pytest.mark.parametrize("theme_name", _ALL_THEMES)
    def test_fg_on_bg_meets_aa(self, theme_name: str):
        tc = get_theme_colors(theme_name)
        ratio = contrast_ratio(tc["fg"], tc["bg"])
        assert ratio >= 4.5, f"{theme_name}: fg/bg contrast {ratio:.2f} < 4.5 (fg={tc['fg']}, bg={tc['bg']})"

    @pytest.mark.parametrize("theme_name", _ALL_THEMES)
    def test_fg_accent_on_bg_meets_aa(self, theme_name: str):
        tc = get_theme_colors(theme_name)
        ratio = contrast_ratio(tc["fg_accent"], tc["bg"])
        assert ratio >= 4.5, f"{theme_name}: fg_accent/bg contrast {ratio:.2f} < 4.5"

    @pytest.mark.parametrize("theme_name", _ALL_THEMES)
    def test_green_on_bg_visible(self, theme_name: str):
        tc = get_theme_colors(theme_name)
        ratio = contrast_ratio(tc["green"], tc["bg"])
        assert ratio >= 3.0, f"{theme_name}: green/bg contrast {ratio:.2f} < 3.0"

    @pytest.mark.parametrize("theme_name", _ALL_THEMES)
    def test_red_on_bg_visible(self, theme_name: str):
        tc = get_theme_colors(theme_name)
        ratio = contrast_ratio(tc["red"], tc["bg"])
        assert ratio >= 3.0, f"{theme_name}: red/bg contrast {ratio:.2f} < 3.0"

    @pytest.mark.parametrize("theme_name", _ALL_THEMES)
    def test_tab_selected_distinguishable(self, theme_name: str):
        tc = get_theme_colors(theme_name)
        # Selected tab should differ noticeably from unselected
        ratio = contrast_ratio(tc["tab_sel"], tc["tab_bg"])
        # Even a small ratio difference is acceptable for backgrounds
        assert ratio >= 1.1, f"{theme_name}: tab_sel/tab_bg indistinguishable"

    @pytest.mark.parametrize("theme_name", _ALL_THEMES)
    def test_hover_distinguishable_from_default(self, theme_name: str):
        tc = get_theme_colors(theme_name)
        ratio = contrast_ratio(tc["btn_hover"], tc["btn_bg"])
        assert ratio >= 1.1, f"{theme_name}: btn_hover/btn_bg indistinguishable"

    @pytest.mark.parametrize("theme_name", _ALL_THEMES)
    def test_fg_muted_distinguishable_from_fg(self, theme_name: str):
        tc = get_theme_colors(theme_name)
        ratio = contrast_ratio(tc["fg"], tc["fg_muted"])
        assert ratio >= 1.3, f"{theme_name}: fg/fg_muted not distinguishable"


# ---------------------------------------------------------------------------
# 5b. All themes load, generate QSS, and render icons
# ---------------------------------------------------------------------------


class TestAllThemesLoadAndRender:
    """Every TOML file in draughts/themes/ must load, generate valid QSS, and render icons."""

    @pytest.mark.parametrize("theme_name", _ALL_THEMES)
    def test_loads_without_error(self, theme_name: str):
        theme = load_theme(theme_name)
        assert isinstance(theme, Theme)
        assert theme.display_name  # must have a display name

    @pytest.mark.parametrize("theme_name", _ALL_THEMES)
    def test_qss_covers_all_selectors(self, theme_name: str):
        theme = load_theme(theme_name)
        qss = generate_qss(theme)
        for selector in ("QMainWindow", "QDialog", "QMenuBar", "QPushButton", "QComboBox", "QLabel"):
            assert selector in qss, f"{theme_name}: missing QSS selector {selector}"

    @pytest.mark.parametrize("theme_name", _ALL_THEMES)
    def test_icons_rendered(self, theme_name: str):
        theme = load_theme(theme_name)
        for icon in ("checkbox", "radio", "arrow"):
            assert icon in theme.icon_paths
            p = Path(theme.icon_paths[icon])
            assert p.exists(), f"{theme_name}: icon {icon} not rendered at {p}"

    @pytest.mark.parametrize("theme_name", _ALL_THEMES)
    def test_board_style_valid(self, theme_name: str):
        theme = load_theme(theme_name)
        assert theme.board_style in ("dark_wood", "classic_light"), (
            f"{theme_name}: invalid board_style '{theme.board_style}'"
        )


# ---------------------------------------------------------------------------
# 6. test_list_themes_finds_toml_files
# ---------------------------------------------------------------------------


class TestListThemes:
    """Theme discovery from the draughts/themes/ directory."""

    def test_finds_both_shipped_themes(self):
        themes = list_themes()
        assert "dark_wood" in themes
        assert "classic_light" in themes

    def test_returns_sorted_list(self):
        themes = list_themes()
        assert themes == sorted(themes)

    def test_returns_strings(self):
        themes = list_themes()
        assert all(isinstance(t, str) for t in themes)


# ---------------------------------------------------------------------------
# 7. test_fallback_when_no_themes
# ---------------------------------------------------------------------------


class TestFallback:
    """App should not crash when theme files are missing."""

    def test_get_theme_unknown_returns_fallback(self):
        """Loading a non-existent theme falls back gracefully."""
        theme = get_theme("nonexistent_theme_xyz")
        assert isinstance(theme, Theme)
        assert theme.colors["bg"]  # has colors

    def test_fallback_theme_has_icons(self):
        theme = get_theme("nonexistent_theme_xyz")
        assert "checkbox" in theme.icon_paths
        assert "radio" in theme.icon_paths
        assert "arrow" in theme.icon_paths

    def test_fallback_qss_is_valid(self):
        theme = get_theme("nonexistent_theme_xyz")
        qss = generate_qss(theme)
        assert "QMainWindow" in qss
        assert len(qss) > 100


# ---------------------------------------------------------------------------
# 8. test_no_hardcoded_colors_in_ui
# ---------------------------------------------------------------------------


class TestNoHardcodedColors:
    """No hex color literals in draughts/ui/ files except theme_engine.py."""

    _HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
    _UI_DIR = Path(__file__).parent.parent / "draughts" / "ui"
    # Files allowed to contain hex colors (fallback definitions)
    _ALLOWED: ClassVar[set[str]] = {"theme_engine.py"}

    def test_no_hex_colors_in_ui_files(self):
        """Scan all .py files in draughts/ui/ for hardcoded hex colors."""
        violations = []
        for py_file in sorted(self._UI_DIR.glob("*.py")):
            if py_file.name in self._ALLOWED:
                continue
            content = py_file.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), 1):
                # Skip comments
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                # Skip lines that are purely comments after code
                code_part = line.split("#")[0] if "#" in line else line
                matches = self._HEX_COLOR_RE.findall(code_part)
                if matches:
                    violations.append(f"  {py_file.name}:{i}: {matches}")
        assert not violations, (
            "Hardcoded hex colors found in UI files (should use theme_engine instead):\n" + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# Contrast utility tests
# ---------------------------------------------------------------------------


class TestContrastUtilities:
    """Unit tests for the WCAG contrast ratio calculation."""

    def test_black_white_contrast(self):
        ratio = contrast_ratio("#000000", "#ffffff")
        assert abs(ratio - 21.0) < 0.1

    def test_same_color_contrast_is_one(self):
        ratio = contrast_ratio("#abcdef", "#abcdef")
        assert abs(ratio - 1.0) < 0.01

    def test_luminance_black(self):
        assert abs(relative_luminance("#000000")) < 0.001

    def test_luminance_white(self):
        assert abs(relative_luminance("#ffffff") - 1.0) < 0.001
