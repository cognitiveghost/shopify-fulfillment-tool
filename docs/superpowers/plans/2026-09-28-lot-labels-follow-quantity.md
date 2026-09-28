# Lot labels follow Quantity; Change quantity verb — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A stock export or packing list can never again carry a quantity the order lines don't, and a person can change a SKU's quantity inside an order.

**Architecture:** One new pure function, `stock_ledger.lot_parts`, is the only reader of `Lot_Details` for output. It fits the run's lot allocation to each (order, SKU) pair's current `Quantity` (rule R3, ADR 0014). Both writers move onto it, the stock export gets a totals guard that refuses to write a wrong file, and Add product stops copying another line's allocation. A new pane verb, "Change quantity…", edits one line's `Quantity` through the same ledger rules as Add product, with undo.

**Tech Stack:** Python 3, pandas, PySide6 (QWebEngine page + QWebChannel bridge), plain JS in `gui/web/`, pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-09-28-lot-labels-follow-quantity-design.md` (read §2 for the root cause and §3 for R3 before starting).

## Global Constraints

- Run everything through `.venv/bin/python` (`python` is not on PATH). Fresh worktree: run `./scripts/setup_venv.sh` first.
- Test command: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` (single file: add the path).
- Never edit anything under `shared/` (synced from packing-tool).
- No hardcoded colors in CSS; no `QInputDialog` in `gui/actions_handler.py` (a test enforces it).
- No UI calls from background threads (none needed here).
- Keep imports clean: no unused typing imports.
- After the last code change, run `graphify update .` (CLAUDE.md).
- PR-only. Commit per task on branch `dr/3-investigate-and-fix-critical-bug-with-st`. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Do not bump the version (not asked).
- Toast copy (exact): `Changed {sku} in order {order} to {n}.` plus ` It is now blocked: not enough {SKU, SKU}.` when the change blocked the order.
- Totals-guard error text (exact prefix): `Stock export does not match the order lines: ` then `{sku} export {n}, lines {m}` items joined by `; `.

## Review Focus

1. **Undo JSON / pickle round-trip copies of `Lot_Details`** — two lines of one pair holding equal but distinct lists must count once (the old `id()` dedupe double-counted them). Pinned in Task 1 (`test_equal_but_distinct_lists_count_once`).
2. **Same SKU added by hand to an order that already has it** — expected: the lot part keeps its label, the extra unit is a blank-lot row; totals equal. Pinned in Task 4 (`test_adding_a_sku_the_order_already_has_labels_only_the_run_part`).
3. **Integer-like SKUs (HERBAR/WT use `10001`)** — the totals guard must compare `10001` and `"10001"` as the same SKU, or every export for those clients is refused. Pinned in Task 2 (`test_guard_accepts_numeric_skus`).
4. **Packaging write-off rows ("merged" mode)** — the guard must run before packaging rows are merged, or every merged export is refused. Pinned in Task 2 (`test_guard_ignores_merged_packaging_rows`).
5. **Change quantity on a held/blocked order** — expected: it stays held, draws nothing, and a lower number never unblocks it. Pinned in Task 5 (`test_changing_a_held_orders_quantity_keeps_it_held`).

---

## File map

| File | Change |
|---|---|
| `shopify_tool/stock_ledger.py` | + R3 docstring, + `lot_parts(rows)` |
| `shopify_tool/stock_export.py` | `_expand_lot_summary` on `lot_parts`; + `_check_totals`; call it in `create_stock_export` |
| `shopify_tool/packing_lists.py` | `_expand_lot_rows` on `lot_parts` |
| `gui/actions_handler.py` | Add product sets `Lot_Details = None`; + `change_line_quantity` |
| `shopify_tool/undo_manager.py` | `_restore_columns_by_position`; + `_undo_change_quantity`; dispatch |
| `gui/results_bridge.py` | + `lineQuantityChangeRequested` signal, `changeLineQuantity` slot |
| `gui/ui_manager.py` | connect the signal |
| `gui/web/pane.js` | line menu item + `openQtyMenu` |
| `docs/adr/0014-lot-labels-follow-quantity.md` | new |
| `CONTEXT.md` | + **Lot label** entry |
| Tests | `tests/test_stock_ledger.py`, `tests/test_stock_export.py`, `tests/test_packing_lists.py`, new `tests/test_lot_integrity.py`, `tests/test_actions_handler_bulk.py`, `tests/test_results_bridge.py`, `tests/test_results_screen.py`, `tests/test_results_pane.py` |

---

### Task 1: R3 — `stock_ledger.lot_parts`

**Files:**
- Modify: `shopify_tool/stock_ledger.py` (module docstring at top; new function at the end of the file)
- Test: `tests/test_stock_ledger.py` (append)

**Interfaces:**
- Produces: `lot_parts(rows: pd.DataFrame) -> list[tuple]` — each tuple `(row_label, qty, expiry: str, batch: str)`. Requires columns `SKU`, `Quantity`; uses `Order_Number` and `Lot_Details` when present. Row labels must be unique (analysis frames carry a RangeIndex).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_stock_ledger.py`:

```python
# --- R3: lot labels follow Quantity (spec 2026-09-28 §3) --------------------

from shopify_tool.stock_ledger import lot_parts  # noqa: E402

L1 = {"expiry": "260601", "expiry_dt": None, "batch": "B1", "qty_allocated": 3}
L2 = {"expiry": "270101", "expiry_dt": None, "batch": "B2", "qty_allocated": 2}


def lines(rows):
    """(order, sku, qty, lot_details)"""
    return pd.DataFrame(rows, columns=["Order_Number", "SKU", "Quantity", "Lot_Details"])


def test_lots_are_clipped_to_a_lower_quantity():
    df = lines([("#1", "A", 4, [L1, L2])])
    assert lot_parts(df) == [(0, 3, "260601", "B1"), (0, 1, "270101", "B2")]


def test_quantity_above_the_lots_is_one_unlabelled_part():
    df = lines([("#1", "A", 7, [L1, L2])])
    assert lot_parts(df) == [(0, 3, "260601", "B1"), (0, 2, "270101", "B2"), (0, 2, "", "")]


def test_one_shared_list_on_two_lines_of_a_pair_counts_once():
    lots = [L1, L2]
    df = lines([("#1", "A", 2, lots), ("#1", "A", 3, lots)])
    assert lot_parts(df) == [(0, 3, "260601", "B1"), (0, 2, "270101", "B2")]


def test_equal_but_distinct_lists_count_once():
    # An undo (JSON) or a pickle reload gives each line its own copy.
    df = lines([("#1", "A", 2, [dict(L1), dict(L2)]), ("#1", "A", 3, [dict(L1), dict(L2)])])
    assert lot_parts(df) == [(0, 3, "260601", "B1"), (0, 2, "270101", "B2")]


