"""File-based theme engine for the DRAUGHTS application.

Loads themes from TOML files in ``draughts/themes/``, renders SVG
templates with color substitution, generates a single complete QSS
string per theme, and applies it to the whole application window.

Public API
----------
- ``list_themes() -> list[str]``  -- discover available theme names
- ``load_theme(name) -> Theme``   -- parse a TOML file into a Theme
- ``apply_theme(window, theme)``  -- set the window stylesheet
- ``get_theme_colors(name) -> dict[str, str]`` -- color dict for non-QSS use
"""

from __future__ import annotations

import logging
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("draughts.theme_engine")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_THEMES_DIR = Path(__file__).parent.parent / "themes"

# Temp directory for rendered SVGs (one per process)
_svg_temp_dir: Path | None = None


def _get_svg_dir() -> Path:
    """Return (and lazily create) a temp directory for rendered SVGs."""
    global _svg_temp_dir
    if _svg_temp_dir is None or not _svg_temp_dir.exists():
        _svg_temp_dir = Path(tempfile.mkdtemp(prefix="draughts_svg_"))
    return _svg_temp_dir


# ---------------------------------------------------------------------------
# Theme dataclass
# ---------------------------------------------------------------------------


@dataclass
class Theme:
    """Parsed theme data."""

    # Meta
    name: str = "Default"
    display_name: str = "Default"
    author: str = ""
    version: str = "1.0"
    file_stem: str = ""  # e.g. "dark_wood" (used as theme ID)

    # Board texture style: "dark_wood" or "classic_light".
    # New themes reuse one of the two procedural texture sets.
    board_style: str = "dark_wood"

    # Color palette -- all values are "#rrggbb" strings
    colors: dict[str, str] = field(default_factory=dict)

    # SVG icon templates (raw strings with {placeholder} variables)
    icon_templates: dict[str, str] = field(default_factory=dict)

    # Rendered SVG file paths (populated after render_icons())
    icon_paths: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Built-in fallback (if no TOML files found)
# ---------------------------------------------------------------------------

_FALLBACK_COLORS: dict[str, str] = {
    "bg": "#2a1a0a",
    "bg_deep": "#1e140a",
    "fg": "#d4b483",
    "fg_muted": "#8a7060",
    "fg_accent": "#f0d090",
    "input_bg": "#3a2a1a",
    "input_border": "#5a4a3a",
    "btn_bg": "#3a2510",
    "btn_hover": "#4a3a2a",
    "btn_border": "#6a4520",
    "btn_disabled_fg": "#5a4a3a",
    "tab_bg": "#3a2510",
    "tab_sel": "#4a3520",
    "tab_border": "#6a4520",
    "check_accent": "#d4b483",
    "green": "#2ecc71",
    "red": "#e74c3c",
    "blue": "#3498db",
    "menu_bg": "#3a2510",
    "menu_hover": "#5a3d20",
    "menu_border": "#6a4a2a",
    "toolbar_bg": "#1e110a",
    "toolbar_border": "#4a3a2a",
    "analysis_run_bg": "#3a5a3a",
    "analysis_run_border": "#5a8a5a",
    "analysis_run_hover": "#4a6a4a",
    "analysis_stop_bg": "#5a2a2a",
    "analysis_stop_border": "#8a4a4a",
    "analysis_stop_hover": "#6a3a3a",
    "disabled_bg": "#2a2a2a",
    "disabled_fg": "#666666",
    "caption_fg": "#a08050",
    "editor_play_fg": "#2a8a2a",
    "editor_cancel_fg": "#a03030",
    "ann_brilliant": "#00cc44",
    "ann_good": "#44cc44",
    "ann_inaccuracy": "#ccaa00",
    "ann_mistake": "#cc6600",
    "ann_blunder": "#cc2222",
    "ann_normal": "#d4b483",
    "ann_move_num": "#806040",
    "curve_zero_line": "#4a3520",
    "curve_line": "#c8a050",
    "curve_point": "#f0d090",
    "curve_selected": "#ff8844",
    "curve_bg": "#1a0e05",
    "curve_axis": "#6a4520",
    "curve_label": "#806040",
    "scroll_bg": "#1a0e05",
}

