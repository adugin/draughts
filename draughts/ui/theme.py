"""Centralized UI theme definitions for all widgets and dialogs.

Every styled widget in the app should import its QSS from here,
not define colors inline. This ensures a single source of truth
for visual consistency and easy theme switching.
"""
from __future__ import annotations

from pathlib import Path

_RES = Path(__file__).parent.parent / "resources"

# ---------------------------------------------------------------------------
# Color palettes
# ---------------------------------------------------------------------------

PALETTES = {
    "dark_wood": {
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
    },
    "classic_light": {
        "bg": "#f5ead0",
        "bg_deep": "#efe4cc",
        "fg": "#3a2a1a",
        "fg_muted": "#7a6a4a",
        "fg_accent": "#6a4a2a",
        "input_bg": "#ffffff",
        "input_border": "#c8b898",
        "btn_bg": "#e0d4b8",
        "btn_hover": "#d0c4a4",
        "btn_border": "#b0a080",
        "btn_disabled_fg": "#b0a080",
        "tab_bg": "#e8dcc0",
        "tab_sel": "#d4c4a4",
        "tab_border": "#b8a888",
        "check_accent": "#6a4a2a",
        "green": "#228b22",
        "red": "#c0392b",
    },
}


def _svg(name: str, theme: str) -> str:
    """Return posix path to a theme-variant SVG resource."""
    suffix = "dark" if theme == "dark_wood" else "light"
    return (_RES / f"{name}_{suffix}.svg").as_posix()


# ---------------------------------------------------------------------------
# Shared QSS generators
# ---------------------------------------------------------------------------

def button_qss(theme: str = "dark_wood") -> str:
    """QSS for QPushButton — flat, themed."""
    t = PALETTES.get(theme, PALETTES["dark_wood"])
    return (
        f"QPushButton {{ background: {t['btn_bg']}; color: {t['fg']};"
        f"  border: 1px solid {t['btn_border']}; border-radius: 4px;"
        f"  padding: 6px 14px; font-size: 13px; }}"
        f"QPushButton:hover {{ background: {t['btn_hover']}; }}"
        f"QPushButton:disabled {{ color: {t['btn_disabled_fg']};"
        f"  border-color: {t['input_bg']}; }}"
    )


def combobox_qss(theme: str = "dark_wood") -> str:
    """QSS for QComboBox — flat drop-down with SVG arrow."""
    t = PALETTES.get(theme, PALETTES["dark_wood"])
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
    """QSS for QCheckBox — themed indicator with SVG checkmark."""
    t = PALETTES.get(theme, PALETTES["dark_wood"])
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
    """QSS for QRadioButton — themed indicator with SVG dot."""
    t = PALETTES.get(theme, PALETTES["dark_wood"])
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
    t = PALETTES.get(theme, PALETTES["dark_wood"])
    color = t["fg_muted"] if muted else t["fg"]
    return f"color: {color};"


def spinbox_qss(theme: str = "dark_wood") -> str:
    """QSS for QSpinBox."""
    t = PALETTES.get(theme, PALETTES["dark_wood"])
    return (
        f"QSpinBox {{ background: {t['input_bg']}; color: {t['fg']};"
        f"  border: 1px solid {t['input_border']}; padding: 3px;"
        f"  border-radius: 3px; }}"
    )