def test_a_line_without_lots_joins_its_pairs_lots():
    # A manual line (Lot_Details None) of a SKU the order already has.
    df = lines([("#1", "A", 3, [L1]), ("#1", "A", 1, None)])
    assert lot_parts(df) == [(0, 3, "260601", "B1"), (0, 1, "", "")]


def test_blank_order_numbers_never_pair():
    df = lines([("", "A", 3, [L1]), (None, "A", 2, [dict(L2)])])
    assert lot_parts(df) == [(0, 3, "260601", "B1"), (1, 2, "270101", "B2")]


def test_sentinel_one_is_blank():
    df = lines([("#1", "A", 4, [{"expiry": "1", "batch": "1", "qty_allocated": 4}])])
    assert lot_parts(df) == [(0, 4, "", "")]


@pytest.mark.parametrize("cell", [None, float("nan"), [], "[{'expiry': '1'}]"])
def test_a_cell_that_is_not_a_lot_list_means_no_lots(cell):
    df = lines([("#1", "A", 2, cell), ("#1", "A", 1, cell)])
    assert lot_parts(df) == [(0, 2, "", ""), (1, 1, "", "")]


def test_a_pair_with_lots_and_no_quantity_yields_nothing():
    df = lines([("#1", "A", 0, [L1])])
    assert lot_parts(df) == []


def test_pairs_come_out_in_row_order():
    df = lines([("#2", "B", 1, None), ("#1", "A", 1, [L1]), ("#2", "C", 1, None)])
    assert [p[0] for p in lot_parts(df)] == [0, 1, 2]


def test_no_lot_details_column_at_all():
    df = pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"], "Quantity": [2]})
    assert lot_parts(df) == [(0, 2, "", "")]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stock_ledger.py -q`
Expected: collection error / FAIL with `ImportError: cannot import name 'lot_parts'`.

- [ ] **Step 3: Implement.** In `shopify_tool/stock_ledger.py`, extend the module docstring — after the R2 paragraph and before `Edit verbs write rows…`, insert:

```
R3  Lot labels follow Quantity (ADR 0014). Lot_Details is the run's FIFO
    allocation and only labels a line's units. Per pair (one order's lines of
    one SKU) the pair's Quantity is walked through its lots, clipping each;
    what is left over has no lot label. lot_parts() is the only reader.
```

Then append at the end of the file:

```python
def _lot_list(cell) -> list:
    return cell if isinstance(cell, list) and cell else []


def _lot_label(value) -> str:
    # The run writes "1" (and None for batch) when the stock file has no lot.
    text = value or ""
    return "" if text == "1" else text


def lot_parts(rows) -> list:
    """R3: [(row label, quantity, expiry, batch)] for writing these rows out.

    A pair is one order's lines of one SKU; lines with a blank order number
    never pair. A pair with lots gives one part per lot it still needs,
    labelled with its first line, then one unlabelled part for any quantity
    the lots don't cover. A pair without lots gives each line as it is.
    Pairs come out in the order their first line appears in `rows`.
    """
    if rows is None or rows.empty:
        return []
    qty = pd.to_numeric(rows["Quantity"], errors="coerce").fillna(0)
    has_orders = "Order_Number" in rows.columns
    pairs: dict = {}
    for label, sku in zip(rows.index, rows["SKU"]):
        order = rows.at[label, "Order_Number"] if has_orders else None
        order = "" if order is None or pd.isna(order) else str(order).strip()
        sku = "" if sku is None or pd.isna(sku) else str(sku).strip()
        key = (order, sku) if order else ("", label)
        pairs.setdefault(key, []).append(label)

    lotted = "Lot_Details" in rows.columns
    parts = []
    for labels in pairs.values():
        lots = next(
            (_lot_list(rows.at[l, "Lot_Details"]) for l in labels
             if lotted and _lot_list(rows.at[l, "Lot_Details"])),
            [],
        )
        if not lots:
            parts.extend((l, rows.at[l, "Quantity"], "", "") for l in labels)
            continue
        need = qty[labels].sum()
        for lot in lots:
            if need <= 0:
                break
            take = min(lot.get("qty_allocated", 0) or 0, need)
            if take > 0:
                parts.append(
                    (labels[0], take, _lot_label(lot.get("expiry")), _lot_label(lot.get("batch")))
                )
                need -= take
        if need > 0:
            parts.append((labels[0], need, "", ""))
    return parts
```

Note `pd.isna` on a list raises/returns arrays — never called on `Lot_Details` here; only on `Order_Number` and `SKU` scalars.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stock_ledger.py -q`
Expected: all PASS. If a tuple compares unequal only because of `numpy.int64` vs `int`, that is fine (`==` holds); if it is `3.0` vs `3`, also fine. Do not change the assertions.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/stock_ledger.py tests/test_stock_ledger.py
git commit -m "feat: R3 lot_parts fits lot labels to Quantity (spec 2026-09-28 §3)"
```

---

### Task 2: Stock export on R3 + totals guard

**Files:**
- Modify: `shopify_tool/stock_export.py` — `_expand_lot_summary` (currently ~lines 80–150), `create_stock_export` (~lines 224–390); add `_check_totals`
- Test: `tests/test_stock_export.py` (append a class)

**Interfaces:**
- Consumes: `stock_ledger.lot_parts(rows)` from Task 1.
- Produces: `_check_totals(filtered_items: pd.DataFrame, export_df: pd.DataFrame) -> None` raising `ValueError`. `create_stock_export` signature unchanged.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_stock_export.py` (it already imports `pandas as pd`, `pytest`, `create_stock_export`, and has helper `_analysis_df(rows)` and `_read(path)`, and constants `COL_SKU`, `COL_QTY`, `COL_EXPIRY`):

