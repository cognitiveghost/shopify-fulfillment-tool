# Bundled UI assets

Static assets for the live GUI. Unrelated to `shopify_tool/templates/assets/`,
which holds fonts baked into *printed label* templates.

## icons/ — Lucide 1.31.0 (ISC, see LICENSE)

Source: https://github.com/lucide-icons/lucide/tree/1.31.0/icons

Only the glyphs the app actually uses are vendored. To add one, download it from
the pinned tag above into this directory; `tests/test_ui_assets.py` and
`tests/test_icons.py` will pick it up.

Pin the tag. Lucide renames glyphs between releases — `filter` became `funnel`
in 2025 and `filter.svg` now 404s on `main`.

## fonts/ — Inter 4.1 (SIL OFL 1.1, see OFL.txt)

Source: https://github.com/rsms/inter/releases/tag/v4.1, from `extras/ttf/`.

Regular and Bold only: `TYPE_SCALE` in `gui/theme_manager.py` expresses no
other weight, and no italic. The variable `InterVariable.ttf` is deliberately
not used.
