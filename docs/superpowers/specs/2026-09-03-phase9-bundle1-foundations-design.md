# Phase 9 Bundle 1 — Foundations: repaint, tokens, borders, controls

**Date:** 2026-09-03
**Status:** design accepted, nothing implemented
**Bundle:** Todoist `6hQXj66J9PhJ5G6V`, under Phase 9 `6hQVhRw68pqRH3f3`
**Covers:** the theme-repaint quick fix (`6hQVj7QQ7wg4xH8V`), 9.1
(`6hQVhmWG8CC9Cv9V`), 9.2 (`6hQVhmgfFr7RpMPV`), 9.5 (`6hQVhmmjf6gCCG73`)
**Mockups worked from:** artboards **F0**, **F0b**, **F1**, **F2**, **F3** of
Claude Design project *Fulfilment System v2*
`75385f2c-4be2-446c-8e9d-bf90ee063ff7`, read through `DesignSync` from
`F0 Foundation Specimen Sheet.dc.html`
**Phase spec:** `docs/superpowers/specs/2026-09-03-phase9-fulfilment-v2-design.md`
**Decisions:** ADR 0002 (glyphs in QSS `image:`), ADR 0003 (re-styling is a
closure) — 0003 is written by this bundle

---

## 1. Why these four are one cycle

All four land in `shared/theme.py` and `build_stylesheet()`. Shipped
separately they would be four PRs rebasing onto each other's edits to one
function. The internal order is fixed and load-bearing:

1. **the repaint fix** — 9.1 changes every colour in the app, which is exactly
   what turns a stale cached value into a visible artifact. Fixing the cache
   after the retune means debugging both at once.
2. **9.1** — the values.
3. **9.2** — the subtraction those values pay for.
4. **9.5** — the toggle, and three `build_stylesheet` corrections.

`shared/` is owned by `packing-tool`. Every `shared/` change here is authored
there and arrives through `scripts/sync_shared.py`. That is two PRs, one per
repo, `packing-tool` first — the same shape 9.0 used.

## 2. What investigation changed

Three things in the briefs did not survive contact with the repo. Each is
recorded here because Stage B would otherwise build the wrong thing.

### 2.1 The repaint diagnosis is wrong, and the fix shrinks

Measured, not assumed — see ADR 0003 for the probe and the numbers.
`app.setStyleSheet()` **already** repaints the table viewport, and every
delegate in this repo reads the theme at paint time, so the delegate half of
the brief describes a bug that does not exist. `unpolish()`/`polish()` cannot
fix the fault that does exist, because that fault is a stylesheet *string*
interpolated once at build time.

The prescribed remedy is therefore dropped in full: no repolish walk, no
`viewport().update()` sweep, no delegate work. What ships instead is one
shared helper, `on_theme_changed(widget, apply)`, plus conversions on the
surfaces the completion criterion names.

The brief's Done-when says "a regression test covers the delegate path". The
delegate path has no defect and the probe shows Qt already handles it. The
criterion is met in substance by a test that asserts the thing that *was*
broken — a converted widget's stylesheet follows a toggle — and that assertion
is what the plan specifies. This is a deliberate departure and Stage C should
confirm it.

### 2.2 The toggle needs a non-square glyph, which `glyph_url()` cannot render

9.0 shipped `shared.icons.glyph_url()` in full, exactly as ADR 0002 specifies —
it rasterises the recoloured SVG through `QSvgRenderer`, caches the PNG on a
digest of `(recoloured source, size)`, spells the path with `as_posix()`, and
raises rather than returning a url that draws nothing. It also vendored
`check`, `chevron-up`, `chevron-down`, `plus` and `ellipsis-vertical`. None of
that needs building.

Two gaps remain, and only one costs code.

**The radio dot needs no glyph.** A filled dot is `background-color` plus
`border-radius` on `QRadioButton::indicator:checked`. Lucide's convention is
`stroke="currentColor"`, so its `circle` draws a ring, not a dot — vendoring
one would be more work than the QSS that replaces it.

**The toggle track is 36×20, and `glyph_url()` renders squares.**
`_pixmap(source, size)` builds a `QPixmap(size, size)`, so a 36×20 glyph
arrives squashed. `glyph_url()` and `_pixmap()` therefore gain an optional
`height`, defaulting to `size` — every existing call is unchanged, and the
cache key extends to include it. This is the smallest change that makes a
non-square sub-control possible, and 9.4's sort carets will want it too.

