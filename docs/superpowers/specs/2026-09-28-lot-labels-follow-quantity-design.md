# Lot labels follow Quantity; Change quantity verb

Incident: REVE session `2026-09-28_1`, order #1221. After the order was edited
down, the stock export listed `01PJ0001L` at **3** and dropped `01PJ0001S`
entirely. The saved frame was right (L×1, S×1). Todoist 6hfMjfhmW4MJcmpv.

Classification: architectural (small). One derived-data rule is added to the
stock ledger and both report writers are moved onto it; one new edit verb.

## 1. Owner decisions (settled; do not re-ask)

| # | Question | Answer |
|---|---|---|
| D1 | Units with no lot allocation from the run (line added by hand, quantity raised, order marked fulfillable after the run) | **Lot left blank.** Годност/Партида empty for those units; the quantity is exact. (2026-09-28) |
| D2 | How to change a SKU's quantity inside an order | **Line ⋯ menu → number entry.** "Change quantity…" opens a small number field; whole number ≥ 1; undoable; blocks the order if it outruns Stock left, same rule as Add product. (2026-09-28) |
| D3 | Design above | Approved. (2026-09-28) |

D2 note: `tests/test_actions_handler_bulk.py::test_no_input_dialog_survives_in_actions_handler`
forbids `QInputDialog` in `gui/actions_handler.py` (Bundle 14). The number
entry is therefore the page's own: a pane menu holding an `<input type=number>`,
the same shape as the tag menu's "New tag" input. That is D2's behaviour in the
repo's idiom, not a different choice.

## 2. Root cause (reproduced)

Replaying `stock_export.create_stock_export` on the session's saved
`analysis/current_state.pkl` writes exactly the incident file.

Operation history for #1221 (`analysis/operations_history.json`,
`manual_additions.json`):

1. remove 01PJ0002M; remove 01PJ0001M
2. Add product 01PJ0001L ×1; Add product 01PJ0001S ×1
3. remove the original 01PJ0001S ×4 line; remove the original 01PJ0001L ×3 line

Defect A — **Add product inherits a lot allocation.**
`ActionsHandler._add_product_to_order` builds the new line as
`existing_rows.iloc[0].copy()`. At step 2 that first row was the original
01PJ0001L ×3 line, so both manual lines carried its `Lot_Details`
(`[{"expiry": "1", "batch": None, "qty_allocated": 3}]`), and, because a
Series copy is shallow for object cells, the *same list object*.

Defect B — **writers trust `Lot_Details` over `Quantity`.**
`stock_export._expand_lot_summary` reads `qty_allocated` and ignores
`Quantity`, and dedupes allocations by `id(list)`. So the L line exported 3,
and the S line (same object) was skipped as a duplicate.
`packing_lists._expand_lot_rows` has the same flaw (replaces `Quantity` with
`qty_allocated`; dedupes by `(Order_Number, SKU)`): the packing list would have
printed L×3 and S×3.

Why it is a class, not a one-off: `Lot_Details` is written once by the run
(`analysis.py`, `final_df["Lot_Details"] = ...`). ADR 0010 made Stock left a
function of the frame after every edit, but nothing ties lot allocations to
`Quantity`. Any edit that changes a line's quantity or copies a row makes them
disagree, and the writers believed the lots.

Not affected: Packing Tool. The packing-list JSON (`core.build_packing_order_data`)
uses `Quantity`, and `packing-tool` never reads lots.

Lots are real for some clients: ALMADERM and WATERDROP stock files carry real
Годност/Партида values; REVE uses the `"1"` sentinel (no lots).

## 3. Rule R3 — lot labels follow Quantity

Lives in `shopify_tool/stock_ledger.py` beside R1/R2, and is the only reader of
`Lot_Details` for output. Record as ADR 0014.