```python
class TestLotLabelsFollowQuantity:
    """Spec 2026-09-28: a lot allocation never outvotes Quantity."""

    def test_a_stale_allocation_is_clipped_to_the_line(self, tmp_path):
        lots = [{"expiry": "260601", "batch": "B1", "qty_allocated": 3}]
        df = _analysis_df([{"Order_Number": "#1", "SKU": "A1", "Quantity": 1, "Lot_Details": lots}])
        out = tmp_path / "e.xls"
        create_stock_export(df, str(out))
        result = _read(out)
        assert result.iloc[:, COL_QTY].tolist() == [1]

    def test_two_skus_sharing_one_list_object_both_export(self, tmp_path):
        # The incident: two manual lines carried one copied allocation object.
        lots = [{"expiry": "1", "batch": None, "qty_allocated": 3}]
        df = _analysis_df([
            {"Order_Number": "#1221", "SKU": "L", "Quantity": 1, "Lot_Details": lots},
            {"Order_Number": "#1221", "SKU": "S", "Quantity": 1, "Lot_Details": lots},
        ])
        out = tmp_path / "e.xls"
        create_stock_export(df, str(out))
        result = _read(out)
        totals = dict(zip(result.iloc[:, COL_SKU].astype(str), result.iloc[:, COL_QTY]))
        assert totals == {"L": 1, "S": 1}


class TestTotalsGuard:
    def test_a_wrong_lot_summary_is_refused_and_nothing_is_written(self, tmp_path, monkeypatch):
        import shopify_tool.stock_export as se

        lots = [{"expiry": "260601", "batch": "B1", "qty_allocated": 2}]
        df = _analysis_df([{"Order_Number": "#1", "SKU": "A1", "Quantity": 2, "Lot_Details": lots}])
        monkeypatch.setattr(
            se, "_expand_lot_summary",
            lambda items: se._finalize_export_df(pd.DataFrame({"Артикул": ["A1"], se.QTY_COL: [3]})),
        )
        out = tmp_path / "e.xls"
        with pytest.raises(ValueError, match=r"A1 export 3, lines 2"):
            create_stock_export(df, str(out))
        assert not out.exists()

    def test_a_dropped_sku_is_refused(self, tmp_path, monkeypatch):
        import shopify_tool.stock_export as se

        lots = [{"expiry": "260601", "batch": "B1", "qty_allocated": 1}]
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Quantity": 1, "Lot_Details": lots},
            {"Order_Number": "#1", "SKU": "A2", "Quantity": 1, "Lot_Details": None},
        ])
        monkeypatch.setattr(
            se, "_expand_lot_summary",
            lambda items: se._finalize_export_df(pd.DataFrame({"Артикул": ["A1"], se.QTY_COL: [1]})),
        )
        with pytest.raises(ValueError, match=r"A2 export 0, lines 1"):
            create_stock_export(df, str(tmp_path / "e.xls"))

    def test_guard_accepts_numeric_skus(self, tmp_path):
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": 10001, "Quantity": 2},
            {"Order_Number": "#2", "SKU": "10001", "Quantity": 1,
             "Lot_Details": [{"expiry": "1", "batch": None, "qty_allocated": 1}]},
        ])
        out = tmp_path / "e.xls"
        create_stock_export(df, str(out))  # must not raise
        assert _read(out).iloc[:, COL_QTY].sum() == 3

    def test_guard_ignores_merged_packaging_rows(self, tmp_path):
        tag_categories = {
            "version": 2,
            "categories": {
                "packaging": {
                    "tags": ["BOX"],
                    "sku_writeoff": {
                        "enabled": True,
                        "mappings": {"BOX": [{"sku": "PKG-1", "quantity": 1.0}]},
                    },
                }
            },
        }
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Quantity": 2, "Internal_Tags": '["BOX"]'},
        ])
        out = tmp_path / "e.xls"
        create_stock_export(df, str(out), writeoff_mode="merged", tag_categories=tag_categories)
        skus = set(_read(out).iloc[:, COL_SKU].astype(str))
        assert {"A1", "PKG-1"} <= skus
```

`_analysis_df` (top of `tests/test_stock_export.py`) defaults every row to `Order_Fulfillment_Status = "Fulfillable"` and `Lot_Details = None`; the tag format is the V2 shape documented at the top of `shopify_tool/sku_writeoff.py`. The point of the packaging test is that a merged export carrying a packaging SKU is **not** refused by the guard.

- [ ] **Step 2: Run to verify failures**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stock_export.py -q -k "LotLabelsFollowQuantity or TotalsGuard"`
Expected: `test_a_stale_allocation_is_clipped_to_the_line` FAIL (exports 3), `test_two_skus_sharing_one_list_object_both_export` FAIL (`{"L": 3}`), both refuse tests FAIL (`DID NOT RAISE`). The numeric-SKU and packaging tests may already pass; they are guards for Step 3.

- [ ] **Step 3: Implement.**

3a. Add the import near the top of `shopify_tool/stock_export.py`:

```python
from shopify_tool.stock_ledger import lot_parts
```

3b. Replace the whole body of `_expand_lot_summary` (keep its name and docstring's first line; rewrite the rest of the docstring) with:

```python
def _expand_lot_summary(filtered_items: pd.DataFrame) -> pd.DataFrame:
    """Aggregate fulfilled quantities per (SKU, expiry, batch) lot for write-off requests.

    The parts come from stock_ledger.lot_parts (R3, ADR 0014): Quantity is the
    truth and Lot_Details only labels it, so a stale or copied allocation can
    neither inflate a SKU nor hide one. Units without a lot label aggregate
    under a blank Годност/Партида.

    Returns:
        DataFrame with the canonical layout (:data:`STOCK_EXPORT_COLUMNS`).
    """
    totals: dict = {}
    for label, qty, expiry, batch in lot_parts(filtered_items):
        qty = pd.to_numeric(qty, errors="coerce")
        if pd.isna(qty):
            continue
        key = (filtered_items.at[label, "SKU"], expiry, batch)
        totals[key] = totals.get(key, 0) + qty

    records = [
        {"Артикул": sku, QTY_COL: qty, "Годност": expiry, "Партида": batch}
        for (sku, expiry, batch), qty in totals.items()
        if qty > 0
    ]
    if not records:
        return _empty_export_df()
    return _finalize_export_df(pd.DataFrame(records))
```

(Delete the old `lot_rows_data` / `no_lot_skus` / `seen_allocations` code and its `id()` comment.)

3c. Add `_check_totals` right after `_expand_lot_summary`:

```python
def _check_totals(filtered_items: pd.DataFrame, export_df: pd.DataFrame) -> None:
    """Refuse an export whose per-SKU Брой differs from the lines it came from.

    The #1221 incident (spec 2026-09-28) wrote 3 for a line of 1 and dropped a
    SKU; this is the net under every path that builds the product rows.
    ponytail: compares after half-up rounding, so fractional quantities split
    across several lots could round differently per part than in total; product
    quantities are whole, so that never happens in practice.
    """
    skus = filtered_items["SKU"].astype(str).str.strip()
    lines = pd.to_numeric(filtered_items["Quantity"], errors="coerce").fillna(0)
    expected = _to_erp_quantity(lines.groupby(skus).sum())
    expected = expected[expected > 0]
    actual = export_df.groupby(export_df["Артикул"].astype(str).str.strip())[QTY_COL].sum()
    wrong = [
        f"{sku} export {int(actual.get(sku, 0))}, lines {int(expected.get(sku, 0))}"
        for sku in sorted(set(expected.index) | set(actual.index))
        if int(actual.get(sku, 0)) != int(expected.get(sku, 0))
    ]
    if wrong:
        raise ValueError("Stock export does not match the order lines: " + "; ".join(wrong))
