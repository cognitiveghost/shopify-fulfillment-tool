# Data layer second review — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every open finding from the second data-layer audit: AUDIT-06-1 … 06-7 in
shopify-fulfillment-tool and AUDIT-03-1 in packing-tool. Lot details, order-level columns,
the inventory snapshot, nested sets, run summaries, undo history, expiry parsing and one
packing metric must follow the data as it is now.

**Architecture:** Lot allocation becomes derived, like Stock left (ADR 0014, rule R3).
`analysis.with_lots` re-allocates FIFO from the session's opening lots (`analysis.lot_table`,
rebuilt from the session's `input/inventory.csv` by `core.session_lot_table`).
`core.with_order_fields` recomputes Order_Type, the weights and box, Stock_Alert and lots in
one pass. It runs at the end of the run and at the top of `MainWindow._update_all_views`,
which every edit, undo and open already goes through. The other fixes stay local to their
function.

**Tech Stack:** Python 3.14, pandas 3.0 (string dtype on by default), PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-data-layer-second-review-design.md`. Read it
first. Also read `docs/audit/06-second-pass.md` (findings, evidence),
`docs/adr/0014-lot-allocation-is-derived-not-stored.md`, `docs/adr/0010-stock-left-is-derived-not-tracked.md`,
and in packing-tool `docs/audit/03-second-pass.md`.

**Worktrees and branch** (both on `dr/4-do-second-review-of-data-layer-of-app-re`):
- shopify: `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-4`
- packing: `/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-4`

Tasks 1–9 and 11 run in the shopify worktree, Task 10 in the packing worktree.

## Global Constraints

- Run Python only as `.venv/bin/python` (a symlink to the main checkout's venv). Bare `python` is not on PATH.
- Tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest <path> -q -p no:cacheprovider`.
- Lint: `ruff check . --exclude shared` must pass in both repos.
- Never edit files under `shared/` (synced from packing-tool; nothing in this plan needs it).
- No new dependencies. No `pyproject.toml`.
- Proof tests already exist and are committed: `tests/audit/test_06_second_pass.py` (shopify) and `tests/audit/test_03_second_pass.py` (packing). Each is `xfail(strict=True)`. The task that fixes a finding removes that finding's markers and nothing else. Never edit a proof test's assertions. If one looks wrong, stop and `runner 5 note` it.
- Existing tests that pin the old model are rewritten, not deleted. List each rewrite in the PR body.
- Keep the repo's style: match the comment density and naming of the surrounding code, and cite the finding id (`AUDIT-06-k`) in comments where the old code had a bug.
- Commit after each task with a message like `fix(lots): … (AUDIT-06-1)` ending with the attribution lines:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (use your own model name if different).

## Review Focus

1. **A frame with no lot columns** (memory-mode session, a client whose stock file has no Годност/Партида): `with_lots(df, None)` must leave `Lot_Details` all `None`, and the export takes the SKU-total path. Covered by `test_no_lot_table_clears_lot_details` (Task 1).
2. **A session whose `input/inventory.csv` is missing or unreadable**: `session_lot_table` returns `None`. It must not raise, and the refresh must not stop. Covered by `test_session_lot_table_reads_the_sessions_stock_file` (Task 3).
3. **Minimal frames in GUI tests** (no `SKU`, `Order_Type` or `Quantity` column): `with_order_fields` must return them without raising. Covered by `test_with_order_fields_leaves_a_minimal_frame_alone` (Task 3).
4. **More demand than the lots hold** (an order forced past stock, a rule bonus line): every line's entries still sum to its `Quantity`, via the `"1"` no-lot entry. Covered by `test_units_beyond_the_lots_get_a_no_lot_entry` (Task 1).
5. **Old pickles whose `Lot_Details` holds `datetime.date`**: the tooltip still renders them. The existing `tests/test_pandas_model.py` lot tests use `date` values and must stay green (Task 1).

---

### Task 1: Lot table and derived lots (R3), ISO expiry dates (AUDIT-06-6)

**Files:**
- Modify: `shopify_tool/stock_ledger.py` (add `drawing_rows`)
- Modify: `shopify_tool/analysis.py` (`_normalized_stock`, `lot_table`, `with_lots`, `_iso`; `_clean_and_prepare_data` block; `_merge_results_to_dataframe`; `run_analysis`)
- Modify: `gui/pandas_model.py:_format_lot`
- Create: `tests/test_lot_allocation.py`
- Modify: `tests/audit/test_01_intake_analysis.py` (remove one xfail marker)
- Modify: `docs/audit/01-intake-analysis.md` (AUDIT-01-12 status → `fixed`)

**Interfaces:**
- Produces: `stock_ledger.drawing_rows(df) -> pd.Series[bool]`;
  `analysis.lot_table(stock_df) -> dict[str, list[dict]] | None` (stock frame with internal names);
  `analysis.with_lots(df, lots, mode="multi_first") -> pd.DataFrame` (mutates and returns `df`).
  Each `Lot_Details` entry is `{"expiry": str, "expiry_dt": str | None, "batch": str | None, "qty_allocated": float}`.

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_lot_allocation.py`:

```python
"""R3 (ADR 0014): lot allocation derived from the frame and the session's opening lots."""

import json
from datetime import date

import pandas as pd

from shopify_tool import analysis, stock_ledger