> **R3** `Quantity` is the truth. `Lot_Details` only labels it. For each
> *pair* — one order's lines of one SKU — the pair's quantity is the sum of
> its lines' `Quantity`. The pair's lots are the first non-empty
> `Lot_Details` list among its lines. Walk those lots in list order (the run
> wrote them FIFO), taking `min(qty_allocated, still needed)` from each; any
> quantity still needed after the last lot is one unlabelled part
> (blank expiry and batch). A pair whose quantity is ≤ 0 yields nothing.

Details:

- **Pair key.** `(order key, SKU)`. Order key = `Order_Number` stripped
  string. A blank or null order number does **not** pair across rows: each such
  row is its own pair (keeps
  `tests/test_stock_export.py::TestConfirmedBugs::test_missing_order_number_does_not_drop_distinct_lot_allocations`).
- **Object identity no longer matters.** The first non-empty list is used by
  value, so a shared object, an undo/JSON round-trip copy, or a pickle reload
  all give the same answer. This replaces both `id()` and
  `(Order_Number, SKU)` dedupe.
- **Sentinels.** `expiry == "1"` → `""`; `batch == "1"` → `""`; `None` → `""`
  (unchanged behaviour).
- **Only list cells are lots.** A cell that is `None`, NaN, an empty list or a
  non-list (e.g. a string from an old xlsx round-trip) counts as "no lots".