```

3d. In `create_stock_export`, directly **after** the `if filtered_items.empty: … elif has_lot_details: … else: …` block that builds `export_df`, and **before** the `# Packaging write-off:` comment, insert:

```python
        # Product rows only: packaging SKUs are not order lines.
        _check_totals(filtered_items, export_df)
```

3e. Update the `create_stock_export` docstring "Raises:" section to mention: `ValueError: the product rows don't add up to the fulfillable lines (nothing is written).`

- [ ] **Step 4: Run the stock-export tests and the output audit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stock_export.py tests/audit/test_04_outputs.py -q`
Expected: all PASS, including the pre-existing `TestLotAggregation`, `TestConfirmedBugs::test_missing_order_number_does_not_drop_distinct_lot_allocations` and `test_stock_export_lot_rows_sum_to_the_allocation`. If a pre-existing test fails only because of **row order** in the export (lot rows used to come before no-lot rows), check the ERP does not care about row order (it doesn't: it reads columns by position) and adjust that assertion to compare sorted rows; note it in the commit message. Any other pre-existing failure is a real regression — fix the code, not the test.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/stock_export.py tests/test_stock_export.py
git commit -m "fix: stock export fits lots to Quantity and refuses wrong totals (#1221)"
```

---

### Task 3: Packing list on R3

**Files:**
- Modify: `shopify_tool/packing_lists.py:16-65` (`_expand_lot_rows`)
- Test: `tests/test_packing_lists.py` (append to `class TestLotExpansion`)

**Interfaces:**
- Consumes: `stock_ledger.lot_parts(rows)`.
- Produces: `_expand_lot_rows(df) -> pd.DataFrame` — same contract as today (adds `Lot_Expiry`, `Lot_Batch`).

- [ ] **Step 1: Write the failing tests** — add inside `class TestLotExpansion` in `tests/test_packing_lists.py`:

```python
    def test_a_stale_allocation_prints_the_line_quantity(self, tmp_path):
        lots = [{"expiry": "260601", "batch": None, "qty_allocated": 3}]
        df = _analysis_df([{"Order_Number": "#1", "SKU": "A1", "Quantity": 1, "Lot_Details": lots}])
        out = tmp_path / "stale.xlsx"
        create_packing_list(df, str(out))
        assert _read_output(out)["Quantity"].tolist() == [1]

    def test_two_skus_sharing_one_list_object_print_their_own_quantity(self, tmp_path):
        lots = [{"expiry": "1", "batch": None, "qty_allocated": 3}]
        df = _analysis_df([
            {"Order_Number": "#1221", "SKU": "L", "Quantity": 1, "Lot_Details": lots},
            {"Order_Number": "#1221", "SKU": "S", "Quantity": 1, "Lot_Details": lots},
        ])
        out = tmp_path / "shared.xlsx"
        create_packing_list(df, str(out))
        result = _read_output(out)
        assert dict(zip(result["SKU"], result["Quantity"])) == {"L": 1, "S": 1}

    def test_unlotted_duplicate_lines_stay_two_lines(self, tmp_path):
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Quantity": 1},
            {"Order_Number": "#1", "SKU": "A1", "Quantity": 2},
            {"Order_Number": "#2", "SKU": "A2", "Quantity": 1,
             "Lot_Details": [{"expiry": "260601", "batch": None, "qty_allocated": 1}]},
        ])
        out = tmp_path / "dups.xlsx"
        create_packing_list(df, str(out))
        result = _read_output(out)
        assert result.loc[result["SKU"] == "A1", "Quantity"].tolist() == [1, 2]
```

- [ ] **Step 2: Run to verify failures**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_packing_lists.py -q -k TestLotExpansion`
Expected: the first two new tests FAIL (print 3). The third may already pass; it guards Step 3.

- [ ] **Step 3: Implement.** Add `from shopify_tool.stock_ledger import lot_parts` to the imports of `shopify_tool/packing_lists.py`, and replace `_expand_lot_rows` with:

```python
def _expand_lot_rows(df: pd.DataFrame) -> pd.DataFrame:
    """One packing-list row per lot part (stock_ledger.lot_parts, R3).

    A line whose order and SKU carry lots becomes one row per lot, Quantity
    fitted to the line's own (a stale or copied allocation cannot change it),
    plus a blank-lot row for units the run never allocated. Lines without lots
    are kept as they are, one row each, with blank Lot_Expiry / Lot_Batch.

    Destination_Country de-duplication must be re-applied by the caller
    AFTER calling this function (expansion changes row count per order).
    """
    rows = []
    for label, qty, expiry, batch in lot_parts(df):
        row = df.loc[label].copy()
        row["Quantity"] = qty
        row["Lot_Expiry"] = expiry
        row["Lot_Batch"] = batch
        rows.append(row)
    if not rows:
        result = df.copy()
        result["Lot_Expiry"] = ""
        result["Lot_Batch"] = ""
        return result
    return pd.DataFrame(rows).reset_index(drop=True)
```

- [ ] **Step 4: Run all packing tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_packing_lists.py tests/test_packing_list_order.py tests/audit/test_04_outputs.py -q`
Expected: all PASS (including `test_repeat_column_in_lot_layout_marks_first_row_only` and `test_packing_list_lot_rows_keep_the_order_quantity`).

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/packing_lists.py tests/test_packing_lists.py
git commit -m "fix: packing list fits lots to Quantity (#1221)"
```

---

### Task 4: Add product stops inheriting a lot allocation + incident regression

**Files:**
- Modify: `gui/actions_handler.py` — `_add_product_to_order`, right after `new_row = template_row.copy()` (~line 1336)
- Create: `tests/test_lot_integrity.py`

**Interfaces:**
- Consumes: `ActionsHandler.remove_line(order_number, line_index, sku)`, `ActionsHandler._add_product_to_order(product_data, stock_df, live_stock)`, `create_stock_export`, `create_packing_list`, `run_analysis`.
- Produces: helpers in `tests/test_lot_integrity.py` reused by Task 5's lot test: `lot_stock(rows)`, `order_rows(rows)`, `window(df)`, `line_of(mw, order, sku)`, `export_totals(path)`, `packing_lines(path)`.

- [ ] **Step 1: Write the failing test file** `tests/test_lot_integrity.py`:

```python
"""The #1221 incident (REVE 2026-09-28_1) and its neighbours.

Spec: docs/superpowers/specs/2026-09-28-lot-labels-follow-quantity-design.md.
Synthetic, lot-tracked fixtures; no production data.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from gui.actions_handler import ActionsHandler
from gui.selection_helper import SelectionHelper
from shopify_tool.analysis import run_analysis
from shopify_tool.packing_lists import create_packing_list
from shopify_tool.stock_export import create_stock_export
from shopify_tool.undo_manager import UndoManager

NO_HISTORY = pd.DataFrame({"Order_Number": []})


def lot_stock(rows):
    """(sku, qty, expiry, batch) -> a stock file with lot columns."""
    df = pd.DataFrame(rows, columns=["Артикул", "Наличност", "Годност", "Партида"])
    df["Име"] = df["Артикул"].astype(str) + " name"
    return df


def order_rows(rows):
    """(order, sku, qty)"""
    df = pd.DataFrame(rows, columns=["Name", "Lineitem sku", "Lineitem quantity"])
    df["Shipping Method"] = "DHL"
    return df


def window(df):
    mw = SimpleNamespace(
        analysis_results_df=df,
        analysis_stats=None,
        save_session_state=Mock(),
        log_activity=Mock(),
        _update_all_views=Mock(),
        results_bridge=Mock(),
        ui_manager=Mock(),
        session_path=None,
        current_client_id="TEST",
        active_profile_config={"settings": {}},
    )
    mw.selection_helper = SelectionHelper(main_window=mw)
    mw.undo_manager = UndoManager(mw)
    return mw


def line_of(mw, order, sku):
    """The index remove_line expects: the line's position within its order."""
    df = mw.analysis_results_df
    own = df[df["Order_Number"] == order].reset_index(drop=True)
    return int(own.index[own["SKU"] == sku][0])


