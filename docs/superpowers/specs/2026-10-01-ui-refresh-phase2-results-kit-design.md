# UI refresh phase 2: Results to mockup, and the web kit

**Task:** dev-runner run 38, Todoist 6hfx8cmwgmH4Gjfv: "UI refresh phase 2: Results to mockup and the web kit".
Brief: `docs/design/ui-refresh/roadmap.md`, phase 2. Depends on phase 1 (merged, #355).
**Path:** architectural. It adds a shared stylesheet every later web page links, changes the theme's token
contract and the shared lint, and changes how the Results page selects orders and confirms bulk actions.
**Mockup followed:** `docs/design/ui-refresh/mockups/results.html` (all six states, both themes) and
`component-sheet.html` (the kit's components). Every departure is in §9.

## 1. What this task delivers

1. Seven tokens in `shared/theme.py`, and a `shared/style_lint.py` that allows `box-shadow` in a stylesheet in
   exactly three spellings (§3).
2. `gui/web/kit.css`: the stylesheet every web page links first (§4), and a kit sheet that renders every kit
   component for tests and for the eye (§4.3).
3. The Results page rebuilt to the mockup on top of the kit (§5).
4. The session chip in the command bar on Results, and a screen menu that takes over what leaves the bar (§6).
5. Docs: `CONTEXT.md`, two ADR amendments, `roadmap.md` (§8).

## 2. Owner's decisions (2026-10-01, run 38)

| Question | Answer |
|---|---|
| A third "Held" status, as the mockup draws | No. Two statuses, as today: Fulfillable and Blocked. The mockup's badge look only |
| Where the column manager lives | A popover under the Columns button holding the full manager. The pane stays visible |
| "Becomes Fulfillable" when a short SKU is removed | Not in this phase. The popover lists only what really changes. Follow-up task (§10) |
| The Qt confirm dialog after the bulk popover | Removed. The popover confirms. Bulk "Exclude from run" moves into More with the same popover |
| The design | Approved, with the kit built in full: segmented control, banner and page header too |

## 3. Tokens and lint (`shared/`, edited here; Packing Tool gets them at its next sync)

### 3.1 New tokens

Fields on `ThemeTokens`, declared after `control_disabled_bg`. No defaults: each is spelled out per theme.

| token | light | dark | kind | used by |
|---|---|---|---|---|
| `surface_inverse` | `#303030` | `#E3E3E3` | colour | toast background |
| `on_inverse` | `#FFFFFF` | `#1A1B1E` | colour | toast text |
| `critical_fill` | `#C70A24` | `#C4343F` | colour | the bulk popover's confirm button |
| `on_critical` | `#FFFFFF` | `#FFFFFF` | colour | text on `critical_fill` |
| `card_border` | `transparent` | `#2E2F34` | CSS value | card edge (dark mode's substitute for the shadow) |
| `card_shadow` | `0 1px 0 rgba(26,26,26,0.07), 0 1px 3px rgba(26,26,26,0.12)` | `none` | CSS value | cards, secondary buttons, filter chips |
| `overlay_shadow` | `0 4px 12px rgba(26,26,26,0.2)` | `none` | CSS value | menus, popovers, toast |

`critical_fill` and `on_critical` are not in the roadmap's list. The mockup's `const T` has `critical_fill`
and paints white on it, and a hex in a stylesheet is banned, so the white needs a token too.

### 3.2 Registration and validation

- The four colours join `_COLOR_FIELDS` after `"control_disabled_bg"`. That gives them the `#RRGGBB` check and
  the `theme_css_vars` emission check.
- `_SURFACE_PLANES` must stay the four planes it is today. `surface_inverse` starts with `surface`, so the
  derivation excludes it by name:
  `tuple(f for f in _COLOR_FIELDS if f.startswith("surface") and f != "surface_inverse")`.
  Two reasons: every text floor would fail against a dark plane in light mode, and Packing Tool's
  `tests/test_theme.py` asserts the tuple equals the four planes.
- `validate_theme` gains one loop over `_INVERSE_PAIRS = (("on_inverse", "surface_inverse"),
  ("on_critical", "critical_fill"))`: each pair must reach 4.5:1. Measured (light / dark): 13.2 / 13.4 for
  inverse, 6.0 / 5.4 for critical.
- The three CSS values go in a new tuple `_CSS_VALUE_FIELDS = ("card_border", "card_shadow",
  "overlay_shadow")`. `validate_theme` checks each is a non-empty `str` containing none of `;`, `{`, `}`, so a
  value cannot close the `:root` block it is written into. They are not hex-checked.
- `theme_css_vars` already emits every dataclass field, so the three arrive as `--card-border`,
  `--card-shadow` and `--overlay-shadow` with no code change. Its "did not emit" check extends to
  `_CSS_VALUE_FIELDS`.
- No contrast floor is added to `_MIN_CONTRAST_ON_PLANES`, so Packing Tool's mirrored floor test needs no
  change.

### 3.3 `shared/style_lint.py`

In a web asset, a `box-shadow` declaration is clean when its whole value is `var(--card-shadow)`,
`var(--overlay-shadow)` or `none`, ended by `;` or `}`. Everything else is still a `banned` finding: any
other value (including `inset` and a literal offset), `-webkit-box-shadow`, `.style.boxShadow`, and
`setProperty("box-shadow", …)`. A shadow in an inline `style="…"` attribute is flagged too, token or not:
shadows belong in a stylesheet. The value's ending does not show that (an inline declaration can end in `;`
as well), so the scan also looks for an unclosed `style="` earlier on the line (`_INLINE_STYLE`).

Implementation: `_BANNED` stays as it is. `_scan_web_asset` skips a `banned` match whose captured property is
exactly `box-shadow` when `_SHADOW_OK.match(code, m.end())` succeeds, where
`_SHADOW_OK = re.compile(r"\s*(?:var\(\s*--(?:card|overlay)-shadow\s*\)|none)\s*[;}]")`.
The module docstring's "banned" sentence is updated to say so and to cite ADR 0016.

## 4. The web kit

### 4.1 Files

- `gui/web/kit.css`: fonts, reset, kit geometry, the z-index scale (`--z-sticky` to `--z-toast`, moved from
  `results.css` so every page stacks the same way), components. No page-specific selector, no `#id`.
- `gui/web/results.html` links `kit.css` and then `results.css`.
- `gui/web/results.css` keeps only what is Results': the page grid, KPI cells, filter bar layout, table,
  selection bar, pane and column manager.
- Every colour is a `var(--token)` from `theme_css_vars`. Sizes that the theme does not own are kit constants
  on `:root` in `kit.css`:

  ```css
  --kit-radius: 8px;          /* buttons, inputs, menus' items use --radius-md (6px) */
  --kit-radius-card: 12px;    /* cards, popovers */
  --kit-control-compact: 24px;
  ```

  Pills use `--radius-lg` (10px), inner items `--radius-md` (6px), checkboxes `--radius` (4px): those three
  already match the mockup.

### 4.2 Components

Border mapping (ADR 0018): the mockup's `border` and `border_subtle` are hairlines and both become
`--border-subtle`. The mockup's `border_strong`, and its `border` where it is the edge of a button or an
input, become `--border`.

| class | what it is |
|---|---|
| `.card` | `--surface`, `1px solid var(--card-border)`, radius 12, `box-shadow: var(--card-shadow)` |
| `.btn` | height `--control-height`, padding 0 12, radius 8, bold, `1px solid transparent`, no wrap |
| `.btn.primary` | `--accent-fill` / `--on-accent`, hover `--accent-fill-hover`, active `--accent-fill-active`, card shadow |
| `.btn.secondary` | `--surface`, edge `--border`, card shadow, hover `--hover` |
| `.btn.ghost` | transparent, hover `--hover` (the mockup's "Plain"; named for the Qt role) |
| `.btn.dashed` | transparent, `1px dashed var(--border)`, hover `--surface` |
| `.btn.danger` | secondary with `--status-danger` text. `.btn.ghost.danger`: transparent, hover `--status-danger-bg` |
| `.btn.critical` | `--critical-fill` / `--on-critical` |
| `.btn.icon` | square, `--control-height` wide, no padding. `.btn.compact`: height 24, padding 0 10 |
| `.btn:disabled` | `--control-disabled-bg`, `--text-disabled`, `1px dashed var(--border)`, `box-shadow: none`, `cursor: not-allowed` |
| `.badge` | 20px high, padding 0 8, radius 10, caption size, bold. `.success` `.danger` `.warning` `.info`: the role's `_bg` and foreground. `.neutral`: `--surface-raised`, `1px solid var(--border-subtle)`, `--text-secondary` |
| `.code` | a neutral badge in the mono face, radius 6: reason codes, the session id |
| `.input` | a label wrapping a glyph and an `<input>`: `--control-height`, radius 8, edge `--border`, `--surface`; `:focus-within` draws the 2px `--focus-ring` outline. `.input.invalid`: edge `--status-danger`, fill `--status-danger-bg` |
| `input[type=checkbox]` | `appearance: none`, 16px, radius 4, edge `--border`, `--surface`. Checked or indeterminate: `--accent-fill`, no edge, and an `::after` in `--on-accent` shaped by `clip-path` (a tick, or a bar for indeterminate). No rotation: `transform` is banned |
| `.segmented` / `.segment` | track: `--surface-sunken`, `1px solid var(--border-subtle)`, radius 8, padding 2, gap 2. Segment: 24px, padding 0 10, radius 6, `--text-secondary`. `[aria-checked="true"]`: `--surface`, `1px solid var(--card-border)`, card shadow, bold, `--text`. `.segment-count`: mono caption |
| `.menu` | `--surface-overlay`, `1px solid var(--border-subtle)`, radius 12, padding 6, overlay shadow. `.menu-item`: 30px, padding 0 10, radius 6, hover `--hover`, `.danger` text. `.menu-group`, `.menu-separator`, `.menu-hint` as today |
| `.popover` | the menu's surface with no padding, for a titled panel with a footer |
| `.toast` | `--surface-inverse` / `--on-inverse`, radius 8, height 40, overlay shadow, 24px from the right and bottom edges. `.toast-action`: bold, underlined, transparent. `.toast-close`: 26px icon button |
| `.banner` | flex, gap 10, padding 10 12, radius 12. `.banner.danger`: `--status-danger-bg`, `1px solid var(--status-danger-border)`. `.banner.neutral`: the card's surface, edge and shadow. Parts: `.banner-title` (bold), `.banner-text`, `.banner-actions` (compact buttons) |
| `.state` | centred column, gap 6: a 22px glyph, `.state-title` (label size, bold), `.state-text` (`--text-secondary`, max 380px), then one secondary button |
| `.page-head` | flex, centred, gap 10, min-height 28. `.page-title`: heading size, bold. `.page-meta`: caption, `--text-secondary`. A `.code` chip sits between them; actions follow a `.spacer` |
| utilities | `.spacer`, `.mono`, `.glyph` (14px stroke icon, `currentColor`), `[hidden]` |

Every interactive kit element gets `:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px }`.

Only `.banner.danger` and `.banner.neutral` exist: the theme has a border token for danger only. A warning or
info banner arrives with the first screen that draws one, and brings its border token.

### 4.3 The kit sheet

`tests/web/kit_sheet.html` shows one of each component in §4.2, laid out like `component-sheet.html`'s
content area. It links `kit.css` and carries the `/* theme-vars */` marker. It is a test fixture, not shipped:
the release build copies `gui/web/` only. `tests/test_web_kit.py` loads it with the theme written over the
marker and `gui/web/` as the base URL, and the visual check (§7) renders it in both themes.

It exists because the segmented control, the banner and the page header have no screen yet. Without it they
would ship unseen.

## 5. The Results page

Geometry is the mockup's at 1366×768 unless §9 says otherwise. Element ids that exist today keep their names.

### 5.1 Page

- `body` is `--surface-sunken`. `#results` has padding `16px 24px 20px` and three rows 12px apart:
  the KPI card (88px, as today, so the table's height does not depend on a font), the filter bar
  (`--control-height`), the split card (the rest).
- `gui/ui_manager.py`: the page area's 5px inset becomes 0 while a web page is the current tab
  (`_WEB_PAGES = {1}`), and 5 again on a Qt page. Otherwise a white ring shows around the grey page.

### 5.2 KPI strip

One `.card` with a grid: four equal cells, then a fifth 196px cell. Cells are divided by
`1px solid var(--border-subtle)` on their left edge, padding 12px 16px.

- Each cell: a label (caption, bold, `--text-secondary`), a value (20pt, bold, line-height 1.1), a sub-line
  (caption, `--text-secondary`, ellipsis). Fulfillable's label carries an 8px `--status-success-dot` dot and
  Blocked's an 8px `--status-danger-dot` dot. 20pt is off the type scale, so it is one constant in
  `results.css` (`--kpi-value-size`).
- Numbers and sub-lines are today's (`results_summary`), unchanged: Orders, Fulfillable, Blocked, Labels.
- Fifth cell, when `summary.value_total` is `null`: an info glyph and "Order value shows once a price column
  is mapped." with a **Map columns** button under it (`id="map-columns"`, styled as a bold underlined link).
  It calls `bridge.openColumnMapping()` (§6.3).
- Fifth cell, when a price column is mapped: label "Value ready", today's compact value
  (`fmtCompact(value_ready)`), sub-line "across N fulfillable orders".
- "Oldest waiting" stays: a fifth equal cell before the value cell, shown only on a wide page, as today. The
  container query's threshold becomes 1496px so it still appears at the same window width (the page padding
  grew from 16 to 24).

### 5.3 Filter bar

Left to right: search, Add filter, the filter chips, Clear all, a spacer, the count, Columns, ⋯, Export.

- Search: a kit `.input` 260px wide with the search glyph.
- Add filter: `.btn.dashed` with a plus glyph. Its menu keeps today's groups and labels (Status, Flags,
  Courier, Tags) in the kit menu's look.
- A filter chip reads "Status is **Blocked**": the key in `--text-secondary`, the value bold, then a 20px ×
  button titled "Remove filter". Only the × removes it. Keys: Status, Flag, Courier, Tag. The chip is
  `--surface` with a `--border-subtle` edge and the card shadow, `--control-height` tall.
- Clear all (kept, §9) is a ghost button, shown when a chip or a query exists, as today.
- Columns: a ghost button with the columns glyph and the count in mono (`9/18`). It opens the column manager
  (§5.8).
- ⋯ : a ghost icon button. It still asks Python for the screen menu (§6.2).
- Export: always primary, with the download glyph. It no longer turns secondary while orders are checked.

### 5.4 The split card

`#table-area` is one `.card` with `overflow: hidden`, holding the table on the left and the pane on the right,
divided by the pane's `border-left: 1px solid var(--border-subtle)`. `data-slot` is `pane`, `rail` or `none`.

- Pane width 340px, rail width 40px. `TABLE_MIN_PX` becomes 728 and the narrow threshold 1068 (728 + 340), so
  the pane is open by default at 1366×768 with the sidebar expanded.
- Header row: 36px, `--surface-raised`, bottom rule `--border-subtle`, labels in caption bold
  `--text-secondary`. The Value header is `--text-disabled` while no price column is mapped.
- Rows: 32px at desk density (`--row-height` + 4, set by `results.js` as `--results-row-height`), bottom rule
  `--border-subtle`, hover `--hover`. The select column is 36px.
- Cells: Order is mono bold. Lines, Units, Value and Age are mono. A missing value is "—" in
  `--text-disabled`. Repeat shows an `.info` badge. Base widths follow the mockup (Status 108, Order 64,
  Customer min 140, Lines 52, Units 52, Value 76, Courier 72, Age 52, Repeat 76); a column still grows to its
  widest value.
- Status: a kit `.badge`, `.success` for Fulfillable and `.danger` for Blocked. No dot. Today's table dot is
  always hollow, so it carried nothing.
- The empty and no-match states are kit `.state` panels inside the card. No-match names what is filtering
  ("Status is Blocked and Courier is DPD and search is “x”.") and offers **Clear filters**.

### 5.5 Cursor and checked orders

Today one set does both jobs: a plain click selects a row, opens the pane and raises the selection bar. The
mockup splits them.

- **Cursor** (`state.cursorKey`): the one order the pane shows. Its row has class `cursor`:
  `--selection-bg` and a 3px `--selection-border` bar on its left edge, drawn as a `::before` pseudo-element.
  The selection ring is gone from this page.
- **Checked** (`state.selected`, the set Python hears through `setSelection`): the orders a bulk action
  reaches. A checked row has class `selected`, `aria-selected="true"`, a ticked box and `--surface-raised`.
  A row that is both shows the cursor's look and the ticked box.

| gesture | effect |
|---|---|
| click a row | cursor and anchor move to it, and a pane the operator hid reopens. The checked set does not change |
| click its checkbox (anywhere in the select cell), or Ctrl-click the row | toggles it in the checked set and moves the anchor. The cursor stays |
| Shift-click | checks the range from the anchor to the row (replacing the set, or adding with Ctrl) and moves the cursor to the row, so Shift+↑ ↓ carries on from it; a hidden pane reopens |
| ↑ ↓ | move the cursor and the anchor from the cursor (with no cursor, from the anchor a checkbox click left; with neither, from the first row); a hidden pane reopens |
| Shift+↑ ↓ | move the cursor and check the range from the anchor to it |
| Ctrl+A | checks every order shown |
| Ctrl+C | copies the checked order numbers; with none checked, the cursor's order number |
| Esc | closes the innermost open thing; otherwise clears the checked set; otherwise clears the cursor |
| header checkbox | with any checked, clears the set (title "Clear selection"); with none, checks every order shown |

A filter that hides an order still unchecks it and drops the cursor from it (ADR 0005), as today.

### 5.6 Selection bar

Shown while any order is checked. It covers the header row (36px, `--surface-raised`) from the first named
column on, as today, so the header checkbox stays reachable.

- "**N selected**" (bold). The units, value and courier counts are dropped (§9).
- **Mark N fulfillable** (secondary, compact): N counts the checked orders that are not fulfillable, and only
  those are sent to `setStatus(keys, true)`. With none, the label is "Mark N fulfillable" over all checked and
  the button is disabled.
- **Hold this** / **Hold these N** (secondary, compact): sends every checked order.
- **More** (secondary, compact, chevron): a menu of eight items, as wide as its labels (§9). The seven that exist keep today's
  count-aware labels ("Add a tag to 3 orders", "Remove a SKU from this order"). Order: add a tag, remove a
  tag, copy the order numbers (Ctrl+C), a separator (new), the two exports, a separator, then in danger text
  the two SKU removals and a new third item, "Exclude this order from the run" / "Exclude these N orders from
  the run".
- The Exclude and Clear buttons leave the bar.

### 5.7 Bulk popover

A `.popover` 384px wide under More: a title (label size), the picker, a "What will change" box, a hint, and a
footer with Cancel (secondary) and the verb.

- **Tags** (add, remove): today's picker and today's primary verb button. No "What will change" box: nothing
  is destroyed.
- **Destructive verbs**: the SKU picker is today's list (count per SKU, search above ten rows). The mockup's
  two-SKU switch does not hold a real session. Exclude has no picker. Under the picker, once a SKU is picked
  (at once for Exclude), a box (`--surface-raised`, `--border-subtle`, radius 8) titled "What will change"
  lists the consequences, and under it "You can undo this from the confirmation that follows." The verb is a
  `.btn.critical`, disabled until the box has something to say.

Every line in the box is computed in the page from the order payload and `summary.fulfillable`, and is true
of what Python then does. The popover is the only confirmation a removal gets, so it speaks for the checked
set it was opened on: its verb sends those keys, and it closes when the checked set changes (Ctrl+A or
Shift+↑ ↓ from the table) or the orders are pushed again (an undo). `hit` is the checked orders that carry the SKU (all checked orders for Exclude).
A list of order numbers shows up to four, or three and "and N more".

| verb | lines |
|---|---|
| Remove a SKU from these orders | "K {sku} line(s) removed from {orders}" · if any order has no other line: "{orders} has/have no lines left and leave(s) the session" · if the SKU's lines sit in fulfillable orders: "U unit(s) of {sku} go back to stock" · if a hit order is blocked and stays in the session: "{orders} stay(s) Blocked until marked fulfillable" · the export line |
| Remove orders containing a SKU | "{orders} leave(s) the session: results, export and labels" · if any is fulfillable: "U unit(s) go back to stock. Other orders do not get them until you mark them fulfillable or run the analysis again" · the export line |
| Exclude these orders from the run | the same two lines over every checked order · the export line |

The export line is "Export goes from X to Y orders", or "Export stays at X orders" when nothing fulfillable
leaves. X is `summary.fulfillable`; Y subtracts the fulfillable orders that leave the session. Units going
back to stock count only lines in fulfillable orders, because only those draw stock (ADR 0010).

Verb labels: "Remove {sku} from N", "Remove N order(s)", "Exclude N order(s)". With no hit the box reads
"None of these orders contain {sku}" and the verb stays disabled.

`gui/actions_handler.py`: the three `ConfirmDialog.ask` blocks in `bulk_remove_sku_from_orders`,
`bulk_remove_orders_with_sku` and `bulk_delete_orders` are deleted. Each already records an undo and raises an
undoable toast. Toast texts stay as they are.

### 5.8 Column manager

A `.popover` 280px wide, right-aligned under the Columns button, holding today's manager unchanged in
function: a head ("Columns" and the count), the search field, the grouped scrolling list (max-height 340px)
with grip, checkbox, title and note per row, and the foot with "Hide empty columns" and Reset. The close
button goes. It closes on Esc, on a click outside, and on a second click on Columns. The pane stays visible
behind it: the slot's `columns` mode is deleted.

### 5.9 Detail pane

- **Header** (36px, `--surface-raised`, bottom rule): "Order {number}" in bold, or "Order detail" with no
  cursor; the order's status badge; the hide button (chevron-right, 24px).
- **Body** (scrolls; padding 14, gap 14):
  1. Verdict: today's title in heading size and the role's colour, with the solid/hollow mark before it;
     then today's sentence(s) in body text; then the source line in caption.
  2. Meta (caption, `--text-secondary`): customer · country · courier · "{age} old" · value, each where known.
  3. Codes: one `.code` chip per reason. `ALL_LINES_IN_STOCK` for a ready order; `MARKED_FULFILLABLE` or
     `HELD_BY_USER` when set by a person; per problem `STOCK_SHORT`, `OUT_OF_STOCK`, `INVALID_QUANTITY`,
     `NO_SKU`, `HELD_BY_RULE`, `OTHER`; then `REPEAT_CUSTOMER`, `UNKNOWN_SKU`, `LOW_STOCK` for the flags.
     The flag chips leave the tags row.
  4. "N lines · U units" (caption, bold, `--text-secondary`).
  5. Lines: one box (`1px solid var(--border-subtle)`, radius 8), rows divided by hairlines. Each row: the SKU
     in mono bold and "× qty" in mono caption; the product name in caption (kept, §9); the stock sentence;
     one caption line per lot ("Lot {batch} · exp {expiry}", with "· ×{qty}" when the line has more than one
     lot; a lot cell that is plain text is shown as it is); and a 26px ⋯ button, always visible.
     - Stock sentence: for a short line with a `short` problem, "{have} of {need} in stock, short {need −
       have}" in `--status-danger` bold; with `out_of_stock`, "None in stock" the same way; otherwise
       "{Final_Stock} left in stock" in `--text-secondary`, omitted when unknown.
     - The ⋯ menu is today's: Remove this line, Change quantity…, Copy SKU. Remove this line is disabled on an
       order's only line, titled "Last line: exclude the order instead".
  6. Tags: the removable tag chips and "+ Tag", as today.
  7. Notes, as today.
- **Footer** (top rule, padding 10 14): the status verb (Hold or Mark fulfillable, secondary), **Exclude
  order** (`.btn.ghost.danger`), a spacer, and "↑ ↓  3 / 40" in mono caption. Today's ⋯ menu held only Copy
  order number and does not fit a 340px footer; Ctrl+C now copies the cursor's order number (§5.5).
- **No cursor:** "No order selected" and today's hint, centred.
- **Collapsed:** `#pane-show` fills a 40px rail: a chevron-left and "Order detail" written vertically
  (`writing-mode: vertical-rl`), hover `--hover`. Clicking a row or moving the cursor reopens a pane the
  operator hid, as the mockup does. A pane collapsed because the window is narrow stays a rail until its rail
  is clicked, as today.

### 5.10 Toast

The kit `.toast`: the text, the run badge (kept), **Undo** as a `.toast-action` when the operation can be
undone, and a new dismiss button (`id="toast-dismiss"`, × glyph, label "Dismiss"). Timing and the Undo rule
are unchanged.

## 6. Shell (Qt)

### 6.1 The command bar on Results

`CommandBar.set_results_mode(on: bool)`, called when the current tab changes (`on` is `index == 1`).

- On: the session button is drawn as the mockup's chip (mono caption, `--surface-raised`, `1px solid
  border`, radius 6, 22px high, no menu arrow). It is still the recent-sessions menu. The two status chips
  hide, and one caption label in `text_secondary` shows their text in the mockup's form: "analysed 14:06 ·
  stock file 19 h old". The open-folder button hides.
- Off: today's bar.
- `_SCREEN_ACTIONS` loses its entry for Results, so the bar shows no Run Analysis button there.

### 6.2 The screen menu

Still a Qt `QMenu` raised by the page's ⋯ (§9). Items: Run analysis again, Open session folder, Copy summary,
a separator, Add Product to Order, Undo.

- Run analysis again clicks `run_analysis_button` and is enabled when that button is.
- Open session folder is enabled when a session is open.
- Copy summary puts one line on the clipboard and toasts "Summary copied". The line comes from a new
  `gui.orders_view.summary_text(summary)`: "40 orders · 30 fulfillable · 10 blocked · labels DHL 10, DPD 10,
  Speedy 10", plus " · value ready 1234.50" when a price is mapped. Enabled when there are results.
- The enabled states are refreshed on the menu's `aboutToShow`.

### 6.3 Bridge

One new member on `ResultsBridge`, added to the catalogue here before the code:

| member | direction | meaning |
|---|---|---|
| `openColumnMapping()` slot → `columnMappingRequested` signal | JS → Python | the KPI hint's Map columns link |

`gui/ui_manager.py` connects it to `actions_handler.open_settings_window(page="Orders Mapping")`. The bridge
module's docstring names this spec as the catalogue's latest amendment.

## 7. Tests (test-first; the seams)

| Seam | File | Asserts |
|---|---|---|
| Tokens | `test_theme_palette.py` | The seven values per theme; both themes validate |
| Validation | `test_theme_contrast.py` | `_SURFACE_PLANES` is the four planes; a theme whose `on_inverse` equals `surface_inverse` fails; a `card_shadow` containing `;` or `}` fails; an empty one fails |
| Emission | `test_theme_css_vars.py` | `--card-shadow`, `--card-border`, `--overlay-shadow` are emitted with their exact values in both themes; the existing round-trip test still passes |
| Lint | `test_style_lint.py` | The three allowed spellings are clean. Still flagged: a literal shadow, `inset …`, `var(--border)`, `-webkit-box-shadow`, `.style.boxShadow`, `setProperty('box-shadow', …)`, and a shadow in an inline `style` attribute. `test_a_box_shadow_in_a_stylesheet_is_flagged` keeps its literal case |
| The shipped assets | `test_style_literals_guard.py` | unchanged: `gui/` scans clean with `kit.css` in it |
| Kit | `test_web_kit.py` (new) | `results.html` links `kit.css` before `results.css`; `kit.css` has no `#id` selector; on the kit sheet, computed styles: the checked segment's background is `surface`, the danger banner's is `status_danger_bg`, the toast's is `surface_inverse`, a disabled button's border style is `dashed`, a card's `box-shadow` is not `none` in light and is `none` in dark |
| Bridge | `test_results_bridge.py` | `openColumnMapping()` emits `columnMappingRequested` |
| No confirm | `test_actions_handler_bulk.py` | Each of the three bulk verbs changes the frame, records an undo and toasts with `undoable=True` without `ConfirmDialog.ask` being called |
| Summary text | `test_results_summary.py` | `summary_text` for a session with and without a price column, and `""` for an empty summary |
| Page: KPI | `test_results_document.py` | One `#kpis.card`; the hint and `#map-columns` show when `value_total` is null and clicking it emits `columnMappingRequested`; the Value ready cell replaces it otherwise |
| Page: cursor and checked | `test_results_document.py` | A plain click sets `.cursor`, leaves `bridge.selection()` empty and the bar hidden; a checkbox click checks and leaves the cursor where it was; Shift-click and Shift+↓ check a range; Esc clears checked, then the cursor; ↓ moves the cursor only; a click reopens a hidden pane |
| Page: selection bar | `test_results_selection_bar.py` | "3 selected"; Mark counts and sends only the blocked ones and is disabled when none; More lists the eight items in order; no `#selection-exclude`, no `#selection-clear`; Export stays primary |
| Page: bulk popover | `test_results_bulk_popover.py` | For each destructive verb on a known frame, the "What will change" lines read exactly as §5.7 gives; the verb is a `.btn.critical`, disabled until a SKU is picked; confirming calls the bridge slot once with the checked orders |
| Page: columns | `test_results_columns.py` | Opening Columns leaves `#pane` visible and `data-slot="pane"`; the popover closes on Esc and on an outside click; show/hide, reorder, hide-empty and reset still store what they stored |
| Page: pane | `test_results_pane.py` | Header title and badge; the code chips for a ready, a short, a hand-held and a rule-held order; the stock sentence for a short and an out-of-stock line; a lot line; Remove this line disabled on a single-line order; hiding leaves a rail whose text is "Order detail" |
| Page: toast | `test_results_toast.py` | `#toast-dismiss` hides the toast; its background is `surface_inverse` |
| Command bar | `test_commandbar_states.py` | In results mode the chips are hidden and the meta label reads "analysed 14:06 · stock file 19 h old"; out of it, today's chips; the action and open-folder buttons are hidden in results mode |
| Screen menu | `test_results_screen.py` | The item texts in order; Run analysis again follows `run_analysis_button`'s enabled state; Copy summary sets the clipboard |
| Page inset | `test_shell.py` | The page area's margins are 0 on Results and 5 on Setup |

