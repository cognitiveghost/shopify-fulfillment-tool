# Audit 05: session browser and whole-app sweep

Scope: `gui/session_browser_widget.py`, `gui/session_row_delegates.py`,
`shopify_tool/session_manager.py`, `shopify_tool/session_lifecycle.py`,
`shopify_tool/profile_manager.py`, the open/new-session paths in
`gui/main_window_pyside.py` and `gui/actions_handler.py`, plus a sweep of the
whole app for silent failures, data-loss paths and `shared/` drift. Findings
already recorded in audits 01–04 are not repeated. The history-file
concurrency issues are AUDIT-02-6 and AUDIT-02-7, and the stock-export write
failure is AUDIT-04-2.

Proof tests: `tests/audit/test_05_sessions_sweep.py`.

## 1. Verdict

Browsing is safe. All 39 production sessions list, open and show an accurate
status. Opening a session writes nothing into it, and no session crashed.
**Moving between sessions is not safe.** If the session you open has no
analysis, the previous session's orders stay loaded. Export stays enabled, and
the first edit saves them into the new session. The same happens with New
session (AUDIT-05-2). Two PCs working in one session overwrite each other's
edits without warning (AUDIT-05-3). If two PCs start a session for the same
client within seconds of each other, one of them can delete the other's
session folder (AUDIT-05-1). The owner can rely on the list and on the status
flags, but not on "the session I just opened contains only its own orders"
until AUDIT-05-2 is fixed.

## 2. Findings

| ID | Severity | Summary | Where | Proof test | Status |
|---|---|---|---|---|---|
| AUDIT-05-1 | critical | A session name another PC just took makes `create_session` delete that PC's session folder | `shopify_tool/session_manager.py:161` (fails at `:114`) | `test_a_session_name_another_pc_just_took_is_never_deleted` | confirmed |
| AUDIT-05-2 | critical | Opening a session with no analysis, or starting a new one, keeps the previous session's orders loaded, exportable and saved into the new session | `gui/main_window_pyside.py:918`, `:942`; `gui/actions_handler.py:89` | `test_opening_a_session_without_analysis_drops_the_previous_orders`, `test_a_new_session_starts_without_the_previous_orders` | confirmed |
| AUDIT-05-3 | critical (needs two PCs on one session) | Two PCs in one session: the last save wins and the other PC's holds and edits are lost without warning | `gui/main_window_pyside.py:743` | `test_a_hold_made_on_one_pc_survives_a_save_from_another` | confirmed |
| AUDIT-05-4 | high | `session_info.json` is rewritten in place, so a failed write leaves it torn. The session disappears from the browser and Packing Tool can't read it | `shopify_tool/session_manager.py:144`, `:477`, `:598`, `:645` | `test_a_failed_session_info_write_keeps_the_old_file` | confirmed |
| AUDIT-05-5 | high | A failed save of a person's edits is only logged; the screen still shows the edit | `gui/main_window_pyside.py:759` | `test_a_failed_save_of_an_edit_reaches_the_person` | confirmed |
| AUDIT-05-6 | low | The Blocked column and Needs attention keep the count from analysis time after a person changes statuses | `shopify_tool/core.py:1177` (only writer) | `test_blocked_count_follows_edits` | confirmed |
| AUDIT-05-7 | low | A session comment that fails to save is dropped silently | `gui/session_browser_widget.py:942` | `test_a_comment_that_fails_to_save_is_reported` | confirmed |
| AUDIT-05-8 | low (cross-repo, `shared/`) | A failed `atomic_write_json` closes its file descriptor a second time, which hides the real error and can close another thread's file | `shared/atomic_write.py:33` | `test_atomic_write_reports_the_real_error` | confirmed |

## 3. Findings in detail

### AUDIT-05-1: a session-name collision deletes the other PC's session (critical)

**What goes wrong.** `create_session` picks the next free `YYYY-MM-DD_N` by
listing the client folder, then calls `mkdir()` with no `exist_ok`. If another
PC created that folder after the listing, `mkdir` raises `FileExistsError`.
The `except` block's cleanup then runs `shutil.rmtree(session_path)`, and that
path is the other PC's session. It deletes its inputs, analysis and anything
else already written.

**Scenario.** Two operators press New session for HERBAR at 09:00. The share
holds `2026-09-25_1` and `_2`. Both PCs list the folder and pick `_3`. PC A
creates `_3` and copies its orders file in. PC B's `mkdir` fails, and PC B
deletes `_3`. PC B shows "Failed to create session". PC A carries on in a
folder that no longer exists, and its next write fails or recreates only part
of the folder.

