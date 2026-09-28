# Data layer second review — design

**Todoist:** `6hfMjv86x5PRm7Wv`. **Runner:** run 5, branch
`dr/4-do-second-review-of-data-layer-of-app-re` in both repos.
**Audits:** `docs/audit/06-second-pass.md` (this repo),
`packing-tool/docs/audit/03-second-pass.md`. Read §3 of each for the findings.
**ADR:** 0014 (new), 0010 (binding). **Proof tests:**
`tests/audit/test_06_second_pass.py`, `packing-tool/tests/audit/test_03_second_pass.py`.

Classification: architectural. Lot allocation changes from stored to derived,
which changes a contract that the run, every edit verb and two output writers
depend on. Everything else is a bounded fix inside an existing function.

## 1. Decisions

| # | Decision | Who |
|---|---|---|
| D1 | **Lots are derived like Stock left** (R3, ADR 0014). They are re-allocated from the session's opening lots on every refresh and at the end of the run. | owner, 2026-09-28 |
| D2 | **Summary_Missing is removed.** Summary_Present stays. It and the run's stats are computed after rules. | owner, 2026-09-28 |
| D3 | **Nested sets are expanded.** | owner, 2026-09-28 |
| D4 | A set that lists itself (HERBAR `NECTAR-30` → `NECTAR-30` + dropper) is not expanded when it appears inside another set. Its six HERBAR parents list the dropper themselves, so expanding it would double the dropper. At top level it still expands one level, as today. | agent, told to owner at design approval |
| D5 | One derivation step, `core.with_order_fields`, recomputes `Order_Type`, the weight and box columns, `Stock_Alert` and `Lot_Details`. It runs at the end of `_run_analysis_and_rules` and at the top of `MainWindow._update_all_views`. | agent |
| D6 | The opening lots come from the session's own `input/inventory.csv`, read the way the run reads it. No new file is persisted. Existing sessions, including REVE 2026-09-28_1, are covered. | agent |
| D7 | Units the lots can't cover get one entry `{"expiry": "1", "expiry_dt": None, "batch": None, "qty_allocated": n}`. Both writers already render expiry `"1"` as blank. So every line's list sums to its `Quantity`. | agent |
| D8 | `expiry_dt` is stored as an ISO string (`"2026-12-30"`) or `None`. The lots tooltip prints `f"exp {expiry_dt}"`, which reads the same for a `date` from an old pickle. This fixes AUDIT-06-6 (AUDIT-01-12). | agent |
| D9 | `Order_Type` keeps the run's definition: `Multi` when the order has more than one line of any kind, NO_SKU lines included. | agent |
| D10 | Packing Tool `avg_time_per_item` = sum of the timed orders' `duration_seconds` / sum of those orders' `items_count`. | agent |
| D12 | **Expiry parsing (AUDIT-06-7):** a 4-digit value tries MMYY, then YYMM. A 6-digit value with day `00` is read as YYMM, day 1, before DDMMYY. Every other value parses as before. | agent |
| D11 | A resumed list's elapsed time in its session summary is left as is (packing audit §4). | agent |

## 2. Lot allocation (AUDIT-06-1, D1, D6, D7, D8)

### 2.1 New and changed functions

