# Audit 07: core path, multi-PC correctness and share I/O

Report only, no code changed. Scope: the analysis run (`core.run_full_analysis` → `analysis.run_analysis`),
the per-edit save path (`MainWindow.save_session_state`), config caching and saving (`profile_manager`),
the session index (`session_manager`), and the `shared/` write primitives. Focus: correctness and the cost
of operations on a slow Windows file server.

Evidence tags: **[confirmed-run]** reproduced with a script; **[confirmed-read]** follows directly from the
code as written; **[unconfirmed]** depends on something not checked here (Windows/SMB behaviour, Packing
Tool, real timings).

Not covered: rules engine, undo, reports and labels, GUI views, and the test suite's own quality. The
suite was not run in this pass (no `.venv` in the review container).

## Summary

| # | Sev | Area | Finding |
|---|-----|------|---------|
| H1 | High | config | Changing a Setup toggle saves this PC's stale copy of the whole `shopify_config` and silently reverts other PCs' Settings edits |
| H2 | High | speed | Every edit performs six groups of share I/O on the GUI thread, including a full history rewrite and an Excel mirror |
| H3 | High | speed | One session folder without `session_info.json` makes every session listing rescan the whole client tree |
| H4 | High | speed | Any Packing Tool write to any session triggers a full rescan, not a one-entry refresh |
| M1 | Med | allocation | With lot columns, negative stock rows are ignored, so orders are promised stock that the total says is not there |
| M2 | Med | multi-PC | The analysis run writes `current_state.pkl`, `analysis_data.json` and `analysis_stats.json` non-atomically, outside the state lock |
| M3 | Med | correctness | The run reports success when the state save fails, so the session on disk keeps the previous run's results |
| M4 | Med | multi-PC | The 0.3 s replace-retry window is shorter than a slow-share read of a large file |
| M5 | Med | safety | With inventory memory on, config backups rotate out after about 10 edits |
| M6 | Med | config | The run mutates the caller's `column_mappings` from the worker thread; via H1 the set list is saved to disk twice |
| M7 | Med | config | A migration whose save fails makes `load_*_config` return `None` for a readable file |
| L1–L5 | Low | misc | See bottom |

## Verification, 2026-10-05

Re-checked on `origin/main` at `afd2397` (Python 3.14, offscreen). Every finding above still holds. Each High
and Medium finding has a strict-xfail test in `tests/audit/test_07_core_io.py`, named `AUDIT-07-<id>`, and each
was confirmed to fail on its own assertion (`--runxfail`), not on a setup error.

| # | Evidence now | What the test shows |
|---|---|---|
| H1 | confirmed-run | Both the memory switch and the strategy cards drop a rule PC-B saved after PC-A opened the client |
| H2 | confirmed-run (local disk) | One edit on the benchmark frame (15,000 lines) takes **2.7–3.3 s** in `save_session_state` before any share latency, mostly the `current_state.xlsx` mirror. Ceiling in the test: 1 s |
| H3 | confirmed-run | 5 full rescans over 5 listings with one stray folder; 1 without (pinned unmarked) |
| H4 | confirmed-run | One session rewritten by Packing Tool: the next listing rereads all 3 `session_info.json` files |
| M1 | confirmed-run | No lots: `Not Fulfillable, 7, 7`; with a lot column: `Fulfillable, 7, 1` |
| M2 | confirmed-run | `current_state.pkl`, `analysis_stats.json` and `analysis_data.json` are all opened for writing in place |
| M3 | confirmed-run | A pickle write that fails for real (`IsADirectoryError`) still returns `True` with no warning |
| M4 | confirmed-run (simulated) | `os.replace` refused for 1 s: all three writers give up. Windows sharing behaviour itself is still [unconfirmed] |
| M5 | confirmed-run | After 12 memory saves no backup holds the config from before a Settings change |
| M6 | confirmed-run | The caller's `column_mappings` gains `set_decoders` and `additional_columns`. The bug also mutated a shared constant in the new test fixtures, which now deep-copy it |
| M7 | confirmed-run | Both `load_shopify_config` and `load_client_config` return `None` when the migration save hits a locked file |

New, Low, **L6** [confirmed-read]: `_create_backup` names backups to the second, so two saves in the same second
write the same backup name and the second overwrites the first. With M5 this shortens the history further.

---

## High

### H1. A Setup toggle reverts other PCs' Settings changes [confirmed-read]

