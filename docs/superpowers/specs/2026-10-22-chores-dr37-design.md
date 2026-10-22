# Chores dr-37: failing tests, xfails, quick fixes, Dependabot ruff

Todoist 6hmWx82FG6FR2FcM, runner run 100. Two repos, one branch name in each:
`dr/37-chores-failing-test-xfails-quick-fixes-d`.

- **F** = shopify-fulfillment-tool (`/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-37`)
- **P** = packing-tool (`/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-37`)

Size: a bundle of small, independent fixes. No ADR: nothing here is hard to reverse. No mockup: the two
UI touches (a search checkbox, chip wrapping) are small enough to decide here.

## What was found (2026-10-22)

| # | Owner's item | Finding |
|---|---|---|
| 1 | Failing tests "with print" | F: 3 `tests/test_label_printing.py::TestImageToZpl` tests fail **only locally**. The shared dev venv has zebrafy 1.2.2; `requirements.txt` says `zebrafy>=2.0.0`; CI installs 2.x and is green. `scripts/setup_venv.sh` checks only that PySide6/pytest import (`have_deps`), so it never re-syncs requirements. Not a code bug. |
| 2 | xfails | F: 7 strict xfails, all GitHub issue F#370 (`tests/audit/test_07_core_io.py`, `tests/audit/test_09_outputs_sets_ledger.py`). P: none. |
| 3 | BG "Confirm" over the SKU status chip | P: the packer row is HTML in QWebEngine. `gui/web/packer.css:16` gives the actions cell a fixed 448px track; `.row-actions` is `justify-content:flex-end` with no wrap (`packer.css:207`), and kit buttons are `flex-shrink:0; white-space:nowrap` (`shared/web/kit.css:84-96`). All four buttons are always laid out (hidden ones use `visibility:hidden`). The BG labels (Потвърди, Потвърди всичко, Отмени, Съпостави SKU) are wider than 448px together, so the group overflows leftwards onto the 116px status column. |
| 4 | Dependency graph PR, failing ruff | F PR #380 (Dependabot) bumps ruff to 0.17. Ruff 0.17 reports RUF100 "unused noqa (non-enabled: DTZ…)" for 7 directives. DTZ is not enabled in `ruff.toml`, so the directives do nothing on either version. P is already on ruff 0.17 and clean. |
| 5 | Open issues | F#370 (atomic and honest saves) is open and not fixed. P#194 (failed lock release logged as "Lock released") is open and not fixed. No other open issues. |
| 6 | Column manager categories | F: the saved order is already one flat list (`config["ui_settings"]["results_columns"]["order"]`). The categories exist only as headings in the popover (`gui/web/columns.js:7` `COLUMN_GROUPS`, heading loop `columns.js:181-194`). No Python reads them. Removing them means the popover lists columns in the true table order. |
| 7 | Search "precise" mode | F: `gui/web/results.js:239` is a case-insensitive substring test over one joined string (`searchText`, `results.js:258-270`: order number, customer, courier, tags, SKU, product name, lot batch/expiry). |
| 8 | Packer shows old list after regeneration | Owner: regenerated a list in F with the list never opened in P; P still showed 16 orders, the new file has 18. **Root cause (P):** `SessionRegistryManager.refresh_available_lists` (`packing_tool/session_registry_manager.py:733+`) skips every key already in `registry_index.json` (`if key in known_keys: continue`), so an unstarted list rewritten under the same name keeps its old registry entry (old `total_orders`, `created_at`). The packer does read the JSON fresh when the list is opened, so the stale data is the browser's entry. **Contributing (F):** `shopify_tool/report_jobs.py` writes the XLSX before the JSON; if the XLSX write fails the old JSON stays and is not withdrawn, and a JSON write error is logged and swallowed (`report_jobs.py` ~209-213) while the run reports success. |
| 9 | Results page visual bugs with filters | No written report exists. Owner: filtered to Fulfillable in a session with many unfulfillable orders, clicked a row, "an additional order line appeared visually in the table". Not reproduced offscreen (Linux software rendering, 100% and 125% scale): the DOM held exactly the filtered rows. Code suspects: (a) `recompute()` never resets the scroller, so the first `renderRows()` after a filter reads the old `scrollTop`, draws zero rows, and the browser's later scroll clamp triggers a second render; (b) `.chips { overflow:hidden }` with non-shrinking chips (`gui/web/results.css:97-112`) clips chips silently at narrow widths. |
| 10 | Tidy | Nothing is clearly dead. Owner chose to delete four groups, listed below. |

## Owner's decisions (run 100, questions 85 and 86)

- **Search mode:** a "Starts with" checkbox. When on, an order matches if **any** searched field starts with the text.
  The order number is also matched without its leading `#`. `4` finds `#4010`, not `#1140`.
- **Results bugs:** fix the suspects; try to reproduce the extra-row report at Windows-like scaling; add a guard.
  The owner sends a screenshot if it happens again.
- **Tidy:** delete all four candidate groups (below).
- **Stale list:** the scenario above (never opened in P).

## Design, per item