- **Output of the helper** — `stock_ledger.lot_parts(rows) -> list[tuple[label, float, str, str]]`,
  each tuple `(row label, qty, expiry, batch)`, in the order the pairs' first
  rows appear in `rows` (callers pass rows already sorted):
  - a pair **with** lots → one tuple per lot part, all carrying the pair's
    first row label, lots in list order, the unlabelled remainder last;
  - a pair **without** lots → one tuple per row of the pair
    `(that row's label, that row's Quantity, "", "")`, rows with Quantity ≤ 0
    skipped. Two unlotted lines of one SKU stay two lines (CONTEXT.md "Order
    line": never collapse two lines).

  The row label lets the packing list copy that row's other columns.

Why this is safe for lot totals: the run's allocations for different orders
are disjoint FIFO takes from the stock file, so labels can only shrink (clip)
or be absent under R3. A lot can never be named for more units than the run
allocated from it.

## 4. Changes

### 4.1 `shopify_tool/stock_ledger.py`
Add R3 to the module docstring and `lot_parts(rows)` as specified in §3.

### 4.2 `shopify_tool/stock_export.py`
- `_expand_lot_summary(filtered_items)` aggregates `lot_parts(filtered_items)`
  by `(SKU, expiry, batch)`; unlabelled parts aggregate under `(SKU, "", "")`.
  Remove the `id()` dedupe and its comment. SKU for a part is
  `filtered_items.at[label, "SKU"]`.
- **Totals guard.** New `_check_totals(filtered_items, export_df)` called in
  `create_stock_export` on the product export frame, after it is built and
  finalized and **before** packaging rows are merged and before anything is
  written. Expected per SKU = `_to_erp_quantity(filtered_items.groupby("SKU")["Quantity"].sum())`
  keeping only values > 0; actual per SKU = the export frame's `Брой` summed by
  `Артикул`. Any difference (a SKU missing, extra, or a different number)
  raises `ValueError` naming each SKU as `SKU export N, lines M`. The caller
  already turns an exception into "1 report wasn't generated … Details are in
  Logs." and nothing is written. SKU keys compare as stripped strings.
  Known ceiling: fractional quantities split across several lots can round
  differently per part than in total; product quantities from Shopify are
  whole, so this is acceptable (write a `ponytail:` comment naming it).

### 4.3 `shopify_tool/packing_lists.py`
`_expand_lot_rows(df)` emits one output row per `lot_parts(df)` tuple: a copy
of `df.loc[label]` with `Quantity` = the tuple's qty, `Lot_Expiry` = expiry,
`Lot_Batch` = batch. By §3 a pair with lots collapses to its lot parts (as
today) and unlotted lines stay one row each with unchanged `Quantity` and blank
lot columns (as today). Remove the `(Order_Number, SKU)` dedupe and its comment.
Keep the empty-input branch (returns `df` with blank lot columns).

### 4.4 `gui/actions_handler.py` — Add product
In `_add_product_to_order`, after `new_row = template_row.copy()`, set
`new_row["Lot_Details"] = None` when the column exists. One line plus a comment
naming this incident.

### 4.5 Change quantity verb

**Page (`gui/web/pane.js`, `gui/web/results.css`).** The line ⋯ menu gains
`"Change quantity…"` between "Remove this line" and "Copy SKU". Choosing it
opens a pane menu `id="qty-menu"` anchored on the same ⋯ button, holding one
`<input type="number" min="1" step="1" id="line-qty" class="new-tag">` with
`aria-label="Quantity"` and value = the line's current `Quantity`. Enter with a
whole number ≥ 1 that differs from the current value closes the menu and calls
`state.bridge.changeLineQuantity(order, index, sku, n)`. Enter with anything
else (empty, 0, negative, fractional, unchanged) closes the menu and sends
nothing. Esc/outside click close it as every pane menu does.
Reusing the `new-tag` class gives the input the existing pane-menu input style;
no CSS change needed.

**Bridge (`gui/results_bridge.py`).** New signal
`lineQuantityChangeRequested = Signal(str, int, str, int)` and slot
`@Slot(str, int, str, int) changeLineQuantity(order_number, line_index, sku, quantity)`
that emits it with `str/int/str/int` coercion, like `removeLine`.

**Wiring (`gui/ui_manager.py`).** Next to `lineRemovalRequested`:
`bridge.lineQuantityChangeRequested.connect(lambda n, i, s, q: actions().change_line_quantity(n, i, s, q))`.

**Handler (`gui/actions_handler.py`).**
`change_line_quantity(self, order_number, line_index: int, sku, quantity: int)`:

1. Frame empty/None → return. `quantity` not an int ≥ 1 → log warning, return.
2. Resolve the line exactly as `remove_line` does (order mask → `line_index`-th
   label → its SKU must still equal `sku`; else log "Aborted quantity change: …"
   and return).
3. Current quantity equal to `quantity` → return (no undo record, no toast).
4. `affected = df[order_mask].copy()` (the whole order: its status may change).
5. `was = stock_ledger.is_fulfillable(df, order_number)`. Copy the frame, set
   `Quantity` at the label. If `was` and `stock_ledger.shortfall(frame, order_number)`
   is non-empty, set every row of the order to `NOT_FULFILLABLE`. A blocked or
   held order stays as it is; a lower quantity never unblocks anything (same as
   Add product, Bundle 1 D6).
6. `self.mw.analysis_results_df = stock_ledger.with_stock_left(frame)`.
7. `undo_manager.record_operation("change_quantity", description,
   {"order_number": order_number, "sku": sku, "quantity_before": old, "quantity_after": quantity}, affected)`.
   Description: `Changed {sku} in order {order} from {old} to {new}`.
8. `data_changed.emit()`, `save_session_state()`, `_update_undo_button()`,
   `log_activity("Data Edit", description + ".")`, and
   `_results_toast(text, undoable=True)` where text is
   `Changed {sku} in order {order} to {new}.` plus
   ` It is now blocked: not enough {skus}.` when step 5 blocked it.
   Quantities print as whole numbers (`int(old)` when integral).

`Lot_Details` is not touched: R3 fits the run's allocation to the new quantity
when a report is written.

**Undo (`shopify_tool/undo_manager.py`).** Generalise
`_restore_statuses_by_position(rows)` into
`_restore_columns_by_position(rows, columns)` (same position/order-number
checks; `_restore_statuses_by_position` becomes a one-line call with
`["Order_Fulfillment_Status"]`). New `_undo_change_quantity` restores
`["Quantity", "Order_Fulfillment_Status"]` by position and returns False (undo
fails, frame untouched) when positions don't hold. Dispatch it from `undo()`
for `"change_quantity"`. `undo()` already re-derives Stock left afterwards.

### 4.6 Docs
- `docs/adr/0014-lot-labels-follow-quantity.md` (Context / Decision /
  Consequences, like ADR 0010).
- `CONTEXT.md`: add **Lot label** under the Stock left entry: "The expiry and
  batch a report names for some of a line's units. It comes from the run's FIFO
  allocation, fitted to the line's current quantity (ADR 0014). Units the run
  never allocated — added by hand, raised later, or in an order marked
  fulfillable after the run — have no lot label."

## 5. Testing (seams)

All pure-Python seams except the page test. Test fixtures live beside the
existing ones they mirror.

1. `stock_ledger.lot_parts` unit tests (append to `tests/test_stock_ledger.py`): clip on reduction; unlabelled remainder on increase;
   two lines of one pair sharing one object → counted once; the same pair with
   two *equal but distinct* list objects → counted once; blank order numbers
   → separate pairs; `"1"` sentinels → blank; NaN/str/empty cells → no lots;
   zero-quantity pair → nothing.
2. **Incident regression** (`tests/test_lot_integrity.py`): build a
   lot-tracked run with `run_analysis` (stock with Годност/Партида, as in
   `tests/audit/test_01_intake_analysis.py::stock(lots=True)`) for #1221
   (L×3, M×4, S×4, 2M×1) plus one other order; drive the real
   `ActionsHandler` over the audit `window()` stand-in through the exact §2
   sequence (`remove_line`, `_add_product_to_order`); then
   `create_stock_export` totals == `{L: 1, S: 1, <other>}` and
   `create_packing_list` lines == `{(#1221, L): 1, (#1221, S): 1, …}`. Also
   assert the manual rows' `Lot_Details` is None.
3. Same-SKU add: order with L×3 (lot X) + Add product L×1 → export L = 4 as
   one row with lot X qty 3 and one blank-lot row qty 1.
4. Totals guard: monkeypatch `_expand_lot_summary` to return a wrong frame →
   `create_stock_export` raises `ValueError` and the output file does not
   exist.
5. Existing tests stay green, in particular
   `tests/test_stock_export.py::TestLotAggregation`,
   `TestConfirmedBugs`, `tests/audit/test_04_outputs.py` lot tests,
   `tests/test_packing_lists.py` lot tests.
6. Change quantity handler (`tests/test_actions_handler_bulk.py`, using
   `_ledger_window` + `run_analysis`): lower → Stock left rises, status kept,
   undo restores quantity and Stock left; raise within stock → stays
   fulfillable; raise beyond Stock left → order blocked, toast says so, undo
   restores status; unchanged value → no undo record; stale `sku` at the index
   → no change; quantity 0 → no change. Then a stock export after a lower
   quantity on a lot-tracked order gives the new quantity.
7. Bridge: add `("changeLineQuantity", ("#1", 2, "SKU-A", 5), "lineQuantityChangeRequested")`
   to the parametrised list in `tests/test_results_bridge.py`.
8. Page (`tests/test_results_pane.py`): open line 1's ⋯ menu on `#10445`,
   choose "Change quantity…", the `#line-qty` input shows the line's quantity;
   set value 7 and dispatch Enter → `lineQuantityChangeRequested` args
   `["#10445", 1, "TS-9002-C", 7]`. Enter with the unchanged value emits
   nothing (use `qtbot.assertNotEmitted`).

Done when: the full suite passes (`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`),
lint passes, and replaying the incident session's `current_state.pkl` through
`create_stock_export` gives L=1, S=1 (manual check; production data is not
committed).

## 6. Out of scope

- Allocating real lots for unallocated units (D1 chose blank).
- Packing Tool (reads `Quantity` only).
- Other inherited template fields on Add product (`Order_Type`, `Stock_Alert`):
  not quantity- or stock-bearing; not touched.
- `merge_session_stock_exports` already sums `Quantity` per SKU without lots.