`gui/main_window_pyside.py:501-512` (`_on_inventory_memory_toggled`) and `:1068-1077`
(`_on_analysis_mode_changed`) call `save_shopify_config(client_id, self.active_profile_config)`.
`sync_inventory_memory()` (`:485-499`) reloads the file from disk, but only copies `inventory_memory`
into the in-memory dict. The whole dict, as loaded when this PC opened the client, is then written back.

**Scenario:** PC-A opens client X at 08:00. At 10:00 PC-B adds a rule or a set. At 11:00 PC-A
switches FIFO / multi-first. PC-B's rule or set is gone, and nobody is told. ADR 0008 accepts
last-writer-wins for *concurrent* writers. This case is a stale snapshot from hours earlier.

**Fix direction:** load fresh, set only the one key, save the fresh dict, then refresh
`active_profile_config` from it.

### H2. Each edit does six groups of share I/O on the GUI thread [confirmed-read; timings unconfirmed]

`save_session_state` (`gui/main_window_pyside.py:707-792`) runs after every DataFrame change,
synchronously:

1. `session_state.save_state`: lock, stat, pickle, replace, stat
2. `fulfillment_history.record_session`: lock, **read the whole all-time history CSV, rewrite it whole**
3. `follow_inventory_memory` (memory on): load config, backup copy, `glob` and unlink old backups, atomic write
4. `current_state.xlsx`: a full Excel rewrite of the frame (a backup mirror only)
5. `analysis_stats.json`: atomic write
6. `update_session_info`: lock, read, write, then a session-index lock, read and rewrite

The code's own ponytail note (`:753`) already flags (2) and (3). Over a slow share, each click freezes the
window for the sum of these round trips. **Fix direction:** keep (1) on the click. Move (2)–(6) to the
threadpool with a per-session coalescing queue, and debounce the Excel mirror (or drop it: the pickle is
the state).

### H3. A stray folder makes every session listing rescan the share [confirmed-run]

`SessionManager._index_is_stale` (`shopify_tool/session_manager.py:398`) returns
`count != len(entries)`. `count` counts every subdirectory. `entries` only holds sessions with a readable
`session_info.json` (`_scan_sessions`, `:404-415`). If one folder has no valid info file (a half-deleted
session after `rmtree(ignore_errors=True)`, a manual `archive` folder, a corrupt JSON), the two never match.
Every `list_client_sessions` call then does a full rescan under an exclusive lock: every analysis run
(`packed_orders.load_session_signals`) and every browser refresh.

Repro (scratch script, three sessions plus one empty folder, five `list_client_sessions` calls):

```
with stray folder : full rescans over 5 list calls: 5
control (none)    : full rescans over 5 list calls: 1
```

**Fix direction:** count only directories containing `session_info.json`, or store the scanned directory
count in the index next to the entries.

### H4. Any Packing Tool write triggers a full rescan [confirmed-read; write frequency unconfirmed]

`_index_is_stale` compares the newest session-directory mtime with the index mtime. When it is stale,
`_rebuild_index` re-reads **every** session's `session_info.json` (`:417-429`). Packing Tool rewrites a
session's `session_info.json` as it packs. While packing is active on another PC, almost every listing
therefore rescans all N sessions over SMB, holding the index lock that blocks other PCs' upserts.
**Fix direction:** refresh only the entries whose directory mtime is newer than the index.

---

## Medium

### M1. Lot (FIFO) allocation ignores negative stock rows [confirmed-run]

`_build_fifo_lots` skips rows with `qty <= 0` (`shopify_tool/analysis.py:210`). The per-SKU total sums
them (`:516-522`). The FIFO simulation checks the lots (`:739`), while the no-lot path checks the total.
The same stock file therefore gives a different answer depending only on whether it has a lot column.

Repro: SKU `A` has rows `+10` and `-3`, and one order needs 9.

```
no lot columns : ('Not Fulfillable', Stock 7, Final_Stock 7)
with lot column: ('Fulfillable',     Stock 7, Final_Stock 1.0)
```

The order is promised 9 units against a displayed stock of 7, and inventory memory then saves 1.
**Fix direction:** decide the owner rule for negative rows (net them against the oldest lots, or cap
lot availability at the SKU total) and apply it in both paths.

### M2. The run's state files are written non-atomically [confirmed-read]

`_save_results_and_reports` writes `current_state.pkl` with a bare `to_pickle` (`core.py:1338`), and
`analysis_stats.json` (`:1346`) and `analysis_data.json` (`:1371`) with `open(..., "w")`. The edit path
uses `session_state.save_state` (lock, atomic replace) and `atomic_write_json`. Another PC opening the
session, or Packing Tool reading `analysis_data.json` mid-write, can get a truncated file. A re-run also
skips the stale-check lock. **Fix direction:** route all three through the existing atomic helpers.

