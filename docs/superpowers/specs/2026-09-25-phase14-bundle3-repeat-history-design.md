# Phase 14 Bundle 3: repeat detection and history — design

**Todoist:** Bundle 3 `6hcgpv9GWx53mVMV` (parent Phase 14 Audit fixes `6hcg47CqmWj2C4f3`).
**Findings:** AUDIT-02-1 … 02-10, reported in `docs/audit/02-repeat-orders.md`.
Each has a strict-xfail proof test in `tests/audit/test_02_repeat_orders.py`.
**Classification:** architectural. History moves from the run to the session
state and changes shape, detection changes its rule, and the Packer (packing-tool)
changes too. **ADR 0012** records the core decision. Read it first.
**Terms:** CONTEXT.md › Repeat order, Fulfillment history, Packer signal,
Memory baseline, Inventory memory.
**Mockup:** none. The UI changes are one printed column, one web column
default, one Packer chip and one removed settings field, all in existing
components.

## Owner decisions

1. **AUDIT-02-8: flag only, don't hold** (2026-09-25, bundle task). A repeat
   order is marked on the packing list, in the results document (column shown
   by default) and in the Packer. Its status is not changed.
2. **Same-day rule: any live session but Abandoned** (2026-09-25, this stage).
   Another session's orders count whatever the date. A session stored as
   `abandoned`, or deleted, stops counting.
3. **Repeat window: remove the setting** (2026-09-25, this stage).
4. **Packing list: add a Repeat column** (2026-09-25, this stage), in both
   default layouts. Custom layouts can pick it.

## Design

### 1. History module (new: `shopify_tool/fulfillment_history.py`)

This is a deep module: the file's location, shape, lock, merge and atomic
write sit behind four functions. `core.py` loses its two copies of the path
logic, `_load_history_data`'s body and `_merge_fulfillment_history`.

```python
COLUMNS = ["Order_Number", "Execution_Date", "Session"]

def history_path(profile_manager, client_id) -> Path
    # client_dir/fulfillment_history.csv, else get_persistent_data_path(...)
    # (same rule as today). Import get_persistent_data_path at module level
    # here; the audit harness then patches fulfillment_history.get_persistent_data_path
    # instead of core's.

class HistoryUnreadable(Exception): ...

def load(path) -> pd.DataFrame
    # Missing file -> empty frame with COLUMNS.
    # Any other failure (ParserError, UnicodeDecodeError, OSError, ...) -> raise HistoryUnreadable.
    # Read with dtype=str for all columns. A legacy file without Session gets Session="".
    # Order_Number stripped.

def record_session(path, session, df, today=None) -> bool
    # Replace `session`'s rows with the orders df currently ships.
    # Returns False (and writes nothing) when the file is unreadable or the lock times out.
```

`record_session`, step by step:

1. Open `path.with_name(path.name + ".lock")` with `"a+"` and take
   `shared.file_lock.locked_file(lock, timeout=2.0)`. This is the same sidecar
   pattern as `session_state.save_state`. The lock is never on the CSV itself,
   because Windows refuses to `os.replace` onto a file another handle holds.
2. Re-read under the lock with `load(path)`. On `HistoryUnreadable`, log a
   warning and return False. **Never write over an unreadable file**
   (AUDIT-02-6).
3. `ships = stock_ledger.fulfillable_orders(df)`. That is the R1 rule on the
   current state, so it already covers a person marking an order fulfillable
   (AUDIT-02-3) or holding it (AUDIT-02-4).
4. `session` is not None: keep every row whose `Session != session`. For each
   order in `ships`, keep this session's existing date if it had a row,
   otherwise today. The rows of orders this session no longer ships are gone.
