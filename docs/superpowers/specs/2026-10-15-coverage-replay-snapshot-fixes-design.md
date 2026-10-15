# Coverage, production replay suite and snapshot fixes: design

Task: Todoist 6hjrf9HP39grC3Qv (dev-runner run 88, branch `dr/29-chores-coverage-test`).
Sources: `~/Desktop/Server./CLAUDE.md` and `findings.md` sections 2 and 5 (production snapshot of 2026-10-11).
No mockup: the only UI change is a toast and a preselected radio button.

## Owner decisions (2026-10-15)

| Question | Answer |
|---|---|
| Coverage goal (already 84% overall) | Per-module floor: the modules listed in part A reach 80% each; CI gates the new total |
| "Also log of errors" | Both: fix the warnings the 2.3.1 production logs still show, and keep a written log of every bug the new tests find |
| 2.2 stale packing list | Withdraw lists the Packer has not started; started lists stay, with a warning; tag-only edits withdraw nothing; a failed regeneration also withdraws |
| 2.3 write-off default | The dialog preselects the mode last used for that client |

## Facts this design rests on

- Coverage on `origin/main` (987deaa), statement coverage of `shopify_tool`, `gui`, `shared`: **84.5%**
  (17,013 statements, 2,644 missed; gui 81.8%, shopify_tool 80.3%, shared 79.9%). 3,774 passed; the 3 ZPL
  tests in `tests/test_label_printing.py::TestImageToZpl` fail on main too and are out of scope.