def export_totals(path):
    e = pd.read_excel(path, dtype={"Артикул": str})
    return e.groupby("Артикул")["Брой"].sum().to_dict()


def packing_lines(path):
    p = pd.read_excel(path, dtype={"Order_Number": str, "SKU": str})
    return p.groupby(["Order_Number", "SKU"])["Quantity"].sum().to_dict()


def add(handler, order, sku, qty):
    stock_df = pd.DataFrame({"SKU": [sku], "Stock": [50], "Product_Name": [sku.lower()]})
    handler._add_product_to_order(
        {"order_number": order, "sku": sku, "product_name": sku.lower(), "quantity": qty},
        stock_df,
        {},
    )


def incident_run():
    stock = lot_stock([
        ("L", 11, "20270101", "B1"), ("M", 12, "20270101", "B1"),
        ("S", 20, "20270101", "B1"), ("SM", 25, "20270101", "B1"),
        ("R", 46, "20270101", "B1"),
    ])
    orders = order_rows([
        ("#1221", "SM", 1), ("#1221", "L", 3), ("#1221", "M", 4), ("#1221", "S", 4),
        ("#1209", "R", 1),
    ])
    df, *_ = run_analysis(stock, orders, NO_HISTORY)
    return df


def test_the_1221_edits_export_exactly_what_the_order_holds(tmp_path):
    mw = window(incident_run())
    h = ActionsHandler(mw)
    # The session's operation history, in order.
    h.remove_line("#1221", line_of(mw, "#1221", "SM"), "SM")
    h.remove_line("#1221", line_of(mw, "#1221", "M"), "M")
    add(h, "#1221", "L", 1)
    add(h, "#1221", "S", 1)
    h.remove_line("#1221", line_of(mw, "#1221", "S"), "S")  # the original S x4
    h.remove_line("#1221", line_of(mw, "#1221", "L"), "L")  # the original L x3
    out = mw.analysis_results_df
    assert out.loc[out["Source"] == "Manual", "Lot_Details"].isna().all()

    create_stock_export(out, str(tmp_path / "e.xls"))
    assert export_totals(tmp_path / "e.xls") == {"L": 1, "S": 1, "R": 1}

    create_packing_list(out, str(tmp_path / "p.xlsx"))
    assert packing_lines(tmp_path / "p.xlsx") == {
        ("#1221", "L"): 1, ("#1221", "S"): 1, ("#1209", "R"): 1,
    }


def test_adding_a_sku_the_order_already_has_labels_only_the_run_part(tmp_path):
    mw = window(incident_run())
    add(ActionsHandler(mw), "#1221", "L", 1)
    out = mw.analysis_results_df
    create_stock_export(out, str(tmp_path / "e.xls"))
    e = pd.read_excel(tmp_path / "e.xls", dtype={"Артикул": str, "Годност": str}).fillna("")
    l_rows = sorted(zip(e.loc[e["Артикул"] == "L", "Годност"], e.loc[e["Артикул"] == "L", "Брой"]))
    assert l_rows == [("", 1), ("20270101", 3)]
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lot_integrity.py -q`
Expected: `test_the_1221_edits_…` FAIL on `assert out.loc[... "Lot_Details"].isna().all()` (manual rows carry the copied list). With Tasks 2–3 already in, the totals would be right even without this fix — which is why the `isna()` assertion is there: the manual line must not claim a lot it never drew. `test_adding_a_sku_…` may already pass after Tasks 1–2; keep it.

- [ ] **Step 3: Implement.** In `gui/actions_handler.py::_add_product_to_order`, directly after `new_row = template_row.copy()`:

```python
        # The template is another line: its lot allocation belongs to that
        # SKU and quantity. A copied one exported 3 for a line of 1 and hid a
        # SKU (#1221, spec 2026-09-28). The new line has no lot label (R3).
        if "Lot_Details" in new_row.index:
            new_row["Lot_Details"] = None
```

- [ ] **Step 4: Run**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lot_integrity.py tests/test_actions_handler_bulk.py tests/audit/test_01_intake_analysis.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/actions_handler.py tests/test_lot_integrity.py
git commit -m "fix: Add product no longer copies another line's lot allocation (#1221)"
```

---

### Task 5: `change_line_quantity` verb + undo

**Files:**
- Modify: `gui/actions_handler.py` — add `change_line_quantity` directly after `remove_line` (~line 1007)
- Modify: `shopify_tool/undo_manager.py` — `_restore_statuses_by_position` (~line 252) → generalise; add `_undo_change_quantity`; dispatch in `undo()` (~line 180–200)
- Test: `tests/test_actions_handler_bulk.py` (append), `tests/test_lot_integrity.py` (append one test)

**Interfaces:**
- Consumes: `stock_ledger.is_fulfillable(df, order)`, `stock_ledger.shortfall(df, order) -> list[str]`, `stock_ledger.with_stock_left(df)`, `stock_ledger.NOT_FULFILLABLE`, `self._order_mask(order_number, df=None)`, `self._results_toast(text, undoable)`, `self._update_undo_button()`, `self.mw.undo_manager.record_operation(type, description, params, affected_rows)`.
- Produces: `ActionsHandler.change_line_quantity(order_number, line_index: int, sku, quantity: int) -> None`; undo type `"change_quantity"`; `UndoManager._restore_columns_by_position(rows, columns) -> bool`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_actions_handler_bulk.py` (the section at ~line 269 already defines `run_analysis`, `UndoManager`, `NO_HISTORY`, `_stock`, `_orders`, `_ledger_window`, and helpers `_status(df, order)` and `_final_stock(df, sku)`; use them):

```python
# --- Change quantity (spec 2026-09-28 §4.5) ---------------------------------