5. `session` is None (legacy mode, no session manager): keep the old
   behaviour. Merge `ships` into the rows with `Session == ""`, earliest date
   per order (today's `_merge_fulfillment_history` rule, moved here).
   Sessioned rows are untouched.
6. Write atomically: `tempfile.mkstemp` in the same directory, `to_csv`, then
   `os.replace` with the 3× `PermissionError` retry `session_state.save_state`
   uses. Clean up the temp file on failure. Return True.
7. `FileLockError` or `OSError` anywhere: log, return False. The caller never
   fails because of history.

`today` defaults to `datetime.now().astimezone().strftime("%Y-%m-%d")`. The
parameter exists so tests can fix the date.

### 2. Detection (`analysis._detect_repeated_orders`, `packed_orders.py`)

**Rule (ADR 0012).** For each row in the detection frame
`[Order_Number, Execution_Date, Session, Source]`:

| source | counts when |
|---|---|
| history, `Session` set | `Session != current_session` |
| history, `Session` empty (legacy row) | its date is before today, or unparseable |
| packed (Packer signal) | always (any live session, this one included) |

Rows from sessions that aren't live are removed before detection (see below).
An order is Repeat when any of its rows counts. Compare order numbers as
`str(x).strip()` on both sides (AUDIT-02-5). That is the same rule as
`selection_helper.order_number_mask` and `stock_ledger._keys`.

`current_session` is `Path(session_path).name` whenever `run_full_analysis`
has a `session_path` after step 1, with or without a session manager, and
None otherwise. With None, every sessioned history row counts.

A detection frame without a `Session` column counts as all legacy rows, and one
without `Source` counts as all history. Direct callers in `tests/test_analysis.py`
pass plain `[Order_Number, Execution_Date]` frames.

**Signature changes.**

- `analysis.run_analysis(..., repeat_window_days=1, ...)` becomes
  `run_analysis(..., current_session=None, ...)`. Grep every caller and test.
- `_detect_repeated_orders(final_df, history_df, current_session=None)`.
  The old "no Execution_Date column → whole history counts" branch stays for
  frames without that column.

**Packer signal.** `packed_orders.load_packed_orders` becomes
`load_session_signals(profile_manager, client_id) -> tuple[pd.DataFrame, set[str] | None]`:

- The frame holds packed rows with columns `[Order_Number, Execution_Date, Session]`.
  `Session` is `entry["session_name"]` (fall back to the name of
  `entry["session_path"]`). Dedupe per (Order_Number, Session), earliest date.
- The set holds the **live session names**: every entry whose `status` isn't
  `"abandoned"`. It is None when the index couldn't be read. None means
  unknown, so nothing is filtered: a failed index read must never hide every
  sessioned row.
- One `list_client_sessions` call serves both, so it is one network read as
  today.

`union_history_with_packed(history_df, packed_df, live_sessions)` returns the
detection frame. It adds `Source` ("history" / "packed"), drops rows whose
`Session` is non-empty and not in `live_sessions` (only when it isn't None),
and no longer dedupes across sessions. The legacy-shape early return stays.

**History load in core.** `core._load_history_data` becomes a thin call:

- Test mode (see §4): `config["test_history_df"]`, as today.
- Otherwise `fulfillment_history.load(history_path(...))`. On
  `HistoryUnreadable`, use an empty frame for detection and set
  `history_unreadable = True`. The run then skips its own history write, and
  `stats["history_warning"]` carries the message in §6.

### 3. Where history is written

- **End of a run** (`_save_results_and_reports`): replace the inline history
  block with
  `fulfillment_history.record_session(history_path, current_session, final_df)`.
  Skip it when history was unreadable at load. When `record_session` returns
  False, set `stats["history_warning"]`.
- **Every session-state save** (`MainWindow.save_session_state`, right after
  the successful `session_state.save_state` and before the backups): call
  `record_session(history_path(self.profile_manager, self.current_client_id),
  Path(self.session_path).name, self.analysis_results_df)`. Wrap it in
  `try/except Exception: logger.exception(...)`. Show nothing: the next save
  rewrites the session's full set, so it heals.

The write runs on the GUI thread. It is a 2 s max lock wait plus one CSV
read and write. Mark it with
`# ponytail: history write on the GUI thread; move to the threadpool with a per-session coalescing queue if saves feel slow on the share`.

The history rows are now written by the save path. `session_state.save_state`
itself does not change.

### 4. Test mode and memory mode (AUDIT-02-9)

**Test mode is `orders_file_path is None`, and only that.** The GUI always
has an orders file, including in memory mode. Replace each
`stock_file_path is None or orders_file_path is None` check:

- `_load_history_data`: history is read whenever `orders_file_path` is given.
- `_save_results_and_reports`: returns `(None, None)` only when
  `orders_file_path is None`.
- `_validate_and_prepare_inputs`: copy the orders file whenever it is given,
  and the stock file only when it is given. Update
  `session_info` with `stock_file: None` when there is none.

Update the docstrings that say "None for test mode" on `stock_file_path`.

**Memory baseline** (glossary term). This is `analysis/memory_baseline.json`
in the session:

```json
{"skus": {"SKU": qty, ...}, "names": {"SKU": "name", ...}}
```

- A run with a stock file and memory enabled writes the baseline from the
  stock file (internal columns, **summed** per SKU, negatives clamped to 0).
  It overwrites any earlier baseline, because a stock file is the truth.
- The baseline exists only when the run has a session path. Legacy-mode runs
  read and write none.
- A run without a stock file (memory mode) reads the session's baseline if it
  exists. Otherwise it uses the client's memory and writes that as the
  baseline. Either way the run's stock comes from the baseline, so **a re-run
  never draws the session's orders from memory twice.** This is where
  `_load_and_validate_files` builds its synthetic `stock_df`. It needs the
  session path, so pass it in.
- Use `atomic_write_json` for the baseline.

**Memory records its session.** `ProfileManager.save_inventory_memory` gains
`session: str | None = None` and stores it as `inventory_memory["session"]`.
The run passes `current_session`.

**Memory follows the session state.** In `save_session_state`, after the
history write, when the profile's `inventory_memory.enabled` is true
(`self.active_profile_config`) and the saved memory's `session` equals this
session:

```python
baseline = <session>/analysis/memory_baseline.json -> DataFrame(SKU, Stock)
snapshot = core.build_inventory_snapshot(self.analysis_results_df, baseline_df)
profile_manager.save_inventory_memory(client_id, snapshot, names_dict=..., session=this)
```

`Final_Stock` in the frame is already re-derived after every edit (ADR 0010),
so the snapshot is exact. When memory was last written by a **different**
session, leave memory alone and log at info level: rewriting it from an older
session would erase the later session's draw. Wrap the whole block in
`try/except Exception: logger.exception`.

### 5. Memory sums rows (AUDIT-02-10)

`build_inventory_snapshot` and `inventory_total_units` sum per SKU instead of
`.last()`: numeric-coerce `Stock` first (`pd.to_numeric(errors="coerce")`),
then `groupby("SKU").sum()`, drop NaN, clamp at 0. The `Final_Stock` overlay
stays `.last()`, because `Final_Stock` is already the SKU total on every row.
Fix both docstrings: "one row per SKU" becomes "summed across rows (Audit 01
§6)". `gui/file_handler.py:222` needs no change.

### 6. Surfacing an unreadable history

On a successful run whose `stats` carries `history_warning`,
`ActionsHandler.on_analysis_complete` calls
`self._results_toast(stats["history_warning"])`. The text:

> "Fulfillment history couldn't be read, so this run didn't check or record repeats. Fix or restore fulfillment_history.csv in the client folder. Details are in Logs."

Use it verbatim for both causes: unreadable at load, and write refused.

### 7. The Repeat mark (AUDIT-02-8)

**Results document** (`gui/web/columns.js:35`): add `shown: true` to the
`repeat` column. Saved column settings that list `visible` keep the
operator's choice, which is correct.

**Packing list** (`shopify_tool/packing_lists.py`):

- Before the layout branch, derive
  `sorted_list["Repeat"] = "Repeat"` on an order's first row when any of its
  rows' `System_note` contains `"Repeat"` and doesn't start with
  `"Cannot fulfill"`. That is the rule of `gui/pandas_model.is_repeat`;
  inline it, because `shopify_tool` must not import `gui`. Other rows get `""`.
  It is applied after `_expand_lot_rows` in the lot branch, so the first row
  is the first expanded row.
- Insert `"Repeat"` right after `"Order_Number"` in **both** default layouts
  (lot and non-lot).
- Custom layouts print it only if they list `"Repeat"`. In
  `gui/settings/report_editor.py`, add `"Repeat"` to the packing-list column
  picker's `offered` list (not to `report_filter_fields`, which also feeds
  filters).
