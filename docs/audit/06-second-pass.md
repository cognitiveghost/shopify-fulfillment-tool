# Audit 06 — Second pass over the data layer: order info and maths

Scope: the Phase 14 fixes (`stock_ledger.py`, `fulfillment_history.py`, the
edit verbs in `gui/actions_handler.py`, `core._settle_rule_changes`), plus the
maths the first audits read but never tested: `weight_calculator.py` (volumetric
weight, box fit), `sku_writeoff.py`, `set_decoder.py` quantities,
`analysis.recalculate_statistics`, `analysis._generate_summary_reports`,
`stock_export.py` and `packing_lists.py` lot handling, `core.build_inventory_snapshot`,
`core.build_packing_order_data`. Proof tests: `tests/audit/test_06_second_pass.py`
(written by the fix plan, red first). Audited against `origin/main` at `f90365f`,
after Phase 14 Bundle 5 (#343). Replayed on the production copy
(`~/Desktop/production info`, 40 session states, 3 client configs).

The Packing Tool half of this pass is `packing-tool/docs/audit/03-second-pass.md`.

## 1. Verdict

**Stock left, statuses and history are right. Lot details are not.** The
stock ledger (ADR 0010) re-derives Stock left after every edit, and the replay
agrees with it in all 40 sessions. But `Lot_Details`, the per-line expiry/batch
allocation that the stock export and the printed packing list read, is still
written once at run time and copied around by reference afterwards. Adding a
product copies another line's allocation, and so does a rule bonus line. Removing
one of two same-SKU lines leaves the whole allocation on the other, and an order
made fulfillable after the run has none. **This reached production today.** The
REVE 2026-09-28_1 stock export writes off 3 × 01PJ0001L and nothing of 01PJ0001S,
for an order holding 1 of each (AUDIT-06-1).

The other order-level columns (`Order_Type`, weights, box, `Stock_Alert`) are
also frozen at run time. The maths inside each function checks out.

## 2. Findings

| id | severity | summary | where | proof test | status |
|---|---|---|---|---|---|
| AUDIT-06-1 | high | `Lot_Details` doesn't follow edits: an added line (by hand or by rule) shares another line's allocation, a removed duplicate line leaves its allocation behind, and an order made fulfillable after the run has none. The stock export and the printed packing list then write off or print the wrong SKU, lot or quantity | `gui/actions_handler.py:1335`, `rules.py:1332`, `stock_export.py:107`, `packing_lists.py:40`, `analysis.py:1099` | `test_an_added_line_exports_its_own_sku_and_quantity`, `test_removing_one_of_two_same_sku_lines_exports_the_other_only`, `test_an_order_made_fulfillable_after_the_run_exports_with_its_lots`, `test_packing_list_prints_each_lines_own_quantity` | fixed |
| AUDIT-06-2 | medium | `Order_Type`, `Order_Volumetric_Weight`, `Order_Min_Box`, `All_No_Packaging`, `SKU_Volumetric_Weight` and `Stock_Alert` are computed at run time only. Add product, remove item, rule bonus lines and holds leave them stale; an added line even carries its template's per-SKU weight | `analysis.py:1005`, `weight_calculator.py:261`, `core.py:919` | `test_order_type_follows_added_and_removed_lines`, `test_box_and_weight_follow_an_added_line`, `test_stock_alert_follows_a_hold` | fixed |
| AUDIT-06-3 | medium (latent) | The inventory-memory snapshot keys opening stock by the raw stock-file SKU and Stock left by the normalised one; a SKU with stray spaces is remembered twice and the next memory run adds the two | `core.py:1018-1040` | `test_inventory_snapshot_keys_are_normalised_skus` | fixed |
| AUDIT-06-4 | medium | A set whose component is itself a set is expanded one level only, so the order asks for the inner set's SKU, which is not in stock | `set_decoder.py:83-111` | `test_a_nested_set_expands_to_its_inner_components`, `test_a_set_that_lists_itself_is_not_expanded_again` | fixed |
| AUDIT-06-5 | low | `Summary_Missing` compares each line with opening stock, not demand per SKU with Stock left. `Summary_Present` and the run's saved stats are computed before rules run | `analysis.py:1219-1227`, `:1494`, `core.py:874` | `test_run_report_has_no_summary_missing_sheet`, `test_summary_present_and_stats_follow_rule_holds` | fixed |
| AUDIT-06-6 | low | AUDIT-01-12 is not fixed. Undo history still can't be saved once `Lot_Details` holds `datetime.date` values; the strict xfail test still fails | `analysis.py:737`, `undo_manager.py:455` | `tests/audit/test_01_intake_analysis.py::test_undo_history_survives_reopen_for_lot_tracked_stock` (xfail marker comes off) | fixed |
| AUDIT-06-7 | medium | Expiry parsing orders lots wrongly: a 4-digit YYMM expiry (`2805`) fails as MMYY and sorts as "no expiry" (last); a 6-digit expiry with day `00` (`261200`) fails as YYMMDD and falls through to DDMMYY, reading as 2000-12-26 (first) | `analysis.py:76-134` | `test_yymm_and_day_zero_expiries_sort_by_their_real_month` | fixed |

## 3. Findings in detail

### AUDIT-06-1 — Lot details don't follow edits (high)

**What goes wrong.** The run allocates lots per (order, SKU) and stores one list
object on every row of that pair (`analysis.py:1099`). Both consumers dedupe on
that sharing: the stock export by object identity (`stock_export.py:107`), the
packing list by (order, SKU) (`packing_lists.py:40`). Every edit after the run
breaks the assumption:

- **Add product** copies the order's first row (`actions_handler.py:1335`).
  `Series.copy()` doesn't copy the list, so the new line shares another SKU's
  allocation. The export skips it as already seen, so the new SKU is never
  written off. The packing list prints it with the other SKU's quantity.
- **Rule `ADD_PRODUCT`** does the same via `df.loc[idx].to_dict()`
  (`rules.py:1332`). No production client uses it today.
- **Remove item** on one of two lines of one SKU leaves the other line holding
  the pair's whole allocation. Both files then count the removed units.
- **Mark fulfillable / bulk / undo of a hold** on an order the run blocked:
  its rows have `Lot_Details = None`. The export writes them with blank expiry
  and batch, even for SKUs that have real lots.

**Production evidence.**
- **REVE 2026-09-28_1**, order #1221. The operator removed its four original
  lines and added 1 × 01PJ0001L and 1 × 01PJ0001S. Both added lines share the
  removed L line's allocation (qty 3). The saved export
  `all_reve_2026-09-28_1417.xls` has `01PJ0001L 3` and no 01PJ0001S. A packing
  list generated now would print 3 × L and 3 × S.
- **WATERDROP 2026-07-20_3**, order #BG6997. The added DW-SW-ST10-00011 shares
  DW-CL-PP01-00021's allocation. The saved export wrote it under the other SKU's
  expiry (301231). Today's code would drop it from the export altogether.
- **ALMADERM** 2026-07-01_1, -07-01_2, -07-02_2, -07-09_1 and **HERBAR**
  2026-07-16_1: 7 to 126 fulfillable rows with no lots, from orders toggled
  fulfillable after the run. Up to 4 of those SKUs per session have real expiry
  dates.

**Root cause.** Lot allocation is state written once. Stock left had the same
problem and was made derived (ADR 0010); lots were left out (Phase 14 Bundle 1
spec §6, "Lot details after edits").

### AUDIT-06-2 — Order-level columns are frozen at run time (medium)

`Order_Type` comes from `item_count` at merge time (`analysis.py:1005`). The
weight columns come from `enrich_dataframe_with_weights`, run once before rules
(`core.py:903`), and `Stock_Alert` from `_add_stock_alert` (`core.py:919`). No
edit verb recomputes them. Consumers: packing-list filters (ALMADERM's
`Masks_Only` list filters `Order_Type == Single`), the Packing Tool payload
(`order_type`, `order_min_box`, `core.py:124,174`), the results table and the
rule test dialog. The replay found no stale `Order_Type` in production today, so
this is latent. An added line also keeps the template row's
`SKU_Volumetric_Weight`, which is another SKU's.

### AUDIT-06-3 — Inventory snapshot counts a SKU twice (medium, latent)

`build_inventory_snapshot` seeds from `stock_df["SKU"]` as read from the file,
then overwrites with `final_df`'s normalised SKUs. For `"S-EX06-2MD "` (it is in
every WATERDROP stock file) the snapshot is
`{"S-EX06-2MD ": 5, "S-EX06-2MD": 3}`. The next memory-mode run normalises and
sums both keys, giving 8 instead of 3. `inventory_total_units` has the same
grouping. Inventory memory is off for all three clients today.

