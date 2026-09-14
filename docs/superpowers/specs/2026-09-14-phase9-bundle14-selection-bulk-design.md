# Phase 9 Bundle 14 — Selection, bulk actions, and the toast that lives inside

**Items:** 9.17 (W7, G4). The last bundle of Phase 9.
**Worktree:** `worktree-phase9-bundle14-selection-bulk`, from `ac8fc2f` (#325 merged).
**Reads:** roadmap § Track W / 9.17, canvas artboards W7 and G4, ADR 0001, ADR 0005,
Bundle 11 § 5.2 (the bridge catalogue), Bundle 13 § 9 (what it deferred here).

---

## 1. What is actually true of this code

The canvas was drawn against the app as it shipped in July. Three of its
assumptions are no longer true, and one was never true.

**Every bulk handler is already dead.** Bundle 12 replaced the Qt results table
and its toolbar with the web document, and took every call site with it.
Nothing in the repo reaches `bulk_change_status`, `bulk_add_tag`,
`bulk_remove_tag`, `bulk_remove_sku_from_orders`, `bulk_remove_orders_with_sku`,
`bulk_delete_orders` or `bulk_export_selection`. `add_tag_manually` (the
`QInputDialog` at `actions_handler.py:997`) is dead too — no caller, not even a
test. This bundle is not a rewire of a working screen; it is the restoration of
seven verbs that have had no door since Bundle 12.

**Every bulk operation is undoable, twenty deep.** `undo_manager.py` carries a
handler for all six write operations (`_undo_bulk_change_status`,
`_undo_bulk_add_tag`, `_undo_bulk_remove_tag`, `_undo_bulk_remove_sku`,
`_undo_bulk_remove_orders_with_sku`, `_undo_bulk_delete_orders`) and
`max_history` is 20. The brief's argument — "the confirm step goes because the
button says the consequence and Undo is real" — holds for all six, not just the
harmless ones.

**Four of W7's verbs have no backing code:** Assign courier, Add a note,
Re-allocate oldest-first, Reset manual overrides. This is the same situation
Bundle 13 met in the pane, where the ruling was *only verbs that exist*
(Bundle 13 § 11). The same ruling applies here.

**The selection already crosses the seam.** `bridge.selectionChanged` is wired
to `selection_helper.set_selected_orders` (`ui_manager.py:623`), and the page
reports on every render. What is missing is not the selection — it is anything
to do with it.

**`ContextualSelectionBar` is not touched.** G4's implementation note reads
"maps to `ContextualSelectionBar`, kept", but the surviving Qt bar belongs to
the Session Browser (D2) and is already built. The Results bar is a web
element that mirrors its composition — 44px, a counting sentence on the left,
actions on the right — and shares no code with it, because they are in
different renderers. The Qt class keeps its one caller and its one test.

---

## 2. Decisions taken by the owner this run

| Question | Answer |
|---|---|
| W7's second slot, where "Assign courier" was drawn | **"Hold these 3"** — `bulk_change_status(False)`, the exact inverse of the primary, and the pane's own word for it |
| `bulk_remove_sku_from_orders` / `bulk_remove_orders_with_sku`, dead since Bundle 12, on no artboard | **Restore both** into More |
| "Add a note to 3 orders", drawn in More with no bulk writer behind it | **Dropped.** `add_tag_manually` is deleted with the other dialog chains |
| The Qt toasts Bundle 13's pane verbs raise, over a `QWebEngineView` | **Every Results-screen toast moves into the document.** This closes Bundle 13 § 9's open question |

---

## 3. The selection bar (W7)

### 3.1 Where it goes, and what it costs the table

```html
<div class="table-wrap">
  <div id="selection-bar" class="selection-bar" role="toolbar" hidden>…</div>
  <div id="table" class="table" role="grid">…</div>
  …
</div>
```

Inside `.table-wrap`, above `#table` — not above `#table-area`. The bar belongs
to the table because the selection is the table's; putting it a level higher
would shorten the 400px slot too, and the pane would jump 44px every time a row
was picked.

44px exactly, `--selection-bar-height`. **No transition** — a bar that fades in
is a bar you act on before it has arrived, and `shared/style_lint.py` bans
`transition` in web assets anyway.

`layout()` loses 44px from the row budget when the bar is up:

```js
const SELECTION_BAR_PX = 44;
const barPx = els.selectionBar.hidden ? 0 : SELECTION_BAR_PX;
const rows = Math.max(0, Math.floor((els.tableArea.clientHeight - barPx - HEADER_PX) / state.rowH));
```

At 768 that is 17 rows without a selection and 15 with one. The rows come off
the table, never out from under it.

### 3.2 Anatomy, left to right

| Part | Copy | Role |
|---|---|---|
| Count | `3 orders · 11 units selected` | body, `--text-primary` |
| Sub | `612.10 · 2 couriers` | caption, `--text-secondary` |
| — | *spacer* | |
| Primary | `Mark 3 fulfillable` | `.btn.primary` |
| Secondary | `Hold these 3` | `.btn.secondary` |
| Menu | `More` + chevron | `.btn.ghost`, `aria-haspopup="menu"` |
| Separator | 1px, `--border-subtle`, 8px margin | |
| Danger | `Exclude from run` | `.btn.danger` (already the outline form: border and text in `--status-danger`, no fill) |
| Ghost | `Clear` | `.btn.ghost` |

The separator is the point of the arrangement: the destructive action is never
adjacent to a harmless one.

**The counts.** Orders is `state.selected.size`. Units is the sum of `o.Units`
over the selected orders — the same number `selection_helper.get_selection_summary`
computes on the Python side, and the same number the table's UNITS column shows.
Value is the sum of `o.Total_Price`, printed with `fmtMoney` (no currency
symbol — nothing else on this screen carries one), and omitted entirely when no
price column is mapped. Couriers is the distinct count of `courierOf(o)`,
written `2 couriers` / `1 courier`.

**Singular selection.** One order reads `1 order · 3 units selected`, and the
verbs lose their counts: `Mark fulfillable`, `Hold`. A button that says
"Mark 1 fulfillable" reads like a bug.

### 3.3 Export drops to secondary

W7's contract challenge — two primaries on Results — is rejected, so W7 as
drawn is the fallback: while the bar is up, its primary is the screen's one
primary and `#export` renders `.secondary`. `renderExport()` gains one line;
nothing else about Export changes.

### 3.4 Mount, unmount, and focus

The bar is shown by `render()` whenever `state.selected.size > 0`, hidden
otherwise, from the same pass that already recomputes the selection. A filter
that hides a selected order deselects it (`recompute()`, ADR 0005), so the bar
can never count a row the operator cannot see.

**Focus never moves on mount.** The operator may be mid-type in the search
field when a Shift-click lands. `Clear` returns focus to the table.

---

## 4. More

A `.menu` opened under the button, built the way `renderMenu()` and pane.js's
`openPaneMenu` already build menus. Items, in order of use, with the two
destructive ones below a separator:

1. `Add a tag to 3 orders`
2. `Remove a tag from 3 orders`
3. `Copy 3 order numbers` — right-aligned hint `Ctrl+C`
4. `Export just these 3 to Excel`
5. `Export just these 3 to CSV`
   — separator —
6. `Remove a SKU from these 3 orders`
7. `Remove whole orders containing a SKU`

Items 1, 2, 6 and 7 open a popover. Item 3 calls `bridge.copyText(...)` with the
order numbers joined by newlines and raises a toast. Items 4 and 5 call
`bridge.exportSelection(orderNumbers, "xlsx" | "csv")`, which reaches
`QFileDialog` on the Python side — a file dialog is a top-level window and
paints above the web view.

Two menu items instead of an Export submenu: a submenu is a second popup layer
for a choice between two words.

`Ctrl+C` with a selection and no open input copies the order numbers, whatever
has focus in the table.

---

## 5. The bulk popover (G4)

One frame, four fillings. `<div class="bulk-popover" role="dialog" aria-modal="false">`,
anchored under the control that opened it, 320px wide, closed by Escape, by a
click outside, and by acting.

**It has no shadow.** `box-shadow` is banned in web assets by
`shared/style_lint.py`; the popover separates from the table with
`--surface-overlay` and a 1px `--border` instead, exactly as the filter menu
does.

```
┌─────────────────────────────────────┐
│ Add a tag to 34 orders              │  header, 40px
├─────────────────────────────────────┤
│ Find a tag                          │  search, 32px — only above 10 rows
│ ┌─ HANDLING ───────────────────────┐│  group header, 22px, sticky
│ │ FRAGILE            on 6 of 34    ││  row, 30px
│ │ FRAGILE-GLASS                    ││
│ └──────────────────────────────────┘│  scroller, max 264px
│ ┌─ NEW ────────────────────────────┐│
│ │ [ New tag                      ] ││
│ └──────────────────────────────────┘│
├─────────────────────────────────────┤
│              Cancel  Add to 28 orders│  footer, 40px
└─────────────────────────────────────┘
```

The scroller is `overflow-y: auto` on a flex child with `min-height: 0` — the
same shape Bundle 13 needed for the column manager, and for the same reason.

### 5.1 Add a tag

- **List:** `bridge.tagCategories`, grouped, group label as the sticky header.
  This is the pane's `openTagMenu` list. Both callers now go through one
  builder (§ 7).
- **Row badge:** `on 6 of 34` when any selected order already carries the tag;
  nothing when none do. This is the mask `bulk_add_tag` already computes before
  it writes — it is only being shown. The canvas also draws the same number as a
  sentence under the title; one place is enough, and the row is the place where
  it answers a question you are actually asking.
- **New tag:** an input as the last group, `NEW`. Enter commits. The canvas
  offers `Create tag "FRAG" in Handling`; a category cannot be chosen here
  because `tag_categories` is client config the page cannot write, and the
  pane's own new-tag input is already uncategorised. Parity wins.
- **Footer verb:** `Add to 28 orders` — the selection minus the ones that
  already carry it. Disabled until a tag is chosen. When every selected order
  already carries the highlighted tag the verb reads `Already on all 34` and
  stays disabled.

### 5.2 Remove a tag

Same frame. The list is only the tags actually present on the selection, each
with `on 2 of 3`, ungrouped — a tag's category does not help you find a tag you
can see. No new-tag row. Footer verb `Remove from 2 orders`.

When the selection carries no tags at all the item is disabled in More, with the
reason in its `title`: `None of these 3 orders carry a tag`.

### 5.3 Remove a SKU from these orders · Remove whole orders containing a SKU

Same frame, `.danger` on the footer verb. The list is the distinct SKUs across
the selection's `lines`, each with `on 2 of 3 orders`, sorted by that count
descending then by SKU. The search row shows above 10 rows.

Footer verbs: `Remove from 2 orders` and `Remove 2 orders`.

These two are the destructive pair, so they keep the confirm — raised by the
Python handler with the existing `ConfirmDialog`, which is a `QDialog` and
therefore a top-level window that paints above the web view:

```
ConfirmDialog.ask(mw,
    title="Remove TS-4409-B from 2 orders?",
    body="2 of the 3 selected orders carry this SKU. Their other lines stay.",
    verb="Remove the line")
```

`Exclude from run` — `bulk_delete_orders` — is the third destructive verb and
also confirms, from the bar rather than a popover:

```
title="Exclude 3 orders from the run?"
body="They leave this session's results and its reports. Undo brings them back."
verb="Exclude 3 orders"
```

Cancel is the default button, so a reflexive Enter destroys nothing — that is
`ConfirmDialog`'s own contract, not a new rule.

---

## 6. The toast, in the document

`Toast` is a `QFrame` parented to the window. The Results tab is entirely a
`QWebEngineView`, whose native surface composites above sibling widgets, so a
Qt toast raised from this screen lands behind the page. Bundle 13 left that
unverified and deferred it here; the owner's answer is that every
Results-screen toast moves into the document. Nothing outside this screen
changes — the other ~40 `toast()` call sites keep the Qt route.

```html
<div id="toast" class="toast" role="status" aria-live="polite" hidden>
  <span id="toast-text"></span>
  <span id="toast-badge" class="badge" hidden></span>
  <button id="toast-undo" class="btn ghost" type="button" hidden>Undo</button>
</div>
```

It mirrors `gui/components/toast.py`'s contract exactly, because "two
implementations, one appearance" is what the 9.11 linter enforces:

| | value | source |
|---|---|---|
| Duration | 4000ms | `Toast.DURATION_MS` |
| Badge from | the 3rd in a run | `Toast.BADGE_AT` |
| Max width | 360px | `Toast.MAX_WIDTH` |
| Margin | 16px, bottom-right of `#results` | `Toast.MARGIN` |
| Fade | none | both |

The newest replaces the oldest and resets the timer; the badge counts the run.

**Undo.** Shown when the raising operation was undoable *and*
`bridge.undoAvailable` is true — so a toast whose operation has already been
undone from the rail does not offer to undo it again. The button calls
`bridge.undo()`, which is the same `undo_last_operation` the rail button calls.

Every write in this bundle raises exactly one toast, and its count matches the
count on the button that caused it:

| Act | Toast |
|---|---|
| Mark fulfillable | `3 orders marked fulfillable` |
| Hold | `3 orders held` |
| Add tag | `FRAGILE added to 28 orders` |
| Remove tag | `FRAGILE removed from 2 orders` |
| Exclude | `3 orders excluded from the run` |
| Remove SKU from orders | `TS-4409-B removed from 2 orders` |
| Remove orders with SKU | `2 orders containing TS-4409-B removed` |
| Copy | `3 order numbers copied` — no Undo |
| Export | `3 orders exported to selection_3_orders.xlsx` — no Undo |
| *(pane)* Exclude one order | `#10445 excluded from the run` |
| *(pane)* Remove one line | `TS-4409-B removed from #10445` |
| *(pane)* Hold / Mark fulfillable | *(none — the pane shows the change)* |

---

## 7. One tag picker, two callers

`pane.js:openTagMenu` already builds the grouped, category-labelled tag list
with a new-tag input. The popover needs the same list plus a per-row count and
a footer. Rather than a second list builder that has to be kept looking like the
first, `bulk.js` exports one:

```js
// rows: [{ id, label, tags: [{ tag, count }] }], count omitted for the pane
function tagRows(categories, exclude)      // grouping and filtering, no DOM
function renderTagList(host, rows, onPick) // DOM, no policy
```

The pane passes its order's own tags as `exclude` and no counts; the popover
passes nothing as `exclude` and counts from the selection. Two real callers, so
the seam is real rather than hypothetical. If a third ever wants it, it is
already the interface.

Deleting `renderTagList` would push the same twenty lines of grouped-list DOM
into two files — which is the test for whether it earns its keep.

---

## 8. The bridge

### 8.1 Catalogue delta

Bundle 11 § 5.2 names six members for Bundle 14. Three are built as written,
three are amended, and four are added. Recorded here per § 5.2's rule.

| Dir | Member | Status |
|---|---|---|
| in | `addTag(orderNumbers: list[str], tag: str)` | as written |
| in | `removeTag(orderNumbers: list[str], tag: str)` | as written |
| in | `excludeOrders(orderNumbers: list[str])` | as written |
| in | `undo()` | as written |
| out | `undoAvailable: bool` | as written, notify property |
| out | `toastRaised(message: str, undoable: bool)` | as written |
| in | `setStatus(orderNumbers: list[str], fulfillable: bool)` | **added** — the bar's primary and its inverse. The catalogue never named a bulk status verb; the pane's singular `holdOrder` / `fulfillOrder` do not take a list |
| in | `removeSkuFromOrders(orderNumbers: list[str], sku: str)` | **added** — restored by the owner this run |
| in | `removeOrdersWithSku(orderNumbers: list[str], sku: str)` | **added** — restored by the owner this run |
| in | `exportSelection(orderNumbers: list[str], fmt: str)` | **added** — More's two export items. `fmt` is `"xlsx"` or `"csv"`, validated Python-side; this is a format, not a verb, so it does not break § 5.1's rule against a string that selects behaviour |

Every in-slot carries `orderNumbers` even though `setSelection` has already
reported it. That is the catalogue's shape and it is the right one: the count
the page put on the button and the set the handler writes are then provably the
same list, and the handlers become functions of their arguments rather than
readers of ambient state.

`toastRaised` is the one signal JS *listens* to rather than calls — the
inverse direction of `focusSearchRequested`, which already exists, so the
protocol needs no new rule.

### 8.2 Python-facing signals

`bulkStatusRequested(list, bool)`, `bulkTagAddRequested(list, str)`,
`bulkTagRemovalRequested(list, str)`, `bulkExcludeRequested(list)`,
`bulkSkuRemovalRequested(list, str)`, `bulkOrderRemovalRequested(list, str)`,
`bulkExportRequested(list, str)`, `undoRequested()`. Named `bulk*` so nothing
collides with Bundle 13's singular pane signals.

---

## 9. Python: what dies and what changes

### 9.1 `gui/actions_handler.py`

Every bulk handler loses its dialogs and gains its arguments. The shape, for all
seven:

```python
def bulk_add_tag(self, order_numbers: list[str], tag: str) -> None:
```

Deleted from each: the `QMessageBox.warning` no-selection guard (the action is
disabled without a selection — the bar does not exist without one), the
`QInputDialog` chain, the `QMessageBox.question` confirm (except the three
destructive verbs, which move to `ConfirmDialog`), and the `QMessageBox.information`
success box (which becomes the toast).

Kept untouched in each: the `affected_rows_before` capture, the write, the
`undo_manager.record_operation` call with its existing `operation_type` and
`params`, `save_session_state()`, `_update_all_views()`, `log_activity`, and
`_update_undo_button()`. **The undo contract does not change in this bundle** —
`params` keys stay exactly as `undo_manager` reads them today.

`add_tag_manually` is deleted. `from PySide6.QtWidgets import QInputDialog`
goes with it, which is what makes the Done-when checkable by grep.

New, one small method: `_results_toast(text, undoable)` emits
`results_bridge.toastRaised`. The three pane verbs Bundle 13 wired
(`remove_entire_order`, `remove_line`, `set_order_fulfillable`) switch their
`toast(...)` calls to it.

### 9.2 `gui/ui_manager.py`

Eight `connect` lines beside Bundle 13's, through one helper that sets the
selection from the payload before calling the verb:

```python
def bulk(verb):
    def run(order_numbers, *args):
        self.mw.selection_helper.set_selected_orders(order_numbers)
        verb(*args)
    return run
```

`set_selected_orders` is idempotent and already ran from `selectionChanged`;
running it again costs one `isin` and removes any question about which set was
written.

### 9.3 `undoAvailable`

`actions_handler._update_undo_button` gains one line pushing
`can_undo()` into `results_bridge.set_undo_available(...)`. It is already the
single place that knows.

---

## 10. Keyboard and screen readers

- The bar is `role="toolbar"`, `aria-label="Actions for the selected orders"`.
  Its counting sentence is `aria-live="polite"` so the count is announced as it
  changes, and the sentence is the bar's accessible description.
- Tab order: the bar sits between the filter bar and the table, matching its
  visual position.
- `More` is `aria-haspopup="menu"` / `aria-expanded`; the popover is
  `role="dialog"` with `aria-label` set to its title. Opening either moves focus
  to the first row; Escape returns focus to the control that opened it.
- Inside a popover the arrows walk rows, Enter picks, and Enter on a picked row
  commits — the same gesture columns.js already uses.
- Escape closes the innermost thing: popover, then menu, then (as today) the
  selection.
- The toast is `role="status"` `aria-live="polite"`. It is not focusable; its
  Undo is reachable by Tab while it is up, which is the Qt toast's behaviour
  too.

---

## 11. Tests, and the seams they sit on

| Seam | File | What it pins |
|---|---|---|
| Page ↔ selection | `tests/test_results_selection_bar.py` | mount and unmount with the selection; the counting sentence for 1 / 3 / all; value and courier counts; Export demoted to secondary and back; the row budget dropping 17 → 15; focus not moving on mount |
| Page ↔ popover | `tests/test_results_bulk_popover.py` | grouped tag list from `tagCategories`; the `on 6 of 34` badge; the footer verb's count excluding those already tagged; `Already on all 34` disabled; remove-tag listing only present tags; SKU list and its counts; Escape and outside-click closing |
| Page ↔ toast | `tests/test_results_toast.py` | text, 4s dismissal, newest replacing oldest, badge from the third, Undo hidden when `undoAvailable` is false, Undo calling `bridge.undo()` |
| Bridge ↔ Python | `tests/test_results_bridge_bulk.py` | each slot emitting its signal with the right types; `undoAvailable` reaching the page |
| Python verbs | `tests/test_actions_handler_bulk.py` | each verb writing the frame from explicit arguments, recording undo with unchanged `params`, raising one toast, and opening no dialog |
| The Done-when | `tests/test_actions_handler_bulk.py` | `QInputDialog` appears nowhere in `gui/actions_handler.py`, and neither does `"Please select orders first"` |

The page-level tests drive a real `QWebEngineView` the way
`tests/test_results_pane.py` does. **Note from Bundle 13:** on this VM's Qt
build, `runJavaScript`'s callback marshals a JS `null` to Python `''`, never
`None` — assert `== ""`, and prove absence with
`document.querySelectorAll(...).length === 0`.

---

## 12. Departures from the brief and the canvas

| Brief / canvas | This design | Why |
|---|---|---|
| `Assign courier` in slot 2 | `Hold these 3` | Courier assignment does not exist; Hold is the pane's word for the inverse of the primary (owner) |
| `Mark 3 ready to ship` | `Mark 3 fulfillable` | The pane already ships `Mark fulfillable`; one screen, one verb |
| `Add a note to 3 orders` in More | Dropped, and `add_tag_manually` deleted | No bulk note writer exists (owner) |
| `Re-allocate these 3 oldest-first`, `Reset manual overrides` | Dropped | No backing code, same ruling as Bundle 13 § 11 |
| `3 orders · 11 items selected` | `3 orders · 11 units selected` | UNITS is a column on this table and `Items` is the line count; "items" names nothing on screen |
| G4: `34 orders selected / 108 lines` | Units, not lines | Consistency with the bar above it, which the popover opens from |
| G4's header sentence `6 already carry FRAGILE…` | The per-row `on 6 of 34` badge only | Same number twice; the row is where the question is asked |
| G4: `Create tag "FRAG" in Handling` | An uncategorised `New tag` input | `tag_categories` is client config the page cannot write, and the pane's new-tag input is already uncategorised |
| `Export just these 3` | Two items, Excel and CSV | A submenu is a second popup layer for a choice between two words |
| W7's two-primaries challenge | Rejected; the drawn fallback | Already decided in the phase spec, `2026-09-03-phase9-fulfilment-v2-design.md` § "What the canvas got wrong" |
| `€612.10` | `612.10` | Nothing else on this screen carries a currency symbol; none is configured |

---

## 13. Not in this bundle

- Bulk courier assignment, bulk notes, re-allocate, reset overrides — no
  backing code in any of the four cases.
- Selecting across a filter change, or a selection that survives a re-run.
- A Qt twin of the bulk popover. The Session Browser's bar (D2) keeps the
  actions it has.
- Changing anything `undo_manager` stores. The `params` shapes are frozen here
  on purpose; a change would invalidate the histories already on disk.
- The remaining ~40 Qt `toast()` call sites outside the Results screen.
- `bulk_export_selection`'s file dialog, which stays Qt — it is the one place
  in this bundle where a native window is the right answer.

---

## 14. Build

One new web file, `gui/web/bulk.js`, loaded after `pane.js` and before
`results.js`. The existing `--add-data "gui/web;gui/web"` already collects it.
New CSS goes in `results.css`. No new dependency, in either tier.

**Load order, twice burned in Bundle 13:** `bulk.js` runs before `results.js`
defines `el`, `svg`, `num`, `str`, `fmtMoney`, `NUMBER` and `courierOf`.
Reference them only inside function bodies — not merely calling them, but
naming them at all at top level, including inside an object literal that is
evaluated at load.

**Also from Bundle 13:** a `QVariantMap` reaching JS has alphabetically sorted
keys, so `JSON.stringify(fromBridge) === JSON.stringify(localLiteral)` is false
even when the values match. Compare positionally.
