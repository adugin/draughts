"""Backward-compatible shim for the old theme API.

All new code should import from ``draughts.ui.theme_engine`` instead.
This module re-exports the legacy function signatures so that existing
callers (dialogs.py, puzzle_widget.py, main_window.py) continue to work
during the migration period.

.. deprecated::
    Use ``draughts.ui.theme_engine`` directly.
"""

from __future__ import annotations

from draughts.ui.theme_engine import get_theme

# ---------------------------------------------------------------------------
# Legacy PALETTES dict — populated from the theme engine
# ---------------------------------------------------------------------------


def _build_palettes() -> dict[str, dict[str, str]]:
    """Build the legacy PALETTES dict from loaded themes."""
    from draughts.ui.theme_engine import list_themes

    result = {}
    for name in list_themes():
        try:
            theme = get_theme(name)
            result[name] = dict(theme.colors)
        except Exception:
            pass

    # Always ensure the two default themes are present
    if "dark_wood" not in result:
        result["dark_wood"] = dict(get_theme("dark_wood").colors)
    if "classic_light" not in result:
        result["classic_light"] = dict(get_theme("classic_light").colors)

    return result


# Lazy initialization to avoid import-time side effects
PALETTES: dict[str, dict[str, str]] | None = None


def _get_palettes() -> dict[str, dict[str, str]]:
    global PALETTES
    if PALETTES is None:
        PALETTES = _build_palettes()
    return PALETTES


# ---------------------------------------------------------------------------
# Legacy QSS generator functions
# ---------------------------------------------------------------------------


def _svg(name: str, theme: str) -> str:
    """Return posix path to a rendered SVG for the given theme."""
    t = get_theme(theme)
    icon_map = {"check": "checkbox", "radio": "radio", "arrow": "arrow"}
    key = icon_map.get(name, name)
    return t.icon_paths.get(key, "")


def button_qss(theme: str = "dark_wood") -> str:
    """QSS for QPushButton -- flat, themed."""
    t = get_theme(theme).colors
    return (
        f"QPushButton {{ background: {t['btn_bg']}; color: {t['fg']};"
        f"  border: 1px solid {t['btn_border']}; border-radius: 4px;"
        f"  padding: 6px 14px; font-size: 13px; }}"
        f"QPushButton:hover {{ background: {t['btn_hover']}; }}"
        f"QPushButton:disabled {{ color: {t['btn_disabled_fg']};"
        f"  border-color: {t['input_bg']}; }}"
    )


def combobox_qss(theme: str = "dark_wood") -> str:
    """QSS for QComboBox -- flat drop-down with SVG arrow."""
    t = get_theme(theme).colors
    arrow = _svg("arrow", theme)
    return (
        f"QComboBox {{ background: {t['input_bg']}; color: {t['fg']};"
        f"  border: 1px solid {t['input_border']}; padding: 4px 8px;"
        f"  border-radius: 3px; font-size: 13px; }}"
        f"QComboBox::drop-down {{ background: transparent; border: none;"
        f"  width: 20px; }}"
        f"QComboBox::down-arrow {{ image: url({arrow});"
        f"  width: 10px; height: 10px; }}"
        f"QComboBox QAbstractItemView {{ background: {t['input_bg']};"
        f"  color: {t['fg']}; outline: 0; border: none;"
        f"  selection-background-color: {t['btn_bg']};"
        f"  selection-color: {t['fg_accent']}; }}"
        f"QComboBox QAbstractItemView::item {{ padding: 3px 6px; }}"
        f"QComboBox QAbstractItemView::item:selected {{"
        f"  background: {t['btn_bg']}; color: {t['fg_accent']}; }}"
        f"QComboBox QAbstractItemView::item:hover {{"
        f"  background: {t['btn_bg']}; color: {t['fg_accent']}; }}"
    )


def checkbox_qss(theme: str = "dark_wood") -> str:
    """QSS for QCheckBox -- themed indicator with SVG checkmark."""
    t = get_theme(theme).colors
    check = _svg("check", theme)
    return (
        f"QCheckBox {{ color: {t['fg']}; spacing: 6px; }}"
        f"QCheckBox::indicator {{ width: 18px; height: 18px;"
        f"  background: {t['input_bg']}; border: 2px solid {t['input_border']};"
        f"  border-radius: 3px; }}"
        f"QCheckBox::indicator:checked {{ border-color: {t['check_accent']};"
        f"  image: url({check}); }}"
    )


def radio_qss(theme: str = "dark_wood") -> str:
    """QSS for QRadioButton -- themed indicator with SVG dot."""
    t = get_theme(theme).colors
    radio = _svg("radio", theme)
    return (
        f"QRadioButton {{ color: {t['fg']}; spacing: 6px; }}"
        f"QRadioButton::indicator {{ width: 16px; height: 16px;"
        f"  background: {t['input_bg']}; border: 2px solid {t['input_border']};"
        f"  border-radius: 9px; }}"
        f"QRadioButton::indicator:checked {{ border-color: {t['check_accent']};"
        f"  image: url({radio}); }}"
    )


def label_qss(theme: str = "dark_wood", muted: bool = False) -> str:
    """QSS for QLabel."""
    t = get_theme(theme).colors
    color = t["fg_muted"] if muted else t["fg"]
    return f"color: {color};"


def spinbox_qss(theme: str = "dark_wood") -> str:
    """QSS for QSpinBox."""
    t = get_theme(theme).colors
    return (
        f"QSpinBox {{ background: {t['input_bg']}; color: {t['fg']};"
        f"  border: 1px solid {t['input_border']}; padding: 3px;"
        f"  border-radius: 3px; }}"
    )