### AUDIT-06-4 — Nested sets (medium)

`decode_sets_in_orders` makes one pass. WATERDROP's `S-TG06-BO-6DK3L2` contains
`DW-BT-GL06-00007`, which is itself a set (→ `DW-GB-GL06-00003`). Neither set
SKU is in any WATERDROP stock file, so such an order is held "out of stock".
HERBAR has the other shape: `NECTAR-30` lists itself plus a dropper. Its six
parent sets each list `NECTAR-DROPPER` explicitly, so expanding `NECTAR-30`
inside them would double the dropper. Owner decision (§6): expand nested sets,
except a set that lists itself.

### AUDIT-06-5 — Run summaries (low)

`Summary_Missing` keeps lines whose own quantity exceeds the SKU's opening
stock. A SKU short only in aggregate (three orders of 2 against stock 5) is
absent, and a NO_SKU line (stock 0) is listed. Owner decision: remove the sheet.
`Summary_Present` and the stats written to `analysis_stats.json` are computed in
`run_analysis`, before `engine.apply` and `_settle_rule_changes`. The GUI
recomputes stats on the first refresh, but the XLSX sheet keeps the pre-rule
figures.

### AUDIT-06-6 — AUDIT-01-12 is still open (low)

Phase 14 Bundle 2 converted `_save_history` to `atomic_write_json` but did not
touch the cause: `expiry_dt` is a `datetime.date`, which `json` can't encode, so
`_save_history` logs and saves nothing. The audit-01 proof test is still
`xfail(strict=True)` and still fails (`--runxfail`:
`TypeError: Object of type date is not JSON serializable`).

