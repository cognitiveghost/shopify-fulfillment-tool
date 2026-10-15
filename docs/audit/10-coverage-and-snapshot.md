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
