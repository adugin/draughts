# Playbook: Creating and Debugging Themes

**When to use:** When creating new themes, fixing visual bugs in
existing themes, or extending the theme system with new widget types.

## Creating a new theme

### Step 1: Copy and rename
```bash
cp draughts/themes/dark_wood.toml draughts/themes/my_theme.toml
```

### Step 2: Edit meta
```toml
[meta]
name = "my_theme"
display_name = "Моя тема"
author = "Your Name"
version = "1.0"
```

### Step 3: Design the palette
Start with 4 anchor colors, derive the rest:
1. **bg** — main background
2. **fg** — main text (MUST contrast bg at ≥ 4.5:1)
3. **accent** — interactive elements highlight
4. **muted** — secondary text (≥ 3:1 contrast with bg)

Derive from anchors:
- `input_bg` — slightly lighter/darker than bg
- `btn_bg` — between bg and accent
- `btn_hover` — between btn_bg and accent
- `*_border` — between bg and fg, at ~40% opacity

### Step 4: Verify contrast
```bash
python -m pytest tests/test_themes_system.py -k contrast -v
```
The test computes luminance ratios for all critical pairs.

### Step 5: Test visually
```bash
python main.py
# Settings → Interface → select your theme
# Check: menus, dialogs, puzzle trainer, analysis pane, board editor
```

## Debugging visual bugs

### "Blue artifact" on dropdowns
**Cause:** Qt system selection color leaks through.
**Fix:** In QSS, MUST have ALL of:
```css
QComboBox QAbstractItemView { selection-background-color: ...; outline: 0; }
QComboBox QAbstractItemView::item:selected { background: ...; }
QComboBox QAbstractItemView::item:hover { background: ...; }
```
Missing ANY ONE of these → blue shows.

### "3D button" on combobox arrow
**Cause:** `QComboBox::drop-down` not styled.
**Fix:** `QComboBox::drop-down { background: transparent; border: none; }`

### Widget not picking up theme
**Cause:** Widget created before theme applied, or has its own
`setStyleSheet()` that overrides parent's cascade.
**Fix:** Either:
1. Remove the widget's `setStyleSheet()` — let parent cascade work
2. Or apply theme explicitly: `apply_theme(widget, theme_name)`

### Theme not propagating to child dialogs
**Cause:** Dialog hardcodes theme name in constructor.
**Fix:** Read from `parent._current_theme`:
```python
current_theme = "dark_wood"
if parent and hasattr(parent, "_current_theme"):
    current_theme = parent._current_theme
apply_theme(self, current_theme)
```

### Colors look different on different monitors
**Cause:** sRGB vs wide-gamut monitors render hex colors differently.
**Fix:** Nothing code-side. Use WCAG contrast ratios (computed from
luminance, not visual perception) as the ground truth.

## Rules for inline colors

**ZERO inline hex colors in `draughts/ui/` files.**

Verify:
```bash
grep -rn "#[0-9a-fA-F]\{6\}" draughts/ui/ --include="*.py" \
  | grep -v theme_engine | grep -v __pycache__ | grep -v "# "
```
Should return 0 hits.

If a widget needs a one-off color (e.g., puzzle correct/wrong flash):
1. Add it to `[colors]` in BOTH theme TOML files
2. Access via `get_theme_colors(theme)["my_new_color"]`
3. Never hardcode `"#2ecc71"` — use the theme key

## SVG icon templates

Icons are defined in TOML `[icons]` with `{placeholder}` syntax:
```toml
[icons]
checkbox = """<svg ...><path stroke="{check_accent}" .../></svg>"""
```

The theme engine substitutes `{check_accent}` with the actual hex
color at load time, renders to a temp file, and references via
`image: url(path)` in QSS.

To add a new icon:
1. Add SVG template to `[icons]` in both TOML files
2. In `theme_engine.py`, render it alongside existing icons
3. Reference in QSS via the icon_paths dict

## Previous bugs from this area

1. **PuzzleTrainer hardcoded "dark_wood"** — fixed by reading
   `parent._current_theme`
2. **AnalysisPane hardcoded "dark_wood"** — same fix
3. **7 UI files had inline hex colors** — all moved to TOML themes
4. **CSS triangle arrow didn't render** — replaced with SVG
5. **Blue focus rect on dropdown** — `outline: 0` + `:selected` style