### AUDIT-06-7 — Expiry formats (medium)

`_parse_expiry_date` tries YYMMDD then DDMMYY for 6 digits, and only MMYY for 4
digits. The latest stock files contain formats it gets wrong:
- **ALMADERM** has 2 lots with 4-digit YYMM expiries (`2805`, `2706`). MMYY
  rejects month 28, so they get no date and FIFO consumes them last, whatever
  their month.
- **WATERDROP** has 3 lots with 6-digit expiries whose day is `00` (`261200`,
  December 2026). YYMMDD rejects day 0 and DDMMYY accepts it as 2000-12-26, so
  FIFO consumes these first.
- **WATERDROP** also has 17 two-digit, 1 three-digit, 2 five-digit and a few
  other unparsable values. Those are data errors and are left as they are.

The replay shows the effect. WATERDROP 2026-07-22_1 now gives the `261200` lot
of AI-WA-MX01-00041 to #BG7496 before the `2701` lot.

**Fix (agent decision, reversible).** For 4 digits, try MMYY, then YYMM. For 6
digits with day `00`, read YYMM and day 1 before trying DDMMYY. Every other
value parses as before.

## 4. Verified correct

- **Stock ledger** (R1, R2): `fulfillable_orders`, `stock_left`, `shortfall`,
  `claim_detail`, `with_stock_left`. Negative and unlisted SKUs behave as the
  spec says. All 40 production states re-derive without error.
- **Toggle and bulk claim** check Stock left with the order's own draw released.
- **Fulfillment history**: `record_session` replaces only its session's rows
  under the lock, keeps first-seen dates, and never writes over an unreadable file.
- **Weights**: volumetric = L×W×H / divisor per unit × quantity. The 6-rotation
  fit is sorted-dimension comparison. The sentinels match the owner's rule
  (audit 04 §5).
- **Writeoff**: one application per (order, tag), fulfillable rows only;
  quantities round half up (`_to_erp_quantity`).
- **Set decoding**: component quantity = line quantity × component quantity,
  and invalid components are skipped with the line kept.
- **Stock export SKU totals** equal the fulfillable quantities (lot-less path).
- **Replay**: the export's total units equal the fulfillable line quantities in
  38 of 40 sessions. The two that differ are the AUDIT-06-1 sessions.

## 5. Observations, no change

- A manual toggle leaves the run's `Cannot fulfill: …` in `System_note`. That
  is by design: `orders_view.order_verdict` reads it as `by_hand`.
- A SKU missing from the stock file can be force-fulfilled (audit 01 §7).
- A tag mapped in two enabled writeoff categories: the later mapping wins
  (`sku_writeoff.py:539`). No client has one.
- `sku_writeoff.apply_writeoff_to_stock_export` has no caller.

## 6. Owner decisions (2026-09-28)

- **Lots → derived like Stock left** (ADR 0014).
- **Summary_Missing → removed.**
- **Nested sets → expanded**, except a set that lists itself (HERBAR
  `NECTAR-30`), which stays one level so its parents don't double the dropper.

## 7. Operational note

REVE 2026-09-28_1's export (`all_reve_2026-09-28_1417.xls`) is wrong as
described in AUDIT-06-1. After the fix ships, reopen the session and generate
its stock export and packing list again. Or correct the ERP import by hand:
01PJ0001L 1, 01PJ0001S 1.