_FALLBACK_ICONS: dict[str, str] = {
    # Breeze-style checkbox checkmark — 16×16, 2px rounded stroke, stroke only
    "checkbox": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
        '<polyline points="3,8 6,11 13,4" stroke="{check_accent}" stroke-width="2"'
        ' fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    ),
    # Breeze-style radio dot — 16×16 outer, filled inner circle ~40% diameter
    "radio": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
        '<circle cx="8" cy="8" r="3" fill="{check_accent}"/>'
        "</svg>"
    ),
    # Breeze-style down chevron — 12×12, 1.8px rounded stroke
    "arrow": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12" width="12" height="12">'
        '<polyline points="2,4 6,8 10,4" stroke="{fg}" stroke-width="1.8"'
        ' fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    ),
    # Breeze-style up chevron — 12×12, 1.8px rounded stroke
    "arrow_up": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12" width="12" height="12">'
        '<polyline points="2,8 6,4 10,8" stroke="{fg}" stroke-width="1.8"'
        ' fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    ),
    # Breeze-style tree branch open (expanded) — down-pointing triangle, 12×12
    "branch_open": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12" width="12" height="12">'
        '<polyline points="2,4 6,8 10,4" stroke="{fg_muted}" stroke-width="1.8"'
        ' fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    ),
    # Breeze-style tree branch closed (collapsed) — right-pointing triangle, 12×12
    "branch_closed": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12" width="12" height="12">'
        '<polyline points="4,2 8,6 4,10" stroke="{fg_muted}" stroke-width="1.8"'
        ' fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    ),
    # Breeze-style close X — 12×12, two crossing diagonal lines, 1.8px rounded stroke
    "close": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12" width="12" height="12">'
        '<line x1="2" y1="2" x2="10" y2="10" stroke="{fg}" stroke-width="1.8"'
        ' stroke-linecap="round"/>'
        '<line x1="10" y1="2" x2="2" y2="10" stroke="{fg}" stroke-width="1.8"'
        ' stroke-linecap="round"/>'
        "</svg>"
    ),
}


def _build_fallback_theme() -> Theme:
    """Return a minimal built-in theme when no TOML files are available."""
    t = Theme(
        name="Dark Wood",
        display_name="Тёмное дерево",
        author="DRAUGHTS Team",
        version="1.0",
        file_stem="dark_wood",
        colors=dict(_FALLBACK_COLORS),
        icon_templates=dict(_FALLBACK_ICONS),
    )
    render_icons(t)
    return t


# ---------------------------------------------------------------------------
# Theme loading
# ---------------------------------------------------------------------------


def list_themes() -> list[str]:
    """Return sorted list of available theme file stems (e.g. ['classic_light', 'dark_wood'])."""
    if not _THEMES_DIR.is_dir():
        return []
    return sorted(p.stem for p in _THEMES_DIR.glob("*.toml"))


def load_theme(name: str) -> Theme:
    """Load and parse a theme by file stem (e.g. 'dark_wood').

    Raises FileNotFoundError if the TOML file does not exist.
    """
    path = _THEMES_DIR / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"Theme file not found: {path}")

    with open(path, "rb") as f:
        data = tomllib.load(f)

    meta = data.get("meta", {})
    colors = data.get("colors", {})
    icons = data.get("icons", {})

    # board_style maps to procedural texture set ("dark_wood" or "classic_light")
    valid_board_styles = ("dark_wood", "classic_light")
    raw_board_style = meta.get("board_style", "dark_wood")
    board_style = raw_board_style if raw_board_style in valid_board_styles else "dark_wood"

    theme = Theme(
        name=meta.get("name", name),
        display_name=meta.get("display_name", meta.get("name", name)),
        author=meta.get("author", ""),
        version=meta.get("version", "1.0"),
        file_stem=name,
        board_style=board_style,
        colors=colors,
        icon_templates=icons,
    )

    # Ensure all required colors have fallback values
    for key, fallback in _FALLBACK_COLORS.items():
        theme.colors.setdefault(key, fallback)

    # Ensure all required icon templates have fallback values
    for key, fallback in _FALLBACK_ICONS.items():
        theme.icon_templates.setdefault(key, fallback)

    render_icons(theme)
    return theme


# ---------------------------------------------------------------------------
# SVG rendering
# ---------------------------------------------------------------------------


def render_icons(theme: Theme) -> None:
    """Render SVG templates by substituting color variables.

    Writes rendered SVGs to temp files and stores paths in theme.icon_paths.
    Uses forward-slash posix paths for Qt QSS compatibility.
    """
    svg_dir = _get_svg_dir()

    for icon_name, template in theme.icon_templates.items():
        # Substitute all color variables
        rendered = template
        for color_name, color_value in theme.colors.items():
            rendered = rendered.replace(f"{{{color_name}}}", color_value)

        # Write to temp file
        svg_path = svg_dir / f"{theme.file_stem}_{icon_name}.svg"
        svg_path.write_text(rendered, encoding="utf-8")

        # Store posix path for Qt url() compatibility
        theme.icon_paths[icon_name] = svg_path.as_posix()


