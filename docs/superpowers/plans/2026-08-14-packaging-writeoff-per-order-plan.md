# Plan — Packaging writeoff: count each tag once per order

Spec: `docs/superpowers/specs/2026-08-14-packaging-writeoff-per-order-design.md`
Branch: `worktree-packaging-writeoff-per-order`
Todoist: `6hGq9FRQVpHFxf53`

Three tasks. TDD: the tests land first and **must be observed failing** before the fix.

Every code block below was executed against this branch's `6181bf6` base before being
written down — but treat it as a verified draft, not gospel. If it does not behave as
described, the code wins.

---

## Task 1 — Add `tests/test_sku_writeoff.py`, red

The module has no tests today. Create the file with the cases below and **run it, and
paste the failures into the commit or the Stage B report**. Cases 1 and 2 must fail;
3-6 must pass on unfixed code (they pin behaviour the fix must not break).

Shared fixture — a *multi-line* order is the point; a one-row-per-order fixture
reproduces the exact blind spot that let this bug ship.

```python
import pandas as pd
import pytest

from shopify_tool.sku_writeoff import calculate_writeoff_quantities


def _config(mappings, enabled=True):
    return {
        "version": 2,
        "categories": {
            "packaging": {
                "tags": list(mappings),
                "sku_writeoff": {"enabled": enabled, "mappings": mappings},
            }
        },
    }


BOX_ONLY = _config({"BOX": [{"sku": "PKG-BOX", "quantity": 1.0}]})
```

**Case 1 — the bug.** Order 1001 has three line items, order 1002 has one; both tagged
`BOX`. Expect `2.0`, unfixed code gives `4.0`.

```python
def test_tag_counts_once_per_order_not_once_per_line_item():
    df = pd.DataFrame({
        "Order_Number": [1001, 1001, 1001, 1002],
        "SKU": ["A", "B", "C", "A"],
        "Order_Fulfillment_Status": ["Fulfillable"] * 4,
        "Internal_Tags": ['["BOX"]'] * 4,
    })
    result = calculate_writeoff_quantities(df, BOX_ONLY)
    row = result[result["SKU"] == "PKG-BOX"].iloc[0]
    assert row["Writeoff_Quantity"] == 2.0
    assert row["Order_Count"] == 2
```

**Case 2 — the dedup key is (order, tag), not (order, SKU).** One order, three lines, two
distinct tags both mapping to `PKG-SEAL`. Expect `2.0`. Unfixed gives `6.0`; a
dedupe-on-SKU fix would give `1.0` — this case is what separates the correct fix from
the plausible wrong one, so **do not drop it**.

```python
def test_two_tags_mapping_to_same_sku_each_count_once():
    cfg = _config({
        "BOX": [{"sku": "PKG-SEAL", "quantity": 1.0}],
        "BAG": [{"sku": "PKG-SEAL", "quantity": 1.0}],
    })
    df = pd.DataFrame({
        "Order_Number": [1001, 1001, 1001],
        "Order_Fulfillment_Status": ["Fulfillable"] * 3,
        "Internal_Tags": ['["BOX", "BAG"]'] * 3,
    })
    result = calculate_writeoff_quantities(df, cfg)
    assert result[result["SKU"] == "PKG-SEAL"].iloc[0]["Writeoff_Quantity"] == 2.0
```

**Case 3 — non-fulfillable orders are excluded** (passes unfixed; guards a real
behaviour the spec says not to touch).

```python
def test_non_fulfillable_orders_are_excluded():
    df = pd.DataFrame({
        "Order_Number": [1001, 1002],
        "Order_Fulfillment_Status": ["Fulfillable", "Not Fulfillable"],
        "Internal_Tags": ['["BOX"]'] * 2,
    })
    result = calculate_writeoff_quantities(df, BOX_ONLY)
    assert result[result["SKU"] == "PKG-BOX"].iloc[0]["Writeoff_Quantity"] == 1.0
```

**Case 4 — one tag mapping to several SKUs still applies all of them, once each.**

```python
def test_multiple_skus_per_tag_all_applied_once():
    cfg = _config({"BOX": [
        {"sku": "PKG-BOX", "quantity": 1.0},
        {"sku": "PKG-TAPE", "quantity": 2.0},
    ]})
    df = pd.DataFrame({
        "Order_Number": [1001, 1001],
        "Order_Fulfillment_Status": ["Fulfillable"] * 2,
        "Internal_Tags": ['["BOX"]'] * 2,
    })
    result = calculate_writeoff_quantities(df, cfg).set_index("SKU")
    assert result.loc["PKG-BOX", "Writeoff_Quantity"] == 1.0
    assert result.loc["PKG-TAPE", "Writeoff_Quantity"] == 2.0
```

**Case 5 — disabled category writes off nothing.**

