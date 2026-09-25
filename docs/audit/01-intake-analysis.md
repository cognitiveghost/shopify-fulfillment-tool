# Audit 01 — Order data intake → core analysis → bulk operations

Scope: `core.py` (load, validate, run), `analysis.py`, `csv_utils.py`,
`set_decoder.py`, `undo_manager.py`, `report_filters.py`,
`gui/actions_handler.py` (single and bulk edits), `gui/file_handler.py`
(folder merge), and the column mappings. Proof tests:
`tests/audit/test_01_intake_analysis.py`. Audited against `origin/main` at
`dea02be`.

## 1. Verdict

**The run is reliable. The edits made after it are not.** Every order line
in the export reaches the analysis with its quantity, and the fulfillable or
blocked decision matches the stock file. I re-ran the analysis on all 39
production sessions and compared it with what each one saved. Lines and
quantities matched in all 39. Statuses matched in 38, and the 39th differs only
because its client's strategy has changed since that run.

Once a person edits the result, **Stock left** (`Final_Stock`) stops being
trustworthy. Adding a product to an order, undoing a status toggle, a bulk
status change, and removing an order each leave it wrong, and every Mark
fulfillable checks against it. Four more bugs are latent: the three production
clients' files don't trigger them today. One of those four is critical:
without lot columns, a blank stock cell counts as unlimited stock.

Nothing found here corrupts persisted inventory. Inventory memory is written
at run time, before any edit.

## 2. Findings

| id | severity | summary | where | proof test | status |
|---|---|---|---|---|---|
| AUDIT-01-1 | high | Adding a product to a fulfillable order re-checks and re-deducts its existing lines, so it can flip to blocked | `gui/actions_handler.py:1389` | `test_add_product_to_fulfillable_order_keeps_it_fulfillable` | confirmed |
| AUDIT-01-2 | high | Undoing a status toggle restores the status but not Stock left | `shopify_tool/undo_manager.py:245` | `test_undo_of_toggle_restores_stock_left` | confirmed |
| AUDIT-01-3 | high | Bulk Hold / Mark fulfillable never moves Stock left; the single-order path does | `gui/actions_handler.py:1506` | `test_bulk_hold_moves_stock_left_like_single_hold` | confirmed |
| AUDIT-01-4 | high | Removing a fulfillable order or line doesn't return its stock to Stock left | `gui/actions_handler.py:1114`, `:1764` (also `:1076`, `:1656`, `:1714`) | `test_removing_fulfillable_order_returns_its_stock` (×2) | confirmed |
| AUDIT-01-5 | high | An order whose first line has no SKU reads as blocked. Hold does nothing, and toggle deducts the stock a second time | `shopify_tool/analysis.py:1778`, root `:1104` | `test_toggle_holds_a_fulfillable_order_whose_first_line_has_no_sku` | confirmed |
| AUDIT-01-6 | low | A fulfillable order with a no-SKU line counts as both completed and not completed | `shopify_tool/analysis.py:1601` | `test_stats_count_each_order_once` | confirmed |
| AUDIT-01-7 | critical (latent) | Without lot columns, a blank stock cell counts as unlimited stock | `shopify_tool/analysis.py:647` | `test_blank_stock_cell_is_not_unlimited_stock` | confirmed |
| AUDIT-01-8 | high (latent) | Without lot columns, a SKU on two stock rows keeps only the first; with lot columns both rows are summed | `shopify_tool/analysis.py:462` | `test_duplicate_stock_rows_count_the_same_with_or_without_lot_columns` | confirmed |
| AUDIT-01-9 | low | Lines above the first order number drop out of the result with no warning | `shopify_tool/analysis.py:1031` | `test_no_order_line_silently_disappears` | confirmed |
| AUDIT-01-10 | low | Set CSV import reads SKUs as numbers: `0042` becomes `42` | `shopify_tool/set_decoder.py:180` | `test_set_import_keeps_sku_text` | confirmed |
| AUDIT-01-11 | low | Undoing a removal appends the rows at the end, so the order moves in the table | `shopify_tool/undo_manager.py:371` | `test_undo_of_removed_order_restores_row_order` | confirmed |
| AUDIT-01-12 | low | Undo history can't be saved once rows carry lot details, so reopening a session loses it | `shopify_tool/undo_manager.py:415` | `test_undo_history_survives_reopen_for_lot_tracked_stock` | confirmed |

"Latent" means the defect is real but no production client's files trigger it
today (see each finding).

## 3. Findings in detail

### AUDIT-01-1 — Add product double-deducts and can block a fulfillable order (high)

