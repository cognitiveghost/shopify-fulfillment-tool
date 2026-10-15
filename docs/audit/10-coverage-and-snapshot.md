# Audit 10: coverage floor and production snapshot findings

Started 2026-10-15 from `~/Desktop/Server./findings.md` (snapshot of 2026-10-11, sections 2 and 5), the
production `log_issues` of the 2.3.1 build, and the coverage pass of part A. Tests:
`tests/audit/test_10_coverage_snapshot.py` unless named otherwise. Each AUDIT-10-k test was committed
as a strict xfail before its fix.

## Already fixed: 2.4 config backups used up by inventory-memory saves

`save_inventory_memory` saves with `backup=False` since AUDIT-07-M5 (PR #371, released in 2.2.1), pinned
by `tests/test_profile_manager.py` ("Settings saves keep a backup; inventory-memory saves don't"). The
snapshot shows no backup from LIDA's 2026-10-09 analysis on 2.3.1. No new id.

## Coverage

| Module | Before | After |
|---|---|---|
| `shopify_tool/core.py` | 68.3 | |
| `shopify_tool/undo_manager.py` | 59.8 | |
| `shopify_tool/groups_manager.py` | 57.3 | |
| `shopify_tool/sku_writeoff.py` | 53.6 | |
| `shopify_tool/tag_manager.py` | 68.3 | |
| `shopify_tool/profile_migrations.py` | 65.2 | |
| `shopify_tool/profile_manager.py` | 75.0 | |
| `gui/client_settings_dialog.py` | 11.1 | |
| `gui/groups_management_dialog.py` | 9.6 | |
| `shared/file_lock.py` | 57.4 | |
| `shared/server_connection.py` | 24.4 | |
| `shared/metadata_utils.py` | 33.3 | |
| **Total** (`shopify_tool`, `gui`, `shared`) | 84.5 | |

## Findings

### AUDIT-10-1: a report file name ending `.XLSX` fails the packing list (finding 2.5)

Found: snapshot finding 2.5, ALMA 2026-10-08 15:15 ("Invalid extension for engine … 'XLSX'").
`_output_file` compared the extension case-sensitively, so `MASKS.XLSX` reached `pd.ExcelWriter`,
which refuses it; a name with no extension (`ALL`) got none, and a stock export named `X.xlsx`
became `X.xlsx.xls`. Fix: one lower-case extension from `Path.with_suffix`.
Test: `test_audit_10_1_*`.

### AUDIT-10-2: the packaging write-off choice resets to "off" every time (finding 2.3)

Found: snapshot finding 2.3, LIDA stock exports from 2026-10-05 written without packaging rows.
`GenerateReportsDialog` checked "Leave packaging materials out" in code on every open, so a client
that wanted write-off had to re-pick it for each export and sometimes did not. Fix: the choice is
stored per client as `last_writeoff_mode` in `shopify_config.json` (saved with `backup=False`, so it
does not use up Settings backups; AUDIT-07-M5) and preselected next time.
Tests: `test_audit_10_2_*`.

### AUDIT-10-3: a list ended with orders unpacked counts as packed (finding 2.1, Shopify side)

Found: snapshot finding 2.1, LIDA 2026-10-02 and 2026-10-05. The Packer writes `status: "completed"`
for a run that ended with orders still unpacked, and `session_lifecycle.packing_completion` trusted
it, so the session read as fully packed. Fix: each packing list's order count is recorded in
`statistics.packing_list_orders` (from the list JSON's `total_orders`); a `completed` block counts only
when its distinct `completed_orders` reach that count. For `full_session` the count is the sum over
the lists, known only when every list has one. A session written before this change has no counts and
keeps today's behaviour. The Packer side (writing `incomplete`) is the packing-tool task.
Tests: `tests/test_session_lifecycle.py` (the five `packing_completion` cases after
`test_a_completed_run_short_of_its_list_is_not_packed`) and `tests/test_report_jobs.py`
(`test_statistics_record_each_lists_order_count`).