The toggle's two states are **authored**, not vendored: Lucide has no toggle
track. Both are drawn entirely in `currentColor` so the single substitution
`glyph_url()` already performs is enough — see §5.2.

### 2.3 The dark values on the canvas disagree with themselves

`_blocks/F0-dark.txt`, a render block on the canvas, carries four values that
differ from the F0b table in the same project:

| token | `_blocks/F0-dark.txt` | F0b table | used |
|---|---|---|---|
| `status_info` | `#1E9BF0` | `#29A0F0` | table |
| `status_danger` | `#FF6A5E` | `#FF6659` | table |
| `selection_border` | `#1E9BF0` | `#29A0F0` | table |
| `hover` | `#1A1A1A` | `#232327` | table |

**The F0b table wins.** It is the specimen that states each change with its
measured before→after ratio and its floor (`status_info` 4.55 → 5.50 / 4.5),
its prose names the change list, and the Todoist brief agrees with it on
`hover`. The render block carries no ratios and is a drawing that drifted.
Taking the block instead would ship two tokens below the floor
`validate_theme` enforces, so the tests would catch it — but only after the
values had been transcribed twice.

## 3. The token retune (9.1)

Transcribed from the F0 and F0b tables. Values not listed are unchanged.
`validate_theme` is the contract and must pass in both themes.

### 3.1 Light — 22 values

| token | from | to |
|---|---|---|
| `surface_raised` | `#F4F4F5` | `#F2F2F4` |
| `surface_overlay` | `#EAEAEC` | `#E6E6EA` |
| `surface_sunken` | `#E8E8EB` | `#DADADF` |
| `text_secondary` | `#5A5A5A` | `#50505A` |
| `text_disabled` | `#808080` | `#6B6B73` |
| `text_placeholder` | `#686868` | `#5C5C64` |
| `border` | `#858585` | `#70707A` |
| `border_subtle` | `#D8D8D8` | `#C6C6CC` |
| `status_info` | `#006BB5` | `#005B99` |
| `status_success` | `#337635` | `#2C6630` |
| `status_warning` | `#985A00` | `#7A4A00` |
| `status_danger` | `#CF180A` | `#B31308` |
| `status_info_bg` | `#E3F2FD` | `#DCEBFA` |
| `status_success_bg` | `#EAF6EA` | `#E2F0E3` |
| `status_warning_bg` | `#FDF2E3` | `#F8EBD8` |
| `status_danger_bg` | `#FDE4E3` | `#FADFDD` |
| `accent_fill_hover` | `#0A78C4` | `#005F9F` |
| `accent_fill_active` | `#005A9E` | `#004B80` |
| `selection_bg` | `#E3F2FD` | `#DCEBFA` |
| `selection_border` | `#006DB7` | `#005B99` |
| `focus_ring` | `#0064AB` | `#005B99` |
| `hover` | `#EEEEEE` | `#E6E6EA` |

`surface` (`#FFFFFF`), `text` (`#1A1A1A`), `border_strong`, `accent_fill`
(`#006FBA`) and `on_accent` are unchanged.

The planes now run **218 / 230 / 242 / 255**. That even ramp is the whole
point: today `surface_sunken`→`surface_overlay` is a **2 sRGB unit** step, so
an input or a menu on the nav rail is invisible and the elevation rule has
nothing to work with.

Three values carry a rule rather than a measurement:

- **`hover` = `surface_overlay`.** Hover is an overlay state; a fifth
  off-ramp value is what made it invisible on the rail.
- **`selection_border` and `focus_ring` fold onto `status_info`.** Three blues
  within 0.02 of each other were three chances to pick the wrong one. Focus
  and selection are the same idea at two scopes.
- **`accent_fill_hover` darkens.** Lightening a fill is the one direction that
  costs contrast on the label sitting on it — `on_accent` goes 4.67 → 6.69.
  `accent_fill_active` moves down with it to stay a step past hover.

### 3.2 Dark — six foreground nudges, one realignment, no plane moves

| token | from | to |
|---|---|---|
| `border` | `#6D6D6D` | `#787878` |
| `text_disabled` | `#6E6E6E` | `#787878` |
| `text_placeholder` | `#8A8A8A` | `#949494` |
| `status_info` | `#008EEE` | `#29A0F0` |
| `status_danger` | `#F54E42` | `#FF6659` |
| `selection_border` | `#008EEE` | `#29A0F0` |
| `hover` | `#1A1A1A` | `#232327` |

