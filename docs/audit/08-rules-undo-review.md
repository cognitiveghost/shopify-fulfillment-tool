# Audit 08: rule engine and undo

Report only, no product code changed. Scope: `shopify_tool/rules.py` (operators, `RuleEngine`), its callers
(`core._run_analysis_and_rules`, the Settings Test panel), and `shopify_tool/undo_manager.py` with the
GUI paths that record and undo operations. Focus: correctness, and speed on realistic volumes.

Evidence tags: **[confirmed-run]** reproduced with a script on the repo's `.venv` (Python 3.14, pandas
3.0.6); **[confirmed-read]** follows directly from the code; **[unconfirmed]** depends on something not
checked here.

Benchmark frame for the timings: 5,000 orders × 3 lines = 15,000 rows, built through
`analysis.run_analysis`.

## Summary

| # | Sev | Area | Finding |
|---|-----|------|---------|
| U1 | High | undo | Undo history survives a re-run of the analysis; undoing an older "remove order" duplicates the order and its stock draw |
| R1 | High | speed | Order-level rules run as a Python loop per order: one rule takes 8.0 s on 5,000 orders |
| R2 | Med | speed | Date operators parse cell by cell, trying up to 6 formats: 3.45 s per condition on 15,000 rows, plus a log line per bad cell |
| U2 | Med | speed | Each undo record stores whole rows; one bulk edit of 6,000 lines writes about 9.9 MB, rewritten on every edit and undo |
| U3 | Med | tests | Most undo handlers have no test; `undo_manager.py` is 55% covered |
| R3 | Low | rules | The Rules page order differs from the run order when a disabled rule has no priority |
| R4 | Low | rules | Text operators disagree on case and whitespace (`equals` is exact, `in list` is not) |
| R5 | Low | rules | `ADD_PRODUCT` copies set-tracking fields from the line it was triggered on |
| U4 | Low | undo | Two PCs on one session overwrite each other's undo history |
| U5 | Low | undo | The "Cleared N future operations" log always says 0 |
| T1 | Low | tooling | `scripts/setup_venv.sh` accepts a Python too old for `requirements.txt` |

---

## High

### U1. Undo survives a re-run of the analysis [confirmed-run]

Undo history is reset only when a session is opened or closed (`gui/main_window_pyside.py:959`, `:984`).
`ActionsHandler.on_analysis_complete` replaces `analysis_results_df` with the new run's frame and leaves
the history alone. Every recorded operation still points at the previous run's frame.

Repro: three orders, then "remove order #2" (recorded the way `remove_entire_order` records it). Re-run
the analysis with the same orders file, then press Undo:

```
can undo after re-run: True
True Undone: Removed order #2
rows for #2 after undo: 2
```

Order #2 is now in the frame twice. `with_stock_left` then draws its stock twice, and both copies go to
packing lists and history. Status and quantity undos are guarded only by `Order_Number` at the recorded
positions (`_restore_columns_by_position`, `:254-266`). When the re-run's layout matches the old one,
they write the previous run's statuses or quantities into the new frame.

**Fix direction:** clear and save the undo history when a run completes, or stamp each operation with
the state stamp it was recorded against and refuse to undo when it differs.

### R1. Order-level rules loop over orders in Python [confirmed-run]

`RuleEngine.apply` (`rules.py:896-945`) loops orders × rules × steps. Each pass takes
`df.iloc[positions]` and evaluates every condition on a tiny frame. For each matched order it also builds
a full-length mask (`pd.Series(False, index=df.index)`) and calls `_execute_actions`, which does `.loc`
writes over the whole frame.

| Rule (15,000 rows, 5,000 orders) | Time |
|---|---|
| article rule, `SKU equals A` → `ADD_TAG` | 0.01 s |
| order rule, `item_count > 1` → `ADD_TAG` (every order matches) | **8.03 s** |
| order rule, `has_sku equals Z` (no order matches) | **2.31 s** |

Each order rule adds its own cost, so five order rules on a busy day add about half a minute to every
analysis run and every Test panel run. Both run on worker threads, so the window stays responsive but
the result is slow. **Fix direction:** evaluate per rule over the whole frame. Use one `groupby`
transform for the order fields (`item_count`, `total_quantity`, ...) and a grouped `any`/`all` for line
fields and `has_sku`/`has_product`. Collect one mask per action and write it once.

---

## Medium

### R2. Date operators parse cell by cell [confirmed-run]