Existing tests that pin what this spec changes (the ring's pixels, the 400px slot, `.chip`, the unified
selection, the Qt confirms, the `Analysed` chip on Results) are rewritten to the new behaviour in the same
commit as the change, never skipped or deleted without a replacement.

**Visual check (required, CLAUDE.md):** render the page through `QWebEngineView.grab()` at the page size a
1366×768 window gives, in light and dark, in each of the mockup's six states (Default, One selected, Three
selected, Bulk popover, No match, Toast), plus the pane collapsed and the Columns popover open. Render the kit
sheet in both themes. Render `MainWindow` on Results in both themes for the command bar and the page inset.
Compare with `mockups/renders/results.png` and `renders/component-sheet.png`, and with the mockup's other
states opened in Chrome. Save the light Default, the dark Three selected, the light Bulk popover and the
light kit sheet under `docs/design/ui-refresh/renders/phase2/` and attach them to the PR.

**Gate:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`, then `graphify update .`.

## 8. Docs

- `CONTEXT.md`:
  - **Web tier**: no longer "Analysis Results only"; it names ADR 0016.
  - **Results document**: two cards, the KPI strip and one split card holding the table and the detail pane.
  - Add **Web kit**: the stylesheet every web page links first; components, never page layout.
  - Add **Badge**: the web tier's status pill, a tinted fill with no outline and no mark. **Chip** stays the
    Qt tier's outlined pill.
  - Add **Cursor** and **Checked orders** (§5.5); **Selection ring** says it is the Qt tier's, and that the
    web tier marks the cursor row with a bar.
  - **Detail pane**: collapses to a labelled rail. **Column manager**: a popover under the Columns button;
    the pane stays.
  - **Selection bar**: 36px, takes the header row's place, counts checked orders.
  - **Bulk popover**: for a verb that removes orders or lines it lists what will change and its verb confirms;
    no dialog follows, because Undo is real.
- ADR 0016, Consequences: the lint change is done; `box-shadow` is allowed only as the two shadow tokens or
  `none`.
- ADR 0007: the web toast now follows the web kit. The Qt toast in `shared/components/toast.py` keeps its look
  until the screens that raise it move.
- `docs/design/ui-refresh/roadmap.md`: phase 2 gets its spec and plan paths, the two extra tokens, and the kit
  sheet. "After the roadmap" gets the follow-up in §10.
- `README.md`: `gui/web/` is "the web pages and their shared kit".

## 9. Departures from the mockup

| Mockup | Phase 2 | Why |
|---|---|---|
| Pale control edges, disabled text, placeholders | Darker (`border`, `text_disabled`, `text_placeholder`) | ADR 0018 |
| 28px controls | `--control-height` (32px at desk) | The density token; the Qt shell beside the page uses it |
| A third Held status; "N held" under Orders | Two statuses | Owner, §2 |
| "1002 becomes Fulfillable" in the popover | "stays Blocked until marked fulfillable" | The app does not re-evaluate; owner, §2 |
| A two-SKU switch as the picker | A searchable list | A session has many SKUs |
| Columns as a checklist | The full manager in the popover | Owner, §2 |
| The cursor bar and separators as `box-shadow` | Pseudo-element and border | Only the shadow tokens may be a `box-shadow` (§3.3) |
| The ⋯ menu drawn in the page | A Qt menu | It already paints above the view; a web menu needs a bridge member and an enabled flag per item |
| Segoe UI | Inter | The bundled face both tiers use |
| "Open recent" and "New session" beside the chip | The chip is the recent-sessions menu; New session stays in the overflow | Roadmap phase 3 owns the bar |
| A trash button per line | A ⋯ menu per line | Change quantity and Copy SKU exist |
| A 268px More menu | As wide as its longest label (282px at desk) | The count-aware labels are longer than the mockup's |
| No scrollbar drawn | Chromium's bar in theme colours (`scrollbar-color` in `kit.css`) | A real session scrolls; the default bar is a light strip in dark |

Kept though the mockup does not draw them: Clear all, the tags row, notes, product names, Change quantity,
Add Product to Order, the toast's run badge, the stock-file age, the sixth "Oldest waiting" cell on a wide
page, the verdict's mark and its explanatory sentence.

Dropped because the mockup does not draw them: the units, value and courier counts in the selection bar; the
Exclude and Clear buttons in the bar (Exclude moved into More; the header checkbox and Esc clear); the pane
footer's ⋯ menu (Ctrl+C copies the order number); the column manager's close and Done buttons.

Found while building, and kept: the pane footer's two buttons are the kit's compact size, with 10px padding
and a wrap fallback, because "Mark fulfillable", "Exclude order" and "↑ ↓  25 / 40" fill 339px in Inter and a
three-digit position wraps to a second row rather than clip. The Results filter chips still clip when a
second chip meets a narrow page (the row's existing `overflow: hidden`); the mockup has room for one chip.
Inter's tabular digits are wider than the mockup's Segoe UI, so every width in the Results table is
measured from the page's own font, not copied from the mockup.

## 10. Out of scope

- Re-evaluating an order's status when its short SKU is removed (stock-ledger work; follow-up task).
- Any other screen. The Qt toast. Packing Tool screens.
- `kit.css` moving to `shared/`: it moves when Packing Tool adopts it, in a Packing Tool task.

## 11. Delivery

One PR on `cognitiveghost/shopify-fulfillment-tool` from `dr/14-ui-refresh-phase-2-results-to-mockup-and`.
No Packing Tool PR. The PR body says what reaches Packing Tool at its next sync: seven tokens in
`shared/theme.py` (no floor moved, `_SURFACE_PLANES` unchanged) and the `box-shadow` allowance in
`shared/style_lint.py`, which its own ADR 0001 still forbids it to use.
