# Phase 14 Bundle 1 — Stock Ledger and Order Status Implementation Plan

> **For agentic workers:** Execute in-session with superpowers:executing-plans
> (the roadmap runner forbids fanning out to subagents). Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Stock left stays true through every edit and undo, an order's status is read one way everywhere, and no output ships part of an order. This fixes AUDIT-01-1 to -11 and AUDIT-04-6.

**Architecture:** A new pure-pandas module, `shopify_tool/stock_ledger.py`, holds the two rules. R1: an order is fulfillable when every SKU line is. R2: Stock left = opening Stock − the SKU lines of fulfillable orders. Every edit verb writes rows and statuses, then calls `with_stock_left(df)`, and so does every undo. Nothing adjusts `Final_Stock` by hand any more (ADR 0010). Every status reader and output filter goes through R1.

**Tech Stack:** Python 3, pandas, PySide6 (GUI handlers only), pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-phase14-bundle1-stock-ledger-design.md`. Read it first: §1 (owner decisions), then §2 (R1 and R2).

## Global Constraints

- Worktree: `.claude/worktrees/worktree-phase14-bundle1-stock-ledger`, branch `worktree-phase14-bundle1-stock-ledger`. Run `./scripts/setup_venv.sh` once before anything else (no `.venv` yet).
- Tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q <path>`.
- Git: use `/usr/bin/git`, **one plain git command per Bash call**. No `cd &&`, no `$VAR` paths, no rtk-wrapped git. Commit with `/usr/bin/git commit -F <msgfile>`, writing the message file under `$CLAUDE_JOB_DIR/tmp` with the Write tool. The pre-commit hook runs ruff, so fix whatever it reports.
- Every commit message ends with the `Co-Authored-By` trailer from the session's attribution reminder.
- Don't touch `shared/` (it's synced from packing-tool).
- Status strings are exactly `"Fulfillable"` and `"Not Fulfillable"`. Use `stock_ledger.FULFILLABLE` / `NOT_FULFILLABLE` in any code you touch.
- Order numbers are matched as `str(x).strip()` on both sides.
- Remove an audit `xfail` marker only for this bundle's findings: AUDIT-01-1 to -11 and the two AUDIT-04-6 tests. Leave AUDIT-01-12 marked. If a **different** finding's strict xfail starts passing (it fails as XPASS), **don't** remove its marker. Record it in `state.md` and stop to report it.
- Toast copy is exactly as the spec (§4.3, §4.5) writes it.

## Review Focus

1. **A legacy session with a mixed order** (fulfillable lines beside one blocked SKU line, as in ALMADERM 07-01_2). Hold, then undo, must bring back the per-line statuses, and Stock left must never go negative. Test: Task 7, `test_undo_of_hold_on_mixed_order_restores_each_line`.
2. **An old `operations_history.json` record with no `row_positions`.** Undo must still work, falling back to appending rows and restoring per order. Test: Task 7, `test_undo_without_row_positions_still_appends`.
3. **An unlisted SKU** (in the orders, missing from the stock file). `Final_Stock` stays null, and Mark fulfillable is not refused because of it. Test: Task 1, `test_unlisted_sku_stays_null_and_counts_as_covered`.
4. **Bulk Mark fulfillable where only the first of two orders fits.** Only the first is marked, the second is skipped, and Stock left is never promised twice. Test: Task 6, `test_bulk_mark_fulfillable_skips_what_stock_left_cannot_cover`.
5. **A frame with no `Stock`/`Final_Stock` columns** (older GUI test fixtures, and the report-only frames in the audit 04 tests). Everything is a no-op, not a crash. Test: Task 1, `test_frame_without_ledger_columns_is_a_no_op`.

---

## File map

| File | Change |
|---|---|
| `shopify_tool/stock_ledger.py` | **new**: R1, R2, shortfall, claim |
| `tests/test_stock_ledger.py` | **new**: module contract |
| `shopify_tool/analysis.py` | stock coercion and summing (§4.10), `NO_ORDER_NUMBER` (§4.11), toggle rewrite (§4.2), stats (§4.9) |
| `shopify_tool/set_decoder.py` | `dtype=str` (§4.12) |
| `shopify_tool/report_filters.py` | `fulfillable_only` uses R1 (§4.8) |
| `shopify_tool/sku_writeoff.py`, `shopify_tool/stock_export.py`, `shopify_tool/sequential_order.py`, `gui/barcode_generator_widget.py` | route through `fulfillable_only` |
| `shopify_tool/core.py` | `build_packing_order_data` status via R1 |
| `gui/orders_view.py` | `orders_frame`, `order_payload` verdict and KPI via R1 |
| `gui/add_product_dialog.py` | displayed status via R1 |
| `gui/actions_handler.py` | `set_order_fulfillable`, bulk status, five removal verbs, add product |
| `shopify_tool/undo_manager.py` | `row_positions`, `_reinsert`, per-row status restore, re-derive after undo |
| `gui/main_window_pyside.py` | re-derive on session open |
| `tests/audit/test_01_intake_analysis.py`, `tests/audit/test_04_outputs.py` | remove this bundle's xfail markers |

---

### Task 1: `stock_ledger` module

**Files:**
- Create: `shopify_tool/stock_ledger.py`
- Test: `tests/test_stock_ledger.py`

**Interfaces:**
- Produces (every later task uses these exact names):
  - `FULFILLABLE: str`, `NOT_FULFILLABLE: str`
  - `fulfillable_orders(df) -> set[str]` (stripped str order numbers)
  - `is_fulfillable(df, order_number) -> bool`
  - `stock_left(df, excluding=None) -> dict` (SKU → float, listed SKUs only)
  - `shortfall(df, order_number) -> list` (SKUs not covered; `[]` = covered)
  - `claim(df, order_numbers) -> tuple[list, list]` (`(covered, skipped)`, as the caller passed them)
  - `with_stock_left(df) -> pd.DataFrame` (updates `Final_Stock` in place, returns the same frame)

- [ ] **Step 1: Write the failing tests**