`_op_date_before`, `_op_date_after` and `_op_date_equals` (`rules.py:467-605`) loop over every value
and call `_parse_date_safe`. It tries six formats with one `pd.to_datetime` call each, catching an
exception for every miss. A Shopify `Created at` value (`2026-10-01 10:00:00 +0200`) only matches the
fifth format. Result: **3.45 s for one date condition** on 15,000 rows, against 0.01 s for an `equals`
condition. Every non-blank cell that matches no format also logs a WARNING (`:241`), so one bad column
floods the log. **Fix direction:** parse the whole series once per format
(`pd.to_datetime(series, format=fmt, errors="coerce")`), fill each format's gaps from the next, and log
one summary line.

### U2. Undo records store whole rows [confirmed-run for size, confirmed-read for the write path]

`record_operation` serialises every column of every affected row (`undo_manager.py:70`), keeps up to 20
operations, and `_save_history` rewrites the whole file with `atomic_write_json` after every edit and
every undo, on the GUI thread. One bulk status change over 6,000 lines × 44 columns produced about
**9.9 MB** of JSON. A few bulk edits in one session make every click write tens of MB to the share.
This adds to the per-edit I/O in Audit 07 H2. **Fix direction:** for status, tag and quantity edits,
store only the changed columns plus positions. Keep whole rows only for removals.

### U3. Most undo handlers are untested [confirmed-run]

Across the full suite (3,571 tests), `rules.py` is **77%** covered and `undo_manager.py` **55%**.

These undo paths never run under test:

- the wrong-client and wrong-session guard (`:153-165`)
- the toggle-status fallback when the recorded positions no longer match (`:285-308`)
- the single-order `add_tag` undo (`:320-346`)
- `remove_item` (`:396-407`)
- loading a corrupt history file (`:492-499`)
- `bulk_remove_tag`, `bulk_remove_sku` and `bulk_remove_orders_with_sku` (`:634-714`)
- re-running the analysis between an edit and its undo (U1)

In `rules.py` these never run: `date after` (`:533-558`), every `CALCULATE` branch (`:1270-1303`),
`ADD_PRODUCT` when the SKU is already in the frame (`:1331-1336`), and the order fields
`total_quantity`, `unique_sku_count`, `max_quantity`, `order_volumetric_weight`, `all_no_packaging`
and `has_product` (`:1450-1579`).

---

## Low

- **R3** The Rules page orders all rules, including disabled ones, through `RuleEngine.execution_order`
  (`gui/settings/rules_state.py:317-321`). The engine drops disabled rules **before** it gives the
  default priorities 1000, 1001, ... (`rules.py:745-766`), so the defaults shift. Repro: A (off, no
  priority), B (no priority), C (priority 1000). The page shows A, C, B; the engine runs B, C. The
  docstring says "what it shows is what runs". [confirmed-run]
- **R4** On text, `equals` and `does not equal` are case-sensitive and do not trim (`rules.py:89-90`,
  `:107-108`). `in list` lower-cases and trims, and `contains` ignores case, but `starts with` and
  `ends with` do not. A rule `Shipping_Provider equals dhl` never matches `DHL`. Decide one rule and
  apply it to every text operator. [confirmed-read]
- **R5** `ADD_PRODUCT` copies the triggering row whole (`rules.py:1346-1369`), including
  `Original_SKU`, `Original_Quantity` and `Is_Set_Component`. A gift triggered by a set-component
  line looks like a component of that set. Nothing in this repo reads those fields downstream
  [confirmed-read]; whether Packing Tool does is [unconfirmed].
- **U4** `operations_history.json` is shared by every PC on a session and rewritten whole by each, so the
  last writer wins. The ADR 0011 stale check refuses the follow-up state save, so data isn't silently
  lost, but one PC's undo stack is. [confirmed-read]
- **U5** `record_operation` logs "Cleared N future operations" after slicing, so N is always 0
  (`undo_manager.py:65-67`). [confirmed-read]
- **T1** `scripts/setup_venv.sh` takes the first `python3` whose `venv` has pip and never checks its
  version. Where `/usr/bin/python3` is 3.11 (this review container), install then fails:
  `numpy>=2.5.3` requires Python ≥3.12, and CI runs 3.14. The `.venv` for this review was built with
  `uv venv --python 3.14`. [confirmed-run]

## Test suite

Full suite on the repo's `.venv` (Python 3.14, offscreen): **3,571 passed, 0 failed** in 9 min 9 s.
`ruff check .` passes. The suite is green, but per U3 a green run does not cover the undo paths
most likely to break.

## Suggested order

1. U1: a one-line clear in `on_analysis_complete`, plus a test (the repro above is the test).
2. R1 and R2: vectorise; the existing 48 tests in `tests/test_rules.py` pin the behaviour to keep.
3. U2, then fill the U3 gaps before changing undo storage.
4. The low items, with R3 and R4 needing a one-line owner decision each.