- **2.4 is already fixed.** `ProfileManager.save_inventory_memory` saves with `backup=False` (AUDIT-07-M5,
  PR #371, first released in 2.2.1) and `tests/test_profile_manager.py:339` pins it. The snapshot agrees:
  after 2.3.x was running (ALMA backups switch to the microsecond file name at 2026-10-08 14:54), LIDA's
  10-09 analysis made no backup. The five ALMA backups after that are Settings saves. Nothing to fix;
  B2 (config copied into each session) removes replay's dependence on the backups.
- 2.1, Shopify side: `session_lifecycle.packing_completion` counts a list done when its `packing_progress`
  block says `completed`. The block carries `completed_orders` but no list total, so the fix needs each
  list's order count recorded when the list is written.
- 2.2: the Packer finds lists by scanning `packing_lists/*.json` (non-recursive,
  `packing_tool/session_registry_manager.py:273,762`) and treats a list as started when
  `packing/<list>/` exists. A file moved into `packing_lists/withdrawn/` is invisible to it.
- Every Results edit ends in `MainWindow.save_session_state()` (13 call sites); it is the one choke point.
- The only clock the analysis reads is `analysis._detect_repeated_orders` (`datetime.now()`, line 911),
  plus `analyzed_at` in `core._create_analysis_data_for_packing`.
- Dead code (no caller outside its own module, no test): `core.create_packing_list_report`,
  `core.create_stock_export_report`, `core.create_writeoff_report`, `sku_writeoff.generate_writeoff_report`
  (only called by `core.create_writeoff_report`), `sku_writeoff.apply_writeoff_to_stock_export`,
  `tag_manager.get_tag_category_cached` and `get_config_hash` (only the cached function used it), and `gui/client_settings_dialog.ClientSelectorWidget`. About 150 of core's and sku_writeoff's missed statements.
- Production warnings still logged on 2.3.1 (snapshot `log_issues`, new tree, last seen 2026-10-09):
  WeasyPrint `Ignored word-break: break-word at 90:3` ×110 (label CSS); `Could not parse expiry date: '0'`
  ×11 (`analysis._parse_expiry_date`); `ResultsBridge did not report revision N within 150 ms` ×10
  (`shared/web_page.py` `when_painted`). The four ERRORs of 2026-10-08 are settled in findings 3.2
  (two fixed by #373, one is 2.5, one by design).

## Order of work

One branch, one PR. Parts in this order, each its own commits: **C** (bugs, small and contained),
**B** (replay suite; it changes `core`, which A then measures), **L** (log warnings), **A** (coverage,
measured last so it includes the new code). Operation replay (task B4) is out of scope: a follow-up task.

Every bug, whether from the snapshot (C), the logs (L) or the new tests (A), follows the audit
convention already in `tests/audit/`: a test that fails because of the bug, committed with
`@pytest.mark.xfail(strict=True, reason="AUDIT-10-k: ...")`, then the fix in a later commit removes the
marker. IDs are `AUDIT-10-k`, numbered in the order they are logged.

## The bug log (`docs/audit/10-coverage-and-snapshot.md`)

The written log the owner asked for. One section per finding, the same shape as `07-core-io-review.md`:
id, one-line title, where it was found (snapshot finding, production log line, or the coverage test that
exposed it), what happens, the test that pins it, the fix commit. It opens with the 2.4 note above
(already fixed, no id) and the coverage before/after table. Tests live in
`tests/audit/test_10_coverage_snapshot.py` except where an existing test file is the natural home.

## Part C: snapshot findings

### C1 (AUDIT-10-1, finding 2.5): `.XLSX` report name fails the packing list

`report_jobs._output_file` checks the extension case-sensitively and `"MASKS.XLSX".replace(".xls", ".xlsx")`
leaves it as is; `pd.ExcelWriter` then refuses the upper-case extension. Fix: build the name with
`Path(base).with_suffix(".xlsx")` for packing lists and `.with_suffix(".xls")` for stock exports when
the current suffix, lower-cased, is not already the right one (a name with no suffix gets one; `.XLSX`
becomes `.xlsx`; `.XLS` becomes `.xls`). Test: `_output_file("packing_lists", "MASKS", {"output_filename":
"MASKS.XLSX"}, tmp)` ends in `MASKS.xlsx`, and `generate_report` with that config writes the file.

### C2 (AUDIT-10-2, finding 2.3): write-off defaults to off every time

`GenerateReportsDialog` gains a `writeoff_mode` argument (`"off" | "merged" | "separate"`, default
`"off"`) that checks the matching radio. `ActionsHandler` passes the client's stored mode, read from
`active_profile_config.get("last_writeoff_mode", "off")`. When a batch with a stock export is generated
and its mode differs from the stored one, `ActionsHandler._generate_reports` stores it with
`profile_manager.update_shopify_config(client_id, apply, backup=False)` and keeps the returned config as
`mw.active_profile_config`. `update_shopify_config` gets a `backup: bool = True` keyword passed through
to `save_shopify_config`, so a radio choice never uses up a Settings backup slot (2.4). A failed save
logs and does not stop the reports. Tests: the dialog preselects each of the three modes; generating
with "merged" stores `last_writeoff_mode == "merged"` without creating a file in `backups/`; reopening
preselects it.

### C3 (AUDIT-10-3, finding 2.1, Shopify side): a list ended with orders unpacked counts as packed

When a packing list is written, its order count is recorded. `report_jobs.update_packing_list_statistics`
already writes `statistics.packing_lists` (names on disk); it also writes
`statistics.packing_list_orders: {name: total_orders}` read from each list JSON's `total_orders`
(a list whose JSON cannot be read is left out of the dict).

`session_lifecycle.packing_completion`: a block counts as done only when its status is `completed` **and**,
when the list's count is known, `len(set(completed_orders)) >= count`. For `full_session` the count is
the sum over all lists, known only when every list has one. Unknown count (sessions written before this
change): trust the status, as today. Effect: such a session is not auto-completed and stays `active`;
the browser's existing packed-lists column shows it as not fully packed. No new UI.
Tests in `tests/test_session_lifecycle.py` (or the audit file): 38 of 40 with status `completed` is not
done; 40 of 40 is; no count recorded keeps today's behaviour; `full_session` with a short count is not
done; `is_fully_packed` follows.

The Packer side (writing `incomplete`) is in the packing-tool coverage task, not here.

### C4 (AUDIT-10-4, finding 2.2): an edit after the packing list leaves the old list for the Packer

**Packing fingerprint.** `report_jobs.packing_fingerprint(df) -> str`: SHA-256 of the canonical JSON of
`[(order_number, sorted((sku, quantity) for items))]` for every order of
`core.build_packing_orders(report_filters.fulfillable_only(df))`, orders sorted by number. It covers
which orders ship and what is in them; tags, notes and internal tags are outside it, so tag-only edits
never change it. A status change to or from Fulfillable, a removed or added item, a quantity change and
a removed order all do. The new functions live in `report_jobs.py`, which already imports `core`,
`packing_lists` and `barcode_processor` (`core` imports `packing_lists`, so they cannot go there).
Code says "out of date" or "withdrawn", never "stale": **Stale** is the glossary's word for a PC's old
copy of the session state.

**Recording.** `ReportOutcome` gains `fingerprint: str | None`. `generate_report` sets it, for a packing
list that was written, from the frame snapshot it was given. `update_packing_list_statistics` takes
the batch's outcomes and merges `{name: fingerprint}` into `statistics.packing_list_fingerprints`
(names are the JSON stems; lists removed as empty are dropped from the dict). The window keeps the
same map in memory as `mw._list_fingerprints`: loaded from `session_info.statistics` when a session is
opened (where the window already reads `get_session_info`), updated in `_on_reports_generated` from
the outcomes, cleared when the session closes or another one opens.

**Withdrawing.** In `save_session_state`, after `current_state.pkl` is saved: when
`mw._list_fingerprints` is not empty, compute the frame's fingerprint once; the lists whose recorded
fingerprint differs are stale. For them:

1. submit a write-queue job (new kind `PACKING_LISTS = "packing_lists"` in `gui/session_write_queue.py`)
   running `report_jobs.withdraw_lists(session_path, names) -> list[str]`, which for each name whose
   `packing/<name>/` folder does not exist moves `packing_lists/<name>.json` and `<name>.xlsx` into
   `packing_lists/withdrawn/` (replacing an older withdrawn copy), then calls
   `barcode_processor.invalidate_label_pdfs(session_path, name)` and swallows a `PermissionError` from
   it with a warning (the JSON is already out of the Packer's reach). Returns the withdrawn names;
   started lists are left in place. The same job then calls
   `report_jobs.update_packing_list_statistics(session_manager, session_path)` (today's private
   `_update_packing_list_statistics`, made public), which rebuilds `packing_lists`,
   `packing_list_orders` and `packing_list_fingerprints` from the JSON files still in `packing_lists/`,
   so withdrawn names drop out of all three.
2. on the GUI thread, drop the stale names from `mw._list_fingerprints` (so it warns once per edit that
   staled them) and show one Results toast, role `info`:
   `"Your change makes packing list ALL out of date. Generate it again; until then the Packer can't
   open it."` (plural form for several names). When a stale list's `packing/<name>/` folder exists
   (checked on the GUI thread with one `Path.exists` per stale name, the same cost as the existing
   label-PDF checks), the toast says instead `"ALL is already being packed and still holds the old
   contents. Check it with the packer."` Both sentences when both cases occur.
3. `mw.session_browser.mark_dirty()` when anything was withdrawn, as `_on_reports_generated` does.

The same check runs at the end of a successful `ActionsHandler.on_analysis_complete`: re-running the
analysis in an open session makes its lists out of date just as an edit does. `mw._list_fingerprints`
is therefore not cleared by an analysis, only by `_reset_session_state`.

**Failed regeneration.** In `report_jobs.generate_report`, when `invalidate_label_pdfs` raises
`PermissionError` for a packing list, call `report_jobs.withdraw_lists(session_path, [stem])` before
returning the failed outcome, so the Packer cannot start from the old list while the operator closes the
PDF. The existing error message ("... is open in another program. Close it, then generate again.")
stays.

ADR **0019** records the contract: a Shopify session's `packing_lists/withdrawn/` holds lists withdrawn after
an edit; the Packer never reads it; regenerating writes a fresh list beside it. CONTEXT.md gets the
terms **Withdrawn packing list** and **Packing fingerprint** under Sessions.

Tests (`tests/audit/test_10_coverage_snapshot.py` plus `tests/test_report_jobs.py`; the re-run case too):
fingerprint unchanged by a tag edit and changed by status/item/quantity edits; `withdraw_lists` moves
JSON and XLSX of an unstarted list, leaves a started one, updates statistics; `save_session_state` on a
window double (the pattern of the existing `test_save_session_*` tests) with a recorded fingerprint and
a changed frame withdraws and toasts once, a second save toasts nothing; `generate_report` with a label
PDF held (monkeypatch `invalidate_label_pdfs` to raise `PermissionError`) leaves no
`packing_lists/<name>.json`.

## Part B: production replay suite

### B1: one public entry point

In `shopify_tool/core.py`:

```python
@dataclass
class AnalysisResult:
    final_df: pd.DataFrame
    summary_present_df: pd.DataFrame
    stats: dict
    analysis_data: dict   # the analysis_data.json document

def analyse(
    orders_df: pd.DataFrame,
    stock_df: pd.DataFrame,
    config: dict,
    *,
    history_df: pd.DataFrame | None = None,  # detection frame (packed_orders.union_history_with_packed)
    current_session: str | None = None,
    now: datetime | None = None,             # aware; None = datetime.now().astimezone()
) -> AnalysisResult:
```

It is today's `_run_analysis_and_rules` plus `_create_analysis_data_for_packing`, with `now` threaded
through: `analysis.run_analysis` and `_detect_repeated_orders` take `today: date | None` (`None` keeps
`datetime.now().date()`), and `_create_analysis_data_for_packing(final_df, now)` stamps `analyzed_at`
with it. `run_full_analysis` calls `analyse` and writes `result.analysis_data` as `analysis_data.json`,
so production and replay run one path. `_run_analysis_and_rules` stays as the private body `analyse` calls (it gains `today`; the six tests that call it keep working);
callers of `_create_analysis_data_for_packing` keep working.

Two loaders become public so a replay reads inputs exactly as the app does:
- `core.read_orders_csv(path, column_mappings, delimiter="auto") -> pd.DataFrame`: the `pd.read_csv`
  call `_load_and_validate_files` makes today (SKU dtypes, `utf-8-sig`, `resolve_delimiter`). It replaces
  both copies of that code in `_load_and_validate_files`.
- `packed_orders.signals_from_entries(entries) -> (packed_df, live)`: the body of
  `_load_session_signals` after the `list_client_sessions` call, so a replay passes index entries
  from a fixture. `_to_date` stays private.

`baseline_stock_df` and `read_memory_baseline` are public already.

### B2: the session keeps its config

`_save_results_and_reports`, in session mode, writes `input/shopify_config.json` with
`atomic_write_json`: the `config` the run used, without keys starting with `_`, without
`test_*` keys and without `inventory_memory` (derived data, and the session's stock is in
`memory_baseline.json` or `input/inventory.csv`). A failure to write it logs a warning and does not fail
the analysis. A re-run overwrites it. Test: after `run_full_analysis` in session mode the file exists,
equals the config minus those keys, and has no `inventory_memory`.

### B3: fixtures and the suite

**Builder** `scripts/build_replay_fixtures.py --server <path to Server/> [--client X] [--session S]`.
Committed (it holds no data). It reads the 26 sessions of the `golden_sessions` view (ALMA 19, HERBAR 6,
LIDA 1: `2026-10-09_1`, the owner's rule) from the snapshot files, never from the DuckDB, so it needs
only the tree. The list of 26 is a constant in the script. Raw files are never copied; the script writes
only anonymised output, under `tests/replay/fixtures/`.

Per client, one order-number mapping shared by everything that client's fixtures hold (orders, history,
packed signals, expected files):
- an order number keeps its non-digit prefix and suffix (`#`) and its digit count; the digit run becomes a
  counter: all of the client's numbers of one digit count, sorted numerically, map to
  `10^(n-1) + 1, + 2, ...`. Numbers without digits map to `ORD<k>`.
- orders CSV: keep only the columns named in the config's `column_mappings.orders` keys, the enabled
  `additional_columns` (`csv_name`), and `_source_file`. The column mapped to `Customer` becomes the
  constant `Customer` where non-empty. The column mapped to `Notes` becomes the constant `Note` where
  non-empty (ALMA's rule tests only `Notes is not empty`). SKUs, quantities, product names, prices, tags,
  shipping method, country and dates stay.
- `memory_baseline.json` is copied as is (SKUs, quantities, product names).
- history (`Clients/CLIENT_X/fulfillment_history.csv`): `Order_Number` mapped; other columns as is.
- `sessions.json`: for every session of the client in the new tree, `{session_name, status, created_at,
  packing_progress}` with `completed_orders` mapped (what `signals_from_entries` reads).
- config: the config in force at the session, which is **the first `backups/shopify_config_*.json` taken
  after the session's `created_at`** (a backup holds the content from before its save), else the current
  `shopify_config.json`. Stored once per distinct content under `config/<sha8>.json`, minus
  `inventory_memory`, `last_updated` and `updated_by`. `meta.json` records `config_exact: false` when
  no backup after the session existed (expected for 18 of the 26).
- expected: `analysis/analysis_data.json` with `order_number` mapped and `notes` transformed as the input
  was; `packing_lists/<name>.json` likewise, only for sessions with `operations == 0` in the golden view
  (20 sessions; the 6 with operations are compared on `analysis_data.json` only).

Layout:

```
tests/replay/
  anonymise.py           # pure anonymising functions the builder uses (tested on synthetic data)
  replay.py              # replay_session(fixture_dir) -> (analysis_data, {name: packing_list_json})
  test_replay.py         # parametrised over the 26; plus test_fixtures_hold_no_pii
  fixtures/<CLIENT>/
    config/<sha8>.json
    history.csv
    sessions.json
    <session>/meta.json  # created_at, config file, config_exact, orders file, packing list names + report configs
    <session>/orders.csv
    <session>/memory_baseline.json
    <session>/expected/analysis_data.json
    <session>/expected/packing_lists/<name>.json
```

**Replay** (`tests/replay/replay.py`), for one session: `read_orders_csv` on `orders.csv` with the
config's mappings; `baseline_stock_df(memory_baseline)`; history = `history.csv` without the rows whose
`Session` is this session or a session created after it; packed signals =
`signals_from_entries(entries of sessions created before this one, each packing_progress block kept only
when its started_at is before this session's created_at)`; detection frame via
`union_history_with_packed`; `core.analyse(..., current_session=name, now=created_at)`; packing lists via
`report_jobs.generate_report(report_config, tmp_path, result.final_df, config["tag_categories"],
session_id=name)` for each expected list, the report config found by the list's file stem among
`packing_list_configs` (by `output_filename` stem, else `name`).

**Comparison** ignores `analyzed_at`, `created_at` and `session_id`; everything else, including the order
of orders and items, must be equal. The failure message names the first differing order and field.

**The builder checks itself:** after writing a session it runs the replay on the anonymised fixture and
refuses to keep the session (deletes its folder, exits non-zero naming it) when the result differs from
the anonymised expected files. Findings section 5 replayed all 26 identically on this code; a difference
now is either a mapping that changed the order of orders, or a real regression, and either way a
person decides. The builder never edits an expected file to make it pass.

**PII guard** `test_fixtures_hold_no_pii`: every CSV column in the fixtures is in the allowed set
(the mapped orders columns, `_source_file`, the history columns); no fixture file matches an e-mail
pattern, a `+`-prefixed phone pattern of 9+ digits, a UNC path (`\\`) or a drive path (`X:\`). Before
committing, also read each `config/*.json` once by eye for e-mails and paths, as the task requires.

Cost: about 0.1 s of analysis per session after imports (findings 5), so the 26 add a few seconds to the
suite. They run in the normal suite and in CI.

## Part L: production log warnings (AUDIT-10-5..7)

- **L1** label CSS: `shopify_tool/templates/barcode_label/style.css:90` and `qr_label/style.css:90`
  replace `word-break: break-word` with `overflow-wrap: anywhere`. Test: rendering a label with a long
  unbroken product name through the existing label test path logs no WeasyPrint warning (capture the
  `weasyprint` logger).
- **L2** expiry `'0'`: `analysis._parse_expiry_date` treats `"0"` like `"1"` and blank: no expiry, no
  warning. Test: returns `None` and logs nothing at WARNING.
- **L3** paint timeout: `shared/web_page.py` `when_painted` logs the 150 ms timeout at INFO instead of
  WARNING. The timeout path is handled (the page shows when it paints); on the warehouse PCs it fires on
  large Results frames and is not something an operator or a log reader can act on. Test: the existing
  `when_painted` timeout test asserts the level. `shared/` change: packing-tool picks it up at its next
  sync; say so in the PR.

## Part A: coverage

**Measure:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q --cov=shopify_tool --cov=gui
--cov=shared --cov-report=term-missing` (statement coverage, as the baseline).

**Delete dead code first** (each deletion: grep for the name across `gui shopify_tool shared tests
scripts gui_main.py`, including string uses, before removing it): the dead symbols listed in Facts.
`sku_writeoff` keeps only what `stock_export` and others import.

**Floor: each module below reaches 80%** (baseline in brackets).

| Module | Now | Main gaps (missed statements) |
|---|---|---|
| `shopify_tool/core.py` | 68.3 | `_load_and_validate_files` (43: CSV error paths), `_validate_and_prepare_inputs` (28), `_save_results_and_reports` (18), `validate_csv_headers`, `_validate_dataframes`; plus the dead report functions |
| `shopify_tool/undo_manager.py` | 59.8 | undo of `bulk_remove_tag` (22), `bulk_change_status` (18), `add_tag` (17), `toggle_status` (13), `bulk_remove_sku`, `bulk_remove_orders_with_sku`, `remove_item`, `_load_history` |
| `shopify_tool/groups_manager.py` | 57.3 | `delete_group`, `update_group`, `load_groups`, `get_clients_in_group` |
| `shopify_tool/sku_writeoff.py` | 53.6 | `_extract_writeoff_mappings` once the dead functions are gone |
| `shopify_tool/tag_manager.py` | 68.3 | `validate_tag_categories_v2` (24) |
| `shopify_tool/profile_migrations.py` | 65.2 | `migrate_tag_categories_v1_to_v2` (27), `migrate_delimiter_config_v1_to_v2` (15) |
| `shopify_tool/profile_manager.py` | 75.0 | `add_set`, `delete_set`, `save_set_decoders`, `load_client_config` error paths, `calculate_metadata`, `update_last_accessed` |
| `gui/client_settings_dialog.py` | 11.1 | the whole dialog: create, edit, validate, save result |
| `gui/groups_management_dialog.py` | 9.6 | create, edit, delete group, list load |
| `shared/file_lock.py` | 57.4 | `locked_file` |
| `shared/server_connection.py` | 24.4 | `ConnectionSettingsDialog`, `prompt_for_recovery_path`, retry and browse |
| `shared/metadata_utils.py` | 33.3 | `load_session_summary`, `_validate_v1_3_0_format`, `parse_timestamp`, `calculate_duration` |

Rules for these tests:
- Each test asserts behaviour a user or a caller depends on (a file written, a value returned, a row
  restored, a signal emitted), never only that a line ran. Undo tests do the edit through the same
  `ActionsHandler`/`undo_manager` path the app uses, undo it, and compare the frame with the one before.
- Dialogs are driven with `qtbot`, through their public widgets (fill the fields, click the button) and
  the `ProfileManager`/`GroupsManager` of the existing `profile_manager` fixture on `tmp_path`, never
  modal `exec()`; patch `QMessageBox`/`QFileDialog` statics where the dialog calls them.
- Windows-only branches (`msvcrt`, `os.name == "nt"`) are tested by monkeypatching where the module
  allows it; a branch that cannot run on Linux is listed in the bug log's coverage table with the reason,
  never excluded with `pragma: no cover`.
- A test that exposes a bug becomes `AUDIT-10-k`: strict xfail first, logged, then fixed (see above).
  A behaviour the test cannot decide (is this a bug or the intent?) goes to the bug log as an open
  question, not a fix.

**CI gate:** `.github/workflows/build_release.yml` test step becomes
`python -m pytest --cov=shopify_tool --cov=gui --cov=shared --cov-report=term --cov-fail-under=<N>`,
N = the final total rounded down to a whole percent. No `.coveragerc` (the flags say it all).

## Done when

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` passes except the 3 known ZPL failures,
  `ruff check .` is clean, every AUDIT-10 xfail marker is removed by its fix.
- The 26 replay tests pass; `test_fixtures_hold_no_pii` passes; no raw snapshot file is in git.
- Every module in the table is at 80% or higher; the total is above 84.5%; the CI gate is in place.
- `docs/audit/10-coverage-and-snapshot.md` lists every finding with its test and fix, and the coverage
  table before and after. ADR 0019 and the CONTEXT.md terms exist. `graphify update .` was run.
- The PR body says the `shared/web_page.py` change reaches packing-tool at its next sync, and that the
  Packer side of 2.1 is in the packing-tool task.

## Out of scope

- Operation replay (`operations_history*.json`, `manual_additions.json`) – task B4, a follow-up.
- Relaxing the LIDA golden rule or adding sessions beyond the 26.
- Packer changes (2.1's `incomplete`, refusing a list older than the session's last edit).
- Stock-export comparison in the replay (needs the write-off mode of the day, stored only from C2 on).
- Raising the ten-backup limit.
