# Theme Icon Attribution

SVG icon templates are inspired by the KDE Breeze icon theme.

- Original: https://github.com/Alexhuszagh/BreezeStyleSheets (MIT License)
- Adapted: simplified to single-color SVG templates with {placeholder}
  color substitution for the DRAUGHTS TOML theme system.

## Available icons in each theme's [icons] section

- **checkbox** — checkmark for `QCheckBox::indicator:checked`
- **radio** — dot for `QRadioButton::indicator:checked`
- **arrow** — down chevron for `QComboBox::down-arrow` and `QSpinBox::down-arrow`
- **arrow_up** — up chevron for `QSpinBox::up-arrow`
- **branch_open** — expanded tree indicator (reserved for future use)
- **branch_closed** — collapsed tree indicator (reserved for future use)
- **close** — X button (reserved for future use)

## SVG design notes

- viewBox: `0 0 16 16` for checkbox/radio, `0 0 12 12` for arrows and controls
- stroke-width: 2 for checkbox/radio, 1.8 for arrows
- stroke-linecap: round
- stroke-linejoin: round
- fill: none (stroke-only) for checkbox and arrows
- fill: {color} (solid) for radio dot
- No gradients, no filters, no animations — pure geometry

## Adding new icons

1. Design the icon as a single-color SVG with `{color_name}` placeholders
2. Add the template to the `[icons]` section in ALL 7 theme TOML files
3. Add the fallback to `_FALLBACK_ICONS` in `draughts/ui/theme_engine.py`
4. The `render_icons()` function handles all icons generically — no code change needed
5. Reference in `generate_qss()` via `image: url(path)` if wiring to a widget