Dark measures healthy. **All four dark planes stay exactly as shipped**, and
so do `text`, `text_secondary`, `status_success`, `status_warning`,
`focus_ring` and every tint. Do not edit dark for symmetry with light.

`accent_fill_hover` and `accent_fill_active` are theme-independent, so dark
receives 3.1's values for them too.

### 3.3 Aliases move on their own — but the literals do not

`_ALIAS_PAIRS` in `shared/theme.py` binds ten aliases to a canonical token and
`validate_theme` asserts each pair stays equal. The values are **literals in
the dataclass**, so every alias must be edited by hand to match; the assertion
is what catches a miss. The pairs that move here:

`accent_green` ← `status_success` · `accent_orange` ← `status_warning` ·
`accent_red` ← `status_danger` · `background_elevated` ← `surface_raised` ·
`active_background` ← `selection_bg` · `active_border` ← `selection_border` ·
**`button_hover_light` and `button_hover_dark` ← `accent_fill_active`**, which
is easy to miss because they sit under "unchanged interaction colors" in the
dataclass and are not visually alias-shaped.

`background` ← `surface` and `accent_blue` ← `accent_fill` do not move.

### 3.4 The comment that comes out

`LIGHT_THEME` opens with a note that `border` lands at 3.02 and
`status_warning` at 4.52, "both 0.02 above their floors… retune those two
tokens with it, not after." **This is that retune.** Delete the comment;
`border` now sits at 3.52 and `status_warning` at 5.37.

## 4. Borders stop being furniture (9.2)

Subtraction, not addition. The fault is a 1px border on every widget — eleven
outlines in one composition, so nothing is grouped because everything is.

- **`Card`** (`gui/components/card.py:27-28`) drops
  `setFrameShape(QFrame.StyledPanel)` + `setFrameShadow(QFrame.Raised)`, which
  draw an **OS frame underneath the stylesheet**, for `QFrame.NoFrame` plus one
  type-scoped rule: `Card { background-color: surface_raised; border: none;
  border-radius: 6px; }`.
- **Five `build_stylesheet` rules** that each say `border: 1px solid
  {theme.border}` today lose it: `QTableView`, `QListWidget`, `QGroupBox`,
  `QToolBar`, `QHeaderView::section`.
- **Borders stay** on `QLineEdit` / `QComboBox` / `QSpinBox`, on `QPushButton`
  (a hit target needs its edge), and on `:focus`.
- **Radius:** `QGroupBox` is `radius + 4` today while `Card` is `radius`. Both
  become `radius_md` (6). `radius_lg` (10) is dialogs only.

Qt has no `box-shadow`, so "raised" is a plane and never a shadow. That is the
entire reason §3's four-step ramp exists, and it is why 9.2 can only run after
9.1.

## 5. The control inventory (9.5)

### 5.1 The one change to `shared/icons.py`

`glyph_url()` and `_pixmap()` gain an optional `height`:

```python
def _pixmap(source: str, size: int, height: int | None = None) -> QPixmap
def glyph_url(name: str, color: str | None = None, size: int = 18,
              height: int | None = None) -> str
```

`height` defaults to `size`, so every existing call site and every cached PNG
keeps its current behaviour; the cache filename gains the height so a square
and a non-square render of the same glyph cannot collide. Nothing else about
the module changes — the `currentColor` substitution, the digest, the
`as_posix()` spelling and the raise-on-failed-write all stay exactly as 9.0
built them.

`glyph_url()` must keep handing QSS a `.png`. ADR 0002 measured why: `image:`
resolves through `QImageReader`, so an `.svg` there reintroduces a dependency
on the `qsvg` imageformats plugin — a PyInstaller collection hazard that
degrades *silently* to a blank image. A data URI does not work either; Qt's
QSS `url()` does not parse one.

### 5.2 The toggle switch — the only new control

A `QCheckBox` with a 36×20 `::indicator` and two authored glyphs,
`toggle-off.svg` and `toggle-on.svg`, added to `shared/assets/icons/` in
`packing-tool`. Lucide has no toggle track, so these are drawn rather than
vendored, and they follow Lucide's convention: **every stroke and fill is
`currentColor`**, so the single substitution `glyph_url()` performs is enough
and both themes are served by one file. The track and thumb separate by
`fill-opacity`, not by a second colour.

**No sliding thumb**: QSS has no transitions, and the travel does not earn a
`QWebEngineView`.