def _qty(df, order, sku):
    return df.loc[(df["Order_Number"] == order) & (df["SKU"] == sku), "Quantity"].tolist()


def test_lowering_a_quantity_returns_stock_and_undo_takes_it_back():
    df, *_ = run_analysis(_stock([("A", 5)]), _orders([("#1", "A", 2)]), NO_HISTORY)
    mw = _ledger_window(df)
    ActionsHandler(mw).change_line_quantity("#1", 0, "A", 1)
    out = mw.analysis_results_df
    assert _qty(out, "#1", "A") == [1]
    assert _status(out, "#1") == {"Fulfillable"} and _final_stock(out, "A") == 4
    mw.results_bridge.raise_toast.assert_called_with("Changed A in order #1 to 1.", undoable=True)
    ok, _ = mw.undo_manager.undo()
    assert ok
    out = mw.analysis_results_df
    assert _qty(out, "#1", "A") == [2] and _final_stock(out, "A") == 3


def test_raising_within_stock_left_keeps_the_order_fulfillable():
    df, *_ = run_analysis(_stock([("A", 5)]), _orders([("#1", "A", 2)]), NO_HISTORY)
    mw = _ledger_window(df)
    ActionsHandler(mw).change_line_quantity("#1", 0, "A", 5)
    out = mw.analysis_results_df
    assert _status(out, "#1") == {"Fulfillable"} and _final_stock(out, "A") == 0


def test_raising_past_stock_left_blocks_the_order_and_undo_restores_it():
    df, *_ = run_analysis(_stock([("A", 5), ("B", 9)]), _orders([("#1", "A", 2), ("#1", "B", 1)]), NO_HISTORY)
    mw = _ledger_window(df)
    own = df[df["Order_Number"] == "#1"].reset_index(drop=True)
    ActionsHandler(mw).change_line_quantity("#1", int(own.index[own["SKU"] == "A"][0]), "A", 6)
    out = mw.analysis_results_df
    assert _status(out, "#1") == {"Not Fulfillable"}
    assert _final_stock(out, "A") == 5 and _final_stock(out, "B") == 9
    mw.results_bridge.raise_toast.assert_called_with(
        "Changed A in order #1 to 6. It is now blocked: not enough A.", undoable=True
    )
    ok, _ = mw.undo_manager.undo()
    assert ok
    out = mw.analysis_results_df
    assert _status(out, "#1") == {"Fulfillable"} and _qty(out, "#1", "A") == [2]
    assert _final_stock(out, "A") == 3 and _final_stock(out, "B") == 8


def test_changing_a_held_orders_quantity_keeps_it_held():
    df, *_ = run_analysis(_stock([("A", 5)]), _orders([("#1", "A", 2)]), NO_HISTORY)
    mw = _ledger_window(df)
    handler = ActionsHandler(mw)
    handler.toggle_fulfillment_status_for_order("#1")  # hold
    handler.change_line_quantity("#1", 0, "A", 1)
    out = mw.analysis_results_df
    assert _status(out, "#1") == {"Not Fulfillable"} and _final_stock(out, "A") == 5
    mw.results_bridge.raise_toast.assert_called_with("Changed A in order #1 to 1.", undoable=True)


@pytest.mark.parametrize(
    ("index", "sku", "quantity"),
    [
        (0, "A", 2),     # unchanged
        (0, "B", 3),     # the line at that index no longer carries B
        (5, "A", 3),     # the line is gone
        (0, "A", 0),     # not a quantity
        (0, "A", -1),
        (0, "A", True),  # bool is an int subclass; refuse it
    ],
)
def test_a_change_that_cannot_apply_changes_nothing(index, sku, quantity):
    df, *_ = run_analysis(_stock([("A", 5)]), _orders([("#1", "A", 2)]), NO_HISTORY)
    mw = _ledger_window(df)
    before = len(mw.undo_manager.operations)
    ActionsHandler(mw).change_line_quantity("#1", index, sku, quantity)
    out = mw.analysis_results_df
    assert _qty(out, "#1", "A") == [2] and _final_stock(out, "A") == 3
    assert len(mw.undo_manager.operations) == before
    mw.results_bridge.raise_toast.assert_not_called()
```

And append to `tests/test_lot_integrity.py`:

```python
def test_a_lowered_lot_line_exports_its_new_quantity(tmp_path):
    mw = window(incident_run())
    ActionsHandler(mw).change_line_quantity("#1221", line_of(mw, "#1221", "S"), "S", 1)
    create_stock_export(mw.analysis_results_df, str(tmp_path / "e.xls"))
    assert export_totals(tmp_path / "e.xls")["S"] == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_actions_handler_bulk.py tests/test_lot_integrity.py -q -k "quantity or change"`
Expected: FAIL with `AttributeError: 'ActionsHandler' object has no attribute 'change_line_quantity'`.

- [ ] **Step 3: Implement the undo side** in `shopify_tool/undo_manager.py`.

Replace the method `_restore_statuses_by_position` with these two methods:

```python
    def _restore_columns_by_position(self, rows: pd.DataFrame, columns) -> bool:
        """Put each line's own values back. False when positions can't be trusted."""
        df = self.main_window.analysis_results_df
        positions = rows.attrs.get("row_positions")
        if not positions or len(positions) != len(rows) or max(positions) >= len(df):
            return False
        here = df["Order_Number"].iloc[positions].astype(str).str.strip().tolist()
        saved = rows["Order_Number"].astype(str).str.strip().tolist()
        if here != saved:
            return False
        for column in columns:
            df.loc[df.index[positions], column] = rows[column].values
        return True

    def _restore_statuses_by_position(self, rows: pd.DataFrame) -> bool:
        return self._restore_columns_by_position(rows, ["Order_Fulfillment_Status"])
```

Add, after `_undo_remove_order`:

```python
    def _undo_change_quantity(self, params: dict, affected_rows_before: pd.DataFrame) -> bool:
        """Put the order's quantities and statuses back; undo() re-derives Stock left."""
        return self._restore_columns_by_position(
            affected_rows_before, ["Quantity", "Order_Fulfillment_Status"]
        )
```

In `undo()`, after the `elif operation_type == "remove_order":` branch, add:

```python
            elif operation_type == "change_quantity":
                success = self._undo_change_quantity(params, affected_rows_before)
