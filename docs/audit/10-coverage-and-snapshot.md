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
| `shopify_tool/core.py` | 68.3 | 84 |
| `shopify_tool/undo_manager.py` | 59.8 | 84 |
| `shopify_tool/groups_manager.py` | 57.3 | 92 |
| `shopify_tool/sku_writeoff.py` | 53.6 | 100 |
| `shopify_tool/tag_manager.py` | 68.3 | 98 |
| `shopify_tool/profile_migrations.py` | 65.2 | 100 |
| `shopify_tool/profile_manager.py` | 75.0 | 89 |
| `gui/client_settings_dialog.py` | 11.1 | 96 |
| `gui/groups_management_dialog.py` | 9.6 | 89 |
| `shared/file_lock.py` | 57.4 | 95 |
| `shared/server_connection.py` | 24.4 | 85 |
| `shared/metadata_utils.py` | 33.3 | 96 |
| **Total** (`shopify_tool`, `gui`, `shared`) | 84.5 | 91.0 |

Measured with `--cov=shopify_tool --cov=gui --cov=shared` over the whole suite (4,042 passed, the three
known ZPL failures, 7 xfailed). Lines that cannot run on Linux, and so stay uncovered: the Windows
`msvcrt` import and the no-`fcntl` fallback in `shared/file_lock.py` (lines 8, 15-16). The total after is
on 16,930 statements; the dead-code removal (Task 11) changed the denominator. The CI gate is
`--cov-fail-under=90` (measured 90.98, rounded down).

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

### AUDIT-10-4: an edit after the packing list was written leaves the old list for the Packer (finding 2.2)

Found: snapshot finding 2.2, ALMA 2026-10-02_2 (a removed line packed and not written off), HERBAR
2026-09-28_1 and 2026-09-29_1. Nothing tied an edit to the lists already on disk. Now each list records
its packing fingerprint (orders + SKU + quantity of fulfillable lines, tags excluded). An edit or a re-run
that changes it moves the unstarted lists to `packing_lists/withdrawn/` and names the started ones; a
failed regeneration withdraws the old list too. ADR 0019.
Tests: `tests/test_report_jobs.py` (fingerprint, withdraw, message), `test_audit_10_4_*` and the window
tests that follow it in the audit file.

### AUDIT-10-5: WeasyPrint warns about `word-break: break-word` on every label run

Found: production `log_issues`, 2.3.1, ×110, last seen 2026-10-09 (WeasyPrint "Ignored `word-break:
break-word`, invalid value"). The label CSS used a value WeasyPrint does not know, so it ignored the
rule and logged it per label. Fix: `overflow-wrap: anywhere` in `barcode_label` and `qr_label`.
Test: `test_audit_10_5_*` (checks the CSS text; a real render is not run here, WeasyPrint is the
dependency that segfaults in some test setups).

### AUDIT-10-6: expiry `"0"` logs a warning for every stock row that carries it

Found: production `log_issues`, 2.3.1, ×11, last seen 2026-10-09 (unparseable expiry "0").
`_parse_expiry_date` treated only "1" as the "no expiry" placeholder; some exports write "0".
Fix: both are "no expiry", silently. Test: `test_audit_10_6_*`.

### AUDIT-10-7: the Results paint timeout is logged as a warning

Found: production `log_issues`, 2.3.1, ×10, last seen 2026-10-09 ("did not report revision N within
… ms"). `when_painted` runs its action anyway when the page is slow to paint, so nothing is wrong
and nobody can act on the line. Fix: INFO. Test: `test_when_painted_gives_up_at_the_timeout_and_says_so`
in `tests/test_web_page.py`. A `shared/` change: packing-tool takes it at its next sync.

### AUDIT-10-8: a bulk tag edit raised `AttributeError` after saving

Found: while writing the AUDIT-10-4 window tests. `bulk_add_tag` and `bulk_remove_tag` called
`ui_manager._populate_tag_filter()`, which the Qt tag filter took with it when the results tier moved to
the web page (Phase 9). On a real window the edit was saved and the undo operation recorded, then the
call raised, so the operator got no toast and the activity log line was skipped. Fix: both calls removed;
`_update_all_views()` already refreshes the page. Tests: `test_audit_10_8_*`.

### AUDIT-10-9: a CSV parse error was reported as a validation error

Found: writing the `core` input tests. In `run_full_analysis` the `except ValueError` came before
`except pd.errors.ParserError`; `ParserError` subclasses `ValueError`, so the "CSV parsing error"
branch never ran and a stock file with a broken quote told the operator "Validation error: Error
tokenizing data". Fix: `ParserError` first. (A cp1251 file is a `UnicodeDecodeError`, also a
`ValueError`; it still reads "Validation error: 'utf-8' codec can't decode…". Left as it is: the text
names the codec, and the operator-facing wording is a UX decision.) Test: `test_audit_10_9_*`.

### AUDIT-10-10: editing a client group without changing it saved and announced an update

Found: writing the groups dialog tests. `_edit_group` compared the colour the picker returns
(`QColor.name()`, lower case) with the stored one case-sensitively, so a stored `#FF0000` never
equalled `#ff0000`, and re-confirming the dialog rewrote `groups.json` (rotating its backup) and
toasted "updated". Fix: compare case-insensitively. Test: `test_audit_10_10_*`.

### AUDIT-10-11: a tag category colour that is not text crashed the validator

Found: writing the `tag_manager` tests. `validate_tag_categories_v2` called `color.startswith` on
whatever the config held, so a hand-edited colour of `123` raised `AttributeError` out of the
Settings validation instead of being listed as an error. Fix: a colour that is not a `#rrggbb`
string is an "invalid color format" error. Test: `test_audit_10_11_*`.

## Replay suite (no id)

`tests/replay/` replays 26 stored production sessions (19 ALMA, 6 HERBAR, 1 LIDA, the golden set of
2026-10-11) through `core.analyse` and compares the result with the `analysis_data.json` each session
stored, and, for the 20 sessions without manual operations, with its packing lists. Fixtures are
anonymised: one shared order-number mapping per client, only the columns the config maps, names and
notes masked down to the words a rule reads, no e-mail, phone or path (`test_fixtures_hold_no_pii`).
Rebuild with `scripts/build_replay_fixtures.py --server ~/Desktop/Server./Server`; the builder replays
each session and refuses one that does not reproduce. 21 of the 26 configs are the nearest backup, not
the exact config of the day (`meta.json: config_exact`): `shopify_config.json` is kept in the session
folder from now on, so later sessions replay exactly. Operation replay (B4) is a follow-up.

## Open questions

- An empty Notes cell is written to `analysis_data.json` and to the packing list as the text `nan`
  (`core._text_or_blank`, kept on purpose "for what each JSON text field has always held"). The Packer
  may show it. Not changed here: it needs a decision on whether the Packer or old sessions depend on it.