- Format: centred (add `"Repeat"` to the centred list), width 8.

**Packer** (packing-tool `gui/packer_bridge.py` `banner()`, `gui/web/packer.js`
`renderBanner()`):

- `banner()` returns a new key, `"repeat": bool`: `system_note` contains
  "Repeat" and doesn't start with "Cannot fulfill".
- `"notes"` is the customer note. Otherwise it falls back to `system_note`,
  **unless** that note is only the repeat mark (`system_note.strip() == "Repeat"`),
  in which case it is empty. The chip carries that information now.
- `renderBanner()` appends `span("chip chip--warning", "Repeat")` straight
  after the order label, when `b.repeat` is true. `.chip--warning` already
  exists in `packer.css`, so no new token is needed.
- This lands as a packing-tool PR, merged **before** the shopify PR is
  released. It works with older shopify builds, because the flag is derived
  from the existing `system_note` field.

### 8. Removing the repeat window (AUDIT-02-2)

- `gui/settings/general.py`: delete the `repeat_days_input` row and its
  `collect()` key. Leave `repeat_detection_days` in saved configs; nothing
  reads it.
- `core._run_analysis_and_rules`: stop reading it. Pass `current_session`
  instead.
- Update `tests/test_settings_page_general.py` and any config fixture that
  asserts the key.