**What goes wrong.** `_add_product_to_order` appends the new line and then
calls `_recalculate_order_fulfillment`. That function checks **every** line of
the order against the current Stock left. For an order that was already
fulfillable, Stock left has already had that order's own units taken out. The
check therefore asks for them a second time. If it passes, the function
deducts them a second time too.

**Scenario.** Stock A = 2, B = 10. Order #1 wants 2 × A, so it is fulfillable
and A's Stock left is 0. Add 1 × B to #1. The check finds that A needs 2 and
has 0, so #1 becomes **Not Fulfillable** although nothing changed for A. If A
had had spare units, #1 would stay fulfillable and A's Stock left would drop
by 2 more.

**Root cause.** It recomputes the whole order from a stock figure that already
has the order's allocation taken out. It also checks line by line, not SKU by
SKU, so two lines of the same SKU are each checked against the full amount.
When an order goes from fulfillable to blocked, its stock is not returned.

**Production evidence.** No production session's saved state contains a
manual addition, so there is no count.

### AUDIT-01-2 — Undo of a status toggle leaves Stock left changed (high)

**What goes wrong.** `toggle_order_fulfillment` changes both the status and
Stock left. Hold returns units and Mark fulfillable draws them.
`_undo_toggle_status` restores only `Order_Fulfillment_Status`.

**Scenario.** Stock A = 5 and #1 wants 2, so Stock left is 3. Hold #1 and
Stock left becomes 5. Undo, and #1 is fulfillable again, but Stock left stays
at 5. Another order can now be marked fulfillable against 2 units that don't
exist.

**Root cause.** The undo record holds only the order's own rows, and the undo
handler writes back only the status. The toggle also changed Stock left on
every row of that SKU, including rows in other orders.

**Production evidence.** ALMADERM 2026-07-01_2 saved 13 toggles and 3 bulk
status changes. In its edited state, 12 SKUs have a Stock left that no longer
equals opening stock minus the fulfillable lines. This finding and
AUDIT-01-3 both produce that pattern.

### AUDIT-01-3 — Bulk status change doesn't move Stock left (high)

**What goes wrong.** `bulk_change_status` only rewrites the status text. Bulk
Hold does not return units. Bulk Mark fulfillable neither checks Stock left
nor draws on it. The single-order path, `toggle_order_fulfillment`, does both.
The same intent therefore leaves a different Stock left depending on whether
one order or many were selected.

**Scenario.** Stock A = 5. #1 wants 2 and #2 wants 1, so Stock left is 2.
Holding #1 on its own gives 4. Holding it through the selection bar leaves 2.

**Rule for the fix (owner, §6).** Bulk Mark fulfillable draws on Stock left
as the single path does, marks only the orders it covers, and says in the
toast how many it skipped. The proof test checks Hold, where both paths
should obviously agree.

**Production evidence.** ALMADERM 2026-07-01_2 (see AUDIT-01-2). HERBAR
2026-07-22_1 and 2026-07-23_1 also used bulk status changes.

### AUDIT-01-4 — Removing a fulfillable order keeps its stock allocated (high)

**What goes wrong.** Five verbs delete rows without returning the stock those
rows had allocated: Remove order, Remove this line, bulk Exclude, bulk Remove
SKU, and bulk Remove orders containing a SKU. The removed order has left the
run, but its units stay out of Stock left.

**Scenario.** Stock A = 3. #1 wants 2 (fulfillable) and #2 wants 2 (blocked),
so Stock left is 1. Exclude #1. Stock left stays 1, so Mark fulfillable on #2
is refused although 3 units are free.

**Root cause.** The removal paths drop rows and never touch `Final_Stock`.

**Production evidence.** WATERDROP 2026-07-20_3: one saved `remove_item` left
3 SKUs whose Stock left disagrees with opening stock minus the fulfillable
lines.

### AUDIT-01-5 — A no-SKU first line makes an order read as blocked (high)

**What goes wrong.** The run marks each no-SKU line (fee, custom item) as
`Not Fulfillable` on its own row. The order's other lines can still be
`Fulfillable` (`analysis.py:1104`). Several readers then take the order's
status from its **first row**:

- `toggle_order_fulfillment` (`analysis.py:1778`) takes a fulfillable order
  for a blocked one and "force-fulfills" it. That deducts its stock a second
  time.
- `set_order_fulfillable` (`actions_handler.py:953`) sees the order as
  already held, so the pane's Hold is a silent no-op.
- The verdict in `order_payload` (`gui/orders_view.py:303`) and the
  `order_fulfillment_status` in `analysis_data.json` (`core.py:116`) also
  read the first row.

