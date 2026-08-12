# UI Design System — Track 2: Iconography & Font Embedding — Design

Roadmap: Todoist `6hG88cfF63cXQWF3`, under epic "UI Design System Foundation"
(`6hG88Vx9CgRHVgG3`). Parent vision doc:
`docs/superpowers/specs/2026-08-11-ui-design-system-vision-design.md`, Track 2.
Builds directly on Track 1 (`2026-08-12-design-tokens-type-scale-design.md`, PR #268,
merged).

## Context

Two gaps this track closes, both verified against the code at `main` (241c6f7 + #268):

- **No iconography.** Every icon in the app is an OS-native `QStyle.SP_*` stock icon —
  17 call sites: 5 on the main tabs (`ui_manager.py:129-133`), 4 more on long-lived
  buttons/labels in `ui_manager.py`, and 8 inside the analysis-table context menu in
  `main_window_pyside.py:1471-1567`. There is no `setWindowIcon` call anywhere, so the
  app has no taskbar or title-bar identity at all.
- **No embedded font.** `shared/theme.py:54` hardcodes `font_family = "Segoe UI,
  sans-serif"` and it is never bundled. Track 1 centralized *sizes and weights* into
  `TYPE_SCALE`; the family was left alone.

Track 1 established the seam this track plugs into: `gui/theme_manager.py` is the
repo-owned customization point, and `shared/theme.py` must never be hand-edited here
(it is one-way synced from `packing-tool` — see `CLAUDE.md`).

## Decisions made in this brainstorm

Two were put to the user; the rest follow from the code.

1. **Embed Inter (2 static weights)** — user's call, chosen over keeping Segoe UI or
   embedding it as a Linux-only dev fallback. Production is Windows-only, where Segoe UI
   always exists, so this buys visual consistency and dev/prod parity rather than
   availability. Accepted cost: the app stops rendering in the native Windows face, and
   text metrics shift on every screen.
2. **Replace all 17 `QStyle.SP_*` sites**, not just the 5 tabs the vision doc names —
   user's call. Lucide line icons sitting beside OS-native Windows icons in the same
   window reads as broken rather than as either style. The `☰` and `⚙` plain-text glyph
   buttons in the global header stay out of scope; the vision doc assigns those to
   Track 3.
3. **Recolor by SVG source substitution, not `CompositionMode_SourceIn`.** The vision
   doc proposed the pixmap-composition technique. Every Lucide icon sets
   `stroke="currentColor"`, so substituting that string and rendering with
   `QSvgRenderer` is both shorter and strictly better: it recolors *vectors* before
   rasterization, so output is crisp at any size and DPI instead of a recolored raster.
   Verified working (see Validation).
4. **Commit the assets; no fetch script.** 15 SVGs (~15 KB) and 2 TTFs (~830 KB) go into
   the repo directly. Provenance and upgrade instructions live in a 10-line
   `gui/assets/README.md`. A download script would be machinery for a one-time job, and
   would make the frozen build depend on network access.
5. **Load fonts from `ThemeManager.get_current_theme()`, not `gui_main.py`.** The vision
   doc says `gui_main.py` at startup. Calling it from the theme manager instead is
   strictly better: it is the only place that needs the family name, it is idempotent
   and cached, and it means the tests (which construct `MainWindow` without going
   through `main()`) exercise the same path production does. `gui_main.py` needs no
   change for fonts at all.

## Component 1 — `gui/icons.py`

Single public function:

```python
def icon(name: str) -> QIcon
```

- Reads `gui/assets/icons/<name>.svg`. Unknown name raises `KeyError` — same fail-loud
  rule Track 1 set for `font_css()`: a typo must break during development, not silently
  render a blank icon in production.
- Substitutes `currentColor` with the current theme's `text` color, then renders through
  `QSvgRenderer` into pixmaps at **16, 24, 32 and 48 px**, all added to one `QIcon` via
  `addPixmap()`. Qt then picks the right one for the widget size and the screen's device
  pixel ratio, so the icons stay sharp on the 125%/150%-scaled displays common on
  Windows warehouse PCs. This avoids querying `devicePixelRatio` ourselves, which is
  per-screen and wrong on multi-monitor setups.
- Caches on `(name, color)`. No invalidation is needed on theme change: the colour
  *is* part of the key, so a toggle simply misses into a second set of entries. Two
  themes × 15 icons is the ceiling.

Notably this depends on `PySide6.QtSvg` (the module) but **not** on Qt's `qsvg`
imageformats plugin, because we drive `QSvgRenderer` directly rather than letting
`QIcon` load an `.svg` path. That is one less thing for PyInstaller to fail to collect.

### Theme switching

Icons handed to `addTab()` / `setIcon()` are snapshots — they do not follow a theme
toggle, and a dark-gray icon on a dark background is invisible. Rather than a
registration/weakref system, the call sites split cleanly by lifetime:

- **8 context-menu icons** (`main_window_pyside.py:1471-1567`) sit inside a `QMenu`
  rebuilt on every right-click. They call `icon()` fresh each time and are correct by
  construction. Nothing to do.
- **9 long-lived icons**, all in `ui_manager.py` and all reachable via `self.mw.*`:
  the 5 tab icons, the session-folder `QLabel` pixmap (`:185`), and three buttons
  (`open_session_folder_button` `:721`, `new_session_btn` `:1055`,
  `clear_filter_button` `:1098`). One `_refresh_icons()` slot connected to the existing
  `theme_changed` signal re-sets all nine. `ui_manager.py:1237` already connects
  `_update_theme_button_text` to that signal, so this follows an established pattern.

### Icon mapping

Fifteen distinct Lucide glyphs, pinned to **Lucide 1.31.0**. Pinning matters: Lucide
renamed `filter` → `funnel` in 2025, and `filter.svg` now 404s on `main`.

| Site | Today | Lucide |
|---|---|---|
| Tab: Session Setup | `SP_FileIcon` | `clipboard-list` |
| Tab: Analysis Results | `SP_FileDialogDetailedView` | `table` |
| Tab: Session Browser | `SP_DirIcon` | `folder-open` |
| Tab: Information | `SP_MessageBoxInformation` | `info` |
| Tab: Tools | `SP_FileDialogContentsView` | `wrench` |
| Header session label `:185` | `SP_DirIcon` | `folder` |
| Open Session Folder `:721` | `SP_DirOpenIcon` | `folder-open` |
| Create New Session `:1055` | `SP_FileDialogNewFolder` | `folder-plus` |
| Clear filter `:1098` | `SP_DialogResetButton` | `funnel-x` |
| Menu: Change Status | `SP_BrowserReload` | `refresh-cw` |
| Menu: Add Tag | `SP_FileDialogDetailedView` | `tag` |
| Menu: Internal Tags submenu | `SP_FileDialogDetailedView` | `tags` |
| Menu: Remove Item | `SP_DialogCancelButton` | `circle-minus` |
| Menu: Remove Order | `SP_TrashIcon` | `trash-2` |
| Menu: Copy Order Number / Copy SKU | `SP_FileDialogDetailedView` | `copy` |
| Window/app icon (new) | — | `package` |

Three separate menu actions currently share `SP_FileDialogDetailedView`, which is why
the app's icons carry no meaning today; the mapping above gives each its own glyph.

### Window icon

`setWindowIcon` in `gui_main.py`, using `package` rendered at 16/32/48/256 px. Coloured
with `accent_blue` rather than `theme.text`, and **not** re-themed: a taskbar icon has
to read against whatever the OS shell's own background is, which has nothing to do with
this app's theme. Per the vision doc's non-goals, one bundled glyph is the whole scope
here — a real brand identity is a separate, much larger ask.

## Component 2 — `gui/fonts.py`

```python
def load_bundled_fonts() -> str | None   # returns "Inter", or None if unavailable
```

- Registers `gui/assets/fonts/Inter-Regular.ttf` and `Inter-Bold.ttf` via
  `QFontDatabase.addApplicationFont()`. Both report family `"Inter"`, so Qt picks the
  real Bold face for `font-weight: bold` rather than synthesizing one. Only two weights
  are bundled because `TYPE_SCALE` only expresses normal and bold.
- Idempotent and cached — safe to call from `get_current_theme()`, which runs on roughly
  180 call sites across `gui/*.py`.
- Returns `None` if `addApplicationFont()` fails (returns `-1`) or the files are
  missing. **Never raises.** A missing font must degrade to Segoe UI, not prevent the
  app from starting — this is the opposite of the fail-loud rule for icon names, and
  deliberately so: an icon name is a developer typo caught in seconds, a missing font
  file at a warehouse PC is a production outage.

### Wiring into `ThemeManager`

```python
def get_current_theme(self) -> ThemeTokens:
    theme = get_theme(self._current_theme_name)
    family = load_bundled_fonts()
    if family:
        theme = replace(theme, font_family=f"'{family}', {theme.font_family}")
    return theme
```

Keeping the original value on the tail of the family list is free insurance — if Inter
ever fails to register on one machine, that machine silently falls back to Segoe UI
instead of to Qt's generic default.

The result is memoized per theme name. `get_current_theme()` is called from ~180 sites
and `dataclasses.replace()` allocates; a two-entry dict removes that churn entirely.

`shared/theme.py:201` is the single place `font_family` reaches the stylesheet, so this
one override covers the whole app.

## Packaging

- `.github/workflows/build_release.yml:95` gains a second
  `--add-data "gui/assets;gui/assets"` next to the existing
  `shopify_tool/templates` entry.
- Runtime path is `Path(__file__).resolve().parent / "assets"`, the identical pattern
  `shopify_tool/barcode_processor.py:23` already uses for its templates directory and
  which is already proven to work under PyInstaller `--onedir`.
- License files ship alongside the assets: `gui/assets/icons/LICENSE` (Lucide, ISC) and
  `gui/assets/fonts/OFL.txt` (Inter, SIL OFL 1.1). Both licenses permit redistribution;
  both require the notice travel with the files.

## Validation already performed

Spiked against PySide6 6.11.1 before writing this document, because two assumptions
would have cost an implementation cycle each if wrong:

- **SVG recolor works.** `QSvgRenderer` accepts the substituted source
  (`isValid() == True`), and the rendered pixmap's opaque pixels come out at exactly the
  requested colour for both a light-theme and a dark-theme value. Rendering at
  `devicePixelRatio` 2.0 produced 720 painted pixels against 219 at 1.0 — genuine vector
  re-rasterization, not upscaling.
- **Inter registers correctly.** Both TTFs return a valid font id and report
  `applicationFontFamilies() == ['Inter']`; `"Inter" in QFontDatabase.families()` is
  `True` afterwards; and the regular and bold faces produce different text advances
  (88 px vs 91 px for `"Session Setup"`), confirming the Bold face is real.
- **`QFont.exactMatch()` is not a usable check** — it returns `False` even for a
  correctly registered Inter. The self-check must assert on
  `QFontDatabase.families()` membership instead. This one would have been diagnosed as a
  packaging bug.

## Testing

Following the vision doc's testing note and Track 1's guard-test precedent:

- `tests/test_icons.py` — `icon()` returns a non-null multi-size `QIcon`; an unknown
  name raises `KeyError`; the rendered pixmap actually contains the theme's text colour;
  and the colour changes after a theme toggle.
- `tests/test_fonts.py` — `load_bundled_fonts()` returns `"Inter"` and the family is
  registered; `get_current_theme().font_family` leads with Inter and retains Segoe UI as
  fallback; and it returns `None` without raising when the assets directory is
  monkeypatched away.
- **Two guard tests**, mirroring the bypass guard Track 1 shipped:
  1. No `QStyle.SP_` occurrences remain anywhere under `gui/` — the whole point of this
     track, and the thing most likely to silently regress when a future dialog is added.
  2. Every icon name passed to `icon()` anywhere under `gui/` has a matching
     `.svg` file on disk. This is the failure mode `KeyError` alone cannot catch, since
     a rarely-opened dialog's icon might not be exercised by any test.

Both guards use `rglob`, not `glob` — Track 1's review caught exactly that bug, and
`gui/` gains a `components/` package in Track 3.

## Known visual risks

Neither blocks the merge; both are one-line adjustments afterward. Recording them
because they are the predictable "this looks wrong on Windows" reports.

- **Inter renders smaller than Segoe UI at the same point size.** Measured 16 px line
  height against the fallback's 18 px at 10pt. Track 1 already shipped a freshly
  designed type scale that has never been seen on Windows, so this stacks a second
  uncalibrated visual change on top of the first. If text reads small, the fix is a
  one-line `TYPE_SCALE` bump in `gui/theme_manager.py` — which is precisely why Track 1
  centralized it.
- **Lucide's 2px stroke on a 24px grid softens at 16px.** Tab icons render at ~16px, so
  strokes land at ~1.33px and anti-alias. Accepted for a first pass. If it reads muddy,
  the fix is a `stroke-width` substitution alongside the existing `currentColor` one.

## Non-goals

- The `☰` and `⚙` plain-text glyph buttons in the global header — Track 3.
- Any edit to `shared/theme.py` or `packing-tool`. If the icon module or the font
  bundling proves useful upstream, that is a future `packing-tool`-side change, per the
  vision doc.
- A brand identity or logo. One bundled glyph resolves "the app has no icon anywhere".
- Italic, and any weight beyond regular and bold. `TYPE_SCALE` expresses neither.
- Migrating the remaining hardcoded `color: red` at `gui/column_mapping_widget.py:152`,
  which Track 1 left commented as Track 3 scope.