```python
"""stock_ledger: the order-status rule (R1) and Stock left (R2).

Spec: docs/superpowers/specs/2026-09-25-phase14-bundle1-stock-ledger-design.md §2-3.
"""

import pandas as pd
import pytest

from shopify_tool.analysis import run_analysis
from shopify_tool.stock_ledger import (
    FULFILLABLE as FF,
    NOT_FULFILLABLE as NF,
    claim,
    fulfillable_orders,
    is_fulfillable,
    shortfall,
    stock_left,
    with_stock_left,
)


def frame(rows):
    """(order, sku, qty, status, stock, final_stock); sku None = no-SKU line."""
    df = pd.DataFrame(
        rows,
        columns=["Order_Number", "SKU", "Quantity", "Order_Fulfillment_Status",
                 "Stock", "Final_Stock"],
    )
    df["Has_SKU"] = df["SKU"].notna()
    df.loc[~df["Has_SKU"], "SKU"] = "NO_SKU"
    return df


def test_one_blocked_sku_line_blocks_the_order():
    df = frame([("#1", "A", 1, FF, 5, 4), ("#1", "GIFT", 1, NF, 0, 0)])
    assert fulfillable_orders(df) == set()


def test_no_sku_line_does_not_block_and_first_row_does_not_decide():
    df = frame([("#1", None, 1, NF, 0, None), ("#1", "A", 2, FF, 5, 3)])
    assert is_fulfillable(df, "#1")
    assert is_fulfillable(df, " #1 ")


def test_order_with_only_no_sku_lines_follows_its_lines():
    df = frame([("#1", None, 1, NF, 0, None)])
    assert not is_fulfillable(df, "#1")
    df["Order_Fulfillment_Status"] = FF
    assert is_fulfillable(df, "#1")


def test_frame_without_has_sku_uses_the_sku_column():
    df = frame([("#1", None, 1, NF, 0, None), ("#1", "A", 2, FF, 5, 3)])
    df = df.drop(columns=["Has_SKU"])
    assert is_fulfillable(df, "#1")


def test_stock_left_is_opening_minus_fulfillable_orders():
    df = frame([
        ("#1", "A", 2, FF, 5, 999),   # stale Final_Stock is ignored
        ("#2", "A", 1, NF, 5, 999),
        ("#3", "A", 1, FF, 5, 999),
        ("#3", "B", 1, NF, 4, 999),   # mixed: #3 is blocked, draws nothing
    ])
    assert stock_left(df) == {"A": 3.0, "B": 4.0}
    assert stock_left(df, excluding="#1") == {"A": 5.0, "B": 4.0}


def test_unlisted_sku_stays_null_and_counts_as_covered():
    df = frame([("#1", "X", 3, NF, 0, None), ("#2", "A", 1, FF, 2, 1)])
    assert "X" not in stock_left(df)
    assert shortfall(df, "#1") == []
    out = with_stock_left(df)
    assert out.loc[out["SKU"] == "X", "Final_Stock"].isna().all()
    assert out.loc[out["SKU"] == "A", "Final_Stock"].tolist() == [1.0]


def test_shortfall_sums_repeated_lines_and_releases_own_draw():
    df = frame([("#1", "A", 2, NF, 3, 3), ("#1", "A", 2, NF, 3, 3)])
    assert shortfall(df, "#1") == ["A"]           # needs 4, has 3
    df2 = frame([("#1", "A", 2, FF, 3, 1), ("#1", "B", 1, FF, 1, 0)])
    assert shortfall(df2, "#1") == []             # its own 2 A are released


def test_claim_takes_orders_in_the_given_order_without_double_promising():
    df = frame([("#1", "A", 2, NF, 3, 3), ("#2", "A", 2, NF, 3, 3),
                ("#3", "A", 1, FF, 3, 3)])
    # #3 already holds 1, so 2 are left: #1 fits, then #2 does not.
    assert claim(df, ["#1", "#2", "#3"]) == (["#1"], ["#2"])


def test_frame_without_ledger_columns_is_a_no_op():
    df = pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"], "Quantity": [1],
                       "Order_Fulfillment_Status": [NF]})
    assert stock_left(df) == {}
    assert shortfall(df, "#1") == []
    assert claim(df, ["#1"]) == (["#1"], [])
    assert with_stock_left(df) is df
    assert "Final_Stock" not in df.columns


def _stock(rows, lots=False):
    cols = ["Артикул", "Наличност", "Годност", "Партида"] if lots else ["Артикул", "Наличност"]
    df = pd.DataFrame(rows, columns=cols)
    df["Име"] = df["Артикул"] + " name"
    return df


def _orders(rows):
    df = pd.DataFrame(rows, columns=["Name", "Lineitem sku", "Lineitem quantity"])
    df["Shipping Method"] = "DHL"
    return df


@pytest.mark.parametrize("lots", [False, True])
def test_derived_stock_left_equals_the_runs_final_stock(lots):
    """The invariant ADR 0010 rests on: re-deriving a fresh run changes nothing."""
    stock = (
        _stock([("A", 3, "261230", "B1"), ("A", 2, "270101", "B2"), ("B", 1, "261230", "B3")], lots=True)
        if lots
        else _stock([("A", 5), ("B", 1)])
    )
    orders = _orders([("#1", "A", 2), ("#1", "B", 1), ("#2", "A", 4),
                      ("#3", "A", 1), ("#3", None, 1), ("#4", "Z", 1)])
    df, *_ = run_analysis(stock, orders, pd.DataFrame({"Order_Number": []}))
    before = df["Final_Stock"].copy()
    after = with_stock_left(df.copy())["Final_Stock"]
    pd.testing.assert_series_equal(before.astype(float), after.astype(float), check_names=False)
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_stock_ledger.py`
Expected: an ImportError / collection error (`shopify_tool.stock_ledger` doesn't exist yet).

- [ ] **Step 3: Implement**

```python
"""Order status and Stock left, derived from the analysis frame.

The only place two rules live (spec 2026-09-25 bundle 1 §2, ADR 0010):

R1  An order is fulfillable when every one of its SKU lines is Fulfillable.
    An order with no SKU lines follows all of its lines.
R2  Stock left = opening Stock - the SKU lines of fulfillable orders, per
    listed SKU. A SKU whose Final_Stock is null on every row is unlisted
    (missing from the stock file): it stays null and never blocks.

Edit verbs write rows and statuses, then call with_stock_left. They never
adjust Final_Stock themselves.
"""

import pandas as pd

FULFILLABLE = "Fulfillable"
NOT_FULFILLABLE = "Not Fulfillable"

_LEDGER_COLUMNS = {"SKU", "Stock", "Final_Stock"}


def _key(value) -> str:
    return str(value).strip()


def _keys(df: pd.DataFrame) -> pd.Series:
    return df["Order_Number"].astype(str).str.strip()


def _sku_lines(df: pd.DataFrame) -> pd.Series:
    if "Has_SKU" in df.columns:
        return df["Has_SKU"].fillna(False).astype(bool)
    if "SKU" in df.columns:
        return df["SKU"].notna() & (df["SKU"].astype(str) != "NO_SKU")
    return pd.Series(True, index=df.index)


def _has_ledger(df) -> bool:
    return df is not None and not df.empty and _LEDGER_COLUMNS <= set(df.columns)


def fulfillable_orders(df) -> set:
    """R1: the order numbers (str, stripped) of the fulfillable orders."""
    if df is None or df.empty or "Order_Fulfillment_Status" not in df.columns:
        return set()
    keys = _keys(df)
    sku = _sku_lines(df)
    deciding = sku | ~sku.groupby(keys).transform("any")
    blocked = (deciding & df["Order_Fulfillment_Status"].ne(FULFILLABLE)).groupby(keys).any()
    return set(blocked.index[~blocked])


def is_fulfillable(df, order_number) -> bool:
    return _key(order_number) in fulfillable_orders(df)


def stock_left(df, excluding=None) -> dict:
    """R2 per listed SKU. `excluding`: an order whose own draw is released."""
    if not _has_ledger(df):
        return {}
    rows = df[_sku_lines(df)]
    by_sku = rows["SKU"]
    listed = rows["Final_Stock"].notna().groupby(by_sku).any()
    opening = pd.to_numeric(rows.groupby("SKU")["Stock"].first(), errors="coerce").fillna(0)
    drawing = _keys(rows).isin(fulfillable_orders(df))
    if excluding is not None:
        drawing &= _keys(rows) != _key(excluding)
    qty = pd.to_numeric(rows["Quantity"], errors="coerce").fillna(0).where(drawing, 0)
    left = (opening - qty.groupby(by_sku).sum())[listed]
    return {sku: float(v) for sku, v in left.items()}


def _needs(df, order_number) -> dict:
    rows = df[(_keys(df) == _key(order_number)) & _sku_lines(df)]
    qty = pd.to_numeric(rows["Quantity"], errors="coerce").fillna(0)
    return qty.groupby(rows["SKU"], sort=False).sum().to_dict()


def _short(needs: dict, left: dict) -> list:
    return [sku for sku, need in needs.items() if sku in left and need > left[sku]]


def shortfall(df, order_number) -> list:
    """SKUs Stock left can't cover for this order, its own draw released."""
    if not _has_ledger(df):
        return []
    return _short(_needs(df, order_number), stock_left(df, excluding=order_number))


def claim(df, order_numbers) -> tuple:
    """Which of these orders Stock left covers, taken in the order given.

    Each covered order draws before the next is checked. Orders that are
    already fulfillable are in neither list. Returns (covered, skipped) with
    the order numbers as the caller passed them.
    """
    already = fulfillable_orders(df)
    left = stock_left(df)
    covered, skipped = [], []
    for number in order_numbers:
        if _key(number) in already:
            continue
        needs = _needs(df, number) if _has_ledger(df) else {}
        if _short(needs, left):
            skipped.append(number)
            continue
        for sku, need in needs.items():
            if sku in left:
                left[sku] -= need
        covered.append(number)
    return covered, skipped


def with_stock_left(df):
    """Rewrite Final_Stock on every row of a listed SKU. Returns df."""
    left = stock_left(df)
    if left:
        derived = df["SKU"].map(left)
        df["Final_Stock"] = derived.where(derived.notna(), df["Final_Stock"])
    return df
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_stock_ledger.py`
Expected: all pass. If `test_derived_stock_left_equals_the_runs_final_stock` fails, **stop**. The invariant is false, and the whole design depends on it. Record which SKU differs, and why, in `state.md`, and end the run.

- [ ] **Step 5: Commit**: `git add shopify_tool/stock_ledger.py tests/test_stock_ledger.py`, then commit with the message `feat(ledger): stock_ledger derives order status and Stock left (AUDIT-01)`.

---

### Task 2: Stock intake, order numbers, set import (AUDIT-01-7, -8, -9, -10)

**Files:**
- Modify: `shopify_tool/analysis.py` (stock branch around `:449-466`, ffill `:299`, `run_analysis` around `:1480-1490`)
- Modify: `shopify_tool/set_decoder.py:180`
- Test: `tests/audit/test_01_intake_analysis.py` (remove 4 markers)

**Interfaces:** Produces `analysis.NO_ORDER_NUMBER = "(no order number)"`.

- [ ] **Step 1: Remove the `@pytest.mark.xfail(...)` decorators** from `test_blank_stock_cell_is_not_unlimited_stock`, `test_duplicate_stock_rows_count_the_same_with_or_without_lot_columns`, `test_no_order_line_silently_disappears` and `test_set_import_keeps_sku_text`. Run each and confirm it fails.

- [ ] **Step 2: Stock coercion and summing.** In `_clean_and_prepare_data`, right after `stock_df.loc[has_sku, "SKU"] = ...map(normalize_sku)`, add:

```python
    # A blank or non-numeric stock cell is no stock, never unlimited stock:
    # NaN fails both "== 0" and "required > available" (AUDIT-01-7).
    stock_numeric = pd.to_numeric(stock_df["Stock"], errors="coerce")
    bad = stock_numeric.isna() & has_sku
    if bad.any():
        logger.warning(
            f"{int(bad.sum())} stock rows have a blank or non-numeric stock cell, "
            f"read as 0: {stock_df.loc[bad, 'SKU'].tolist()[:10]}"
        )
    stock_df["Stock"] = stock_numeric.fillna(0)
```

Then replace the no-lot branch's body so that duplicate rows are summed, like the lot branch (AUDIT-01-8, owner rule):

```python
    if not lot_columns_present:
        # One total per SKU, summed like the lot path (AUDIT-01-8, owner rule).
        fifo_lots = None
        agg_dict: dict = {"Stock": ("Stock", "sum")}
        if "Product_Name" in stock_df.columns:
            agg_dict["Product_Name"] = ("Product_Name", "first")
        stock_clean_df = stock_df.dropna(subset=["SKU"]).groupby("SKU", as_index=False).agg(**agg_dict)
```

Keep the `else:` (lot) branch as it is. Its `agg_dict` is now defined in both branches, so ruff shouldn't complain. If it flags a redefinition, hoist the shared `agg_dict` above the `if`.

- [ ] **Step 3: No order number.** Near the top of `analysis.py`, after the imports: `NO_ORDER_NUMBER = "(no order number)"`. At `:299`:

```python
    if "Order_Number" in orders_df.columns:
        orders_df["Order_Number"] = orders_df["Order_Number"].ffill()
        orphans = orders_df["Order_Number"].isna()
        if orphans.any():
            # Lines above the first order number stay visible as one blocked
            # order instead of vanishing in a groupby (AUDIT-01-9).
            logger.warning(f"{int(orphans.sum())} order lines have no order number")
            orders_df.loc[orphans, "Order_Number"] = NO_ORDER_NUMBER
```

In `run_analysis`, right after `prioritized_orders = _prioritize_orders(...)`:

```python
        prioritized_orders = prioritized_orders[
            prioritized_orders["Order_Number"] != NO_ORDER_NUMBER
        ]
```

And right after the `_simulate_stock_allocation(...)` call:

```python
        if (orders_clean["Order_Number"] == NO_ORDER_NUMBER).any():
            fulfillment_results[NO_ORDER_NUMBER] = {
                "fulfillable": False,
                "reason": "No order number",
            }
```

- [ ] **Step 4: Set import.** `set_decoder.py:180`: change it to `df = pd.read_csv(csv_path, dtype=str)`.

- [ ] **Step 5:** Run `tests/audit/test_01_intake_analysis.py tests/test_analysis.py tests/test_core.py tests/test_set_decoder*.py tests/test_stock_ledger.py`. The 4 unmarked tests must pass and nothing else may regress. Then commit: `fix(analysis): stock intake reads blanks as 0 and sums duplicate rows; keep orphan lines; set import keeps SKU text (AUDIT-01-7, -8, -9, -10)`.

---

### Task 3: One order-status rule for toggle and every reader (AUDIT-01-5)

**Files:**
- Modify: `shopify_tool/analysis.py:1740-1838` (`toggle_order_fulfillment`)
- Modify: `gui/actions_handler.py:942-956` (`set_order_fulfillable`)
- Modify: `gui/orders_view.py` (`orders_frame` `:204`, `order_payload` `:303`, KPI `:398`)
- Modify: `shopify_tool/core.py:116`, `gui/add_product_dialog.py:205`
- Test: `tests/audit/test_01_intake_analysis.py`, `tests/test_analysis.py`, `tests/test_order_payload.py`

**Interfaces:** Consumes `is_fulfillable`, `fulfillable_orders`, `shortfall`, `with_stock_left`, `FULFILLABLE`, `NOT_FULFILLABLE` from Task 1.

- [ ] **Step 1:** Remove the xfail marker from `test_toggle_holds_a_fulfillable_order_whose_first_line_has_no_sku` and confirm it fails. Then add this to `tests/test_order_payload.py` (reuse that file's own frame helpers if it has them; otherwise build the frame inline, as below):

```python
def test_order_status_ignores_a_no_sku_first_line():
    import pandas as pd
    from gui.orders_view import order_payload, orders_frame

    df = pd.DataFrame({
        "Order_Number": ["#1", "#1"],
        "SKU": ["NO_SKU", "A"],
        "Has_SKU": [False, True],
        "Quantity": [1, 2],
        "Order_Fulfillment_Status": ["Not Fulfillable", "Fulfillable"],
        "System_note": ["[NO_SKU]", ""],
    })
    assert orders_frame(df)["Order_Fulfillment_Status"].tolist() == ["Fulfillable"]
    assert order_payload(df)[0]["Order_Fulfillment_Status"] == "Fulfillable"
```

Check how `order_payload` exposes the status key. If the entry names it differently, assert on that name. Run it and confirm it fails.

- [ ] **Step 2: Rewrite `toggle_order_fulfillment`.** Keep the docstring's first paragraph, and update the bullets to say that status follows R1 and Stock left is re-derived. Body:

```python
    if df is None:
        return False, "DataFrame is None.", df

    order_mask = df["Order_Number"].astype(str).str.strip() == str(order_number).strip()
    if not order_mask.any():
        return False, "Order number not found.", df

    if is_fulfillable(df, order_number):
        new_status = NOT_FULFILLABLE
    else:
        lacking = shortfall(df, order_number)
        if lacking:
            return (
                False,
                "Cannot force fulfill. Insufficient stock for SKUs: "
                + ", ".join(map(str, lacking)),
                df,
            )
        new_status = FULFILLABLE

    df.loc[order_mask, "Order_Fulfillment_Status"] = new_status
    return True, None, with_stock_left(df)
```

Add the import at the top of `analysis.py`: `from .stock_ledger import FULFILLABLE, NOT_FULFILLABLE, is_fulfillable, shortfall, with_stock_left`.

- [ ] **Step 3: Fix the test that pins the old model.** In `tests/test_analysis.py::TestToggleOrderFulfillment::test_force_fulfill_succeeds_when_stock_available`, change the top-up line to
`final_df.loc[final_df["SKU"] == "A1", "Stock"] = 25  # Stock left is derived from Stock (ADR 0010)`.
The assertion `Final_Stock == 5` stays.

- [ ] **Step 4: Readers.**
  - `set_order_fulfillable`: `is_fulfillable = stock_ledger.is_fulfillable(df, order_number)`. Import `from shopify_tool import stock_ledger`, and rename the local so it doesn't shadow.
  - `orders_view.orders_frame`: after `out` is built, and when `"Order_Fulfillment_Status" in out.columns`:
    ```python
    ready = fulfillable_orders(df)
    out["Order_Fulfillment_Status"] = [
        FULFILLABLE if str(k).strip() in ready else NOT_FULFILLABLE for k in out[ORDER_KEY]
    ]
    ```
  - `order_payload`: compute `ready = fulfillable_orders(df)` once before the loop, and pass `FULFILLABLE if str(key).strip() in ready else NOT_FULFILLABLE` as `status` to `order_verdict`. This only applies when the column exists; otherwise keep `""`.
  - KPI at `:398`: `fulfillable = fulfillable_orders(df)` and `blocked_rows = df[~df[ORDER_KEY].astype(str).str.strip().isin(fulfillable)]`. Keep the rest of the function as it is, and check any other use of `fulfillable_orders` / `ready_mask` in it.
  - `core.build_packing_order_data`: `fulfillment_status = FULFILLABLE if is_fulfillable(group, order_number) else NOT_FULFILLABLE` when the group has the column; otherwise `"Unknown"`, as today.
  - `add_product_dialog:205`: `status = FULFILLABLE if is_fulfillable(order_rows, text_str) else NOT_FULFILLABLE`.

- [ ] **Step 5:** Run `tests/audit/test_01_intake_analysis.py tests/test_analysis.py tests/test_order_payload.py tests/test_order_verdict.py tests/test_core.py tests/test_pane_actions.py tests/test_results_pane.py tests/test_add_product_dialog.py`. Everything should pass. Commit: `fix(status): order status follows R1 everywhere; toggle re-derives Stock left (AUDIT-01-5)`.

---

### Task 4: Statistics count each order once (AUDIT-01-6)

**Files:** Modify `shopify_tool/analysis.py:1552` (`recalculate_statistics`). Test: `tests/audit/test_01_intake_analysis.py`.

**Interfaces:** Consumes `report_filters.fulfillable_only`, which Task 5 changes. The row selection this task relies on is correct once Task 5 lands. The order counts are correct already.

- [ ] **Step 1:** Remove the xfail marker from `test_stats_count_each_order_once`, then run it and confirm it fails.
- [ ] **Step 2:** Replace the two row sets and the two counts:

```python
    from shopify_tool.report_filters import fulfillable_only  # local: avoids an import cycle

    completed_orders_df = fulfillable_only(df).copy()
    not_completed_orders_df = df.drop(index=completed_orders_df.index)

    stats["total_orders_completed"] = int(completed_orders_df["Order_Number"].nunique())
    stats["total_orders_not_completed"] = int(df["Order_Number"].nunique()) - stats["total_orders_completed"]
```

In the tags block, use `fulfillable_df = completed_orders_df` and `not_fulfillable_df = not_completed_orders_df`. In the SKU summary, set `Fulfillable_Qty` to `Quantity` on rows whose index is in `completed_orders_df.index`, and 0 elsewhere:
`df_temp["Fulfillable_Qty"] = df_temp["Quantity"].where(df_temp.index.isin(completed_orders_df.index), 0)`.
- [ ] **Step 3:** Run `tests/audit/test_01_intake_analysis.py tests/test_analysis.py tests/test_core.py`, then commit: `fix(stats): count each order once (AUDIT-01-6)`.

---

### Task 5: Outputs never ship part of an order (AUDIT-04-6)

**Files:**
- Modify: `shopify_tool/report_filters.py:78`, `shopify_tool/sku_writeoff.py:156-160`, `shopify_tool/stock_export.py:391`, `shopify_tool/sequential_order.py:83-85`, `gui/barcode_generator_widget.py:314-320`
- Test: `tests/audit/test_04_outputs.py` (remove 2 markers), `tests/test_report_filters*.py` (add one test)

- [ ] **Step 1:** Remove the markers from `test_packing_list_never_lists_part_of_an_order` and `test_stock_export_never_writes_off_part_of_an_order`, and add the following next to the existing `fulfillable_only` tests (find them with `rg -l fulfillable_only tests`):

```python
def test_fulfillable_only_drops_an_order_with_a_blocked_sku_line_but_not_for_a_fee_line():
    import pandas as pd
    from shopify_tool.report_filters import fulfillable_only

    df = pd.DataFrame({
        "Order_Number": ["#1", "#1", "#2", "#2"],
        "SKU": ["A", "GIFT", "C", "NO_SKU"],
        "Has_SKU": [True, True, True, False],
        "Order_Fulfillment_Status": ["Fulfillable", "Not Fulfillable", "Fulfillable", "Not Fulfillable"],
    })
    out = fulfillable_only(df)
    assert out[["Order_Number", "SKU"]].values.tolist() == [["#2", "C"]]
```

Run them all and confirm they fail.

- [ ] **Step 2:** In `fulfillable_only`, replace the last line with:

```python
    ships = df["Order_Number"].astype(str).str.strip().isin(fulfillable_orders(df))
    return df[df["Order_Fulfillment_Status"].eq(FULFILLABLE) & ships]
```

Import `from shopify_tool.stock_ledger import FULFILLABLE, fulfillable_orders`. Add one sentence to the docstring: an order ships whole or not at all (AUDIT-04-6).

- [ ] **Step 3:** Route the other four through it:
  - `sku_writeoff.py`: `rows_df = fulfillable_only(analysis_df)` inside the existing `if has_status_col:`, keeping its `else`.
  - `stock_export.py:391`: `fulfillable = fulfillable_only(df).copy()`.
  - `sequential_order.py`: `fulfillable_df = fulfillable_only(analysis_results_df).copy()`.
  - `barcode_generator_widget.py`: `base = fulfillable_only(self.mw.analysis_results_df)`, then `filtered_df = base[base["Order_Number"].isin(packing_list_orders)].copy()`.

  Check each file's imports for a cycle. `report_filters` imports `rules` and `tag_manager` only.

- [ ] **Step 4:** Run `tests/audit/test_04_outputs.py tests/audit/test_01_intake_analysis.py tests/test_packing_lists.py tests/test_stock_export.py tests/test_barcode_generator_widget.py` plus any `tests/test_sku_writeoff*.py`, `tests/test_sequential*.py` and `tests/test_report_filters*.py`. Then commit: `fix(outputs): an order ships whole or not at all (AUDIT-04-6)`.

---

### Task 6: Edit verbs re-derive Stock left (AUDIT-01-1, -3, -4; D1, D6)

**Files:** Modify `gui/actions_handler.py` (`bulk_change_status` `:1493`, the five removal verbs, `_add_product_to_order` `:1262`; delete `_recalculate_order_fulfillment` `:1360`). Test: `tests/audit/test_01_intake_analysis.py`, `tests/test_actions_handler_bulk.py`, `tests/test_actions_handler.py`.

**Interfaces:** Consumes `claim`, `shortfall`, `is_fulfillable`, `with_stock_left`, `FULFILLABLE` and `NOT_FULFILLABLE`.

- [ ] **Step 1:** Remove the markers from `test_add_product_to_fulfillable_order_keeps_it_fulfillable`, `test_bulk_hold_moves_stock_left_like_single_hold` and `test_removing_fulfillable_order_returns_its_stock`. Then add these to `tests/test_actions_handler_bulk.py`. They build their own frame through `run_analysis`, like the audit tests; copy the `window()` / `stock()` / `orders()` helpers from `tests/audit/test_01_intake_analysis.py` into the test module rather than importing them from it:

```python
def test_bulk_mark_fulfillable_skips_what_stock_left_cannot_cover():
    df, *_ = run_analysis(stock([("A", 3)]), orders([("#1", "A", 2), ("#2", "A", 2), ("#3", "A", 2)]), NO_HISTORY)
    mw = window(df)
    ActionsHandler(mw).bulk_change_status(["#1"], False)          # free #1's 2 units: 3 left
    ActionsHandler(mw).bulk_change_status(["#1", "#2", "#3"], True)
    out = mw.analysis_results_df
    assert status(out, "#1") == {"Fulfillable"}
    assert status(out, "#2") == {"Not Fulfillable"} and status(out, "#3") == {"Not Fulfillable"}
    assert final_stock(out, "A") == 1
    mw.results_bridge.raise_toast.assert_called_with(
        "1 order marked fulfillable · 2 skipped: not enough stock", undoable=True
    )


def test_bulk_mark_fulfillable_with_nothing_covered_records_no_undo():
    df, *_ = run_analysis(stock([("A", 1)]), orders([("#1", "A", 1), ("#2", "A", 5)]), NO_HISTORY)
    mw = window(df)
    before = len(mw.undo_manager.operations)
    ActionsHandler(mw).bulk_change_status(["#2"], True)
    assert len(mw.undo_manager.operations) == before
    mw.results_bridge.raise_toast.assert_called_with(
        "No orders marked fulfillable: not enough stock for 1 order", undoable=False
    )


def test_add_product_to_a_held_order_keeps_it_held_and_draws_nothing():
    df, *_ = run_analysis(stock([("A", 5), ("B", 10)]), orders([("#1", "A", 2)]), NO_HISTORY)
    mw = window(df)
    handler = ActionsHandler(mw)
    handler.toggle_fulfillment_status_for_order("#1")             # hold
    stock_df = pd.DataFrame({"SKU": ["A", "B"], "Stock": [5, 10], "Product_Name": ["a", "b"]})
    handler._add_product_to_order(
        {"order_number": "#1", "sku": "B", "product_name": "b", "quantity": 1}, stock_df, {}
    )
    out = mw.analysis_results_df
    assert status(out, "#1") == {"Not Fulfillable"}
    assert final_stock(out, "A") == 5 and final_stock(out, "B") == 10
```

Run them and confirm they fail. The first test's frame order is `#1, #2, #3`: #1 takes 2 of the 3, and #2 and #3 need 2 each with 1 left.

- [ ] **Step 2: `bulk_change_status`.** Keep the existing selection plumbing and the `params` keys (`is_fulfillable`, `affected_indexes`), because an existing test pins them. New body after `selected_indexes` / `orders_count`:

```python
        df = self.mw.analysis_results_df
        in_frame_order = list(dict.fromkeys(df.loc[selected_indexes, "Order_Number"]))
        if is_fulfillable:
            covered, skipped = stock_ledger.claim(df, in_frame_order)
        else:
            covered, skipped = in_frame_order, []
        if not covered:
            if skipped:
                self._results_toast(
                    f"No orders marked fulfillable: not enough stock for {_plural(len(skipped), 'order')}",
                    undoable=False,
                )
            return
        changed = self._order_mask_many(covered)
        changed_indexes = df.index[changed].tolist()
        affected_rows_before = df.loc[changed_indexes].copy()
        status_text = stock_ledger.FULFILLABLE if is_fulfillable else stock_ledger.NOT_FULFILLABLE
        df.loc[changed_indexes, "Order_Fulfillment_Status"] = status_text
        self.mw.analysis_results_df = stock_ledger.with_stock_left(df)
```

Then record the undo with `affected_indexes: changed_indexes`, save, and update the views as today. `_order_mask_many(numbers)` is `order_number_mask(self.mw.analysis_results_df, numbers)`: add it next to `_order_mask`, or call `order_number_mask` directly. The toast:

```python
        count = _plural(len(covered), "order")
        if not is_fulfillable:
            text = f"{count} held"
        elif skipped:
            text = f"{count} marked fulfillable · {len(skipped)} skipped: not enough stock"
        else:
            text = f"{count} marked fulfillable"
        self._results_toast(text, undoable=True)
```

`claim` skips orders that are already fulfillable, so under Mark `covered` counts only the orders that changed. Check `tests/test_actions_handler_bulk.py`'s `mw` fixture: which of `10443` / `10444` start Fulfillable, and does the frame carry `Stock`/`Final_Stock`? Three existing tests call Mark: `test_bulk_change_status_toasts_with_undo`, `test_bulk_change_status_records_undo_with_the_frozen_params` and `test_bulk_change_status_works_for_int_order_numbers`. If an order they mark is already Fulfillable, it now changes nothing: no toast count and no undo record. Rewrite those tests so the orders they mark start as `Not Fulfillable`, keeping what each one asserts, and list each rewrite in the PR body. Hold keeps every selected order, so `"N orders held"` is unchanged.

- [ ] **Step 3: Removal verbs.** In each of `remove_item_from_order`, `remove_entire_order`, `bulk_remove_sku_from_orders`, `bulk_remove_orders_with_sku` and `bulk_delete_orders`, wrap the assignment that writes the reduced frame:
`self.mw.analysis_results_df = stock_ledger.with_stock_left(<reduced frame>.reset_index(drop=True))`.
Nothing else changes.

- [ ] **Step 4: `_add_product_to_order`.** Keep the signature. `live_stock` is no longer read, so say so in the docstring. Replace Steps 3–6 of the method with:

```python
        frame = self.mw.analysis_results_df
        known = frame.loc[frame["SKU"].astype(str) == str(sku), "Stock"].dropna()
        in_file = stock_df[stock_df["SKU"].astype(str).str.strip() == sku] if "SKU" in stock_df else stock_df.iloc[0:0]
        if not known.empty:
            new_row["Stock"] = known.iloc[0]
        elif not in_file.empty and "Stock" in in_file:
            new_row["Stock"] = pd.to_numeric(in_file["Stock"], errors="coerce").fillna(0).sum()
        else:
            new_row["Stock"] = 0
        new_row["Final_Stock"] = new_row["Stock"]  # any non-null value marks it listed; the ledger rewrites it

        was_fulfillable = stock_ledger.is_fulfillable(frame, order_num)
        new_row["Order_Fulfillment_Status"] = (
            stock_ledger.FULFILLABLE if was_fulfillable else stock_ledger.NOT_FULFILLABLE
        )
        frame = pd.concat([frame, pd.DataFrame([new_row])], ignore_index=True)
        now_blocked = was_fulfillable and bool(stock_ledger.shortfall(frame, order_num))
        if now_blocked:
            frame.loc[self._order_mask(order_num, frame), "Order_Fulfillment_Status"] = stock_ledger.NOT_FULFILLABLE
        self.mw.analysis_results_df = stock_ledger.with_stock_left(frame)
```

Toast: append `f" It is now blocked: not enough {sku}."` to the existing text when `now_blocked`. Delete `_recalculate_order_fulfillment`, and run `rg _recalculate_order_fulfillment` to confirm it has no callers left.

- [ ] **Step 5:** Run `tests/audit/test_01_intake_analysis.py tests/test_actions_handler.py tests/test_actions_handler_bulk.py tests/test_pane_actions.py tests/test_results_bulk_popover.py tests/test_results_selection_bar.py tests/test_add_product_dialog.py`. Then commit: `fix(edits): every edit verb re-derives Stock left; bulk Mark only takes what Stock left covers (AUDIT-01-1, -3, -4)`.

---

### Task 7: Undo restores rows in place and re-derives Stock left (AUDIT-01-2, -11)

**Files:** Modify `shopify_tool/undo_manager.py`. Test: `tests/audit/test_01_intake_analysis.py`, `tests/test_undo_manager.py`.

- [ ] **Step 1:** Remove the markers from `test_undo_of_toggle_restores_stock_left` and `test_undo_of_removed_order_restores_row_order`. Then add these to `tests/test_undo_manager.py`, reusing the `window()` helper pattern from the audit test file:

```python
def test_undo_of_hold_on_mixed_order_restores_each_line():
    df = pd.DataFrame({
        "Order_Number": ["#1", "#1", "#2"],
        "SKU": ["A", "GIFT", "A"],
        "Has_SKU": [True, True, True],
        "Quantity": [2, 1, 1],
        "Order_Fulfillment_Status": ["Fulfillable", "Not Fulfillable", "Fulfillable"],
        "Stock": [3, 0, 3],
        "Final_Stock": [2.0, 0.0, 2.0],
    })
    mw = window(df)
    # #1 is mixed, so R1 reads it as blocked. Hold still writes every line.
    ActionsHandler(mw).bulk_change_status(["#1"], False)
    assert mw.undo_manager.undo()[0]
    out = mw.analysis_results_df
    assert out["Order_Fulfillment_Status"].tolist() == ["Fulfillable", "Not Fulfillable", "Fulfillable"]
    assert final_stock(out, "A") == 2    # only #2 draws; the mixed #1 is blocked


def test_undo_without_row_positions_still_appends():
    df = pd.DataFrame({"Order_Number": ["#1", "#2"], "SKU": ["A", "A"], "Quantity": [1, 1],
                       "Order_Fulfillment_Status": ["Fulfillable"] * 2,
                       "Stock": [5, 5], "Final_Stock": [3.0, 3.0]})
    mw = window(df)
    ActionsHandler(mw).remove_entire_order("#1")
    mw.undo_manager.operations[-1].pop("row_positions")           # a record from an older build
    assert mw.undo_manager.undo()[0]
    assert mw.analysis_results_df["Order_Number"].tolist() == ["#2", "#1"]
    assert final_stock(mw.analysis_results_df, "A") == 3


def test_undo_of_bulk_delete_restores_row_order(confirm):
    df = pd.DataFrame({"Order_Number": ["#1", "#2", "#3"], "SKU": ["A"] * 3, "Quantity": [1] * 3,
                       "Order_Fulfillment_Status": ["Fulfillable"] * 3,
                       "Stock": [9] * 3, "Final_Stock": [6.0] * 3})
    mw = window(df)
    ActionsHandler(mw).bulk_delete_orders(["#1", "#3"])
    assert mw.undo_manager.undo()[0]
    assert mw.analysis_results_df["Order_Number"].tolist() == ["#1", "#2", "#3"]
```

(`confirm` is the fixture from the audit file, which monkeypatches `ConfirmDialog.ask`. Copy it into the test module.) Run them and confirm they fail.

- [ ] **Step 2: Record positions.** In `record_operation`, add this to the `operation` dict:
`"row_positions": [int(i) for i in affected_rows_before.index],`

- [ ] **Step 3: Hand positions to the handlers.** In `undo()`, right after `affected_rows_before = pd.DataFrame(affected_rows_serialized)`:
`affected_rows_before.attrs["row_positions"] = operation.get("row_positions")`

- [ ] **Step 4: Two helpers** on `UndoManager`:

```python
    def _reinsert(self, rows: pd.DataFrame) -> None:
        """Put removed rows back where they were (AUDIT-01-11).

        Undo is last-in-first-out, so the frame is exactly as the removal left
        it and the recorded positions still hold. Records from older builds
        have no positions: those rows are appended, as before.
        """
        current = self.main_window.analysis_results_df
        positions = rows.attrs.get("row_positions")
        total = len(current) + len(rows)
        if not positions or len(positions) != len(rows) or max(positions) >= total:
            self.main_window.analysis_results_df = pd.concat([current, rows], ignore_index=True)
            return
        taken = set(positions)
        rest = [p for p in range(total) if p not in taken]
        current = current.copy()
        current.index = rest
        rows = rows.copy()
        rows.index = positions
        self.main_window.analysis_results_df = (
            pd.concat([current, rows]).sort_index().reset_index(drop=True)
        )

    def _restore_statuses_by_position(self, rows: pd.DataFrame) -> bool:
        """Put each line's own status back. False when positions can't be trusted."""
        df = self.main_window.analysis_results_df
        positions = rows.attrs.get("row_positions")
        if not positions or len(positions) != len(rows) or max(positions) >= len(df):
            return False
        here = df["Order_Number"].iloc[positions].astype(str).str.strip().tolist()
        saved = rows["Order_Number"].astype(str).str.strip().tolist()
        if here != saved:
            return False
        df.loc[df.index[positions], "Order_Fulfillment_Status"] = rows["Order_Fulfillment_Status"].values
        return True
```

- [ ] **Step 5: Use them.**
  - `_undo_toggle_status` and `_undo_bulk_change_status`: first `if self._restore_statuses_by_position(affected_rows_before): return True`, then fall through to today's code.
  - The five removal handlers (`_undo_remove_item`, `_undo_remove_order`, `_undo_bulk_remove_sku`, `_undo_bulk_remove_orders_with_sku`, `_undo_bulk_delete_orders`): replace the `pd.concat([...])` assignment with `self._reinsert(affected_rows_before)`.
  - `undo()`: inside `if success:`, first line:
    `self.main_window.analysis_results_df = with_stock_left(self.main_window.analysis_results_df)`
    Import it with `from shopify_tool.stock_ledger import with_stock_left`.

- [ ] **Step 6:** Run `tests/audit/test_01_intake_analysis.py tests/test_undo_manager.py tests/test_actions_handler.py tests/test_actions_handler_bulk.py tests/test_session_restore.py`. `test_undo_history_survives_reopen_for_lot_tracked_stock` (AUDIT-01-12) must **still XFAIL**. Commit: `fix(undo): restore rows in place and re-derive Stock left after every undo (AUDIT-01-2, -11)`.

---

### Task 8: Re-derive on session open (D4), then the full suite

**Files:** Modify `gui/main_window_pyside.py` (`load_existing_session`, around `:942`). Test: `tests/test_session_restore.py`.

- [ ] **Step 1:** Add a test to `tests/test_session_restore.py`, following that file's existing pattern for loading a session. The session's saved frame should have a stale `Final_Stock`, for example `Stock` 5, one fulfillable line of 2, and `Final_Stock` 5. After `load_existing_session`, `Final_Stock` must be 3. If that file's harness can't reach `load_existing_session` without a real server, test the one-line hook through `_load_session_analysis` plus an explicit call, and say so in the PR.
- [ ] **Step 2:** In `load_existing_session`, right after `if self._load_session_analysis(session_path):` and before `self._update_all_views()`:
  `self.analysis_results_df = with_stock_left(self.analysis_results_df)`.
  Import it at the top with `from shopify_tool.stock_ledger import with_stock_left`.
- [ ] **Step 3: Full suite.** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q`. Expected: green, with AUDIT-01-12 and every other bundle's findings still XFAIL. For any **XPASS** from another bundle, follow the Global Constraints rule.
- [ ] **Step 4:** `rg -n 'Final_Stock"\] [+-]=|"Final_Stock"\] = ' shopify_tool gui` should find no hand-written Stock-left arithmetic left outside `stock_ledger.py`. `rules.py:1277` copies a value at run time. That belongs to Bundle 5, so leave it.
- [ ] **Step 5:** Commit: `fix(session): re-derive Stock left when a session opens (D4)`. Then run `graphify update .`.

---

## Spec coverage (self-review)

| spec § | task |
|---|---|
| §3 module | 1 |
| §4.1 readers | 3 |
| §4.2 toggle | 3 |
| §4.3 bulk | 6 |
| §4.4 removals | 6 |
| §4.5 add product | 6 |
| §4.6 undo | 7 |
| §4.7 open | 8 |
| §4.8 outputs | 5 |
| §4.9 stats | 4 (row sets correct after 5) |
| §4.10 intake | 2 |
| §4.11 no order number | 2 |
| §4.12 set import | 2 |