**Scenario.** #1's first line is a custom item without a SKU and its second
is 2 × A, with stock A = 5. Toggling #1 leaves it fulfillable and drops A's
Stock left from 3 to 1.

**Root cause.** Status is stored per line, but it is read as per order.

**Production evidence.** No-SKU lines appear in all 8 HERBAR sessions (2–11
per session). None is an order's first line in this data, because set
expansion moves no-SKU rows to the end for clients with set definitions.
ALMADERM has no set definitions, and there line order is the export's order.

### AUDIT-01-6 — Statistics count an order twice (low)

`recalculate_statistics` counts distinct order numbers among fulfillable rows
and, separately, among not-fulfillable rows. A fulfillable order with a no-SKU
line lands in both. **Production:** HERBAR 2026-07-16_2 saved
`analysis_stats.json` with 11 completed + 14 not completed for 23 orders. Its
`session_info.json` says 12 not completed, which is correct because it is
computed differently. Nothing else in either repo reads
`total_orders_not_completed`, so this is low.

### AUDIT-01-7 — Blank stock cell = unlimited stock (critical, latent)

**What goes wrong.** The Stock column is never coerced to a number. On the path
for stock files without lot columns, a SKU whose stock cell is blank carries
`NaN`. `available == 0` and `required > available` are both false for `NaN`,
so every order for that SKU is marked **Fulfillable** and goes to packing with
nothing on the shelf.

**Root cause.** `_clean_and_prepare_data` coerces Quantity
(`analysis.py:384`) but not Stock. The lot path is safe by accident:
`_build_fifo_lots` maps `NaN` to 0.

**Production evidence: 0 exposure.** All 39 production stock files carry the
`Годност` / `Партида` lot columns, so they take the lot path. Their one blank
stock cell is on a footer row with no SKU, which is correctly dropped. A client
whose ERP export lacks lot columns would hit this.

### AUDIT-01-8 — Duplicate stock rows counted differently by path (high, latent)

Without lot columns, `drop_duplicates(keep="first")` keeps only the first row
of a SKU listed twice. With lot columns, the rows are summed. The same
warehouse file therefore gives 3 or 7 units depending on whether the ERP
exported lot columns. Inventory memory takes yet another row (`.last()`,
`core.py:949`). **Production: 0 exposure.** WATERDROP lists 22 SKUs on several
rows (52 rows), but all of its files take the lot path, which sums them
correctly. The owner chose summing (§6).

### AUDIT-01-9 — Lines before the first order number vanish (low)

Order number is forward-filled, so a line above the first order number stays
blank. `groupby` drops the blank key, and the inner merge with item counts
(`analysis.py:1031`) removes the line from the result. A warning goes to the
log only. A Shopify export always fills `Name`, so this needs a hand-edited
file.

### AUDIT-01-10 — Set CSV import mangles numeric SKUs (low)

`import_sets_from_csv` calls `pd.read_csv` without `dtype=str`, so `0100` and
`0042` become `100` and `42`. The set then never matches the order's SKU, or a
component never matches stock. The order is blocked, not dropped, so a person
sees it. **Production:** all 221 saved set definitions are already clean text,
so the damage only happens on a new import.

### AUDIT-01-11 — Undo of a removal moves the order to the end (low)

The removal undo handlers `pd.concat` the saved rows onto the end. Row content
comes back intact (verified), but the order's position in the table and a
restored line's position within its order both change. The pane's "Remove
this line" addresses lines by position, and it re-checks the SKU before it
removes anything.

### AUDIT-01-12 — Undo history lost for lot-tracked sessions (low)

Since #258, `Lot_Details` holds `datetime.date` objects (`expiry_dt`).
`UndoManager._save_history` writes `json.dump` straight into
`operations_history.json`. The dump raises partway through and leaves a
truncated file. On reopen, `_load_history` hits `JSONDecodeError` and starts
with an empty history. **Production:** all 39 sessions carry lot details. Their
saved histories still parse because they were written by a build older than
#258. On the current build, every edit made in any of the three clients
would lose its undo history when the session is reopened. Undo within the
running session still works.

## 4. Production check

I copied all 39 sessions (ALMADERM 25, HERBAR 8, WATERDROP 6) out of
`production info/` and re-ran `core._load_and_validate_files` and
`_run_analysis_and_rules` on each session's `input/` files. I used the
current client configs with the delimiter set to Auto and an empty history,
and compared the result with the saved `analysis/fulfillment_analysis.xlsx`.