### 1. Local test failures (F)
`scripts/setup_venv.sh`: when the venv is already good (step 1, both the "already good" and "linked" paths), run
`"$REPO/.venv/bin/python" -m pip install -q -r requirements.txt -r requirements-dev.txt` so a floor bump in
`requirements.txt` reaches the shared venv. Then run the script once, so the shared venv gets zebrafy 2.x, and
confirm `TestImageToZpl` passes. No change to `label_printing.py`. Because the venv is shared, this also upgrades
the main checkout's venv. That is intended, since it should match requirements.

### 2 + 5a. F#370: atomic and honest saves (removes all 7 xfails)
Follow the issue's proposal exactly:
- `shopify_tool/core.py` `_save_results_and_reports`: write `current_state.pkl` through `session_state.save_state`
  and both JSON files (`analysis_stats.json`, `analysis_data.json`) through `shared/atomic_write.atomic_write_json`.
- One retry helper in `shared/atomic_write.py`: exponential backoff for `os.replace`, a few seconds in total,
  retrying on `PermissionError` only. Used by `atomic_write_json`, `session_state.save_state` and
  `fulfillment_history._write_atomic` (today each retries 3 × 0.15 s).
- **07-M3, decided (issue's recommendation (a), the agent's call):** a failed state save does not fail the run. It sets
  a `*_warning` stat that `gui/actions_handler.py` `on_analysis_complete` shows as a toast, the same way it already
  shows `history_warning`. Reason: history and inventory memory are already written by then, so failing the run
  would hide a half-saved result rather than undo it.
- 09-O5: the packing-list JSON is written with `atomic_write_json`, and a failed `_create_analysis_data_for_packing`
  raises instead of saving `{"orders": []}`.
- Done when the 7 tests pass and their `xfail` markers are removed. `shared/` changes reach P at its next sync;
  the F PR says so.

### 3. Packer Confirm overlap (P)
- `gui/web/packer.css`: widen the actions track in `--pm-cols` so all four buttons fit in Bulgarian. Measure
  the real widths in a render. Also give `.row-actions` `min-width:0` and `overflow:hidden` (or `flex-wrap:wrap`),
  so a future longer label stays inside its own cell instead of covering the status chip.
- Check that the layout still fits the 1366px window in both EN and BG and in both themes. The product column
  (`minmax(0,1fr)`) is the one that gives up width.
- Test: extend `tests/test_packer_scanner_focus.py`'s offscreen render pattern. With `lang=bg`, the Confirm
  button's left edge must be at or right of the status cell's right edge. Save a PNG and look at it.

### 4. Ruff 0.17 (F)
Delete the 7 unused `# noqa: DTZ…` directives: `scripts/build_replay_fixtures.py:80`,
`shopify_tool/analysis.py:918`, `tests/replay/test_anonymise.py:1` (file-level `# ruff: noqa: DTZ001` line),
`tests/test_session_lifecycle.py:98`, `tests/test_stats_manager.py:137,138,148`. Keep any other code on those lines.
Do not bump the ruff pin here. Dependabot PR #380 does that and goes green once this merges.

### 5b. P#194: lock-release failure (P)
`release_lock()` returns `False` and never raises. At the three call sites in `gui/main_window.py` (cleanup
~1080-1086, ~1167-1173, `_teardown_session` ~1686-1693), log "Lock released" only when it returns `True`.
Otherwise log a WARNING naming the work dir and saying the `.session.lock` was left behind. In
`_teardown_session` only, also tell the operator with `self._toast(<message>, role=<the warning role toast
supports>)`. The message says the list may still look open on other PCs until the lock is removed. The text goes
through `_()` with a BG entry in `locales/bg.json`. The `try/except` stays for unexpected errors.

### 6. Column manager without categories (F)
`gui/web/columns.js`: list the columns in `orderedColumns()` order with no group headings or group counts.
Remove `COLUMN_GROUPS`, `GROUP_TITLES`, the per-column `group` field and the `.col-group*` CSS once nothing
uses them. The popover's own search still filters rows by title. Move up/down and drag-drop already work on
the flat order and keep working. Persistence is unchanged. Update or remove the tests that assert groups
(`tests/test_results_columns.py` ~260 "search groups" and ~282 "group count", plus any
`tests/test_results_bridge.py` / `tests/test_results_screen.py` asserts on group headings). Add one test: the
popover's row order equals the table's column order. Remove BG catalogue entries that become unused only if
the i18n guard tests require it.

### 7. "Starts with" search (F)
- `gui/web/results.html`: a checkbox right after the search input, inside `#filterbar`, labelled "Starts with"
  (BG "Започва с"), styled like the kit's existing checkbox (the table's select box). Words go through the
  page's `data-i18n` mechanism and `locales/bg.json`.
- `gui/web/results.js`: each record keeps a list of its searched fields, lowercased (`record.fields`), built
  from the same parts as `searchText`. The order number is added twice: as-is and without a leading `#`. With
  the box off, matching is unchanged (`hay.includes`). With it on, a record matches if
  `fields.some(f => f.startsWith(query))`.