# ---------------------------------------------------------------------------
# QSS generation
# ---------------------------------------------------------------------------


def generate_qss(theme: Theme) -> str:
    """Generate a single, complete QSS string covering every widget type.

    This eliminates blue Qt artifacts — every widget falls through to
    themed styles rather than system defaults.
    """
    c = theme.colors
    icons = theme.icon_paths

    # Convenience aliases
    bg = c["bg"]
    bg_deep = c["bg_deep"]
    fg = c["fg"]
    fg_muted = c["fg_muted"]
    fg_accent = c["fg_accent"]
    input_bg = c["input_bg"]
    input_border = c["input_border"]
    btn_bg = c["btn_bg"]
    btn_hover = c["btn_hover"]
    btn_border = c["btn_border"]
    btn_disabled_fg = c["btn_disabled_fg"]
    tab_bg = c["tab_bg"]
    tab_sel = c["tab_sel"]
    tab_border = c["tab_border"]
    check_accent = c["check_accent"]
    menu_bg = c["menu_bg"]
    menu_hover = c["menu_hover"]
    menu_border = c["menu_border"]
    toolbar_bg = c["toolbar_bg"]
    toolbar_border = c["toolbar_border"]
    disabled_fg = c.get("disabled_fg", "#666666")
    scroll_bg = c.get("scroll_bg", bg_deep)

    # Icon paths (with fallbacks)
    check_icon = icons.get("checkbox", "")
    radio_icon = icons.get("radio", "")
    arrow_icon = icons.get("arrow", "")
    arrow_up_icon = icons.get("arrow_up", "")

    return f"""
/* === Generated by theme_engine — {theme.name} === */

/* --- Top-level containers --- */
QMainWindow {{
    background-color: {bg};
}}

QDialog {{
    background: {bg};
    color: {fg};
}}

/* --- Menu bar --- */
QMenuBar {{
    background: {menu_bg};
    color: {fg};
    border-bottom: 1px solid {menu_border};
    font-size: 13px;
}}
QMenuBar::item:selected {{
    background: {menu_hover};
}}

/* --- Menus --- */
QMenu {{
    background: {menu_bg};
    color: {fg};
    border: 1px solid {menu_border};
}}
QMenu::item:selected {{
    background: {menu_hover};
}}
QMenu::item:disabled {{
    color: {disabled_fg};
}}
QMenu::separator {{
    background: {menu_border};
    height: 1px;
}}

/* --- Toolbars --- */
QToolBar {{
    background: {toolbar_bg};
    border-top: 1px solid {toolbar_border};
    spacing: 12px;
}}

QToolButton {{
    background: {btn_bg};
    color: {fg};
    border: 1px solid {btn_border};
    border-radius: 3px;
    padding: 3px 8px;
}}
QToolButton:hover {{
    background: {btn_hover};
}}

/* --- Labels --- */
QLabel {{
    color: {fg};
}}

/* --- Push buttons --- */
QPushButton {{
    background: {btn_bg};
    color: {fg};
    border: 1px solid {btn_border};
    border-radius: 4px;
    padding: 6px 14px;
    font-size: 13px;
}}
QPushButton:hover {{
    background: {btn_hover};
}}
QPushButton:disabled {{
    color: {btn_disabled_fg};
    border-color: {input_bg};
}}

QDialogButtonBox QPushButton {{
    min-width: 70px;
}}

/* --- ComboBox --- */
QComboBox {{
    background: {input_bg};
    color: {fg};
    border: 1px solid {input_border};
    padding: 4px 8px;
    border-radius: 3px;
    font-size: 13px;
}}
QComboBox::drop-down {{
    background: transparent;
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: url({arrow_icon});
    width: 10px;
    height: 10px;
}}
QComboBox QAbstractItemView {{
    background: {input_bg};
    color: {fg};
    outline: 0;
    border: 1px solid {input_border};
    selection-background-color: {btn_bg};
    selection-color: {fg_accent};
}}
QComboBox QAbstractItemView::item {{
    padding: 3px 6px;
}}
QComboBox QAbstractItemView::item:selected {{
    background: {btn_bg};
    color: {fg_accent};
}}
QComboBox QAbstractItemView::item:hover {{
    background: {btn_bg};
    color: {fg_accent};
}}

/* --- CheckBox --- */
QCheckBox {{
    color: {fg};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    background: {input_bg};
    border: 2px solid {input_border};
    border-radius: 3px;
}}
QCheckBox::indicator:checked {{
    border-color: {check_accent};
    image: url({check_icon});
}}

/* --- RadioButton --- */
QRadioButton {{
    color: {fg};
    spacing: 6px;
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    background: {input_bg};
    border: 2px solid {input_border};
    border-radius: 9px;
}}
QRadioButton::indicator:checked {{
    border-color: {check_accent};
    image: url({radio_icon});
}}

/* --- SpinBox --- */
QSpinBox {{
    background: {input_bg};
    color: {fg};
    border: 1px solid {input_border};
    padding: 3px;
    border-radius: 3px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 16px;
}}
QSpinBox::up-arrow {{
    image: url({arrow_up_icon});
    width: 12px;
    height: 12px;
}}
QSpinBox::down-arrow {{
    image: url({arrow_icon});
    width: 12px;
    height: 12px;
}}

/* --- Slider --- */
QSlider::groove:horizontal {{
    background: {input_bg};
    border: 1px solid {input_border};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {check_accent};
    border: 1px solid {btn_border};
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {btn_bg};
    border-radius: 3px;
}}

/* --- Tab widget --- */
QTabWidget::pane {{
    background: {bg};
    border: 1px solid {tab_border};
}}
QTabBar::tab {{
    background: {tab_bg};
    color: {fg};
    padding: 6px 14px;
    border: 1px solid {tab_border};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {tab_sel};
    font-weight: bold;
}}

/* --- Text edit --- */
QTextEdit {{
    background: {input_bg};
    color: {fg};
    border: 1px solid {input_border};
}}

/* --- Scroll area --- */
QScrollArea {{
    border: none;
    background: {scroll_bg};
}}

/* --- Scroll bars --- */
QScrollBar:vertical {{
    background: {bg_deep};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {fg_muted};
    min-height: 20px;
    border-radius: 4px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {bg_deep};
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {fg_muted};
    min-width: 20px;
    border-radius: 4px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* --- Dock widget (analysis pane) --- */
QDockWidget {{
    color: {fg};
    font-size: 13px;
}}
QDockWidget::title {{
    background: {menu_bg};
    padding: 4px 8px;
    color: {fg};
    font-weight: bold;
}}
/* --- Group box --- */
QGroupBox {{
    color: {fg};
    border: 1px solid {tab_border};
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 12px;
}}
QGroupBox::title {{
    color: {fg};
}}

/* --- Progress bar --- */
QProgressBar {{
    background: {input_bg};
    border: 1px solid {input_border};
    border-radius: 3px;
    text-align: center;
    color: {fg};
    font-size: 12px;
}}
QProgressBar::chunk {{
    background: {check_accent};
    border-radius: 2px;
}}
"""


