# ERP Export Quantity Rounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement
> this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> (This plan's runner declines `subagent-driven-development` — stay in-session.)

**Goal:** Stop the ERP stock export from truncating fractional quantities to zero, by rounding
half-up at the single point every export path already funnels through.

**Architecture:** All five export builders end at `_finalize_export_df()` in
`shopify_tool/stock_export.py` — including the catch-all guard at `stock_export.py:275` that
exists precisely to catch paths which skipped it. Put the quantity coercion there and the four
scattered `.astype(int)` casts become deletable. Net negative diff, and the bug class dies on
paths nobody reported.

**Tech Stack:** pandas, pytest, xlwt (`.xls` writer).

**Spec:** None — this is a bounded bug fix. The problem statement, the rejected alternatives,
and the rounding-direction decision are recorded in the "Background" section below, which is
the whole of what a spec would have carried.

## Global Constraints

- Python, PySide6 desktop app; Windows-only in production, developed on Linux.
- Gate before finishing: `QT_QPA_PLATFORM=offscreen python -m pytest` and
  `ruff check . --exclude shared` (use `.venv/bin/python`; bare `python` is not on PATH).
- Never hand-edit anything under `shared/` — it is synced from `../packing-tool`.
- The ERP column layout `["Артикул", "", "Мярка", "Брой", "Годност", "Партида"]` is positional
  and MUST NOT be reordered or renamed.
- `_finalize_export_df()` must stay idempotent — `create_stock_export()` calls it twice on some
  paths.

---

## Background

### The bug

`Брой` (quantity) is measured in `Мярка = "брой"` — pieces. The ERP cannot represent a
fraction, so the export has to convert to `int`. Four sites do that with `.astype(int)`, which
**truncates**:

| source | `.astype(int)` | correct |
|---|---|---|
| 0.5 (one order, 0.5/order mapping) | **0 — material vanishes** | 1 |
| 1.5 (three orders, 0.5/order) | 1 | 2 |
| 2.5 | 2 | 3 |

Write-off quantities are genuinely fractional: the mapping UI is a `QDoubleSpinBox` with
`setMinimum(0.01)` and `setDecimals(2)` (`gui/tag_categories_dialog.py:590-594`), because a
per-order rate like 0.05 ("one roll of tape per 20 orders") is a sensible way to configure
packaging. `calculate_writeoff_quantities()` returns `round(quantity, 2)` — a float, by design
(`shopify_tool/sku_writeoff.py:191`).

This was pre-existing, but PR #281 is what makes it bite. Before #281 the quantity was
inflated by the line-item count per order, which masked the truncation. Now a single-order
session with a 0.5/order mapping exports `0`.

### Rounding direction: half-up, and NOT `Series.round()`

**`.round()` is wrong here.** numpy rounds half to **even**, so it leaves the headline case
broken. Verified in this repo's venv:

```
raw          [0.5, 1.5, 2.5, 0.4, 0.15, 3.0]
astype(int)  [0,   1,   2,   0,   0,    3]     <- today: truncates
.round()     [0,   2,   2,   0,   0,    3]     <- 0.5 still 0, 2.5 still 2
floor(x+0.5) [1,   2,   3,   0,   0,    3]     <- half-up: correct
```

Any implementation that reaches for `.round()` reintroduces the bug it was meant to fix.

**Rejected: `ceil`.** Never under-writes-off, but a 0.05/order tape mapping on a one-order
session would write off a whole roll. Too aggressive.

**Rejected: carrying the remainder across sessions.** Correct accounting, but needs persistent
per-client per-SKU state. Out of proportion to the bug. Half-up is unbiased on average; the
residual is under one piece per SKU per session.

### Rows that round to zero are dropped, and logged

A quantity below 0.5 still rounds to 0 (0.05/order × 3 orders = 0.15). Writing `Брой = 0` to
the ERP is a meaningless row, so those rows are dropped — but with a `logger.warning` naming
the SKU. A packaging material disappearing from an export with **no trace** is exactly the
failure mode this milestone is hunting; the log is the load-bearing half of this decision.

### Open question left for the user (does not block this plan)

Half-up rounding is chosen from repo evidence — `Мярка = "брой"` means the ERP column is
pieces, so integers are right. If the warehouse ERP in fact accepts decimal quantities, the
better fix is to drop the int conversion entirely rather than round. Flag this in the PR body;
do not attempt it.

Historical over-write-off correction remains out of scope (already raised in PR #281's body).

---

## File Structure

| file | responsibility | change |
|---|---|---|
| `shopify_tool/stock_export.py` | canonical ERP frame layout + export builders | add `_to_erp_quantity()`; call it in `_finalize_export_df()`; delete 3 `.astype(int)` |
| `shopify_tool/sku_writeoff.py` | write-off calculation + write-off report | delete 1 `.astype(int)` |
| `tests/test_stock_export.py` | export accuracy tests | add `TestQuantityRounding` |

---

### Task 1: Half-up quantity coercion in `_finalize_export_df`

**Files:**
- Modify: `shopify_tool/stock_export.py:25-42` (`_finalize_export_df`)
- Test: `tests/test_stock_export.py`

**Interfaces:**
- Produces: `_to_erp_quantity(values: pd.Series) -> pd.Series` — module-private in
  `shopify_tool.stock_export`. Returns an `int` Series, half-up rounded, non-negative.
  Task 2 relies on `_finalize_export_df()` applying it to `QTY_COL` on every path.

- [ ] **Step 1: Write the failing tests**

Extend the existing import at the top of `tests/test_stock_export.py` (line 9) to read:

```python
from shopify_tool.stock_export import (
    _finalize_export_df,
    _to_erp_quantity,
    create_stock_export,
    merge_session_stock_exports,
)
```

Then append the class at the end of the file. `_analysis_df` and `_read` are the existing
module-level helpers; `COL_SKU` / `COL_QTY` are the existing column-index constants.

Verified already: `_empty_export_df()` is object-dtype, and `pd.to_numeric(...)` handles it
without error; `ShopifyToolLogger` has `propagate=True`, so `caplog` captures its records.

```python
class TestQuantityRounding:
    def test_rounds_half_up_not_half_to_even(self):
        # pandas/numpy .round() is banker's rounding: 0.5 -> 0 and 2.5 -> 2, which
        # leaves the exact bug this helper exists to fix. Half-up is required.
        result = _to_erp_quantity(pd.Series([0.5, 1.5, 2.5, 3.5]))
        assert list(result) == [1, 2, 3, 4]

    def test_rounds_down_below_the_half(self):
        result = _to_erp_quantity(pd.Series([0.4, 0.49, 1.2, 2.499]))
        assert list(result) == [0, 0, 1, 2]

    def test_whole_numbers_are_unchanged(self):
        result = _to_erp_quantity(pd.Series([0.0, 1.0, 7.0, 100.0]))
        assert list(result) == [0, 1, 7, 100]

    def test_non_numeric_and_missing_become_zero(self):
        result = _to_erp_quantity(pd.Series([1.6, None, "abc"]))
        assert list(result) == [2, 0, 0]

    def test_negative_quantities_clip_to_zero(self):
        result = _to_erp_quantity(pd.Series([-3.0, -0.4]))
        assert list(result) == [0, 0]

    def test_finalize_rounds_the_quantity_column(self):
        df = pd.DataFrame({"Артикул": ["A1", "A2"], "Брой": [1.5, 2.5]})
        result = _finalize_export_df(df)
        assert list(result["Брой"]) == [2, 3]

    def test_finalize_drops_rows_that_round_to_zero(self):
        df = pd.DataFrame({"Артикул": ["KEEP", "DROP"], "Брой": [1.0, 0.15]})
        result = _finalize_export_df(df)
        assert list(result["Артикул"]) == ["KEEP"]

    def test_finalize_logs_the_sku_it_dropped(self, caplog):
        df = pd.DataFrame({"Артикул": ["PKG-TAPE"], "Брой": [0.15]})
        with caplog.at_level("WARNING", logger="ShopifyToolLogger"):
            _finalize_export_df(df)
        assert "PKG-TAPE" in caplog.text

    def test_finalize_stays_idempotent(self):
        df = pd.DataFrame({"Артикул": ["A1"], "Брой": [2.5]})
        once = _finalize_export_df(df)
        twice = _finalize_export_df(once)
        assert list(twice["Брой"]) == [3]
        assert list(once.columns) == list(twice.columns)
        assert len(twice) == 1

    def test_finalize_handles_an_empty_frame(self):
        from shopify_tool.stock_export import _empty_export_df

        result = _finalize_export_df(_empty_export_df())
        assert result.empty
        assert list(result.columns) == list(_empty_export_df().columns)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stock_export.py::TestQuantityRounding -v
```

Expected: collection fails with `ImportError: cannot import name '_to_erp_quantity'`.

- [ ] **Step 3: Add the helper**

Insert into `shopify_tool/stock_export.py` immediately above `_finalize_export_df`:

```python
def _to_erp_quantity(values: pd.Series) -> pd.Series:
    """Coerce a quantity column to the ERP's whole-piece integers, rounding half UP.

    The ERP's Брой column is measured in Мярка="брой" -- pieces -- so it cannot carry a
    fraction. Write-off quantities do arrive fractional (a per-order mapping rate such as
    0.5 times the order count), so this conversion has to round rather than truncate:
    a bare ``.astype(int)`` turned a 0.5-piece write-off into 0 and the material vanished
    from the export with no trace.

    Do NOT reach for ``Series.round()`` here -- numpy rounds half to EVEN, so 0.5 -> 0 and
    2.5 -> 2, which is the very bug this function exists to fix.
    """
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0).clip(lower=0)
    # Adding 0.5 and truncating is round-half-up, and .astype(int) truncates toward zero
    # -- which equals floor only because clip(lower=0) guarantees a non-negative input.
    return (numeric + 0.5).astype(int)
```

- [ ] **Step 4: Wire it into `_finalize_export_df`**

Replace the final line of `_finalize_export_df` (currently
`return df[STOCK_EXPORT_COLUMNS].reset_index(drop=True)`) with:

```python
    df = df[STOCK_EXPORT_COLUMNS].copy()
    df[QTY_COL] = _to_erp_quantity(df[QTY_COL])
    dropped = df.loc[df[QTY_COL] <= 0, "Артикул"]
    if not dropped.empty:
        logger.warning(
            f"Dropped {len(dropped)} export row(s) whose quantity rounded to zero: "
            f"{', '.join(map(str, dropped))}"
        )
    return df[df[QTY_COL] > 0].reset_index(drop=True)
```

Leave the rest of the function untouched — the `Колич` rename, the `Мярка` fill, and the
`Годност`/`Партида`/`BLANK_COL` defaults all still run first.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stock_export.py::TestQuantityRounding -v
```

Expected: 10 passed.

- [ ] **Step 6: Run the whole suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

Expected: 642 passed before this change; 652 after. **If an existing test now fails because a
zero-quantity row is no longer exported, that is this change working** — read the test, confirm
it was asserting the truncation behaviour, and update its expectation rather than weakening the
helper. If a test fails for any other reason, stop and investigate before continuing.

- [ ] **Step 7: Commit**

```bash
rtk git add shopify_tool/stock_export.py tests/test_stock_export.py
rtk git commit -m "Stock export: round ERP quantities half-up instead of truncating"
```

---

### Task 2: Delete the four `.astype(int)` truncations

With Task 1 in place these casts are redundant, and each one truncates before the finalizer
ever sees the value — so leaving any of them in keeps the bug alive on that path.

**Files:**
- Modify: `shopify_tool/stock_export.py:218`, `:257`, `:373`
- Modify: `shopify_tool/sku_writeoff.py:420`
- Test: `tests/test_stock_export.py`

**Interfaces:**
- Consumes: `_finalize_export_df()` from Task 1, which now owns the int conversion.

- [ ] **Step 1: Write the failing integration test**

Append to `TestQuantityRounding` in `tests/test_stock_export.py`:

```python
    def test_fractional_writeoff_on_a_single_order_is_not_lost(self, tmp_path):
        # The headline bug: 0.5 boxes for one order truncated to 0 and the packaging
        # material vanished from the export entirely.
        config = {
            "version": 2,
            "categories": {
                "packaging": {
                    "tags": ["BOX"],
                    "sku_writeoff": {
                        "enabled": True,
                        "mappings": {"BOX": [{"sku": "PKG-BOX", "quantity": 0.5}]},
                    },
                }
            },
        }
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Quantity": 1, "Internal_Tags": '["BOX"]'},
        ])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out), apply_writeoff=True, tag_categories=config)
        result = _read(out)
        packaging = result[result.iloc[:, COL_SKU] == "PKG-BOX"]
        assert len(packaging) == 1
        assert packaging.iloc[0, COL_QTY] == 1

    def test_fractional_writeoff_across_three_orders_rounds_up(self, tmp_path):
        config = {
            "version": 2,
            "categories": {
                "packaging": {
                    "tags": ["BOX"],
                    "sku_writeoff": {
                        "enabled": True,
                        "mappings": {"BOX": [{"sku": "PKG-BOX", "quantity": 0.5}]},
                    },
                }
            },
        }
        # 3 orders x 0.5 = 1.5 -> 2. Truncation gave 1.
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Quantity": 1, "Internal_Tags": '["BOX"]'},
            {"Order_Number": "#2", "SKU": "A1", "Quantity": 1, "Internal_Tags": '["BOX"]'},
            {"Order_Number": "#3", "SKU": "A1", "Quantity": 1, "Internal_Tags": '["BOX"]'},
        ])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out), apply_writeoff=True, tag_categories=config)
        result = _read(out)
        packaging = result[result.iloc[:, COL_SKU] == "PKG-BOX"]
        assert packaging.iloc[0, COL_QTY] == 2
