# Shared Modules for Shopify Tool and Packing Tool

Code that must behave identically in both **Shopify Fulfillment Tool** and
**Packing Tool** lives here.

## The sync rule

**`shopify-fulfillment-tool/shared/` is canonical** (ADR 0017 there).
`packing-tool/shared/` is a one-way copy, refreshed by running
`python scripts/sync_shared.py /path/to/shopify-fulfillment-tool` from
packing-tool's root (the bare sibling default resolves wrongly from a
worktree, so pass the path). The script mirrors this folder and records the
source commit in `packing-tool/scripts/shared_synced_from.txt`; packing-tool's
CI fails if its copy differs from this folder at that commit. A `shared/` file
hand-edited in packing-tool is silently overwritten by the next sync — author
every change here.

## What's in here

| Module | What it does |
|---|---|
| `theme.py` | Colour/spacing tokens, `build_stylesheet()`/`build_palette()`, density profiles, the type scale, `on_theme_changed()` |
| `icons.py` | Themed Lucide glyphs — `icon()` for `QIcon`, `glyph_url()` for a QSS `image:` url |
| `fonts.py` | Loads and registers the bundled Inter faces with Qt |
| `navrail.py` | The vertical navigation rail widget |
| `style_lint.py` | Build-time check for hardcoded colours / pixel font sizes / frozen alias reads in widget code |
| `logger.py` | Unified logging setup for both apps |
| `stats_manager.py` | Centralized usage statistics, written to the file server |
| `session_id.py` | Canonical `session_id` derivation, so both apps agree on one string for the same session |
| `atomic_write.py` | Atomic JSON writes (temp file + rename) for network storage |
| `file_lock.py` | Cross-platform advisory locking for shared JSON files |
| `metadata_utils.py` | Session metadata read/write helpers |
| `server_connection.py` | File-server path resolution, persistence, and the connection-settings dialog |
| `assets/` | Bundled fonts (Inter) and icons (Lucide SVGs, `currentColor`-recolourable), each with its license |

## Tests

Each module's own tests live in `shopify-fulfillment-tool/tests/`. packing-tool
keeps the tests that exercise its own use of `shared/` (its `gui.theme`
wiring, its type-scale default, session metadata, the atomic state write).
