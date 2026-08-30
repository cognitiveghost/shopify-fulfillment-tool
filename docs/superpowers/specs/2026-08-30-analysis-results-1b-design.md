# Analysis Results 1b — Order & detail

**Date:** 2026-08-30
**Roadmap item:** Phase 8.8 (Todoist `6hMhXghP4xpM3g73`)
**Design contract this refines:** `2026-08-26-phase8-unified-design-system.md` §6
**Direction:** **1b — Order & detail**, chosen by the user on 2026-08-27. 1a and 1c are dead.

---

## 1. The problem, restated in this repo's terms

Depot's fault #3: *"the results table is one row per SKU line, but staff decide per order.
1 842 rows to make 312 decisions."*

Reading the code confirms the diagnosis and adds a sharper one: **the app already knows the
unit is the order, and pays to fake it at every layer.**

| where | what it does | why |
|---|---|---|
| `gui/order_group_delegate.py` | paints a rule under the last line of each order | to make groups legible in a list that has none |
| `SelectionHelper.toggle_row` | ticking one line ticks every line of that order | because a decision is per order |
| `SelectionHelper.select_all` | expands visible lines to their whole orders | so a filter cannot half-apply a bulk action |
| `on_selection_changed_for_tags` | re-merges `Internal_Tags` across the order's lines | tags are order-level, stored per line |
| `show_context_menu` | every action but one takes `order_number` | the line is not the subject |
| bulk mode + checkbox column | a second, parallel selection model | native row selection selects lines, which is the wrong thing |

So 1b is not a new feature bolted on. **It deletes a workaround.** The checkbox column,
`CheckboxDelegate`, the bulk-mode toggle and `OrderGroupDelegate` all exist only because the
row is not the order. When the row becomes the order, they have nothing left to do.

`analysis.py:1062` already writes the blocking reason (`"Cannot fulfill: {reason}"`) into
`System_note` for **every line of the order** — it is keyed by `Order_Number`. The blocker
the mockup wants on the row is already computed; nothing needs re-deriving.

---

## 2. Scope

**In:** the Analysis Results screen — its table, its selection model, its detail pane, its
filter row, its action affordances.

**Out:** the analysis backend. `shopify_tool/analysis.py` is not touched, and
`analysis_results_df` keeps its exact shape.

That boundary is the single most important decision here — see §3.

---

## 3. Architecture: derive, never duplicate

`analysis_results_df` (one row per order/SKU line) is the app's spine. Reports, packing
lists, stock exports, the undo manager, session persistence and `analysis_data.json` all
read it. Two candidate designs:

**(a) Derive an order-level view in the GUI.** `analysis_results_df` stays the one source of
truth; a pure function folds it to 312 rows for display; every write still lands on the line
frame.

**(b) Have `analysis.py` emit an orders frame.** A second persisted artifact, a second thing
that can go stale, a migration for every saved session, and a change to the file the Packing
Tool reads.

**(a).** Not close. The view is a projection, and a projection belongs where it is consumed.
Everything downstream of the table keeps working *because* nothing downstream changes.

### The seam that makes it cheap

`SelectionHelper.checked_rows` is a set of **source line indexes**, and all seven bulk
actions plus `get_selected_orders_data()` read only that. Populate the same set from an
order-level selection and every consumer is untouched:

```
table selection (order rows)  ->  order numbers  ->  line indexes  ->  checked_rows
```

`toggle_row`'s expansion logic already does the second arrow; it moves up one level and
stops being a workaround.

---

## 4. The order frame

A new module `gui/orders_view.py`, no Qt imports, one job:

```python
def orders_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Fold the line frame to one row per Order_Number, preserving row order."""
```

### Which columns survive as columns

