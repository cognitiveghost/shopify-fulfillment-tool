# Packaging writeoff: count each tag once per order, not once per line item

Date: 2026-08-14
Todoist: `6hGq9FRQVpHFxf53` (p2) — "Bug: Packaging categories do write off from all
Internal Tags. It supposed to count only each unique tag from fulfillable order to
formulate a writeoff."
Milestone: `6hGqQ9fCPjM6qWjV` (p1) — "Revision, bug fixes, preparing for stable".

## The bug, in one sentence

`calculate_writeoff_quantities()` accumulates a tag's packaging quantity **once per
DataFrame row**, but `Internal_Tags` is an *order-level* field replicated across every
line of the order — so an order with three SKU lines writes off three boxes.

## Evidence (measured, not read)

Probe against `shopify_tool/sku_writeoff.py` at `6181bf6`, two fulfillable orders — order
1001 with three line items, order 1002 with one, both tagged `BOX`, mapping
`BOX → PKG-BOX ×1.0`:

```
       SKU  Writeoff_Quantity Tags_Applied  Order_Count
0  PKG-BOX                4.0        [BOX]            2
```

**4.0 boxes for 2 orders.** Expected 2.0.

Note `Order_Count` is already correct — it accumulates into a `set`. So the existing
report is *internally self-contradictory*: it states two orders and four boxes on the
same row. That inconsistency is the visible symptom the bug report describes.

Second probe — one order (three lines) carrying two tags that both map to the same SKU
(`BOX → PKG-SEAL ×1`, `BAG → PKG-SEAL ×1`):

```
        SKU  Writeoff_Quantity Tags_Applied  Order_Count
0  PKG-SEAL                6.0   [BAG, BOX]            1
```

**6.0 for one order.** Expected 2.0 — two distinct tags applied once each. This case
pins the dedup key: it must be **(order, tag)**, not (order, SKU). Deduping on SKU would
give 1.0 here and be a *different* wrong answer.

## Root cause

`shopify_tool/sku_writeoff.py:153-180`. The loop is `for idx, row in rows_df.iterrows()`
over a **line-item-level** DataFrame. `writeoff_accumulator[sku]["orders"]` is a set (so
`Order_Count` self-corrects) but `["quantity"] += quantity` runs unconditionally on every
row.

That `Internal_Tags` is order-level is not an inference — it is documented in this repo,
in `shopify_tool/tag_manager.py:132`:

> `Internal_Tags` is order-level, not line-level, but `df` has one row per order line

And `shopify_tool/analysis.py:1606-1637` already implements the correct reading for the
stats panel, commented "counted per unique order", via parse → explode → `drop_duplicates`
→ `value_counts`. **The writeoff module is the only consumer that gets this wrong.**

## Blast radius — one function, three callers, no sibling bugs

Every caller passes a line-item DataFrame, so all three are affected and all three are
fixed by the single change:

| caller | passes |
|---|---|
| `shopify_tool/stock_export.py:249` | `filtered_items` (line items, pre-filtered to Fulfillable) |
| `shopify_tool/core.py:1555` | full `analysis_df` |
| `gui/actions_handler.py:936` | `self.mw.analysis_results_df` |

`grep parse_tags` across `shopify_tool/` and `gui/` returns exactly one other accumulating
consumer — `analysis.py`, which already dedups. The rest (`tag_delegate.py`,
`tag_management_panel.py`, `ui_manager.py`, `actions_handler.py:1718`) are display or edit
paths where per-row parsing is correct. **No second instance of this bug exists.** One
guard in the shared function is the root-cause fix.

## The fix

Deduplicate `(Order_Number, tag)` pairs before accumulating quantity. Reuse the
established `analysis.py` idiom (parse → explode → `drop_duplicates`) rather than
inventing a second one, so the two modules that must agree on "per unique order" stay
visibly written the same way.

`Tags_Applied` and `Order_Count` keep their current semantics — they are already correct
and must not regress.

## Fulfillable filtering — already correct, leave alone

`sku_writeoff.py:146-150` pre-filters to `Order_Fulfillment_Status == "Fulfillable"` when
the column is present. The bug report's phrase "from fulfillable order" is already
satisfied; this is not part of the defect. Do not touch it — but do keep the behaviour
under test so the fix cannot silently drop it.

## Decisions taken without asking (reversible, noted for the record)

- **Missing `Order_Number` column.** The existing fallback synthesizes `f"row_{idx}"` per
  row, which post-fix means no deduplication happens at all. Kept as-is — it is the only
  defensible reading when order identity is unavailable — but it now logs a warning, since
  silently returning line-multiplied quantities is what caused this bug in the first place.
- **No quantity scaling with order size.** One application per (order, tag), flat. The bug
  report specifies "each unique tag from fulfillable order"; a large order needing two
  boxes is a mapping-configuration concern, not this fix.
- **No config-format or mapping-schema change.** `_extract_writeoff_mappings()` is not
  touched.

## Non-goals

- Redesigning the writeoff UI or the mapping editor.
- The Packing list & Stock Export settings redesign (Todoist `6h8v4VxRHVq7MrGV`) — separate
  queued task.
- Reconciling stock exports **already sent to the ERP**. See below.

## Operational note for the release note — read this

This bug has been over-writing off packaging materials in production for as long as the
feature has shipped, by a factor equal to the average line-item count per order. ERP stock
levels for packaging SKUs are therefore **understated**, and no code change corrects data
already exported. Someone should decide whether a one-off reconciliation is warranted; the
per-SKU inflation factor is recoverable from any past session's analysis file by comparing
`Order_Count` against `Writeoff_Quantity` in the writeoff report, which is exactly the
self-contradiction described above.

Flagging, not fixing — a data-correction pass is the user's call, not this PR's.

## Test coverage gap (the reason this survived)

`shopify_tool/sku_writeoff.py` is 518 lines of stock-deduction arithmetic with **zero
tests** — `tests/` contains no `test_sku_writeoff.py` and no test references the module.
The module's own docstring examples encode the bug: every example uses a
one-row-per-order DataFrame, the single shape where per-row and per-order accumulation
agree. That is why reading the file does not reveal the defect and the probe does.

This PR adds the missing test file. Its first case must use a **multi-line order**, or it
reproduces the blind spot it exists to close.