**Root cause.** The cleanup can't tell "I created this and then failed" from
"I never created this". The window is wider than it looks: Windows' SMB
client caches directory listings for about 10 s by default
(`DirectoryCacheLifetime`), so PC B's listing can be seconds out of date.

**Production evidence.** None in the sample: 39 sessions, 1–3 per client per
day, no gaps in the numbering. The deployment is multi-PC by design
(CLAUDE.md), so the precondition is ordinary use.

### AUDIT-05-2: the previous session's orders follow you into the next one (critical)

**What goes wrong.** `load_existing_session` sets `self.session_path` to the new
session and replaces `analysis_results_df` only when the new session has an
analysis to load. The same happens when the session has no analysis yet,
when its analysis files won't load, or when its `session_info.json` is
unreadable. New session (`create_new_session`) never touches it. In each case
the previous session's DataFrame, stock path and statistics stay in memory,
and `update_ui_state` enables export, because `has_session and
has_analysis` is true. Every edit then calls `save_session_state`, which writes
that DataFrame to the **new** session's `analysis/current_state.pkl`.

**Scenario.** An operator finishes session `_1` (40 orders, packed). From the
overflow they choose New session, or they open yesterday's empty `_2`. The
results screen still lists `_1`'s 40 orders. They generate a packing list,
which is written to `_2/packing_lists/` with `_1`'s orders, and Packing Tool
packs them a second time. If they hold one order first, `_2` now permanently
holds `_1`'s analysis, and reopening `_2` tomorrow shows the same thing.

**Root cause.** The analysis state is only ever replaced, never cleared, on
the two paths into a session. The client-switch path
(`gui/main_window_pyside.py:213`) does clear it, and that shows the intended
behaviour.

**Production evidence.** Every production session has an analysis, so opening
them one after another always replaced the state. The failing paths need a
session without one: a New session, or a session created and then abandoned
before analysis. Proof test 1 shows the leaked DataFrame reaching
`current_state.pkl` in the second session.

### AUDIT-05-3: two PCs in one session lose each other's edits (critical, conditional)

**What goes wrong.** Each PC loads `current_state.pkl` into memory once, when
the session opens. Every edit then rewrites the whole file from that PC's
in-memory copy. Nothing locks the session, checks whether the file changed
since it was loaded, or tells either operator that someone else has the
session open. Packing Tool has a session lock with a heartbeat; this tool
doesn't.

**Scenario.** PC A holds order #1001 (bad address). PC B, in the same
session, marks #1002 fulfillable a minute later. B's save carries #1001 as
fulfillable, which is what B loaded, so A's hold is gone. Whichever PC
generates the packing list next ships #1001. The screen on PC A still shows
it held.

**Root cause.** Last-writer-wins persistence with no ownership or version
check.

**Production evidence.** Not visible in saved files. A lost write leaves no
trace. Severity is critical because the result is a held order being shipped.
It is marked conditional because it needs two PCs in one session at the same
time.

### AUDIT-05-4: `session_info.json` is rewritten in place (high)

**What goes wrong.** `create_session`, `update_session_status`,
`update_session_info` and `append_to_session_list` open the file with `'w'`,
which truncates it, and then stream JSON into it. A dropped connection or a
full disk mid-write leaves a truncated file. After that, `get_session_info`
returns `None`, so:

- the session drops out of the browser on the next index rebuild, silently,
  because `_scan_sessions` skips it;
- the index count never matches the folder count again, so every refresh
  after that does a full rescan of the client (`_index_is_stale`);
- Packing Tool's `update_session_metadata` can't parse it and stops
  recording progress;
- `load_existing_session` does nothing visible. AUDIT-05-2 then applies.

`apply_status_updates` already writes atomically, with a comment explaining
this exact risk. The other four writers were never converted.

**Scenario.** Wi-Fi drops while a packing list is being generated
(`append_to_session_list`). The session vanishes from the list, and nobody
can open it from the app.

**Production evidence.** All 39 production `session_info.json` files parse.
The proof test uses a value `json` can't encode as a stand-in for a
mid-write I/O failure, because both fail after the file is truncated.

### AUDIT-05-5: a failed save of an edit is only logged (high)

**What goes wrong.** `save_session_state` runs after every edit: hold, mark
fulfillable, add product, remove, undo. It wraps the whole save in
`except Exception: logger.exception(...)` and tells nobody. The table shows
the edit, but it isn't on disk. When the session is reopened, or someone else
opens it, or it is exported from another PC, the edit is gone.

**Root cause.** The UI thread treats persistence as optional. The comment says
"Don't block UI if save fails", but a failed save is exactly what the
operator needs to see.

