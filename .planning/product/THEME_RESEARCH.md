# Theme Research Summary

## Standards Found

**Qt Style Sheets (QSS)** are the de facto standard for Qt app theming.
Professional Qt apps (KDE, Telegram Desktop, Wireshark) use `.qss` files or
embedded stylesheets. No universal theme-exchange format exists; each app
defines its own schema.

**Catppuccin** publishes palettes in JSON, TOML, YAML, and language-native
formats. Their 26-color system (base tones + 14 accents) is the closest
thing to a community standard. Over 400 app ports.

**Dracula**, **Nord**, **Solarized**, **Gruvbox** publish hex values openly;
none define a TOML schema. Each has 8-16 named colors.

## Our TOML Format vs Standards

Our `[colors]` keys map cleanly to standard palette roles:

| Our key | Catppuccin | Material | Role |
|---------|-----------|----------|------|
| bg | base | surface | Background |
| fg | text | on-surface | Primary text |
| fg_muted | overlay0 | on-surface-variant | Secondary text |
| fg_accent | lavender | primary | Accent |
| btn_bg | surface0 | surface-container | Controls |
| green/red/blue | green/red/blue | tertiary/error | Semantic |

No schema change needed. The `board_style` field in `[meta]` maps new
themes to existing procedural texture sets (dark_wood / classic_light).

## Decisions

1. **Keep our TOML format** -- it already maps to standard palettes well.
2. **Do not adopt Material/Catppuccin schema** -- our keys are domain-
   specific (analysis pane, eval curve, annotations) and more granular.
3. **Added 5 themes** from established palettes: Catppuccin Mocha, Nord
   Frost, Dracula, Solarized Dark, Gruvbox Dark. These cover warm/cool,
   high/low contrast, and popular developer aesthetics.
4. **board_style mapping** -- new themes declare which texture set to use
   (dark_wood or classic_light), avoiding the need for per-theme textures.
5. **Future**: could add Solarized Light and Catppuccin Latte as light
   variants mapping to `board_style = "classic_light"`.