### M3. A failed state save still reports success [confirmed-read]

Failures writing `current_state.pkl` and the JSON files are logged and swallowed (`core.py:1351-1361`,
`:1397-1410`), and the run returns `True`. Fulfilment history and inventory memory are written for the new
run. On a re-run, the old `current_state.pkl` stays, and `on_analysis_complete` stamps it as current
(`gui/actions_handler.py:276-283`). If the operator closes without an edit, reopening shows the
**previous** run's results, while history and memory reflect the new one. **Fix direction:** fail the run,
or at least toast it like `history_warning`.

### M4. The replace-retry window is shorter than a slow read [unconfirmed on production]

`session_state.save_state` (`:62-70`), `fulfillment_history._write_atomic` (`:91-99`) and
`shared/atomic_write.atomic_write_json` retry `os.replace` 3 × 0.15 s. On Windows, replacing a file that
another process has open without `FILE_SHARE_DELETE` fails, and CPython's `open` does not request it.
`fulfillment_history.csv` grows forever (L1), and `current_state.pkl` can be large, so another PC
reading them over a slow share can easily hold them longer than 0.3 s. The history write then fails
(`history_warning`), and the edit fails ("Your last change wasn't saved"). The `atomic_write_json`
docstring says "backoff", but the delay is constant. **Fix direction:** an exponential backoff of a few
seconds total, for `PermissionError` only.

### M5. Config backups rotate out after about 10 edits [confirmed-read]

`_create_backup` keeps the last 10 `shopify_config_*.json` (`profile_manager.py:863-885`). With inventory
memory on, every edit saves `shopify_config` (`save_inventory_memory`, via H2 step 3), so the 10 slots
fill with routine stock writes within minutes. A bad Settings change from earlier the same day cannot be
recovered. **Fix direction:** skip the backup for inventory-memory-only saves, or keep a separate
rotation for them.

### M6. The run mutates the GUI's `column_mappings` [confirmed-read]

`run_full_analysis` takes a shallow `dict(config)` (`core.py:1570`). `_run_analysis_and_rules` then writes
`set_decoders` and `additional_columns` into the **nested** `config["column_mappings"]` (`:897-907`),
which is the GUI's `active_profile_config["column_mappings"]`, from the worker thread. Through H1's save
sites, the full set list is then persisted a second time inside `column_mappings` in
`shopify_config.json`. That makes every load and save over the share larger, and it freezes a legacy
profile's additional columns at run-time values (ADR 0006: `column_mappings` wins). **Fix direction:**
copy `column_mappings` before adding keys.

### M7. A failed migration save hides a readable config [confirmed-read]

In `load_client_config` and `load_shopify_config`, a migration that needs a save calls `save_*_config`,
which raises `ProfileManagerError` on failure (for example, the file is briefly locked by another PC).
The outer `except Exception` turns that into `return None` (`profile_manager.py:522-534`, `:610-612`).
The caller loses the whole config for that call, even though it was read fine. **Fix direction:** return
the migrated in-memory config and log the failed save.

---

## Low

- **L1** `fulfillment_history.csv` is never pruned. Every analysis reads it whole and every edit
  rewrites it whole (H2 step 2), so its cost grows linearly forever. [confirmed-read]
- **L2** `session_info.analysis_report_path` is `analysis/analysis_report.xlsx`, but the file written is
  `fulfillment_analysis.xlsx` (`core.py:1385`). There is no reader in this repo; whether Packing Tool
  reads it is [unconfirmed].
- **L3** `analysis._calculate_final_stock` (`:843`) has no production caller. It is dead code with an
  O(orders × rows) loop. [confirmed-read]
- **L4** `SessionManager._exclusive_lock` unlocks in `finally` even when the lock was never taken
  (Windows `LK_LOCK` gives up after about 10 s), so the unlock error masks the real one
  (`session_manager.py:280-296`).
- **L5** `_merge_results_to_dataframe` builds `System_note` with a row-wise `apply(axis=1)`
  (`analysis.py:1134`). It runs on the worker thread and is cheap to vectorise.

## Suggested order

1. H1 and M6: small, and they stop config loss now.
2. H3: a one-line count fix with a ready repro.
3. M1: needs the owner's rule for negative stock rows first.
4. H2 and H4: the biggest speed win on the share. Worth a short design note: what moves off the GUI
   thread, and an incremental index refresh.
5. M2, M3, M4, M5, M7, then the low items.

Each fix removes the marker from its `xfail(strict=True)` test in `tests/audit/test_07_core_io.py`
(added in the verification pass above).