## Proof-test harness changes (`tests/audit/test_02_repeat_orders.py`)

Every AUDIT-02 xfail marker is removed, and each test passes for the reason it
names. Allowed adjustments:

- `Shop.__init__` patches `core.load_session_signals` (renamed) to return
  `(self.packed, None)`. `packed()` gains `session="2026-01-01_1"`, so the
  fake Packer rows carry a session, as the real reader's now do.
- `Shop.write_history(rows)` accepts 2-tuples (legacy rows, `Session=""`) or
  3-tuples. `history_rows()` returns `{order: date}` over all rows. If an
  order has rows in several sessions, keep the earliest date.
- `Shop` patches `fulfillment_history.get_persistent_data_path` (moved from core).
- Tests call `run_full_analysis` in legacy mode, where `current_session` is
  None. **AUDIT-02-3 and -4** need a session. Pass `session_path=str(tmp_path / "2026-09-25_1")`
  through `Shop.run(**kw)`. With no session manager the run stays in legacy
  mode, but `current_session` becomes the folder name (§2). At the "call the
  real writer here" comment, call
  `fulfillment_history.record_session(shop.history, "2026-09-25_1", mw.analysis_results_df)`.
  That is what `save_session_state` calls. The second run uses a **different**
  session path (`2026-09-25_2`). Drop `age_history()` from these two tests:
  the new rule doesn't need it.
- `MemoryProfile.save_inventory_memory` gains the `session=None` keyword.
- **AUDIT-02-1**: the Packer row is today, in another session. With the Packer
  rule it is flagged whatever the date.
- **AUDIT-02-2**: `window=7` is ignored now. Keep the test as written; it
  proves the old minimum-age rule is gone.
- `test_rerunning_the_same_export_today_does_not_flag_its_own_orders` must stay
  green unchanged. In legacy mode both runs write `Session=""` rows dated
  today, and the legacy date rule doesn't count today.
- `test_rerun_keeps_the_earliest_history_date` stays green: legacy merge rule.

New tests, at these seams:

- `tests/test_fulfillment_history.py`, over a tmp file, no Qt:
  - missing file loads empty;
  - an unreadable file raises and `record_session` leaves its bytes untouched;
  - replace keeps other sessions and drops the orders this session no longer ships;
  - dates survive a re-record;
  - legacy file without `Session` loads;
  - no temp files are left behind.
- `tests/test_analysis.py`: the detection-rule table in §2, one test per row,
  plus "abandoned or unknown session ignored" and "live_sessions None filters
  nothing".
- `tests/test_packed_orders.py`: `load_session_signals` returns `Session` and
  the live set. An unreadable index returns `(empty, None)`.
- A memory-mode re-run of the same session leaves memory equal to the first
  run's (no double draw). `save_session_state` on a toggled frame rewrites
  memory only when `inventory_memory.session` matches. Test at the `core`
  level plus one `save_session_state` test with a `Mock` main window, in the
  style of the audit `window()` helper.
- packing-tool: `banner()` with note plus repeat, repeat only, and neither.

## Out of scope

- Labels (barcode, reference) show no Repeat mark. The owner decision names
  the packing list, the results document and the Packer only.
- The `analysis_stats.json` `repeated_orders_found` count (audit §6: no reader).
- Backfilling `Session` into existing history rows. Legacy rows keep the date
  rule and age out of relevance naturally.
- Moving the history write off the GUI thread (the ponytail marker in §3).

## Departures from the Todoist plans

- **Packer rows count from the current session too.** AUDIT-02-1's plan said
  "a different session". Packed is a fact, so an order packed in this
  session and then re-analysed here is flagged. History rows still exclude
  the current session, and that is what keeps the pinned re-run test green.
- **The memory baseline lives in the session (`memory_baseline.json`).** It
  is not a restored pre-run snapshot in the client config. That also covers
  AUDIT-02-9's "inputs not copied" for memory mode.