- The setting lasts while the app runs, including across session changes, and resets to off on restart. Not
  persisted (agent's call; persisting needs a new bridge slot, so add it only if the owner asks).
- Tests in `tests/test_results_document.py`, with a small fixture where prefix and substring differ (orders
  `#4010` and `#1140`, query `4`): box on, so `#4010` only. Box off, so both. Box on, a SKU prefix matches and a
  mid-SKU substring does not.

### 8. Stale packing list after regeneration
- **P, the fix:** `refresh_available_lists` also re-reads known **available** (unstarted) lists whose JSON changed.
  Each available entry stores the JSON's `mtime` (from `pl_entry.stat().st_mtime`, which is free from `os.scandir` on
  Windows). On refresh, a known available key whose stored `mtime` differs, or is missing (legacy entries), is
  registered again from the file, replacing the old entry under the registry lock. A known available key whose
  JSON is gone (withdrawn by F, ADR 0019) is removed from `available_lists`. Entries in `sessions` (started
  lists) are not touched. `_register_available_from_file` and `register_available_list` record `mtime`.
- **P test:** register a list with 16 orders and refresh. Rewrite the JSON with 18 orders and a new mtime
  (`os.utime`), refresh again, and `get_available_lists` reports 18. Delete the JSON, refresh, and the entry is
  gone. A started list is untouched.
- **F, the contributing writer path** (`shopify_tool/report_jobs.py` `generate_report`, packing_lists branch): a JSON
  write error is no longer swallowed. It fails the outcome (`failed=True`). Any failure in the packing_lists branch
  after the old files could have diverged (XLSX write failed, JSON write failed) withdraws the list with
  `withdraw_lists(session_path, [stem])` before returning `failed`, as the label-PDF-lock path already does, so the
  packer can never open the previous run's JSON. Correct the overstated comment near `report_jobs.py:264`. The JSON
  write itself becomes atomic under #370 (09-O5).
- **F test:** XLSX write raises `PermissionError`, so the outcome is failed and the old JSON is in `packing_lists/withdrawn/`.
  JSON write raises, so the outcome is failed and the list is withdrawn.

### 9. Results filters (F)
- **Scroll guard:** when the filter or search changes (chip toggled, chip removed, clear all, search input,
  mode checkbox), set `els.scroller.scrollTop = 0` before rendering. `recompute()` is also called by sort and
  row clicks, which must not jump, so do it at those call sites (a small `filterChanged()` helper), not in
  `recompute()`. Test: scroll down, apply a filter, and the rows drawn on that same render equal
  `min(visible, view.length)` with the first view row at top 0.
- **Chips:** `.chips` wraps (`flex-wrap: wrap`) instead of clipping. The filter bar grows taller and the
  existing `ResizeObserver` re-lays the table rows. Test at a narrow width with 4+ chips: every chip's rect is
  inside the viewport, and the table still shows whole rows.
- **Repro attempt:** Stage B re-runs the owner's scenario (mostly unfulfillable session, filter Fulfillable,
  click a row) at `QT_SCALE_FACTOR` 1.25 and 1.5 and records what it saw in the runner notes. If it does not
  reproduce, the guard above ships and the item stays watch-only, waiting for the owner's screenshot.

### 10. Tidy (both repos)
Delete (owner's choice):
- P `docs/design/i18n-renders/packer/` (30 PNG, referenced nowhere).
- `docs/design/ui-refresh/current/` in **both** repos (old before-shots, cited only by shipped specs).
- F `docs/superpowers/plans/*` for merged work. Keep this task's own plan. Fix the links in
  `docs/superpowers/roadmap.md` (or wherever `rg` finds references) to say the plans are in git history.
- F `docs/audit/repro/*.py`, **after** #370 lands in the same branch. Fix the one citation in the deleted plans
  (gone with them) and any other `rg` hit.
Before each deletion: `rg` for the path, and confirm no test, CI workflow, PyInstaller spec or script reads it.
Code comments that cite a deleted doc path stay as they are (CLAUDE.md: such paths are in git history).

## Non-goals
- No changes to `label_printing.py` or zebrafy usage.
- No ruff version bump here. No merging of #380.
- No persisted search mode. No new column categories or column presets.
- No change to how P reconciles a **started** list with a regenerated JSON (AUDIT-01-3 already toasts list changes).
- No rewrite of the Results virtual list.

## Constraints
- F gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`. CI keeps 90% coverage.
- P gate: same, run in P.
- No bare UI strings: `_()` / `data-i18n` plus `locales/bg.json`. The guard tests in F `tests/test_i18n_catalogue.py`
  (and P's equivalent) must pass.
- Theme tokens only, no hardcoded colours.
- `shared/` is edited only in F. P picks it up at its next sync, and the F PR says so.
- Two PRs, one per repo, both on `dr/37-chores-failing-test-xfails-quick-fixes-d`.

## Left to the builder
- The exact width of the packer actions track (measure it).
- The exact backoff numbers for the #370 retry helper (a few seconds in total, `PermissionError` only).
- The checkbox markup details, within the kit's existing checkbox style.