Columns are **order-level** (constant by construction across an order's lines) or
**line-level**. Order-level columns become columns of the order frame; line-level ones move
into the detail pane.

Declared order-level, from `analysis.py:1119`'s `output_columns`:

`Order_Number`, `Order_Type`, `Order_Fulfillment_Status`, `Shipping_Provider`,
`Destination_Country`, `Shipping_Method`, `Tags`, `Notes`, `Status_Note`, `Internal_Tags`,
`Total_Price`, `Subtotal`

Declared line-level: `SKU`, `Has_SKU`, `Product_Name`, `Warehouse_Name`, `Quantity`,
`Stock`, `Final_Stock`, `Source`, `Stock_Alert`, `System_note`, `Lot_Details`

**Client-defined additional columns** (`additional_columns_config`) are not in either list —
their level is unknowable ahead of time. For those only, decide from the data: a column
whose value is constant within every multi-line order is order-level, otherwise line-level.

> The data check is deliberately **not** used for the declared columns. In a session where
> every order happens to have one line, every column tests as constant — `SKU` included —
> and the table would silently grow a column that means nothing at the order level.

### Derived columns

Three columns exist only on the order frame:

| column | value |
|---|---|
| `Items` | number of lines in the order |
| `Blocker` | the `Cannot fulfill: …` reason lifted out of `System_note`, else `""` |
| `_search_text` | every line's display text, joined — hidden from the view, see §6 |

`Items` answers "is this a one-liner or a 12-line order" without opening the pane, which is
the whole reason the 1 842-row list was tolerable.

`Blocker` is **extracted, not computed** — split `System_note` on `"Cannot fulfill: "` and
take the tail. Per roadmap §3 rule 3's spirit, the analysis owns the reason; the view only
reads it.

### Column configuration keeps working

`TableConfigManager` persists a per-client visible-column list against the *line* frame's
names. It is not migrated and not versioned-up. The order table applies that saved list
intersected with the order-level columns; the detail pane's line table applies it
intersected with the line-level ones. A client's saved configuration therefore keeps its
meaning, split across the two surfaces, with no profile migration.

---

## 5. The detail pane

A new `gui/order_detail_pane.py`, docked right of the table, showing the **current** row
(not the multi-selection):

1. **Header** — order number in `display_xl`, status as a StatusChip, courier / country /
   method as caption text.
2. **Blocker banner** — present only when `Blocker` is non-empty, `status_danger` role.
3. **Lines table** — the order's line-level columns. This is where `Lot_Details` tooltips,
   `Stock`/`Final_Stock` and per-SKU actions live.
4. **Tags** — `TagManagementPanel` moves in here whole.
5. **Notes** — `Notes` and `System_note`, read-only.

### The Tags Manager panel is absorbed, not rebuilt

`TagManagementPanel` is already a 300 px right-hand panel keyed to one selected order and
already fed by `on_selection_changed_for_tags`. It becomes the pane's tag section unchanged.
The `Tags Manager` toggle button and `toggle_tag_panel()` are deleted: the panel stops being
something you reveal and becomes part of the screen.

### SKU-level actions move to the lines table

`remove_item_from_order` is the only genuinely per-line action on the table's context menu,
and it needs a row snapshot to detect a stale click. In the pane it is a right-click on the
line it acts on, which is both correcter and simpler — the snapshot guard stays, but it
guards a click on the thing itself.

`bulk_remove_sku_from_orders` and `bulk_remove_orders_with_sku` are cross-order operations
that take a SKU; they stay with the selection actions, not the pane.

---

## 6. Filtering must still find a SKU

Typing a SKU into the filter has to return the orders containing it, or the order table is a
downgrade. `FulfillmentFilterProxy` searches source-frame columns by index, so the order
frame carries `_search_text` — each order's lines' display text, joined — which the
"All Columns" search reaches for free. The view hides that column; the column selector lists
order-level columns only.

Tag filtering is unchanged: `Internal_Tags` is order-level and survives as a column.

---

## 7. What gets deleted

| file / symbol | why |
|---|---|
| `gui/checkbox_delegate.py` | native row selection is now order selection |
| `PandasModel.enable_checkboxes` and its column offset | ditto — removes an offset threaded through `data`, `headerData`, `get_column_index` |
| `gui/order_group_delegate.py` | one row per order; there are no groups to rule off |
| `toggle_bulk_mode()`, `toggle_bulk_mode_btn` | there is no second mode |
| `toggle_tag_panel()`, `toggle_tags_panel_btn` | the pane is always there |
| `tests/test_checkbox_delegate.py` | tests a deleted file |

`SelectionHelper` keeps its public API and loses `toggle_row` / `is_row_checked`.

---

## 8. Presentation (second cycle)

Deliberately **not** in the same commits as §3–§7, per spec §6's navigation guardrail:
structure lands separately from restyle so it can be reverted alone.

- KPI strip above the table — orders, fulfillable, blocked, items — from the existing
  `StatCard`, replacing the one-line `summary_label`.
- Status as a **left edge** on the row, not a filled background. `PandasModel`'s
  `BackgroundRole` / `ForegroundRole` row tint goes; a delegate paints a 3 px status edge.
  Selection stays the 2px `selection_border` ring shipped in 8.7.
- `ContextualSelectionBar` (`gui/components/selectionbar.py`, built in 8.5 and still unused
  on this screen) replaces `BulkOperationsToolbar` and the eleven-button action row.
  Its own docstring says this replacement was meant for 8.7 and it did not happen here.
- `FilterBar` replaces the hand-rolled filter row.
- Screen-level buttons that are not per-selection (Settings, Configure Columns, Generate
  Reports, Undo) go to the command bar or the row's overflow — one primary action per
  screen, reviewed at Stage C.

---

## 9. Two cycles

Sized so each is one A→B→C pass, and split on the guardrail line.

**8.8a — the unit.** §3–§7. The table shows 312 rows, the pane shows the order, selection
and every bulk action keep working, the workaround code is deleted. Visually it is still the
old screen: `BulkOperationsToolbar` and the eleven-button row stay, now driven by native
selection instead of checkboxes.

**8.8b — the chrome.** §8.

Shipping 8.8a alone is coherent: it is strictly the unit fix. Shipping 8.8b without 8.8a is
not, so the order is fixed.

---

## 10. Testing

New, in `tests/test_orders_view.py` (pure, no Qt):

1. A 3-order / 7-line frame folds to 3 rows in first-appearance order.
2. `Items` counts lines per order.
3. `Blocker` extracts the reason from `System_note` and is `""` for a fulfillable order,
   including the `"Repeat…; Cannot fulfill: …"` compound form `analysis.py:1071` writes.
4. `_search_text` contains a line's SKU that appears in no order-level column.
5. An unknown additional column constant within every multi-line order classifies as
   order-level; one that varies classifies as line-level.
6. In a frame where every order has exactly one line, `SKU` still classifies as line-level —
   the declared list wins over the data check.

Extended, in `tests/test_selection_helper.py`:

7. Selecting one order row puts every line index of that order in `checked_rows`, so
   `get_selected_orders_data()` returns the full order.
8. `get_selection_summary()` is unchanged for the same selection expressed the new way.

Widget-level, in a new `tests/test_analysis_results_1b.py` (offscreen):

9. Loading a frame into `update_results_table` gives the view `orders_frame` row count.
10. Filtering by a SKU string leaves the containing order visible.
11. Selecting a row populates the detail pane header and its line table with that order's
    lines.

Gate for both cycles: `QT_QPA_PLATFORM=offscreen python -m pytest` and
`ruff check . --exclude shared`.

---

## 11. Risks

**Warehouse retraining.** The screen staff use every day changes unit. Mitigated by the
guardrail split (§9) — 8.8a is revertable without dragging a restyle with it — and by the old
labels surviving verbatim.

**A client's saved column configuration appears to lose columns.** It does not; the
line-level ones are in the pane. This belongs in the PR body and in the release note, not in
a migration.

**`Blocker` extraction is string-matching on `System_note`.** It is the same string
`analysis.py` writes, and test 3 pins both forms. If the analysis ever emits the reason as a
column, `Blocker` should read it instead — noted, not pre-built.

---

## 12. Light theme

Per the Todoist brief: **dark is designed, light is derived.** Build to the mockup in dark,
let light fall out of the tokens, and say exactly that in the PR. Contrast is safe in both —
every token is validated — but light is an implementer's reading until it gets its own
design pass.
