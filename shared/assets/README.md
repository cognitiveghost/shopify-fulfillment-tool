# Bundled UI assets

Static assets for the live GUI, shared by both apps via `shared/icons.py` and
`shared/fonts.py`. Unrelated to `shopify-fulfillment-tool`'s
`shopify_tool/templates/assets/`, which holds fonts baked into *printed
label* templates.

## icons/ — Lucide 1.31.0 (ISC, see LICENSE)

Source: https://github.com/lucide-icons/lucide/tree/1.31.0/icons

Only the glyphs the app actually uses are vendored. To add one, download it from
the pinned tag above into this directory, then add its name to `EXPECTED_ICONS`
in **each** repo's `tests/test_ui_assets.py` — that list is a hardcoded literal,
so nothing picks a new glyph up on its own.

Pin the tag. Lucide renames glyphs between releases — `filter` became `funnel`
in 2025 and `filter.svg` now 404s on `main`.

## fonts/ — Inter 4.1 (SIL OFL 1.1, see OFL.txt)

Source: https://github.com/rsms/inter/releases/tag/v4.1, from `extras/ttf/`.

Regular and Bold only: `TYPE_SCALE` in `shared/theme.py` expresses no other
weight, and no italic. The variable `InterVariable.ttf` is deliberately not
used.
