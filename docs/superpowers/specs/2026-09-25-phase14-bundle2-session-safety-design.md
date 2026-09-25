# Phase 14 Bundle 2: session safety and atomic writes — design

**Todoist:** Bundle 2 `6hcgpvFM9WvhH9F3` (parent Phase 14 Audit fixes `6hcg47CqmWj2C4f3`).
**Findings:** AUDIT-05-1 … 05-8 and AUDIT-01-12, reported in `docs/audit/05-sessions-sweep.md`.
Each finding has a strict-xfail proof test in `tests/audit/test_05_sessions_sweep.py`.
**Classification:** bounded. The fixes are known, sit in one module area, and
two owner decisions are already made (below). No UI mockup is involved: the
only UI is error-banner copy.

## Owner decisions

1. **AUDIT-05-3: refuse the stale save** (2026-09-25, in the bundle's Todoist task).
   At load, record what `current_state.pkl` looked like. If the file changed on
   disk before a save, refuse the save and tell the operator to reopen the
   session. There is no session lock.
2. **Stale exports are refused too** (2026-09-25, asked in the Stage A run).
   Generate reports and Export selection run the same check and refuse with the
   same instruction. Without this, a PC that never edits can still ship an order
   another PC held, which is the audit's own scenario.

## Terms (CONTEXT.md, Sessions)

- **Session state**: the session's analysis as saved in `analysis/current_state.pkl`,
  which every edit rewrites whole.
- **Stale**: this PC's copy of the session state is older than the one on the
  server, because another PC saved after this PC loaded or last saved it.

## Design

### Session state module (new: `shopify_tool/session_state.py`)

A small, deep module that owns `current_state.pkl`. Its interface has four names:

| Name | Does |
|---|---|
| `state_stamp(session_path) -> tuple[int, int] \| None` | `(st_mtime_ns, st_size)` of the pickle, or `None` when there is none. |
| `is_stale(session_path, loaded_stamp) -> bool` | `state_stamp(...) != loaded_stamp` |
| `save_state(session_path, df, loaded_stamp) -> tuple[int, int]` | Under a sidecar lock (`current_state.pkl.lock`, `shared.file_lock.locked_file`): refuse with `StaleSessionError` if stale, otherwise write the pickle to a temp file in the same folder, `os.replace` it over the old one, and return the new stamp. |
| `order_counts(df) -> dict` | `total_orders`, `fulfillable_orders`, `not_fulfillable_orders`, with fulfillable meaning `stock_ledger.fulfillable_orders` (R1 from Bundle 1). |

Why the stamp includes the size: file times on the Windows server tick at about
1–16 ms. Two saves in one tick would share an mtime, but an edit almost always
changes the pickle's size. What's left, two saves of the same size in one tick,
gets a `ponytail:` comment naming a version token as the upgrade.

Why a lock around check-and-replace: without it, two PCs can both pass the check
and then both replace the file. The lock covers only the stamp check and the
pickle replace. It does not cover the slow `.xlsx` backup.

`MainWindow._state_stamp` holds this PC's stamp. It is set:
- in `_load_session_analysis`, **before** reading the pickle. If another PC
  writes between the stamp and the read, the next save is refused needlessly,
  which is the safe direction;
- after every successful `save_state`;
- in `on_analysis_complete`, from the pickle `core.run_full_analysis` just wrote;
- to `None` by `_reset_session_state`.

### `save_session_state` (AUDIT-05-3, 05-5, 05-6)

1. `save_state`. On `StaleSessionError`, show an error banner and return:
   *"Another PC changed this session"* / *"Your change wasn't saved. Reopen the
   session from Sessions to load their changes, then make it again."*
   On any other exception, log it, show a banner and return:
   *"Your last change wasn't saved"* / *"Check the connection to the server.
   Your next change saves everything on screen. Details are in Logs."*
2. Best effort, logged only, because the pickle is the state and these files
   only mirror it: write `current_state.xlsx` (in place, as now) and
   `analysis_stats.json` (now through `atomic_write_json`).
3. If the window has a `session_manager`, call `update_session_info` with
   `order_counts(df)`, so the browser's Blocked column follows edits (05-6).
   Logged only on failure.

### Session reset (AUDIT-05-2)

`MainWindow._reset_session_state()` forgets the open session's orders: the
DataFrame, stats, stamp, orders and stock paths and slots, and undo history.
Then it pushes the empty views. It does not touch `session_path`, which each
caller sets. It is called:
- at the top of `load_existing_session`;
- in `actions_handler.create_new_session`, after `create_session` succeeds (a
  failed create leaves the open session as it was);
- in `load_client_config`, replacing that method's inline reset. Its only
  caller, `_on_client_data_loaded`, already clears the slots straight after, so
  this changes nothing there.

### Export check (owner decision 2)

`ActionsHandler._refuse_stale_export() -> bool`. If the session is stale it shows
*"Another PC changed this session"* / *"Nothing was exported. Reopen the session
from Sessions to load their changes, then export again."* and returns True.
If the stat itself fails (`OSError`), it shows *"The session couldn't be checked"* /
*"Check the connection to the server, then export again."* and returns True.
It fails safe. It is called in `open_generate_reports_dialog`, after the
empty-analysis check, and in `bulk_export_selection`, after the empty-selection
check. The multi-session stock export reads pickles from disk and needs no check.

### Session-name collision (AUDIT-05-1)

`create_session` treats `mkdir()` without `exist_ok` as the claim. On
`FileExistsError` it moves to the next number, `N+1`, counting from the name it
tried. It doesn't list the folder again, because the listing may be the stale
one. It gives up after 10 tries with `SessionManagerError`. Cleanup (`rmtree`)
stays in the `except`, but now runs only after this call's own `mkdir`
succeeded, so it can only remove a folder this call created.

### Atomic JSON writers (AUDIT-05-4, AUDIT-01-12)

The four `session_info.json` writers in `session_manager.py`
(`create_session`, `update_session_status`, `update_session_info`,
`append_to_session_list`) and four other in-place writers move to
`atomic_write_json(path, data, indent=2)`. The four others are
`undo_manager._save_history`, `actions_handler._save_manual_addition`,
`sequential_order._write_sequential_order_map` and `barcode_history._save_history`.
`ensure_ascii` changes from json's default `True` to `False` for the session_info
writers. That is safe: Packing Tool reads session_info.json as UTF-8
(`packing_tool/session_manager.py:395,711`, `session_registry_manager.py:297`),
and `apply_status_updates` already writes it that way.

Not converted, because the audit didn't name them and they're out of scope:
`profile_manager.create_client_profile` (new files only), `core.py`'s
analysis-time writes, and the packing-list JSON (a new file per run).

### Comment save (AUDIT-05-7)

`SessionBrowserWidget._on_comments_changed` shows *"The comment wasn't saved"* /
*"Details are in Logs."* on failure, like its sibling `_on_status_changed`.

### `atomic_write_json` fd double-close (AUDIT-05-8, packing-tool)

In packing-tool `shared/atomic_write.py`, drop the inner `try/except: os.close(fd); raise`.
`os.fdopen`'s `with` already owns and closes the fd. Add a packing-tool test in
`tests/test_atomic_write.py`. That branch gets its own packing-tool PR. Sync it
into this repo with `scripts/sync_shared.py <packing-tool worktree>`.

## Proof-test harness changes

The audit tests' assertions stay as they are. Two harness changes are needed,
because the audit harness does things a real PC never does:
- **05-3:** `pc_a = _pc(path, _reopen(path))` copies a loaded DataFrame into a
  fresh namespace and drops what the load recorded. Add `_open_on_a_pc(path)`,
  which returns the loaded namespace, and use it for both PCs.
- **05-3:** `show_error` rejects a non-QWidget source (`TypeError`), so the test
  monkeypatches it, as the 05-5 test already does. It also asserts that PC B
  was told.

## Out of scope

- A session lock or read-only second PC (the owner chose the refusal).
- Two PCs' undo histories (`operations_history.json`): still last-writer-wins.
  A refused save stops the DataFrame, the part that ships.
- Reloading automatically on a stale refusal. The owner's instruction is
  "tell the operator to reopen".