The checkbox tick uses the `check` glyph 9.0 vendored. The radio dot uses no
glyph at all — `QRadioButton::indicator:checked` draws it with
`background-color` and `border-radius`, because Lucide's stroke convention
would give a ring rather than a dot. Both reach QSS through `::indicator`, a
**sub-control**, which is legal — unlike `::before`.

### 5.3 Three corrections to what already ships

1. **`QPushButton` font size.** `build_stylesheet` hardcodes
   `font-size: 10pt`. It becomes `font_css("body")`, so a floor-density button
   grows with its own rung instead of staying at the desk size.
2. **Focus on a primary button.** A `focus_ring` border on an accent fill is
   invisible. **Primary alone** focuses with `2px solid border_strong`; every
   other variant keeps `focus_ring`. One exception, written down once.
3. **The spin box renders at 35px, not 32.** Qt's `QAbstractSpinBox` adds room
   for the up/down buttons *after* `min-height` applies, and `min-height` is a
   floor so it never binds. `DensityProfile.control_content_height` already
   documents this as a measured `ponytail:` shortcut. Specify it as it
   renders, not as the spec wishes.

Indeterminate progress stays a native `QProgressBar` (min=max=0): Qt animates
the widget itself, so no CSS animation is needed.

## 6. The repaint fix

Mechanism and rationale are ADR 0003. In short: `shared/theme.py` gains
`on_theme_changed(widget, apply)`, which applies now, re-applies whenever the
rendering inputs change, and disconnects when the widget dies.
`ui_manager._connect_theme_change` is the first hand-rolled copy of that trio
and is deleted in its favour.

Density is included by one line in `ThemeManager.set_density()`, which already
persists and repaints. `shared.set_density()` stays pure — its docstring says
"no QSettings, no restyle, no Qt" and that decision is not reversed here.

**Scope.** 53 theme-derived widget stylesheets exist across 14 files. Bundle 1
converts the surfaces the completion criterion names — the results table, the
session browser, and Settings (`gui/settings/*.py`) — and fixes the one real
stale-icon snapshot at `session_browser_widget.py:448`. The remaining files
convert as later bundles touch them. Converting all 53 now would be a large
diff in files this bundle otherwise never opens.

## 7. Riders

Two items `state.md` assigns to this bundle, both in `packing-tool`:

- **`_tokens_with_font()` is duplicated.** `packing-tool/gui/theme.py:48` and
  `shopify/gui/theme_manager.py:212` are the same memoised function under two
  names, each wrapped by a near-identical `_tokens()` / `_themed_tokens()`. It
  moves into `shared/theme.py` as `themed_tokens(name)` and both shims call
  it. A shim adapts; which font layers onto the tokens is a decision, so it
  belongs in the module that owns the tokens. `on_theme_changed` then has a
  correct source for the tokens it passes.
- **`shared/README.md` is stale.** It documents "Phase 1.4: Unified Statistics
  System" and nothing else, across 300+ lines, while `shared/` now holds the
  theme, the asset library, file locking, atomic writes and session IDs.
  Rewrite it to what the directory contains, with the one-way sync rule stated
  at the top.

## 8. Departures from the mockups

Named per Stage A's standing amendment.

| Departure | Why |
|---|---|
| The `_blocks/F0-dark.txt` values are not used; the F0b table's are | §2.3 — the block contradicts the table, and two of its values fail `validate_theme` |
| No repolish walk, contrary to the repaint brief | §2.1 / ADR 0003 — measured to fix nothing that is broken |
| The delegate regression test becomes a converted-widget test | §2.1 — the delegate path has no defect to regress against |
| `glyph_url()` gains a `height` parameter | §2.2 — it renders squares, and the toggle track is 36×20 |
| The radio dot is QSS, not a bundled glyph | §5.2 — Lucide's stroke convention draws a ring; `border-radius` draws the dot in one rule |

Everything else follows F0, F0b, F1, F2 and F3 exactly.

## 9. Done when

- `validate_theme` passes in both themes, and every foreground clears its floor
  in `_MIN_CONTRAST_ON_PLANES` with more than 0.1 to spare.
- `tests/test_theme_contrast.py` carries the new values in both repos.
- A card-on-panel-on-page composition separates by plane, with the only borders
  in it on an input and on the focused control.
- Every control on F3 renders in all five states in both themes, and a button's
  font size follows the active density profile.
- Switching theme on a populated results table, the session browser and an open
  Settings page leaves no stale colour, and a test asserts a converted widget's
  stylesheet follows the toggle.
- `ruff` and the full suite pass in both repos.