**Production evidence.** None readable from files. A failed save leaves the
previous state, which looks valid.

### AUDIT-05-6: the Blocked count never sees a person's edits (low)

`not_fulfillable_orders` is written to `session_info.json` once, at analysis
(`core.py:1177`). Holds and mark-fulfillable change the DataFrame but never
this count, so the Blocked column and the Needs attention group (which fires
on `blocked > 0` for in-flight sessions) describe the analysis, not the
session.

**Production evidence.** In 8 of 39 sessions the stored count differs from
the count in the saved state. 7 of those 8 have edits in their undo history
(for example 30 → 13, 27 → 0 and 11 → 3). The eighth (12 → 14, no edits)
comes from counting by an order's first line against all of its lines. That
difference is already covered by AUDIT-01-5 and AUDIT-04-6.

### AUDIT-05-7: a failed comment save is silent (low)

`_on_comments_changed` logs and returns ("less critical"). The dialog closes
and the refresh shows the old comment, or none. That is the only sign, and
it is easy to miss.

### AUDIT-05-8: `atomic_write_json` closes its fd twice (low, cross-repo)

When `json.dump` fails inside `with os.fdopen(fd, ...)`, the `with` block has
already closed `fd`. The `except` then calls `os.close(fd)` again. That
raises `EBADF`, which replaces the real error, so the log shows "Bad file
descriptor" instead of, say, "disk full". Worse, if another thread opened a
file in between and got the same descriptor number, this closes that
thread's file. The file lives in `shared/`, so fix it in `packing-tool` and
sync it (CLAUDE.md, Shared Module).

## 4. Verified correct

| What was checked | How | Test |
|---|---|---|
| Every production session lists, opens and loads its saved state, with no crash and no error dialog | 39 sessions (25 ALMADERM, 8 HERBAR, 6 WATERDROP) opened through `SessionLoaderWorker.run` and `MainWindow.load_existing_session` on a copy | `test_opening_a_session_writes_nothing_into_it` (pins the no-write half) |
| Opening a session modifies nothing in it | SHA-1 of all 562 session files before and after: only `session_info.json` changed, and only `status` and `status_updated_at`, from the auto-archive pass. The sidecar `.lock` and `session_index.json` files are new. | same |
| The auto-archive pass is the only writer during browsing, and it writes atomically | Production: all 39 were `active`, over 30 days old, not set by a person, so all became `archived`, as designed | `test_bulk_status_updates_write_atomically` |
| Status flags match packing progress | Production statuses as of 2026-07-24, after the derive pass: 26 completed (every one fully packed), 4 stale (lists in progress, idle for 7+ days), 9 not started (no progress, or no lists). `statistics.packing_lists` matches the lists on disk in all 39 | `test_status_derivation_matches_the_production_shapes` |
| Two sessions on one day get distinct numbers | Sequential create | `test_a_second_session_the_same_day_takes_the_next_number` |
| One PC reopening its session gets its last save | Save, edit, save, reopen | `test_one_pc_reopening_its_session_gets_its_last_save` |
| Packing Tool and this tool serialize `session_info.json` writes | Packing Tool's `update_session_metadata` now takes `locked_file` on the same `session_info.json.lock`. The `apply_status_updates` docstring saying it doesn't is out of date | `test_packing_tools_lock_excludes_our_session_info_writes` |
| `shared/` matches packing-tool | `diff -r` against `../packing-tool/shared` and `git diff origin/main -- shared` there: identical | none (needs the sibling repo) |
| Old pickles still load | All 39 production `current_state.pkl` files load under the pinned pandas | production run only |
| Background workers report failures | Every `Worker`/`BackgroundWorker` in `gui/` connects its error signal to a handler that reaches the UI, except the analysis-stats recorder, which is deliberately best-effort | code read |

## 5. Not covered

- **Pickle trust.** `pd.read_pickle` runs code from any `current_state.pkl` on
  the share. The share is trusted by design: anyone who can write there can
  also replace the app. Recorded here, not filed as a finding.
- **Other in-place writers.** `undo_manager.py:415` (undo history),
  `actions_handler.py:1463` (`manual_additions.json`), `sequential_order.py:49`
  and `barcode_history.py:57` have the same in-place write as AUDIT-05-4. A
  torn file there costs undo history or label numbering, not the session
  itself, and none showed up torn in production. The AUDIT-05-4 fix should
  convert them in the same pass.
- **The Packing Tool side of two-PC use.** Packing Tool's own session lock
  was read, not tested.
- **Real SMB timing.** AUDIT-05-1's window was simulated by forcing the stale
  name. Measuring the directory-cache lifetime on the production server needs
  that server.