```

- [ ] **Step 2: Run to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stock_export.py -k "fractional_writeoff" -v
```

Expected: both FAIL. The single-order case fails on `len(packaging) == 1` (the row is absent —
`.astype(int)` truncated 0.5 to 0 at `stock_export.py:257` and Task 1's finalizer then dropped
the zero row). The three-order case fails with `1 != 2`.

- [ ] **Step 3: Delete the cast at `stock_export.py:257`**

In `create_stock_export`, inside the `packaging_rows = _finalize_export_df(...)` block:

```python
                            QTY_COL: writeoff_df["Writeoff_Quantity"],
```

(was `writeoff_df["Writeoff_Quantity"].astype(int)`)

- [ ] **Step 4: Delete the cast at `stock_export.py:218`**

In the "Summarize quantities by SKU" branch, drop the `.astype(int)` line so the chain reads:

```python
            sku_summary = (
                filtered_items.groupby("SKU")["Quantity"]
                .sum()
                .reset_index()
            )
```

The `sku_summary[sku_summary["Quantity"] > 0]` filter on the next line now operates on floats,
which is what it should have been doing — a 0.6 no longer truncates to 0 and gets filtered out
before the finalizer can round it to 1.

- [ ] **Step 5: Delete the cast at `stock_export.py:373`**