```

- [ ] **Step 4: Implement the verb** in `gui/actions_handler.py`, directly after `remove_line`:

```python
    def change_line_quantity(self, order_number, line_index: int, sku, quantity):
        """The pane's Change quantity (spec 2026-09-28 §4.5): the order's
        `line_index`-th line, in frame order, only while it still carries
        `sku`. The order keeps its status unless the new quantity outruns
        Stock left, as Add product does; a lower one never releases a hold.
        Lot_Details is left alone: R3 fits it to the new quantity on output."""
        df = self.mw.analysis_results_df
        if df is None or df.empty:
            return
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            self.log.warning(f"Aborted quantity change: {quantity!r} is not a whole number from 1")
            return
        mask = self._order_mask(order_number)
        labels = df.index[mask]
        if not 0 <= line_index < len(labels):
            self.log.warning("Aborted quantity change: the line is gone")
            return
        label = labels[line_index]
        own_sku = df.loc[label, "SKU"]
        own = "" if pd.isna(own_sku) else str(own_sku).strip()
        if own != str(sku).strip():
            self.log.warning("Aborted quantity change: the line moved")
            return
        old = pd.to_numeric(df.loc[label, "Quantity"], errors="coerce")
        if old == quantity:
            return

        affected_rows = df[mask].copy()
        was_fulfillable = stock_ledger.is_fulfillable(df, order_number)
        frame = df.copy()
        frame.loc[label, "Quantity"] = quantity
        short = stock_ledger.shortfall(frame, order_number) if was_fulfillable else []
        if short:
            frame.loc[
                self._order_mask(order_number, frame), "Order_Fulfillment_Status"
            ] = stock_ledger.NOT_FULFILLABLE
        self.mw.analysis_results_df = stock_ledger.with_stock_left(frame)

        before = None if pd.isna(old) else (int(old) if float(old).is_integer() else float(old))
        description = f"Changed {own} in order {order_number} from {before} to {quantity}"
        self.mw.undo_manager.record_operation(
            "change_quantity",
            description,
            {
                "order_number": order_number,
                "sku": own,
                "quantity_before": before,
                "quantity_after": quantity,
            },
            affected_rows,
        )

        self.data_changed.emit()
        self.mw.save_session_state()
        self._update_undo_button()
        self.mw.log_activity("Data Edit", f"{description}.")
        text = f"Changed {own} in order {order_number} to {quantity}."
        if short:
            text += f" It is now blocked: not enough {', '.join(short)}."
        self._results_toast(text, undoable=True)
```

(`stock_ledger` and `pd` are already imported in this module — check the import block; do not add duplicates.)

- [ ] **Step 5: Run**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_actions_handler_bulk.py tests/test_lot_integrity.py tests/test_undo_manager*.py tests/audit/test_01_intake_analysis.py -q`
Expected: all PASS. (If `tests/test_undo_manager*.py` matches nothing, drop it from the command.) `test_no_input_dialog_survives_in_actions_handler` must still pass.

- [ ] **Step 6: Commit**

```bash
git add gui/actions_handler.py shopify_tool/undo_manager.py tests/test_actions_handler_bulk.py tests/test_lot_integrity.py
git commit -m "feat: change a line's quantity, with undo (spec 2026-09-28 §4.5)"
```

---

### Task 6: Bridge, wiring and the pane's number entry

**Files:**
- Modify: `gui/results_bridge.py` — signal next to `lineRemovalRequested = Signal(str, int, str)` (~line 79); slot next to `removeLine` (~line 178)
- Modify: `gui/ui_manager.py` — after the `bridge.lineRemovalRequested.connect(...)` statement (~line 642)
- Modify: `gui/web/pane.js` — `paneLines` line menu (~line 164); new `openQtyMenu` after `openTagMenu` (~line 294)
- Test: `tests/test_results_bridge.py` (~line 224 parametrize list), `tests/test_results_screen.py` (~line 265 parametrize list), `tests/test_results_pane.py` (after `test_remove_this_line_sends_the_index_and_its_sku`)

**Interfaces:**
- Consumes: `ActionsHandler.change_line_quantity(order_number, line_index, sku, quantity)` from Task 5.
- Produces: `ResultsBridge.lineQuantityChangeRequested: Signal(str, int, str, int)`; JS-callable slot `changeLineQuantity(order, index, sku, quantity)`; page element `#qty-menu` holding `input#line-qty`.

- [ ] **Step 1: Write the failing tests.**

In `tests/test_results_bridge.py`, add to the `("slot", "args", "signal")` parametrize list of `test_each_pane_verb_is_a_request_python_hears`:

```python
        ("changeLineQuantity", ("#1", 2, "SKU-A", 5), "lineQuantityChangeRequested"),
```

In `tests/test_results_screen.py`, add to the parametrize list of `test_each_pane_request_reaches_its_handler`:

```python
        (
            "lineQuantityChangeRequested",
            ("1001", 0, "A", 3),
            "change_line_quantity",
            ("1001", 0, "A", 3),
        ),
```

In `tests/test_results_pane.py`, after `test_remove_this_line_sends_the_index_and_its_sku` (line 1 of `#10445` is `TS-9002-C` with Quantity 2 in `pane_lines()`):

```python
def _open_qty_entry(qtbot, view):
    _select(qtbot, view, "#10445")
    _js(
        qtbot,
        view,
        "document.querySelector('#pane .line[data-index=\"1\"] .line-menu-button').click()",
    )
    _js(qtbot, view, _menu_item("line-menu", "Change quantity…"))


def _enter_qty(value):
    return (
        "(i => { i.value = %r; i.dispatchEvent(new KeyboardEvent('keydown', "
        "{key: 'Enter', bubbles: true})); })(document.getElementById('line-qty'))" % value
    )


def test_change_quantity_offers_the_lines_own_number(qtbot, doc):
    view, _ = doc
    _open_qty_entry(qtbot, view)
    assert _eval(qtbot, view, "document.getElementById('line-qty').value") == "2"
    assert _eval(qtbot, view, "document.activeElement.id") == "line-qty"


def test_change_quantity_sends_the_new_number(qtbot, doc):
    view, bridge = doc
    _open_qty_entry(qtbot, view)
    with qtbot.waitSignal(bridge.lineQuantityChangeRequested, timeout=3000) as blocker:
        _js(qtbot, view, _enter_qty("7"))
    assert list(blocker.args) == ["#10445", 1, "TS-9002-C", 7]
    assert _eval(qtbot, view, "document.querySelectorAll('.pane-menu').length") == 0


@pytest.mark.parametrize("value", ["2", "0", "-3", "2.5", ""])
def test_change_quantity_sends_nothing_for_a_non_change(qtbot, doc, value):
    view, bridge = doc
    _open_qty_entry(qtbot, view)
    with qtbot.assertNotEmitted(bridge.lineQuantityChangeRequested, wait=300):
        _js(qtbot, view, _enter_qty(value))
    assert _eval(qtbot, view, "document.querySelectorAll('.pane-menu').length") == 0
```