| check | result |
|---|---|
| orders in export = orders in analysis | 39/39 |
| rows in analysis (after set expansion) = rows saved | 39/39 |
| quantity per (order, SKU) | 0 differences |
| status per order | 0 differences in 38. HERBAR 2026-07-17_1: 11 differ. **Config drift**: that run used `multi_first`, and HERBAR is now `fifo`. Re-running it under `multi_first` gives 0. Its re-run, 2026-07-17_2, ran under `fifo` and matches. |
| Auto delimiter on every production file | all 78 files parsed into the mapped columns |

Repeat flags (`System_note`) were not compared, because they depend on the
history at run time.

The edited states (`current_state.pkl`) differ from the runs only in the
ways AUDIT-01-2/3/4 predict. ALMADERM 2026-07-01_2 and 2026-07-02_3 also hold
12 and 8 orders whose lines disagree on status after bulk status changes. That
came from an older build. Bulk verbs now select every line of each order (see
§5), so it is **fixed**, not a finding.

## 5. Verified correct

| area | what was checked | test |
|---|---|---|
| Line and quantity conservation | Repeated same-SKU lines stay separate and are summed for allocation. Row and quantity totals are preserved. Production: 39/39 sessions. | `test_repeated_sku_lines_stay_separate_and_allocate_together` |
| Set decoding | Component quantity × ordered quantity. An unknown SKU stays as a blocked line with the SKU in its reason. | `test_sets_multiply_quantities_and_unknown_skus_stay_visible` |
| Allocation | Competing orders never share a unit, and Stock left is never negative. `fifo` ranks by order number (#9 before #10). `multi_first` takes the multi-line order first. | `test_competing_orders_never_double_allocate` |
| Lot path | Rows of one SKU are summed and the earliest expiry is consumed first. | `test_lot_rows_sum_and_earliest_expiry_goes_first` |
| Folder merge | An overlapping order is taken whole from the newest file, and repeated lines within one file are kept. | `test_folder_merge_conserves_lines_under_the_owning_file_rule` |
| Delimiters | Auto reads a `;` file whose text fields contain commas. | `test_auto_delimiter_reads_semicolon_file_with_commas_in_text` |
| Order-level fields | Tags and shipping method fill within an order, never from the order above. | `test_order_level_fields_fill_within_an_order_only` |
| Bulk status change | Every line of each selected order changes, and undo restores it. | `test_bulk_status_change_touches_every_line_of_each_order` |
| Undo of bulk tag / bulk exclude | Row content is restored exactly (order aside, AUDIT-01-11). | `test_undo_of_bulk_tag_and_bulk_delete_restores_content` |
| Stats after edits | `_update_all_views` recomputes statistics after every edit and every undo. | read: `gui/main_window_pyside.py:973` |

## 6. Business rules (answered by the owner, 2026-09-25)

1. **Stocked set SKUs.** HERBAR stocks 7 of its 10 set SKUs as items in their
   own right, about 6,800 units, and WATERDROP stocks 3 of its 211. The run
   always breaks a set into its components and never uses the set SKU's own
   stock. On HERBAR 2026-07-21_1 that leaves 1 of 38 orders fulfillable.
   **Answer: always split into components.** Today's behaviour is intended,
   so this is not a finding.
2. **Duplicate stock rows without lot columns** (AUDIT-01-8). **Answer: sum
   them**, as the lot path does. Inventory memory should follow the same rule.
3. **Bulk Mark fulfillable** (AUDIT-01-3). **Answer: mark only what Stock left
   covers**, drawing on it as the single-order path does. Skip the orders it
   can't cover, and say in the toast how many were skipped.

## 7. Not covered

- **`analysis_data.json` after edits.** It is written once, at run time, and
  `save_session_state` never rewrites it. Packing Tool's
  `load_from_shopify_analysis` reads it. Whether any reachable Packing Tool
  path packs from it rather than from a packing list is a cross-repo question.
  It is left to Audit 02 and is **unproven** here.
- **Inventory memory seeding** (`core.build_inventory_snapshot`) takes
  `.last()` per SKU, so a SKU stocked on several lot rows and untouched by the
  run is remembered at one lot's quantity. This belongs to Audit 02, which owns
  inventory memory, and is **unproven** here.
- **Rules.** `stats` is computed before the rule engine runs
  (`core.py:853` → `:900`). If a rule can change a status, the saved stats
  predate it. Left to Audit 03.
- **Force-fulfilling an order with a SKU missing from stock** passes the
  toggle's stock check, because Stock left is `NaN` there. The code comment
  says this is intended ("unlisted item, we assume it's on hand"). It is
  recorded here, not raised as a finding.
- `report_filters.py` was read but not tested beyond what its own suite
  covers. Its output is Audit 04's.