Same edit in `merge_session_stock_exports`:

```python
    sku_summary = (
        combined.groupby("SKU")["Quantity"]
        .sum()
        .reset_index()
    )
```

Leave the `> 0` filter on the following line in place.

- [ ] **Step 6: Delete the cast at `sku_writeoff.py:420`**

In `generate_writeoff_report`:

```python
                QTY_COL: writeoff_df["Writeoff_Quantity"],
```

- [ ] **Step 7: Verify no `.astype(int)` remains on an export path**

```bash
rtk grep -nE "astype\(int\)|int\(" shopify_tool/stock_export.py shopify_tool/sku_writeoff.py
```

Expected: only the `.astype(int)` inside `_to_erp_quantity` itself. **The `int(` half of this
grep matters** — the first pass of this plan searched for the literal `astype(int)` only and
missed two bare `int(qty)` calls in `_expand_lot_summary`, which truncate *before*
`_finalize_export_df` runs and so cannot be recovered by it. Code review caught them.

(`set_decoder.py:206` is a different concern — `Component_Quantity` on set expansion, not an
ERP export column. Leave it alone.)

- [ ] **Step 8: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stock_export.py tests/test_sku_writeoff.py -v
```

Expected: all pass.

- [ ] **Step 9: Run the gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

Expected: 654 passed, ruff clean.

- [ ] **Step 10: Commit**

```bash
rtk git add shopify_tool/stock_export.py shopify_tool/sku_writeoff.py tests/test_stock_export.py
rtk git commit -m "Stock export: remove the four .astype(int) quantity truncations"
```

- [ ] **Step 11: Refresh the knowledge graph**

```bash
graphify update .
```

---

## Verification

Manual check is not required — the ERP layout is asserted positionally by the existing tests in
`tests/test_stock_export.py`, and `test_canonical_column_layout` still guards the column order.

Definition of done:
- `_to_erp_quantity` rounds half-up and is the only place an export quantity becomes an `int`.
- No `.astype(int)` remains in `stock_export.py` or `sku_writeoff.py`.
- A zero-rounding row is dropped **and** named in a `WARNING` log line.
- Full suite green, `ruff check . --exclude shared` clean, `graphify update .` run.