```python
def test_disabled_category_produces_no_writeoff():
    df = pd.DataFrame({
        "Order_Number": [1001],
        "Order_Fulfillment_Status": ["Fulfillable"],
        "Internal_Tags": ['["BOX"]'],
    })
    cfg = _config({"BOX": [{"sku": "PKG-BOX", "quantity": 1.0}]}, enabled=False)
    assert calculate_writeoff_quantities(df, cfg).empty
```

**Case 6 — degenerate inputs keep the documented empty shape.** Empty frame, and a frame
with no `Internal_Tags` column.

```python
@pytest.mark.parametrize("df", [
    pd.DataFrame(),
    pd.DataFrame({"Order_Number": [1], "Order_Fulfillment_Status": ["Fulfillable"]}),
])
def test_degenerate_inputs_return_empty_with_correct_columns(df):
    result = calculate_writeoff_quantities(df, BOX_ONLY)
    assert result.empty
    assert list(result.columns) == [
        "SKU", "Writeoff_Quantity", "Tags_Applied", "Order_Count",
    ]
```

---

## Task 2 — Fix `calculate_writeoff_quantities`

`shopify_tool/sku_writeoff.py`. Replace the row loop at **lines 152-180** (from the
`# Process each row` comment through the `writeoff_accumulator[sku]["orders"].add(...)`
line). Leave lines 128-150 (guards, mapping extraction, the Fulfillable pre-filter) and
everything from line 182 (`# Convert to DataFrame`) onward untouched.

The `has_status_col` local becomes unused once the loop is replaced — either keep using it
or delete it, but do not leave it dangling; `ruff` will flag it.

```python
    # Internal_Tags is order-level, but rows_df has one row per order LINE
    # (see tag_manager.expand_to_order_rows). Dedupe (order, tag) so each tag
    # is counted once per order -- matching how analysis.py builds its tags
    # breakdown. Accumulating per row multiplies every writeoff by the order's
    # line count.
    if "Order_Number" in rows_df.columns:
        order_col = rows_df["Order_Number"].astype(str)
    else:
        logger.warning(
            "Order_Number column missing - writeoff cannot deduplicate per order; "
            "quantities will be counted per row"
        )
        order_col = pd.Series(
            [f"row_{i}" for i in rows_df.index], index=rows_df.index
        )

    order_tags = (
        pd.DataFrame({
            "order": order_col,
            "tag": rows_df["Internal_Tags"].fillna("[]").apply(parse_tags),
        })
        .explode("tag")
        .dropna(subset=["tag"])
        .drop_duplicates()
    )

    for pair in order_tags.itertuples(index=False):
        if pair.tag not in writeoff_mappings:
            continue

        for mapping in writeoff_mappings[pair.tag]:
            sku = mapping["sku"]

            if sku not in writeoff_accumulator:
                writeoff_accumulator[sku] = {
                    "quantity": 0.0,
                    "tags": set(),
                    "orders": set(),
                }

            writeoff_accumulator[sku]["quantity"] += mapping["quantity"]
            writeoff_accumulator[sku]["tags"].add(pair.tag)
            writeoff_accumulator[sku]["orders"].add(pair.order)
```

### Verified behaviour of that snippet (measured on this base)

| input | result |
|---|---|
| 2 orders (3 lines + 1 line), both `["BOX"]` | `1001/BOX`, `1002/BOX` — 2 pairs |
| same rows, `["BOX","BAG"]` | 4 pairs — each order × each tag |
| empty frame | 0 rows, columns `['order','tag']` intact |
| no `Order_Number` column | falls back to `row_0..row_3`, warning logged |
| `'[]'`, `None`, `'["BOX"]'`, `'[""]'` | only `BOX` and an **empty-string tag** survive |

**On that empty-string tag:** `analysis.py` filters it out explicitly; here it needs no
filter, because `if pair.tag not in writeoff_mappings: continue` already discards it. Do
not add a length filter for symmetry — it is dead code. (Noted so review does not raise
it as a finding.)

**On the duplicated index:** `.explode()` repeats index labels (`0, 0, 3, 3`).
`itertuples(index=False)` never reads the index, so this is fine — do not "fix" it with a
`reset_index()`.

**On `astype(str)`:** matches the old code's `str(order_number)`, so `Order_Count` keeps
its exact current semantics. A NaN order number becomes `"nan"` — pre-existing behaviour,
not a regression, out of scope.

---

## Task 3 — Green, then the full gate

1. Re-run `tests/test_sku_writeoff.py`; all six cases pass.
2. Full gate, from the worktree root:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

`main` was **634 passed** at `6181bf6`; expect 634 + the new cases, with **no test newly
failing**. If any existing test breaks, stop — it means something depended on the inflated
quantities, which the spec did not predict and which changes the story.

3. `graphify update .` in the worktree.

Commit spec, plan, test and fix together.

---

## Definition of done

- [ ] Cases 1 and 2 observed failing before the fix, and reported as such.
- [ ] All six pass after.
- [ ] Full suite green, no pre-existing test regressed.
- [ ] `ruff` clean (watch the `has_status_col` local).
- [ ] Spec's ERP-reconciliation note carried into the PR body — the user must see it.
