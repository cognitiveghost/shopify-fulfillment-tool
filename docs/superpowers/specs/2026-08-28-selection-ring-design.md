# Selection: the ring replaces the accent fill

**Date:** 2026-08-28
**Todoist:** `6hP5mg5Mcc4wwrcV` (p2, Phase 8) — also closes `6hP5mg8wvrc5X4rV` (p4), see §7
**Worktrees:** `worktree-selection-ring` in **both** repos
**Authored in:** `packing-tool` (`shared/theme.py`), pulled into shopify with `scripts/sync_shared.py`

---

## 1. The problem

`shared/theme.py` paints item-view selection as a solid accent fill:

```python
QTableView::item:selected { background-color: accent_fill; color: on_accent; }   # :682
QListWidget::item:selected { background-color: accent_fill; color: on_accent; }  # :701
```

8.9's brief specifies the opposite: *"Selection is a 2px `selection_border` ring on
`selection_bg`, **not an accent fill**, so a row can show *selected* and *blocked* at
once."* The tokens exist and are validated. Nothing uses them for item views.

**Why this is a defect and not a preference.** `accent_fill` is the same `#006FBA` in
both themes, while every status token is theme-dependent. So any cell that paints its
own content lands on a background the theme system cannot reason about. That produced
three real defects in 1e (PR #302), all patched with workarounds rather than fixes:

| symptom | measured | current patch |
|---|---|---|
| status dot on a selected row | 1.05:1 (light) | a `theme.surface` backing disc |
| delegate labels on a selected row | 3.30:1 (light) | a `label_color()` helper returning `on_accent` |
| packing-bar track on a selected row | 1.05:1 (dark) | uses `border` instead of `surface_sunken` |

The first two carry a `ponytail:` comment in `gui/session_row_delegates.py` naming this
change as the fix. Under the ring, the dot is `status_info` on `selection_bg` = **4.80:1**
and needs no disc; labels are `theme.text` on `selection_bg` = **14.74:1 / 15.24:1** and
need no helper. **This change deletes code.**

It also unblocks 8.9's semantic directly: an accent fill cannot show *selected* and
*blocked* simultaneously, because it owns the whole cell background. A ring can.

---

## 2. What Qt can and cannot do (verified, not assumed)

QSS styles **cells**, not rows. `QTableView::item:selected { border: 2px solid X }`
therefore draws a box around every cell in the row — seven boxes on a seven-column row,
not one ring.

A pixel probe against a real `QTableWidget` (`SelectRows`, `showGrid(False)`) settles the
mechanic. With `border-top` + `border-bottom` only, the adjacent cells' edges join into
one continuous line across the full row width, including across cell boundaries:

```
x=100  #101014 #008EEE #008EEE #042134 … #042134 #008EEE #008EEE #101014
x=199  #101014 #008EEE #008EEE #042134 … #042134 #008EEE #008EEE #101014   <- cell edge
x=201  #101014 #008EEE #008EEE #042134 … #042134 #008EEE #008EEE #101014   <- next cell
```

Two further probe results that de-risk the implementation:

- **Delegate-painted columns inherit the ring.** A delegate following the 1e pattern
  (blank `opt.text`, then `style.drawControl(CE_ItemViewItem, …)`) renders identically to
  a plain cell — `#008EEE` band, `#042134` fill. No delegate change is needed to *get*
  the ring.
- **`QPalette.Highlight` does not leak through.** With the palette left on `accent_fill`,
  `#006FBA` appears nowhere in the rendered table once the `::item:selected` rule is set.

**Consequence for the design:** a table row gets a **top-and-bottom band**; a list item —
one item is one full-width cell — gets a **true four-sided ring**. This asymmetry is
forced by Qt, not chosen, and must be stated in the spec so it is not later "fixed".

### 2.1 Geometry stability

An unselected item has no border; a selected one gains 2px top and bottom. Without a
counter-rule the row's content jumps 2px when selected. The fix is already in this
codebase — `gui/theme_manager.py:380-385` styles the settings nav and carries the
comment *"matches :selected's accent bar so selecting does not shift text"*:

```python
QListWidget#settingsNav::item { border-left: 2px solid transparent; }
```

The global rules adopt the same trick with `transparent` top/bottom borders.

### 2.2 Hover currently defeats selection

The existing rules are ordered `::item:selected` then `::item:hover`. Both are
single-pseudo-state, so on equal specificity the later rule wins and **hovering a
selected row erases its selection colour today**. Latent, pre-existing, and cheap to fix
here: add an explicit `::item:selected:hover`.

---

## 3. Measured contrast

Every pairing the ring introduces, measured with the repo's own `contrast_ratio`:

| pairing | light | dark | floor |
|---|---|---|---|
| `selection_border` vs `selection_bg` | **4.75** | **4.80** | 3.0 (non-text) |
| `text` vs `selection_bg` | **15.24** | **14.74** | 4.5 — already asserted, `theme.py:339` |
| `status_info` vs `selection_bg` | **4.88** | **4.80** | 4.5 |
| `status_success` vs `selection_bg` | **4.86** | **5.94** | 4.5 |
| `status_warning` vs `selection_bg` | **4.84** | **7.66** | 4.5 |
| `status_danger` vs `selection_bg` | **4.85** | **4.76** | 4.5 |
| `text_secondary` vs `selection_bg` | **6.04** | **7.61** | 4.5 |

Every foreground clears AA on `selection_bg` in both themes. The accent fill cleared it
for exactly one foreground (`on_accent`); that is the whole difference.

`selection_bg` vs `surface` is 1.14 / 1.15 — low *luminance* separation, which is why the
2px `selection_border` band carries the signal and the fill only supports it. The band is
5.42 / 5.52 against `surface`, so the row boundary is unambiguous.

---

## 4. The regression the ring introduces

Status **chips** are drawn as a `status_*_bg` tint. Measured against `selection_bg`:

| tint | vs `selection_bg` (light) | vs `selection_bg` (dark) |
|---|---|---|
| `status_info_bg` | 1.00 | **1.00** |
| `status_success_bg` | 1.03 | 1.04 |
| `status_danger_bg` | 1.06 | 1.08 |

In dark, `selection_bg` **is** `#042134` — the same value as `status_info_bg`. An "active"
chip on a selected row is not merely low-contrast, it is *the identical colour*. The pill
disappears completely.

This is genuinely new: on `accent_fill` the tints cleared 4.3:1 unaided, which is why 1e's
chip branch needed no workaround while its dot branch did. Shipping the ring without
addressing it trades one selection defect for another.

**Fix: give the chip a 1px outline in its own `status_*` foreground.** The foreground
clears 4.5:1 on every plane *and* on `selection_bg` (§3), so the pill acquires a defined
edge on any background the theme can produce.

Chips are painted in two places, by two different mechanisms, so the outline is one line
in each:

| site | mechanism | change |
|---|---|---|
| `shared/theme.py::StatusChip.set_status` (`chip` variant) | `QLabel` stylesheet | add `border: 1px solid {fg}` |
| `gui/session_row_delegates.py::SessionStatusDelegate.paint` | `QPainter` | `setPen(QColor(fg))` instead of `Qt.NoPen` before `drawRoundedRect` |

`StatusChip`'s docstring currently reasons that *"validate_theme already proves every
`status_*` against its `status_*_bg` at 4.5:1, so the chip's contrast is guaranteed."*
That remains true and remains insufficient — it covers the label on its tint, never the
tint on whatever the chip sits on. The docstring is updated alongside, or the next reader
concludes this case is already handled.

This is the root-cause form of the fix, so it is not scope creep: it is what makes the
ring safe to ship. See §7 for what else it closes.

---

## 5. What does **not** change

Three call sites keep `accent_fill`, deliberately:

- **`QMenu::item:selected` (`:744`) and `QComboBox` `selection-background-color`
  (`:628`).** These are transient hover-tracking highlights in a popup, not persistent
  selection state. Nothing paints its own content into a menu row, and no menu item is
  ever simultaneously "selected and blocked". The ring solves a problem they do not have.
- **`build_palette`'s `Highlight` / `HighlightedText` (`:774`).** `QPalette.Highlight`
  drives *text* selection in `QLineEdit`/`QTextEdit`, which is a different affordance from
  row selection and correctly reads as an accent fill.

  There is also a hard blocker. `packing-tool/gui/packer_mode_widget.py:510` computes a
  cell background as `palette.color(Highlight).lighter(180)`, paired with
  `HighlightedText` as its foreground. On `accent_fill` that yields a usable pale blue.
  On `selection_bg` (`#E3F2FD`) it yields near-white, under a `#FFFFFF` foreground — an
  invisible "Pending" cell in Packer Mode. Repointing the palette would break a screen
  this change never intended to touch.

- **`QListWidget#settingsNav::item:selected` (`gui/theme_manager.py:387`).** Already the
  ring pattern (`selection_bg` + `theme.text`), but with a 2px **left** bar: it marks
  navigation position, not data selection. It keeps its own override, and it is the
  precedent §2.1 borrows from.

`QTabBar::tab:selected` never used the accent fill and is untouched.

---

## 6. The change

**`packing-tool/shared/theme.py`** — the only file that changes behaviour:

```python
# geometry: unselected items reserve the band so selection does not shift content
QTableView::item { border-top: 2px solid transparent;
                   border-bottom: 2px solid transparent; }
QTableView::item:selected { background-color: {selection_bg}; color: {text};
                            border-top: 2px solid {selection_border};
                            border-bottom: 2px solid {selection_border}; }
QTableView::item:selected:hover { background-color: {selection_bg}; }

QListWidget::item { border: 2px solid transparent; }
QListWidget::item:selected { background-color: {selection_bg}; color: {text};
                             border: 2px solid {selection_border};
                             border-radius: {r}px; }
QListWidget::item:selected:hover { background-color: {selection_bg}; }
```

Plus the chip outline of §4, and a `validate_theme` clause asserting every `status_*`,
`text` and `text_secondary` clears 4.5:1 on `selection_bg` — the matrix that would have
caught the original defect. `selection_border` vs `selection_bg` joins it at the 3.0
non-text floor.

**`shopify-fulfillment-tool`** — pure deletion, after `scripts/sync_shared.py`:

- delete the `State_Selected` disc branch in `SessionStatusDelegate.paint`
- delete `label_color()`; its two call sites become `theme.text`
- delete `tests/test_session_browser_1e.py::TestASelectedRowStaysReadable`, replaced by
  the `validate_theme` matrix, which covers the same property for every token rather than
  for the two that happened to break

---

## 7. Relationship to the archived-chip task

`6hP5mg8wvrc5X4rV` (p4) reports the `archived` chip having no visible pill: `archived`
maps to `text_secondary`, which has no `_bg` partner, so `StatusChip` falls back to
`surface_sunken` — 1.05:1 against the row.

§4's outline fixes that too, and fixes it at the root: **any** token without a `_bg`
partner has the problem, and any tint can collide with the background it lands on. An
outline in the chip's own foreground is one rule that covers both failure modes, where
changing the fallback tint covers only one. That task should be closed by this PR rather
than fixed separately.

Its guard still applies: `gui/session_row_delegates.py::chip_colors` intentionally
duplicates `StatusChip`'s rule, with a divergence test at
`tests/test_session_browser_1e.py::test_the_delegate_resolves_what_status_chip_resolves`.
Both sides must change together or that test fails — which is its purpose, and it is why
§4 lists both.

**The helper is not hoisted into `shared/` here.** The 1e comment nominates the second
call site as the moment to hoist, but that reasoning was about *colour resolution*, and
the two sites still resolve colours identically — it is the *painting* that differs
(stylesheet vs `QPainter`), and that cannot be shared. The divergence test already makes
the duplication safe, so hoisting would add cross-repo churn to this PR and remove
nothing. 8.9 gives packing-tool its own painted status column; that is a better trigger.

---

## 8. Testing

- **`validate_theme` matrix** (packing-tool) — the real regression guard. Parametrized
  over both themes, mirrored in `tests/test_theme.py` per the existing convention that
  the test copy is what catches someone *weakening* a floor.
- **Stylesheet assertions** — `accent_fill` no longer appears in the `QTableView::item` /
  `QListWidget::item` rules; `selection_border` and `selection_bg` do; the transparent
  counter-rules are present.
- **A pixel test for the band**, following §2's probe: select a row, render offscreen,
  assert `selection_border` runs continuously across a cell boundary and that a
  delegate-painted column matches a plain one. This is the assertion that would fail if a
  future change moves the border to all four sides and reintroduces per-cell boxes.
- **Both repos' full gates.** shopify: `QT_QPA_PLATFORM=offscreen python -m pytest` +
  `ruff check . --exclude shared`.

## 9. Risk

Selection appearance changes in **both** apps — visible to warehouse staff daily. It is
cosmetic, not navigational, so the "structure and labels never change in the same
release" guardrail does not bind; but it wants its own release note. The two repos must
merge together: shopify's deletions assume the synced `shared/theme.py`, so shopify's PR
depends on packing-tool's.

**Dark first, light after** (Phase 8 standing rule): both themes are contrast-validated
above, but the dark rendering is the designed one and light is derived from tokens.