- [ ] **Step 2: Run to verify failures**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bridge.py tests/test_results_screen.py tests/test_results_pane.py -q -k "quantity or Quantity or pane_verb or pane_request"`
Expected: FAIL (`AttributeError: … lineQuantityChangeRequested` / no "Change quantity…" menu item).

- [ ] **Step 3: Implement the bridge.** In `gui/results_bridge.py`, under `lineRemovalRequested = Signal(str, int, str)`:

```python
    lineQuantityChangeRequested = Signal(str, int, str, int)
```

and after the `removeLine` slot:

```python
    @Slot(str, int, str, int)
    def changeLineQuantity(self, order_number, line_index, sku, quantity) -> None:
        self.lineQuantityChangeRequested.emit(
            str(order_number), int(line_index), str(sku), int(quantity)
        )
```

- [ ] **Step 4: Wire it.** In `gui/ui_manager.py`, after the `bridge.lineRemovalRequested.connect(...)` statement:

```python
        bridge.lineQuantityChangeRequested.connect(
            lambda n, i, s, q: actions().change_line_quantity(n, i, s, q)
        )
```

- [ ] **Step 5: Implement the page.** In `gui/web/pane.js::paneLines`, change the line menu items to:

```js
    more.addEventListener("click", () => openPaneMenu(more, "line-menu", [
      ["Remove this line", () => state.bridge.removeLine(order, index, sku)],
      ["Change quantity…", () => openQtyMenu(more, order, index, sku, line.Quantity)],
      ["Copy SKU", () => state.bridge.copyText(sku)],
    ]));
```

After `openTagMenu`, add:

```js
// Change quantity (spec 2026-09-28 §4.5): the page's own number entry, as the
// tag menu's "New tag" -- actions_handler holds no Qt input dialog. Only a
// whole number from 1 that differs from the line's own is sent.
function openQtyMenu(anchor, order, index, sku, current) {
  const own = num(current);
  const menu = newMenu("qty-menu");
  const input = el("input", "new-tag");
  input.id = "line-qty";
  input.type = "number";
  input.min = "1";
  input.step = "1";
  input.value = own === null ? "" : String(own);
  input.setAttribute("aria-label", "Quantity");
  input.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const n = input.value.trim() === "" ? NaN : Number(input.value);
    closePaneMenus();
    if (Number.isInteger(n) && n >= 1 && n !== own && state.bridge) {
      state.bridge.changeLineQuantity(order, index, sku, n);
    }
  });
  menu.append(input);
  placeMenu(menu, anchor);
}
```

`num`, `el`, `newMenu`, `placeMenu`, `closePaneMenus` already exist (`num` lives in `gui/web/results.js` and is global to the page — confirm by grepping `function num(`). The `new-tag` class already styles inputs inside `.pane-menu` (`gui/web/results.css:579`), so no CSS change. Esc and outside click already close any `.pane-menu` (`pane.js` ~line 315).

- [ ] **Step 6: Run**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bridge.py tests/test_results_screen.py tests/test_results_pane.py -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add gui/results_bridge.py gui/ui_manager.py gui/web/pane.js tests/test_results_bridge.py tests/test_results_screen.py tests/test_results_pane.py
git commit -m "feat: Change quantity in the pane's line menu"
```

---

### Task 7: ADR 0014, glossary, full gate

**Files:**
- Create: `docs/adr/0014-lot-labels-follow-quantity.md`
- Modify: `CONTEXT.md` (after the **Stock left** entry, ~line 88)

- [ ] **Step 1: Write the ADR** `docs/adr/0014-lot-labels-follow-quantity.md`:

```markdown
# 0014 — Lot labels follow Quantity

**Status:** Accepted, 2026-09-28
**Context:** `docs/superpowers/specs/2026-09-28-lot-labels-follow-quantity-design.md`

## Context

The run writes each line's FIFO lot allocation (`Lot_Details`) once. ADR 0010
made Stock left a function of the frame after every edit, but nothing kept
lot allocations in step with `Quantity`, and both report writers believed the
lots over the quantity. In REVE 2026-09-28_1, Add product copied another
line's allocation onto two new lines; the stock export wrote 3 for a line of
1 and dropped the other SKU. The packing list would have printed 3 for both.

## Decision

**`Quantity` is the truth; `Lot_Details` only labels it** (R3,
`shopify_tool/stock_ledger.lot_parts`, the only reader for output). Per pair —
one order's lines of one SKU — the pair's quantity is walked through its lots,
clipping each. Units the lots don't cover have no lot label (blank
Годност/Партида). Edit verbs never rewrite `Lot_Details`; Add product gives a
new line none. The stock export also refuses to write when its per-SKU totals
differ from the fulfillable lines.

Rejected: allocating real lots at edit time from the session's stock file.
Exact labels, but a second allocator that has to agree with the run's; the
owner chose blank labels (2026-09-28).

## Consequences

- An export's quantities can no longer disagree with the order lines, whatever
  edits came before. A future bug that tries is refused, not written.
- Units added by hand, raised later, or in an order marked fulfillable after
  the run go to the ERP without a lot; the storekeeper picks it.
- A lot is never named for more units than the run allocated from it: labels
  only shrink or disappear.
- Object identity of `Lot_Details` no longer matters (undo, pickle, JSON).
```

- [ ] **Step 2: Add the glossary entry** to `CONTEXT.md`, as a new paragraph directly after the **Stock left** entry:

```markdown
**Lot label** — the expiry and batch a report names for some of a line's
units. It comes from the run's FIFO allocation, fitted to the line's current
quantity (ADR 0014). Units the run never allocated — added by hand, raised
later, or in an order marked fulfillable after the run — have no lot label.
```

- [ ] **Step 3: Full gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all PASS (xfails stay xfail).
Run the lint CI uses — read `.github/workflows/build_release.yml` for the exact command (e.g. `.venv/bin/python -m ruff check .`) and run it. Expected: clean.

- [ ] **Step 4: Manual replay of the incident session (not committed; production data stays out of the repo)**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'EOF'
import pandas as pd, tempfile, os
from shopify_tool.stock_export import create_stock_export
df = pd.read_pickle(os.path.expanduser("~/Desktop/production info/2026-09-28_1/analysis/current_state.pkl"))
out = os.path.join(tempfile.mkdtemp(), "e.xls")
create_stock_export(df, out)
print(pd.read_excel(out, dtype={"Артикул": str})[["Артикул", "Брой"]])
EOF
```

Expected: `01PJ0001L 1` and `01PJ0001S 1` both present (plus the four other SKUs at 1). If the folder is absent on this machine, skip and say so in the handoff.

- [ ] **Step 5: Refresh the graph and commit**

```bash
graphify update .
git add docs/adr/0014-lot-labels-follow-quantity.md CONTEXT.md
git commit -m "docs: ADR 0014 lot labels follow Quantity; glossary"
```

(If `graphify update .` changes tracked files under `graphify-out/`, include them in this commit only if that directory is tracked — check `git status`.)
