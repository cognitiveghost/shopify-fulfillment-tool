# Phase 14 Bundle 1 — stock ledger and order status

Fixes AUDIT-01-1, -2, -3, -4, -5, -6, -7, -8, -9, -10, -11 and AUDIT-04-6
(reports: `docs/audit/01-intake-analysis.md`, `docs/audit/04-outputs.md`).
AUDIT-01-12 belongs to Bundle 2 and is not touched here.

Classification: architectural. One new module replaces per-verb stock
bookkeeping, and a single order-status rule replaces first-row reads.
No UI design: the only visible changes are toast copy and the numbers
becoming correct.

## 1. Owner decisions (settled; do not re-ask)

| # | Question | Answer |
|---|---|---|
| D1 | AUDIT-01-3: bulk Mark fulfillable | Mark only the orders Stock left covers, drawing on it as the single-order path does. Skip the rest and give the skipped count in the toast. (2026-09-25) |
| D2 | AUDIT-01-8: duplicate stock rows without lot columns | Sum them, as the lot path does. (2026-09-25) |
| D3 | An order whose SKU lines disagree | **Blocked.** An order is fulfillable only when every SKU line is Fulfillable. This replaces the bundle text's "any SKU line", so the screen, the KPIs and the outputs agree. (this run) |
| D4 | Saved sessions whose Stock left is already wrong | **Re-derive on open.** (this run) |
| D5 | AUDIT-01-9: lines above the first order number | Keep them as **one blocked order named `(no order number)`**, with the reason "No order number". (this run) |
| D6 | Add product on a held or blocked order | **The order stays held.** The new line draws nothing. Only Mark fulfillable releases a hold. (this run) |

## 2. The two rules everything else follows

**R1 — Fulfillable order.** A line is a *SKU line* when `Has_SKU` is true.
For a frame without `Has_SKU`, it is a SKU line when `SKU` is not null and
not `"NO_SKU"`. An order is fulfillable when **every one of its SKU lines**
has `Order_Fulfillment_Status == "Fulfillable"`. An order with no SKU lines
is fulfillable when every one of its lines is Fulfillable. Line statuses stay
stored per line. Nothing reads an order's status off one row any more.

**R2 — Stock left.** For every SKU,
`Stock left = opening Stock − Σ Quantity over the SKU lines of fulfillable orders`.

- Opening Stock is the frame's `Stock` value for that SKU: the first non-null
  one in frame order.
- A SKU is **unlisted** when every row carrying it has `Final_Stock` null.
  The run leaves `Final_Stock` null for SKUs missing from the stock file.
  An unlisted SKU is left out of the ledger. Its `Final_Stock` stays null,
  and every check treats it as covered. That is today's documented behaviour
  ("unlisted item, we assume it's on hand"), kept as it is.
- `NaN` quantities count as 0.

On a fresh run R2 reproduces the run's `Final_Stock` exactly, on both the lot
path and the plain path. So Stock left is **derived after every edit, never
adjusted**. There is no per-verb arithmetic to get wrong, and the undo stack
needs to restore only rows and statuses. See ADR 0010.

## 3. Module: `shopify_tool/stock_ledger.py` (new)

A deep module: five functions, and the only place R1 and R2 are written down.
It depends on pandas alone, so `analysis`, `report_filters`, `undo_manager`,
`core` and the GUI can all import it without a cycle.

```python
FULFILLABLE = "Fulfillable"
NOT_FULFILLABLE = "Not Fulfillable"

def fulfillable_orders(df) -> set[str]
    """R1. Order numbers (str, stripped) of the fulfillable orders."""

def is_fulfillable(df, order_number) -> bool
    """R1 for one order. False for an order not in df."""

def stock_left(df, excluding=None) -> dict[str, float]
    """R2 per listed SKU. `excluding`: an order number whose own draw is
    ignored, as if that order were blocked."""

def shortfall(df, order_number) -> list[str]
    """SKUs of the order's SKU lines that Stock left (with this order's own
    draw released) cannot cover, in first-seen order. [] = covered.
    Quantities of one SKU across several lines are summed first."""

def with_stock_left(df) -> pd.DataFrame
    """Rewrites Final_Stock on every row of a listed SKU from stock_left(df).
    Returns df unchanged when Stock, Final_Stock or SKU is missing."""
```