# ---------------------------------------------------------------------------
# Theme application
# ---------------------------------------------------------------------------


# Cache: theme name -> Theme object
_theme_cache: dict[str, Theme] = {}


def get_theme(name: str) -> Theme:
    """Load a theme (cached). Falls back to built-in default on error."""
    if name in _theme_cache:
        return _theme_cache[name]

    try:
        theme = load_theme(name)
    except FileNotFoundError:
        logger.warning("Theme '%s' not found, using fallback", name)
        theme = _build_fallback_theme()
    except Exception:
        logger.exception("Failed to load theme '%s', using fallback", name)
        theme = _build_fallback_theme()

    _theme_cache[name] = theme
    return theme


def get_theme_colors(name: str) -> dict[str, str]:
    """Return the color dict for a theme (for non-QSS uses like QPainter)."""
    return get_theme(name).colors


def get_board_style(name: str) -> str:
    """Return the board texture style for a theme ('dark_wood' or 'classic_light').

    New themes map to one of the two procedural texture sets via ``board_style``.
    """
    return get_theme(name).board_style


def apply_theme(window, theme_name: str) -> None:
    """Apply a theme to the given QMainWindow or QDialog.

    Sets the full application stylesheet on the widget.
    """
    theme = get_theme(theme_name)
    qss = generate_qss(theme)
    window.setStyleSheet(qss)


def clear_cache() -> None:
    """Clear the theme cache (useful for testing or hot-reload)."""
    _theme_cache.clear()


# ---------------------------------------------------------------------------
# WCAG contrast utilities
# ---------------------------------------------------------------------------


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert '#rrggbb' to (r, g, b) in [0, 1]."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0


def relative_luminance(hex_color: str) -> float:
    """WCAG 2.0 relative luminance of a hex color."""
    r, g, b = _hex_to_rgb(hex_color)

    def _linearize(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def contrast_ratio(color1: str, color2: str) -> float:
    """WCAG 2.0 contrast ratio between two hex colors.

    Returns a value >= 1.0.  WCAG AA requires >= 4.5 for normal text.
    """
    l1 = relative_luminance(color1)
    l2 = relative_luminance(color2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)
