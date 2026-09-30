# Bundled UI assets

Static assets for the live GUI, shared by both apps via `shared/icons.py` and
`shared/fonts.py`. Unrelated to `shopify-fulfillment-tool`'s
`shopify_tool/templates/assets/`, which holds fonts baked into *printed
label* templates.

## icons/ — Lucide 1.31.0 (ISC, see LICENSE)

Source: https://github.com/lucide-icons/lucide/tree/1.31.0/icons

Only the glyphs the app actually uses are vendored. To add one, download it from
the pinned tag above into this directory, then add its name to `EXPECTED_ICONS`
in `tests/test_ui_assets.py` of this repo (shopify-fulfillment-tool; packing-tool
receives the glyph through its next sync) — that list is a hardcoded literal,
so nothing picks a new glyph up on its own.

Pin the tag. Lucide renames glyphs between releases — `filter` became `funnel`
in 2025 and `filter.svg` now 404s on `main`.

## fonts/ — Inter 4.1 (SIL OFL 1.1, see OFL.txt)

Source: https://github.com/rsms/inter/releases/tag/v4.1, from `extras/ttf/`.

Regular and Bold only: `TYPE_SCALE` in `shared/theme.py` expresses no other
weight, and no italic. The variable `InterVariable.ttf` is deliberately not
used.

## brand/ — app logos

`fulfilment-tool` (Lucide `package` on `#006FBA`) and `packer-assistant`
(Lucide `scan-barcode` on `#2C6630`): white Lucide 1.31.0 glyphs (ISC, see
`icons/LICENSE`) on a rounded tile. The `.svg` is the source; the `.ico`
(16/24/32/48/256 px) is rendered from it once with QSvgRenderer + Pillow and is
what both the exe (PyInstaller `--icon`) and `shared.icons.brand_icon()` load.
Re-render the `.ico` whenever the `.svg` changes.