Order numbers are matched with `str(x).strip()`, the rule
`gui/selection_helper.order_number_mask` documents. The module inlines that
rule, because `shopify_tool` must not import `gui`.

A frame without a `Stock` or `Final_Stock` column has no ledger. There,
`shortfall` returns `[]` and `with_stock_left` changes nothing. Existing GUI
tests build frames like that, and this keeps them green.

## 4. What changes, per finding

### AUDIT-01-5 and every reader of order status (R1)

These read the first row today and switch to `stock_ledger`:

| reader | change |
|---|---|
| `analysis.toggle_order_fulfillment` | `is_fulfillable` decides Hold or Mark (§4.2) |
| `ActionsHandler.set_order_fulfillable` | `is_fulfillable` for its no-op check |
| `orders_view.order_payload` (verdict) | status passed to `order_verdict` = `FULFILLABLE if key in fulfillable_orders(df) else NOT_FULFILLABLE` |
| `orders_view.orders_frame` | the folded row's `Order_Fulfillment_Status` column is overwritten with the same R1 value, so the table and search agree with the pane |
| `orders_view` KPI strip (`:398`, `ready_mask`) | `fulfillable_orders` replaces "any line is Fulfillable" |
| `core.build_packing_order_data` (`:116`) | `status` = R1 for the group |
| `add_product_dialog` (`:205`) | the displayed status = R1 |

### 4.2 Hold / Mark fulfillable, one order (AUDIT-01-5, -2)

`toggle_order_fulfillment(df, order_number)` keeps its signature and its
`(ok, error, df)` return:

1. The order is not found: `(False, "Order number not found.", df)`, as today.
2. `is_fulfillable`: write `NOT_FULFILLABLE` to **every** line of the order.
3. Otherwise: if `shortfall` is non-empty, return
   `(False, "Cannot force fulfill. Insufficient stock for SKUs: A, B", df)`
   (today's text) and change nothing. If it is empty, write `FULFILLABLE` to
   every line.
4. `return True, None, with_stock_left(df)`.

Delete the unreachable "unlisted SKU → append a row" branch. Its SKUs come
from the order's own rows, so it can never run.

### 4.3 Bulk status (AUDIT-01-3, D1)

`bulk_change_status(order_numbers, is_fulfillable)`:

- **Hold**: write `NOT_FULFILLABLE` to every line of every selected order,
  then `with_stock_left`.
- **Mark fulfillable**: walk the selected orders in **frame order**.
  - Skip an order that is already fulfillable. It is not counted either way.
  - For each blocked order, call `shortfall` against the current frame. If it
    is empty, write `FULFILLABLE` to its lines and run `with_stock_left`
    before checking the next order, so two orders can't be promised the same
    units. Otherwise count it as skipped.
- Record one undo operation covering the rows of the orders that changed. If
  nothing changed, record nothing and don't save.
- Toast copy (`_plural` as today):
  - all covered: `"3 orders marked fulfillable"` (unchanged), undoable
  - some skipped: `"3 orders marked fulfillable · 2 skipped: not enough stock"`, undoable
  - none covered: `"No orders marked fulfillable: not enough stock for 2 orders"`, not undoable
  - Hold: `"3 orders held"` (unchanged)

The frame order is a decision this run made on its own, and it is
reversible. The run's priority order no longer exists after the run, and
frame order is what the person sees.

### 4.4 Removal verbs (AUDIT-01-4)

Five verbs remove rows: `remove_item_from_order` (through `remove_line`),
`remove_entire_order`, `bulk_remove_sku_from_orders`,
`bulk_remove_orders_with_sku` and `bulk_delete_orders`. Each one writes
`with_stock_left(new_df)` back to `mw.analysis_results_df`. A removal never
changes an order's status.

### 4.5 Add product (AUDIT-01-1, D6)

`_add_product_to_order` builds the new row as today, with these changes:

- The new row's `Stock` is the frame's existing opening Stock for that SKU
  when the SKU is already in the frame. Otherwise it is the **sum** of that
  SKU's rows in the stock file (D2). Otherwise 0. Its `Final_Stock` is 0 for
  a SKU missing from both, which keeps today's behaviour: the SKU counts as
  listed, with no stock.
- The new row takes the order's R1 status.
- **Fulfillable order**: append the row. If `shortfall(df, order)` is
  non-empty, write `NOT_FULFILLABLE` to every line of the order. Then run
  `with_stock_left`.
- **Held or blocked order**: append the row as `NOT_FULFILLABLE` and run
  `with_stock_left`. Nothing is drawn.
- Toast: `"Added 1x B to order #1."` as today. When the add blocks a
  fulfillable order, `"Added 1x B to order #1. It is now blocked: not enough B."`
- Delete `_recalculate_order_fulfillment`. It has no other caller (verify
  with `rg`).

### 4.6 Undo (AUDIT-01-2, -11)

- `UndoManager.record_operation` also stores
  `"row_positions": [int(i) for i in affected_rows_before.index]` on the
  operation record, not in `params`. Every verb passes a slice of the live
  frame, which always has a RangeIndex, so labels are positions. This needs
  no change at any call site.
- **Status undos** (`_undo_toggle_status`, `_undo_bulk_change_status`): when
  `row_positions` is present, every position is `< len(df)`, and each
  position's `Order_Number` matches the saved row's, restore
  `Order_Fulfillment_Status` row by row. Otherwise fall back to today's
  per-order restore. Row by row is exact for an order whose lines disagreed;
  the per-order restore would make it fully fulfillable and over-draw.
- **Removal undos** (`_undo_remove_item`, `_undo_remove_order`,
  `_undo_bulk_remove_sku`, `_undo_bulk_remove_orders_with_sku`,
  `_undo_bulk_delete_orders`): when `row_positions` is present, put the rows
  back at their positions. The remaining rows take the positions not in
  `row_positions`, in their current order, and the result is sorted and
  re-indexed. Otherwise append the rows, as today. One private helper,
  `_reinsert(rows, positions)`, serves all five.
- `undo()`: after any successful handler, write
  `with_stock_left(main_window.analysis_results_df)` back. One line, which
  covers every operation type.

Why positions stay valid: undo is strictly last-in-first-out, so the frame
is exactly as the operation left it. Add product isn't recorded in undo, but
it appends at the end, so earlier positions don't move.

### 4.7 Session open (D4)

In `MainWindow.load_existing_session`, right after `_load_session_analysis`
returns true and before `_update_all_views()`:
`self.analysis_results_df = with_stock_left(self.analysis_results_df)`.
Nothing is written to disk until the next edit saves.

### 4.8 Outputs (AUDIT-04-6)

`report_filters.fulfillable_only(df)` keeps the lines whose own status is
`Fulfillable` **and** whose order is in `fulfillable_orders(df)`. No-SKU lines
still drop out on their line status, as today. The packing list, the stock
export, the dialog preview, the report-editor counts and the Packing Tool JSON
already go through it.

Four more writers select Fulfillable lines on their own. They switch to
`fulfillable_only`, so one rule decides what ships:

- `sku_writeoff.py:158`
- `stock_export.py:391` (multi-session merge)
- `sequential_order.py:84`
- `barcode_generator_widget.py:318`

`sku_writeoff` and `sequential_order` keep their "no status column" handling:
`fulfillable_only` already returns an empty frame there, so check that each
caller's current fallback still holds, and keep that fallback where it
differs.

### 4.9 Statistics (AUDIT-01-6)

In `recalculate_statistics`:

- The completed rows are `fulfillable_only(df)`.
- `total_orders_completed` is their `Order_Number.nunique()`.
- `total_orders_not_completed` is `df.Order_Number.nunique()` minus completed.
- The not-completed rows are the rows outside completed, and
  `total_items_not_to_write_off` sums them.
- The courier stats and the fulfillable/not-fulfillable tag breakdowns use
  the same two row sets.
- The SKU summary's `Fulfillable_Qty` counts completed rows only.

Import `fulfillable_only` inside the function if a module-level import would
cycle.

### 4.10 Stock intake (AUDIT-01-7, -8)

In `_clean_and_prepare_data`, before the lot/no-lot branch:
`stock_df["Stock"] = pd.to_numeric(stock_df["Stock"], errors="coerce").fillna(0)`.
Log a warning naming up to 10 SKUs whose cell was blank or not a number. The
no-lot branch replaces `drop_duplicates(keep="first")` with the lot branch's
aggregation: `groupby("SKU")`, summing `Stock` and taking the `first`
`Product_Name`. Inventory memory's `.last()` is AUDIT-02-10 (Bundle 3), so
leave it alone.

### 4.11 No order number (AUDIT-01-9, D5)

- `analysis.py`: `NO_ORDER_NUMBER = "(no order number)"`. After the ffill at
  `:299`, run `.fillna(NO_ORDER_NUMBER)` and log a warning with the count.
- In `run_analysis`, drop `NO_ORDER_NUMBER` from `prioritized_orders` before
  `_simulate_stock_allocation`. Afterwards set
  `fulfillment_results[NO_ORDER_NUMBER] = {"fulfillable": False, "reason": "No order number"}`
  when those lines exist.
- The existing System_note path then writes `Cannot fulfill: No order number`.
  The verdict parser reads that as code `other`, so the order shows as
  "review". No new reason code is added.

### 4.12 Set import (AUDIT-01-10)

`import_sets_from_csv`: `pd.read_csv(csv_path, dtype=str)`. The
Component_Quantity `astype(int)` and the empty-cell checks already work on
strings.

## 5. Testing

The acceptance tests are the proof tests, with their `xfail` markers removed:

- `tests/audit/test_01_intake_analysis.py`: all AUDIT-01-1 to -11 tests. Leave
  -12 marked.
- `tests/audit/test_04_outputs.py`:
  `test_packing_list_never_lists_part_of_an_order` and
  `test_stock_export_never_writes_off_part_of_an_order`.

New tests go at the seams:

- **`tests/test_stock_ledger.py`** (the module's own contract, pure pandas):
  - R1 on a mixed order, a no-SKU first line, a no-SKU-only order and a
    missing `Has_SKU` column.
  - R2 equals the run's `Final_Stock` on a fresh `run_analysis`, on the plain
    path and the lot path. This is the invariant everything rests on.
  - An unlisted SKU stays null and counts as covered.
  - `shortfall` sums repeated SKU lines and releases the order's own draw.
  - A frame with no ledger columns is a no-op.
- **Handler seam** (`tests/test_actions_handler_bulk.py`):
  - bulk Mark with one covered and one uncovered order: the uncovered one is
    skipped, the toast gives the count, and there is no double promise.
  - bulk Mark with nothing covered records no undo.
- **Undo seam** (`tests/test_undo_manager.py`):
  - A mixed order held and then undone keeps its per-line statuses.
  - An operation record without `row_positions` (older history) still undoes
    by appending.
  - Bulk-delete undo restores the row order.
- **Add product**: adding to a held order leaves it held, and nothing is
  drawn.

Existing tests that pin the old tracked model get rewritten, not deleted.
Known one: `tests/test_analysis.py::TestToggleOrderFulfillment::test_force_fulfill_succeeds_when_stock_available`
tops up `Final_Stock` by hand. Top up `Stock` instead, so the derived value is
25 − 20 = 5. List every such rewrite in the PR body.

Other bundles' `xfail(strict=True)` tests: if one starts passing, **don't**
remove its marker. Record it in `state.md` and the PR body, because it means
this bundle fixed part of another finding. Likely candidates:
AUDIT-03-1/-2 via R1/R2, and AUDIT-02-10.

## 6. Not covered

- **Lot details after edits.** Hold and Mark fulfillable don't rewrite
  `Lot_Details`, so a held order keeps its lots and a force-fulfilled order
  has none. The audits didn't raise this, and it is unchanged here.
- **Add product isn't undoable** (unchanged).
- **Run-time rules** (AUDIT-03-1, -2) still produce frames that R2 would
  re-derive differently. The first edit, or the next open, corrects them.
  Bundle 5 fixes the rules themselves.
- **Inventory memory seeding** (AUDIT-02-10), Bundle 3.