**`analysis._normalized_stock(stock_df) -> DataFrame`** (new, private). This is
the block now inline in `_clean_and_prepare_data` (analysis.py, "Normalize before
any dedupe" through `stock_df["Stock"] = stock_numeric.fillna(0)`), moved
unchanged. It copies the frame, normalises non-null SKUs with `normalize_sku`,
coerces `Stock` to numeric with blanks as 0, and logs the same warning.
`_clean_and_prepare_data` calls it in place of the inline block.

**`analysis.lot_table(stock_df) -> dict | None`** (new, public). It takes a stock
frame with internal column names and returns `_build_fifo_lots(_normalized_stock(stock_df))`.
The result is `None` without lot columns. The FIFO list per SKU is unchanged.

**`analysis.with_lots(df, lots, mode="multi_first") -> DataFrame`** (new). R3:

```
df["Lot_Details"] = None (object column), on every row
if not lots: return df
left = {sku: [{**lot} for lot in lot_list] for sku, lot_list in lots.items()}   # own copy; qty is consumed
drawing = stock_ledger.drawing_rows(df)            # SKU lines of fulfillable orders (R1)
keys = df["Order_Number"].astype(str).str.strip()
sequence = [str(o).strip() for o in _prioritize_orders(df[["Order_Number"]], mode)["Order_Number"]]
rows_of = keys[drawing].groupby(keys[drawing]).groups      # order key -> row labels, computed once
for order in sequence:
    for idx in rows_of.get(order, []):                     # row order
        sku = df.at[idx, "SKU"]
        if sku not in left: continue                            # unlisted SKU: stays None
        need = pd.to_numeric(df.at[idx, "Quantity"], errors="coerce"); need = 0 if NaN
        entries, take FIFO from left[sku] (lot["qty"] > 0), each entry
            {"expiry": lot["expiry"], "expiry_dt": iso(lot["expiry_dt"]), "batch": lot["batch"], "qty_allocated": take}
        if need > taken: entries.append({"expiry": "1", "expiry_dt": None, "batch": None, "qty_allocated": need - taken})
        df.at[idx, "Lot_Details"] = entries                    # a fresh list per row
return df
```

`iso(d)` is `d.isoformat()` when `d` is a date, else `None`. Rows of one order
with the same SKU draw in row order, which is what the run's per-(order, SKU)
FIFO gave, now split per line. On an unedited frame, the sum of each
(order, SKU)'s entries per (expiry, batch) equals the run's old allocation.

**`stock_ledger.drawing_rows(df) -> Series`** (new, public). It returns
`_sku_lines(df) & in_fulfillable_order(df)`, and an all-False mask for an empty
frame or one without `Order_Fulfillment_Status`. It is the same row set R2
draws from.

**`analysis.run_analysis`**: `_merge_results_to_dataframe` no longer takes
`lot_allocations`. It sets `final_df["Lot_Details"] = None`. `run_analysis` then
calls `final_df = with_lots(final_df, fifo_lots, mode)` before computing stats.
`_simulate_stock_allocation` is unchanged, because its lot pass still decides
fulfillability. Its `lot_allocations` return value just has no reader. Leave it:
removing it is churn in its tests.

**`core.session_lot_table(session_path, config) -> dict | None`** (new):

```
path = Path(session_path) / "input" / "inventory.csv"; if not session_path or not path.exists(): return None
mappings = config.get("column_mappings", {}) or {}
sep = resolve_delimiter(str(path), config.get("settings", {}).get("stock_csv_delimiter", AUTO_DELIMITER), "stock")
raw = pd.read_csv(path, delimiter=sep, encoding="utf-8-sig", dtype=_get_sku_dtype_dict(mappings, "stock"))
return analysis.lot_table(analysis.stock_with_internal_columns(raw, mappings))
```

Any exception is caught and logged with `logger.exception`, and the function
returns `None`. Without a lot table, lines export without lots and the
quantities stay right.

### 2.2 Consumers read each row's own list

- `stock_export._expand_lot_summary`: delete `seen_allocations` and the identity
  check. Every row with a non-empty list adds its entries. Every other row adds
  `Quantity` to the SKU-only bucket. Replace the comment block with one line
  that cites ADR 0014.
- `packing_lists._expand_lot_rows`: delete `seen_order_sku`. Every row with a
  non-empty list expands into one row per entry. Update the comment the same way.

## 3. One derivation step (AUDIT-06-2, D5, D9)

**`core.with_order_fields(df, config, lots) -> DataFrame`** (new). It returns
`df` unchanged when `df` is `None`, empty, or lacks `Order_Number`. Otherwise,
in this order:

1. `Order_Type`: `Multi` if the order has more than one row, else `Single`, from
   `df.groupby(keys)["Order_Number"].transform("size")`. Only when the column
   already exists, so a minimal frame is left alone.
2. When `config.get("weight_config", {}).get("products")` and `SKU` exists:
   `df = enrich_dataframe_with_weights(df, weight_config)`.
3. `_add_stock_alert(df, config)`. It is already a no-op without a threshold.
4. When `SKU`, `Quantity` and `Order_Fulfillment_Status` exist:
   `df = analysis.with_lots(df, lots, config.get("analysis_mode", "multi_first"))`.

Call sites:

- **Run.** At the end of `core._run_analysis_and_rules`, after the rules block,
  always run: `lots = analysis.lot_table(analysis.stock_with_internal_columns(stock_df, config.get("column_mappings", {})))`,
  then `final_df = with_order_fields(final_df, config, lots)`. This also gives
  rule bonus lines their own lots and the right `Order_Type`.
- **GUI.** `MainWindow` gets `self.lot_table = None` in `__init__` and in
  `_reset_session_state`. `self.lot_table = core.session_lot_table(self.session_path, self.active_profile_config)`
  is set in `load_existing_session`, right after `_load_session_analysis`
  succeeds and before `_update_all_views`. It is also set in
  `ActionsHandler.on_analysis_complete` after `self.mw.analysis_results_df = df`.
  At the top of `_update_all_views`, when the frame is non-empty, wrap the call
  in `try/except Exception: logger.exception(...)`:
  `self.analysis_results_df = core.with_order_fields(self.analysis_results_df, self.active_profile_config, self.lot_table)`.
  A failure must not stop the refresh. Use `getattr(self, "lot_table", None)`,
  because some tests build a bare namespace.

Every edit verb, bulk verb and undo already ends in `_update_all_views`,
directly or through `data_changed`, so none of them change. Several bulk verbs
call `save_session_state()` before `_update_all_views()`, so the pickle can
briefly hold the pre-derivation columns. The next save or open corrects them,
and every writer reads the in-memory frame. This is accepted, not fixed.

## 4. Inventory snapshot (AUDIT-06-3)

In `core.build_inventory_snapshot` and `core.inventory_total_units`, group the
stock rows by `stock_df["SKU"].map(normalize_sku)` over the non-null SKUs, not
by the raw column. Nothing else changes.

## 5. Nested sets (AUDIT-06-4, D3, D4)

In `set_decoder.decode_sets_in_orders`, replace the flat component loop with a
recursive helper:

```
def _lists_itself(sku, set_decoders): any(c.get("sku") == sku for c in set_decoders.get(sku) or [])

def _components(sku, qty, set_decoders, path) -> list[tuple[str, number]]:
    out = []
    for c in set_decoders[sku]:
        c_sku, c_qty = c.get("sku"), c.get("quantity")
        (same validation and warnings as today; skip invalid)
        q = qty * c_qty
        nested = c_sku in set_decoders and c_sku not in path and not _lists_itself(c_sku, set_decoders)
        if c_sku in path and c_sku != sku: logger.warning(cycle ...)   # kept as a plain component
        inner = _components(c_sku, q, set_decoders, path | {c_sku}) if nested else []
        out += inner or [(c_sku, q)]
    return out
```

The top-level call is `_components(sku, quantity, set_decoders, {sku})`. Each
returned pair becomes one row as today: `SKU`, `Quantity`, `Original_SKU` = the
top-level set, `Original_Quantity` = the line quantity, `Is_Set_Component=True`.
When the list is empty, the original row is kept, as today. WATERDROP
`S-TG06-BO-6DK3L2` × 1 then yields `DW-GB-GL06-00003` × 1 and
`AI-WA-MX01-00041` × 1. HERBAR `SET_360` is unchanged.

## 6. Run summaries and stats (AUDIT-06-5, D2)

- `analysis._generate_summary_reports` becomes `summary_present(final_df)`,
  which returns only the present frame. It filters with
  `report_filters.fulfillable_only` (R1), not the raw status column. Import it
  inside the function, as `recalculate_statistics` does, to avoid the cycle. The
  Summary_Missing code is deleted.
- `analysis.run_analysis` returns `(final_df, stats)`. Update its docstring.
- `core._run_analysis_and_rules` returns `(final_df, summary_present_df, stats)`.
  After `with_order_fields` it computes
  `summary_present_df = analysis.summary_present(final_df)` and
  `stats = analysis.recalculate_statistics(final_df)`.
- `core._save_results_and_reports` loses its `summary_missing_df` parameter and
  the `Summary_Missing` sheet. `run_full_analysis` unpacks three values.
- Tests that unpack four values from `run_analysis`, or three from
  `_run_analysis_and_rules`, by name are updated. Most use `final_df, *_`.

## 7. Undo history with lots (AUDIT-06-6, D8)

The run and `with_lots` now store `expiry_dt` as an ISO string (§2.1), so
`operations_history.json` serialises. In `gui/pandas_model._format_lot`, print
`f"exp {expiry_dt}"` when `expiry_dt` is not None, which handles both old
`date` values and new strings. Remove the `xfail` marker from
`tests/audit/test_01_intake_analysis.py::test_undo_history_survives_reopen_for_lot_tracked_stock`
and set its status to `fixed` in `docs/audit/01-intake-analysis.md`.

## 8. Packing Tool (packing AUDIT-03-1, D10)

In `packing_tool/packer_logic.compute_order_timing_metrics`, replace the
`item_times` block with:

```
timed = [o for o in orders_with_timing if o.get('duration_seconds')]
units = sum(o.get('items_count', 0) for o in timed)
avg_time_per_item = round(sum(o['duration_seconds'] for o in timed) / units, 1) if units else 0
```

Update the docstring example in `generate_session_summary` and the one-line
contract in the function docstring. No other caller changes. The session detail
page's partial summary uses the same function.

## 8b. Expiry parsing (AUDIT-06-7, D12)

In `analysis._parse_expiry_date`:
- 4 digits: `candidate_specs = [("MMYY", s[2:4], s[0:2], "01"), ("YYMM", s[0:2], s[2:4], "01")]`.
- 6 digits: when `s[4:6] == "00"`, `candidate_specs = [("YYMM00", s[0:2], s[2:4], "01")]`.
  Otherwise the list stays as today.
- Update the docstring's format list. The ambiguity warning is unchanged: `"0101"`
  is valid as both 4-digit formats and logs as ambiguous, keeping MMYY.

## 9. Testing

**Proof tests are committed with the audit** as `xfail(strict=True)`:
`tests/audit/test_06_second_pass.py` (13 tests plus one pin) and
`packing-tool/tests/audit/test_03_second_pass.py`. Each fails on `main` for the
reason its finding names, or on the missing new seam (`lot_table`,
`with_order_fields`). The fix for a finding removes its markers.

Seams to test at:
- `analysis.run_analysis` + `core.with_order_fields(df, config, lots)` +
  `stock_export.create_stock_export` / `packing_lists.create_packing_list`, for
  AUDIT-06-1 and -2. The verbs run through `ActionsHandler` on the
  `window(df)` namespace from `test_01_intake_analysis.py`, copied locally. Its
  `_update_all_views` is a Mock, so the test calls `with_order_fields` itself,
  standing in for the refresh.
- One GUI test in `tests/test_results_screen.py`: set `main_window.lot_table`
  and a frame, call `_update_all_views`, and assert `Lot_Details` is derived.
  This pins the call site.
- `core.session_lot_table` against a `tmp_path` session with an
  `input/inventory.csv` in ERP headers (`Артикул,Годност,Партида,Наличност`),
  and one with no file (→ `None`).
- `core.build_inventory_snapshot`, `set_decoder.decode_sets_in_orders`,
  `core._run_analysis_and_rules` (stats and summary after a `SET_STATUS` rule),
  and `core._save_results_and_reports` via `run_full_analysis` in test mode
  (no Summary_Missing sheet).

**Existing tests that pin the old model get rewritten, not deleted:**
`tests/audit/test_04_outputs.py::test_packing_list_lot_rows_keep_the_order_quantity`
and `::test_stock_export_lot_rows_sum_to_the_allocation`. Both give two rows the
same list. Rewrite them to per-row lists
(`[[L1:2], [L1:1, L2:1]]`, still totalling L1 3 and L2 1) and keep their
assertions. List every such rewrite in the PR body.

**Production replay (manual, before the PR).** A throwaway script outside the
repo loads every `~/Desktop/production info/**/analysis/current_state.pkl`. It
rebuilds lots with `core.session_lot_table(<session dir>, <client config>)` and
applies `with_order_fields`, then checks:
1. the lot export total equals the fulfillable quantity total in every session;
2. in sessions with no manual rows and no removals, the per-(order, SKU)
   `qty_allocated` per (expiry, batch) equals the saved `Lot_Details`
   (superseded at review: saved pickles predate AUDIT-06-7's parser, so 12 of
   40 differ by expiry order. The check run instead re-runs each session from
   its `input/` files and compares `with_lots` with the run's own
   `lot_allocations`: 39/39 identical);
3. REVE 2026-09-28_1 exports `01PJ0001L 1, 01PJ0001S 1`.
Put the counts in the PR body. The client configs are
`~/Desktop/production info/CLIENT_*/shopify_config.json`. REVE has none there,
so use `{}`.

**Gates:** `ruff check . --exclude shared` and the full suite
(`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`) in both repos, then
`graphify update .`.

## 10. Not covered

- The resumed-list elapsed time in Packing Tool summaries (D11).
- `apply_writeoff_to_stock_export` (no caller) and a tag mapped in two writeoff
  categories. Both are recorded in audit 06 §5.
- Multi-session stock export stays per-SKU without lots, by its own contract.
- Pickled `Lot_Details` from before this change keeps `date` values until the
  session is opened, which re-derives them.