FF, NF = "Fulfillable", "Not Fulfillable"
LOTS = {
    "A": [
        {"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "E", "qty": 3.0},
        {"expiry": "270101", "expiry_dt": date(2027, 1, 1), "batch": "L", "qty": 2.0},
    ],
    "B": [{"expiry": "1", "expiry_dt": None, "batch": None, "qty": 5.0}],
}


def frame(rows):
    """(order, sku, qty, status) rows."""
    return pd.DataFrame(rows, columns=["Order_Number", "SKU", "Quantity", "Order_Fulfillment_Status"])


def shares(lot_details):
    return [(e["batch"], e["qty_allocated"]) for e in lot_details]


def test_drawing_rows_are_sku_lines_of_fulfillable_orders():
    df = frame([("#1", "A", 1, FF), ("#1", "NO_SKU", 1, NF), ("#2", "A", 1, NF)])
    assert stock_ledger.drawing_rows(df).tolist() == [True, False, False]
    assert stock_ledger.drawing_rows(df.drop(columns="Order_Fulfillment_Status")).tolist() == [False] * 3


def test_each_line_owns_its_share_in_row_order():
    out = analysis.with_lots(frame([("#1", "A", 2, FF), ("#1", "A", 2, FF)]), LOTS)
    assert [shares(ld) for ld in out["Lot_Details"]] == [[("E", 2.0)], [("E", 1.0), ("L", 1.0)]]
    assert out["Lot_Details"].iloc[0] is not out["Lot_Details"].iloc[1]


def test_units_beyond_the_lots_get_a_no_lot_entry():
    ld = analysis.with_lots(frame([("#1", "A", 6, FF)]), LOTS)["Lot_Details"].iloc[0]
    assert [(e["expiry"], e["qty_allocated"]) for e in ld] == [("261230", 3.0), ("270101", 2.0), ("1", 1.0)]


def test_held_orders_no_sku_lines_and_unlisted_skus_get_none():
    df = frame([("#1", "A", 1, NF), ("#2", "ZZZ", 1, FF), ("#3", "NO_SKU", 1, FF)])
    assert analysis.with_lots(df, LOTS)["Lot_Details"].isna().all()


def test_orders_draw_in_the_runs_priority_order():
    rows = [("#1", "A", 3, FF), ("#9", "A", 1, FF), ("#9", "B", 1, FF)]
    multi = analysis.with_lots(frame(rows), LOTS)  # the two-line #9 draws first
    assert shares(multi["Lot_Details"].iloc[1]) == [("E", 1.0)]
    assert shares(multi["Lot_Details"].iloc[0]) == [("E", 2.0), ("L", 1.0)]
    fifo = analysis.with_lots(frame(rows), LOTS, mode="fifo")  # #1 first
    assert shares(fifo["Lot_Details"].iloc[0]) == [("E", 3.0)]


def test_the_lot_table_is_not_consumed():
    analysis.with_lots(frame([("#1", "A", 5, FF)]), LOTS)
    assert [lot["qty"] for lot in LOTS["A"]] == [3.0, 2.0]


def test_expiry_dt_is_an_iso_string_so_rows_serialise():
    ld = analysis.with_lots(frame([("#1", "A", 1, FF)]), LOTS)["Lot_Details"].iloc[0]
    assert ld[0]["expiry_dt"] == "2026-12-30"
    json.dumps(ld)


def test_no_lot_table_clears_lot_details():
    df = frame([("#1", "A", 1, FF)])
    df["Lot_Details"] = [[{"qty_allocated": 9}]]
    assert analysis.with_lots(df, None)["Lot_Details"].isna().all()


def test_lot_table_is_none_without_lot_columns():
    assert analysis.lot_table(pd.DataFrame({"SKU": ["A"], "Stock": [1]})) is None


def test_lot_table_normalises_skus_and_stock():
    lots = analysis.lot_table(
        pd.DataFrame({"SKU": [" A ", 5170.0], "Stock": ["3", 2], "Expiry_Date": ["261230", None]})
    )
    assert set(lots) == {"A", "5170"}
    assert lots["A"][0]["qty"] == 3.0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lot_allocation.py -q -p no:cacheprovider`
Expected: every test FAILS with `AttributeError` (`drawing_rows`, `with_lots`, `lot_table` don't exist).

- [ ] **Step 3: Add `drawing_rows` to `shopify_tool/stock_ledger.py`**

Insert after `in_fulfillable_order`:

```python
def drawing_rows(df) -> pd.Series:
    """Row mask: the SKU lines of fulfillable orders, the rows R2 draws from."""
    if df is None or df.empty or "Order_Fulfillment_Status" not in df.columns:
        return pd.Series(False, index=getattr(df, "index", None), dtype=bool)
    return _sku_lines(df) & in_fulfillable_order(df)
```

- [ ] **Step 4: Move the stock normalisation into `_normalized_stock` and add `lot_table`**

In `shopify_tool/analysis.py`:
1. Change the import `from shopify_tool.csv_utils import order_number_sort_key` to
   `from shopify_tool.csv_utils import normalize_sku, order_number_sort_key`, and add `drawing_rows` to the
   `from shopify_tool.stock_ledger import (...)` list.
2. In `_clean_and_prepare_data`, delete the now-redundant local `from .csv_utils import normalize_sku`. The
   order-SKU normalisation there uses the module-level import from item 1.
3. Replace the block from `# Normalize before any dedupe or aggregation:` through `stock_df["Stock"] = stock_numeric.fillna(0)`
   with `stock_df = _normalized_stock(stock_df)`, and add these two functions right above `_build_fifo_lots`:

```python
def _normalized_stock(stock_df: pd.DataFrame) -> pd.DataFrame:
    """Stock rows with normalised SKUs and numeric stock, blank or text read as 0.

    Normalize before any dedupe or aggregation: "501 " and "501.0" are one
    SKU, and deduping first let both through to double every order line
    the merge matched against them (F4). Blank SKUs stay blank so dropna
    still drops them -- normalize_sku(NaN) would return "".
    """
    stock_df = stock_df.copy()
    stock_df["SKU"] = stock_df["SKU"].astype(object)  # float SKUs take strings
    has_sku = stock_df["SKU"].notna()
    stock_df.loc[has_sku, "SKU"] = stock_df.loc[has_sku, "SKU"].map(normalize_sku)

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
    return stock_df


def lot_table(stock_df: pd.DataFrame) -> dict[str, list[dict]] | None:
    """The opening lots per SKU, FIFO-sorted, from a stock frame with internal
    column names. None without lot columns (R3, ADR 0014)."""
    return _build_fifo_lots(_normalized_stock(stock_df))
```

- [ ] **Step 5: Add `with_lots` below `_simulate_stock_allocation`**

```python
def _iso(value) -> str | None:
    return value.isoformat() if isinstance(value, date) else None


def with_lots(df: pd.DataFrame, lots: dict | None, mode: str = "multi_first") -> pd.DataFrame:
    """R3 (ADR 0014): each SKU line of a fulfillable order owns its lots.

    `lots` is lot_table's FIFO list per SKU, or None. Orders draw in the run's
    priority sequence (_prioritize_orders, `mode`), an order's lines in row
    order. Units the lots can't cover get one "no lot" entry (expiry "1"), so
    a line's entries always sum to its Quantity. Held orders, no-SKU lines and
    SKUs without lots get None. Mutates and returns df, like with_stock_left.
    """
    df["Lot_Details"] = pd.Series([None] * len(df), index=df.index, dtype=object)
    if not lots or df.empty:
        return df
    left = {sku: [dict(lot) for lot in lot_list] for sku, lot_list in lots.items()}
    drawing = drawing_rows(df)
    keys = df["Order_Number"].astype(str).str.strip()
    rows_of = keys[drawing].groupby(keys[drawing]).groups
    quantity = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    sequence = _prioritize_orders(df[["Order_Number"]], mode)["Order_Number"]
    for order in (str(o).strip() for o in sequence):
        for idx in rows_of.get(order, []):
            sku_lots = left.get(df.at[idx, "SKU"])
            if sku_lots is None:
                continue
            need = float(quantity[idx])
            entries = []
            for lot in sku_lots:
                if need <= 0:
                    break
                take = min(lot["qty"], need)
                if take > 0:
                    entries.append(
                        {
                            "expiry": lot["expiry"],
                            "expiry_dt": _iso(lot["expiry_dt"]),
                            "batch": lot["batch"],
                            "qty_allocated": take,
                        }
                    )
                    lot["qty"] -= take
                    need -= take
            if need > 0:
                entries.append({"expiry": "1", "expiry_dt": None, "batch": None, "qty_allocated": need})
            df.at[idx, "Lot_Details"] = entries
    return df
```

- [ ] **Step 6: Run the unit tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lot_allocation.py -q -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 7: Make the run use `with_lots`**

In `analysis.py`:
- `_merge_results_to_dataframe`: remove the `lot_allocations` parameter (signature and docstring) and replace the
  whole `# Attach lot allocation details per order/SKU row` block with `final_df["Lot_Details"] = None`.
- `run_analysis`: drop `lot_allocations` from the `_merge_results_to_dataframe(...)` call. Right after that call,
  add `final_df = with_lots(final_df, fifo_lots, mode)`. The simulation's `lot_allocations` return value is left
  unread, on purpose (spec §2.1). Rename the unpacked name to `_lot_allocations`.

- [ ] **Step 8: Tooltip reads both date and string**

In `gui/pandas_model.py:_format_lot`, replace `f"exp {expiry_dt.isoformat()}"` with `f"exp {expiry_dt}"`.
`str(date)` is ISO, so old pickles render the same.

- [ ] **Step 9: AUDIT-06-6 — take the marker off AUDIT-01-12**

In `tests/audit/test_01_intake_analysis.py`, delete the `@pytest.mark.xfail(...)` decorator above
`test_undo_history_survives_reopen_for_lot_tracked_stock`. In `docs/audit/01-intake-analysis.md`, change the
AUDIT-01-12 row's status from `confirmed` to `fixed (AUDIT-06-6)`.

- [ ] **Step 10: Run the affected suites**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lot_allocation.py tests/test_analysis.py tests/audit/test_01_intake_analysis.py tests/test_pandas_model.py tests/test_results_document.py -q -p no:cacheprovider`
Expected: all PASS (`TestFifoLotAllocation` still sees lots on `run_analysis` output, now with float `qty_allocated`).

- [ ] **Step 11: Commit**

```bash
git add shopify_tool/stock_ledger.py shopify_tool/analysis.py gui/pandas_model.py tests/test_lot_allocation.py tests/audit/test_01_intake_analysis.py docs/audit/01-intake-analysis.md
git commit -m "fix(lots): derive lot allocation per line from the opening lots (R3, AUDIT-06-6)"
```

---

### Task 2: Writers read each line's own lots

**Files:**
- Modify: `shopify_tool/stock_export.py:_expand_lot_summary` (≈ lines 79-149)
- Modify: `shopify_tool/packing_lists.py:_expand_lot_rows` (≈ lines 14-63)
- Modify: `tests/audit/test_04_outputs.py` (two tests rewritten)

**Interfaces:**
- Consumes: the per-line `Lot_Details` from Task 1. Every line owns its list, and entries sum to `Quantity`.

- [ ] **Step 1: Rewrite the two tests that pin shared lists**

In `tests/audit/test_04_outputs.py`, give each line its own list with the same totals:

```python
def test_packing_list_lot_rows_keep_the_order_quantity(tmp_path):
    df = frame([("#1", "A", 2, FF), ("#1", "A", 2, FF)])
    df["Lot_Details"] = [  # one list per line (ADR 0014)
        [{"qty_allocated": 2, "expiry": "2027-01", "batch": "L1"}],
        [{"qty_allocated": 1, "expiry": "2027-01", "batch": "L1"},
         {"qty_allocated": 1, "expiry": "2027-06", "batch": "L2"}],
    ]
    create_packing_list(df, str(tmp_path / "p.xlsx"))
    assert xlsx_lines(tmp_path / "p.xlsx") == {("#1", "A"): 4}


def test_stock_export_lot_rows_sum_to_the_allocation(tmp_path):
    df = frame([("#1", "A", 2, FF), ("#1", "A", 2, FF)])
    df["Lot_Details"] = [
        [{"qty_allocated": 2, "expiry": "2027-01", "batch": "L1"}],
        [{"qty_allocated": 1, "expiry": "2027-01", "batch": "L1"},
         {"qty_allocated": 1, "expiry": "2027-06", "batch": "L2"}],
    ]
    create_stock_export(df, str(tmp_path / "e.xls"))
    e = pd.read_excel(tmp_path / "e.xls", dtype={"Артикул": str})
    assert e["Брой"].tolist() == [3, 1]
```

- [ ] **Step 2: Run them. They fail against the dedupe**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/audit/test_04_outputs.py -q -p no:cacheprovider -k "lot_rows"`
Expected: the packing-list test FAILS (the second line is skipped as a seen (order, SKU)). The export test may already
pass, because the lists are distinct objects. Both must pass after Step 3.

- [ ] **Step 3: Remove both dedupes**

`stock_export._expand_lot_summary`: delete `seen_allocations`, the long comment above it, and the
`alloc_id` / `continue` lines. Put in its place the one-line comment
`# Each line owns its lots (ADR 0014): sum every row, never dedupe.`. The loop body then adds every entry of every
non-empty list, and `Quantity` to `no_lot_skus` otherwise.

`packing_lists._expand_lot_rows`: delete `seen_order_sku`, its comment, and the `order_key` / `continue` lines. Put the
same one-line comment in their place. Update the docstring sentence about duplicate rows accordingly.

- [ ] **Step 4: Run the writer suites**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/audit/test_04_outputs.py tests/test_stock_export.py tests/test_packing_lists.py tests/test_packing_list_order.py -q -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/stock_export.py shopify_tool/packing_lists.py tests/audit/test_04_outputs.py
git commit -m "fix(outputs): read each line's own lots, drop the shared-list dedupe (AUDIT-06-1)"
```

---

### Task 3: `session_lot_table`, `with_order_fields` and the run (AUDIT-06-1, AUDIT-06-2)

**Files:**
- Modify: `shopify_tool/core.py` (new `session_lot_table`, `with_order_fields`; end of `_run_analysis_and_rules`; import `AUTO_DELIMITER`)
- Test: `tests/test_lot_allocation.py` (append)
- Modify: `tests/audit/test_06_second_pass.py` (remove the AUDIT-06-1 and AUDIT-06-2 markers only)

**Interfaces:**
- Consumes: `analysis.lot_table`, `analysis.with_lots`, `analysis.stock_with_internal_columns`, `core._add_stock_alert`, `core._get_sku_dtype_dict`, `weight_calculator.enrich_dataframe_with_weights`.
- Produces: `core.session_lot_table(session_path, config) -> dict | None`; `core.with_order_fields(df, config, lots) -> pd.DataFrame`.

- [ ] **Step 1: Append the seam tests to `tests/test_lot_allocation.py`**

```python
from shopify_tool import core  # add to the imports at the top

CONFIG = {"column_mappings": {"stock": {"Артикул": "SKU", "Наличност": "Stock", "Име": "Product_Name"}}}


def test_session_lot_table_reads_the_sessions_stock_file(tmp_path):
    (tmp_path / "input").mkdir()
    (tmp_path / "input" / "inventory.csv").write_text(
        "Артикул,Име,Годност,Партида,Наличност\nA,Alpha,270101,LATE,2\nA,Alpha,261230,EARLY,3\n",
        encoding="utf-8",
    )
    lots = core.session_lot_table(str(tmp_path), CONFIG)
    assert [(lot["batch"], lot["qty"]) for lot in lots["A"]] == [("EARLY", 3.0), ("LATE", 2.0)]
    assert core.session_lot_table(str(tmp_path / "missing"), CONFIG) is None
    assert core.session_lot_table(None, CONFIG) is None
    (tmp_path / "input" / "inventory.csv").write_text("not,a\nstock,file\n", encoding="utf-8")
    assert core.session_lot_table(str(tmp_path), CONFIG) is None  # unreadable: logged, not raised


def test_with_order_fields_leaves_a_minimal_frame_alone():
    df = pd.DataFrame({"Order_Number": ["1"], "System_note": [""]})
    assert core.with_order_fields(df, {}, None).columns.tolist() == ["Order_Number", "System_note"]
    assert core.with_order_fields(None, {}, None) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lot_allocation.py -q -p no:cacheprovider -k "session_lot_table or minimal"`
Expected: FAIL with `AttributeError: module 'shopify_tool.core' has no attribute ...`.

- [ ] **Step 3: Implement both functions in `shopify_tool/core.py`**

Change `from .csv_utils import normalize_sku, resolve_delimiter` to
`from .csv_utils import AUTO_DELIMITER, normalize_sku, resolve_delimiter`. Add below `_add_stock_alert`:

```python
def session_lot_table(session_path, config) -> dict | None:
    """The session's opening lots (R3, ADR 0014), from its own input/inventory.csv.

    None when the session has no stock file (memory mode, or none copied),
    the file has no lot columns, or it can't be read: lines then export
    without lots, with the right quantities.
    """
    if not session_path:
        return None
    path = Path(session_path) / "input" / "inventory.csv"
    if not path.exists():
        return None
    config = config or {}
    mappings = config.get("column_mappings") or {}
    try:
        setting = (config.get("settings") or {}).get("stock_csv_delimiter", AUTO_DELIMITER)
        raw = pd.read_csv(
            path,
            delimiter=resolve_delimiter(str(path), setting, "stock"),
            encoding="utf-8-sig",
            dtype=_get_sku_dtype_dict(mappings, "stock"),
        )
        return analysis.lot_table(analysis.stock_with_internal_columns(raw, mappings))
    except Exception:
        logger.exception(f"Could not read this session's lots from {path}")
        return None


def with_order_fields(df, config, lots):
    """Recompute every order-level column a run derives, from the frame as it is now.

    Order_Type, the weight and box columns, Stock_Alert and Lot_Details were
    computed once at run time, and add product, remove item, holds, rule bonus
    lines and undo left them stale (AUDIT-06-1, -2). Runs at the end of the
    run and on every MainWindow refresh (spec 2026-09-28 §3).
    """
    if df is None or df.empty or "Order_Number" not in df.columns:
        return df
    config = config or {}
    if "Order_Type" in df.columns:
        keys = df["Order_Number"].astype(str).str.strip()
        lines = df.groupby(keys)["Order_Number"].transform("size")
        df["Order_Type"] = np.where(lines > 1, "Multi", "Single")
    weight_config = config.get("weight_config") or {}
    if weight_config.get("products") and "SKU" in df.columns:
        from .weight_calculator import enrich_dataframe_with_weights

        df = enrich_dataframe_with_weights(df, weight_config)
    _add_stock_alert(df, config)
    if {"SKU", "Quantity", "Order_Fulfillment_Status"} <= set(df.columns):
        df = analysis.with_lots(df, lots, config.get("analysis_mode", "multi_first"))
    return df
```

Order_Type counts every line, NO_SKU lines included, as the run does (spec D9).

- [ ] **Step 4: Call it at the end of the run**

In `core._run_analysis_and_rules`, after the `if rules:` block and before the `return`, add:

```python
    # Order-level columns and lots follow the frame as the rules left it:
    # bonus lines get their own lots and the right Order_Type (ADR 0014).
    lots = analysis.lot_table(
        analysis.stock_with_internal_columns(stock_df, config.get("column_mappings", {}))
    )
    final_df = with_order_fields(final_df, config, lots)
```

- [ ] **Step 5: Take the markers off AUDIT-06-1 and AUDIT-06-2**

In `tests/audit/test_06_second_pass.py`, delete the `@pytest.mark.xfail(...)` line above each of these seven tests:
`test_an_added_line_exports_its_own_sku_and_quantity`, `test_removing_one_of_two_same_sku_lines_exports_the_other_only`,
`test_an_order_made_fulfillable_after_the_run_exports_with_its_lots`, `test_packing_list_prints_each_lines_own_quantity`,
`test_order_type_follows_added_and_removed_lines`, `test_box_and_weight_follow_an_added_line`,
`test_stock_alert_follows_a_hold`.

- [ ] **Step 6: Run**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lot_allocation.py tests/audit/test_06_second_pass.py tests/test_rule_settle.py tests/audit/test_03_rule_engine.py tests/test_core.py tests/test_weight_calculator.py -q -p no:cacheprovider`
Expected: all PASS. The remaining AUDIT-06-3/-4/-5/-7 tests are still `xfailed`. If `tests/test_weight_calculator.py`
doesn't exist, drop it from the command.

- [ ] **Step 7: Commit**

```bash
git add shopify_tool/core.py tests/test_lot_allocation.py tests/audit/test_06_second_pass.py
git commit -m "fix(core): re-derive order-level columns and lots after the run (AUDIT-06-1, AUDIT-06-2)"
```

---

### Task 4: GUI refresh derives from the session's lots

**Files:**
- Modify: `gui/main_window_pyside.py` (`__init__` ≈ line 116, `_reset_session_state` ≈ 962, `load_existing_session` ≈ 1016, `_update_all_views` ≈ 1048)
- Modify: `gui/actions_handler.py:on_analysis_complete` (≈ line 214)
- Test: `tests/test_results_screen.py` (append)

**Interfaces:**
- Consumes: `core.session_lot_table`, `core.with_order_fields` (Task 3).
- Produces: `MainWindow.lot_table: dict | None`.

- [ ] **Step 1: Write the failing GUI test**

Append to `tests/test_results_screen.py` (it has the `main_window` fixture; add `from datetime import date` to its imports):

```python
def test_update_all_views_derives_lots_from_the_session_table(main_window):
    main_window.analysis_results_df = pd.DataFrame([{
        "Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable", "Shipping_Provider": "DHL",
        "SKU": "AAA", "Quantity": 2, "System_note": "", "Internal_Tags": "[]", "Lot_Details": None,
    }])
    main_window.lot_table = {
        "AAA": [{"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty": 5.0}]
    }
    main_window._update_all_views()
    assert main_window.analysis_results_df["Lot_Details"].iloc[0] == [
        {"expiry": "261230", "expiry_dt": "2026-12-30", "batch": "B1", "qty_allocated": 2.0}
    ]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_screen.py -q -p no:cacheprovider -k derives_lots`
Expected: FAIL (`Lot_Details` stays `None`).

- [ ] **Step 3: Wire `lot_table`**

`gui/main_window_pyside.py`:
- `__init__`: next to `self.analysis_results_df = None`, add `self.lot_table = None`.
- `_reset_session_state`: after `self.analysis_stats = None`, add `self.lot_table = None`.
- `load_existing_session`: inside `if self._load_session_analysis(session_path):`, before the `with_stock_left` line, add
  `self.lot_table = core.session_lot_table(session_path, self.active_profile_config)`.
- `_update_all_views`: at the top of the `if self.analysis_results_df is not None and not self.analysis_results_df.empty:`
  branch, before the stats `try`, add:

```python
            # Lots and order-level columns follow every edit, undo and open
            # (ADR 0014). A failure must not stop the refresh.
            try:
                self.analysis_results_df = core.with_order_fields(
                    self.analysis_results_df,
                    self.active_profile_config,
                    getattr(self, "lot_table", None),
                )
            except Exception:
                logger.exception("Failed to re-derive order fields")
```

Also add one sentence to the `_update_all_views` docstring: "Lots and order-level columns are re-derived first
(core.with_order_fields, ADR 0014)."

`gui/actions_handler.py:on_analysis_complete`: right after `self.mw.analysis_results_df = df`, add

```python
            # The run's own stock file is now the session's; later refreshes
            # derive lots from it (ADR 0014).
            self.mw.lot_table = core.session_lot_table(
                self.mw.session_path, self.mw.active_profile_config
            )
```

(`core` is already imported there.)

- [ ] **Step 4: Run the GUI suites**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_screen.py tests/test_actions_handler_bulk.py tests/test_shell.py tests/audit/test_05_sessions_sweep.py -q -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/main_window_pyside.py gui/actions_handler.py tests/test_results_screen.py
git commit -m "fix(gui): refresh re-derives lots and order fields from the session's stock (AUDIT-06-1)"
```

---

### Task 5: Summary_Present and stats after rules, Summary_Missing removed (AUDIT-06-5)

**Files:**
- Modify: `shopify_tool/analysis.py` (`_generate_summary_reports` → `summary_present`; `run_analysis` return)
- Modify: `shopify_tool/core.py` (`_run_analysis_and_rules`, `_save_results_and_reports`, `run_full_analysis`)
- Modify: `tests/test_analysis.py:41` (unpacking) and any other test that unpacks by name (see Step 5)
- Modify: `tests/audit/test_06_second_pass.py` (remove the two AUDIT-06-5 markers)

**Interfaces:**
- Produces: `analysis.summary_present(final_df) -> pd.DataFrame` with columns `["Name", "SKU", "Total Quantity"]`;
  `analysis.run_analysis(...) -> (final_df, stats)`; `core._run_analysis_and_rules(...) -> (final_df, summary_present_df, stats)`.

- [ ] **Step 1: Confirm the proof tests fail now**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/audit/test_06_second_pass.py -q -p no:cacheprovider --runxfail -k "summary"`
Expected: 2 FAIL (`Summary_Missing` present; `too many values to unpack`).

- [ ] **Step 2: Replace `_generate_summary_reports` with `summary_present`**

```python
def summary_present(final_df: pd.DataFrame) -> pd.DataFrame:
    """Units per SKU that the fulfillable orders ship: the Summary_Present sheet.

    Columns: Name, SKU, Total Quantity. Computed after rules (AUDIT-06-5).
    """
    from shopify_tool.report_filters import fulfillable_only  # local: avoids an import cycle

    present_df = fulfillable_only(final_df)
    if "Product_Name" in present_df.columns:
        summary = present_df.groupby(["SKU", "Product_Name"], as_index=False)["Quantity"].sum()
        summary = summary.rename(columns={"Product_Name": "Name", "Quantity": "Total Quantity"})
    else:
        summary = present_df.groupby(["SKU"], as_index=False)["Quantity"].sum()
        summary["Name"] = "N/A"
        summary = summary.rename(columns={"Quantity": "Total Quantity"})
    return summary[["Name", "SKU", "Total Quantity"]]
```

Delete `_generate_summary_reports` entirely (the Summary_Missing logic goes with it).

- [ ] **Step 3: `run_analysis` returns `(final_df, stats)`**

Delete the "Phase 7: Generate summary reports" lines, change the return to `return final_df, stats`, and update its
docstring's Returns section and any log line that mentions the summaries.

- [ ] **Step 4: Core computes the summary and stats after rules; drop the sheet**

`core._run_analysis_and_rules`:
- `final_df, stats = analysis.run_analysis(...)`.
- After the `with_order_fields` line added in Task 3, add:
  `summary_present_df = analysis.summary_present(final_df)` and `stats = analysis.recalculate_statistics(final_df)`.
- `return final_df, summary_present_df, stats`. Update the docstring's Returns line.

`core._save_results_and_reports`: remove the `summary_missing_df` parameter (signature and docstring) and the
`summary_missing_df.to_excel(writer, sheet_name="Summary_Missing", index=False)` line.

`core.run_full_analysis`: unpack `final_df, summary_present_df, stats = (_run_analysis_and_rules(...))` and remove
`summary_missing_df,` from the `_save_results_and_reports(...)` call.

- [ ] **Step 5: Fix tests that unpack by name**

Run: `grep -rn "run_analysis(\|_run(" tests | grep -v "\*_\|\[0\]"`. For each hit that unpacks four names from
`run_analysis` (known: `tests/test_analysis.py:41`, `final_df, _present, _missing, _stats = _run(orders, stock)`), change
it to two names (`final_df, _stats = ...`). Do the same for any three-name unpack of `_run_analysis_and_rules`
(`grep -rn "_run_analysis_and_rules" tests`). Those found so far use `[0]` and need nothing. Then remove the two AUDIT-06-5
markers in `tests/audit/test_06_second_pass.py`.

- [ ] **Step 6: Run**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_analysis.py tests/test_core.py tests/test_rule_settle.py tests/audit -q -p no:cacheprovider`
Expected: all PASS. AUDIT-06-3/-4/-7 are still `xfailed`.

- [ ] **Step 7: Commit**

```bash
git add shopify_tool/analysis.py shopify_tool/core.py tests
git commit -m "fix(run): Summary_Present and stats after rules; drop Summary_Missing (AUDIT-06-5)"
```

---

### Task 6: Inventory snapshot keys by normalised SKU (AUDIT-06-3)

**Files:**
- Modify: `shopify_tool/core.py:build_inventory_snapshot`, `inventory_total_units`
- Modify: `tests/audit/test_06_second_pass.py` (remove one marker)

- [ ] **Step 1: Confirm red**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/audit/test_06_second_pass.py -q -p no:cacheprovider --runxfail -k snapshot`
Expected: FAIL (`{'S-EX06-2MD ': 5.0, ...}`).

- [ ] **Step 2: Group by the normalised SKU**

Add a helper above `build_inventory_snapshot`:

```python
def _stock_per_sku(stock_df: pd.DataFrame) -> pd.Series:
    """Stock summed per normalised SKU ("X " and "X" are one SKU, AUDIT-06-3)."""
    listed = stock_df[stock_df["SKU"].notna()]
    stock = pd.to_numeric(listed["Stock"], errors="coerce")
    return stock.groupby(listed["SKU"].map(normalize_sku)).sum(min_count=1).dropna()
```

In `build_inventory_snapshot`, replace the two lines that build `stock` and the `stock.groupby(stock_df["SKU"])...` chain with:

```python
        snapshot = (
            _stock_per_sku(stock_df)
            .apply(lambda x: max(0.0, float(x)))
            .to_dict()
        )
```

In `inventory_total_units`, replace the two computing lines with `per_sku = _stock_per_sku(stock_df)`
(keep `return float(per_sku.clip(lower=0).sum())`).

- [ ] **Step 3: Remove the AUDIT-06-3 marker and run**

Delete the xfail line above `test_inventory_snapshot_keys_are_normalised_skus`.
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/audit tests/test_core.py tests/test_inventory_memory*.py -q -p no:cacheprovider`
(drop the glob if no such file matches). Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add shopify_tool/core.py tests/audit/test_06_second_pass.py
git commit -m "fix(memory): inventory snapshot keys by normalised SKU (AUDIT-06-3)"
```

---

### Task 7: Nested sets expand, except a set that lists itself (AUDIT-06-4)

**Files:**
- Modify: `shopify_tool/set_decoder.py:decode_sets_in_orders`
- Modify: `tests/audit/test_06_second_pass.py` (remove two markers)

- [ ] **Step 1: Confirm red**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/audit/test_06_second_pass.py -q -p no:cacheprovider --runxfail -k "set"`
Expected: `test_a_nested_set_expands_to_its_inner_components` and `test_a_set_cycle_stops_instead_of_recursing` FAIL.
`test_a_set_that_lists_itself_is_not_expanded_again` PASSES, and must keep passing.

- [ ] **Step 2: Add the recursive helper**

Add at module level in `set_decoder.py`, above `decode_sets_in_orders`:

```python
def _lists_itself(sku, set_decoders) -> bool:
    return any(c.get("sku") == sku for c in set_decoders.get(sku) or [])


def _components(sku, quantity, set_decoders, path) -> list[tuple[str, Any]]:
    """(component SKU, quantity) pairs for `quantity` of set `sku`, nested sets expanded.

    A component that is itself a set is expanded, unless it lists itself
    (a product sold with extras, HERBAR NECTAR-30: its parent sets list the
    extras themselves) or it is already on `path` (a cycle). AUDIT-06-4.
    """
    out = []
    for component in set_decoders[sku]:
        component_sku = component.get("sku")
        component_qty = component.get("quantity")
        if not component_sku:
            logger.warning(f"Component in set '{sku}' has no SKU, skipping component")
            continue
        if not component_qty or component_qty <= 0:
            logger.warning(
                f"Component '{component_sku}' in set '{sku}' has invalid quantity: {component_qty}, skipping"
            )
            continue
        total = quantity * component_qty
        if component_sku in path and component_sku != sku:
            logger.warning(f"Set '{sku}' reaches '{component_sku}' again (a cycle); not expanding it")
        nested = (
            component_sku in set_decoders
            and component_sku not in path
            and not _lists_itself(component_sku, set_decoders)
        )
        inner = _components(component_sku, total, set_decoders, path | {component_sku}) if nested else []
        out.extend(inner or [(component_sku, total)])
    return out
```

- [ ] **Step 3: Use it in `decode_sets_in_orders`**

Replace the loop `for component in components:` … `valid_components_added += 1` with:

```python
            for component_sku, component_total in _components(sku, quantity, set_decoders, {sku}):
                new_row = row.copy()
                new_row["SKU"] = component_sku
                new_row["Quantity"] = component_total
                new_row["Original_SKU"] = sku
                new_row["Original_Quantity"] = quantity
                new_row["Is_Set_Component"] = True
                expanded_rows.append(new_row)
                valid_components_added += 1
```

Keep the `if not components:` guard above it and the `if valid_components_added == 0:` fallback below it, unchanged.
Update the function docstring with one line: "A component that is itself a set is expanded too, unless it lists
itself or would loop (AUDIT-06-4)."

- [ ] **Step 4: Remove the two markers and run**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/audit/test_06_second_pass.py tests/test_set_decoder.py tests/test_analysis.py -q -p no:cacheprovider`
Expected: PASS (drop `tests/test_set_decoder.py` if absent; `grep -rln decode_sets_in_orders tests` lists the owners).

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/set_decoder.py tests/audit/test_06_second_pass.py
git commit -m "fix(sets): expand nested sets, not self-listing ones, guard cycles (AUDIT-06-4)"
```

---

### Task 8: Expiry formats (AUDIT-06-7)

**Files:**
- Modify: `shopify_tool/analysis.py:_parse_expiry_date`
- Modify: `tests/test_analysis.py::TestParseExpiryDate::test_unparseable_value_returns_none_and_logs_warning` (rewrite)
- Modify: `tests/audit/test_06_second_pass.py` (remove one marker)

- [ ] **Step 1: Rewrite the test that pins "2805" as unparsable**

"2805" is YYMM (May 2028) and parses after this task. In `test_unparseable_value_returns_none_and_logs_warning`,
use `"2899"` instead (invalid as MMYY and as YYMM) and update its comment to `# month 28 (MMYY) and 99 (YYMM) both invalid`.
Add one test next to `test_mmyy_4_digit_defaults_to_day_1`:

```python
    def test_yymm_4_digit_when_mmyy_is_invalid(self):
        assert analysis._parse_expiry_date("2805") == date(2028, 5, 1)

    def test_day_zero_6_digit_is_the_month(self):
        assert analysis._parse_expiry_date("261200") == date(2026, 12, 1)
```

- [ ] **Step 2: Run to confirm red**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_analysis.py -q -p no:cacheprovider -k "yymm or day_zero"`
Expected: 2 FAIL.

- [ ] **Step 3: Change the candidate lists**

In `_parse_expiry_date`:

```python
    if len(s) == 6 and s[4:6] == "00":
        # Day "00" means the month itself (WATERDROP "261200"); DDMMYY would
        # read it as 2000-12-26 and FIFO would draw it first (AUDIT-06-7).
        candidate_specs = [("YYMM00", s[0:2], s[2:4], "01")]
    elif len(s) == 6:
        candidate_specs = [
            ("YYMMDD", s[0:2], s[2:4], s[4:6]),
            ("DDMMYY", s[4:6], s[2:4], s[0:2]),
        ]
    elif len(s) == 8:
        candidate_specs = [("YYYYMMDD", s[0:4], s[4:6], s[6:8])]
    elif len(s) == 4:
        candidate_specs = [
            ("MMYY", s[2:4], s[0:2], "01"),
            ("YYMM", s[0:2], s[2:4], "01"),  # ALMADERM "2805" (AUDIT-06-7)
        ]
    else:
        candidate_specs = []
```

Update the docstring's list: "6-digit: YYMM with day 00 → the 1st; else YYMMDD, then DDMMYY" and
"4-digit: MMYY, then YYMM (day defaults to 1)".

- [ ] **Step 4: Remove the AUDIT-06-7 marker and run**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_analysis.py tests/audit/test_06_second_pass.py -q -p no:cacheprovider`
Expected: all PASS. The ambiguity test (`"261230"`) is unchanged, and `"0101"`-style values log as ambiguous and keep MMYY.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/analysis.py tests/test_analysis.py tests/audit/test_06_second_pass.py
git commit -m "fix(lots): read YYMM and day-00 expiries by their month (AUDIT-06-7)"
```

---

### Task 9: Docs, glossary, graph

**Files:**
- Modify: `docs/audit/06-second-pass.md` (status column → `fixed` for AUDIT-06-1 … 06-7)
- Modify: `CONTEXT.md` (glossary entry)

- [ ] **Step 1: Mark the findings fixed**

In `docs/audit/06-second-pass.md` §2, change every `open` in the status column to `fixed`.

- [ ] **Step 2: Add the glossary entry**

In `CONTEXT.md`, next to the existing stock/ledger terms (search for "Stock left"; if absent, put it at the end of the
glossary), add:

```markdown
**Lot allocation** — which lots (expiry, batch) each SKU line of a fulfillable
order ships from. Derived, never stored: `analysis.with_lots` re-allocates FIFO
from the session's opening lots (its `input/inventory.csv`) after every change,
and every line owns its own list (ADR 0014). Not **Stock left**, which is the
per-SKU total after the draws.
```

- [ ] **Step 3: Refresh the graph and commit**

```bash
graphify update .
git add docs/audit/06-second-pass.md CONTEXT.md
git commit -m "docs: audit 06 findings fixed; Lot allocation in the glossary"
```

(`graphify-out/` is updated by the post-commit hook as well. Commit whatever it changes if git shows it as modified.)

---

### Task 10 (packing-tool worktree): Avg time per item (AUDIT-03-1)

**Files:**
- Modify: `packing_tool/packer_logic.py:compute_order_timing_metrics` (≈ lines 84-146) and the `generate_session_summary` docstring example
- Modify: `tests/audit/test_03_second_pass.py` (remove the marker)
- Modify: `docs/audit/03-second-pass.md` (status → `fixed`)

Work in `/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-4`.

- [ ] **Step 1: Confirm red**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/audit/test_03_second_pass.py -q -p no:cacheprovider --runxfail`
Expected: FAIL, `assert 17.5 == 10.0`.

- [ ] **Step 2: Fix the metric**

Replace the block from `all_items = []` through the `avg_time_per_item = ...` line with:

```python
    # Time per unit packed: the timed orders' seconds over their units
    # (AUDIT-03-1). Averaging each scan's offset from its order's start
    # reported about half an order's time instead.
    timed = [o for o in orders_with_timing if o.get('duration_seconds')]
    units = sum(o.get('items_count', 0) for o in timed)
    avg_time_per_item = round(sum(o['duration_seconds'] for o in timed) / units, 1) if units else 0

    all_items = []
    for order in orders_with_timing:
        all_items.extend(order.get('items', []))
```

`all_items` is still needed by `total_manual_confirms`. In the function docstring, change "items (with
time_from_order_start_seconds)" to "items_count". In `generate_session_summary`'s example, leave the numbers as they are
(they're illustrative).

- [ ] **Step 3: Remove the marker, run, commit**

Delete the xfail line in `tests/audit/test_03_second_pass.py`. In `docs/audit/03-second-pass.md` §2, set the status to `fixed`.

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -p no:cacheprovider` (whole packing suite) and
`ruff check . --exclude shared`. Expected: all PASS.

```bash
git add packing_tool/packer_logic.py tests/audit/test_03_second_pass.py docs/audit/03-second-pass.md
git commit -m "fix(metrics): avg time per item is order time over units (AUDIT-03-1)"
graphify update .
```

---

### Task 11: Production replay and gates (shopify)

**Files:** none in the repo. The replay script is throwaway: write it under `$CLAUDE_JOB_DIR/tmp/`, never under the repo.

- [ ] **Step 1: Replay every production session**

Write `$CLAUDE_JOB_DIR/tmp/replay.py` and run it with `PYTHONPATH=. .venv/bin/python $CLAUDE_JOB_DIR/tmp/replay.py 2>/dev/null`:

```python
import glob, json, os
import pandas as pd
from shopify_tool import core
from shopify_tool.report_filters import fulfillable_only
from shopify_tool.stock_export import QTY_COL, _expand_lot_summary

root = os.path.expanduser("~/Desktop/production info/")
clients = {"alma/": "CLIENT_ALMADERM", "herbar/": "CLIENT_HERBAR", "wt/": "CLIENT_WATERDROP"}
bad = 0
for p in sorted(glob.glob(root + "**/analysis/current_state.pkl", recursive=True)):
    session = os.path.dirname(os.path.dirname(p))
    name = session.replace(root, "")
    client = next((c for k, c in clients.items() if k in name), None)
    config = json.load(open(f"{root}{client}/shopify_config.json")) if client else {
        "column_mappings": {"stock": {"Артикул": "SKU", "Наличност": "Stock", "Име": "Product_Name"}}}
    df = core.with_order_fields(pd.read_pickle(p), config, core.session_lot_table(session, config))
    ful = fulfillable_only(df)
    export = _expand_lot_summary(ful)
    got = int(export[QTY_COL].sum()) if len(export) else 0
    want = int(pd.to_numeric(ful["Quantity"]).sum())
    bad += got != want
    print(f"{name}: export {got} / fulfillable {want}")
    if name.startswith("2026-09-28_1"):
        print(export[["Артикул", QTY_COL]].to_string())
print("mismatches:", bad)
```

Expected: `mismatches: 0` over 40 sessions. The REVE `2026-09-28_1` block shows `01PJ0001L 1` and `01PJ0001S 1`.
Put the summary line and the REVE block in the PR body. (Planning measured the same: 40/40 equal.)

- [ ] **Step 2: Full gates**

Run in the shopify worktree:
```bash
ruff check . --exclude shared
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -p no:cacheprovider
```
Expected: ruff clean; the whole suite passes with **0 xfailed** from audits 01 and 06. The baseline before this plan was
2041 passed, 1 xfailed (AUDIT-01-12).

- [ ] **Step 3: Timing check**

Time one refresh on the largest production frame (ALMADERM 2026-07-01_2, 366 rows):
`PYTHONPATH=. .venv/bin/python -c "import time,json,pandas as pd;from shopify_tool import core;r='$HOME/Desktop/production info/';c=json.load(open(r+'CLIENT_ALMADERM/shopify_config.json'));s=r+'alma/2026-07-01_2';df=pd.read_pickle(s+'/analysis/current_state.pkl');l=core.session_lot_table(s,c);t=time.perf_counter();core.with_order_fields(df,c,l);print(round((time.perf_counter()-t)*1000),'ms')"`
Record the number in the PR body. Anything over 250 ms is worth a `runner 5 note`. It runs on every edit.

- [ ] **Step 4: Push**

```bash
git push
```

(and `git push` in the packing worktree after Task 10.)

---

## PR notes (for Stage C)

Two PRs, one per repo, both from `dr/4-do-second-review-of-data-layer-of-app-re`. The shopify PR body lists:
- the findings fixed (AUDIT-06-1 … 06-7) with one line each;
- the rewritten tests: `tests/audit/test_04_outputs.py` (two lot tests, per-line lists), `tests/test_analysis.py`
  (`test_unparseable_value_returns_none_and_logs_warning` now uses "2899"; any unpacking changes from Task 5);
- the replay result and the timing from Task 11;
- **Operational note:** REVE 2026-09-28_1's stock export (`all_reve_2026-09-28_1417.xls`) is wrong. After merge, reopen
  that session and generate its stock export and packing list again.
